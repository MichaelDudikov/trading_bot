from aiogram import Router, F, types
from pybit import exceptions

from bybit_api.client import client
from config import SYMBOL

router = Router()


@router.callback_query(F.data.startswith("cancel_sell_"))
async def cancel_sell_callback(callback: types.CallbackQuery):
    order_id = callback.data.split("_")[-1]
    try:
        resp = client.cancel_order(
            category="spot",
            symbol=SYMBOL,
            orderId=order_id
        )
        print("cancel_order:", resp)
        await callback.message.answer("❌ Лимитный ордер отменён")
    except (exceptions.InvalidRequestError, exceptions.FailedRequestError) as e:
        await callback.message.answer(f"⚠ Ошибка при отмене ордера : {e}")
    await callback.answer()
