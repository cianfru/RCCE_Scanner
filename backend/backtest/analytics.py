"""
analytics.py
~~~~~~~~~~~~
Performance metrics, per-signal breakdown, and condition analysis
for backtest results.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np


# ---------------------------------------------------------------------------
# Output containers
# ---------------------------------------------------------------------------

@dataclass
class SignalStats:
    """Per-signal performance breakdown."""
    signal: str
    count: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    avg_return_pct: float = 0.0
    avg_bars_held: float = 0.0
    total_pnl_pct: float = 0.0
    best_pct: float = 0.0
    worst_pct: float = 0.0


@dataclass
class ConditionAnalysis:
    """Predictive value of a single condition in the Decision Matrix."""
    condition_name: str
    condition_index: int
    times_true: int = 0
    times_false: int = 0
    avg_return_when_true: float = 0.0
    avg_return_when_false: float = 0.0
    predictive_value: float = 0.0   # true_return - false_return


@dataclass
class BacktestMetrics:
    """Full performance report."""
    # Returns
    total_return_pct: float = 0.0
    btc_return_pct: float = 0.0
    alpha_pct: float = 0.0
    annualized_return_pct: float = 0.0

    # Risk
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0

    # Activity
    total_trades: int = 0
    avg_bars_held: float = 0.0
    avg_trade_return_pct: float = 0.0
    best_trade_pct: float = 0.0
    worst_trade_pct: float = 0.0
    avg_win_pct: float = 0.0
    avg_loss_pct: float = 0.0

    # Per-signal breakdown
    signal_stats: Dict[str, SignalStats] = field(default_factory=dict)

    # Condition analysis
    condition_analysis: List[ConditionAnalysis] = field(default_factory=list)


# ---------------------------------------------------------------------------
# The 10 Decision Matrix conditions (names for reporting)
# ---------------------------------------------------------------------------

CONDITION_NAMES = [
    "RCCE Regime (MARKUP/BLOWOFF/REACC)",
    "Z-Score > 0",
    "Heatmap Heat ≥ 40",
    "Volume Regime (HIGH/SPIKE)",
    "Exhaustion (NEUTRAL/RECOVERING)",
    "Consensus ≥ 60%",
    "Divergence (NONE/POSITIVE)",
    "Positioning (neutral/underweight)",
    "Fear & Greed < 75",
    "Stablecoin (GROWING/STABLE)",
]


# ---------------------------------------------------------------------------
# Core metrics computation
# ---------------------------------------------------------------------------

def compute_metrics(
    trades: list,
    equity_curve: List[Tuple[float, float]],
    btc_equity_curve: List[Tuple[float, float]],
    test_days: int,
) -> BacktestMetrics:
    """Compute full backtest performance metrics.

    Parameters
    ----------
    trades : list[Trade]
        All completed trades from position manager.
    equity_curve : list[(timestamp, equity)]
        Strategy equity over time.
    btc_equity_curve : list[(timestamp, equity)]
        BTC buy-and-hold equity (same initial capital).
    test_days : int
        Number of calendar days in the test period.
    """
    metrics = BacktestMetrics()

    if not equity_curve:
        return metrics

    # --- Returns ---
    initial_equity = equity_curve[0][1]
    final_equity = equity_curve[-1][1]
    metrics.total_return_pct = _pct_change(initial_equity, final_equity)

    if btc_equity_curve:
        btc_initial = btc_equity_curve[0][1]
        btc_final = btc_equity_curve[-1][1]
        metrics.btc_return_pct = _pct_change(btc_initial, btc_final)

    metrics.alpha_pct = metrics.total_return_pct - metrics.btc_return_pct

    if test_days > 0:
        years = test_days / 365.0
        if years > 0:
            total_mult = final_equity / initial_equity if initial_equity > 0 else 1
            metrics.annualized_return_pct = (total_mult ** (1 / years) - 1) * 100

    # --- Equity-based risk metrics ---
    equities = np.array([e[1] for e in equity_curve], dtype=np.float64)
    metrics.max_drawdown_pct = _max_drawdown(equities)

    # Daily returns (approximate: group by ~6 bars for 4h data = 1 day)
    daily_returns = _compute_periodic_returns(equities, period=6)
    if len(daily_returns) > 1:
        metrics.sharpe_ratio = _sharpe(daily_returns)
        metrics.sortino_ratio = _sortino(daily_returns)

    if metrics.max_drawdown_pct < 0:
        metrics.calmar_ratio = metrics.annualized_return_pct / abs(metrics.max_drawdown_pct)

    # --- Trade statistics ---
    closed = [t for t in trades if t.pnl_pct is not None]
    metrics.total_trades = len(closed)

    if closed:
        pnls = [t.pnl_pct for t in closed]
        bars = [t.bars_held for t in closed]

        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]

        metrics.win_rate = len(wins) / len(pnls) * 100 if pnls else 0
        metrics.avg_trade_return_pct = sum(pnls) / len(pnls)
        metrics.avg_bars_held = sum(bars) / len(bars)
        metrics.best_trade_pct = max(pnls)
        metrics.worst_trade_pct = min(pnls)

        metrics.avg_win_pct = sum(wins) / len(wins) if wins else 0
        metrics.avg_loss_pct = sum(losses) / len(losses) if losses else 0

        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        metrics.profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    # --- Per-signal breakdown ---
    metrics.signal_stats = _compute_signal_stats(closed)

    return metrics


# ---------------------------------------------------------------------------
# Per-signal breakdown
# ---------------------------------------------------------------------------

def _compute_signal_stats(trades: list) -> Dict[str, SignalStats]:
    """Group trades by entry signal and compute stats."""
    by_signal: Dict[str, list] = {}
    for t in trades:
        sig = t.entry_signal
        by_signal.setdefault(sig, []).append(t)

    result = {}
    for sig, sig_trades in sorted(by_signal.items()):
        pnls = [t.pnl_pct for t in sig_trades if t.pnl_pct is not None]
        bars = [t.bars_held for t in sig_trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]

        stats = SignalStats(
            signal=sig,
            count=len(sig_trades),
            wins=len(wins),
            losses=len(losses),
            win_rate=len(wins) / len(pnls) * 100 if pnls else 0,
            avg_return_pct=sum(pnls) / len(pnls) if pnls else 0,
            avg_bars_held=sum(bars) / len(bars) if bars else 0,
            total_pnl_pct=sum(pnls),
            best_pct=max(pnls) if pnls else 0,
            worst_pct=min(pnls) if pnls else 0,
        )
        result[sig] = stats

    return result


# ---------------------------------------------------------------------------
# Condition analysis
# ---------------------------------------------------------------------------

def compute_condition_analysis(
    bar_results: list,
    trades: list,
) -> List[ConditionAnalysis]:
    """Analyze which conditions predict positive returns.

    For each of the 10 conditions, compare average forward return
    when the condition was True vs False at entry.

    Parameters
    ----------
    bar_results : list[BarResult]
        All bar results from replay (with condition_flags).
    trades : list[Trade]
        Completed trades.
    """
    if not trades or not bar_results:
        return []

    # Build lookup: (symbol, entry_time) -> trade
    trade_lookup: Dict[tuple, object] = {}
    for t in trades:
        if t.pnl_pct is not None:
            trade_lookup[(t.symbol, t.entry_time)] = t

    # Build lookup: (symbol, timestamp) -> bar_result
    bar_lookup: Dict[tuple, object] = {}
    for b in bar_results:
        bar_lookup[(b.symbol, b.timestamp)] = b

    # For each trade, find the bar at entry to get condition flags
    num_conditions = len(CONDITION_NAMES)
    true_returns: Dict[int, list] = {i: [] for i in range(num_conditions)}
    false_returns: Dict[int, list] = {i: [] for i in range(num_conditions)}

    for (sym, entry_time), trade in trade_lookup.items():
        bar = bar_lookup.get((sym, entry_time))
        if bar is None or not bar.condition_flags:
            continue

        flags = bar.condition_flags
        pnl = trade.pnl_pct

        for i in range(min(len(flags), num_conditions)):
            if flags[i]:
                true_returns[i].append(pnl)
            else:
                false_returns[i].append(pnl)

    # Compute analysis
    analysis = []
    for i in range(num_conditions):
        tr = true_returns[i]
        fr = false_returns[i]

        avg_true = sum(tr) / len(tr) if tr else 0
        avg_false = sum(fr) / len(fr) if fr else 0

        ca = ConditionAnalysis(
            condition_name=CONDITION_NAMES[i],
            condition_index=i,
            times_true=len(tr),
            times_false=len(fr),
            avg_return_when_true=round(avg_true, 3),
            avg_return_when_false=round(avg_false, 3),
            predictive_value=round(avg_true - avg_false, 3),
        )
        analysis.append(ca)

    return analysis


# ---------------------------------------------------------------------------
# Math helpers
# ---------------------------------------------------------------------------

def _pct_change(start: float, end: float) -> float:
    if start <= 0:
        return 0.0
    return (end - start) / start * 100.0


def _max_drawdown(equities: np.ndarray) -> float:
    """Maximum peak-to-trough drawdown as a negative percentage."""
    if len(equities) < 2:
        return 0.0
    peak = np.maximum.accumulate(equities)
    dd = (equities - peak) / peak * 100.0
    return float(np.min(dd))


def _compute_periodic_returns(equities: np.ndarray, period: int = 6) -> np.ndarray:
    """Compute returns over fixed periods (default: 6 bars ≈ 1 day for 4h)."""
    if len(equities) < period + 1:
        return np.array([])
    # Sample every `period` bars
    sampled = equities[::period]
    if len(sampled) < 2:
        return np.array([])
    returns = np.diff(sampled) / sampled[:-1]
    return returns


def _sharpe(returns: np.ndarray, periods_per_year: float = 365.0) -> float:
    """Annualized Sharpe ratio (assumes 0 risk-free rate)."""
    if len(returns) < 2:
        return 0.0
    mean_r = np.mean(returns)
    std_r = np.std(returns, ddof=1)
    if std_r < 1e-10:
        return 0.0
    return float(mean_r / std_r * math.sqrt(periods_per_year))


def _sortino(returns: np.ndarray, periods_per_year: float = 365.0) -> float:
    """Annualized Sortino ratio (downside deviation only)."""
    if len(returns) < 2:
        return 0.0
    mean_r = np.mean(returns)
    downside = returns[returns < 0]
    if len(downside) < 1:
        return float("inf") if mean_r > 0 else 0.0
    dd = np.std(downside, ddof=1)
    if dd < 1e-10:
        return 0.0
    return float(mean_r / dd * math.sqrt(periods_per_year))
