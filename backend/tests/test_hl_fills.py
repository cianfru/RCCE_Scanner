import asyncio
import collections
import time
from collections import deque

import pytest

import hl_fills
import hl_intelligence as hl
import trader_entries as te
import trader_profile as tp
from cohorts.sweeper import TokenBucket
from hl_intelligence import PositionSnapshot, TrackedWallet, WalletPosition

A = "0x" + "a" * 40      # tracked
U = "0x" + "e" * 40      # not tracked (a pasted address)
V = "0x" + "f" * 40
NOW = time.time()


def hf(t_s, side, px, sz, start, coin="ETH", d=None, pnl=0.0, fee=0.1, tid=None):
    """A Hyperliquid fill as userFills / userFillsByTime send it."""
    t = int(t_s * 1000)
    return {"coin": coin, "px": str(px), "sz": str(sz), "side": side, "time": t, "startPosition": str(start),
            "dir": d or ("Open Long" if side == "B" else "Close Long"), "closedPnl": str(pnl), "hash": "0x0",
            "oid": 1, "crossed": True, "fee": str(fee), "tid": tid if tid is not None else t // 7 + len(coin),
            "feeToken": "USDC", "twapId": None}


def seq(t0):
    """open, add, trim, close, open, flip, close (as in test_trader_profile), a spot and a builder-dex fill."""
    return [
        hf(t0, "B", 100, 10, 0), hf(t0 + 60, "B", 110, 5, 10),
        hf(t0 + 120, "A", 120, 5, 15, pnl=83.33), hf(t0 + 180, "A", 130, 10, 10, pnl=266.67),
        hf(t0 + 240, "B", 125, 4, 0), hf(t0 + 300, "A", 120, 10, 4, pnl=-20, d="Long > Short"),
        hf(t0 + 360, "B", 110, 6, -6, pnl=60, d="Close Short"),
        hf(t0 + 30, "B", 1, 100, 0, coin="PURR/USDC", d="Buy"), hf(t0 + 30, "B", 1, 1, 0, coin="xyz:TSLA"),
    ]


class FakeHL:
    """userFillsByTime / userTwapSliceFillsByTime / userTwapSliceFills / userFills over fixed lists."""

    def __init__(self):
        self.regular = collections.defaultdict(list)
        self.twap = collections.defaultdict(list)
        self.calls = []
        self.fail_at = {}          # request type -> the call number (1-based) answered with a 429


    async def http(self, session, body):
        self.calls.append(body)
        n = sum(1 for c in self.calls if c["type"] == body["type"])
        if self.fail_at.get(body["type"]) == n:
            raise hl_fills.RateLimited()
        u, kind = body["user"], body["type"]
        if kind == "userFillsByTime":
            fs = sorted((f for f in self.regular[u] if f["time"] >= body["startTime"]), key=lambda f: f["time"])
            return fs[:hl_fills.PAGE]
        if kind == "userTwapSliceFillsByTime":
            fs = sorted((f for f in self.twap[u] if f["time"] >= body["startTime"]), key=lambda f: f["time"])
            return [{"fill": f, "twapId": 1} for f in fs[:hl_fills.PAGE]]
        if kind == "userTwapSliceFills":
            fs = sorted(self.twap[u], key=lambda f: -f["time"])[:hl_fills.PAGE]
            return [{"fill": f, "twapId": 1} for f in fs]
        if kind == "userFills":
            return sorted(self.regular[u], key=lambda f: -f["time"])[:2000]
        raise AssertionError(kind)


@pytest.fixture
def fake(tmp_path, monkeypatch):
    hl_fills.use_store(hl_fills.Store(str(tmp_path / "fills.db")))
    for name in ("_dirty", "_retry_at", "_waiters", "_rev"):
        monkeypatch.setattr(hl_fills, name, {})
    for name in ("_view_requests", "_priority", "_load_cache"):
        monkeypatch.setattr(hl_fills, name, collections.OrderedDict())
    monkeypatch.setattr(hl_fills, "_weight_log", collections.deque())
    monkeypatch.setattr(hl_fills, "_bucket", TokenBucket(1e6, capacity=1e6))
    monkeypatch.setattr(hl_fills, "_backfill_bucket", TokenBucket(1e6, capacity=1e6))
    monkeypatch.setattr(hl_fills, "live_limiter", hl_fills.LiveLimiter(2))
    monkeypatch.setattr(hl_fills, "_quiet", lambda now: False)
    for name, value in (("_started_at", None), ("_current", None), ("_last_attempt", None),
                        ("_last_exception", None), ("_state", "not started"), ("_task", None)):
        monkeypatch.setattr(hl_fills, name, value, raising=False)
    monkeypatch.setattr(hl, "_roster", [TrackedWallet(A, account_value=1e6)])
    monkeypatch.setattr(te, "_fills_cache", {})
    monkeypatch.setattr(tp, "_live_loads", {})
    f = FakeHL()
    monkeypatch.setattr(hl_fills, "_http", f.http)

    async def te_post(session, body):
        return await f.http(session, body)
    monkeypatch.setattr(te, "_post", te_post)
    yield f
    hl_fills.use_store(None)


def run(coro):
    return asyncio.run(coro)


def test_store_keeps_a_fill_read_twice_once(fake):
    st = hl_fills.store()
    wid = st.wallet(A)["id"]
    rows = [hl_fills.row_of(f, False) for f in seq(NOW - 3600)[:3]]
    assert st.insert(wid, rows) == 3
    assert st.insert(wid, rows) == 0                         # same fills again: nothing new
    assert st.count(wid) == 3
    # A self-trade (same trade id, both sides) is two fills.
    both = [hl_fills.row_of(hf(NOW - 10, "B", 1, 1, 0, tid=99), False), hl_fills.row_of(hf(NOW - 10, "A", 1, 1, 1, tid=99), False)]
    assert st.insert(wid, both) == 2
    # Through a read: the overlap before the cursor is read again and ignored.
    fake.regular[A] = seq(NOW - 3600)
    assert run(hl_fills.sync(None, A, "backfill")) == 4       # 7 perp fills, 3 already stored; spot/xyz dropped
    assert run(hl_fills.sync(None, A, "change")) == 0


def test_incremental_read_starts_at_the_last_stored_fill(fake, monkeypatch):
    monkeypatch.setattr(hl_fills, "PAGE", 3)                   # page through 7 fills 3 at a time
    fake.regular[A] = seq(NOW - 7200)
    assert run(hl_fills.sync(None, A, "backfill")) == 7
    w = hl_fills._meta[A]
    assert w["backfilled_at"] and w["n"] == 7
    starts = [c["startTime"] for c in fake.calls if c["type"] == "userFillsByTime"]
    assert starts[0] == pytest.approx((NOW - hl_fills.RETENTION_DAYS * 86400) * 1000, abs=5000)
    assert len(starts) >= 3 and starts == sorted(starts)       # forward, page by page
    assert w["covered_from"] == pytest.approx(NOW - hl_fills.RETENTION_DAYS * 86400, abs=5)
    # New fills after the cursor: only they are read and stored.
    fake.calls.clear()
    fake.regular[A] += [hf(NOW - 30, "B", 111, 2, 0), hf(NOW - 20, "B", 112, 1, 2)]
    cursor = w["cursor_ms"]
    assert run(hl_fills.sync(None, A, "change")) == 2
    first = next(c for c in fake.calls if c["type"] == "userFillsByTime")
    assert first["startTime"] == cursor - hl_fills.OVERLAP_MS
    assert [c["type"] for c in fake.calls].count("userTwapSliceFills") == 0    # the cursor, not the latest 2,000
    assert hl_fills._meta[A]["cursor_ms"] >= int((NOW - 20) * 1000)
    # A sweep of a wallet that never used timed orders skips the timed-order request.
    fake.calls.clear()
    run(hl_fills.sync(None, A, "sweep"))
    assert [c["type"] for c in fake.calls] == ["userFillsByTime"]


def test_timed_order_backfill(fake, monkeypatch):
    monkeypatch.setattr(hl_fills, "PAGE", 3)
    since = NOW - hl_fills.RETENTION_DAYS * 86400
    B = "0x" + "b" * 40
    monkeypatch.setattr(hl, "_roster", [TrackedWallet(A, account_value=1e6), TrackedWallet(B, account_value=1e6)])
    # The latest slices reach back past the window: those inside it are all there is.
    fake.twap[A] = [hf(since - 86400 * d, "B", 1, 1, 0, tid=10 + d) for d in (1, 2)] + \
                   [hf(NOW - 600 + i, "B", 1, 1, i, tid=20 + i) for i in range(2)]
    run(hl_fills.sync(None, A, "backfill"))
    w = hl_fills._meta[A]
    assert w["n"] == 2 and w["twap_seen"] and w["covered_from"] == pytest.approx(since, abs=5)
    assert [c["type"] for c in fake.calls].count("userTwapSliceFillsByTime") == 0
    # A heavy user (a full page, all recent): read forward by time from an estimated start.
    fake.calls.clear()
    fake.twap[B] = [hf(NOW - 3000 + 10 * i, "B", 1, 1, i, tid=100 + i) for i in range(12)]
    run(hl_fills.sync(None, B, "backfill"))
    assert hl_fills._meta[B]["n"] == 12
    assert [c["type"] for c in fake.calls].count("userTwapSliceFillsByTime") >= 2
    assert hl_fills._meta[B]["covered_from"] < NOW - 2000


def test_stored_fills_classify_like_the_live_path(fake):
    t0 = NOW - 5000
    fake.regular[A] = seq(t0)
    fake.twap[A] = [hf(t0 + 400, "B", 105, 1, 0, tid=5001), hf(t0 + 460, "B", 106, 1, 1, tid=5002),
                    hf(t0 + 120, "A", 120, 5, 15, pnl=83.33, tid=5003)]   # a slice at a regular fill's time: dropped by both
    live = run(te._wallet_fills(None, A, max_age=0))
    run(hl_fills.sync(None, A, "backfill"))
    stored = hl_fills.stored_fills(A)
    assert stored is not None and stored["stored"]
    for k in ("coin", "time", "px", "sz", "side", "dir", "startPosition", "twap", "tid", "closedPnl", "fee"):
        assert k in stored["fills"][0]
    live_perp = [f for f in live["fills"] if tp.is_perp_fill(f)]
    assert len(stored["fills"]) == len(live_perp)
    assert tp.classify_fills(stored["fills"]) == tp.classify_fills(live["fills"])
    assert tp.round_trips(tp.classify_fills(stored["fills"])) == tp.round_trips(tp.classify_fills(live["fills"]))
    assert te.position_bursts(stored["fills"], "ETH", NOW) == te.position_bursts(live["fills"], "ETH", NOW)


def test_live_read_limit_and_backfill_budget(fake, monkeypatch):
    clock = [0.0]
    lim = hl_fills.LiveLimiter(3, clock=lambda: clock[0])
    assert all(lim.try_acquire()[0] for _ in range(3))
    ok, retry = lim.try_acquire()
    assert not ok and retry == pytest.approx(60) and lim.refused == 1
    clock[0] = 30
    assert not lim.try_acquire()[0]
    clock[0] = 60.01
    assert lim.try_acquire()[0] and lim.used() == 1
    # Weight: 20 a request plus 1 per 20 fills; the backfill also draws on its own smaller bucket.
    main, back = TokenBucket(300, capacity=300), TokenBucket(240, capacity=240)
    monkeypatch.setattr(hl_fills, "_bucket", main)
    monkeypatch.setattr(hl_fills, "_backfill_bucket", back)
    fake.regular[A] = [hf(NOW - 1000 + i, "B", 1, 1, i) for i in range(45)]
    run(hl_fills._post(None, {"type": "userFillsByTime", "user": A, "startTime": 0}, backfill=True))
    assert main.tokens == pytest.approx(300 - 22, abs=0.5) and back.tokens == pytest.approx(240 - 22, abs=0.5)
    run(hl_fills._post(None, {"type": "userFillsByTime", "user": A, "startTime": 0}, backfill=False))
    assert main.tokens == pytest.approx(300 - 44, abs=0.5) and back.tokens == pytest.approx(240 - 22, abs=0.5)
    assert hl_fills.status()["weight_per_min_5m"] == pytest.approx(44 / 5)


def test_untracked_wallets_are_read_live_shared_and_limited(fake, monkeypatch):
    fake.regular[U] = seq(NOW - 900)
    fake.regular[V] = seq(NOW - 800)

    async def views():
        return await asyncio.gather(tp.wallet_fills(U), tp.wallet_fills(U), tp.wallet_fills(U))
    got = run(views())
    assert all(g["fills"] == got[0]["fills"] for g in got)
    assert [c["type"] for c in fake.calls] == ["userFills", "userTwapSliceFills"]      # one read for three viewers
    run(tp.wallet_fills(U))                                    # cached for the next viewers
    assert len(fake.calls) == 2 and hl_fills.live_limiter.used() == 1
    run(tp.wallet_fills(V))                                    # second live read this minute (limit 2)
    other = "0x" + "9" * 40
    with pytest.raises(hl_fills.Busy) as e:
        run(tp.wallet_fills(other))
    assert e.value.retry_after >= 1
    # A tracked wallet with its backfill done: from the store, no request, no limit.
    fake.regular[A] = seq(NOW - 700)
    run(hl_fills.sync(None, A, "backfill"))
    fake.calls.clear()
    assert len(run(tp.wallet_fills(A))["fills"]) == 7 and fake.calls == []


def test_busy_answer_from_the_endpoints(fake, monkeypatch):
    from fastapi.testclient import TestClient
    import main
    monkeypatch.setattr(hl_fills, "live_limiter", hl_fills.LiveLimiter(0))
    c = TestClient(main.app)
    for path in (f"/api/traders/{U}/fills", f"/api/traders/{U}/history"):
        r = c.get(path)
        assert r.status_code == 503, r.text
        assert r.status_code == 503 and r.json()["detail"] == "Busy, try again shortly"
        assert int(r.headers["Retry-After"]) >= 1


def test_job_order_changes_before_sweep_before_backfill(fake, monkeypatch):
    B, C = "0x" + "b" * 40, "0x" + "c" * 40
    roster = [A, B, C]
    for a in roster:
        fake.regular[a] = seq(NOW - 600)
    assert hl_fills.next_job(NOW, roster) == (A, "backfill")
    hl_fills.prioritise([C])
    assert hl_fills.next_job(NOW, roster) == (C, "backfill")
    for a in (A, C):
        run(hl_fills.sync(None, a, "backfill"))
    hl_fills._priority.clear()
    assert hl_fills.next_job(time.time(), roster) == (B, "backfill")
    later = time.time() + 120
    hl_fills._dirty[A] = later - 1
    assert hl_fills.next_job(later, roster) == (A, "change")
    hl_fills._dirty.clear()
    swept = time.time() + hl_fills.SWEEP_S * 1.2
    assert hl_fills.next_job(swept, roster)[1] == "sweep"
    monkeypatch.setattr(hl_fills, "_quiet", lambda now: True)
    assert hl_fills.next_job(time.time() + 120, roster) is None       # backfill waits out the quiet window
    # A failed read is retried later, not at once.
    hl_fills._retry_at[B] = (time.time() + 600, 1)
    monkeypatch.setattr(hl_fills, "_quiet", lambda now: False)
    assert hl_fills.next_job(time.time() + 120, roster) is None


def test_position_change_asks_for_new_fills(fake):
    prev = PositionSnapshot(NOW - 600, [], 1e6)
    snap = PositionSnapshot(NOW, [WalletPosition(coin="ETH", side="LONG", size=10, size_usd=30_000, entry_px=3000,
                                                 unrealized_pnl=0, leverage=3)], 1e6)
    hl._note_change(A, prev, snap)
    assert A in hl_fills._dirty
    hl_fills._dirty.clear()
    hl._note_change(A, snap, PositionSnapshot(NOW + 600, snap.positions, 1e6))    # unchanged
    assert hl_fills._dirty == {}


def test_retention_cap_and_off_roster(fake, monkeypatch):
    old = hf(NOW - (hl_fills.RETENTION_DAYS + 5) * 86400, "B", 1, 1, 0)
    st = hl_fills.store()
    fake.regular[A] = seq(NOW - 900)
    run(hl_fills.sync(None, A, "backfill"))
    wid = hl_fills._meta[A]["id"]
    st.insert(wid, [hl_fills.row_of(old, False)])
    out = hl_fills.maintain([A], NOW)
    assert out["pruned"] == 1 and st.count(wid) == 7
    assert hl_fills._meta[A]["covered_from"] >= NOW - hl_fills.RETENTION_DAYS * 86400 - 5
    monkeypatch.setattr(hl_fills, "MAX_FILLS_PER_WALLET", 3)
    fake.regular[A].append(hf(NOW - 5, "B", 1, 1, 0, coin="SOL"))
    run(hl_fills.sync(None, A, "change"))
    assert st.count(wid) == 3 and hl_fills._meta[A]["covered_from"] > NOW - 900
    # Off the roster: kept for a while, then dropped.
    hl_fills.maintain(["0x" + "1" * 40], NOW)
    assert A in hl_fills._meta
    hl_fills.maintain(["0x" + "1" * 40], NOW + (hl_fills.OFF_ROSTER_DAYS + 1) * 86400)
    assert A not in hl_fills._meta and st.count(wid) == 0


def test_status_shows_backfill_progress(fake):
    fake.regular[A] = seq(NOW - 900)
    run(hl_fills.sync(None, A, "backfill"))
    st = hl.get_status()["fills_store"]
    assert st["wallets"] == 1 and st["backfilled"] == 1 and st["backfill_pending"] == 0 and st["fills"] == 7
    assert st["weight_budget_per_min"] == hl_fills.WEIGHT_PER_MIN and st["db_mb"] is not None
    assert "weight_per_min_5m" in hl.get_status()["api_calls"]


def test_profile_behind_live_positions(fake):
    cl = tp.classify_fills([hf(0, "B", 100, 10, 0)])
    state = lambda szi: {"assetPositions": [{"position": {"coin": "ETH", "szi": str(szi)}}]}
    assert not tp._behind(state(10), cl)
    assert tp._behind(state(12), cl) and tp._behind({"assetPositions": []}, cl)
    assert tp._behind(state(10), []) and not tp._behind({"assetPositions": []}, [])


# --- Regressions from the first production deploy (30 September 2026) --------------------------

def test_status_right_after_a_start_reads_the_database(fake, tmp_path, monkeypatch):
    """After a restart the status showed 0 wallets, 0 fills and db_mb null until the reader had
    opened the store, although the file held 136 wallets."""
    fake.regular[A] = seq(NOW - 900)
    run(hl_fills.sync(None, A, "backfill"))
    path = hl_fills.store().path
    hl_fills.use_store(None)                      # a new process: nothing loaded yet
    monkeypatch.setenv("FILLS_DB_PATH", path)
    st = hl_fills.status()
    assert st["backfilled"] == 1 and st["stored_wallets"] == 1 and st["fills"] == 7
    assert st["db_mb"] is not None and st["db_path"] == path


def test_backfill_cut_short_resumes_from_the_last_page(fake, monkeypatch):
    """A 429 (or a restart) in the middle of a wallet's backfill threw away its progress: the
    cursor was saved only at the end, so every retry read the wallet from 180 days ago again."""
    monkeypatch.setattr(hl_fills, "PAGE", 3)
    fake.regular[A] = seq(NOW - 7200)[:7]         # 7 perp fills: pages of 3, each starting at the last one read
    fake.fail_at["userFillsByTime"] = 3           # the third page is refused
    run(hl_fills._run_one(None, A, "backfill"))
    st = hl_fills.status()
    assert st["last_attempt"]["outcome"] == "error" and st["last_attempt"]["pages"] == 2
    assert st["last_exception"]["address"] == A and "RateLimited" in st["last_exception"]["error"]
    assert st["current"] is None
    saved = hl_fills.store().wallets()[A]
    assert saved["cursor_ms"] == int((NOW - 7200 + 240) * 1000)     # the last fill of the second page
    assert saved["backfilled_at"] is None and hl_fills.store().count(saved["id"]) == 5
    # The retry starts at the saved cursor, not at the start of the window.
    fake.calls.clear()
    hl_fills._retry_at.clear()
    run(hl_fills._run_one(None, A, "backfill"))
    first = next(c for c in fake.calls if c["type"] == "userFillsByTime")
    assert first["startTime"] == saved["cursor_ms"] - hl_fills.OVERLAP_MS
    w = hl_fills._meta[A]
    assert w["backfilled_at"] and w["n"] == 7 and hl_fills.status()["last_attempt"]["outcome"] == "ok"
    assert w["covered_from"] == pytest.approx(NOW - hl_fills.RETENTION_DAYS * 86400, abs=5)


def test_backfill_waits_out_the_startup_burst(fake, monkeypatch):
    """At start the scanner loads every market's candles (2,700+ weight a minute seen in
    production, over Hyperliquid's 1,200): the backfill waits, reads after a change do not."""
    roster = [A]
    now = time.time()
    monkeypatch.setattr(hl_fills, "_started_at", now - 60)
    assert hl_fills.next_job(now, roster) is None
    monkeypatch.setattr(hl_fills, "_started_at", now - hl_fills.BACKFILL_AFTER_START_S - 1)
    assert hl_fills.next_job(now, roster) == (A, "backfill")
    fake.regular[A] = seq(NOW - 900)
    run(hl_fills.sync(None, A, "backfill"))
    monkeypatch.setattr(hl_fills, "_started_at", time.time())
    hl_fills._dirty[A] = time.time() + 100
    assert hl_fills.next_job(time.time() + 120, roster) == (A, "change")


def test_a_view_does_not_wait_behind_a_read_in_progress(fake, monkeypatch):
    """A profile waited 4 seconds for its refresh while the reader was busy with a long backfill."""
    fake.regular[A] = seq(NOW - 900)
    run(hl_fills.sync(None, A, "backfill"))
    hl_fills._meta[A]["synced_at"] = time.time() - hl_fills.VIEW_REFRESH_S - 1

    async def view(busy):
        monkeypatch.setattr(hl_fills, "_task", asyncio.get_running_loop().create_task(asyncio.sleep(10)))
        monkeypatch.setattr(hl_fills, "_current", {"address": "0x" + "b" * 40} if busy else None)
        t0 = time.monotonic()
        await hl_fills.refresh(A, wait=0.5)
        hl_fills._task.cancel()
        return time.monotonic() - t0
    assert run(view(busy=True)) < 0.2 and A in hl_fills._view_requests
    assert run(view(busy=False)) >= 0.45           # a free reader: the view waits for it
