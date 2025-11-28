import asyncio
import numpy as np
from aiogram import Bot

from bybit_api.detector import get_price
from bybit_api.balances import balance_usdt
from bybit_api.client import client
from config import SYMBOL, DOWN_LEVELS
from strategy import state as st
from strategy.stats_storage import save_stats_to_file


# ===================== ATR CALCULATION =====================
def calc_atr_percent() -> float:
    """
    Реальная ATR-адаптация:
    Берём последние ~50 цен (lastPrice), считаем средний TR
    и нормализуем в процентах.
    """
    prices: list[float] = []

    try:
        for _ in range(50):
            prices.append(get_price())
            # здесь не await, это sync-функция; просто быстро насобирали lastPrice
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

    atr_percent = atr / last  # доля от цены

    # Ограничим 0.5%–5%
    return max(0.005, min(atr_percent, 0.05))


# ===================== RESET DOWN VARS =====================
def reset_down_vars():
    st.down_active = False
    st.down_base_price = None
    st.down_usdt_total = None
    st.down_usdt_per_level = None
    st.down_levels_completed = 0
    st.down_sell_orders = []

    # очищаем массивы уровней
    st.down_entry_prices = []
    st.down_qty_list = []


# ===================== ENTER DOWN MODE =====================
async def enter_down_mode(chat_id: int, last_price: float, bot: Bot):
    """
    Вход в DOWN-режим:
    - фиксируем базовую цену
    - считаем, сколько USDT есть
    - делим депозит на DOWN_LEVELS частей
    - запускаем down_mode_cycle
    """

    st.trade_mode = "DOWN"
    st.down_active = True

    # базовая цена — откуда началось падение
    st.down_base_price = st.entry_price_up if st.entry_price_up else last_price

    usdt = balance_usdt()
    if not isinstance(usdt, (int, float)) or usdt <= 0:
        await bot.send_message(chat_id, "❌ Нет USDT для DOWN-режима.")
        st.trade_mode = "UP"
        st.down_active = False
        return

    st.down_usdt_total = float(usdt)
    st.down_usdt_per_level = round(st.down_usdt_total / DOWN_LEVELS, 2)

    # наглядный уровень ~ -0.0050 от базы (для текста)
    down_base_price_90 = round(st.down_base_price - 0.0050, 4)

    await bot.send_message(
        chat_id,
        f"📉 Переход в режим торговли вниз (DOWN)\n\n"
        f"Базовая цена : *{st.down_base_price}* (ждём ≈ *{down_base_price_90}*)\n"
        f"Текущая цена : *{last_price}*\n\n"
        f"Всего USDT для откупа : *{st.down_usdt_total}*\n"
        f"На каждый уровень (~) : *{st.down_usdt_per_level}*\n"
        f"Уровней : *{DOWN_LEVELS}*\n"
        f"ATR-адаптация активна ⚡",
        parse_mode="Markdown"
    )

    asyncio.create_task(down_mode_cycle(chat_id, bot))


# ===================== MAIN DOWN CYCLE =====================
async def down_mode_cycle(chat_id: int, bot: Bot):
    """
    PRO-версии DOWN:
    - гибридный шаг сетки (3% + ATR)
    - усиление сетки при глубоких падениях
    - авто-выход при возврате к базе
    - подсчёт PnL по всем откупленным уровням
    """

    await bot.send_message(
        chat_id,
        "✔ DOWN-режим активирован\n🔍 Ждём уровни падения ..."
    )

    while st.down_active:
        await asyncio.sleep(2)

        try:
            price = get_price()
        except Exception as e:
            print("down_mode_cycle get_price error:", e)
            continue

        if st.down_base_price is None:
            # на всякий случай
            st.down_base_price = price

        base = st.down_base_price
        lvl = st.down_levels_completed + 1

        # ---------------- 1) ATR-адаптация шага ----------------
        atr_percent = calc_atr_percent()
        grid_step = 0.03              # базовый шаг 3%
        hybrid_step = grid_step + atr_percent

        # ---------------- 2) Усиление сетки при глубоком падении ----------------
        drawdown = (base - price) / base if base > 0 else 0.0
        extra_levels = 0

        if drawdown > 0.20:
            extra_levels += 1
        if drawdown > 0.35:
            extra_levels += 1
        if drawdown > 0.50:
            extra_levels += 1

        target_level = lvl + extra_levels

        # ---------------- 3) Итоговая цена уровня ----------------
        target_price = base * (1 - hybrid_step * target_level)

        # ---------------- 4) ОТКУП УРОВНЯ ----------------
        if price <= target_price and st.down_levels_completed < DOWN_LEVELS:

            part = st.down_usdt_per_level
            if part is None or part <= 0:
                await bot.send_message(chat_id, "❌ Слишком маленькая сумма уровня для DOWN.")
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

            # ждём avgPrice и cumExecQty
            lst = []
            for _ in range(6):
                h = client.get_order_history(
                    category="spot",
                    orderId=buy_id,
                    symbol=SYMBOL
                )
                lst = h.get("result", {}).get("list", [])
                if lst and lst[0].get("avgPrice") not in ("0", None, ""):
                    break
                await asyncio.sleep(0.3)

            if not lst:
                await bot.send_message(chat_id, "⚠ Не удалось получить историю ордера DOWN.")
                continue

            row = lst[0]
            try:
                avg = float(row.get("avgPrice", "0") or "0")
                qty_raw = float(row.get("cumExecQty", "0") or "0")
            except ValueError:
                await bot.send_message(chat_id, "⚠ Ошибка парсинга avgPrice/cumExecQty.")
                continue

            # комиссия в STRK
            fee = 0.0
            try:
                fee_detail = row.get("cumFeeDetail", {})
                if isinstance(fee_detail, dict):
                    fee = float(fee_detail.get("STRK", 0) or 0)
            except Exception:
                fee = 0.0

            qty_net = max(qty_raw - fee, 0.0)
            qty_sell = int(qty_net * 10) / 10

            if qty_sell <= 0:
                await bot.send_message(chat_id, "❌ Ошибка: количество STRK для TP получилось 0.")
                continue

            # TP = +2% от средней цены входа уровня
            tp = round(avg * 1.02, 4)

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

            # Сохраняем данные уровня для последующего PnL
            st.down_entry_prices.append(avg)
            st.down_qty_list.append(qty_sell)

            await bot.send_message(
                chat_id,
                f"🟢 Уровень *{st.down_levels_completed}/{DOWN_LEVELS}* откуплен\n"
                f"Цена входа : *{avg}*\n"
                f"Take Profit : *{tp}*\n"
                f"ATR: {round(atr_percent * 100, 2)}%",
                parse_mode="Markdown"
            )

        # ---------------- 5) AUTO EXIT — цена вернулась к базе ----------------
        if price >= base:
            await bot.send_message(
                chat_id,
                "📈 Цена восстановилась выше базовой\n"
                "Выход из DOWN → возврат в UP ⬆️"
            )

            reset_down_vars()

            from strategy.up_cycle import strategy_cycle
            st.strategy_running = True
            st.strategy_task = asyncio.create_task(strategy_cycle(chat_id, bot))
            return

        # ---------------- 6) Проверка закрытия всех TP ----------------
        if st.down_levels_completed > 0 and st.down_sell_orders:
            try:
                open_orders = client.get_open_orders(category="spot", symbol=SYMBOL)
                open_ids = {o["orderId"] for o in open_orders["result"]["list"]}
            except Exception as e:
                print("DOWN get_open_orders error:", e)
                open_ids = set()

            all_closed = True
            for oid in st.down_sell_orders:
                if oid in open_ids:
                    all_closed = False
                    break

            if all_closed:
                # === Считаем PnL по всем откупленным уровням ===
                total_profit_down = 0.0
                closed_levels = len(st.down_entry_prices)

                for entry_price, qty in zip(st.down_entry_prices, st.down_qty_list):
                    # по логике мы ставили TP = entry * 1.02
                    tp_price = entry_price * 1.02
                    total_profit_down += (tp_price - entry_price) * qty

                # Обновляем общую статистику
                st.total_trades += closed_levels
                st.profit_trades += closed_levels  # уровни DOWN всегда с положительным TP
                st.total_pnl += total_profit_down

                # Обновляем DOWN-статистику
                st.levels_down_closed += closed_levels
                st.total_pnl_down += total_profit_down
                st.wins_down += closed_levels

                # сохраняем в stats.json
                save_stats_to_file()

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
