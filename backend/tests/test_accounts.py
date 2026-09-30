"""Accounts: wallet sign-in (message, expiry, domain, one-time nonce), sessions, per-account
follows and watch list with caps, the Telegram link, per-account alert fan-out with dedupe,
the tier function, the free tier's delayed Radar, and that with the flags off everything
behaves as before. No network: balances and Telegram delivery are replaced by recorders."""
import asyncio
import os
import time
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi.testclient import TestClient

import accounts
import followed_traders as ft
import radar_delay
import tg_alerts as ta
import tg_brief as tb
import tiers
import user_alerts as ua
import wallet_auth as wa

DOMAIN = "app.test"
NOON = datetime(2026, 9, 30, 10, 0, tzinfo=timezone.utc).timestamp()     # 12:00 in Rome
FLAG_VARS = ("REFLEX_ACCOUNTS", "ACCESS_TIERS", "REFLEX_OWNER_ADDRESS", "REFLEX_HOLDER_ALLOWLIST",
             "REFLEX_TOKEN_NAME", "REFLEX_TOKEN_INDEX", "REFLEX_TOKEN_MIN", "REFLEX_FOLLOW_CAP",
             "REFLEX_WATCH_CAP", "REFLEX_SIWE_DOMAINS", "REFLEX_ADMIN_KEY", "REFLEX_ACCESS_CODE",
             "REFLEX_FREE_RADAR_DELAY_MIN")


def run(coro):
    return asyncio.run(coro)


def addr(n: int) -> str:
    return "0x" + f"{n:040x}"


@pytest.fixture
def off(tmp_path, monkeypatch):
    """Every account flag unset (production today), storage in a temp dir."""
    for k in FLAG_VARS:
        monkeypatch.delenv(k, raising=False)
    accounts.use_path(tmp_path / "accounts.db")
    wa._cache.clear()
    tiers.reset()
    radar_delay.reset(tmp_path)
    monkeypatch.setattr(ft, "PATH", tmp_path / "f.json")
    monkeypatch.setattr(ft, "_items", {})
    monkeypatch.setattr(ft, "_loaded", True)
    monkeypatch.setattr(ta, "PATH", tmp_path / "telegram_alerts.json")
    monkeypatch.setattr(ta, "TZ_NAME", "Europe/Rome")
    monkeypatch.setattr(ta, "BRIEF_TIME", "08:00")
    ta.reset()
    return tmp_path


@pytest.fixture
def on(off, monkeypatch):
    monkeypatch.setenv("REFLEX_ACCOUNTS", "1")
    monkeypatch.setenv("REFLEX_SIWE_DOMAINS", DOMAIN)
    return off


@pytest.fixture
def outbox(monkeypatch):
    """Telegram delivery replaced by a recorder; quiet hours off for the per-account defaults."""
    out = []

    async def deliver(chats, text):
        out.append((list(chats), text))
        return len(list(chats))
    monkeypatch.setattr(ta, "_deliver", deliver)
    monkeypatch.setenv("TELEGRAM_QUIET", "off")
    return out


def sign(acct, message: str) -> str:
    return acct.sign_message(encode_defunct(text=message)).signature.hex()


# ------------------------------------------------------------------ sign-in
def test_valid_signature_signs_in(on):
    acct = Account.create()
    msg = wa.issue(acct.address, DOMAIN, now=NOON)["message"]
    assert msg.startswith(f"{DOMAIN} wants you to sign in with your Ethereum account:\n{acct.address}\n")
    assert "Nonce: " in msg and "Expiration Time: " in msg and "URI: https://app.test" in msg
    assert wa.verify(msg, sign(acct, msg), now=NOON + 30) == acct.address.lower()


def test_expired_message_is_refused(on):
    acct = Account.create()
    msg = wa.issue(acct.address, DOMAIN, now=NOON)["message"]
    with pytest.raises(wa.AuthError) as e:
        wa.verify(msg, sign(acct, msg), now=NOON + wa.NONCE_S + 1)
    assert e.value.reason == "expired"


def test_wrong_domain_is_refused(on, monkeypatch):
    acct = Account.create()
    with pytest.raises(wa.AuthError) as e:
        wa.issue(acct.address, "evil.test", now=NOON)
    assert e.value.reason == "domain"
    # A message made for an allowed domain is refused once that domain is no longer the app's.
    msg = wa.issue(acct.address, DOMAIN, now=NOON)["message"]
    monkeypatch.setenv("REFLEX_SIWE_DOMAINS", "other.test")
    with pytest.raises(wa.AuthError) as e:
        wa.verify(msg, sign(acct, msg), now=NOON + 5)
    assert e.value.reason == "domain"
    # Rewriting the domain in the text breaks the nonce binding and the signature.
    monkeypatch.setenv("REFLEX_SIWE_DOMAINS", f"{DOMAIN},evil.test")
    forged = msg.replace(DOMAIN, "evil.test")
    with pytest.raises(wa.AuthError):
        wa.verify(forged, sign(acct, forged), now=NOON + 5)


def test_replayed_nonce_is_refused(on):
    acct = Account.create()
    msg = wa.issue(acct.address, DOMAIN, now=NOON)["message"]
    sig = sign(acct, msg)
    assert wa.verify(msg, sig, now=NOON + 1)
    with pytest.raises(wa.AuthError) as e:
        wa.verify(msg, sig, now=NOON + 2)
    assert e.value.reason == "nonce"


def test_other_signer_and_edited_text_are_refused(on):
    acct, other = Account.create(), Account.create()
    msg = wa.issue(acct.address, DOMAIN, now=NOON)["message"]
    with pytest.raises(wa.AuthError) as e:
        wa.verify(msg, sign(other, msg), now=NOON + 1)
    assert e.value.reason == "signature"
    edited = msg.replace("Sign in to Reflex.", "Sign in to Reflex!")
    with pytest.raises(wa.AuthError) as e:
        wa.verify(edited, sign(acct, edited), now=NOON + 1)
    assert e.value.reason == "format"
    # The untouched message still works: failed attempts did not use the nonce up.
    assert wa.verify(msg, sign(acct, msg), now=NOON + 1) == acct.address.lower()


# ------------------------------------------------------------------ sessions
def test_session_lifecycle(on, monkeypatch):
    token, expires = wa.start_session(addr(1), now=NOON)
    assert accounts.user_exists(addr(1))
    assert wa.session_address(token, now=NOON + 60) == addr(1)
    assert wa.session_address(token, now=expires + 1) is None
    assert wa.session_address("nope", now=NOON) is None
    assert wa.request_address({wa.HEADER: token}) == addr(1)
    monkeypatch.delenv("REFLEX_ACCOUNTS")
    assert wa.request_address({wa.HEADER: token}) is None          # flag off: no accounts
    monkeypatch.setenv("REFLEX_ACCOUNTS", "1")
    assert wa.end_session(token) and wa.session_address(token) is None


# ------------------------------------------------------------------ follows and watch list
def test_follows_have_a_cap_and_feed_the_shared_poll(on, monkeypatch):
    monkeypatch.setenv("REFLEX_FOLLOW_CAP", "3")
    ft.add(addr(900))                                          # the owner's own list
    for i in range(3):
        assert accounts.follow(addr(1), addr(100 + i)) == "added"
    assert accounts.follow(addr(1), addr(100)) == "exists"
    assert accounts.follow(addr(1), addr(200)) == "cap"
    assert accounts.follow(addr(2), addr(100), "same wallet") == "added"
    assert accounts.followed_union() == {addr(100), addr(101), addr(102)}
    assert ft.addresses() == {addr(900), addr(100), addr(101), addr(102)}      # read once each
    assert sorted(u for u, _ in accounts.followers_of(addr(100))) == [addr(1), addr(2)]
    assert accounts.unfollow(addr(1), addr(101)) and addr(101) not in accounts.followed_union()


def test_watch_list_cap(on, monkeypatch):
    monkeypatch.setenv("REFLEX_WATCH_CAP", "2")
    assert accounts.watch(addr(1), "SUI", "4h") == "added"
    assert accounts.watch(addr(1), "ETH") == "added"
    assert accounts.watch(addr(1), "BTC") == "cap"
    assert accounts.watch(addr(1), "SUI", "1d") == "exists"
    assert accounts.watch_list(addr(1))["SUI"]["tf"] == "1d"
    assert accounts.unwatch(addr(1), "SUI") and accounts.all_watch() == {addr(1): {"ETH": {"tf": "1d"}}}


# ------------------------------------------------------------------ Telegram link
def test_telegram_link_flow(on):
    code, expires = accounts.tg_code(addr(1), now=NOON)
    assert len(code) == 10 and expires == NOON + accounts.CODE_S
    assert accounts.tg_claim(code.lower(), 555, now=NOON + 60) == addr(1)
    assert accounts.tg_chat(addr(1)) == 555 and accounts.tg_user_of(555) == addr(1)
    assert accounts.tg_claim(code, 556, now=NOON + 61) is None                   # used up
    late, _ = accounts.tg_code(addr(2), now=NOON)
    assert accounts.tg_claim(late, 777, now=NOON + accounts.CODE_S + 1) is None  # expired
    # The same chat linked from another account moves there.
    again, _ = accounts.tg_code(addr(2), now=NOON)
    assert accounts.tg_claim(again, 555, now=NOON + 5) == addr(2)
    assert accounts.tg_chat(addr(1)) is None and accounts.tg_user_of(555) == addr(2)
    assert accounts.tg_unlink(chat_id=555) and accounts.tg_linked() == []


def test_bot_start_with_a_code_links_the_chat(on):
    import telegram_bot
    bot = telegram_bot.TelegramBot()
    replies = []

    class Msg:
        async def reply_text(self, text, **kw):
            replies.append(text)
    code, _ = accounts.tg_code(addr(3))
    update = SimpleNamespace(effective_chat=SimpleNamespace(id=4242), message=Msg())
    run(bot._cmd_start(update, SimpleNamespace(args=[code])))
    assert accounts.tg_chat(addr(3)) == 4242 and replies[-1].startswith("Linked to")
    run(bot._cmd_start(update, SimpleNamespace(args=[code])))
    assert "not valid" in replies[-1]
    run(bot._cmd_unlink(update, SimpleNamespace(args=[])))
    assert accounts.tg_chat(addr(3)) is None


# ------------------------------------------------------------------ per-account fan-out
CHANGES = [{"kind": "open", "coin": "SUI", "side": "long", "usd": 120_000, "px": 1.23},
           {"kind": "open", "coin": "DOGE", "side": "long", "usd": 12_000, "px": 0.2}]
HOLD = [{"coin": "SUI", "side": "long", "size_usd": 120_000}]


def _link(user, chat):
    code, _ = accounts.tg_code(user)
    accounts.tg_claim(code, chat)


def test_fan_out_once_per_follower_with_dedupe(on, outbox):
    w = addr(100)
    for u, chat in ((addr(1), 11), (addr(2), 22)):
        accounts.follow(u, w, "big fish")
        _link(u, chat)
    accounts.follow(addr(3), w)                                # no Telegram: skipped
    followers = accounts.followers_of(w)
    got = run(ua.fan_out(w, "profitable", CHANGES, HOLD, followers, now=NOON))
    assert got == {addr(1): ["sent"], addr(2): ["sent"]}       # DOGE under the size threshold
    assert sorted(c[0] for c, _ in outbox) == [11, 22]
    assert all("big fish opened long <b>SUI</b> $120K" in t for _, t in outbox)
    again = run(ua.fan_out(w, "profitable", CHANGES, HOLD, followers, now=NOON + 600))
    assert again == {addr(1): ["dup"], addr(2): ["dup"]} and len(outbox) == 2


def test_fan_out_cap_and_quiet_hours_per_account(on, outbox, monkeypatch):
    monkeypatch.setenv("TELEGRAM_DAILY_CAP", "1")
    _link(addr(1), 11)
    st = ua.state(addr(1))
    assert st["settings"]["cap"] == 1
    assert run(ua.submit(addr(1), 11, "followed", "a", "first", now=NOON)) == "sent"
    assert run(ua.submit(addr(1), 11, "followed", "b", "second", now=NOON + 60)) == "held"
    ua.set_prefs(addr(1), quiet=["11:00", "13:00"])
    monkeypatch.setenv("TELEGRAM_DAILY_CAP", "5")
    assert run(ua.submit(addr(1), 11, "followed", "c", "third", now=NOON + 120)) == "held"
    assert [h["line"] for h in ua.state(addr(1))["held"]] == ["second", "third"]
    assert len(outbox) == 1


def test_record_sends_owner_and_accounts_separately(on, outbox, monkeypatch):
    """The owner's wallets keep the owner's alerts; a wallet only accounts follow goes to them."""
    monkeypatch.setattr(ta, "default_chats", lambda: [1])
    ta.settings().update({"quiet": None, "cap": 6})
    owner_w, acct_w = addr(900), addr(100)
    ft.add(owner_w)
    accounts.follow(addr(1), acct_w)
    _link(addr(1), 11)

    async def go():
        ft.record(owner_w, "profitable", NOON, CHANGES[:1], HOLD)
        ft.record(acct_w, "profitable", NOON, CHANGES[:1], HOLD)
        for _ in range(10):
            await asyncio.sleep(0)
    run(go())
    assert sorted(c[0] for c, _ in outbox) == [1, 11]
    assert [e["address"] for e in ft.events()] == [owner_w]                    # the owner's record unchanged
    assert [e["address"] for e in accounts.events_for([acct_w])] == [acct_w]


def test_free_accounts_get_no_alerts_while_tiers_are_on(on, outbox, monkeypatch):
    monkeypatch.setenv("ACCESS_TIERS", "1")
    monkeypatch.setenv("REFLEX_HOLDER_ALLOWLIST", addr(2))
    for u, chat in ((addr(1), 11), (addr(2), 22)):
        accounts.follow(u, addr(100))
        _link(u, chat)
    got = run(ua.fan_out(addr(100), "large", CHANGES, HOLD, accounts.followers_of(addr(100)), now=NOON))
    assert got == {addr(2): ["sent"]}


def test_watched_coins_per_account(on, outbox):
    _link(addr(1), 11)
    accounts.watch(addr(1), "SUI", "1d")
    item = {"coin": "SUI", "zone": "outside", "signal": "WAIT", "regime": "ACCUM", "crowd": "quiet",
            "zscore": 0.4, "traders": {"pl": 3, "ps": 1}}
    maps = {"1d": {"coins": [item]}}
    calls = []

    async def provider(tf):
        calls.append(tf)
        return maps[tf]
    assert run(ua.check_watched(provider, now=NOON)) == {addr(1): []}            # first reading
    item["zone"] = "watch"
    assert run(ua.check_watched(provider, now=NOON + 300)) == {addr(1): ["sent"]}
    assert run(ua.check_watched(provider, now=NOON + 600)) == {addr(1): []}
    assert "entered Early setups" in outbox[0][1] and calls == ["1d"] * 3


def test_brief_per_account(on, outbox, monkeypatch):
    sent = []

    async def fake_send(chat, caption, png):
        sent.append((chat, caption))
        return True

    async def fake_gather(now=None):
        return {"now": NOON, "smap": {"coins": [{"coin": "SUI", "zone": "watch", "traders": {"pl": 4, "ps": 0}}]}}

    async def no_positions(address):
        return None
    monkeypatch.setattr(tb, "_send", fake_send)
    monkeypatch.setattr(tb, "gather", fake_gather)
    monkeypatch.setattr(tb, "render_image", lambda smap, now: None)
    monkeypatch.setattr(tb, "_positions", no_positions)
    monkeypatch.setenv("REFLEX_OWNER_ADDRESS", addr(9))
    _link(addr(1), 11)
    _link(addr(9), 99)                                       # the owner gets the owner's brief
    accounts.watch(addr(1), "SUI")
    st = ua.state(addr(1))
    st["held"] = [{"ts": NOON, "cat": "followed", "line": "held line"}]
    ua.save(addr(1), st)
    assert run(tb.send_user_briefs(now=NOON, scheduled=True)) == 1
    assert sent[0][0] == 11 and "Held: held line" in sent[0][1] and "Watched:" in sent[0][1]
    assert ua.state(addr(1))["held"] == []
    assert run(tb.send_user_briefs(now=NOON + 60, scheduled=True)) == 0            # once a day


# ------------------------------------------------------------------ tiers
def test_tier_allowlist_threshold_and_cache(on, monkeypatch):
    reads = []

    async def fetch(a):
        reads.append(a)
        return {"balances": [{"coin": "USDC", "token": 0, "total": "5000"},
                             {"coin": "RFX", "token": 321, "total": "150.5"}]}
    assert run(tiers.tier_for(addr(1), fetch=fetch)) == "free" and reads == []   # token not configured
    monkeypatch.setenv("REFLEX_HOLDER_ALLOWLIST", f"{addr(5)}, junk")
    monkeypatch.setenv("REFLEX_OWNER_ADDRESS", addr(6))
    assert run(tiers.tier_for(addr(5).upper().replace("0X", "0x"), fetch=fetch)) == "holder"
    assert run(tiers.tier_for(addr(6), fetch=fetch)) == "holder"
    assert run(tiers.tier_for(None, fetch=fetch)) == "free"
    monkeypatch.setenv("REFLEX_TOKEN_NAME", "RFX")
    monkeypatch.setenv("REFLEX_TOKEN_MIN", "100")
    assert run(tiers.tier_for(addr(1), now=NOON, fetch=fetch)) == "holder"
    assert run(tiers.tier_for(addr(1), now=NOON + 60, fetch=fetch)) == "holder" and len(reads) == 1   # cached
    monkeypatch.setenv("REFLEX_TOKEN_MIN", "200")
    assert run(tiers.tier_for(addr(1), now=NOON + 120, fetch=fetch)) == "free"
    run(tiers.tier_for(addr(1), now=NOON + tiers.CACHE_S + 1, fetch=fetch))
    assert len(reads) == 2                                                          # read again after 10 min
    monkeypatch.setenv("REFLEX_TOKEN_INDEX", "0")                                   # by index: USDC here
    tiers.reset()
    assert run(tiers.tier_for(addr(1), now=NOON, fetch=fetch)) == "holder"


def test_tiers_are_open_until_both_flags_are_on(off, monkeypatch):
    monkeypatch.setenv("ACCESS_TIERS", "1")
    assert not tiers.enforced() and run(tiers.allows(None))          # accounts off: nothing gated
    monkeypatch.setenv("REFLEX_ACCOUNTS", "1")
    assert tiers.enforced() and not run(tiers.allows(None))


def test_delayed_radar(off):
    assert radar_delay.get("1d", 3600, now=NOON)["coins"] == []
    assert radar_delay.note("1d", {"coins": [{"coin": "A"}]}, 3600, now=NOON)
    assert not radar_delay.note("1d", {"coins": [{"coin": "B"}]}, 3600, now=NOON + 60)       # too soon
    assert radar_delay.note("1d", {"coins": [{"coin": "C"}]}, 3600, now=NOON + 900)
    got = radar_delay.get("1d", 3600, now=NOON + 3600)
    assert got["coins"] == [{"coin": "A"}] and got["delayed"] and got["as_of"] == NOON
    radar_delay.reset(off)                                                               # after a restart
    assert radar_delay.get("1d", 3600, now=NOON + 4500)["coins"] == [{"coin": "C"}]


# ------------------------------------------------------------------ HTTP, flags off and on
@pytest.fixture
def client():
    import main
    return TestClient(main.app), main


def test_flags_off_behave_as_before(off, client, monkeypatch):
    c, main = client
    assert c.get("/api/auth/status").json() == {"enforced": False}
    assert c.get("/api/me").json() == {"accounts": False, "tiers": False}
    assert c.post("/api/auth/wallet/nonce", json={"address": addr(1), "domain": DOMAIN}).status_code == 404
    assert c.get("/api/me/follows").status_code == 404
    assert c.post("/api/me/follows", json={"address": addr(2)}).status_code == 404
    live = {"tf": "1d", "coins": [{"coin": "LIVE"}]}

    async def build(tf):
        return live
    monkeypatch.setattr(main, "_setup_map_cached", build)
    assert c.get("/api/setup-map?tf=1d").json() == live
    # The owner's lists answer as before, without a session.
    assert c.get("/api/hyperlens/followed").status_code == 200
    assert c.post("/api/hyperlens/followed", json={"address": addr(3)}).json() == {"added": True, "address": addr(3)}
    assert ft.addresses() == {addr(3)}
    assert run(main.accounts_api.require_holder(SimpleNamespace(headers={}))) is None
    assert radar_delay._snaps == {}                                   # nothing kept while tiers are off


def test_sign_in_and_lists_over_http(on, client, monkeypatch):
    c, main = client
    monkeypatch.setenv("REFLEX_ADMIN_KEY", "k3y")                     # account writes do not need it
    monkeypatch.setenv("REFLEX_FOLLOW_CAP", "2")
    acct = Account.create()
    msg = c.post("/api/auth/wallet/nonce", json={"address": acct.address, "domain": DOMAIN}).json()["message"]
    r = c.post("/api/auth/wallet/verify", json={"message": msg, "signature": sign(acct, msg)})
    assert r.status_code == 200 and r.json()["tier"] == "free"
    replay = c.post("/api/auth/wallet/verify", json={"message": msg, "signature": sign(acct, msg)})
    assert replay.status_code == 400 and "already used" in replay.json()["detail"]
    h = {"X-Reflex-Session": r.json()["token"]}
    me = c.get("/api/me", headers=h).json()
    assert me["address"] == acct.address.lower() and me["features"]["follows"] is True     # tiers off
    assert c.get("/api/me/follows").status_code == 403                                     # no session
    for i in range(2):
        assert c.post("/api/me/follows", json={"address": addr(10 + i)}, headers=h).json()["added"]
    over = c.post("/api/me/follows", json={"address": addr(20)}, headers=h)
    assert over.status_code == 400 and "at most 2" in over.json()["detail"]
    body = c.get("/api/me/follows", headers=h).json()
    assert {t["address"] for t in body["traders"]} == {addr(10), addr(11)} and body["cap"] == 2
    assert c.post("/api/me/watch", json={"coin": "sui", "tf": "4h"}, headers=h).json() == {"watching": "SUI"}
    assert c.get("/api/me/watch", headers=h).json()["coins"][0]["coin"] == "SUI"
    link = c.post("/api/me/telegram/link", headers=h).json()
    assert accounts.tg_claim(link["code"], 31337) == acct.address.lower()
    assert c.put("/api/me/telegram", json={"quiet": None, "brief": False}, headers=h).json() == {"quiet": None, "brief": False}
    assert c.post("/api/hyperlens/followed", json={"address": addr(3)}).status_code == 403  # the owner's list: admin key
    assert c.post("/api/auth/wallet/logout", headers=h).json() == {"ok": True}
    assert c.get("/api/me/follows", headers=h).status_code == 403


def test_owner_account_is_the_single_owner_lists(on, client, monkeypatch):
    c, _ = client
    owner = Account.create()
    monkeypatch.setenv("REFLEX_OWNER_ADDRESS", owner.address.lower())
    ft.add(addr(77), "old follow")
    token, _ = wa.start_session(owner.address.lower())
    h = {"X-Reflex-Session": token}
    body = c.get("/api/me/follows", headers=h).json()
    assert [t["address"] for t in body["traders"]] == [addr(77)] and body["cap"] is None
    c.post("/api/me/follows", json={"address": addr(78)}, headers=h)
    assert ft.addresses() == {addr(77), addr(78)} and accounts.follows(owner.address) == {}


def test_tiers_on_gate_holder_features(on, client, monkeypatch):
    c, main = client
    monkeypatch.setenv("ACCESS_TIERS", "1")
    monkeypatch.setenv("REFLEX_HOLDER_ALLOWLIST", addr(2))
    free, _ = wa.start_session(addr(1))
    holder, _ = wa.start_session(addr(2))
    live = {"tf": "1d", "coins": [{"coin": "LIVE"}]}

    async def build(tf):
        return live
    monkeypatch.setattr(main, "_setup_map_cached", build)
    got = c.get("/api/setup-map?tf=1d", headers={"X-Reflex-Session": free}).json()
    assert got["delayed"] and got["coins"] == []                            # nothing an hour old yet
    assert c.get("/api/setup-map?tf=1d", headers={"X-Reflex-Session": holder}).json() == live
    assert c.get("/api/setup-map?tf=1d").json()["delayed"]                   # signed out: free
    trader = f"/api/traders/{addr(50)}"
    assert c.get(trader, headers={"X-Reflex-Session": free}).json() == {"detail": "holder"}
    assert c.get("/api/setup-map/ladder?coin=BTC", headers={"X-Reflex-Session": free}).status_code == 403
    assert c.post("/api/me/follows", json={"address": addr(9)}, headers={"X-Reflex-Session": free}).status_code == 403
    assert c.post("/api/me/follows", json={"address": addr(9)}, headers={"X-Reflex-Session": holder}).json()["added"]
    assert c.get("/api/hyperlens/followed", headers={"X-Reflex-Session": holder}).status_code == 403   # owner only
    me = c.get("/api/me", headers={"X-Reflex-Session": free}).json()
    assert me["tier"] == "free" and me["features"]["live_radar"] is False and me["radar_delay_min"] == 60
