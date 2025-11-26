import asyncio
from aiogram import Bot
from pybit import exceptions
from bybit_api.detector import get_price, get_active_limit_sell_order
from bybit_api.balances import balance_usdt
from bybit_api.orders_up import buy_strk, sell_strk
from bybit_api.client import client
from strategy import state as st
from config import DRAWDOWN_TRIGGER, SYMBOL
from strategy.down_cycle import enter_down_mode
from strategy.stats_storage import save_stats_to_file


# ===========================================================
#   Обновление статистики после успешного TP
# ===========================================================
def _update_up_stats_after_tp():
    """
    Вызывается в момент, когда лимитный ордер (TP) исчез.
    Рассчитываем profit и обновляем статистику.
    """

    try:
        history = client.get_order_history(category="spot", symbol=SYMBOL)
    except Exception as e:
        print("UP stats: get_order_history error:", e)
        return

    lst = history.get("result", {}).get("list", []) if history else []
    if not lst:
        return

    o = lst[0]

    # Интересует последний полностью закрытый SELL LIMIT TP
    if o.get("side") != "Sell" or o.get("orderType") != "Limit":
        return
    if o.get("orderStatus") not in ("Filled", "PartiallyFilled", "PartiallyFilledCanceled", "PartiallyFilledCanceledByUser"):
        return

    order_id = o.get("orderId")
    if order_id is None:
        return

    # Защита: чтобы один и тот же TP не засчитывался дважды
    if st.last_up_tp_order_id == order_id:
        return

    try:
        tp_price = float(o.get("avgPrice", "0") or 0)
        qty = float(o.get("cumExecQty", "0") or 0)
    except ValueError:
        return

    if st.entry_price_up is None or qty <= 0 or tp_price <= 0:
        return

    entry = st.entry_price_up
    profit = (tp_price - entry) * qty

    # ---- Обновляем общую статистику ----
    st.total_trades += 1
    if profit >= 0:
        st.profit_trades += 1
    else:
        st.loss_trades += 1

    st.total_pnl += profit

    # ---- Обновляем UP-статистику ----
    st.total_trades_up += 1
    st.total_pnl_up += profit
    if profit >= 0:
        st.wins_up += 1
    else:
        st.losses_up += 1

    # Помечаем этот TP, чтобы не считать дважды
    st.last_up_tp_order_id = order_id

    print(f"[UP STATS] TP order {order_id}: entry={entry}, tp={tp_price}, qty={qty}, pnl={profit}")

    # === ВАЖНО ===
    # Сохраняем статистику в stats.json
    save_stats_to_file()


# ===========================================================
#   Основной цикл UP-стратегии
# ===========================================================
async def strategy_cycle(chat_id: int, bot: Bot):
    """
    Цикл BUY → TP → BUY → TP, пока не произойдёт разворот вниз.
    """
    while st.strategy_running:

        # 1) Ждём исчезновения лимитки (значит TP исполнен)
        while st.strategy_running:

            active = get_active_limit_sell_order()
            if not active:
                break  # TP исчез -> TP исполнен

            # --- Детектор разворота вниз ---
            if st.trade_mode == "UP" and st.entry_price_up is not None:

                try:
                    last_price = get_price()
                except (exceptions.InvalidRequestError, exceptions.FailedRequestError):
                    last_price = None

                if last_price is not None:

                    # если цена упала ниже точки входа на DRAWDOWN_TRIGGER
                    if last_price <= st.entry_price_up - DRAWDOWN_TRIGGER:

                        await bot.send_message(
                            chat_id,
                            f"📉 Обнаружен разворот вниз\n\n"
                            f"Цена входа : *{st.entry_price_up}*\n"
                            f"Текущая цена : *{last_price}*\n"
                            f"Падение на *{round(st.entry_price_up - last_price, 5)}*",
                            parse_mode="Markdown")

                        # отменяем лимитку
                        try:
                            client.cancel_order(
                                category="spot",
                                symbol=SYMBOL,
                                orderId=active.get("orderId")
                            )
                        except Exception as e:
                            print("cancel_order (reversal) error:", e)

                        # продаём STRK по рынку
                        sell_msg = sell_strk()
                        await bot.send_message(chat_id, sell_msg)

                        # выключаем UP
                        st.strategy_running = False

                        # передаём управление DOWN-режиму
                        await enter_down_mode(chat_id, last_price, bot)
                        return

            await asyncio.sleep(5)

        # Если UP-стратегия выключена — прекращаем цикл
        if not st.strategy_running:
            break

        # === TP полностью закрыт — обновляем статистику ===
        _update_up_stats_after_tp()

        # 2) Проверяем баланс USDT перед новой покупкой
        usdt = balance_usdt()
        if not isinstance(usdt, (int, float)):
            await bot.send_message(chat_id, f"❌ Ошибка получения баланса USDT :\n{usdt}")
            st.strategy_running = False
            break

        if int(usdt) <= 0:
            await bot.send_message(chat_id, "❌ Недостаточно USDT для новой сделки. Стратегия остановлена.")
            st.strategy_running = False
            break

        # 3) Совершаем новую покупку
        await bot.send_message(
            chat_id,
            "♻️ TP исполнен или лимитка отсутствует\n"
            "Открываю новую сделку на покупку ⬇️"
        )

        result = buy_strk()
        await bot.send_message(chat_id, result, parse_mode="Markdown")

        await asyncio.sleep(3)
