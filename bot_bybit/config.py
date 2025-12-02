import os
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()

# === API KEYS ===
API_KEY = os.getenv("BYBIT_API_KEY")
SECRET_KEY = os.getenv("BYBIT_API_SECRET")
BOT_TOKEN = os.getenv("BOT_TOKEN_TRADE")

# Проверка — если ключи не загрузились, выводим предупреждение
if not API_KEY or not SECRET_KEY:
    print("⚠ WARNING: BYBIT API KEYS NOT LOADED FROM .env")

if not BOT_TOKEN:
    print("⚠ WARNING: BOT_TOKEN_TRADE NOT LOADED FROM .env")

# === Торговые настройки ===
SYMBOL = "STRKUSDT"

# Порог разворота вниз от avg_price (например, 0.0050)
DRAWDOWN_TRIGGER = 0.0050

# Настройки DOWN-стратегии
DOWN_LEVELS = 5          # Сколько уровней откупа
DOWN_STEP = 0.0050       # Шаг падения на каждом уровне 0.0090
DOWN_TP_STEP = 0.0050    # TP для каждого уровня

# --- Авто-возврат в UP после DOWN ---
AUTORESTART_UP = True
