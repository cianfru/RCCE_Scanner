"""Invites and usage: invite codes at the same login (attribution, revoke, expiry), the shared
code unchanged, the beacon (validation, caps, rate limit, no address kept), the aggregates
(active people, the week-4 bar, the retention grid) and the owner-only Intel endpoints."""
import json
import sqlite3
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

import access
import accounts
import invites
import usage
import usage_api
import usage_db
import usage_geo
import wallet_auth as wa

CODE = "shared-s3cret"
KEY = "adm1n"
UA_PHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Version/17.0 Mobile/15E148 Safari/604.1"
IP = "203.0.113.77"


@pytest.fixture
def env(tmp_path, monkeypatch):
    for k in ("REFLEX_ACCESS_CODE", "REFLEX_AUTH_SECRET", "REFLEX_ADMIN_KEY", "REFLEX_ACCOUNTS",
              "REFLEX_OWNER_ADDRESS", "REFLEX_USAGE", "REFLEX_USAGE_GEO_LOOKUP", "REFLEX_USAGE_DAYS"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("REFLEX_ACCESS_CODE", CODE)
    monkeypatch.setenv("REFLEX_ADMIN_KEY", KEY)
    monkeypatch.setenv("REFLEX_USAGE_TZ", "UTC")
    usage_db.use_path(tmp_path / "usage.db")
    accounts.use_path(tmp_path / "accounts.db")
    wa._cache.clear()
    usage.reset_memory()
    usage_api._limiter._hits.clear()
    return tmp_path


@pytest.fixture
def client(env):
    import main
    return TestClient(main.app)


def login(c, code):
    return c.post("/api/auth/login", json={"code": code})


def beacon(c, token, events, sid="abcdef123456", headers=None, **extra):
    body = {"t": token, "sid": sid, "e": events, **extra}
    return c.post("/api/usage/beacon", content=json.dumps(body),
                  headers={"content-type": "text/plain", "user-agent": UA_PHONE, "x-forwarded-for": IP,
                           **(headers or {})})


# ------------------------------------------------------------------ invites and login
def test_invite_login_is_attributed_and_revoke_ends_it(client):
    inv = invites.create("Marco")
    assert inv["code"].startswith("RFX-") and inv["label"] == "Marco"
    r = login(client, inv["code"].lower().replace("-", " "))       # case, spaces and dashes do not matter
    assert r.status_code == 200
    token = r.json()["token"]
    assert access.token_person(token) == inv["id"]
    assert invites.get(inv["id"])["logins"] == 1 and invites.get(inv["id"])["first_login"]
    assert client.get("/api/auth/status", headers={"authorization": f"Bearer {token}"}).status_code == 200
    assert client.get("/api/net-stats", headers={"authorization": f"Bearer {token}"}).status_code == 200

    invites.revoke(inv["id"])
    assert access.token_person(token) is None
    assert client.get("/api/net-stats", headers={"authorization": f"Bearer {token}"}).status_code == 401
    assert login(client, inv["code"]).status_code == 401


def test_expired_invite_and_forged_tokens_are_refused(env):
    now = 1_800_000_000
    inv = invites.create("Temp", expires=now + 3600, now=now)
    assert access.login(inv["code"], now=now)
    assert access.login(inv["code"], now=now + 7200) is None
    token = access.issue_token(now, invite=inv["id"])
    assert access.token_person(token, now=now) == inv["id"]
    assert access.token_person(token, now=now + 7200) is None
    expires, _, sig = token.split(".")
    other = invites.create("Other", now=now)["id"]
    assert access.token_person(f"{expires}.{other}.{sig}", now=now) is None      # the id is signed
    assert access.token_person(f"{expires}.{sig}", now=now) is None
    assert access.token_person("x" * 500) is None


def test_shared_code_still_works(client):
    r = login(client, CODE)
    token = r.json()["token"]
    assert r.json()["enforced"] is True
    assert token.count(".") == 1                       # the old token form
    assert access.token_person(token) == invites.SHARED
    assert access.allowed("/api/scan", {"authorization": f"Bearer {token}"}, {})
    assert login(client, "wrong").status_code == 401
    assert invites.labels()[invites.SHARED] == "shared code"


def test_open_api_login_unchanged(env, monkeypatch, client):
    monkeypatch.delenv("REFLEX_ACCESS_CODE")
    assert login(client, "anything").json() == {"ok": True, "enforced": False, "token": None}


# ------------------------------------------------------------------ the beacon
def test_beacon_stores_counts_session_and_person(client):
    inv = invites.create("Ana")
    token = login(client, inv["code"]).json()["token"]
    r = beacon(client, token, [["view_radar", ""], ["radar_tab", "short"], ["radar_tab", "sideways"],
                               ["nope", ""], "search", ["theme", "light"], 42],
               headers={"x-vercel-ip-country": "PT", "x-vercel-ip-city": "S%C3%A3o%20Jo%C3%A3o"})
    assert r.status_code == 202 and r.json() == {"ok": True, "kept": 4}
    rows = usage_db.q("SELECT name, v, n FROM counts ORDER BY name")
    assert rows == [("radar_tab", "short", 1), ("search", "", 1), ("theme", "light", 1), ("view_radar", "", 1)]
    s = usage_db.q("SELECT person, country, city, device, browser, n FROM sessions")
    assert s == [(inv["id"], "PT", "São João", "phone", "Safari", 4)]
    beacon(client, token, [["view_coin", "BTC"]])
    assert usage_db.q("SELECT v FROM counts WHERE name = 'view_coin'") == [("",)]   # no detail kept
    assert usage_db.q("SELECT n FROM sessions") == [(5,)]


def test_beacon_validation_and_caps(client):
    token = login(client, CODE).json()["token"]
    assert beacon(client, "1.bad", [["view_radar", ""]]).json() == {"ok": False, "kept": 0}
    assert beacon(client, token, [["view_radar", ""]], sid="BAD SID!").json()["kept"] == 0
    assert beacon(client, token, [["search", ""]] * 80).json()["kept"] == usage.MAX_EVENTS
    big = client.post("/api/usage/beacon", content="x" * (usage.MAX_BODY + 1), headers={"x-forwarded-for": "1.1.1.1"})
    assert big.status_code == 413
    assert client.post("/api/usage/beacon", content="not json", headers={"x-forwarded-for": "1.1.1.2"}).status_code == 400
    assert client.post("/api/usage/beacon", content="[1]", headers={"x-forwarded-for": "1.1.1.3"}).status_code == 400
    assert usage_db.q("SELECT COUNT(*) FROM sessions")[0][0] == 1


def test_beacon_needs_no_admin_key_or_header_token(client):
    token = login(client, CODE).json()["token"]
    # No Authorization header, no X-Admin-Key: the token rides in the body.
    assert beacon(client, token, [["view_scanner", ""]]).json()["ok"] is True


def test_beacon_is_rate_limited(client):
    token = login(client, CODE).json()["token"]
    codes = [beacon(client, token, [["search", ""]]).status_code for _ in range(25)]
    assert codes.count(202) == 20 and codes[-1] == 429


def test_daily_cap_per_person(env, monkeypatch):
    monkeypatch.setattr(usage, "DAILY_CAP", 5)
    assert usage.ingest("shared", "aaaaaaaa", [("search", "")] * 4, now=1_800_000_000) == 4
    assert usage.ingest("shared", "aaaaaaaa", [("search", "")] * 4, now=1_800_000_010) == 1
    assert usage.ingest("shared", "aaaaaaaa", [("search", "")], now=1_800_000_020) == 0


def test_session_id_cannot_move_between_people(env):
    assert usage.ingest("shared", "abcdefgh", [("search", "")], now=1_800_000_000) == 1
    assert usage.ingest("0000abcd", "abcdefgh", [("search", "")], now=1_800_000_010) == 0


def test_no_raw_ip_or_user_agent_is_stored(client, env, monkeypatch):
    monkeypatch.setenv("REFLEX_USAGE_GEO_LOOKUP", "1")
    seen = []

    async def fake(ip):
        seen.append(ip)
        return "IT", "Rome"
    monkeypatch.setattr(usage_geo, "_fetch", fake)
    token = login(client, CODE).json()["token"]
    beacon(client, token, [["view_scanner", ""]], sid="sessionone")
    beacon(client, token, [["view_radar", ""]], sid="sessiontwo")
    assert seen == [IP]                                          # looked up once for the day
    assert usage_db.q("SELECT country, city FROM sessions ORDER BY sid") == [("IT", "Rome"), ("IT", "Rome")]
    usage_db.conn().execute("PRAGMA wal_checkpoint(FULL)")
    dump = "\n".join(sqlite3.connect(str(usage_db.PATH)).iterdump())
    assert IP not in dump and "iPhone" not in dump and "Mozilla" not in dump
    raw = (env / "usage.db").read_bytes()
    assert IP.encode() not in raw
    assert all(IP not in k for k in usage_geo._cache)


def test_wallet_session_marks_wallet_and_telegram(client, monkeypatch):
    monkeypatch.setenv("REFLEX_ACCOUNTS", "1")
    user = "0x" + "ab" * 20
    session, _ = wa.start_session(user)
    accounts.tg_code(user)
    code = accounts._q("SELECT code FROM tg_codes")[0][0]
    accounts.tg_claim(code, 555)
    token = login(client, CODE).json()["token"]
    beacon(client, token, [["view_traders", ""]], s=session)
    assert usage_db.q("SELECT wallet, telegram FROM people") == [(1, 1)]
    assert user not in "\n".join(sqlite3.connect(str(usage_db.PATH)).iterdump())


def test_recording_can_be_switched_off(client, monkeypatch):
    monkeypatch.setenv("REFLEX_USAGE", "0")
    token = login(client, CODE).json()["token"]
    assert beacon(client, token, [["view_radar", ""]]).json()["ok"] is False
    assert usage_db.q("SELECT COUNT(*) FROM counts")[0][0] == 0


def test_request_details():
    assert usage.device_of(UA_PHONE) == ("phone", "Safari")
    assert usage.device_of("Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 Chrome/120.0 Safari/537.36") == ("desktop", "Chrome")
    assert usage.device_of("Mozilla/5.0 (iPad; CPU OS 17_0) Version/17.0 Safari/604.1")[0] == "tablet"
    assert usage.device_of("Mozilla/5.0 (Linux; Android 14) Chrome/120 Mobile Safari/537.36 Edg/120")[1] == "Edge"
    assert usage.device_of(None) == ("unknown", "other")
    assert usage.geo_of({"cf-ipcountry": "de"}) == ("DE", None)
    assert usage.geo_of({}, {"cc": "FR", "city": "Lyon"}) == ("FR", "Lyon")
    assert usage.geo_of({}, {"cc": "BR", "city": "S%25C3%25A3o%2520Paulo"}) == ("BR", "São Paulo")
    assert usage.geo_of({"x-vercel-ip-country": "XX"}) == (None, None)
    assert usage.geo_of({"x-vercel-ip-country": "<script>"}) == (None, None)


def test_old_data_is_pruned(env):
    old = 1_800_000_000
    usage.ingest("shared", "oldsession", [("search", "")], now=old)
    usage.reset_memory()
    usage.ingest("shared", "newsession", [("search", "")], now=old + 200 * 86400)
    assert usage_db.q("SELECT sid FROM sessions") == [("newsession",)]
    assert len(usage_db.q("SELECT * FROM activity")) == 1
    assert usage_db.q("SELECT COUNT(*) FROM people")[0][0] == 1        # first seen outlives the window


# ------------------------------------------------------------------ aggregates
def at(day: str, hour: int = 12) -> float:
    return datetime.fromisoformat(f"{day}T{hour:02d}:00:00+00:00").timestamp()


def use(person, day, name="view_scanner"):
    usage.ingest(person, f"s{person}{day.replace('-', '')}"[:32].lower(), [(name, "")], now=at(day))


def test_active_people_and_invited(env):
    a = invites.create("A")["id"]
    b = invites.create("B")["id"]
    invites.create("C")                                         # invited, never logged in
    invites.record_login(a)
    invites.record_login(b)
    today = "2026-09-30"
    use(a, today)
    use(b, "2026-09-26")
    use("shared", "2026-09-10")
    use(a, "2026-07-01")
    s = usage.summary(now=at(today, 18))
    top = s["top"]
    assert (top["today"], top["d7"], top["d28"]) == (1, 2, 3)
    assert (top["invited"], top["logged_in"]) == (3, 2)
    assert s["dau"][-1] == {"day": today, "n": 1} and len(s["dau"]) == 90
    people = {p["label"]: p for p in s["people"]}
    assert people["A"]["d7"] == 1 and people["A"]["days"] == 2
    assert people["shared code"]["d28"] == 1
    assert people["C"]["first_seen"] is None
    assert people["A"]["device"] == "unknown"


def test_week4_bar_counts_only_finished_windows(env):
    start = datetime(2026, 7, 1)
    d = lambda n: (start + timedelta(days=n)).strftime("%Y-%m-%d")
    for p in ("p1", "p2", "p3"):
        use(p, d(0))
    use("p1", d(30))                     # active in its fourth week
    use("p2", d(20))                     # came back, but not in week four
    use("p4", d(40))                     # too recent to count
    s = usage.summary(now=at(d(40), 20))
    w4 = s["top"]["week4"]
    assert (w4["n"], w4["kept"]) == (3, 1)
    assert abs(w4["share"] - 1 / 3) < 1e-9
    assert w4["pending"] == 1


def test_retention_grid(env):
    # Monday 2026-09-07 cohort of two; one returns in week 2. Monday 2026-09-21 cohort of one.
    use("a", "2026-09-07")
    use("b", "2026-09-09")
    use("a", "2026-09-22")
    use("c", "2026-09-21")
    grid = usage.retention_grid(usage._active_days(), datetime(2026, 9, 30).date())
    assert [r["week"] for r in grid] == ["2026-09-07", "2026-09-21"]
    first = grid[0]
    assert first["size"] == 2 and len(first["cells"]) == 4
    assert [c["n"] for c in first["cells"]] == [2, 0, 1, 0]
    assert grid[1]["cells"][0]["share"] == 1.0


def test_features_returning_vs_once(env):
    use("r", "2026-09-20", "follow")
    use("r", "2026-09-25", "view_radar")
    use("o", "2026-09-25", "view_radar")
    f = {x["key"]: x for x in usage.summary(now=at("2026-09-30"))["features"]}
    assert f["view_radar"]["people"] == 2 and f["view_radar"]["returning"] == 1.0 and f["view_radar"]["once"] == 1.0
    assert f["follow"]["returning"] == 1.0 and f["follow"]["once"] == 0.0


# ------------------------------------------------------------------ the owner only
def test_intel_is_owner_only(client, monkeypatch):
    token = login(client, CODE).json()["token"]
    auth = {"authorization": f"Bearer {token}"}
    assert client.get("/api/owner/intel", headers=auth).status_code == 403
    assert client.get("/api/owner/intel", headers={**auth, "x-admin-key": "wrong"}).status_code == 403
    r = client.get("/api/owner/intel", headers={**auth, "x-admin-key": KEY})
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    assert client.post("/api/owner/invites", json={"label": "X"}, headers=auth).status_code == 403
    made = client.post("/api/owner/invites", json={"label": "  Luca  ", "expires_days": 14},
                       headers={**auth, "x-admin-key": KEY}).json()
    assert made["label"] == "Luca" and made["expires"] and made["code"]
    assert client.post("/api/owner/invites", json={"label": ""}, headers={**auth, "x-admin-key": KEY}).status_code == 400
    assert client.delete(f"/api/owner/invites/{made['id']}", headers=auth).status_code == 403
    assert client.delete(f"/api/owner/invites/{made['id']}", headers={**auth, "x-admin-key": KEY}).json()["revoked"]
    assert client.delete("/api/owner/invites/zzzz", headers={**auth, "x-admin-key": KEY}).status_code == 404

    # Without an admin key configured, nobody reads it (it does not fall open).
    monkeypatch.delenv("REFLEX_ADMIN_KEY")
    assert client.get("/api/owner/intel", headers=auth).status_code == 403


def test_owner_wallet_session_reads_intel(client, monkeypatch):
    owner = "0x" + "cd" * 20
    monkeypatch.setenv("REFLEX_ACCOUNTS", "1")
    monkeypatch.setenv("REFLEX_OWNER_ADDRESS", owner)
    token = login(client, CODE).json()["token"]
    auth = {"authorization": f"Bearer {token}"}
    mine, _ = wa.start_session(owner)
    other, _ = wa.start_session("0x" + "ef" * 20)
    assert client.get("/api/owner/intel", headers={**auth, wa.HEADER: mine}).status_code == 200
    assert client.get("/api/owner/intel", headers={**auth, wa.HEADER: other}).status_code == 403
