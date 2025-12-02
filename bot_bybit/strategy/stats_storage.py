import json
from strategy import state as st

FILE = "stats.json"


def save_stats_to_file():
    data = {
        "total_trades": st.total_trades,
        "profit_trades": st.profit_trades,
        "loss_trades": st.loss_trades,
        "total_pnl": st.total_pnl,
    }

    with open(FILE, "w") as f:
        json.dump(data, f, indent=4)


def load_stats_from_file():
    try:
        with open(FILE, "r") as f:
            data = json.load(f)
    except FileNotFoundError:
        return  # файла нет — статистика нулевая

    st.total_trades = data.get("total_trades", 0)
    st.profit_trades = data.get("profit_trades", 0)
    st.loss_trades = data.get("loss_trades", 0)
    st.total_pnl = data.get("total_pnl", 0.0)


def reset_stats():
    """Очищаем только общую статистику — без UP/DOWN, т.к. теперь статистика единая."""

    st.total_trades = 0
    st.profit_trades = 0
    st.loss_trades = 0
    st.total_pnl = 0.0

    save_stats_to_file()
