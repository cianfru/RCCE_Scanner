// Performance chart series (Portfolio v2, B6). Lightweight Charts spaces points by index, not by
// time, and Hyperliquid's history thins out unevenly (the month: daily points for three weeks, then
// one every ~9 h), so each period is resampled to one fixed step before it is drawn.

// Seconds per step: 1D at 30 min, 1W at 2 h, 1M at 6 h, All at one day.
export const PERIOD_STEP = { day: 1800, week: 7200, month: 21600, allTime: 86400 };

const clean = pts => (pts || []).filter(p => Number.isFinite(p?.time) && Number.isFinite(p?.value)).sort((a, b) => a.time - b.time);

// Linear interpolation on the multiples of `step` between the first and the last point, then the
// last point itself, so the line ends on the latest value (that final step is the only shorter one).
export function resample(points, step) {
  const pts = clean(points);
  if (pts.length < 2 || !(step > 0)) return pts;
  const t1 = pts[pts.length - 1].time;
  const out = [];
  let j = 0;
  for (let t = Math.ceil(pts[0].time / step) * step; t <= t1; t += step) {
    while (j < pts.length - 2 && pts[j + 1].time < t) j++;
    const a = pts[j], b = pts[j + 1];
    const k = b.time === a.time ? 1 : Math.max(0, Math.min(1, (t - a.time) / (b.time - a.time)));
    out.push({ time: t, value: a.value + (b.value - a.value) * k });
  }
  if (!out.length || out[out.length - 1].time < t1) out.push({ time: t1, value: pts[pts.length - 1].value });
  return out;
}

// The drawn point nearest a time (the Last visit line sits on an exact step), or null outside.
export function nearestPoint(points, t) {
  if (!points?.length || t == null || t < points[0].time) return null;
  let best = points[0];
  for (const p of points) if (Math.abs(p.time - t) < Math.abs(best.time - t)) best = p;
  return best;
}

// The highest and the lowest raw point (their true values), each placed on the nearest drawn step.
// The first raw point can sit before the first step (the grid starts on a multiple of the step), so
// an extreme there takes the first step rather than none.
export function extremes(raw, drawn) {
  const pts = clean(raw);
  if (pts.length < 2 || !drawn?.length) return null;
  const hi = pts.reduce((x, y) => (y.value > x.value ? y : x)), lo = pts.reduce((x, y) => (y.value < x.value ? y : x));
  const on = t => drawn.reduce((b, p) => (Math.abs(p.time - t) < Math.abs(b.time - t) ? p : b), drawn[0]).time;
  return { hi: { value: hi.value, time: on(hi.time) }, lo: { value: lo.value, time: on(lo.time) } };
}
