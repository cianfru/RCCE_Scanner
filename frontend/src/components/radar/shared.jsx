import { col, isLightMode } from "../../theme.js";
import { CROWD_WORD } from "../../utils/setupMap.js";

// Colours and small marks shared by the Radar map, its picks, rail and sheet, and the
// scanner's Radar strip (moved unchanged from the former SetupMap.jsx).
export const STAGE_COLOR = { forming: "#91b9e8", fresh: "#97FCE4", running: "#7d9b95", stretched: "#fbbf24", leaving: "#cf9185", waiting: "#52525b" };
export const CROWD_COLOR = { quiet: "var(--t-text3)", early: "var(--t-accent)", crowded: "#fbbf24", against: "#cf9185", holding: "var(--t-text2)" };
export const ZONE_COLOR = { watch: "var(--t-accent)", late: "#fbbf24", crowded: "#fbbf24", quiet: "var(--t-text3)", outside: "var(--t-text3)" };
export const XS = [-2.5, 3.5];
export const RM = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
export const store = { get: k => { try { return localStorage.getItem(k); } catch { return null; } }, set: (k, v) => { try { localStorage.setItem(k, v); } catch { /* private mode */ } } };
// Light theme: Leaving turns rose, so it no longer reads as Stretched's amber (#b4533f against
// #b45309); Running stays a quiet grey-green (col), the background of the map.
const STAGE_LIGHT = { leaving: "#9f3a4a" };
export const stageColor = k => (isLightMode() && STAGE_LIGHT[k]) || col(STAGE_COLOR[k] || STAGE_COLOR.waiting);
export const sc = c => stageColor(c.stage);
export const crowdColor = k => col(CROWD_COLOR[k] || CROWD_COLOR.holding);
export const zoneColor = z => col(ZONE_COLOR[z] || ZONE_COLOR.outside);
export const hrs = s => { const h = Math.max(0, Math.round(s / 3600)); return h < 48 ? `${h}h` : `${Math.round(h / 24)}d`; };
export const signed = n => `${n > 0 ? "+" : ""}${n}`;

// A close's time in the viewer's time zone with fixed English names: "Wed 24 Sep" on 1D,
// "Wed 16:00" on 4H (toLocaleString would give "Wed, 24 Sept" in en-GB).
const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export function stepLabel(tSec, tf) {
  const d = new Date(tSec * 1000);
  const two = n => String(n).padStart(2, "0");
  return tf === "1d" ? `${WEEKDAYS[d.getDay()]} ${d.getDate()} ${MONTHS[d.getMonth()]}` : `${WEEKDAYS[d.getDay()]} ${two(d.getHours())}:${two(d.getMinutes())}`;
}

export const STAR_TIP = "Starred: pinned to the top of the scanner and scanned more often. Telegram opportunity alerts include starred coins.";
export const WATCH_TIP = "Watching: Telegram message when it enters Early setups or the entry zone, or gets an exit signal; other changes appear in the daily brief.";

export function Crowd({ k }) {
  return k ? <b className="smap-crowd" style={{ color: crowdColor(k) }}>{CROWD_WORD[k]}</b> : null;
}

// The map's watch marker: a small downward triangle.
export function Pin({ size = 8, color = "var(--t-text1)", title }) {
  return <svg className="radar-pin" width={size + 2} height={size} viewBox="0 0 10 8" role={title ? "img" : undefined} aria-hidden={title ? undefined : "true"} aria-label={title}>
    <path d="M1,1 L9,1 L5,7 Z" fill={color} />
  </svg>;
}

// Watch on buttons and beside words: the map's pin on a short stem, in accent, centred on the
// text, so it reads as a pin and never as a menu caret (a bare triangle before a word does).
export function WatchMark({ color = "var(--t-accent)" }) {
  return <svg className="radar-watchmark" width="10" height="13" viewBox="0 0 10 13" aria-hidden="true">
    <path d="M1,1 L9,1 L5,6.5 Z" fill={color} />
    <path d="M5,6 L5,12" stroke={color} strokeWidth="1.5" strokeLinecap="round" />
  </svg>;
}

// Forming coins: one square per candle the regime change needs, filled as they close.
export function Progress({ t }) {
  return <span className="regime-progress">{Array.from({ length: t.need }, (_, k) => <i key={k} style={k < Math.min(t.seen, t.need)
    ? { background: STAGE_COLOR.forming, borderColor: STAGE_COLOR.forming } : { borderColor: `${STAGE_COLOR.forming}80` }} />)}</span>;
}
