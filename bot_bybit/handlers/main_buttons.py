from aiogram import Router, F, types
from aiogram.filters import CommandStart, Command
import asyncio
from keyboards import main_kb, cancel_order_kb, stats_clear_kb
from bybit_api.detector import get_price, get_active_limit_sell_order
from bybit_api.balances import balance_strk, balance_usdt
from bybit_api.orders_up import buy_strk, sell_strk
from strategy import state as st
from strategy.up_cycle import strategy_cycle
from strategy.down_cycle import reset_down_vars
from strategy.stats_storage import save_stats_to_file, reset_stats
from config import DOWN_LEVELS, DOWN_STEP


router = Router()


# START КОМАНДА
@router.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.answer(
        "Привет 👋 я бот для торговли на Bybit 🤖\n\n"
        "Стратегия: BUY → TP → BUY → TP\n"
        "При развороте вниз включается откуп падения по уровням (DOWN).\n\n"
        "Выбери действие ⬇️",
        reply_markup=main_kb
    )


# КОМАНДА STOP: Полный стоп UP + DOWN
@router.message(Command("stop"))
async def cmd_stop(message: types.Message):
    st.strategy_running = False
    if st.strategy_task:
        st.strategy_task.cancel()
        st.strategy_task = None

    # Останавливаем DOWN
    if st.down_active:
        reset_down_vars()
        st.down_active = False
        st.trade_mode = "UP"

    await message.answer("⏹ Все стратегии остановлены.")


# 📈 Цена STRK
@router.message(F.text == "📈 цена STRK")
async def btn_price_strk(message: types.Message):
    price = get_price()
    await message.answer(f"📈 Цена STRK: *{price}*", parse_mode="Markdown")


# 💰 Баланс STRK
@router.message(F.text == "💰 баланс STRK")
async def btn_balance_strk(message: types.Message):
    bal = balance_strk()
    if isinstance(bal, (int, float)):
        bal = round(bal, 3)

    await message.answer(f"💰 Ваш баланс STRK: *{bal}*", parse_mode="Markdown")


# 💲 Баланс USDT
@router.message(F.text == "💲 баланс USDT")
async def btn_balance_usdt(message: types.Message):
    bal = balance_usdt()
    if isinstance(bal, (int, float)):
        bal = round(bal, 2)

    await message.answer(f"💲 Ваш баланс USDT: *{bal}*", parse_mode="Markdown")


# 📊 Активный ордер
@router.message(F.text == "📊 Активный ордер")
async def btn_active_order(message: types.Message):
    order = get_active_limit_sell_order()
    if not order:
        await message.answer("📭 Активных лимитных ордеров нет.")
        return

    price = order.get("price")
    qty = order.get("qty")
    status = order.get("orderStatus")
    order_id = order.get("orderId")

    await message.answer(
        "📊 *Активный лимитный ордер*\n\n"
        f"ID: `{order_id}`\n"
        f"Цена: *{price}*\n"
        f"Количество: *{qty}*\n"
        f"Статус: {status}",
        reply_markup=cancel_order_kb(order_id),
        parse_mode="Markdown"
    )


# 💷 Купить STRK
@router.message(F.text == "💷 Купить STRK")
async def btn_buy_strk(message: types.Message):
    # Блокируем BUY если включён DOWN
    if st.down_active:
        await message.answer(
            "⚠️ Сейчас активен DOWN-режим.\n"
            "Остановите его командой /stop перед запуском BUY.",
            parse_mode="Markdown"
        )
        return

    result = buy_strk()
    await message.answer(result, parse_mode="Markdown")

    # Запускаем стратегию, если покупка успешная
    if "Куплено STRK" in result and not st.strategy_running:
        st.strategy_running = True
        st.strategy_task = asyncio.create_task(
            strategy_cycle(message.chat.id, message.bot)
        )
        await message.answer("🚀 Стратегия BUY → TP запущена.\nОстановить → /stop")


# 💸 Продать STRK
@router.message(F.text == "💸 Продать STRK")
async def btn_sell_strk(message: types.Message):
    result = sell_strk()
    await message.answer(result, parse_mode="Markdown")


# 📊 Статистика
@router.message(Command("stats"))
async def cmd_stats(message: types.Message):

    total = st.total_trades
    wins = st.profit_trades
    losses = st.loss_trades

    if wins + losses > 0:
        win_rate = round(wins / (wins + losses) * 100, 1)
    else:
        win_rate = 0.0

    text = f"""
📊 *Статистика торговли*

Всего сделок : *{total}*
Прибыльных : *{wins}*
Убыточных : *{losses}*
Win rate : *{win_rate}%*

Общий PnL : *{round(st.total_pnl, 4)} USDT*

🔵 *UP-стратегия*
• Сделок : *{st.total_trades_up}*
• PnL : *{round(st.total_pnl_up, 4)} USDT*

🟡 *DOWN-стратегия*
• Уровней закрыто : *{st.levels_down_closed}*
• PnL : *{round(st.total_pnl_down, 4)} USDT*
"""

    # перед показом — сохраним статистику в файл
    save_stats_to_file()

    await message.answer(text, parse_mode="Markdown", reply_markup=stats_clear_kb())


@router.callback_query(F.data == "stats_clear")
async def on_stats_clear(callback: types.CallbackQuery):
    reset_stats()
    await callback.message.answer("📊 Статистика торговли очищена")
    await callback.answer()


@router.message(Command("down"))
async def cmd_down(message: types.Message):
    # Если DOWN выключен
    if not st.down_active:
        text = "DOWN-режим : ❌ не активен\n"
        if st.down_base_price:
            text += f"Последняя базовая цена : *{st.down_base_price}*\n"
        await message.answer(text, parse_mode="Markdown")
        return

    # Если DOWN включен
    # Текущая цена
    try:
        last_price = get_price()
    except:
        last_price = None

    base = st.down_base_price or 0

    text = "*DOWN-режим активен* ✅\n\n"
    text += f"Базовая цена : *{base}*\n"
    if last_price:
        text += f"Текущая цена : *{last_price}*\n\n"

    text += "Уровни :\n"

    for lvl in range(1, DOWN_LEVELS + 1):
        level_price = round(base - DOWN_STEP * lvl, 4)
        text += f"{lvl} уровень : *{level_price}*\n"

    text += "\n"
    text += f"Откупов выполнено : *{st.down_levels_completed}/{DOWN_LEVELS}*\n"
    text += f"Ордера TP выставлены : *{len(st.down_sell_orders)}*\n"

    await message.answer(text, parse_mode="Markdown")
