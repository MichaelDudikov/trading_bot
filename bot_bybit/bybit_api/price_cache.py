import time
from bybit_api.detector import get_price

_last_price = None
_last_time = 0.0


def get_price_cached(max_age=0.1):
    """
    Обновляет цену не чаще, чем 1 раз в 0.1 сек.
    Это резко снижает пропуски разворотов.
    """
    global _last_price, _last_time

    now = time.time()

    if _last_price is None or (now - _last_time) > max_age:
        try:
            _last_price = get_price()
            _last_time = now
        except Exception:
            pass  # оставляем старую цену на случай ошибки

    return _last_price
