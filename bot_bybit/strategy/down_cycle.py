import asyncio
import time
import numpy as np
from aiogram import Bot
from bybit_api.detector import get_price
from bybit_api.balances import balance_usdt
from bybit_api.client import client
from config import SYMBOL, DOWN_LEVELS
from strategy import state as st
from bybit_api.price_cache import get_price_cached
from strategy.trade_stats import register_trade   # <-- главное!


# ===================== ATR CALCULATION =====================
def calc_atr_percent() -> float:
    """
    Реальная ATR-адаптация:
    Берём последние ~50 цен, считаем средний TR и нормализуем.
    """
    prices: list[float] = []

    try:
        for _ in range(50):
            prices.append(get_price())
    except Exception as e:
        print("ATR calc error:", e)
        return 0.02  # fallback: 2%

    if len(prices) < 3:
        return 0.02

    tr_list = [abs(prices[i] - prices[i - 1]) for i in range(1, len(prices))]
    atr = float(np.mean(tr_list))
    last = prices[-1]

    if last <= 0:
        return 0.02

    atr_percent = atr / last

    return max(0.005, min(atr_percent, 0.05))   # 0.5%–5%


# ===================== RESET DOWN VARS =====================
def reset_down_vars():
    st.down_active = False
    st.down_base_price = None
    st.down_usdt_total = None
    st.down_usdt_per_level = None
    st.down_levels_completed = 0
    st.down_sell_orders = []

    # очищаем массивы уровней (если нужны)
    st.down_entry_prices = []
    st.down_qty_list = []


# ===================== ENTER DOWN MODE =====================
async def enter_down_mode(chat_id: int, last_price: float, bot: Bot):

    st.trade_mode = "DOWN"
    st.down_active = True

    st.down_base_price = st.entry_price_up if st.entry_price_up else last_price

    usdt = balance_usdt()
    if not isinstance(usdt, (int, float)) or usdt <= 0:
        await bot.send_message(chat_id, "❌ Нет USDT для DOWN-режима.")
        st.trade_mode = "UP"
        st.down_active = False
        return

    st.down_usdt_total = float(usdt)
    st.down_usdt_per_level = round(usdt / DOWN_LEVELS, 2)

    # для отображения — первый уровень -0.0060
    down_base_price_60 = round(st.down_base_price - 0.0060, 4)

    await bot.send_message(
        chat_id,
        f"📉 Переход в режим торговли вниз DOWN\n\n"
        f"Базовая цена : *{st.down_base_price}* (ждём ≈ *{down_base_price_60}*)\n"
        f"Текущая цена : *{last_price}*\n\n"
        f"Всего USDT для откупа : *{st.down_usdt_total}*\n"
        f"На уровень (~) : *{st.down_usdt_per_level}*\n"
        f"Уровней : *{DOWN_LEVELS}*\n"
        f"ATR-адаптация активна ⚡",
        parse_mode="Markdown"
    )

    asyncio.create_task(down_mode_cycle(chat_id, bot))


# ===================== MAIN DOWN CYCLE =====================
async def down_mode_cycle(chat_id: int, bot: Bot):

    await bot.send_message(chat_id, "✔ DOWN-режим активирован\nЖдём уровни падения 🔍")

    while st.down_active:
        await asyncio.sleep(2)

        try:
            price = get_price_cached()
        except Exception as e:
            print("down_mode_cycle price error:", e)
            continue

        if st.down_base_price is None:
            st.down_base_price = price

        base = st.down_base_price
        lvl = st.down_levels_completed + 1

        # ----------- ATR + базовый шаг сетки -----------
        atr_percent = calc_atr_percent()
        grid_step = 0.03
        hybrid_step = grid_step + atr_percent

        # ----------- усиление сетки при глубоком падении -----------
        drawdown = (base - price) / base if base > 0 else 0
        extra = 0
        if drawdown > 0.20:
            extra += 1
        if drawdown > 0.35:
            extra += 1
        if drawdown > 0.50:
            extra += 1

        # ----------- уровень цены -----------
        if st.down_levels_completed == 0:
            target_price = round(base - 0.0060, 4)   # фиксированный первый уровень
        else:
            target_level = lvl + extra
            target_price = base * (1 - hybrid_step * target_level)

        # ------------------ ОТКУП УРОВНЯ ------------------
        if price <= target_price and st.down_levels_completed < DOWN_LEVELS:

            part = st.down_usdt_per_level
            if part is None or part <= 0:
                await bot.send_message(chat_id, "❌ Ошибка: часть депозита для уровня = 0.")
                reset_down_vars()
                st.trade_mode = "UP"
                return

            try:
                buy = client.place_order(
                    category="spot",
                    symbol=SYMBOL,
                    side="BUY",
                    orderType="Market",
                    qty=int(part),
                    marketUnit="quoteCoin"
                )
            except Exception as e:
                await bot.send_message(chat_id, f"⚠ Ошибка покупки DOWN : {e}")
                continue

            buy_id = buy["result"]["orderId"]

            # ждём историю ордера
            lst = []
            for _ in range(3):
                h = client.get_order_history(category="spot", orderId=buy_id, symbol=SYMBOL)
                lst = h.get("result", {}).get("list", [])
                if lst and lst[0].get("avgPrice") not in ("0", None, ""):
                    break
                await asyncio.sleep(0.8)

            if not lst:
                await bot.send_message(chat_id, "⚠ Не удалось получить историю BUY.")
                continue

            row = lst[0]
            avg = float(row.get("avgPrice", 0) or 0)
            qty_raw = float(row.get("cumExecQty", 0) or 0)

            fee = 0.0
            try:
                fee = float(row.get("cumFeeDetail", {}).get("STRK", 0) or 0)
            except:
                fee = 0.0

            qty_net = max(qty_raw - fee, 0.0)
            qty_sell = int(qty_net * 10) / 10

            if qty_sell <= 0:
                await bot.send_message(chat_id, "❌ Кол-во STRK для TP = 0")
                continue

            # ----------- Проф. TP: hybrid_step + 1% -----------
            tp_percent = hybrid_step + 0.01
            tp = round(avg * (1 + tp_percent), 4)

            try:
                sell = client.place_order(
                    category="spot",
                    symbol=SYMBOL,
                    side="SELL",
                    orderType="Limit",
                    qty=qty_sell,
                    price=tp,
                    timeInForce="GTC"
                )
            except Exception as e:
                await bot.send_message(chat_id, f"⚠ Ошибка установки TP : {e}")
                continue

            st.down_sell_orders.append(sell["result"]["orderId"])
            st.down_levels_completed += 1

            # PnL УРОВНЯ (считаем СРАЗУ!)
            pnl = (tp - avg) * qty_sell
            register_trade(pnl)   # <--- теперь статистика правильная!

            await bot.send_message(
                chat_id,
                f"🟢 Уровень *{st.down_levels_completed}/{DOWN_LEVELS}* откуплен\n"
                f"Цена входа : *{avg}*\n"
                f"Take Profit : *{tp}*\n"
                f"ATR : *{round(atr_percent * 100, 2)}* %",
                parse_mode="Markdown"
            )

        # ------------------ AUTO EXIT цена вернулась к базе ------------------
        if price >= base:
            await bot.send_message(
                chat_id,
                "📈 Цена восстановилась выше базовой\nВозвращаемся в UP ⬆️"
            )

            reset_down_vars()

            from strategy.up_cycle import strategy_cycle
            st.strategy_running = True
            st.strategy_task = asyncio.create_task(strategy_cycle(chat_id, bot))
            return

        # ------------------ Проверка закрытия TP ------------------
        if st.down_levels_completed > 0 and st.down_sell_orders:

            if time.time() - st.last_open_check < 8:
                continue
            st.last_open_check = time.time()

            try:
                od = client.get_open_orders(category="spot", symbol=SYMBOL)
                open_ids = {o.get("orderId") for o in od.get("result", {}).get("list", [])}
            except Exception as e:
                print("open_orders error:", e)
                continue

            all_closed = all(oid not in open_ids for oid in st.down_sell_orders)

            if all_closed:

                await bot.send_message(
                    chat_id,
                    "🎯 Все уровни DOWN закрыты по TP\n"
                    "Возвращаемся в UP ⬆️"
                )

                reset_down_vars()

                from strategy.up_cycle import strategy_cycle
                st.strategy_running = True
                st.strategy_task = asyncio.create_task(strategy_cycle(chat_id, bot))
                return
