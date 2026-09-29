"""Telegram: the alert gate (dedupe, daily cap, quiet hours, categories), the daily brief
and its picture, the brief's schedule across DST, and that off categories send nothing.
No real messages: delivery is replaced by a recorder."""
import asyncio
import io
from datetime import datetime, timezone

import pytest

import followed_traders as ft
import tg_alerts as ta
import tg_brief as tb


def utc(*a) -> float:
    return datetime(*a, tzinfo=timezone.utc).timestamp()


# 2026-09-30 is summer time in Rome (UTC+2): 10:00 UTC is 12:00 in Rome, 01:00 UTC is 03:00.
NOON = utc(2026, 9, 30, 10, 0)
NIGHT = utc(2026, 9, 30, 1, 0)


@pytest.fixture
def sent(tmp_path, monkeypatch):
    """A blank alert record in a temp file, Rome time, and a recorder instead of Telegram."""
    monkeypatch.setattr(ta, "PATH", tmp_path / "telegram_alerts.json")
    monkeypatch.setattr(ta, "TZ_NAME", "Europe/Rome")
    monkeypatch.setattr(ta, "BRIEF_TIME", "08:00")
    ta.reset()
    s = ta.settings()
    s.update({"quiet": ["23:00", "07:30"], "cap": 6, "paused_until": 0.0})
    out = []

    async def deliver(chats, text):
        out.append((list(chats), text))
        return len(list(chats))
    monkeypatch.setattr(ta, "_deliver", deliver)
    monkeypatch.setattr(ta, "default_chats", lambda: [111])
    return out


def run(coro):
    return asyncio.run(coro)


# ------------------------------------------------------------------ dedupe
def test_same_coin_and_kind_once_a_day(sent):
    assert run(ta.submit("watched", "early:SUI", "<b>SUI</b> · entered Early setups", now=NOON)) == "sent"
    assert run(ta.submit("watched", "early:SUI", "again", now=NOON + 3600)) == "dup"
    assert run(ta.submit("watched", "exit:SUI", "<b>SUI</b> · exit signal Trim", now=NOON + 3600)) == "sent"
    assert run(ta.submit("watched", "early:SUI", "a day later", now=NOON + 24 * 3600 + 1)) == "sent"
    assert [t for _, t in sent] == ["<b>SUI</b> · entered Early setups", "<b>SUI</b> · exit signal Trim", "a day later"]


def test_dedupe_survives_a_restart(sent):
    run(ta.submit("positions", "exit:ETH", "x", now=NOON))
    ta._loaded = False                         # read the file again, as after a redeploy
    assert run(ta.submit("positions", "exit:ETH", "x", now=NOON + 60)) == "dup"


# ------------------------------------------------------------------ cap and the brief
def test_daily_cap_holds_the_rest_for_the_brief(sent):
    ta.settings()["cap"] = 2
    got = [run(ta.submit("followed", f"k{i}", f"<b>C{i}</b> · opened", now=NOON + i)) for i in range(4)]
    assert got == ["sent", "sent", "held", "held"] and len(sent) == 2
    assert [h["line"] for h in ta.state()["held"]] == ["<b>C2</b> · opened", "<b>C3</b> · opened"]
    # the count starts again at the next brief time (08:00 Rome = 06:00 UTC the next day)
    assert run(ta.submit("followed", "k9", "next day", now=utc(2026, 10, 1, 6, 30))) == "sent"


def test_held_alerts_go_into_the_brief_and_are_cleared(sent, monkeypatch):
    ta.settings()["cap"] = 0
    run(ta.submit("watched", "exit:LINK", "<b>LINK</b> · exit signal Trim", "<b>LINK</b> exit signal Trim", now=NOON))
    monkeypatch.setattr(tb, "gather", lambda now: _ctx_async(now))
    monkeypatch.setattr(tb, "render_image", lambda smap, now: None)
    captions = []

    async def send(cid, caption, png):
        captions.append(caption)
        return True
    monkeypatch.setattr(tb, "_send", send)
    assert run(tb.send_brief(chats=[111], now=utc(2026, 10, 1, 6, 0), scheduled=True)) == 1
    assert "Held: <b>LINK</b> exit signal Trim" in captions[0]
    assert ta.state()["held"] == [] and ta.state()["last_brief"] == "2026-10-01"
    assert ta.state()["brief_watch"] == {"SUI": {"zone": "watch"}}


async def _ctx_async(now):
    return {"now": now, "consensus": "MIXED", "watch_now": {"SUI": {"zone": "watch"}}}


# ------------------------------------------------------------------ quiet hours
def test_quiet_hours_wrap_midnight(sent):
    q = ["23:00", "07:30"]
    assert ta.in_quiet(NIGHT, q)                                   # 03:00 Rome
    assert ta.in_quiet(utc(2026, 9, 30, 21, 0), q)                 # 23:00 Rome
    assert not ta.in_quiet(utc(2026, 9, 30, 5, 30), q)             # 07:30 Rome: quiet has ended
    assert not ta.in_quiet(NOON, q) and not ta.in_quiet(NIGHT, None)
    assert ta.in_quiet(NOON, ["11:00", "13:00"])


def test_quiet_hours_hold_but_liquidation_goes_through(sent):
    assert run(ta.submit("followed", "a", "trader opened", now=NIGHT)) == "held"
    assert run(ta.submit("positions", "liq:ETH", "<b>ETH</b> · liquidation 4.0% away", urgent=True, now=NIGHT)) == "sent"
    assert [t for _, t in sent] == ["<b>ETH</b> · liquidation 4.0% away"]


def test_pause_holds_everything(sent):
    ta.pause(24, now=NOON)
    assert run(ta.submit("positions", "liq:ETH", "x", urgent=True, now=NOON + 60)) == "held"
    ta.resume()
    assert run(ta.submit("positions", "liq:BTC", "y", urgent=True, now=NOON + 60)) == "sent"


# ------------------------------------------------------------------ categories and /alerts
def test_off_categories_send_nothing(sent):
    for cat in ("signals", "whales", "bridge", "anomalies_all", "position_notes", "opportunities", "overview",
                "market_shift", "watched_more"):
        assert not ta.enabled(cat)
        assert run(ta.submit(cat, "k", "text", now=NOON)) == "off"
    ta.set_on("followed", False)
    assert run(ta.submit("followed", "k", "text", now=NOON)) == "off"
    assert sent == [] and ta.state()["held"] == []


def test_alerts_buttons_toggle_and_pause(sent):
    text, rows = ta.alerts_view("main", now=NOON)
    labels = [b[0] for r in rows for b in r]
    assert "My positions: on" in labels and "Quiet hours: 23:00-07:30" in labels and "Pause 24h" in labels
    assert ta.apply_callback("al:t:positions") == "main" and not ta.enabled("positions")
    assert ta.apply_callback("al:t:signals") == "more" and ta.enabled("signals")
    assert ta.apply_callback("al:q") == "main" and ta.settings()["quiet"] == ["22:00", "08:00"]
    ta.apply_callback("al:p", now=NOON)
    assert ta.paused(NOON + 3600) and not ta.paused(NOON + 25 * 3600)
    assert ta.apply_callback("al:b") == "brief"
    more = [b[0] for r in ta.alerts_view("more", now=NOON)[1] for b in r]
    assert "4H signal changes, all coins: on" in more and "Whale follows: off" in more
    for _ in range(3):
        ta.cycle_quiet()
    assert ta.settings()["quiet"] == ["23:00", "07:30"]


def test_settings_persist(sent):
    ta.set_on("followed", False)
    ta.set_quiet(["22:30", "07:00"])
    ta._loaded = False
    assert not ta.enabled("followed") and ta.enabled("positions") and ta.settings()["quiet"] == ["22:30", "07:00"]


def test_trade_and_anomaly_pushes_respect_categories(sent, monkeypatch):
    import telegram_bot
    ta.settings()["quiet"] = None                                  # these use the real clock
    bot = telegram_bot.TelegramBot()
    bot.app, bot._running = object(), True
    t = {"symbol": "TAO/USDT", "signal": "STRONG_LONG", "transition_type": "ENTRY", "conditions_met": 11}
    assert run(bot.push_trade_alerts([t])) == 0                   # "signals" is off

    class A:
        symbol, anomaly_type, direction, context = "SAGA/USDT", "EXTREME_FUNDING", "SHORT", "-47% annualized"
        dedup_key = "SAGA/USDT:EXTREME_FUNDING:SHORT"
    monkeypatch.setattr(telegram_bot, "_my_coins", lambda: set())
    assert run(bot.push_anomaly_alerts([A()])) == 0               # not watched or held: off
    monkeypatch.setattr(telegram_bot, "_my_coins", lambda: {"SAGA"})
    assert run(bot.push_anomaly_alerts([A()])) == 1
    assert sent[-1][1] == "<b>SAGA</b> · extreme funding, short side\n-47% annualized"
    assert run(bot.push_anomaly_alerts([A()])) == 0               # once a day


def test_bridge_is_off_by_default(sent):
    import hl_bridge_alerts as hb
    div = {"label": "EXHAUSTION", "confirmed": True, "score_6h": 2.5, "btc_return_6h_z": 2.1, "net_flow_6h_z": -1.8}
    assert run(hb._send_telegram(hb._format_alert(div))) == 0 and sent == []


# ------------------------------------------------------------------ followed traders
def test_followed_trader_opens_closes_and_flips(sent, tmp_path, monkeypatch):
    monkeypatch.setattr(ft, "PATH", tmp_path / "f.json")
    monkeypatch.setattr(ft, "_items", {})
    monkeypatch.setattr(ft, "_loaded", True)
    ta.settings()["quiet"] = None                                  # record() uses the real clock
    ch = [{"kind": "open", "coin": "SUI", "side": "long", "usd": 120_000, "px": 1.23},
          {"kind": "close", "coin": "ETH", "side": "long", "usd": 60_000, "px": 2400},
          {"kind": "open", "coin": "ETH", "side": "short", "usd": 50_000, "px": 2400},
          {"kind": "open", "coin": "DOGE", "side": "long", "usd": 12_000, "px": 0.2},
          {"kind": "add", "coin": "HYPE", "side": "long", "usd": 900_000, "delta_usd": 300_000, "px": 40}]
    got = sorted((c["kind"], c["coin"]) for c in ft.alerts(ch, 25_000))
    assert got == [("flip", "ETH"), ("open", "SUI")]

    async def go():
        ft.record("0xabcdef0123456789abcdef0123456789abcdef01", "profitable", NOON, ch,
                  [{"coin": "SUI", "side": "long", "size_usd": 120_000}])
        for _ in range(5):
            await asyncio.sleep(0)
    run(go())
    texts = sorted(t for _, t in sent)
    assert len(texts) == 2 and all("0x" not in t for t in texts)          # codenames, not addresses
    assert any("opened long <b>SUI</b> $120K at 1.23" in t for t in texts)
    assert any("flipped to short <b>ETH</b> $50K" in t for t in texts)


# ------------------------------------------------------------------ watched coins
def test_watch_events_and_entry_zone():
    base = {"zone": "outside", "signal": "WAIT", "regime": "ACCUM", "crowd": "quiet", "entry": None}
    assert ta.watch_events(None, base) == []
    cur = dict(base, zone="watch", entry=True)
    kinds = [(c, k) for c, k, _ in ta.watch_events(base, cur)]
    assert kinds == [("watched", "early"), ("watched", "entry")]
    ex = [(c, k, w) for c, k, w in ta.watch_events(cur, dict(cur, zone="late", signal="TRIM", regime="MARKUP"))]
    assert ("watched", "exit", "exit signal Trim") in ex and ("watched_more", "left", "left Early setups") in ex
    assert ("watched_more", "uptrend", "Uptrend confirmed") in ex
    assert ta.entry_in({"price": 5}) is None
    assert ta.entry_in({"price": 5, "entry": {"lo": 4, "hi": 6}}) is True
    assert ta.entry_in({"price": 7, "entry": [4, 6]}) is False
    assert ta.entry_in({"entry": {"state": "inside"}}) is True and ta.entry_in({"entry": "odd"}) is None


def test_check_watched_sends_once(sent, monkeypatch):
    import setup_map
    monkeypatch.setattr(setup_map, "watched", lambda: {"SUI": {"tf": "1d"}})
    item = {"coin": "SUI", "zone": "outside", "signal": "WAIT", "regime": "ACCUM", "crowd": "quiet", "zscore": 0.3,
            "traders": {"pl": 2, "ps": 0}}
    m = lambda **kw: {"1d": {"coins": [dict(item, **kw)]}}
    assert run(ta.check_watched(m(), now=NOON)) == []                         # first reading
    assert run(ta.check_watched(m(zone="watch"), now=NOON + 300)) == ["sent"]
    run(ta.check_watched(m(), now=NOON + 600))                                # left: watched_more, off
    assert run(ta.check_watched(m(zone="watch"), now=NOON + 900)) == ["dup"]  # back in: once a day
    assert len(sent) == 1 and sent[0][1].startswith("<b>SUI</b> · entered Early setups\nStretch 0.3")


# ------------------------------------------------------------------ the brief
def coin(name, zone="watch", priority=50, pl=3, ps=0, usd=500_000, **kw):
    return {"coin": name, "symbol": f"{name}/USDT", "zone": zone, "priority": priority, "stage": kw.pop("stage", "running"),
            "crowd": kw.pop("crowd", "holding"), "traders": {"pl": pl, "ps": ps}, "zscore": kw.pop("z", 0.5),
            "money": {"long_usd": usd, "short_usd": 0, "gross_usd": usd, "net_long_share": 1.0}, **kw}


SMAP = {"box": {"z": [-0.5, 1.5], "n": [1, 8]}, "coins": [
    coin("SUI", priority=50, pl=5, usd=2_100_000, crowd="early", band={"state": "above", "d": 0.04},
         trail={"z": [-1.0, 0.2, 0.4], "n": [0, 3, 5]}),
    coin("ENA", priority=55, usd=640_000, band={"state": "inside", "d": -0.01}),
    coin("TAO", priority=40, pl=2, usd=310_000, stage="fresh", price=5.0, entry={"lo": 4.8, "hi": 5.2},
         band={"state": "above", "d": 0.2}),
    coin("XYZ", priority=20, crowd="against"),
    coin("BTC", zone="crowded", priority=90, pl=92, usd=160_000_000, z=1.4),
]}


def brief_ctx(**kw):
    return {"now": utc(2026, 9, 30, 6, 0), "consensus": "RISK-ON", "uptrend": 0.848,
            "cycle": {"type": "on", "day": 40}, "fear_greed": (73, "Greed"), "smap": SMAP,
            "positions": [{"coin": "ETH", "symbol": "ETH/USDT", "side": "LONG"},
                          {"coin": "SUI", "symbol": "SUI/USDT", "side": "LONG"}],
            "results": {"ETH/USDT": {"signal": "TRIM"}, "SUI/USDT": {"signal": "LIGHT_LONG"}},
            "watched": 2, "changes": ["<b>SUI</b> entered Early setups"],
            "held": [{"line": "<b>LINK</b> exit signal Trim"}], "app_url": "https://app.example", **kw}


def test_brief_lines(sent):
    lines = tb.compose(brief_ctx())
    assert lines == [
        "Risk-on · 85% in Uptrend · risk-on run day 40",
        "Fear &amp; Greed 73 · Greed",
        "",
        "<b>Early setups</b>",
        "<b>SUI</b> · new · 5 traders · $2.1M · 4% above band",
        "<b>ENA</b> · 3 traders · $640K · in band",
        "<b>TAO</b> · 2 traders · $310K · in entry zone",
        "",
        "Positions: 2 open · 1 agree · 1 against: <b>ETH</b>",
        "Watched: <b>SUI</b> entered Early setups",
        "Held: <b>LINK</b> exit signal Trim",
        "",
        '<a href="https://app.example/radar?tf=1d">Open Radar</a>',
        "<i>Reflex · 08:00</i>",
    ]
    assert len([ln for ln in lines if ln]) <= 12


def test_brief_without_wallet_or_watch_list(sent):
    lines = tb.compose(brief_ctx(positions=None, watched=0, held=[], app_url="", smap={"coins": []}))
    assert "Early setups: none" in lines
    assert not any(ln.startswith(("Positions", "Watched", "Held", "<a ")) for ln in lines)
    assert lines[-1] == "<i>Reflex · 08:00</i>"


def test_brief_words():
    assert tb.stance("LONG", "TRIM") == "against" and tb.stance("SHORT", "TRIM") == "agree"
    assert tb.stance("SHORT", "STRONG_LONG") == "against" and tb.stance("LONG", "WAIT") == "none"
    assert tb.band_note({"band": {"state": "closed_under"}}) == "closed under band"
    held = [{"line": f"<b>C{i}</b>"} for i in range(5)]
    assert tb.compose(brief_ctx(held=held))[10] == "Held: <b>C0</b> · <b>C1</b> · +3 more"


def test_brief_image_smoke():
    pytest.importorskip("PIL")
    from PIL import Image
    import radar_image
    png = radar_image.render(SMAP, ["SUI", "ENA", "TAO"], "Radar 1D")
    assert png and png[:8] == b"\x89PNG\r\n\x1a\n"
    assert Image.open(io.BytesIO(png)).size == (800, 500)
    assert radar_image.render({"coins": []}) is None


# ------------------------------------------------------------------ the schedule across DST
def test_next_brief_across_dst(sent):
    # Summer time ends on Sunday 25 Oct 2026: 08:00 Rome is 06:00 UTC on the 24th, 07:00 UTC on the 25th.
    assert ta.next_brief_at(utc(2026, 10, 24, 10, 0)).timestamp() == utc(2026, 10, 25, 7, 0)
    assert ta.next_brief_at(utc(2026, 10, 24, 5, 59)).timestamp() == utc(2026, 10, 24, 6, 0)
    # Summer time starts on Sunday 29 Mar 2026: 07:00 UTC on the 28th, 06:00 UTC on the 29th.
    assert ta.next_brief_at(utc(2026, 3, 28, 7, 0)).timestamp() == utc(2026, 3, 29, 6, 0)
    assert ta.next_brief_at(utc(2026, 3, 28, 6, 0)).timestamp() == utc(2026, 3, 28, 7, 0)
    assert ta.period_start(utc(2026, 10, 25, 6, 30)) == utc(2026, 10, 24, 6, 0)


def test_brief_due_once_within_grace(sent):
    at = utc(2026, 9, 30, 6, 0)                                    # 08:00 Rome
    assert not tb.brief_due(at - 60, "")                            # 07:59: not yet (yesterday's slot is past its grace)
    assert tb.brief_due(at + 30, "2026-09-29")
    assert not tb.brief_due(at + 30, "2026-09-30")                  # already sent
    assert tb.brief_due(at + 2 * 3600, "2026-09-29")                 # a restart at 10:00 still sends it
    assert not tb.brief_due(at + 4 * 3600, "2026-09-29")             # too late: wait for tomorrow


# ------------------------------------------------------------------ style
def test_calm_turns_old_alerts_into_the_house_style():
    old = "⚠️ HEAT RISING — ETH\nHeat: 72/100 <high>"
    assert ta.calm(old) == "<b>ETH</b> · Heat rising\nHeat: 72/100 &lt;high&gt;"
    assert ta.calm("\U0001f4ca OI WARNING — SOL").startswith("<b>SOL</b> · OI warning")
    assert ta.strip_emoji("\U0001f7e2 BTC — LIGHT_LONG") == "BTC — LIGHT_LONG"


# ------------------------------------------------------------------ open positions
def test_position_alerts_exit_band_and_liquidation(sent, monkeypatch):
    from position_monitor import PositionMonitor, Watcher
    pm = PositionMonitor.__new__(PositionMonitor)
    pm._last_exit_signal, pm._band_cache = {}, {}
    band = {"state": "inside"}
    monkeypatch.setattr(pm, "_band", lambda sym, price, now: band, raising=False)
    w = Watcher(chat_id=5, address="0x" + "ab" * 20)
    pos = [{"symbol": "ETH/USDT", "coin": "ETH", "side": "LONG", "size_usd": 12_400, "leverage": 3,
            "unrealized_pnl": 230, "liq_px": 1500}]
    px = {"ETH/USDT": {"price": 2410}}
    ta.settings()["quiet"] = None                                  # the real clock
    run(pm._position_alerts(w, pos, px, {"ETH/USDT": {"signal": "LIGHT_LONG"}}))
    assert sent == []                                              # first reading, far from liquidation
    run(pm._position_alerts(w, pos, px, {"ETH/USDT": {"signal": "TRIM"}}))
    band.update(state="closed_under", week=1790553600, week_close=2400, lo=2480, hi=2600)
    run(pm._position_alerts(w, pos, px, {"ETH/USDT": {"signal": "TRIM"}}))
    run(pm._position_alerts(w, [dict(pos[0], liq_px=2300)], px, {"ETH/USDT": {"signal": "TRIM"}}))
    assert [c for c, _ in sent] == [[5], [5], [5]]
    assert sent[0][1] == "<b>ETH</b> · exit signal Trim (1D)\nYou hold long $12K · 3x · PnL +$230"
    assert sent[1][1].startswith("<b>ETH</b> · weekly close under the support band\nClose 2,400 · band 2,480-2,600")
    assert sent[2][1].startswith("<b>ETH</b> · liquidation 4.6% away\nPrice 2,410 · liquidation 2,300")
    ta.set_on("positions", False)
    run(pm._position_alerts(w, [dict(pos[0], liq_px=2380)], px, {"ETH/USDT": {"signal": "LIGHT_LONG"}}))
    assert len(sent) == 3
