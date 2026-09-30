// "as of HH:MM" for a feed the server served from its last good copy (backend/degrade.py):
// shown only when the body says it is stale and carries the time of its data.
const pad = n => String(n).padStart(2, "0");
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function asOfLabel(body, now = Date.now()) {
  if (!body || !body.stale) return null;
  const t = Number(body.as_of);
  if (!Number.isFinite(t) || t <= 0) return null;
  const d = new Date(t * 1000);
  const time = `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  const today = new Date(now);
  const sameDay = d.getFullYear() === today.getFullYear() && d.getMonth() === today.getMonth() && d.getDate() === today.getDate();
  return sameDay ? `as of ${time}` : `as of ${d.getDate()} ${MONTHS[d.getMonth()]} ${time}`;
}

// The stalest of several bodies (a page built from two feeds shows one note).
export function stalest(...bodies) {
  let out = null;
  for (const b of bodies) {
    if (!b?.stale || !Number.isFinite(Number(b.as_of)) || !b.as_of) continue;
    if (!out || Number(b.as_of) < Number(out.as_of)) out = b;
  }
  return out;
}
