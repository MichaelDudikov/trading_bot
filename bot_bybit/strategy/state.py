# === GLOBAL STATE ===

trade_mode: str = "UP"
entry_price_up: float | None = None

strategy_running: bool = False
strategy_task = None

# DOWN-режим
down_active: bool = False
down_base_price: float | None = None
down_usdt_total: float | None = None
down_usdt_per_level: float | None = None
down_levels_completed: int = 0
down_sell_orders: list[str] = []

# === SIMPLE STATISTICS ===
total_trades: int = 0          # всего завершённых сделок
profit_trades: int = 0         # прибыльных
loss_trades: int = 0           # убыточных
total_pnl: float = 0.0         # суммарный PnL

# сохраняем цену покупки DOWN-уровней, чтобы считать PnL
down_level_entries: list[tuple[float, float]] = []
# (entry_price, qty)

# уменьшенные API запросы
last_price_cache = None
last_price_time = 0
last_open_check = 0

reversal_detected: bool = False
