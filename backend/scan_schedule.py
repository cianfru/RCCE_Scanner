"""Wall-clock refresh policy. One worker, no per-market timers or task fan-out."""


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
        self.unavailable = set()

    def prune(self, symbols):
        current = set(symbols)
        self.attempts = {s: t for s, t in self.attempts.items() if s in current}
        self.unavailable.intersection_update(current)

    def next_due(self, symbols, now, tier_for, kind_for, active):
        due = [s for s in symbols if s not in self.attempts or
               now - self.attempts[s] >= refresh_interval(
                   tier=tier_for(s), kind=kind_for(s), active=active,
                   unavailable=s in self.unavailable)]
        # Oldest attempts first prevent a large hot set starving other listings.
        # BTC and ETH lead the initial pass because other engines reference them.
        return min(due, key=lambda s: (self.attempts.get(s, float('-inf')),
                                      s not in ('BTC/USDT', 'ETH/USDT')),
                   default=None)

    def record(self, symbol, now, available):
        self.attempts[symbol] = now
        if available:
            self.unavailable.discard(symbol)
        else:
            self.unavailable.add(symbol)
