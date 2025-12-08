from aiogram import BaseMiddleware
from aiogram.types import Message

ALLOWED_USER_ID = 1678086777  # ← твой ID


class AllowOnlyOwnerMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if isinstance(event, Message):
            if event.from_user.id != ALLOWED_USER_ID:
                # Игнорируем чужие сообщения
                return
        return await handler(event, data)
