from strategy import state as st
from strategy.stats_storage import save_stats_to_file


def register_trade(pnl: float):
    st.total_trades += 1

    if pnl >= 0:
        st.profit_trades += 1
    else:
        st.loss_trades += 1

    st.total_pnl += pnl
    save_stats_to_file()

    print(f"[TRADE LOG] PnL={round(pnl, 4)}, total={round(st.total_pnl, 4)}")
