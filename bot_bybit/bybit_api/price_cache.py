import time
from bybit_api.detector import get_price

_last_price = None
_last_time = 0


def get_price_cached(max_age=0.5):
    """
    Возвращает цену, обновляя её не чаще чем раз в max_age секунд.
    """
    global _last_price, _last_time

    now = time.time()

    if _last_price is None or (now - _last_time) > max_age:
        _last_price = get_price()
        _last_time = now

    return _last_price
