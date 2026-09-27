from intel import coin_intel, pulse

NOW = 1_000_000.0


def op(coin, side, cohort, addr, ago_h, px=1.0, usd=50_000):
    return {"ts": NOW - ago_h * 3600, "prev_ts": NOW - ago_h * 3600 - 1800, "address": addr, "cohort": cohort,
            "coin": coin, "side": side, "entry_px": px, "size_usd": usd}


def test_coin_intel_counts_distinct_new_wallets_and_orders_recent():
    opens = [op("FET", "long", "profitable", "0xa", 2, 0.66), op("FET", "long", "profitable", "0xa", 1, 0.67),
             op("FET", "long", "profitable", "0xb", 10, 0.70), op("FET", "short", "large", "0xc", 3),
             op("ARB", "long", "profitable", "0xd", 1), op("FET", "long", "profitable", "0xe", 30)]
    prof = {"mark": 0.71, "long": {"n": 4, "usd": 900_000, "median_entry": 0.68, "in_profit": 3},
            "short": {"n": 0, "usd": 0, "median_entry": None, "in_profit": 0}}
    out = coin_intel("FET", prof, None, opens, None, NOW)
    assert out["mark"] == 0.71
    assert out["new_24h"]["profitable"] == {"long": 2, "short": 0}        # 0xa twice counts once; 0xe is too old
    assert out["new_6h"]["profitable"] == {"long": 1, "short": 0}
    assert out["new_6h"]["large"] == {"long": 0, "short": 1}
    assert out["large"]["short"]["n"] == 0                               # nobody large holds it
    assert [r["t"] for r in out["recent"]] == sorted((r["t"] for r in out["recent"]), reverse=True)
    assert len(out["recent"]) == 4 and all(r["px"] for r in out["recent"])


def test_pulse_reports_flat_share_and_clusters():
    opens = [op("FET", "long", "profitable", "0xa", 1), op("FET", "long", "profitable", "0xb", 2),
             op("FET", "long", "profitable", "0xb", 3), op("ARB", "short", "profitable", "0xc", 1),
             op("ZEC", "long", "large", "0xd", 1), op("SOL", "long", "profitable", "0xe", 7)]
    p = pulse(278, 98, opens, NOW)
    assert p["flat"] == 180 and p["hours"] == 6
    assert p["opens"] == 4 and p["traders"] == 3 and p["coins"] == 2
    assert p["clusters"] == [{"coin": "FET", "side": "long", "n": 2}]
