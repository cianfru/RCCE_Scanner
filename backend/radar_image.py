"""
A small picture of the Radar for the daily Telegram brief, drawn with Pillow.

The same map as the app: x is the stretch (the engine's z-score), y the profitable traders
net long on a symlog scale, bubble area the dollars they hold in the coin, the Early setups
box shaded, the coins with the most money labelled and the brief's early setups in accent.
Dark background as the app. Drawn at twice the size and scaled down for smooth edges.

Pillow is imported only here, only when a brief is drawn; ``render`` returns None when it is
missing or anything fails, and the brief goes out as text.
"""
from __future__ import annotations

import io
import logging
import math
from typing import Iterable, List, Optional

logger = logging.getLogger(__name__)

W, H = 800, 500
SS = 2                                    # supersampling factor
L, R, T, B = 46, 16, 34, 40
XS = (-2.5, 3.5)
BG = (4, 6, 12)
TEXT1 = (245, 254, 253)
TEXT3 = (245, 254, 253, 150)
AXIS = (151, 252, 228, 40)
ACCENT = (151, 252, 228)
STAGE = {"forming": (145, 185, 232), "fresh": (151, 252, 228), "running": (125, 155, 149),
         "stretched": (251, 191, 36), "leaving": (207, 145, 133), "waiting": (82, 82, 91)}
SHORT = (253, 164, 175)


def symlog(v: float) -> float:
    return math.copysign(math.log10(1 + abs(v)), v)


def _net(c: dict) -> int:
    t = c.get("traders") or {}
    return (t.get("pl") or 0) - (t.get("ps") or 0)


def _gross(c: dict) -> float:
    return (c.get("money") or {}).get("gross_usd") or 0


def _font(size: int):
    from PIL import ImageFont
    for name in ("DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    try:
        return ImageFont.load_default(size=size)
    except TypeError:                                  # Pillow < 10.1: fixed bitmap font
        return ImageFont.load_default()


def render(smap: dict, highlight: Iterable[str] = (), title: str = "", labels: int = 10) -> Optional[bytes]:
    """PNG bytes of the map, or None (no Pillow, no coins, or a drawing error)."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None
    try:
        return _draw(Image, ImageDraw, smap, list(highlight), title, labels)
    except Exception as exc:                           # a picture never blocks the brief
        logger.warning("radar image: %s", exc)
        return None


def _draw(Image, ImageDraw, smap: dict, highlight: List[str], title: str, labels: int) -> Optional[bytes]:
    coins = [c for c in smap.get("coins") or [] if c.get("zscore") is not None]
    if not coins:
        return None
    box = smap.get("box") or {"z": [-0.5, 1.5], "n": [1, 8]}
    s = SS
    w, h = W * s, H * s
    nets = [_net(c) for c in coins]
    y0, y1 = symlog(min(-4, *nets)), symlog(max(25, *nets)) + 0.06
    X = lambda z: (L + (max(XS[0], min(XS[1], z)) - XS[0]) / (XS[1] - XS[0]) * (W - L - R)) * s
    Y = lambda n: (T + (1 - (symlog(n) - y0) / (y1 - y0)) * (H - T - B)) * s

    img = Image.new("RGBA", (w, h), BG + (255,))
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    f_ax, f_lab, f_title = _font(11 * s), _font(12 * s), _font(13 * s)

    # axes and ticks
    for t in (-3, 0, 1, 3, 8, 20, 50):
        if y0 <= symlog(t) <= y1:
            yy = Y(t)
            d.line([(L * s, yy), ((W - R) * s, yy)], fill=AXIS if t else AXIS[:3] + (80,), width=s)
            d.text(((L - 6) * s, yy), f"+{t}" if t > 0 else str(t), font=f_ax, fill=TEXT3, anchor="rm")
    for z in (-2, -1, 0, 1, 2, 3):
        xx = X(z)
        d.line([(xx, T * s), (xx, (H - B) * s)], fill=AXIS[:3] + (22 if z else 60,), width=s)
        d.text((xx, (H - B + 8) * s), str(z), font=f_ax, fill=TEXT3, anchor="mt")
    d.text(((W - R) * s, (H - 8) * s), "Stretch (z-score)", font=f_ax, fill=TEXT3, anchor="rb")
    d.text((L * s, (T - 8) * s), "Profitable traders, net long", font=f_ax, fill=TEXT3, anchor="lb")
    if title:
        d.text(((W - R) * s, (T - 8) * s), title, font=f_title, fill=TEXT1[:3] + (210,), anchor="rb")

    # the Early setups box: shaded, dashed edge
    bx0, bx1, by0, by1 = X(box["z"][0]), X(box["z"][1]), Y(box["n"][1]), Y(box["n"][0])
    d.rectangle([bx0, by0, bx1, by1], fill=ACCENT + (18,))
    dash = 8 * s
    for x in range(int(bx0), int(bx1), dash * 2):
        for yy in (by0, by1):
            d.line([(x, yy), (min(x + dash, bx1), yy)], fill=ACCENT + (90,), width=s)
    for y in range(int(by0), int(by1), dash * 2):
        for xx in (bx0, bx1):
            d.line([(xx, y), (xx, min(y + dash, by1))], fill=ACCENT + (90,), width=s)
    d.text((bx0 + 6 * s, by0 + 5 * s), "Early setups", font=f_lab, fill=ACCENT + (230,), anchor="lt")
    img.alpha_composite(layer)

    # bubbles: area = dollars, largest drawn first
    G = max((_gross(c) for c in coins), default=0)
    rmax = 30
    radius = lambda c: 2.0 if not _gross(c) or not G else max(3.2, rmax * math.sqrt(_gross(c) / G))
    hl = set(highlight)
    layer.paste((0, 0, 0, 0), (0, 0, w, h))                                  # one overlay, reused: less memory
    d = ImageDraw.Draw(layer)
    for c in sorted(coins, key=lambda c: (c["coin"] in hl, -radius(c))):      # the brief's picks on top
        r = radius(c) * s
        cx, cy = X(c["zscore"]), Y(_net(c))
        if not _gross(c):
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(82, 82, 91, 150))
            continue
        col = ACCENT if c["coin"] in hl else STAGE.get(c.get("stage"), STAGE["waiting"])
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col + (95,), outline=col + (230,), width=max(1, s))
        if c["coin"] in hl:                                                    # a ring marks the picks
            q = r + 4 * s
            d.ellipse([cx - q, cy - q, cx + q, cy + q], outline=ACCENT + (200,), width=max(1, s))
        share = (c.get("money") or {}).get("net_long_share")
        if share is not None and 1 - share >= 0.02 and r >= 8 * s:          # the short share as a slice
            d.pieslice([cx - r + s, cy - r + s, cx + r - s, cy + r - s], -90, -90 + 360 * (1 - share),
                       fill=SHORT + (120,))
    img.alpha_composite(layer)

    # labels: the coins with the most money, plus the highlighted ones, without overlaps
    layer.paste((0, 0, 0, 0), (0, 0, w, h))
    d = ImageDraw.Draw(layer)
    top = sorted((c for c in coins if _gross(c)), key=lambda c: -_gross(c))[:labels]
    order = [c for c in coins if c["coin"] in hl] + [c for c in top if c["coin"] not in hl]
    tb = d.textbbox((bx0 + 6 * s, by0 + 5 * s), "Early setups", font=f_lab, anchor="lt")
    taken = [(tb[0] - 2, tb[1] - 2, tb[2] + 2, tb[3] + 2)]                    # the box's own label
    for c in order:
        r = (radius(c) + (4 if c["coin"] in hl else 0)) * s
        cx, cy = X(c["zscore"]), Y(_net(c))
        font = f_lab
        tw = d.textlength(c["coin"], font=font)
        th = 12 * s
        for ax, ay, anchor in ((cx + r + 3 * s, cy, "lm"), (cx - r - 3 * s, cy, "rm"),
                               (cx, cy - r - 3 * s, "mb"), (cx, cy + r + 3 * s, "mt")):
            x0 = ax if anchor[0] == "l" else ax - tw if anchor[0] == "r" else ax - tw / 2
            y0b = ay - th / 2 if anchor[1] == "m" else ay - th if anchor[1] == "b" else ay
            bb = (x0 - 2, y0b - 2, x0 + tw + 2, y0b + th + 2)
            if bb[0] < 0 or bb[2] > w or bb[1] < 0 or bb[3] > h:
                continue
            if any(bb[0] < o[2] and o[0] < bb[2] and bb[1] < o[3] and o[1] < bb[3] for o in taken):
                continue
            taken.append(bb)
            d.text((ax, ay), c["coin"], font=font, anchor=anchor,
                   fill=ACCENT + (255,) if c["coin"] in hl else TEXT1 + (220,))
            break
    img.alpha_composite(layer)

    del layer
    out = img.convert("RGB")
    del img
    out = out.resize((W, H), Image.LANCZOS)
    buf = io.BytesIO()
    out.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
