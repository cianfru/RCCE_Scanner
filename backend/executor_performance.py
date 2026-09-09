"""Read-only attribution for the executor ledger. Never alters trading state."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import math
import time
from executor_ledger_audit import closure_issue


def number(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def performance(positions, trades, marks, initial_balance, now=None, portfolio=None):
    now = now or time.time()
    closed = [t for t in trades if number(t.get('pnl_usd')) is not None and number(t.get('exit_time'))]
    realized = sum(float(t['pnl_usd']) for t in closed)
    issues = [{**t, 'quality_issue': closure_issue(t)} for t in closed if closure_issue(t)]
    flagged_pnl = sum(float(t['pnl_usd']) for t in issues)
    wins = sum(float(t['pnl_usd']) > 0 for t in closed)
    losses = sum(float(t['pnl_usd']) < 0 for t in closed)
    flat = len(closed) - wins - losses
    gain = sum(max(0, float(t['pnl_usd'])) for t in closed)
    loss = -sum(min(0, float(t['pnl_usd'])) for t in closed)
    valued = []
    for p in positions:
        row = dict(p)
        symbol = p['symbol']
        mark = marks.get(symbol, {})
        price, entry, cost = number(mark.get('price')), number(p.get('entry_price')), number(p.get('cost_usd'))
        reason = None
        if symbol.rsplit('/', 1)[-1] not in ('USD', 'USDT', 'USDC', 'USDH'):
            reason = 'Legacy cross-quoted position: USD valuation needs reconciliation.'
        elif number(p.get('peak_unrealized_pct')) is not None and float(p['peak_unrealized_pct']) > 100000 and not mark.get('entry_unit_verified'):
            reason = 'Legacy price-unit anomaly: entry history needs reconciliation.'
        elif entry is None or entry <= 0 or cost is None or cost <= 0:
            reason = 'Missing or invalid entry cost.'
        elif price is None or price <= 0:
            reason = 'No reliable current quote available; frozen delisting prices are not used.'
        observed = number(mark.get('observed_at'))
        if not reason and (not observed or now - observed > 6 * 3600):
            reason = 'Scanner price is older than six hours or has no observation time.'
        pct = None if reason else (price / entry - 1) * (100 if p.get('side') != 'SHORT' else -100)
        row.update(mark_source=mark.get("source"), mark_price=price if not reason else None, mark_observed_at=observed,
                   unrealized_pnl_pct=pct, unrealized_pnl_usd=None if reason else cost * pct / 100,
                   valuation_issue=reason)
        valued.append(row)
    unrealized = sum(p['unrealized_pnl_usd'] for p in valued if p['unrealized_pnl_usd'] is not None)
    priced_count = sum(p['unrealized_pnl_usd'] is not None for p in valued)
    complete = priced_count == len(positions) and len(closed) == len(trades) and not issues
    cash = number((portfolio or {}).get('cash'))
    cash_difference = None
    if cash is not None and all(p.get('side', 'LONG') == 'LONG' for p in positions):
        expected_cash = initial_balance + realized - sum(number(p.get('cost_usd')) or 0 for p in positions)
        cash_difference = cash - expected_cash
    accounting_reconciled = cash_difference is None or abs(cash_difference) <= max(1, initial_balance * .0001)
    total = realized + unrealized
    starts = [float(t['entry_time']) for t in [*trades, *positions] if number(t.get('entry_time')) and float(t['entry_time']) > 0]
    months = defaultdict(lambda: {'pnl_usd': 0, 'closed': 0, 'wins': 0})
    cumulative, curve = 0, []
    for t in sorted(closed, key=lambda t: t['exit_time']):
        cumulative += t['pnl_usd']
        curve.append({'time': t['exit_time'], 'pnl_usd': cumulative})
        month = datetime.fromtimestamp(t['exit_time'], timezone.utc).strftime('%Y-%m')
        months[month]['pnl_usd'] += t['pnl_usd']
        months[month]['closed'] += 1
        months[month]['wins'] += t['pnl_usd'] > 0
    return {
        'as_of': now, 'first_entry_at': min(starts) if starts else None,
        'history_days': int((now - min(starts)) / 86400) if starts else 0,
        'initial_balance_usd': initial_balance,
        'realized_pnl_usd': realized, 'flagged_closed_trades': len(issues),
        'flagged_closed_pnl_usd': flagged_pnl, 'unflagged_realized_pnl_usd': realized-flagged_pnl,
        'closed_issues': issues, 'open_profitable_count': sum((p['unrealized_pnl_usd'] or 0)>0 for p in valued), 'unrealized_pnl_usd': unrealized,
        'combined_pnl_usd': total if complete else None,
        'valued_pnl_subtotal_usd': total,
        'return_on_starting_capital_pct': total / initial_balance * 100 if complete and initial_balance > 0 else None,
        'estimated_equity_usd': initial_balance + total if complete and accounting_reconciled else None,
        'cash_reconciliation_difference_usd': cash_difference, 'accounting_reconciled': accounting_reconciled,
        'unmatched_holdings': sorted(p['symbol'] for p in positions if portfolio is not None and p['symbol'] not in portfolio.get('holdings', {})),
        'valuation_complete': complete, 'priced_positions': priced_count, 'open_positions': len(positions),
        'unpriced_cost_usd': sum(max(0, number(p.get('cost_usd')) or 0) for p in valued if p['valuation_issue']),
        'closed_trades': len(closed), 'unusable_closed_records': len(trades)-len(closed),
        'wins': wins, 'losses': losses, 'breakeven': flat,
        'closed_win_rate': wins / len(closed) * 100 if closed else None,
        'profit_factor': gain / loss if loss else None,
        'exit_reasons': dict(Counter(t.get('exit_signal', 'UNKNOWN') for t in closed)),
        'monthly_realized': [{'month': key, **value} for key, value in sorted(months.items())],
        'realized_curve': curve, 'positions': valued,
        'basis': 'Recorded executor ledger with scanner marks and explicitly mapped external reference quotes. USD and USD-pegged quotes are treated as equivalent for reference valuation. Paper results exclude fees, funding and slippage. The realized curve is not an equity curve. Legacy records have not been rewritten.',
    }
