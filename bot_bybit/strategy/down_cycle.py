import asyncio
from aiogram import Bot
from bybit_api.detector import get_price
from bybit_api.balances import balance_usdt
from bybit_api.client import client
from config import SYMBOL, DOWN_LEVELS, DOWN_STEP, DOWN_TP_STEP
from strategy import state as st


# =============== СБРОС DOWN-ПЕРЕМЕННЫХ ==================
def reset_down_vars():
    st.down_active = False
    st.down_base_price = None
    st.down_usdt_total = None
    st.down_usdt_per_level = None
    st.down_levels_completed = 0
    st.down_sell_orders = []
    st.down_entry_prices = []       # <-- NEW
    st.down_qty_list = []           # <-- NEW


# =============== ВХОД В DOWN-РЕЖИМ ======================
async def enter_down_mode(chat_id: int, last_price: float, bot: Bot):
    st.trade_mode = "DOWN"
    st.down_active = True

    st.down_entry_prices = []   # <-- NEW
    st.down_qty_list = []       # <-- NEW

    # базовая цена — откуда начали падать
    st.down_base_price = st.entry_price_up if st.entry_price_up else last_price

    # сколько USDT есть для DOWN
    usdt = balance_usdt()
    if not isinstance(usdt, (int, float)):
        await bot.send_message(chat_id, f"❌ Ошибка баланса USDT :\n{usdt}")
        st.down_active = False
        st.trade_mode = "UP"
        return

    st.down_usdt_total = float(usdt)
    if st.down_usdt_total <= 0:
        await bot.send_message(chat_id, "❌ Нет USDT для DOWN-режима.")
        st.down_active = False
        st.trade_mode = "UP"
        return

    # делим депозит на уровни
    st.down_usdt_per_level = round(st.down_usdt_total / DOWN_LEVELS, 2)
    st.down_levels_completed = 0
    st.down_sell_orders = []

    # Информативный текст для Telegram
    down_base_price_90 = round(st.down_base_price - 0.0050, 4)

    await bot.send_message(
        chat_id,
        f"📉 Переход в режим торговли вниз (DOWN)\n\n"
        f"Базовая цена : *{st.down_base_price}* ждём (~) *{down_base_price_90}*\n"
        f"Текущая цена : *{last_price}*\n\n"
        f"Всего USDT для откупа : *{st.down_usdt_total}*\n"
        f"На каждый уровень (~) : *{st.down_usdt_per_level}*\n"
        f"Уровней : *{DOWN_LEVELS}*", parse_mode="Markdown")

    asyncio.create_task(down_mode_cycle(chat_id, bot))


# =============== DOWN-ЦИКЛ — ПО УРОВНЯМ =================
async def down_mode_cycle(chat_id: int, bot: Bot):

    await bot.send_message(chat_id, "✔ DOWN-режим активирован\n🔍 Ждём уровни падения ...")

    while st.down_active:
        await asyncio.sleep(2)

        try:
            price = get_price()
        except Exception:
            continue

        # ----------------- 1) Откуп уровня -----------------
        if st.down_levels_completed < DOWN_LEVELS:

            target_price = st.down_base_price - DOWN_STEP * (st.down_levels_completed + 1)

            if price <= target_price:

                part = st.down_usdt_per_level
                if part < 1:
                    await bot.send_message(chat_id, f"❌ Слишком маленькая сумма ({part})")
                    reset_down_vars()
                    st.trade_mode = "UP"
                    return

                # покупка по рынку
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
                avg = None
                qty = None
                lst = []

                for _ in range(6):
                    h = client.get_order_history(
                        category="spot",
                        orderId=buy_id,
                        symbol=SYMBOL
                    )
                    lst = h.get("result", {}).get("list", [])
                    if lst:
                        avg = lst[0].get("avgPrice")
                        qty = lst[0].get("cumExecQty")
                    if avg not in [None, "", "0"] and qty not in [None, "", "0"]:
                        break
                    await asyncio.sleep(0.3)

                if not avg:
                    avg = price
                avg = float(avg)

                # расчёт STRK после комиссии
                qty_raw = float(qty or 0)
                fee = 0.0
                fee_detail = lst[0].get("cumFeeDetail", {})
                if isinstance(fee_detail, dict):
                    try:
                        fee = float(fee_detail.get("STRK", 0))
                    except:
                        fee = 0.0

                net_qty = max(qty_raw - fee, 0.0)
                qty_sell = int(net_qty * 10) / 10

                if qty_sell <= 0:
                    await bot.send_message(chat_id, "❌ Ошибка STRK qty для лимитки DOWN")
                    continue

                tp = round(avg + DOWN_TP_STEP, 4)

                # === Сохраняем данные уровня для статистики ===
                st.down_entry_prices.append(avg)   # <-- NEW
                st.down_qty_list.append(qty_sell)  # <-- NEW

                # лимитка на продажу
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

                await bot.send_message(
                    chat_id,
                    f"🟢 Уровень *{st.down_levels_completed}/{DOWN_LEVELS}* откуплен\n"
                    f"Цена входа : *{avg}*\nTake Profit : *{tp}*", parse_mode="Markdown")

        # ----------------- 2) EXIT IF PRICE RECOVERED -----------------
        if st.down_active:
            if price >= st.down_base_price:

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

        # ----------------- 3) Проверка закрытия всех TP -----------------
        if st.down_levels_completed > 0 and st.down_sell_orders:

            try:
                open_data = client.get_open_orders(category="spot", symbol=SYMBOL)
                open_ids = {o.get("orderId") for o in open_data["result"]["list"]}
            except:
                open_ids = set()

            all_closed = all(oid not in open_ids for oid in st.down_sell_orders)

            if all_closed:
                await bot.send_message(
                    chat_id,
                    "🎯 Все TP DOWN-стратегии выполнены\n"
                    "Возвращаемся в UP ⬆️"
                )

                # —== Тут считаем PnL ==—
                # Считаем суммарный PnL по DOWN: разница между текущим USDT и тем,
                # что было на входе в DOWN.
                try:
                    current_usdt = balance_usdt()
                    if isinstance(current_usdt, (int, float)) and st.down_usdt_total is not None:
                        total_down_profit = current_usdt - st.down_usdt_total

                        # Обновляем общую статистику
                        st.total_trades += len(st.down_entry_prices)
                        st.levels_down_closed += len(st.down_entry_prices)

                        if total_down_profit >= 0:
                            st.profit_trades += len(st.down_entry_prices)
                            st.wins_down += len(st.down_entry_prices)
                        else:
                            st.loss_trades += len(st.down_entry_prices)
                            st.losses_down += len(st.down_entry_prices)

                        st.total_pnl += total_down_profit
                        st.total_pnl_down += total_down_profit

                        print(f"[DOWN STATS] levels={len(st.down_entry_prices)}, pnl={total_down_profit}")

                        from strategy.stats_storage import save_stats_to_file
                        save_stats_to_file()

                except Exception as e:
                    print("Error while calculating DOWN PnL:", e)

                reset_down_vars()

                # импорт внутри функции → нет circular import
                from strategy.up_cycle import strategy_cycle

                st.strategy_running = True
                st.strategy_task = asyncio.create_task(strategy_cycle(chat_id, bot))
                return
