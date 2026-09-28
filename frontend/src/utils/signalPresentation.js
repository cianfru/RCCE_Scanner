// Presentation only: never changes eligibility, engine scores, or signal output.
export function signalDirection(signal) {
  if (['STRONG_LONG', 'LIGHT_LONG', 'ACCUMULATE', 'REVIVAL_SEED', 'REVIVAL_SEED_CONFIRMED'].includes(signal)) return 'bullish';
  if (['STRONG_SHORT', 'LIGHT_SHORT'].includes(signal)) return 'bearish';
  return null; // Exit instructions are not short entries.
}

export function friendlyReason(text = '') {
  return String(text).replace(/core context unavailable/gi, 'Required market context is missing; Strong Long is unavailable')
    .replace(/final eligibility cap/gi, 'Entry restrictions applied')
    .replace(/final eligibility:/gi, 'Entry restriction:')
    .replace(/\w+ LIGHT_LONG demoted: no CVD\/spot confirmation.*/, 'Held at Accumulate: no taker-buying confirmation')
    // Engine win-rate notes come from small in-sample tallies; they are not a forecast.
    .replace(/\s*\(\d+(\.\d+)?% WR[^)]*\)/g, '');
}

// Engine reason strings ("MARKUP + z=2.14 + conf=100% + consensus=RISK-ON [8/9 cond, ...]")
// in plain words, for places that show one position's rationale (the executor rows).
const REGIME_WORDS = {MARKUP:'Uptrend', BLOWOFF:'Overheated', REACC:'Re-accumulating', MARKDOWN:'Downtrend',
  CAP:'Capitulation', ACCUM:'Accumulation', ABSORBING:'Absorbing', FLAT:'Flat'};
const regimeWord = r => REGIME_WORDS[r] || r;
const lowerWords = v => String(v).replace(/_/g, ' ').toLowerCase();
const sentence = t => t ? t[0].toUpperCase() + t.slice(1) : t;

function zWords(z) {
  const a = Math.abs(z), side = z >= 0 ? 'above' : 'below';
  if (a < 1) return 'Near its mean';
  return `${a >= 2 ? 'Stretched' : 'Trading'} ${side} its mean`;
}

function termWords(term) {
  const kv = /^([A-Za-z]+)=(.+)$/.exec(term);
  if (!kv) return REGIME_WORDS[term] ? regimeWord(term) : sentence(lowerWords(term));
  const [, k, v] = kv;
  const trend = /^([A-Z]+)\((\d+%)\)$/.exec(v);
  switch (k.toLowerCase()) {
    case 'z': return Number.isFinite(+v) ? zWords(+v) : null;
    case 'conf': return `${v} regime confidence`;
    case 'confidence': return `${v} confidence`;
    case 'consensus': return `Market ${lowerWords(v).replace('risk on', 'risk-on').replace('risk off', 'risk-off')}`;
    case 'heat': return `Heat ${v}`;
    case 'div': return /BEAR/.test(v) ? 'Bearish divergence' : /BULL/.test(v) ? 'Bullish divergence' : `Divergence ${lowerWords(v)}`;
    case 'funding': return `${sentence(lowerWords(v))} funding`;
    case 'oi': return `Open interest ${lowerWords(v)}`;
    case 'vs': return null; // volatility scaling of the engine's own thresholds, not a reading
    case 'wallets': return trend ? `Tracked wallets ${trend[1].toLowerCase()} (${trend[2]})` : `Tracked wallets ${lowerWords(v)}`;
    case 'whales': return trend ? `Whales ${trend[1].toLowerCase()} (${trend[2]})` : `Whales ${lowerWords(v)}`;
    case 'f&g': return `Fear & Greed ${v}`;
    default: return `${sentence(lowerWords(k))} ${lowerWords(v)}`;
  }
}

function tagWords(tag) {
  let m;
  if ((m = /^(\d+)\/(\d+) cond/.exec(tag))) return `${m[1]} of ${m[2]} entry checks`;
  if ((m = /^(\d+)\/(\d+) raw\b/.exec(tag))) return `${m[1]} of ${m[2]} entry checks`;
  if ((m = /^([\d.]+)\/([\d.]+) effective(?: \((\d+)%\))?(.*)$/.exec(tag))) {
    const pct = m[3] ?? Math.round(100 * m[1] / m[2]);
    return `Entry checks ${pct}%${/insufficient/.test(m[4]) ? ', not enough for an entry' : ''}`;
  }
  if ((m = /^([A-Z]+) downgrade:/.exec(tag))) return `Outside the strict ${regimeWord(m[1]).toLowerCase()} entry band`;
  if ((m = /^([A-Z]+) extended$/.exec(tag))) return `${regimeWord(m[1])} extended`;
  if (/no CVD demand/.test(tag)) return 'No taker-buying demand: held at Accumulate';
  if (/\+ CVD demand/.test(tag)) return 'Taker-buying demand confirmed';
  if (/^downgraded: /.test(tag)) return sentence(tag.replace(/^downgraded: /, 'downgraded: '));
  if (/tracked_wallets_bullish/.test(tag)) return 'Upgraded: tracked wallets bullish';
  if (/tracked_wallets_loading/.test(tag)) return 'Tracked wallets accumulating';
  if ((m = /^ACCUM \+ F&G=(\d+)/.exec(tag))) return `Fear & Greed ${m[1]}`;
  if ((m = /^CAP revival \+ F&G=(\d+)/.exec(tag))) return `Capitulation revival, Fear & Greed ${m[1]}`;
  if ((m = /^absorption in ([A-Z]+)/.exec(tag))) return `Absorption in ${regimeWord(m[1]).toLowerCase()}`;
  if (/^CAP absorption/.test(tag)) return 'Capitulation absorption';
  if (/macro blocked bear rally short/.test(tag)) return 'Bear-rally short while longs are blocked';
  if ((m = /^cvd:\s*(.*)$/.exec(tag))) return `Taker flow: ${lowerWords(m[1]).replace(/\bcvd\s*/g, '').replace(/\s*\+\s*/g, ' with ')
    .replace(/\s*→\s*accum\w*/g, ', upgraded to Accumulate').replace(/\s*→\s*(up|down)grade/g, ', $1graded')}`;
  if ((m = /^([A-Z]+) \+ ([A-Z-]+)$/.exec(tag))) return `${regimeWord(m[1])} with market ${lowerWords(m[2])}`;
  if ((m = /^regime chop: (\d+) changes\/(\d+)d.*capped (\w+)/.exec(tag))) return `Regime flipped ${m[1]} times in ${m[2]} days: capped at ${signalWords(m[3])}`;
  return sentence(cleanEngineText(tag));
}

const SIGNAL_WORDS = {STRONG_LONG:'Strong long', LIGHT_LONG:'Light long', ACCUMULATE:'Accumulate', REVIVAL_SEED_CONFIRMED:'Revival confirmed',
  REVIVAL_SEED:'Revival', WAIT:'Wait', TRIM_HARD:'Trim hard', TRIM:'Trim', RISK_OFF:'Risk-off', NO_LONG:'No long',
  LIGHT_SHORT:'Light short', STRONG_SHORT:'Strong short'};
const signalWords = s => SIGNAL_WORDS[s] || lowerWords(s);

// Leftover engine notation: key=value pairs, snake_case and σ-vs-history notes.
function cleanEngineText(t) {
  return String(t)
    .replace(/^(\[(Agent|inertia)\]\s*)+/i, '')
    .replace(/\s*\((?:z=[^)]*|[^)]*σ vs history)\)/g, '')
    .replace(/\bBEAR-DIV\b/g, 'Bearish divergence').replace(/\bBULL-DIV\b/g, 'Bullish divergence')
    .replace(/,\s*ratio=[-+\d.]+/g, '')
    .replace(/\s*\|\s*confirmed:\s*/gi, ' · confirmed on ')
    .replace(/\s*\|\s*/g, ' · ')
    .replace(/\b(hyperliquid|binance|bybit|okx)\b/g, w => w[0].toUpperCase() + w.slice(1))
    .replace(/\b(BULLISH|BEARISH|NEUTRAL)\b/g, w => w.toLowerCase())
    .replace(/\b(STRONG_LONG|LIGHT_LONG|ACCUMULATE|REVIVAL_SEED_CONFIRMED|REVIVAL_SEED|TRIM_HARD|RISK_OFF|NO_LONG|LIGHT_SHORT|STRONG_SHORT)\b/g, signalWords)
    .replace(/([a-z])\(/g, '$1 (')
    .replace(/\s*\[absolute threshold\]/g, '')
    .replace(/\blsr=([\d.]+)/g, 'long/short $1')
    .replace(/\bF&G=(\d+)/g, 'Fear & Greed $1')
    .replace(/\bz=(-?[\d.]+)/g, 'z-score $1')
    .replace(/\bconf(?:idence)?=(\d+%)/g, '$1 confidence')
    .replace(/→\s*downgrade/g, ': downgrade')
    .replace(/\b([a-z]+(?:_[a-z]+)+)\b/g, w => w.replace(/_/g, ' '))
    .replace(/\s{2,}/g, ' ').trim();
}

export function plainReason(text = '') {
  const t = friendlyReason(text).trim();
  if (!t) return '';
  if (/^(BMSB data unavailable|Macro blocked)/i.test(t)) return blockedText(t);
  const md = /^([A-Z]+) regime \(consensus=([A-Z-]+)\)$/.exec(t);
  if (md) return `${regimeWord(md[1])} \u00b7 ${termWords(`consensus=${md[2]}`)}`;
  if (!/^[A-Z]+ \+ z=/.test(t)) return sentence(cleanEngineText(t));
  const tags = [];
  const body = t.replace(/\s*\[([^\]]*)\]/g, (_, tag) => { tags.push(tag.trim()); return ''; });
  const parts = body.split(' + ').map(s => s.trim()).filter(Boolean).map(termWords).filter(Boolean);
  const extra = tags.map(tagWords).filter(Boolean);
  return [...parts, ...extra].join(' · ');
}

// Why the engine blocked long entries, in plain words. Most blocks come
// from the weekly BMSB gate, which is not one of the entry checks.
function blockedText(reason = '') {
  if (/BMSB data unavailable/i.test(reason)) return 'Long entries blocked: not enough weekly history to compute the BMSB.';
  if (/Macro blocked/i.test(reason)) return 'Long entries blocked: price is below the weekly bull-market support band (BMSB).';
  return 'Long entries blocked by the engine. Inspect the entry checks for the blocking condition.';
}

// Spot markets have no funding rate: the Funding check is never available there, which is
// not an outage (the spot page carries a permanent note instead).
export function notApplicable(row = {}, c = {}) {
  return row.market_kind === 'spot' && c.name === 'funding_ok';
}

// Core inputs missing on most rows are a market-wide outage (e.g. the Fear & Greed
// feed), shown once above the grid rather than as an icon on every row.
export function marketWideMissing(rows = [], share = 0.8) {
  if (rows.length < 10) return [];
  const counts = {};
  for (const r of rows) for (const c of r.conditions_detail || []) {
    if (c.group === 'core' && c.available === false && !notApplicable(r, c)) { const k = c.label || c.name; counts[k] = (counts[k] || 0) + 1; }
  }
  return Object.entries(counts).filter(([, n]) => n / rows.length >= share).map(([k]) => k);
}

export function signalContext(row = {}, { marketWide = [] } = {}) {
  const signal = row.signal;
  const direction = signalDirection(signal);
  const allMissing = (row.conditions_detail || []).filter(c => c.group === 'core' && c.available === false);
  const missing = allMissing.filter(c => !marketWide.includes(c.label || c.name) && !notApplicable(row, c));
  const onlyMarketWide = allMissing.length > 0 && missing.length === 0;
  const messages = [...new Set([...(row.signal_warnings || []), ...(row.strong_long_blockers || [])])];
  const items = [];
  if (row.signal_status === 'unavailable') {
    // The synthesizer's own notes describe a signal that has been withdrawn, so they are not repeated.
    const stale = /stale|missing|future/i.test(row.signal_reason || '');
    return [{kind:'missing', text: stale
      ? 'Signal paused — the latest candles have not been refreshed yet. New entries resume after the next update.'
      : 'Assessment unavailable — the signal could not be calculated. Entries are suppressed.'}];
  }
  if (missing.length || (!onlyMarketWide && messages.some(w => /core context unavailable/i.test(w)))) {
    items.push({kind:'missing', text:`Assessment incomplete — ${missing.length ? missing.map(c => c.label || c.name).join(', ') : 'required market context'} unavailable. Strong Long cannot be confirmed.`});
  }
  if (row.entry_blocked && row.signal_status !== 'unavailable') items.push({kind:'caution', text:blockedText(row.signal_reason)});
  for (const raw of messages) {
    if (/core context unavailable/i.test(raw)) continue;
    const text = friendlyReason(raw);
    let kind = 'info';
    // Restrictions take precedence over directional words inside the same message.
    if ((row.strong_long_blockers || []).includes(raw) || /blocked|downgrade|risk|overextension|escalation|euphoria|may not sustain|cascade|contracting|capped|limit|unstable|outside strict|waiting for|demoted|held at|forced exit|extreme funding: \+/.test(text.toLowerCase())) kind = 'caution';
    else if (/unavailable|missing|pipeline failed/i.test(text)) kind = 'missing';
    else if (/bearish|BEAR-DIV|heavy_short/i.test(text)) kind = 'bearish';
    else if (/bullish|BULL-DIV|Floor confirmed|Absorption detected|spot_led_demand|top_trader_long|smart_money_long|rally fuel|potential bottom/i.test(text)) kind = 'bullish';
    const opposed = direction && ['bullish','bearish'].includes(kind) && kind !== direction;
    const aligned = direction && kind === direction;
    items.push({kind: opposed ? 'conflict' : kind, text: `${text}${opposed ? ` — opposes this ${direction === 'bullish' ? 'long' : 'short'}` : aligned ? ` — supports this ${direction === 'bullish' ? 'long' : 'short'}` : ''}`});
  }
  return items;
}

export function setupAlignment(row = {}, opts = {}) {
  const signal = row.signal;
  const direction = signalDirection(signal);
  if (!row.regime || row.signal_status === 'unavailable' || signalContext(row, opts).some(i => i.kind === 'missing')) return {state:'incomplete', label:'Assessment incomplete', strength:0};
  if (row.entry_blocked || ['BLOWOFF', 'CAP', 'ABSORBING'].includes(row.regime)) return {state:'caution', label: row.entry_blocked ? 'Entry restricted' : 'Transition / elevated risk', strength:0};
  if (!direction) return {state:'neutral', label:signal === 'WAIT' ? 'No active setup' : 'Position management', strength:0};
  const aligned = direction === 'bullish' ? ['MARKUP','REACC'].includes(row.regime) : row.regime === 'MARKDOWN';
  if (aligned) return {state:direction, label:`Aligned · ${signal.startsWith('STRONG') ? 'Strong' : signal.startsWith('LIGHT') ? 'Light' : 'Early'} signal`, strength:signal.startsWith('STRONG') ? 2 : 1};
  if ((direction === 'bullish' && row.regime === 'MARKDOWN') || (direction === 'bearish' && ['MARKUP','REACC'].includes(row.regime))) return {state:'conflict',label:'Countertrend',strength:0};
  return {state:'neutral',label:row.regime === 'ACCUM' ? 'Base forming' : 'No trend alignment',strength:0};
}
