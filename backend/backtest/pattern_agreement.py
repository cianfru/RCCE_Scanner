"""
Agreement of the frozen pattern detector (patterns-1) with Larsson Pro's pattern tags.

    python -m backtest.pattern_agreement --out pattern_agreement      (from backend/)

Diagnostic only, never an optimisation target. Pro's tags (private file, 15 Apr -
16 Sep 2026) sit inside the study's holdout window, so this reports agreement and
nothing about returns. A tag is matched when the detector confirms a pattern of the
same family on the same pair within +-1 day and, where Pro's level is known, with
its neckline within 1% of that level.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from backtest import binance_history as bh
from backtest.larsson_study import RUNS_DIR
from engines.patterns_engine import detect_patterns

PRIVATE = Path(__file__).resolve().parent.parent / "data" / "private"
FAMILY = {"rect": "rect", "hs": "hs", "ihs": "hs", "cup": "cup_handle", "asc": "triangle", "desc": "triangle"}
DAY = 86_400_000


def _ms(d):
    return int(datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)


def run():
    tags = [r for r in csv.DictReader((PRIVATE / "larsson_pattern_history.csv").open()) if r["side"] == "U"]
    levels = {(r["date"], r["pair"]): float(r["level"]) for r in csv.DictReader((PRIVATE / "larsson_level_history.csv").open())}
    lo, hi = _ms(min(t["date"] for t in tags)), _ms(max(t["date"] for t in tags)) + DAY
    by_pair = defaultdict(list)
    for t in tags:
        by_pair[t["pair"]].append(t)
    matched, ours_total, ours_matched, missing = [], 0, 0, []
    for pair, ts_ in by_pair.items():
        try:
            d = bh.load(pair, "1d", "2024-06-01", "2026-09-25")
        except Exception:
            d = None
        if d is None or len(d["close"]) < 80:
            missing.append(pair)
            continue
        pats = [p for p in detect_patterns(d) if p.status == "confirmed" and lo - DAY <= d["timestamp"][p.resolved] <= hi + DAY]
        ours_total += len(pats)
        hit_ours = set()
        for t in ts_:
            day = _ms(t["date"])
            lvl = levels.get((t["date"], pair))
            hit = None
            for k, p in enumerate(pats):
                if FAMILY[p.kind] != t["pattern"] or abs(d["timestamp"][p.resolved] - day) > DAY:
                    continue
                neck = p.upper if p.code == 10 else p.lower if p.code == 20 else p.neckline
                if lvl is not None and abs(neck / lvl - 1) > 0.01:
                    continue
                hit = k
                break
            matched.append({"date": t["date"], "pair": pair, "pattern": t["pattern"], "matched": hit is not None,
                            "any_confirmed_same_day": any(abs(d["timestamp"][p.resolved] - day) <= DAY for p in pats)})
            if hit is not None:
                hit_ours.add(hit)
        ours_matched += len(hit_ours)
    by_family = defaultdict(lambda: [0, 0])
    for m in matched:
        by_family[m["pattern"]][0] += m["matched"]
        by_family[m["pattern"]][1] += 1
    return {
        "pro_tags_usd": len(tags), "pairs_without_data": missing,
        "recall": sum(m["matched"] for m in matched) / len(matched) if matched else None,
        "recall_any_pattern_same_day": sum(m["any_confirmed_same_day"] for m in matched) / len(matched) if matched else None,
        "precision": ours_matched / ours_total if ours_total else None,
        "detector_confirmed_on_these_pairs": ours_total,
        "by_family": {k: {"matched": a, "tags": b} for k, (a, b) in by_family.items()},
        "tags": matched,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    out = RUNS_DIR / args.out
    if out.exists():
        ap.error("results are never overwritten")
    res = run()
    out.mkdir(parents=True)
    (out / "summary.json").write_text(json.dumps(res, indent=1))
    print(json.dumps({k: v for k, v in res.items() if k != "tags"}, indent=1))


if __name__ == "__main__":
    main()
