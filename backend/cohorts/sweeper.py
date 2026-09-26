"""Cohort sweep: whales and proven traders every sweep, everyone else once a day, within a
fixed share of Hyperliquid's per-IP weight budget (1,200/min, shared with the scanner's
candles and HyperLens).

- Focus set (assign.in_focus): $100K+ perp equity, or $100K+ all-time PnL with $10K+
  perp equity (~3,100 wallets). Polled every sweep (at most one sweep per 30 min).
- Every other $10K+ leaderboard wallet: one check a day (jittered 18-30h) to see
  whether it has joined the focus set. Largest accounts are checked first.

- Token bucket at COHORTS_WEIGHT_PER_MIN (default 400); halves for 5 min on a 429.
- Quiet for 20 min after each 4h candle close, when the scanner refreshes every market.
- Resumable: states are saved every 200 wallets; after a restart the unfinished sweep
  continues, skipping wallets already polled since it started.
- Off entirely with COHORTS_ENABLED=0.

    python -m cohorts.sweeper --dry-run 200        (from backend/: sample, aggregate, print; no DB)
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import random
import resource
import time
from typing import Callable, List, Optional

import aiohttp

from cohorts.assign import Position, WalletState, aggregate, in_focus, zscore
from cohorts.source import ApiSource, RateLimited
from cohorts.store import Store

logger = logging.getLogger(__name__)

MIN_EQUITY_FLOOR = 10_000          # discovery floor on leaderboard account value
CHECK_EVERY_S = 24 * 3600          # wallets outside the focus set
CHECK_JITTER_S = 6 * 3600
MIN_SWEEP_GAP_S = 30 * 60           # ~3,100 focus wallets take ~15 min of budget
QUIET_AFTER_CLOSE_S = 20 * 60
STATE_MAX_AGE_S = 2 * 3600         # focus wallets are polled every sweep
BATCH = 200
WORKERS = 4
Z_WINDOW_S = 30 * 86400
Z_MIN_SPAN_S = 3 * 86400


def enabled() -> bool:
    return os.environ.get("COHORTS_ENABLED", "1") not in ("0", "false", "no")


class TokenBucket:
    """Weight budget per minute. take() waits until the weight is available."""

    def __init__(self, per_min: float, capacity: Optional[float] = None,
                 clock: Callable[[], float] = time.monotonic, sleep=asyncio.sleep):
        self.base = self.rate = per_min / 60.0
        self.capacity = capacity if capacity is not None else max(10.0, per_min / 10)
        self.tokens = self.capacity
        self.clock, self.sleep = clock, sleep
        self.last = clock()
        self.penalty_until = 0.0

    def _refill(self):
        now = self.clock()
        if self.penalty_until and now >= self.penalty_until:
            self.rate, self.penalty_until = self.base, 0.0
        self.tokens = min(self.capacity, self.tokens + (now - self.last) * self.rate)
        self.last = now

    async def take(self, n: float) -> None:
        while True:
            self._refill()
            if self.tokens + 1e-6 >= n:          # tolerance: a sub-ULP deficit would never refill
                self.tokens = max(0.0, self.tokens - n)
                return
            await self.sleep(max(1e-3, (n - self.tokens) / self.rate))

    def penalize(self, seconds: float = 300.0) -> None:
        self._refill()
        self.rate = max(self.base / 8, self.rate / 2)
        self.tokens = 0.0
        self.penalty_until = self.clock() + seconds


def quiet_until(now: float) -> Optional[float]:
    """End of the post-close quiet window, or None when outside it."""
    from scan_schedule import BAR_SECONDS
    close = now // BAR_SECONDS * BAR_SECONDS
    return close + QUIET_AFTER_CLOSE_S if now - close < QUIET_AFTER_CLOSE_S else None


def schedule(equity: float, all_time_pnl: Optional[float], now: float, rng: Callable[[], float] = random.random):
    """(in focus, next_poll_at) after a poll: focus wallets every sweep, others about daily."""
    if in_focus(equity, all_time_pnl):
        return True, 0.0
    return False, now + CHECK_EVERY_S + (2 * rng() - 1) * CHECK_JITTER_S


def with_first_seen(raw_positions, previous, now) -> List[Position]:
    return [Position(c, usd, lg, previous.get((c, lg), now)) for c, usd, lg in raw_positions]


class Sweeper:
    def __init__(self, store: Store, source, bucket: TokenBucket, clock: Callable[[], float] = time.time,
                 sleep=asyncio.sleep, respect_quiet: bool = True):
        self.store, self.source, self.bucket = store, source, bucket
        self.clock, self.sleep, self.respect_quiet = clock, sleep, respect_quiet
        self.last: dict = {}

    async def run_once(self) -> dict:
        t0 = self.clock()
        run_id, started, resumed = self.store.open_run(t0)
        todo = self.store.due(t0, polled_since=started if resumed else None)
        queue: asyncio.Queue = asyncio.Queue()
        for item in todo:
            queue.put_nowait(item)
        retried: set = set()
        done: List[tuple] = []
        stats = {"polled": 0, "errors": 0, "rate_limited": 0, "weight": 0}

        async def flush():
            if not done:
                return
            self.store.save_states(list(done))
            self.store.progress(run_id, len(todo), stats["polled"], stats["errors"], stats["rate_limited"], stats["weight"])
            for k in stats:
                stats[k] = 0
            done.clear()

        async def worker():
            while True:
                try:
                    address, pnl = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                if self.respect_quiet:
                    q = quiet_until(self.clock())
                    if q:
                        await self.sleep(q - self.clock())
                await self.bucket.take(self.source.weight)
                stats["weight"] += self.source.weight
                try:
                    raw = await self.source.fetch(address)
                except RateLimited:
                    stats["rate_limited"] += 1
                    self.bucket.penalize()
                    queue.put_nowait((address, pnl))
                    continue
                if raw is None:
                    if address not in retried:          # one retry, at the back of the queue
                        retried.add(address)
                        queue.put_nowait((address, pnl))
                    else:
                        stats["errors"] += 1
                    continue
                now = self.clock()
                equity, positions = raw
                ps = with_first_seen(positions, self.store.previous_first_seen(address), now)
                focus, nxt = schedule(equity, pnl, now)
                done.append((address, now, equity, ps, focus, nxt))
                stats["polled"] += 1
                if len(done) >= BATCH:
                    await flush()

        await asyncio.gather(*(worker() for _ in range(WORKERS)))
        await flush()
        now = self.clock()
        rows = self.aggregate(now)
        self.store.close_run(run_id, now)
        self.last = {"run_id": run_id, "resumed": resumed, "wallets_due": len(todo), "rows": len(rows),
                     "duration_s": round(now - t0, 1)}
        return self.last

    def aggregate(self, now: float) -> List[dict]:
        states = self.store.load_states(now, STATE_MAX_AGE_S)
        rows = aggregate(states, now)
        # All-market rows every sweep; per-symbol rows once per 4h candle (keeps the file ~1 MB/day).
        from scan_schedule import BAR_SECONDS
        last_sym = self.store.latest_symbol_ts()
        if last_sym is not None and last_sym // BAR_SECONDS == now // BAR_SECONDS:
            rows = [r for r in rows if r["symbol"] is None]
        hist = self.store.bias_history(now - Z_WINDOW_S)
        for r in rows:
            h = hist.get((r["dimension"], r["cohort"], r["symbol"]), [])
            span_ok = h and now - min(t for t, _ in h) >= Z_MIN_SPAN_S
            r["bias_z"] = zscore([b for _, b in h], r["bias"], min_points=1) if span_ok else None
        ts = int(now)
        self.store.write_snapshot(ts, rows)
        return rows

    async def loop(self) -> None:
        while True:
            if not enabled() or not self.store.registry_size():
                await self.sleep(600)
                continue
            t0 = self.clock()
            try:
                info = await self.run_once()
                logger.info("Cohorts: sweep %s", info)
            except Exception:
                logger.exception("Cohorts: sweep failed")
            await self.sleep(max(60.0, MIN_SWEEP_GAP_S - (self.clock() - t0)))


# --- wiring -------------------------------------------------------------------------

_store: Optional[Store] = None


def store() -> Store:
    global _store
    if _store is None:
        _store = Store()
    return _store


def registry_from_leaderboard(wallets, now: Optional[float] = None) -> int:
    """Called by HyperLens after its daily leaderboard download (one download serves both).
    wallets: HyperLens TrackedWallet list (market makers already removed)."""
    if not enabled():
        return 0
    rows = [(w.address, w.account_value, w.all_time_pnl) for w in wallets if w.account_value >= MIN_EQUITY_FLOOR]
    return store().update_registry(rows, time.time() if now is None else now)


async def run_forever() -> None:
    per_min = float(os.environ.get("COHORTS_WEIGHT_PER_MIN", "400"))
    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        await Sweeper(store(), ApiSource(session), TokenBucket(per_min)).loop()


# --- dry run ------------------------------------------------------------------------

def _leaderboard(path: Optional[str]) -> dict:
    import json
    import urllib.request
    if path:
        with open(path) as fh:
            return json.load(fh)
    for attempt in range(3):
        try:
            return json.loads(urllib.request.urlopen("https://stats-data.hyperliquid.xyz/Mainnet/leaderboard", timeout=90).read())
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


async def _dry_run(n: int, per_min: float, seed: int, leaderboard: Optional[str] = None) -> None:
    import tempfile
    t0, cpu0 = time.time(), time.process_time()
    raw = _leaderboard(leaderboard)
    rows = []
    for e in raw.get("leaderboardRows", []):
        w = {x[0]: x[1] for x in e.get("windowPerformances", [])}
        av = float(e.get("accountValue") or 0)
        vlm = float((w.get("month") or {}).get("vlm", 0) or 0)
        if av >= MIN_EQUITY_FLOOR and not (av > 0 and vlm / av > 100):
            rows.append((e["ethAddress"].lower(), av, float((w.get("allTime") or {}).get("pnl", 0) or 0)))
    lb_s = time.time() - t0
    del raw
    random.seed(seed)
    sample = random.sample(rows, min(n, len(rows)))
    with tempfile.TemporaryDirectory() as d:
        st = Store(os.path.join(d, "dry.db"))
        st.update_registry(sample, time.time())
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
            sw = Sweeper(st, ApiSource(session), TokenBucket(per_min), respect_quiet=False)
            t1, cpu1 = time.time(), time.process_time()
            info = await sw.run_once()
            sweep_s, sweep_cpu = time.time() - t1, time.process_time() - cpu1
        run = st.runs(1)[0]
        snap = st.snapshot(st.latest_ts(), symbol="")
    print(f"leaderboard: {len(rows)} wallets >= $10K (non market maker), fetched in {lb_s:.0f}s")
    print(f"sweep: {info['wallets_due']} wallets, {run['polled']} polled, {run['errors']} errors, "
          f"{run['rate_limited']} rate-limited, weight {run['weight']}, {sweep_s:.0f}s wall, {sweep_cpu:.2f}s CPU "
          f"({1000 * sweep_cpu / max(1, run['polled']):.1f} ms CPU per wallet)")
    print(f"peak RSS {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024:.0f} MB, total CPU {time.process_time() - cpu0:.1f}s")
    for dim in ("equity", "pnl"):
        print(f"\n{dim:<8}{'cohort':<16}{'wallets':>8}{'pos%':>7}{'long $M':>9}{'short $M':>9}{'bias':>7}{'lev':>6}")
        for r in sorted((r for r in snap if r["dimension"] == dim), key=lambda r: r["cohort"]):
            print(f"{'':<8}{r['cohort']:<16}{r['wallets']:>8}{(r['positioned_pct'] or 0):>7.0f}"
                  f"{r['long_usd'] / 1e6:>9.2f}{r['short_usd'] / 1e6:>9.2f}{(r['bias'] if r['bias'] is not None else float('nan')):>7.2f}"
                  f"{(r['lev_median'] or 0):>6.1f}")
    print(f"\nfocus set: {st.focus_size()} of {len(sample)} sampled wallets")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", type=int, default=200)
    ap.add_argument("--weight-per-min", type=float, default=400)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--leaderboard", help="a saved leaderboard JSON instead of downloading it")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(_dry_run(args.dry_run, args.weight_per_min, args.seed, args.leaderboard))


if __name__ == "__main__":
    main()
