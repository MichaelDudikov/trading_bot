# ============================================================
#                   GLOBAL STATE OF BOT
# ============================================================

# ——— Основной режим стратегии ———
trade_mode: str = "UP"            # "UP" → BUY/TP цикл, "DOWN" → откуп уровней

# ——— UP-параметры ———
entry_price_up: float | None = None
strategy_running: bool = False
strategy_task = None              # asyncio.Task | None


# ============================================================
#                     DOWN PARAMETERS
# ============================================================
down_active: bool = False
down_base_price: float | None = None
down_usdt_total: float | None = None
down_usdt_per_level: float | None = None
down_levels_completed: int = 0
down_sell_orders: list[str] = []

# Для статистики DOWN (чтобы PyCharm не ругался)
down_entry_prices: list[float] = []     # цены входа по уровням
down_qty_list: list[float] = []         # количества STRK по уровням


# ============================================================
#                    GLOBAL STATISTICS
# ============================================================

# ——— Общая статистика ———
total_trades: int = 0              # все сделки (UP + DOWN)
profit_trades: int = 0
loss_trades: int = 0
total_pnl: float = 0.0


# ============================================================
#                       UP STATISTICS
# ============================================================

total_trades_up: int = 0
total_pnl_up: float = 0.0
wins_up: int = 0
losses_up: int = 0

last_up_tp_order_id: str | None = None
pnl_total: float = 0.0             # полная прибыль UP (историческая)
up_trades: int = 0                 # количество UP-сделок
up_pnl: float = 0.0                # PnL по UP


# ============================================================
#                      DOWN STATISTICS
# ============================================================

levels_down_closed: int = 0        # закрыто уровней TP
down_pnl: float = 0.0
total_pnl_down: float = 0.0        # суммарный PnL DOWN
wins_down: int = 0
losses_down: int = 0


# ============================================================
#                AUTO-RESTART FEATURES
# ============================================================

autorestart_up: bool = True        # автоматический возврат в UP после DOWN
