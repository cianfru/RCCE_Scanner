// Wallet accounts, the pure parts (tested in account.test.js). The store and the sign-in
// live in ../account.js; the backend is accounts_api.py.

// API paths that carry the account session. Everything else stays a plain request, so
// shared reads keep caching the same for everyone.
const SESSION_PATHS = [
  /^\/api\/me(\/|$)/,
  /^\/api\/auth\/wallet\//,
  /^\/api\/setup-map(\/ladder|\/watch)?$/,
  /^\/api\/setup-map\/watch\//,
  /^\/api\/traders\/0x[0-9a-fA-F]{40}(\/|$)/,
  /^\/api\/hyperlens\/followed(\/|$)/,
];

export function sendsSession(url, apiBase) {
  if (typeof url !== "string" || !url.startsWith(apiBase)) return false;
  const path = url.slice(apiBase.length).split("?")[0];
  return SESSION_PATHS.some(re => re.test(path));
}

export const shortAddress = a => (typeof a === "string" && a.length > 10 ? `${a.slice(0, 6)}…${a.slice(-4)}` : a || "");

// A refusal from the server: "holder" (a feature for token holders), "signin" or null.
export function refusal(status, detail) {
  if (status !== 403) return null;
  if (detail === "holder") return "holder";
  if (typeof detail === "string" && /sign in/i.test(detail)) return "signin";
  return null;
}

// The (i) text behind a locked feature.
export const LOCK_TITLE = "For Reflex token holders";
export function lockHelp(me) {
  const lines = ["Hold the Reflex token on Hyperliquid and sign in with that wallet (the button in the header)."];
  if (me && me.address && me.tier === "free") lines.push("This wallet does not hold enough of the token. Balances are read every 10 minutes.");
  return lines;
}

// The Radar's line while it shows the delayed map.
export function delayedLine(data) {
  if (!data?.delayed) return null;
  const min = data.delay_min || 60;
  if (!data.as_of) return `Delayed ${min} min · no map that old yet`;
  const d = new Date(data.as_of * 1000);
  const hh = String(d.getHours()).padStart(2, "0"), mm = String(d.getMinutes()).padStart(2, "0");
  return `Delayed ${min} min · as of ${hh}:${mm}`;
}

// UTF-8 text as 0x hex, for personal_sign.
export function toHex(text) {
  const bytes = new TextEncoder().encode(String(text));
  let out = "0x";
  for (const b of bytes) out += b.toString(16).padStart(2, "0");
  return out;
}

// Quiet hours presets, cycled from the account menu (null: off).
export const QUIET_PRESETS = [["23:00", "07:30"], ["22:00", "08:00"], ["00:00", "07:00"], null];
export function nextQuiet(cur) {
  const i = QUIET_PRESETS.findIndex(q => (q === null ? cur == null : !!cur && q[0] === cur[0] && q[1] === cur[1]));
  return QUIET_PRESETS[(i + 1) % QUIET_PRESETS.length];
}
export const quietText = q => (q ? `${q[0]}–${q[1]}` : "off");
