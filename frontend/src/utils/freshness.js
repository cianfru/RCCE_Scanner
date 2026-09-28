// How fresh the scanner's data is, for the header clock (components/FreshnessClock.jsx).
//
// The backend re-synthesises every IDLE_SYNTHESIS_S = 300 seconds (backend/main.py) even when
// idle, so data 900s old means three missed syntheses in a row: something is stuck.
export const STALE_S = 900;

// lastRefresh: when this browser last received data (Date or ms). cacheAge: how old the
// server's cache was at that moment, in seconds. The data itself dates from their difference.
// Returns { state: "live" | "stale" | "down" | null, dataTime: Date | null, ageS, ageLabel }.
// state is null while nothing has arrived yet (nothing to show).
export function freshness({ lastRefresh, cacheAge, error, now = Date.now() }) {
  const received = lastRefresh == null ? null : +new Date(lastRefresh);
  const valid = received != null && Number.isFinite(received);
  const lag = Number.isFinite(cacheAge) && cacheAge > 0 ? cacheAge * 1000 : 0;
  const dataTime = valid ? new Date(received - lag) : null;
  const ageS = dataTime ? Math.max(0, Math.floor((+new Date(now) - +dataTime) / 1000)) : null;
  const state = error ? "down" : ageS == null ? null : ageS >= STALE_S ? "stale" : "live";
  return { state, dataTime, ageS, ageLabel: ageS == null ? "" : ageShort(ageS) };
}

// "now", "2m", "3h", "2d": the short age after the clock ("Updated 15:31 · 2m").
export function ageShort(s) {
  if (!Number.isFinite(s) || s < 60) return "now";
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h`;
  return `${Math.floor(s / 86400)}d`;
}

// "just now", "1 minute ago", "12 minutes ago", "2 hours ago": for tooltips and screen readers.
export function ageLong(s) {
  if (!Number.isFinite(s) || s < 60) return "just now";
  const [n, unit] = s < 3600 ? [Math.floor(s / 60), "minute"] : s < 86400 ? [Math.floor(s / 3600), "hour"] : [Math.floor(s / 86400), "day"];
  return `${n} ${unit}${n === 1 ? "" : "s"} ago`;
}

// 24-hour clock, "15:31" or "15:31:34", independent of the browser locale.
export function clockLabel(date, seconds = false) {
  if (!date) return "";
  const d = new Date(date);
  const p = n => String(n).padStart(2, "0");
  return `${p(d.getHours())}:${p(d.getMinutes())}${seconds ? `:${p(d.getSeconds())}` : ""}`;
}

// The texts the clock shows, by viewport width (spec 2.5): long at 1280+, medium below,
// and the tooltip / accessible name.
export function freshnessText(f) {
  if (!f?.dataTime) return { long: "", medium: "", title: "", aria: "" };
  const hm = clockLabel(f.dataTime), age = ageShort(f.ageS);
  const ago = ageLong(f.ageS);
  return {
    long: `Updated ${hm} · ${age}`,
    medium: `${hm} · ${age}`,
    title: `Last scan ${clockLabel(f.dataTime, true)}, ${ago}${f.state === "stale" ? " (late)" : f.state === "down" ? " (feed unavailable)" : ""}`,
    aria: `Updated ${ago}`,
  };
}
