"""
Chart patterns with a horizontal neckline (version ``patterns-1``) — research, shadow only.

The seven types Larsson's Pro tags, each on body pivots (max/min of open and
close) so they share Module B's anchors:

    10 rectangle breakout      bull  neckline = range top
    11 inverse head & shoulders bull  neckline = peaks between the three troughs
    12 cup & handle            bull  neckline = cup rims
    13 ascending triangle      bull  neckline = flat top
    20 rectangle breakdown     bear  neckline = range bottom
    21 head & shoulders        bear  neckline = troughs between the three peaks
    23 descending triangle     bear  neckline = flat bottom

Every pattern has a life cycle, evaluated on daily closes with completed data
only:

    forming    the geometry is complete (its last pivot is confirmed, i.e. n
               bars later) and the neckline has not broken yet
    confirmed  a close beyond the neckline by the buffer, in the pattern's
               direction (rectangles confirm either way: 10 up, 20 down)
    failed     a close through the opposite boundary first (e.g. above the head
               of a head & shoulders)
    expired    no break within ``max_wait`` bars of the last pivot

Detection runs when a new pivot is confirmed, and only patterns that include
that pivot are created, so a pattern is found once, at the first bar it is
knowable. Several patterns can confirm on the same bar (Pro packs such codes,
e.g. 11010 = inverse H&S + rectangle).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Sequence

import numpy as np

from engines.levels_engine import body_pivots

PATTERNS_VERSION = "patterns-1"
CODES = {"rect_up": 10, "ihs": 11, "cup": 12, "asc": 13, "rect_down": 20, "hs": 21, "desc": 23}
NAMES = {10: "rectangle breakout", 11: "inverse head & shoulders", 12: "cup & handle", 13: "ascending triangle",
         20: "rectangle breakdown", 21: "head & shoulders", 23: "descending triangle"}
BULL, BEAR = 1, -1


@dataclass(frozen=True)
class PatternConfig:
    n: int = 5                  # body-pivot half window (Module B default)
    tol: float = 0.015          # flat edge / neckline tolerance (Module B default)
    b: float = 0.01             # break buffer (Module B default)
    lookback: int = 250
    max_wait: int = 40          # bars after the last pivot for a forming pattern to break
    rect_min_bars: int = 20
    rect_height: tuple = (0.05, 0.60)
    tri_min_bars: int = 20
    tri_step: float = 0.01      # each rising low / falling high moves at least 1%
    hs_head: float = 0.05       # head beyond both shoulders by at least 5%
    hs_shoulders: float = 0.12  # shoulders within 12% of each other
    hs_symmetry: tuple = (0.5, 2.0)
    hs_bars: tuple = (30, 250)
    cup_min_bars: int = 20
    cup_depth: tuple = (0.12, 0.50)
    cup_round: float = 0.40     # share of cup bars in its bottom third. Spec: 0.30, but a
                                # straight-line V has exactly 1/3 there, so 0.30 cannot reject it.
    handle_bars: tuple = (5, 30)


@dataclass
class Pattern:
    kind: str                   # rect | asc | desc | hs | ihs | cup
    direction: int              # +1 bull, -1 bear, 0 either way (rectangle)
    neckline: float             # break level (rectangle: see upper / lower)
    invalidation: float         # a close beyond this (the other way) fails the pattern
    anchors: List[tuple]        # (bar, price) key points, oldest first
    start: int
    last_pivot: int
    formed: int                 # first bar at which the pattern is knowable
    upper: Optional[float] = None
    lower: Optional[float] = None
    status: str = "forming"
    resolved: Optional[int] = None
    code: Optional[int] = None

    @property
    def key(self):
        return (self.kind, round(self.neckline, 12), self.start)


def _cluster(points: Sequence[tuple], tol: float) -> List[List[tuple]]:
    pts = sorted(points, key=lambda p: p[1])
    out, cur = [], []
    for p in pts:
        if cur and p[1] > cur[0][1] * (1 + tol):
            out.append(cur)
            cur = []
        cur.append(p)
    if cur:
        out.append(cur)
    return [c for c in out if len(c) >= 2]


def _distinct(pivots: Sequence[tuple], n: int) -> List[tuple]:
    """One pivot per turn. A daily candle usually opens at the previous close, so the
    bodies on either side of a turn share the same extreme and both qualify as pivots.
    Two same-kind pivots within n bars can only be such ties; keep the first."""
    out, last = [], {}
    for p in sorted(pivots, key=lambda p: (p[0], p[2])):
        if p[2] in last and p[0] - last[p[2]] <= n:
            continue
        out.append(p)
        last[p[2]] = p[0]
    return out


class _Detector:
    def __init__(self, o, h, l, c, cfg: PatternConfig):
        self.cfg = cfg
        self.c = c
        self.top = np.maximum(o, c)
        self.bot = np.minimum(o, c)
        self.pivots = _distinct(body_pivots(o, c, cfg.n), cfg.n)

    def _contained(self, start, end, lo, hi) -> bool:
        seg = self.c[start:end]
        return len(seg) == 0 or (seg.min() >= lo and seg.max() <= hi)

    # ----------------------------------------------------------------- per type
    def rectangles(self, t, highs, lows, newest):
        cfg, out = self.cfg, []
        for R in _cluster(highs, cfg.tol):
            for S in _cluster(lows, cfg.tol):
                r, s = float(np.mean([p[1] for p in R])), float(np.mean([p[1] for p in S]))
                if not (cfg.rect_height[0] <= (r - s) / s <= cfg.rect_height[1]):
                    continue
                rt, st = [p[0] for p in R], [p[0] for p in S]
                if not (min(rt) < max(st) and min(st) < max(rt)):       # interleaved touches
                    continue
                if newest not in R and newest not in S:
                    continue
                start, last = min(rt + st), max(rt + st)
                if t - start < cfg.rect_min_bars:
                    continue
                if not self._contained(start, t, s * (1 - cfg.b), r * (1 + cfg.b)):
                    continue
                anchors = sorted([(p[0], p[1]) for p in R + S])
                out.append(Pattern("rect", 0, r, s, anchors, start, last, t, upper=r, lower=s))
        return out

    def triangles(self, t, highs, lows, newest):
        cfg, out = self.cfg, []
        for flat, others, kind in ((highs, lows, "asc"), (lows, highs, "desc")):
            for F in _cluster(flat, cfg.tol):
                f = float(np.mean([p[1] for p in F]))
                ft = sorted(p[0] for p in F)
                seq = sorted((p for p in others if p[0] >= ft[0] - 2 * cfg.n), key=lambda p: p[0])
                if len(seq) < 2:
                    continue
                if kind == "asc":
                    ok = all(b2[1] >= a[1] * (1 + cfg.tri_step) for a, b2 in zip(seq, seq[1:])) and seq[-1][1] < f
                else:
                    ok = all(b2[1] <= a[1] * (1 - cfg.tri_step) for a, b2 in zip(seq, seq[1:])) and seq[-1][1] > f
                if not ok or (newest not in F and newest not in seq):
                    continue
                start = min(ft[0], seq[0][0])
                last = max(ft[-1], seq[-1][0])
                if t - start < cfg.tri_min_bars:
                    continue
                # Contained between the first (widest) sloping pivot and the flat edge.
                lim = (seq[0][1] * (1 - cfg.b), f * (1 + cfg.b)) if kind == "asc" else (f * (1 - cfg.b), seq[0][1] * (1 + cfg.b))
                if not self._contained(start, t, *lim):
                    continue
                anchors = sorted([(p[0], p[1]) for p in list(F) + seq])
                inv = seq[-1][1]
                out.append(Pattern(kind, BULL if kind == "asc" else BEAR, f, inv, anchors, start, last, t))
        return out

    def head_shoulders(self, t, highs, lows, newest):
        cfg, out = self.cfg, []
        for peaks, troughs, kind in ((highs, lows, "hs"), (lows, highs, "ihs")):
            if newest not in peaks:
                continue
            rs = newest
            sign = 1 if kind == "hs" else -1          # hs: peaks are highs; ihs: mirror
            beyond = lambda a, b2, k: (a >= b2 * (1 + k)) if sign > 0 else (a <= b2 * (1 - k))
            earlier = [p for p in peaks if p[0] < rs[0]]
            for hd in earlier:
                if not beyond(hd[1], rs[1], cfg.hs_head):
                    continue
                for ls in earlier:
                    if ls[0] >= hd[0] or not beyond(hd[1], ls[1], cfg.hs_head):
                        continue
                    if abs(ls[1] - rs[1]) / min(ls[1], rs[1]) > cfg.hs_shoulders:
                        continue
                    ratio = (hd[0] - ls[0]) / max(rs[0] - hd[0], 1)
                    if not (cfg.hs_symmetry[0] <= ratio <= cfg.hs_symmetry[1]):
                        continue
                    if not (cfg.hs_bars[0] <= t - ls[0] <= cfg.hs_bars[1]):
                        continue
                    # the head must be the extreme of the whole span
                    span = self.top[ls[0]:rs[0] + 1] if sign > 0 else self.bot[ls[0]:rs[0] + 1]
                    if (span.max() > hd[1] * (1 + 1e-12)) if sign > 0 else (span.min() < hd[1] * (1 - 1e-12)):
                        continue
                    t1 = [p for p in troughs if ls[0] < p[0] < hd[0]]
                    t2 = [p for p in troughs if hd[0] < p[0] < rs[0]]
                    if not t1 or not t2:
                        continue
                    pick = min if sign > 0 else max
                    a, b2 = pick(t1, key=lambda p: p[1]), pick(t2, key=lambda p: p[1])
                    if abs(a[1] - b2[1]) / min(a[1], b2[1]) > cfg.tol:
                        continue
                    neck = (a[1] + b2[1]) / 2
                    lo, hi = (neck * (1 - cfg.b), hd[1]) if sign > 0 else (hd[1], neck * (1 + cfg.b))
                    if not self._contained(rs[0], t, lo, hi):
                        continue
                    anchors = [(ls[0], ls[1]), (a[0], a[1]), (hd[0], hd[1]), (b2[0], b2[1]), (rs[0], rs[1])]
                    out.append(Pattern(kind, BEAR if kind == "hs" else BULL, neck, hd[1], anchors, ls[0], rs[0], t))
        return out

    def cups(self, t, highs, newest):
        cfg, out = self.cfg, []
        if newest not in highs:
            return out
        right = newest
        for left in highs:
            if left[0] >= right[0] or right[0] - left[0] < cfg.cup_min_bars:
                continue
            if abs(left[1] - right[1]) / min(left[1], right[1]) > cfg.tol:
                continue
            rim = (left[1] + right[1]) / 2
            inner_top = self.top[left[0] + 1:right[0]]
            inner_bot = self.bot[left[0] + 1:right[0]]
            if len(inner_bot) == 0 or inner_top.max() > rim * (1 + cfg.tol):
                continue
            bottom = float(inner_bot.min())
            depth = (rim - bottom) / rim
            if not (cfg.cup_depth[0] <= depth <= cfg.cup_depth[1]):
                continue
            if np.mean(inner_bot <= bottom + (rim - bottom) / 3) < cfg.cup_round:
                continue
            handle_floor = rim - (rim - bottom) / 3
            if not self._contained(right[0], t, handle_floor, rim * (1 + cfg.b)):
                continue
            j = int(left[0] + 1 + np.argmin(inner_bot))
            anchors = [(left[0], left[1]), (j, bottom), (right[0], right[1])]
            out.append(Pattern("cup", BULL, rim, handle_floor, anchors, left[0], right[0], t))
        return out


def detect_patterns(ohlcv: Dict[str, np.ndarray], cfg: PatternConfig = PatternConfig()) -> List[Pattern]:
    """Every pattern in the series with its full life cycle (causal: bar i uses bars <= i)."""
    o, h, l, c = (np.asarray(ohlcv[k], dtype=np.float64) for k in ("open", "high", "low", "close"))
    det = _Detector(o, h, l, c, cfg)
    by_confirm: Dict[int, List[tuple]] = {}
    for p in det.pivots:
        by_confirm.setdefault(p[0] + cfg.n + 1, []).append(p)
    known: List[tuple] = []
    active: List[Pattern] = []
    done: List[Pattern] = []
    seen = set()
    for i in range(len(c)):
        # 1. resolve active patterns on this close
        still = []
        for pt in active:
            if i <= pt.formed - 1:
                still.append(pt)
                continue
            up, dn = c[i], c[i]
            prev = c[i - 1] if i > 0 else c[i]
            res = None
            if pt.kind == "rect":
                if up > pt.upper * (1 + cfg.b) >= prev:
                    res = ("confirmed", CODES["rect_up"])
                elif dn < pt.lower * (1 - cfg.b) <= prev:
                    res = ("confirmed", CODES["rect_down"])
            elif pt.direction == BULL:
                if up > pt.neckline * (1 + cfg.b):
                    res = ("confirmed", CODES[pt.kind])
                    if pt.kind == "cup" and not (cfg.handle_bars[0] <= i - pt.last_pivot <= cfg.handle_bars[1]):
                        res = ("failed", None)            # no handle, or a handle that ran too long
                elif dn < pt.invalidation * (1 - cfg.b):
                    res = ("failed", None)
            else:
                if dn < pt.neckline * (1 - cfg.b):
                    res = ("confirmed", CODES[pt.kind])
                elif up > pt.invalidation * (1 + cfg.b):
                    res = ("failed", None)
            if res is None and i - pt.last_pivot > (cfg.handle_bars[1] if pt.kind == "cup" else cfg.max_wait):
                res = ("expired", None)
            if res is None:
                still.append(pt)
            else:
                pt.status, pt.code, pt.resolved = res[0], res[1], i
                done.append(pt)
        active = still
        # 2. detect new patterns when pivots are confirmed at this bar
        new = by_confirm.get(i, [])
        if not new:
            continue
        known.extend(new)
        recent = [p for p in known if p[0] >= i - cfg.lookback]
        highs = [p for p in recent if p[2] == "H"]
        lows = [p for p in recent if p[2] == "L"]
        for newest in new:
            found = (det.rectangles(i, highs, lows, newest) + det.triangles(i, highs, lows, newest)
                     + det.head_shoulders(i, highs, lows, newest) + det.cups(i, highs, newest))
            for pt in found:
                dup = any(a.kind == pt.kind and abs(a.neckline / pt.neckline - 1) <= cfg.tol for a in active)
                if pt.key in seen or dup:
                    continue
                seen.add(pt.key)
                active.append(pt)
    for pt in active:
        pt.status = "forming"
    return done + active


def breaks_by_bar(patterns: Sequence[Pattern]) -> Dict[int, List[int]]:
    """Confirmed pattern codes per bar, for attaching to level events."""
    out: Dict[int, List[int]] = {}
    for p in patterns:
        if p.status == "confirmed":
            out.setdefault(p.resolved, []).append(p.code)
    return out


def pack(codes: Sequence[int]) -> int:
    """Pro-style packed code for simultaneous patterns (first x 1000 + second)."""
    codes = list(codes)
    return codes[0] if len(codes) == 1 else codes[0] * 1000 + codes[1]


def pattern_dict(p: Pattern) -> dict:
    d = asdict(p)
    d["name"] = NAMES.get(p.code) if p.code else None
    return d


# Measured track record of patterns-1 (docs/reviews/larsson-study.md, run patterns_w1-9:
# 40 coins, Binance spot daily, patterns formed and resolved 2021-10-21 to 2026-03-29).
# "forming" is what happened to patterns once seen forming; "after" is the return 20 bars
# after a confirmed break (entry next open) against plain breakouts without a pattern.
TRACK_RECORD = {
    "rect": {"forming": "Breaks 84% of the time: up 44%, down 40%, so the direction is a coin flip.",
             "after_up": "After an upside break: +9.6% at 20 bars, not better than a plain breakout (+5.1%) beyond noise.",
             "after_down": "After a downside break: no edge as a short (+0.2% at 20 bars)."},
    "asc": {"forming": "Confirms 36%, fails 62%.",
            "after": "After the break: -4.8% at 20 bars, significantly worse than a plain breakout."},
    "desc": {"forming": "Confirms 47%, fails 51%.",
             "after": "After the break: no edge as a short (-1.1% at 20 bars)."},
    "hs": {"forming": "Confirms 76%, fails 6%.",
           "after": "After the break: no edge as a short; price was 9% higher on average 40 bars later."},
    "ihs": {"forming": "Confirms 36%, fails 21%, expires 43%.",
            "after": "After the break: +17.9% at 20 bars on only 20 cases, within noise."},
    "cup": {"forming": "Confirms 33%, fails 67%.",
            "after": "After the break: +8.2% at 20 bars, within noise."},
}
SHORT_NAMES = {"rect": "Rectangle", "asc": "Asc triangle", "desc": "Desc triangle",
               "hs": "H&S", "ihs": "Inv H&S", "cup": "Cup & handle"}


def track_record(p: Pattern) -> str:
    tr = TRACK_RECORD[p.kind]
    if p.status != "confirmed":
        return tr["forming"]
    if p.kind == "rect":
        return tr["after_up" if p.code == CODES["rect_up"] else "after_down"]
    return tr["after"]


def chart_patterns(ohlcv: Dict[str, np.ndarray], recent: int = 180) -> List[dict]:
    """Patterns for the terminal chart: forming, confirmed or failed within the last
    ``recent`` bars (expired ones are left out). Display only; times in unix seconds."""
    ts = np.asarray(ohlcv["timestamp"], dtype=np.float64)
    n = len(ts)
    t = lambda i: int(ts[min(i, n - 1)] / 1000)
    out = []
    for p in detect_patterns(ohlcv):
        end = p.resolved if p.resolved is not None else n - 1
        if p.status == "expired" or end < n - recent:
            continue
        if p.kind == "rect":
            levels = [p.upper, p.lower]
        else:
            levels = [p.neckline]
        direction = p.direction
        if p.kind == "rect" and p.status == "confirmed":
            direction = BULL if p.code == CODES["rect_up"] else BEAR
        out.append({
            "kind": p.kind, "name": SHORT_NAMES[p.kind], "status": p.status, "direction": direction,
            "code": p.code, "levels": [float(v) for v in levels], "invalidation": float(p.invalidation),
            "anchors": [{"time": t(i), "value": float(v)} for i, v in p.anchors],
            "start": t(p.start), "formed": t(p.formed), "end": t(end),
            "track_record": track_record(p),
        })
    return out
