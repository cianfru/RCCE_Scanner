"""backtest/live_logic_trades.py: the trade tables beside the scorer."""
from backtest.larsson_study import INITIAL_CAPITAL
from backtest.live_logic_trades import summarize
from backtest.position_manager import Trade


def test_tables_by_entry_coin_and_exit():
    k = INITIAL_CAPITAL / 100.0                      # 1% of a window's starting capital
    trades = [(1, Trade("BTC/USDT", entry_signal="STRONG_LONG", exit_signal="TRIM", pnl_usd=2 * k, pnl_pct=4.0)),
              (1, Trade("ETH/USDT", entry_signal="LIGHT_LONG", exit_signal="STOP_LOSS", pnl_usd=-1 * k, pnl_pct=-2.0)),
              (2, Trade("BTC/USDT", entry_signal="LIGHT_LONG", exit_signal=None, pnl_usd=3 * k, pnl_pct=6.0))]
    out = summarize(trades)
    assert out["by_entry"]["STRONG_LONG"] == {"trades": 1, "wins": 1, "pnl_pct": 2.0, "median_trade_pct": 4.0}
    assert out["by_entry"]["LIGHT_LONG"] == {"trades": 2, "wins": 1, "pnl_pct": 2.0, "median_trade_pct": 2.0}
    assert out["by_coin_pnl_pct"] == {"BTC/USDT": 5.0, "ETH/USDT": -1.0}
    assert out["exits"] == {"TRIM": 1, "STOP_LOSS": 1, "END": 1}
