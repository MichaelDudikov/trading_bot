from pybit.unified_trading import HTTP
from config import API_KEY, SECRET_KEY


client = HTTP(
    api_key=API_KEY,
    api_secret=SECRET_KEY,
    recv_window=60000,
    # time_sync=True  # можно включить, если захочешь
)
