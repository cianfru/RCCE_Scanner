"""The Portfolio page's signal and regime changes per coin (portfolio_context.events_body, /api/portfolio/events)."""

import sqlite3

import pytest

import portfolio_context as pc

NOW = 1_800_000_000.0
DAY = 86400


def _db(path, signals=(), regimes=()):
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE signal_events (id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT, timeframe TEXT, signal TEXT,
            prev_signal TEXT, regime TEXT, price REAL, timestamp INTEGER);
        CREATE INDEX idx_sig_sym_tf_ts ON signal_events(symbol, timeframe, timestamp);
        CREATE TABLE regime_events (id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT, timeframe TEXT, regime TEXT,
            prev_regime TEXT, price REAL, timestamp INTEGER);
        CREATE INDEX idx_regime_sym_tf_ts ON regime_events(symbol, timeframe, timestamp);
    """)
    con.executemany("INSERT INTO signal_events (symbol, timeframe, signal, prev_signal, regime, price, timestamp) "
                    "VALUES (?,?,?,?,?,?,?)", signals)
    con.executemany("INSERT INTO regime_events (symbol, timeframe, regime, prev_regime, price, timestamp) "
                    "VALUES (?,?,?,?,?,?)", regimes)
    con.commit()
    con.close()
    return str(path)


def test_window_is_fixed_for_the_day():
    ws = pc.window_start(NOW)
    assert ws % DAY == 0 and NOW - ws >= 30 * DAY and NOW - ws < 31 * DAY
    assert pc.window_start(NOW + 3600) == ws or (int(NOW + 3600) // DAY != int(NOW) // DAY)


def test_events_since_the_window_with_the_reading_at_its_start(tmp_path):
    ws = pc.window_start(NOW)
    db = _db(tmp_path / "s.db", signals=[
        ("HYPE/USDT", "4h", "LIGHT_LONG", "WAIT", "REACC", 60.0, ws - 5 * DAY),       # before: the start reading
        ("HYPE/USDT", "4h", "STRONG_LONG", "LIGHT_LONG", "MARKUP", 79.1, ws + 2 * DAY),
        ("HYPE/USDT", "1d", "WAIT", None, "MARKUP", 55.0, ws - DAY),
        ("HYPE/USDC", "4h", "WAIT", "LIGHT_LONG", "FLAT", 79.0, ws + DAY),            # spot: not this coin
        ("BTC/USDT", "4h", "TRIM", "LIGHT_LONG", "MARKUP", 90000, ws + DAY),
    ], regimes=[
        ("HYPE/USDT", "1d", "MARKUP", "REACC", 80.2, ws + 3 * DAY),
        ("HYPE/USDT", "4h", "REACC", "MARKUP", 58.0, ws - 2 * DAY),
    ])
    body = pc.events_body(["HYPE", "XMR", "xyz:MSTR"], db, now=NOW)
    assert body["window_start"] == ws
    h = body["coins"]["HYPE"]
    assert h["at_start"] == {"h4": {"signal": "LIGHT_LONG", "regime": "REACC"}, "d1": {"signal": "WAIT", "regime": None}}
    assert h["events"] == [
        {"t": ws + 2 * DAY, "tf": "4h", "kind": "signal", "from": "LIGHT_LONG", "to": "STRONG_LONG", "px": 79.1},
        {"t": ws + 3 * DAY, "tf": "1d", "kind": "regime", "from": "REACC", "to": "MARKUP", "px": 80.2},
    ]
    assert h["truncated"] is False
    assert body["coins"]["XMR"] == {"at_start": {"h4": {"signal": None, "regime": None}, "d1": {"signal": None, "regime": None}},
                                    "events": [], "truncated": False}
    # TradFi is read from the TradFi scan's log ("MSTR/USD", tradfi_4h/tradfi_1d): nothing logged here.
    assert body["coins"]["xyz:MSTR"] == {"at_start": {"h4": {"signal": None, "regime": None}, "d1": {"signal": None, "regime": None}},
                                         "events": [], "truncated": False}
    assert body["last_id"] == 2                       # the newest id among HYPE's rows (signal 2, regime 1)


def test_tradfi_rows_read_the_tradfi_scan_log(tmp_path):
    # Data review: the TradFi scan logs its transitions as "NAME/USD" with timeframes tradfi_4h and
    # tradfi_1d; the page's WHILE HELD strip and the 24H baseline read them as 4h and 1d.
    ws = pc.window_start(NOW)
    db = _db(tmp_path / "s.db", signals=[
        ("SILVER/USD", "tradfi_4h", "WAIT", "LIGHT_LONG", "FLAT", 48.0, ws - DAY),
        ("SILVER/USD", "tradfi_1d", "RISK_OFF", "WAIT", "FLAT", 47.1, ws + 4 * DAY),
        ("SILVER/USD", "tradfi_4h", "LIGHT_LONG", "WAIT", "MARKUP", 49.2, ws + 5 * DAY),
        ("SILVER/USDT", "4h", "TRIM", "LIGHT_LONG", "MARKUP", 1.0, ws + DAY),            # not this market
    ], regimes=[("SILVER/USD", "tradfi_4h", "MARKUP", "FLAT", 49.0, ws + 5 * DAY)])
    body = pc.events_body(["xyz:SILVER", "xyz:MSTR", "para:PAPER"], db, now=NOW)
    s = body["coins"]["xyz:SILVER"]
    assert s["at_start"]["h4"] == {"signal": "WAIT", "regime": None}
    assert [(e["t"] - ws, e["tf"], e["kind"], e["to"]) for e in s["events"]] == [
        (4 * DAY, "1d", "signal", "RISK_OFF"), (5 * DAY, "4h", "regime", "MARKUP"), (5 * DAY, "4h", "signal", "LIGHT_LONG")]
    assert body["coins"]["xyz:MSTR"]["events"] == []
    assert body["coins"]["para:PAPER"] == {"at_start": None, "events": [], "truncated": False}
    assert body["last_id"] == 3


def test_capped_at_60_keeping_the_latest(tmp_path):
    ws = pc.window_start(NOW)
    rows = [("LINK/USDT", "4h", f"S{i}", f"S{i - 1}", "MARKUP", 10.0 + i, ws + i * 3600) for i in range(75)]
    body = pc.events_body(["LINK"], _db(tmp_path / "s.db", signals=rows), now=NOW)
    ev = body["coins"]["LINK"]
    assert len(ev["events"]) == pc.EVENTS_CAP and ev["truncated"] is True
    assert ev["events"][-1]["to"] == "S74" and ev["events"][0]["to"] == "S15"


def test_etag_is_the_newest_event_id(tmp_path):
    ws = pc.window_start(NOW)
    path = tmp_path / "s.db"
    db = _db(path, signals=[("HYPE/USDT", "4h", "TRIM", "STRONG_LONG", "MARKUP", 80.0, ws + DAY)])
    a = pc.events_body(["HYPE"], db, now=NOW)
    b = pc.events_body(["HYPE"], db, now=NOW + 120)                  # a later minute, nothing new
    assert a["as_of"] != b["as_of"] and pc.events_etag(a) == pc.events_etag(b)
    con = sqlite3.connect(path)
    con.execute("INSERT INTO signal_events (symbol, timeframe, signal, prev_signal, regime, price, timestamp) "
                "VALUES ('HYPE/USDT','4h','WAIT','TRIM','MARKUP',78.0,?)", (ws + 2 * DAY,))
    con.commit()
    con.close()
    c = pc.events_body(["HYPE"], db, now=NOW + 180)
    assert pc.events_etag(c) != pc.events_etag(a)


def test_missing_database_gives_empty_lists(tmp_path):
    body = pc.events_body(["HYPE"], str(tmp_path / "none.db"), now=NOW)
    assert body["coins"]["HYPE"]["events"] == [] and body["last_id"] == 0


def test_route_is_on_by_default_and_answers_304(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    import main
    import signal_log
    import aiohttp

    async def aboom(*a, **k):
        raise AssertionError("outbound call from the portfolio events")
    monkeypatch.setattr(aiohttp.ClientSession, "_request", aboom)
    c = TestClient(main.app)
    monkeypatch.setenv("PORTFOLIO_CONTEXT", "off")
    assert c.get("/api/portfolio/events?coins=HYPE").status_code == 404
    monkeypatch.delenv("PORTFOLIO_CONTEXT", raising=False)
    monkeypatch.setattr(main, "_PF_BODIES", pc.BodyCache())
    ws = pc.window_start(__import__("time").time())
    db = _db(tmp_path / "s.db", signals=[("HYPE/USDT", "4h", "TRIM", "STRONG_LONG", "MARKUP", 80.0, ws + DAY)])
    monkeypatch.setattr(signal_log, "_DB_PATH", db)
    monkeypatch.setattr(main, "_PF_EVENTS_MEMO", pc.Memo())
    r = c.get("/api/portfolio/events?coins=HYPE,BTC")
    assert r.status_code == 200, r.text
    assert r.json()["coins"]["HYPE"]["events"][0]["to"] == "TRIM"
    assert r.headers["cache-control"] == "max-age=60"
    r2 = c.get("/api/portfolio/events?coins=BTC,HYPE", headers={"If-None-Match": r.headers["etag"]})
    assert r2.status_code == 304
