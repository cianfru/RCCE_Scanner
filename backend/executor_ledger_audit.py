"""Specific legacy closures verified against native Hyperliquid daily candles.

Do not rewrite fills or infer replacement trades: the bad prices also triggered
exits that might never have occurred with consistent units.
"""
AUDITED_UNIT_MISMATCHES = (
    ('FLOKI/USDT', 1776312447, 1776410772, .030687, .00003153),
    ('PEPE/USDT', 1777608091, 1778801096, .003951, .0000041),
    ('BONK/USDT', 1777565097, 1778801096, .006247, .00000691),
    ('FLOKI/USDT', 1786825036, 1787255729, .020442, .00002317),
    ('PEPE/USDT', 1786825035, 1787257011, .002645, .00000315),
)


def closure_issue(trade):
    try:
        entry_time, exit_time = int(trade.get('entry_time', 0)), int(trade.get('exit_time', 0))
    except (ValueError, TypeError, OverflowError):
        return None
    for symbol, entered, exited, entry, exit_price in AUDITED_UNIT_MISMATCHES:
        if (trade.get('symbol') == symbol and entry_time == entered
                and exit_time == exited
                and trade.get('entry_price') == entry and trade.get('exit_price') == exit_price):
            return 'Verified price-unit mismatch: entry per 1,000 tokens, exit per single token. The recorded closure cannot be treated as a valid strategy loss.'
    return None
