from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton


main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📊 Активный ордер"), KeyboardButton(text="📈 цена STRK")],
        [KeyboardButton(text="💰 баланс STRK"), KeyboardButton(text="💲 баланс USDT")],
        [KeyboardButton(text="💷 Купить STRK"), KeyboardButton(text="💸 Продать STRK")],
    ],
    resize_keyboard=True
)


def cancel_order_kb(order_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="❌ Отменить лимитный ордер",
                    callback_data=f"cancel_sell_{order_id}"
                )
            ]
        ]
    )


def stats_clear_kb() -> InlineKeyboardMarkup:
    """ Инлайн-кнопка для очистки статистики под сообщением /stats."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🧹 Очистить статистику",
                    callback_data="stats_clear"
                )
            ]
        ]
    )
