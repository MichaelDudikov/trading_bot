from .client import client
from pybit import exceptions
from config import SYMBOL


def get_price() -> float:
    data = client.get_tickers(category="spot", symbol=SYMBOL)
    item = data["result"]["list"][0]
    return float(item["lastPrice"])


def get_active_limit_sell_order():
    """
    Ищем активный лимитный ордер на продажу STRK.
    """
    try:
        data = client.get_open_orders(category="spot", symbol=SYMBOL)
    except (exceptions.InvalidRequestError, exceptions.FailedRequestError) as e:
        print("get_open_orders error:", e)
        return None

    orders = data.get("result", {}).get("list", [])
    for o in orders:
        if o.get("side") == "Sell" and o.get("orderType") == "Limit":
            return o
    return None
