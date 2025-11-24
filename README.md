# 📘 Bybit Trading Bot (UP + DOWN Strategy)

## 🚀 Overview

This project is a fully automated Telegram bot for algorithmic trading on **Bybit Spot** (e.g., STRKUSDT).  
The bot runs 24/7 and combines two core strategies:

### 1) UP Strategy — Trend Following (BUY → TP → BUY → TP → …)

Classic “trend up” logic:

- Buy STRK **market** using the entire available USDT balance
- Place a **limit sell order** at `avg_price + 0.0030`
- Once TP is hit and the limit order is fully filled → open a new BUY
- Repeat indefinitely: **BUY → TP → BUY → TP** as long as the market goes up

### 2) DOWN Strategy — Buying the Dip in Levels

If price reverses down after a BUY:

- The bot detects a **drawdown from entry price**
- Cancels the active TP-limit
- Sells STRK **market** (locking in a small loss / unfilled profit)
- Switches to **DOWN mode**
- Splits your USDT into N equal parts (e.g. 5 levels)
- On each drop (e.g. −0.0090 from the base price) it:
  - Buys STRK with `1/N` of the USDT
  - Places a limit TP at `avg_price + 0.0050` for that portion
- When all TP orders from DOWN mode are fully filled:
  - Bot automatically exits DOWN mode
  - Returns to UP strategy (BUY → TP → BUY → TP)

---

## 🎯 Main Features

- ✅ Automatic trend-following trading on Bybit Spot
- ✅ Automatic detection of downward reversal
- ✅ Multi-level dip buying (DOWN mode, configurable levels/step)
- ✅ Automatic transition: **UP → DOWN → UP**
- ✅ Manual stop with `/stop`
- ✅ Balance & price info buttons
- ✅ Basic **PnL analytics** and **trading stats**
- ✅ **Stats are persisted to `stats.json`** and restored after restart
- ✅ Button to **clear statistics** from Telegram

---

## 🧩 Project Structure

Example layout:

```text
bot/
│── main.py
│── config.py
│── state.py
│── keyboards.py
│
├── handlers/
│   └── main_buttons.py
│
├── bybit_api/
│   ├── client.py
│   ├── detector.py
│   ├── balances.py
│   ├── orders_up.py
│   └── cancel_order.py
│
└── strategy/
    ├── up_cycle.py
    ├── down_cycle.py
    └── state.py
```
The architecture is modular — all Bybit logic, strategy cycles, handlers and keyboards are separated into their own modules.

🛠 Requirements

- Python 3.11+ (you use 3.12)
- aiogram 3.x
- pybit (unified_trading HTTP client)

Install: pip install aiogram pybit

🔐 Configuration

In config.py you should provide:

API_KEY = "YOUR_BYBIT_API_KEY"
SECRET_KEY = "YOUR_BYBIT_SECRET_KEY"
BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"

SYMBOL = "STRKUSDT"          # trading pair
DOWN_LEVELS = 5              # number of averaging levels
DOWN_STEP = 0.0090           # drop per level
DOWN_TP_STEP = 0.0050        # TP above each buy level
DRAWDOWN_TRIGGER = 0.0050    # fall from entry price to start DOWN mode

Make sure your Bybit API key has:

✅ Read balance

✅ Spot trading permissions

▶ Running the Bot

From the project root: python main.py

The bot will:

Load saved statistics from stats.json (if exists)

Start polling Telegram updates

Wait for /start or button interactions
