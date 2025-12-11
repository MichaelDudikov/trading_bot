from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery


# 🔥 WHITELIST — сюда добавляешь свои ID
ALLOWED_USERS = {
    1678086777,   # ← твой ID
    # 123456789, ← добавишь позже при необходимости
}


class AllowOnlyWhitelistMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):

        user_id = None

        # Сообщения
        if isinstance(event, Message):
            user_id = event.from_user.id

        # Кнопки (callback)
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id

        # Если что-то другое — пропускаем
        if user_id is None:
            return await handler(event, data)

        # 🔒 Если пользователь НЕ в whitelist
        if user_id not in ALLOWED_USERS:
            try:
                if isinstance(event, Message):
                    await event.answer(
                        "⛔ *Доступ запрещён*\n"
                        "Этот бот является приватным и недоступен для использования.",
                        parse_mode="Markdown"
                    )

                elif isinstance(event, CallbackQuery):
                    await event.message.answer(
                        "⛔ *Доступ запрещён*\n"
                        "Этот бот является приватным и недоступен для использования.",
                        parse_mode="Markdown"
                    )
            except:
                pass

            return  # полностью блокируем дальнейшие хендлеры

        # ✅ Пользователь в whitelist → пропускаем
        return await handler(event, data)
