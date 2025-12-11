import asyncio
from aiogram import Bot

from bybit_api.detector import get_active_limit_sell_order
from bybit_api.balances import balance_usdt
from bybit_api.orders_up import buy_strk, sell_strk
from bybit_api.client import client

from strategy import state as st
from strategy.down_cycle import enter_down_mode

from config import DRAWDOWN_TRIGGER, SYMBOL
from bybit_api.price_cache import get_price_cached
from strategy.trade_stats import register_trade   # <-- ТОЛЬКО ЭТО считаем статистикой!


# ===========================================================
#   Обновление статистики после успешного TP
# ===========================================================
def _update_up_stats_after_tp():
    """
    Вызывается в момент, когда лимитный ордер (TP) исчез.
    Смотрим последний SELL-Limit в истории и считаем PnL.
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
    if o.get("orderStatus") not in (
        "Filled",
        "PartiallyFilled",
        "PartiallyFilledCanceled",
        "PartiallyFilledCanceledByUser",
    ):
        return

    order_id = o.get("orderId")
    if order_id is None:
        return
    
    # Если уже учитывали этот TP — выходим, защищаемся от дублирования
    if getattr(st, "last_up_tp_order_id", None) == order_id:
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

    # Учёт сделки
    register_trade(profit)

    # Запоминаем, что этот TP уже учли
    st.last_up_tp_order_id = order_id

    print(f"[UP STATS] TP order {order_id}: entry={entry}, tp={tp_price}, qty={qty}, pnl={profit}")


# ===========================================================
#   Основной цикл UP-стратегии
# ===========================================================
async def strategy_cycle(chat_id: int, bot: Bot):
    """
    Стратегия BUY → TP → BUY → TP … пока не произойдёт разворот.
    """
    while st.strategy_running:

        # 🔄 Каждый новый цикл — считаем, что разворота еще НЕ было
        st.reversal_detected = False

        # --- 1) ЖДЁМ ИСЧЕЗНОВЕНИЯ ЛИМИТКИ ---
        while st.strategy_running:

            active = get_active_limit_sell_order()
            if not active:   # лимитка исчезла → TP исполнен
                break

            # --- Проверка разворота вниз ---
            if st.trade_mode == "UP" and st.entry_price_up is not None:

                try:
                    last_price = get_price_cached()
                except:
                    last_price = None

                if last_price is not None:

                    trigger = st.entry_price_up - DRAWDOWN_TRIGGER

                    # ФАЗА 1. Детектор: фиксируем факт пробоя триггера ---
                    if last_price <= trigger:
                        st.reversal_detected = True

                    # ФАЗА 2. Если разворот был зафиксирован — выполняем разворот ---
                    if st.reversal_detected:

                        await bot.send_message(
                            chat_id,
                            f"📉 Обнаружен разворот вниз\n\n"
                            f"Цена входа : *{st.entry_price_up}*\n"
                            f"Текущая цена : *{last_price}*\n"
                            f"Падение на *{round(st.entry_price_up - last_price, 5)}*",
                            parse_mode="Markdown"
                        )

                        # отменяем лимитку
                        try:
                            client.cancel_order(
                                category="spot",
                                symbol=SYMBOL,
                                orderId=active.get("orderId")
                            )
                        except Exception as e:
                            print("cancel_order (reversal) error:", e)

                        # продаём STRK рыночным ордером
                        sell_msg = sell_strk()
                        await bot.send_message(chat_id, sell_msg, parse_mode="Markdown")

                        # выключаем UP
                        st.strategy_running = False

                        # включаем DOWN
                        await enter_down_mode(chat_id, last_price, bot)
                        return

            # раньше было 4 секунды — из-за этого пропуск разворотов
            await asyncio.sleep(0.5)

        # если UP выключился выше — выходим
        if not st.strategy_running:
            break

        # --- 2) TP исполнен → считаем PnL ---
        # 2) TP ИСПОЛНЕН — СЧИТАЕМ ТОЛЬКО ЕСЛИ НЕ БЫЛО РАЗВОРОТА
        if not st.reversal_detected:
            try:
                _update_up_stats_after_tp()
            except Exception as e:
                print("UP stats error:", e)

        # --- 3) Проверяем баланс ---
        usdt = balance_usdt()
        if not isinstance(usdt, (int, float)):
            await bot.send_message(chat_id, f"❌ Ошибка получения баланса USDT :\n{usdt}")
            st.strategy_running = False
            break

        if int(usdt) <= 0:
            await bot.send_message(chat_id, "❌ Недостаточно USDT. Стратегия остановлена.")
            st.strategy_running = False
            break

        # --- 4) Открываем новую сделку UP ---
        await bot.send_message(
            chat_id,
            "♻️ TP исполнен или лимитки нет\n"
            "Открываю новую сделку на покупку ⬇️"
        )

        result = buy_strk()
        await bot.send_message(chat_id, result, parse_mode="Markdown")

        await asyncio.sleep(2)
