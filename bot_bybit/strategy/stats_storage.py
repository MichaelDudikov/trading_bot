import json
from pathlib import Path
from typing import Any
from strategy import state as st

STATS_FILE = Path("stats.json")

# Какие поля сохраняем в файл
STATS_FIELDS = [
    # Общая статистика
    "total_trades",
    "profit_trades",
    "loss_trades",
    "total_pnl",

    # UP
    "up_trades",
    "up_pnl",
    "total_trades_up",
    "total_pnl_up",
    "wins_up",
    "losses_up",

    # DOWN
    "levels_down_closed",
    "total_pnl_down",
    "wins_down",
    "losses_down",
]


def load_stats_from_file() -> None:
    """Загружаем статистику из stats.json в state.py (если файл есть)."""
    if not STATS_FILE.exists():
        return

    try:
        raw = STATS_FILE.read_text(encoding="utf-8")
        data: dict[str, Any] = json.loads(raw)
    except Exception:
        # Файл битый — игнорируем
        return

    for field in STATS_FIELDS:
        if field in data:
            setattr(st, field, data[field])


def save_stats_to_file() -> None:
    """Сохраняем текущую статистику из state.py в stats.json."""
    data: dict[str, Any] = {}

    for field in STATS_FIELDS:
        data[field] = getattr(st, field, 0)

    try:
        STATS_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass


def reset_stats() -> None:
    """Сбрасываем статистику в ноль (и в state.py, и в файле)."""
    # Общая статистика
    st.total_trades = 0
    st.profit_trades = 0
    st.loss_trades = 0
    st.total_pnl = 0.0

    # UP
    st.up_trades = 0
    st.up_pnl = 0.0
    st.total_trades_up = 0
    st.total_pnl_up = 0.0
    st.wins_up = 0
    st.losses_up = 0

    # DOWN
    st.levels_down_closed = 0
    st.total_pnl_down = 0.0
    st.wins_down = 0
    st.losses_down = 0

    save_stats_to_file()
