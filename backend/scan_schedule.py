"""Wall-clock refresh policy. One worker, no per-market timers or task fan-out."""

BAR_SECONDS = 4 * 3600      # every daily close is also a 4h close
SETTLE_SECONDS = 15         # give the exchange a moment to publish the finished candle


def last_bar_close(wall):
    """Most recent 4h candle close (UTC epoch seconds) that is ready to fetch."""
    return (wall - SETTLE_SECONDS) // BAR_SECONDS * BAR_SECONDS + SETTLE_SECONDS


def refresh_interval(*, tier, kind, active, unavailable=False):
    # Seconds between attempts, not promises of exact delivery under load.
    interval = 900 if tier == "hot" else 3600
    if tier == "cold":
        interval = max(interval, 3600)
    elif tier == "deep_cold":
        interval = max(interval, 14400)
    if unavailable:
        interval = max(interval, 3600)
    if not active:
        interval = max(interval, 3600)
    return interval


class ScanSchedule:
    def __init__(self):
        self.attempts = {}
        self.wall_attempts = {}
        self.unavailable = set()

    def prune(self, symbols):
        current = set(symbols)
        self.attempts = {s: t for s, t in self.attempts.items() if s in current}
        self.wall_attempts = {s: t for s, t in self.wall_attempts.items() if s in current}
        self.unavailable.intersection_update(current)

    def next_due(self, symbols, now, tier_for, kind_for, active, wall=None):
        # A candle close makes every market's signal stale until it is refetched, so
        # each market is refreshed once after every 4h close before interval work.
        # Without this, hourly and 4-hourly tiers left most of the universe on the
        # previous candle (and the decision pipeline withheld their signals) for up
        # to an hour after each close.
        if wall is not None:
            close = last_bar_close(wall)
            fresh = [s for s in symbols if s not in self.unavailable
                     and self.wall_attempts.get(s, float('-inf')) < close]
            if fresh:
                return min(fresh, key=lambda s: (s not in ('BTC/USDT', 'ETH/USDT'), s != 'BTC/USDT',
                                                 self.wall_attempts.get(s, float('-inf'))))
        due = [s for s in symbols if s not in self.attempts or
               now - self.attempts[s] >= refresh_interval(
                   tier=tier_for(s), kind=kind_for(s), active=active,
                   unavailable=s in self.unavailable)]
        # Oldest attempts first prevent a large hot set starving other listings.
        # BTC and ETH lead the initial pass because other engines reference them.
        return min(due, key=lambda s: (self.attempts.get(s, float('-inf')),
                                      s not in ('BTC/USDT', 'ETH/USDT')),
                   default=None)

    def record(self, symbol, now, available, wall=None):
        self.attempts[symbol] = now
        if wall is not None:
            self.wall_attempts[symbol] = wall
        if available:
            self.unavailable.discard(symbol)
        else:
            self.unavailable.add(symbol)
