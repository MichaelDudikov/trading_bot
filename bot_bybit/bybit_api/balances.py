from .client import client
from pybit import exceptions


def _get_assets(coin: str) -> float:
    data_balance = client.get_wallet_balance(accountType="UNIFIED")
    try:
        coins = data_balance["result"]["list"][0]["coin"]
    except Exception:
        return 0.0

    assets = {c["coin"]: float(c.get("equity", 0.0)) for c in coins}
    return assets.get(coin, 0.0)


def balance_strk() -> float:
    for _ in range(3):
        try:
            return _get_assets("STRK")
        except (exceptions.InvalidRequestError, exceptions.FailedRequestError) as e:
            print("Bybit API error (STRK balance):", e)
            continue
    return 0.0


def balance_usdt() -> float:
    for _ in range(3):
        try:
            return _get_assets("USDT")
        except (exceptions.InvalidRequestError, exceptions.FailedRequestError) as e:
            print("Bybit API error (USDT balance):", e)
            continue
    return 0.0
