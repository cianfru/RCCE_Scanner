// A wallet's avatar: a small abstract face drawn from the address, in the spirit of the
// "beam" avatars. A tilted body shape in one palette colour over a second colour, two eyes
// and a mouth whose shape, spread and angle come from the address hash. Pure data and an SVG
// string, no requests. The body colour is the wallet's colour (its chart markers use it too).

import { draw, walletSeed } from "./walletName.js";

// Mid-bright hues that read on the dark green-black theme and on white, kept off pure red and
// green so a wallet never looks like profit or loss. light: a deeper copy for marks drawn
// straight on a light background (chart markers).
export const AVATAR_PALETTE = [
  { c: "#5eead4", light: "#0f766e" }, // teal
  { c: "#38bdf8", light: "#0369a1" }, // sky
  { c: "#818cf8", light: "#4f46e5" }, // indigo
  { c: "#c084fc", light: "#7e22ce" }, // violet
  { c: "#f472b6", light: "#be185d" }, // pink
  { c: "#fb923c", light: "#c2410c" }, // orange
  { c: "#fbbf24", light: "#a16207" }, // amber
  { c: "#bef264", light: "#4d7c0f" }, // lime
  { c: "#e7c9a0", light: "#8a6a2f" }, // sand
  { c: "#94a3b8", light: "#475569" }, // slate
];
const INK_DARK = "#0b1411";
const INK_LIGHT = "#f4faf7";
export const AVATAR_VIEW = 36;

const range = (v, lo, hi) => lo + (v % (hi - lo + 1));
function luminance(hex) {
  const n = parseInt(hex.slice(1), 16);
  const ch = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map(v => {
    const s = v / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2];
}

// Everything the avatar needs, all from the address.
export function avatarSpec(address) {
  const seed = walletSeed(address);
  const r = k => draw(seed, 0x2545f491 * (k + 1));
  const P = AVATAR_PALETTE.length;
  const bodyI = r(0) % P;
  const bgI = (bodyI + 1 + (r(1) % (P - 1))) % P;       // never the body colour
  const body = AVATAR_PALETTE[bodyI].c;
  const bg = AVATAR_PALETTE[bgI].c;
  const ink = luminance(body) > 0.3 ? INK_DARK : INK_LIGHT;
  const t = r(2), f = r(3), m = r(4);
  // Shift the body off centre so a crescent of the background shows (at least 6 units).
  let tx = range(t >>> 1, -10, 10), ty = range(t >>> 6, -10, 10);
  if (Math.abs(tx) + Math.abs(ty) < 6) { tx = tx < 0 ? -6 : 6; ty = ty < 0 ? -3 : 3; }
  return {
    bg, body, ink,
    bodyLight: AVATAR_PALETTE[bodyI].light,
    round: (t & 1) === 1,                               // circle or rounded square
    tx, ty,
    rotate: range(t >>> 11, 0, 359),
    scale: 1 + range(t >>> 20, 0, 2) / 10,
    faceX: Math.round(tx / 3) + range(f, -1, 1), faceY: Math.round(ty / 3) + range(f >>> 2, -1, 1),
    faceRotate: range(f >>> 6, -12, 12),
    eyeSpread: range(f >>> 11, 5, 7),
    eyes: ["dot", "dot", "line", "wide"][(f >>> 14) & 3],
    mouth: ["smile", "open", "flat", "smile", "small"][m % 5],
    mouthWidth: range(m >>> 4, 7, 10),
  };
}

// The marks for one spec (shared by the SVG string and the React avatar).
export function avatarShapes(s) {
  const V = AVATAR_VIEW, h = V / 2;
  const cx = h + s.faceX, cy = h + s.faceY;
  const ey = cy - 3;
  const eyes = s.eyes === "line"
    ? [-1, 1].map(d => ({ tag: "line", x1: cx + d * s.eyeSpread - 2, x2: cx + d * s.eyeSpread + 2, y1: ey, y2: ey }))
    : [-1, 1].map(d => ({ tag: "circle", cx: cx + d * s.eyeSpread, cy: ey, r: s.eyes === "wide" ? 2.6 : 2 }));
  const w = s.mouthWidth, my = cy + 4.5;
  const mouth = s.mouth === "open"
    ? { tag: "path", d: `M${cx - w / 2} ${my} a${w / 2} ${w / 2.4} 0 0 0 ${w} 0 Z`, fill: true }
    : s.mouth === "flat"
    ? { tag: "line", x1: cx - w / 2, x2: cx + w / 2, y1: my + 1, y2: my + 1 }
    : s.mouth === "small"
    ? { tag: "circle", cx, cy: my + 1.5, r: 1.8 }
    : { tag: "path", d: `M${cx - w / 2} ${my} q${w / 2} ${w / 2.2} ${w} 0` };
  return {
    body: { x: 0, y: 0, width: V, height: V, rx: s.round ? V : 6,
      transform: `translate(${s.tx} ${s.ty}) rotate(${s.rotate} ${h} ${h}) translate(${h} ${h}) scale(${s.scale}) translate(${-h} ${-h})` },
    faceTransform: `rotate(${s.faceRotate} ${cx} ${cy})`,
    eyes, mouth,
  };
}

const n = v => (Number.isInteger(v) ? String(v) : v.toFixed(2));
function markup(el, ink) {
  const { tag, fill, ...a } = el;
  const attrs = Object.entries(a).map(([k, v]) => `${k}="${typeof v === "number" ? n(v) : v}"`).join(" ");
  const paint = tag === "circle" || fill ? `fill="${ink}"` : `fill="none" stroke="${ink}" stroke-width="2" stroke-linecap="round"`;
  return `<${tag} ${attrs} ${paint}/>`;
}

// A standalone SVG string (for places outside React).
export function avatarSvg(address, size = 28) {
  const s = avatarSpec(address);
  const sh = avatarShapes(s);
  const V = AVATAR_VIEW;
  const b = sh.body;
  const id = `wa${walletSeed(address).toString(36)}`;
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 ${V} ${V}">`
    + `<defs><clipPath id="${id}"><circle cx="${V / 2}" cy="${V / 2}" r="${V / 2}"/></clipPath></defs>`
    + `<g clip-path="url(#${id})"><rect width="${V}" height="${V}" fill="${s.bg}"/>`
    + `<rect x="0" y="0" width="${V}" height="${V}" rx="${b.rx}" transform="${b.transform}" fill="${s.body}"/>`
    + `<g transform="${sh.faceTransform}">${sh.eyes.map(e => markup(e, s.ink)).join("")}${markup(sh.mouth, s.ink)}</g></g></svg>`;
}

// The wallet's colour for marks drawn on the page itself (chart markers).
export const walletColor = (address, light = false) => {
  const s = avatarSpec(address);
  return light ? s.bodyLight : s.body;
};
