import followed_traders as ft


def p(size, usd, px=1.0):
    return {"size": size, "size_usd": usd, "entry_px": px, "mark_px": usd / size if size else px}


def test_diff_finds_opens_closes_adds_and_cuts():
    prev = {("SUI", "long"): p(10_000, 30_000), ("ETH", "short"): p(10, 25_000), ("DOGE", "long"): p(100, 20)}
    cur = {("SUI", "long"): p(15_000, 45_000), ("BTC", "long"): p(1, 80_000), ("DOGE", "long"): p(100, 20)}
    kinds = sorted((c["kind"], c["coin"]) for c in ft.diff(prev, cur))
    assert kinds == [("add", "SUI"), ("close", "ETH"), ("open", "BTC")]
    cut = ft.diff({("SUI", "long"): p(20_000, 60_000)}, {("SUI", "long"): p(10_000, 30_000)})
    assert [c["kind"] for c in cut] == ["cut"] and round(cut[0]["delta_usd"]) == 30_000


def test_small_changes_are_ignored():
    assert ft.diff({}, {("X", "long"): p(1, 5_000)}) == []                                  # open under $10K
    assert ft.diff({("X", "long"): p(100, 50_000)}, {("X", "long"): p(110, 55_000)}) == []  # +10% size


def test_follow_list_and_message(tmp_path, monkeypatch):
    monkeypatch.setattr(ft, "PATH", tmp_path / "f.json")
    monkeypatch.setattr(ft, "_items", {})
    monkeypatch.setattr(ft, "_loaded", True)
    assert ft.add("0xABCDEF0123456789", "2Z early") and not ft.add("0xabcdef0123456789")
    assert "0xabcdef0123456789" in ft.addresses()
    msg = ft.message("0xabcdef0123456789", "profitable trader",
                     [{"kind": "open", "coin": "2Z", "side": "long", "usd": 38_000, "px": 0.0505}],
                     [{"coin": "2Z", "side": "long", "size_usd": 38_000}, {"coin": "HYPE", "side": "long", "size_usd": 120_000}])
    assert "(2Z early)" in msg and "Opened long 2Z $38K at 0.0505" in msg and "Now holds: long HYPE $120K, long 2Z $38K" in msg
    assert ft.remove("0xABCDEF0123456789") and ft.addresses() == set()
