"""Conservative spot eligibility; volume is a screen, not proof of order-book depth."""
import math
import os
import time

MIN_SPOT_VOLUME = max(0, float(os.environ.get('REFLEX_SPOT_MIN_VOLUME_USD', '25000')))


def volume_reason(market):
    if market.get('kind') != 'spot':
        return None
    if market.get('quote') != 'USDC':
        return 'Only USDC-quoted spot markets are currently supported'
    try:
        volume = float(market.get('volume_24h_usd'))
    except (ValueError, TypeError):
        return '24-hour volume unavailable'
    if not math.isfinite(volume) or volume < MIN_SPOT_VOLUME:
        return f'24-hour volume below ${MIN_SPOT_VOLUME:,.0f}'
    return None


def candle_reason(ohlcv, timeframe, now=None):
    """Require usable closed bars; never fill missing trades with invented candles."""
    if ohlcv is None:
        return 'Candle history unavailable'
    step = {'4h': 14400, '1d': 86400}.get(timeframe)
    if step is None:
        return None
    now = time.time() if now is None else now
    try:
        fields = ('timestamp', 'open', 'high', 'low', 'close', 'volume')
        n = len(ohlcv['timestamp'])
        if n < 51 or any(len(ohlcv[k]) != n for k in fields):
            return 'Fewer than 50 closed candles'
        rows = [[float(ohlcv[k][i]) for k in fields] for i in range(n)]
        closed = [r for r in rows if r[0] / 1000 + step <= now]
        if len(closed) < 50:
            return 'Fewer than 50 closed candles'
        if now - (closed[-1][0] / 1000 + step) > step * 2:
            return 'Recent candles are stale'
        recent = closed[-30:]
        for ts, op, hi, lo, cl, vol in rows:
            if not all(math.isfinite(v) for v in (ts, op, hi, lo, cl, vol)) or min(op, hi, lo, cl) <= 0 or vol < 0:
                return 'Invalid candle prices or volume'
            if not (lo <= min(op, cl) <= max(op, cl) <= hi):
                return 'Invalid candle price range'
        gaps = [(b[0]-a[0])/1000 for a,b in zip(recent,recent[1:])]
        if any(g <= 0 for g in gaps) or sum(g <= step * 1.01 for g in gaps) / len(gaps) < .8:
            return 'Recent candle history is too sparse'
        if sum(r[5] > 0 and r[2] > r[3] for r in recent) / len(recent) < .8:
            return 'Too few recent candles have trading activity'
    except (KeyError, ValueError, TypeError, IndexError):
        return 'Malformed candle history'
    return None
