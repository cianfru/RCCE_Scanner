import asyncio
import json
import math
from pathlib import Path

import pytest

import options_surface as osf

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "derive_surface_btc.json").read_text())
TS = FIXTURE["ts"]


@pytest.fixture(autouse=True)
def _setup(monkeypatch):
    osf._cache.clear()
    osf._locks.clear()
    monkeypatch.setenv("DERIVE_SCAN_URL", "https://derive-scan.example")
    monkeypatch.delenv("DERIVE_SCAN_UNDERLYINGS", raising=False)
    reads = []

    async def fake_read(coin):
        reads.append(coin)
        if fake_read.fail:
            raise RuntimeError("down")
        return dict(FIXTURE, ts=fake_read.ts)

    fake_read.fail = False
    fake_read.ts = TS
    monkeypatch.setattr(osf, "_read", fake_read)
    return fake_read, reads


def run(symbol, now):
    return asyncio.run(osf.surface_for(symbol, now=now))


def test_shape_from_recorded_body():
    body = osf.shape(FIXTURE)
    f = FIXTURE["features"]
    assert body["iv"]["30"] == round(f["atm_iv_30d"], 4)
    move = f["atm_iv_30d"] * math.sqrt(30 / 365)
    assert body["move_30d"] == pytest.approx(move, abs=1e-4)
    lo, hi = body["range_30d"]
    assert lo < f["index_price"] < hi
    assert len(body["curve"]) == len(FIXTURE["expiries"])
    assert all(p["days"] > 0 and p["iv"] > 0 for p in body["curve"])


def test_unrecorded_coin_or_no_url_never_reads(_setup, monkeypatch):
    _, reads = _setup
    assert run("SOL/USDT", TS + 10) == {"available": False}
    monkeypatch.delenv("DERIVE_SCAN_URL")
    assert run("BTC/USDT", TS + 10) == {"available": False}
    assert reads == []


def test_one_read_per_snapshot(_setup):
    fake, reads = _setup
    out = run("BTC/USDT", TS + 30)
    assert out["available"] and out["symbol"] == "BTC" and out["as_of"] == TS and not out["stale"]
    run("btc", TS + 300)
    run("BTC-PERP", TS + 900)                     # next snapshot not landed yet (grace)
    assert reads == ["BTC"]
    fake.ts = TS + 900
    assert run("BTC", TS + 900 + osf.GRACE_SEC)["as_of"] == TS + 900
    assert reads == ["BTC", "BTC"]


def test_failure_serves_last_good_marked_stale(_setup):
    fake, reads = _setup
    run("ETH", TS + 30)
    fake.fail = True
    late = TS + osf.STALE_SEC + 60
    out = run("ETH", late)
    assert out["available"] and out["as_of"] == TS and out["stale"]
    run("ETH", late + 10)                         # retry waits RETRY_SEC
    assert len(reads) == 2


def test_failure_with_nothing_cached(_setup):
    fake, _ = _setup
    fake.fail = True
    assert run("BTC", TS) == {"available": False}


def test_rate_limit_class():
    import ratelimit
    assert ratelimit.classify("GET", "/api/options/surface/BTC", {}) == "exchange"
