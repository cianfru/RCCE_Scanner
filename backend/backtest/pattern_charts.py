"""Render detected chart patterns on daily candles (research tooling for visual review).

    render(ohlcv, pattern, title, path)

Draws the candles around the pattern, its anchor pivots, the neckline and
boundaries, the bar at which the pattern became knowable ("formed") and the
bar at which it resolved (break, failure or expiry).
"""
from __future__ import annotations

from datetime import datetime, timezone

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from engines.patterns_engine import NAMES, Pattern  # noqa: E402

BG, FG, GRID = "#0b0b0d", "#d4d4d8", "#27272a"
UP, DOWN = "#34d399", "#f87171"
ACCENT, NECK, FORM = "#fbbf24", "#60a5fa", "#a78bfa"
KIND_LABEL = {"rect": "rectangle", "asc": "ascending triangle", "desc": "descending triangle",
              "hs": "head & shoulders", "ihs": "inverse head & shoulders", "cup": "cup & handle"}


def _date(ms: float) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def render(ohlcv: dict, p: Pattern, title: str, path, pad_before: int = 15, pad_after: int = 25) -> None:
    o, h, l, c, ts = (np.asarray(ohlcv[k], dtype=float) for k in ("open", "high", "low", "close", "timestamp"))
    end_ref = p.resolved if p.resolved is not None else p.formed
    a, b = max(0, p.start - pad_before), min(len(c), end_ref + pad_after + 1)
    x = np.arange(a, b)
    fig, ax = plt.subplots(figsize=(9, 4.6), dpi=110)
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    for i in x:
        col = UP if c[i] >= o[i] else DOWN
        ax.vlines(i, l[i], h[i], color=col, linewidth=0.7, alpha=0.8)
        ax.add_patch(plt.Rectangle((i - 0.35, min(o[i], c[i])), 0.7, max(abs(c[i] - o[i]), 1e-12),
                                   facecolor=col, edgecolor=col, linewidth=0.5))
    stop = p.resolved if p.resolved is not None else b - 1
    if p.kind == "rect":
        ax.hlines([p.upper, p.lower], p.start, stop, colors=NECK, linewidth=1.4, linestyles="-")
    else:
        ax.hlines(p.neckline, p.start, stop, colors=NECK, linewidth=1.6, label="neckline")
    ax_idx = [q[0] for q in p.anchors]
    ax_px = [q[1] for q in p.anchors]
    if p.kind in ("hs", "ihs", "cup"):
        ax.plot(ax_idx, ax_px, color=ACCENT, linewidth=1.1, alpha=0.9)
    elif p.kind in ("asc", "desc"):
        slope_side = [q for q in p.anchors if abs(q[1] / p.neckline - 1) > 0.015]
        if len(slope_side) >= 2:
            ax.plot([q[0] for q in slope_side], [q[1] for q in slope_side], color=ACCENT, linewidth=1.1)
    ax.scatter(ax_idx, ax_px, s=28, color=ACCENT, zorder=5, edgecolors=BG, linewidths=0.6)
    ax.axvline(p.formed, color=FORM, linewidth=1.0, linestyle="--")
    ax.text(p.formed, ax.get_ylim()[1], " formed", color=FORM, fontsize=8, va="top")
    if p.resolved is not None:
        col = UP if (p.code in (10, 11, 12, 13)) else DOWN if p.code else "#71717a"
        ax.axvline(p.resolved, color=col, linewidth=1.2)
        label = {"confirmed": "break", "failed": "failed", "expired": "expired"}[p.status]
        ax.text(p.resolved, ax.get_ylim()[0], f" {label}", color=col, fontsize=8, va="bottom")
    ticks = np.linspace(a, b - 1, 6).astype(int)
    ax.set_xticks(ticks)
    ax.set_xticklabels([_date(ts[i]) for i in ticks], color=FG, fontsize=8)
    ax.tick_params(axis="y", colors=FG, labelsize=8)
    for s in ax.spines.values():
        s.set_color(GRID)
    ax.grid(color=GRID, linewidth=0.5)
    name = NAMES.get(p.code) if p.code else KIND_LABEL[p.kind]
    ax.set_title(f"{title}  ·  {name}  ·  {p.status}", color=FG, fontsize=10, loc="left")
    ax.set_xlim(a - 1, b)
    fig.tight_layout()
    fig.savefig(path, facecolor=BG)
    plt.close(fig)
