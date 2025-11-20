import asyncio
import time
import os
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from pybit.unified_trading import HTTP
from pybit import exceptions  # <-- добавили для более узких except

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN_TRADE")
API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")

client = HTTP(
    api_key=API_KEY,
    api_secret=API_SECRET,
    recv_window=60000,
)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# === Глобальные переменные стратегии (чтобы не было warning'ов) ===
strategy_running: bool = False
strategy_task: asyncio.Task | None = None

# Клавиатура с кнопками (2 в ряд)
main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📊 Активный ордер"), KeyboardButton(text="📈 цена STRK")],
        [KeyboardButton(text="💰 баланс STRK"), KeyboardButton(text="💲 баланс USDT")],
        [KeyboardButton(text="💷 Купить STRK"), KeyboardButton(text="💸 Продать STRK")],
    ],
    resize_keyboard=True
)


# === BYBIT функции ===

# Получаем цену STRK
def get_price():
    data = client.get_tickers(category="spot", symbol="STRKUSDT")
    item = data["result"]["list"][0]
    return float(item["lastPrice"])


# Получаем актив по монете
def get_assets(clients: HTTP, coin: str):
    data_balance = clients.get_wallet_balance(accountType="UNIFIED")
    assets = {
        asset.get('coin'): float(asset.get('equity', '0.0'))
        for asset in data_balance.get('result', {}).get('list', [])[0].get('coin', [])
    }
    return assets.get(coin, 0.0)


# Получаем баланс STRK
def balance_strk():
    for _ in range(3):  # пробуем три раза
        try:
            return get_assets(client, "STRK")
        except (exceptions.InvalidRequestError, exceptions.FailedRequestError) as e:
            print("Bybit API error (STRK balance):", e)
            continue
    return "❌ Ошибка : не удалось получить баланс STRK"


# Получаем баланс USDT
def balance_usdt():
    for _ in range(3):
        try:
            return get_assets(client, "USDT")
        except (exceptions.InvalidRequestError, exceptions.FailedRequestError) as e:
            print("Bybit API error (USDT balance):", e)
            continue
    return "❌ Ошибка : не удалось получить баланс USDT"


# Ищем активный лимитный ордер на продажу STRK
def get_active_limit_sell_order():
    try:
        data = client.get_open_orders(category="spot", symbol="STRKUSDT")
    except (exceptions.InvalidRequestError, exceptions.FailedRequestError) as e:
        print("get_open_orders error:", e)
        return None

    orders = data.get("result", {}).get("list", [])
    for o in orders:
        if o.get("side") == "Sell" and o.get("orderType") == "Limit":
            return o
    return None


# Покупка STRK с лимиткой +0.0030
def buy_strk():
    usdt = balance_usdt()
    if not isinstance(usdt, (int, float)):
        return f"❌ Ошибка получения баланса USDT :\n{usdt}"

    usdt = int(usdt)
    if usdt <= 0:
        return "❌ Недостаточно USDT"

    # 1) Market BUY
    order = client.place_order(
        category="spot",
        symbol="STRKUSDT",
        side="BUY",
        orderType="Market",
        qty=usdt,
        marketUnit="quoteCoin"
    )
    print("place_order:", order)

    order_id = order["result"]["orderId"]

    # 2) Ждём avgPrice
    avg_price = None
    for _ in range(5):
        history = client.get_order_history(
            category="spot",
            orderId=order_id,
            symbol="STRKUSDT"
        )
        order_list = history.get("result", {}).get("list", [])
        print("get_order_history:", history)

        if order_list:
            avg_price = order_list[0].get("avgPrice")
        if avg_price not in [None, "", "0"]:
            break

        time.sleep(0.3)

    if not avg_price:
        return f"❌ avgPrice так и не получен после 5 попыток."

    avg_price = float(avg_price)

    # 3) Берём ФАКТИЧЕСКИЙ баланс STRK (после комиссии!)
    time.sleep(0.3)
    bal = balance_strk()

    if not isinstance(bal, (int, float)):
        return f"❌ Ошибка получения баланса STRK после покупки :\n{bal}"

    # 4) Обрезаем до 1 знака после запятой (truncate)
    qty_to_sell = int(bal * 10) / 10

    if qty_to_sell <= 0:
        return f"❌ После покупки баланс STRK слишком маленький : {bal}"

    # 5) Цена лимитного ордера
    sell_price = round(avg_price + 0.0030, 4)

    # 6) Размещаем лимитный ордер
    sell_order = client.place_order(
        category="spot",
        symbol="STRKUSDT",
        side="SELL",
        orderType="Limit",
        qty=qty_to_sell,
        price=sell_price,
        timeInForce="GTC"
    )
    print("sell limit order:", sell_order)

    return (
        f"✅ Куплено STRK на сумму {usdt} USDT по цене {avg_price} за STRK\n\n"
        f"📌 Выставлен лимитный ордер\n"
        f"Цена : {sell_price}\n"
        f"Количество : {qty_to_sell}"
    )


# Продажа STRK рыночным ордером (ручная кнопка)
def sell_strk():
    bal = balance_strk()

    # если баланс вернул ошибку
    if not isinstance(bal, (int, float)):
        return bal

    # Обрезаем до 1 знака после запятой (truncate)
    strk = int(bal * 10) / 10

    if strk <= 0:
        return "❌ Недостаточно STRK"

    order = client.place_order(
        category="spot",
        symbol="STRKUSDT",
        side="SELL",
        orderType="Market",
        qty=strk
    )
    print(order)

    return f"✅ Продано STRK : {strk}"


# === АВТОСТРАТЕГИЯ BUY → TP → BUY → TP → ... ===

async def strategy_cycle(chat_id: int):
    global strategy_running

    # Цикл работает, пока strategy_running = True
    while strategy_running:
        # 1) Ждём, пока активный лимитный ордер ИСЧЕЗНЕТ (TP исполнен или отменён)
        while strategy_running:
            active = get_active_limit_sell_order()
            if not active:
                break
            await asyncio.sleep(5)

        if not strategy_running:
            break

        # 2) Проверяем баланс USDT перед новой покупкой
        usdt = balance_usdt()
        if not isinstance(usdt, (int, float)):
            await bot.send_message(chat_id, f"❌ Ошибка при получении баланса USDT :\n{usdt}")
            strategy_running = False
            break

        usdt_int = int(usdt)
        if usdt_int <= 0:
            await bot.send_message(chat_id, "❌ Недостаточно USDT для следующего цикла. Стратегия остановлена.")
            strategy_running = False
            break

        # 3) Делаем новую покупку по стратегии
        await bot.send_message(chat_id, "♻️ TP исполнен или лимитка отсутствует. Открываю новую покупку по стратегии ⬇️")
        result = buy_strk()
        await bot.send_message(chat_id, result)

        await asyncio.sleep(3)


# === ОБРАБОТЧИКИ КОМАНД И КНОПОК ===

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.answer(
        "Привет 👋 я бот для торговли 🤖\n\n"
        "Выбери действие ⬇️\n\n"
        "Стратегия : BUY → TP → BUY → TP",
        reply_markup=main_kb
    )


@dp.message(Command("stop"))
async def cmd_stop(message: types.Message):
    global strategy_running, strategy_task
    if strategy_running:
        strategy_running = False
        if isinstance(strategy_task, asyncio.Task):
            strategy_task.cancel()
        strategy_task = None
        await message.answer("⏹ Стратегия остановлена")
    else:
        await message.answer("Стратегия и так не запущена")


# Кнопка: Активный ордер
@dp.message(F.text == "📊 Активный ордер")
async def btn_active_order(message: types.Message):
    order = get_active_limit_sell_order()
    if not order:
        await message.answer("📭 Активных лимитных ордеров на продажу STRK нет.")
        return

    price = order.get("price")
    qty = order.get("qty")
    status = order.get("orderStatus")
    order_id = order.get("orderId")

    inline_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="❌ Отменить лимитный ордер",
                    callback_data=f"cancel_sell_{order_id}"
                )
            ]
        ]
    )

    text = (
        "📊 Активный лимитный ордер\n\n"
        f"ID : {order_id}\n"
        f"Тип : {order.get('orderType')} {order.get('side')}\n"
        f"Цена : {price}\n"
        f"Количество : {qty}\n"
        f"Статус : {status}"
    )

    await message.answer(text, reply_markup=inline_kb)


# Обработка нажатия inline-кнопки "❌ Отменить лимитный ордер"
@dp.callback_query(F.data.startswith("cancel_sell_"))
async def cancel_sell_callback(callback: types.CallbackQuery):
    order_id = callback.data.split("_")[-1]
    try:
        resp = client.cancel_order(
            category="spot",
            symbol="STRKUSDT",
            orderId=order_id
        )
        print("cancel_order:", resp)
        await callback.message.answer("❌ Лимитный ордер отменён")
    except (exceptions.InvalidRequestError, exceptions.FailedRequestError) as e:
        await callback.message.answer(f"⚠ Ошибка при отмене ордера : {e}")
    await callback.answer()


@dp.message(F.text == "📈 цена STRK")
async def btn_price_strk(message: types.Message):
    price = get_price()
    await message.answer(f"📈 Цена STRK : {price}")


@dp.message(F.text == "💰 баланс STRK")
async def btn_balance_strk(message: types.Message):
    bal = balance_strk()

    if isinstance(bal, (int, float)):
        bal = round(bal, 2)

    await message.answer(f"💰 Ваш баланс STRK : {bal}")


@dp.message(F.text == "💲 баланс USDT")
async def btn_balance_usdt(message: types.Message):
    bal = balance_usdt()

    if isinstance(bal, (int, float)):
        bal = round(bal, 2)

    await message.answer(f"💲 Ваш баланс USDT : {bal}")


@dp.message(F.text == "💷 Купить STRK")
async def btn_buy_strk(message: types.Message):
    global strategy_running, strategy_task

    result = buy_strk()
    await message.answer(result)

    # Запускаем стратегию после первой покупки, если ещё не запущена
    if not strategy_running:
        strategy_running = True
        strategy_task = asyncio.create_task(strategy_cycle(message.chat.id))
        await message.answer("🚀 Стратегия запущена.\nОстановить : /stop")


@dp.message(F.text == "💸 Продать STRK")
async def btn_sell_strk(message: types.Message):
    result = sell_strk()
    await message.answer(result)


async def main():
    print("Бот запущен ...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
