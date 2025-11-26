import asyncio
from aiogram import Bot, Dispatcher
from config import BOT_TOKEN
# import logging
# Импортируем роутеры с кнопками
from handlers.main_buttons import router as buttons_router
from handlers.cancel_order import router as cancel_router
from strategy.stats_storage import load_stats_from_file


bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


async def main():
    print("Бот запущен ...")

    await bot.delete_webhook(drop_pending_updates=True)

    # Регистрируем роутеры
    dp.include_router(buttons_router)
    dp.include_router(cancel_router)

    # загружаем статистику до старта поллинга
    load_stats_from_file()

    # Стартуем
    await dp.start_polling(bot)


if __name__ == "__main__":

    # === SUPPRESS TRANSPORT ERRORS (WinError 10054, SSL EOF, etc.) ===
    def ignore_transport_errors(_loop, context):
        msg = context.get("message", "")
        exc = context.get("exception")

        # Игнорируем ошибки транспорта
        if (
                "SSL error" in msg
                or "transport" in msg.lower()
                or "connection lost" in msg.lower()
                or isinstance(exc, ConnectionResetError)
                or isinstance(exc, OSError)
        ):
            # Можно логировать тихо:
            # logging.debug(f"Ignored transport error: {context}")
            return

        # всё остальное — по дефолту
        loop.default_exception_handler(context)

    # === Правильное создание event loop на Python 3.10+ ===
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.set_exception_handler(ignore_transport_errors)

    # === START BOT ===
    asyncio.run(main())
