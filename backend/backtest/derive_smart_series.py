"""
Derive options wallets for the market history page's Derive drawer (docs/reviews/derive-smart-wallets.md).
Exploration, not a study: context, not a signal.

Two steps, run by hand from backend/ (the page reads only the seed; nothing here runs on the server):

  python -m backtest.derive_smart_series build DATA_DIR OUT_JSON --derive-scan /path/to/derive_scan/backend
      Daily series of what Derive's directional options wallets did, from a sparse copy of Cowboy's `data`
      branch (history/, candles/; cianfru/derive_scan). Wallet names, classes and tiers come from Cowboy's own code
      (derive.history, derive.wallet_alias, derive.balance_history.Replay), so they match its app. Written by the
      exploration of 28 October 2026 and kept as it ran.
  python -m backtest.derive_smart_series seed OUT_JSON [--out seeds/derive_smart_seed.json]
      The drawer's compact seed from that series.
"""
import csv
import json
import sys
import time
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

H = Replay = close_ts = day_ts = index_closes = load_settlements = canonical = None   # Cowboy's modules, at build


def _import_derive(backend: str) -> None:
    global H, Replay, close_ts, day_ts, index_closes, load_settlements, canonical
    sys.path.insert(0, backend)
    from derive import history
    from derive.balance_history import Replay as R, close_ts as ct, day_ts as dt, index_closes as ic, load_settlements as ls
    from derive.wallet_alias import canonical as cn
    H, Replay, close_ts, day_ts, index_closes, load_settlements, canonical = history, R, ct, dt, ic, ls, cn

YEAR = 365 * 86400
COUNT_MIN = 1_000          # the app's count form: a wallet counts long or short from $1,000 of delta
FLOW = ("d_net", "d_long", "d_short", "put_buy", "call_buy", "put_sell", "call_sell", "put_buy_open",
        "n_active", "n_put_buyers", "n_put_open", "n_dl", "n_ds")
OPEN = ("o_net", "o_long", "o_short", "o_put_long", "o_wl", "o_ws", "o_iv_stale", "o_unvalued")
FIELDS = FLOW + OPEN
COINS = ("BTC", "ETH", "ALL")
GROUPS = ("smart", "profitable", "directional", "smart_pit")


def f(x) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def build(root: Path, out: Path) -> None:
    t0 = time.time()
    files = sorted((root / "history" / "days").glob("*.csv.gz"))
    days = [p.name[:10] for p in files]

    # -- prices: candle close, else next-day 08:00 settlement, else the day's perp-weighted index --
    candles = index_closes(root)                                   # {UND: {bar_open_sec: close}}
    sett = {p.stem: json.loads(p.read_text()) for p in (root / "history" / "settlements").glob("*.json")}
    surf = {}
    for p in (root / "history" / "surface").glob("*.csv"):
        surf[p.stem] = {r["day"]: f(r["index"]) for r in csv.DictReader(p.open()) if f(r["index"]) > 0}
    unds = sorted(set(candles) | set(sett) | set(surf))

    def price_for(und, day):
        c = candles.get(und, {}).get(day_ts(day))
        if c:
            return c, "candle"
        s = sett.get(und, {}).get((date.fromisoformat(day) + timedelta(days=1)).strftime("%Y%m%d"))
        if s:
            return s, "settle_next_0800"
        s = surf.get(und, {}).get(day)
        if s:
            return s, "index_avg"
        return None, None

    closes = {u: {} for u in unds}   # what Replay's TradeIVs uses to find near-the-money trades
    for u in unds:
        for d in days:
            v, _ = price_for(u, d)
            if v:
                closes[u][day_ts(d)] = v

    # -- hindsight groups: today's classes and tiers (history/wallets.json, as the app shows them) --
    wdoc = json.loads((root / "history" / "wallets.json").read_text())
    W = wdoc["wallets"]
    SM = {w for w, v in W.items() if v.get("tier") in ("top", "smart")}
    PR = {w for w, v in W.items() if v.get("tier") in ("top", "smart", "profitable")}
    DI = {w for w, v in W.items() if v["class"] == "directional"}
    canon = canonical(root)
    assert canon.digest == wdoc["aliases"], "alias map differs from the one wallets.json was built with"

    rp = Replay(load_settlements(root))   # point-in-time classes and tiers (the balance backfill's replay)
    pos = defaultdict(dict)               # wallet -> {instrument: net contracts}, every wallet
    first_seen = {}                       # wallet -> first day with an option trade
    pit_smart = set()                     # Smart cohort at the previous close (point in time)
    out_rows, val_rows = [], []
    unvalued_total = defaultdict(int)

    for p, day in zip(files, days):
        rows = H.canonical_rows(H.read_day(p), canon, rp.members)
        acc = {(g, c): defaultdict(float) for g in GROUPS for c in COINS}
        active = {(g, c): set() for g in GROUPS for c in COINS}
        putbuy = {(g, c): set() for g in GROUPS for c in COINS}
        putopen = {(g, c): set() for g in GROUPS for c in COINS}
        wcd = {g: defaultdict(float) for g in GROUPS}      # (wallet, und) -> delta added today
        for r in rows:
            name = r["instrument"]
            if name.endswith("-PERP"):
                continue
            o = rp.opt(name)
            if not o:
                continue
            und, _, _, cp = o
            w = r["wallet"]
            first_seen.setdefault(w, day)
            buy, sell = f(r["buy_contracts"]), f(r["sell_contracts"])
            bv, sv, d = f(r["buy_value_usd"]), f(r["sell_value_usd"]), f(r["delta_usd"])
            before = pos[w].get(name, 0.0)
            after = before + buy - sell
            if abs(after) < 1e-9:
                pos[w].pop(name, None)
            else:
                pos[w][name] = after
            gs = [g for g, s in (("smart", SM), ("profitable", PR), ("directional", DI), ("smart_pit", pit_smart))
                  if w in s]
            if not gs:
                continue
            # net new long put contracts today (a mixed buy/sell day is netted), at the day's average buy price
            opened = max(0.0, max(after, 0.0) - max(before, 0.0)) if cp == "P" and buy > 0 else 0.0
            put_open = opened * bv / buy if opened else 0.0
            keys = (und, "ALL") if und in ("BTC", "ETH") else ("ALL",)
            for g in gs:
                wcd[g][(w, und)] += d
                for c in keys:
                    a = acc[(g, c)]
                    a["d_net"] += d
                    if cp == "P":
                        a["put_buy"] += bv
                        a["put_sell"] += sv
                        a["put_buy_open"] += put_open
                        if buy > 0:
                            putbuy[(g, c)].add(w)
                        if opened:
                            putopen[(g, c)].add(w)
                    else:
                        a["call_buy"] += bv
                        a["call_sell"] += sv
                    active[(g, c)].add(w)
        for g in GROUPS:   # long and short parts: each wallet's net delta added on a coin that day
            wall = defaultdict(float)
            for (w, und), d in wcd[g].items():
                wall[w] += d
                for c in ((und, "ALL") if und in ("BTC", "ETH") else ("ALL",)):
                    acc[(g, c)]["d_long" if d > 0 else "d_short"] += d
                    if c != "ALL":
                        acc[(g, c)]["n_dl"] += d >= COUNT_MIN
                        acc[(g, c)]["n_ds"] += d <= -COUNT_MIN
            for d in wall.values():
                acc[(g, "ALL")]["n_dl"] += d >= COUNT_MIN
                acc[(g, "ALL")]["n_ds"] += d <= -COUNT_MIN
            for c in COINS:
                acc[(g, c)]["n_active"] = len(active[(g, c)])
                acc[(g, c)]["n_put_buyers"] = len(putbuy[(g, c)])
                acc[(g, c)]["n_put_open"] = len(putopen[(g, c)])
        flow_cohort = len(pit_smart)

        # -- point-in-time tiers at this close (used for the close's book and the next day's flows) --
        rp.add_day(day, rows, closes)
        as_of = close_ts(day)
        rp.settle_through(as_of)
        tiers = rp.tiers()
        pit_close = {w for w, t in tiers.items() if t in ("top", "smart")}

        # -- open books at the close, re-valued: Black-76 at the close with the traded IV of the time --
        units = {}

        def unit(name):
            if name not in units:
                und, exp, k, cp = rp.opt(name)
                idx, _ = price_for(und, day)
                res = None
                if idx and exp > as_of:
                    iv, stale = rp.ivs.iv_for(name, und, day), False   # the app's bounds: 21 d own IV, 7 d ATM IV
                    if not iv:
                        got = rp.ivs.inst.get(name) or rp.ivs.und.get(und)   # older evidence, flagged
                        iv, stale = (got[1] if got else None), True
                    if iv:
                        res = (H.option_delta(idx, k, (exp - as_of) / YEAR, iv, cp) * idx, stale)
                units[name] = res
            return units[name]

        members = {"smart": SM, "profitable": PR, "directional": DI, "smart_pit": pit_close}
        union = SM | PR | DI | pit_close
        wo = defaultdict(lambda: defaultdict(float))       # wallet -> und -> open delta
        wput = defaultdict(lambda: defaultdict(float))     # wallet -> und -> delta of long puts
        wstale = defaultdict(lambda: defaultdict(float))   # wallet -> und -> |delta| valued with stale IV
        wgross = defaultdict(lambda: defaultdict(float))
        wunv = defaultdict(lambda: defaultdict(int))
        win = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])    # (wallet, und) -> 7 d net, gross, 30 d net, gross
        for w in union:
            book = pos.get(w)
            if not book:
                continue
            for name in list(book):
                o = rp.opt(name)
                if o[1] <= as_of:          # expired: settled, no longer held
                    del book[name]
                    continue
                net = book[name]
                u = unit(name)
                if u is None:
                    wunv[w][o[0]] += 1
                    continue
                v = net * u[0]
                wo[w][o[0]] += v
                wgross[w][o[0]] += abs(v)
                if u[1]:
                    wstale[w][o[0]] += abs(v)
                if net > 0 and o[3] == "P":
                    wput[w][o[0]] += v
                if w in pit_close and o[0] in ("BTC", "ETH"):
                    cell = win[(w, o[0])]
                    if o[1] <= as_of + 7 * 86400:
                        cell[0] += v
                        cell[1] += abs(v)
                    if o[1] <= as_of + 30 * 86400:
                        cell[2] += v
                        cell[3] += abs(v)
        for g in GROUPS:
            tot = defaultdict(float)   # wallet -> open delta over every coin (for the ALL counts)
            gross = defaultdict(float)
            stale = defaultdict(float)
            for w in members[g]:
                for und, v in wo.get(w, {}).items():
                    keys = (und, "ALL") if und in ("BTC", "ETH") else ("ALL",)
                    for c in keys:
                        a = acc[(g, c)]
                        a["o_net"] += v
                        a["o_long" if v > 0 else "o_short"] += v
                        a["o_put_long"] += wput[w].get(und, 0.0)
                        gross[c] += wgross[w][und]
                        stale[c] += wstale[w][und]
                        if c != "ALL":
                            a["o_wl"] += v >= COUNT_MIN
                            a["o_ws"] += v <= -COUNT_MIN
                    tot[w] += v
                for und, n in wunv.get(w, {}).items():
                    for c in ((und, "ALL") if und in ("BTC", "ETH") else ("ALL",)):
                        acc[(g, c)]["o_unvalued"] += n
                    unvalued_total[(g, und)] += n
            for v in tot.values():
                acc[(g, "ALL")]["o_wl"] += v >= COUNT_MIN
                acc[(g, "ALL")]["o_ws"] += v <= -COUNT_MIN
            for c in COINS:
                acc[(g, c)]["o_iv_stale"] = stale[c] / gross[c] if gross[c] else 0.0

        # point-in-time Smart book within 7 and 30 days, to compare with history/balance.json
        vr = {"close": as_of}
        for und in ("BTC", "ETH"):
            cells = [c for (w, u), c in win.items() if u == und]
            vr[und] = [sum(c[0] for c in cells), sum(c[1] for c in cells), sum(c[2] for c in cells),
                       sum(c[3] for c in cells)]
        val_rows.append(vr)

        sizes = {"smart": sum(1 for w in SM if first_seen.get(w, "9999") <= day),
                 "profitable": sum(1 for w in PR if first_seen.get(w, "9999") <= day),
                 "directional": sum(1 for w in DI if first_seen.get(w, "9999") <= day),
                 "smart_pit": flow_cohort}
        row = {"day": day, "sizes": sizes, "pit_close_size": len(pit_close)}
        for und in ("BTC", "ETH"):
            v, src = price_for(und, day)
            row[und] = {"price": v, "src": src, "close": candles.get(und, {}).get(day_ts(day)),
                        "settle_0800": sett.get(und, {}).get(day.replace("-", "")), "index_avg": surf.get(und, {}).get(day)}
        row["acc"] = {f"{g}.{c}": dict(acc[(g, c)]) for g in GROUPS for c in COINS}
        out_rows.append(row)
        pit_smart = pit_close

    # -- validation: final open contracts of the Smart wallets vs history/positions.json --
    pdoc = json.loads((root / "history" / "positions.json").read_text())
    mine = defaultdict(float)
    for w in SM:
        for name, net in pos.get(w, {}).items():
            if rp.opt(name)[1] > close_ts(days[-1]):
                mine[name] += net
    theirs = {name: cell["smart"][0] for und, insts in pdoc["positions"].items() for name, cell in insts.items()
              if cell.get("smart") and cell["smart"][1]}
    names = set(mine) | set(theirs)
    diff = [n for n in names if abs(mine.get(n, 0) - theirs.get(n, 0)) > 1e-6 * max(1, abs(theirs.get(n, 0)))]
    print(f"validation positions.json smart: {len(names)} instruments, {len(diff)} differ", diff[:5])

    # -- write: one row per day, columns named group.coin.field --
    cols = ["day"]
    for und in ("BTC", "ETH"):
        cols += [f"{und}.price", f"{und}.price_src", f"{und}.close", f"{und}.settle_0800", f"{und}.index_avg"]
    cols += [f"{g}.size" for g in GROUPS]
    cols += [f"{g}.{c}.{k}" for g in GROUPS for c in COINS for k in FIELDS]

    def num(k, v):
        if v is None:
            return None
        if k in ("o_iv_stale",):
            return round(v, 3)
        return int(round(v))

    rows_json = []
    for r in out_rows:
        line = [r["day"]]
        for und in ("BTC", "ETH"):
            x = r[und]
            line += [None if x["price"] is None else round(x["price"], 2), x["src"],
                     None if x["close"] is None else round(x["close"], 2),
                     None if x["settle_0800"] is None else round(x["settle_0800"], 2),
                     None if x["index_avg"] is None else round(x["index_avg"], 2)]
        line += [r["sizes"][g] for g in GROUPS]
        for g in GROUPS:
            for c in COINS:
                a = r["acc"][f"{g}.{c}"]
                line += [num(k, a.get(k, 0.0)) for k in FIELDS]
        rows_json.append(line)

    meta = {
        "title": "Derive options wallets, daily: delta added, premium by side, open delta at the close",
        "status": "Exploration, not the declared study. Context, not a signal.",
        "first_day": days[0], "last_day": days[-1], "days": len(days),
        "source": "cianfru/derive_scan data branch: history/days (per wallet and instrument per finished UTC day), "
                  "history/wallets.json, history/wallet_aliases.json, history/settlements, history/surface, candles",
        "wallets_as_of": wdoc["through"],
        "groups": {
            "smart": "today's Smart wallets as the app shows them (tiers top and smart); identical to the top tier "
                     "today because the top fifth of directional wallets is more than 50, so no wallet carries the "
                     "'smart' label",
            "profitable": "every directional wallet with positive options PnL (tiers top, smart, profitable)",
            "directional": "class directional today: market makers, income sellers, hedgers and occasional wallets "
                           "(< 20 option legs or < 90 days active) left out",
            "smart_pit": "point-in-time Smart cohort: classes and tiers recomputed at every close from the "
                         "information up to it (balance_history.Replay); a day's flows use the previous close's "
                         "cohort, a close's open book that close's cohort",
        },
        "group_sizes_today": {"smart": len(SM), "profitable": len(PR), "directional": len(DI)},
        "fields": {
            "d_net": "option delta added that day, USD (Black-76 at each trade's IV on the index; buys of calls and "
                     "sales of puts add, buys of puts and sales of calls subtract; closing trades count too)",
            "d_long": "sum over wallets of each wallet's positive net delta added on the coin that day (ALL: summed per coin)",
            "d_short": "same, negative part (a negative number)",
            "put_buy": "premium paid on puts bought, USD (includes buying back sold puts)",
            "call_buy": "premium paid on calls bought, USD", "put_sell": "premium received on puts sold, USD",
            "call_sell": "premium received on calls sold, USD",
            "put_buy_open": "premium on net new long put contracts (increase in a wallet's long put position that "
                            "day x its average buy price; a day with buys and sells of one put is netted)",
            "n_active": "wallets of the group that traded an option of the coin that day",
            "n_put_buyers": "wallets of the group that bought a put of the coin that day",
            "n_put_open": "wallets of the group that opened net new long puts of the coin that day",
            "n_dl": "wallets whose net delta added on the coin that day was >= +$1,000 (ALL: summed over coins per wallet)",
            "n_ds": "wallets whose net delta added on the coin that day was <= -$1,000",
            "o_net": "open option delta at the close (00:00 UTC after the day), USD: positions are running sums of "
                     "buys minus sells since December 2023, held to expiry, re-valued with Black-76 at the close "
                     "price and the instrument's last traded IV (21 days), else the coin's near-the-money traded IV "
                     "(7 days), else older traded IV (counted in o_iv_stale)",
            "o_long": "sum of positive per-wallet open delta on the coin", "o_short": "negative part",
            "o_put_long": "open delta of long put positions (negative)",
            "o_wl": "wallets with open delta >= +$1,000 on the coin (ALL: summed over coins per wallet)",
            "o_ws": "wallets with open delta <= -$1,000",
            "o_iv_stale": "share of gross open delta valued with IV older than the app's bounds",
            "o_unvalued": "open positions with no traded IV at all (left out of the open figures)",
            "size": "hindsight groups: members that had traded an option by that day; smart_pit: the cohort size "
                    "used for that day's flows",
        },
        "price": {
            "price": "close proxy: Derive's daily index candle close (candles/{UND}/1d.csv, from 2024-10-31); before "
                     "that the next day's 08:00 UTC option settlement price (history/settlements, daily from March "
                     "2024); before that the day's contract-weighted index at perp trades (history/surface/{UND}.csv "
                     "'index'). price_src names which. Median gap to the candle close where both exist: 0.5% "
                     "(settlement) and 0.6% (index average) for BTC, 0.8% and 0.7% for ETH",
            "settle_0800": "Derive settlement price of options expiring that day at 08:00 UTC",
        },
        "columns": cols,
    }
    doc = {"meta": meta, "rows": rows_json}
    out.write_text(json.dumps(doc, separators=(",", ":")))
    (out.parent / "validation_balance.json").write_text(json.dumps(val_rows[-120:]))
    print("unvalued positions (group, und) summed over days:", dict(sorted(unvalued_total.items())))
    print(f"wrote {out} {out.stat().st_size} bytes, {len(rows_json)} rows x {len(cols)} cols, {time.time() - t0:.0f}s")



# ---------------------------------------------------------------------------
# The drawer's seed
# ---------------------------------------------------------------------------

SEED_COINS = ("BTC", "ETH", "ALL")
# Per coin, in this order: wallets net long and net short of the open book ($1,000 of delta or more) for the Smart
# wallets as ranked at each close (point in time) and as ranked today (hindsight), and the premium they paid on
# net new long puts that day (as ranked the close before, and today).
SEED_FIELDS = (("pit_long", "smart_pit", "o_wl"), ("pit_short", "smart_pit", "o_ws"), ("now_long", "smart", "o_wl"),
               ("now_short", "smart", "o_ws"), ("pit_puts", "smart_pit", "put_buy_open"),
               ("now_puts", "smart", "put_buy_open"))
TOP_WINDOW, TOP_FALL, TOP_AHEAD = 30, 0.15, 90


def tops(prices: list) -> list:
    """Days whose close is the highest within TOP_WINDOW days either side and was followed by a fall of TOP_FALL or
    more within TOP_AHEAD days. prices: [(day, close)] in order. Uses the closes after each day: it marks where
    the tops were, it does not find them."""
    out = []
    for i, (d, p) in enumerate(prices):
        near = [q for _, q in prices[max(0, i - TOP_WINDOW):i + TOP_WINDOW + 1]]
        ahead = [q for _, q in prices[i + 1:i + 1 + TOP_AHEAD]]
        if p >= max(near) and ahead and min(ahead) / p - 1 <= -TOP_FALL:
            out.append(d)
    return out


def seed(series: dict) -> dict:
    """The compact seed: one row a day, [day, btc, eth, then SEED_FIELDS for each of SEED_COINS]; days as days since
    1970 (a row's open book is at its 00:00 UTC close, as the market history days)."""
    cols = series["meta"]["columns"]
    ix = {c: i for i, c in enumerate(cols)}
    epoch = date(1970, 1, 1)
    rows = []
    for r in series["rows"]:
        day = (date.fromisoformat(r[0]) - epoch).days
        line = [day, r[ix["BTC.price"]], r[ix["ETH.price"]]]
        for coin in SEED_COINS:
            line += [r[ix[f"{g}.{coin}.{k}"]] for _, g, k in SEED_FIELDS]
        rows.append(line)
    price = lambda k: [(row[0], row[k]) for row in rows if row[k]]
    meta = series["meta"]
    return {
        "version": 1,
        "source": "Cowboy's records of Derive options trades (cianfru/derive_scan data branch), "
                  "backend/backtest/derive_smart_series.py",
        "first": rows[0][0], "through": rows[-1][0], "wallets_as_of": meta.get("wallets_as_of"),
        "smart_today": meta.get("group_sizes_today", {}).get("smart"),
        "coins": list(SEED_COINS),
        "fields": [f for f, _, _ in SEED_FIELDS],
        "columns": ["day", "btc", "eth"] + [f"{c}.{f}" for c in SEED_COINS for f, _, _ in SEED_FIELDS],
        "rows": rows,
        "tops": {"BTC": tops(price(1)), "ETH": tops(price(2))},
        "top_rule": {"window": TOP_WINDOW, "fall": TOP_FALL, "ahead": TOP_AHEAD},
    }


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["build", "seed"])
    ap.add_argument("src", help="build: the data branch copy; seed: the series JSON")
    ap.add_argument("dest", nargs="?", help="build: the series JSON to write")
    ap.add_argument("--derive-scan", default="../../derive_scan/backend", help="Cowboy's backend/ (build only)")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "seeds" / "derive_smart_seed.json"))
    a = ap.parse_args()
    if a.step == "build":
        _import_derive(a.derive_scan)
        build(Path(a.src), Path(a.dest))
    else:
        doc = seed(json.loads(Path(a.src).read_text()))
        Path(a.out).write_text(json.dumps(doc, separators=(",", ":")) + "\n")
        print(f"wrote {a.out}: {len(doc['rows'])} days, tops {doc['tops']}")
