// Presentation only: never changes eligibility, engine scores, or signal output.
export function signalDirection(signal) {
  if (['STRONG_LONG', 'LIGHT_LONG', 'ACCUMULATE', 'REVIVAL_SEED', 'REVIVAL_SEED_CONF'].includes(signal)) return 'bullish';
  if (['STRONG_SHORT', 'LIGHT_SHORT'].includes(signal)) return 'bearish';
  return null; // Exit instructions are not short entries.
}

export function friendlyReason(text = '') {
  return String(text).replace(/core context unavailable/gi, 'Required market context is missing; Strong Long is unavailable')
    .replace(/final eligibility cap/gi, 'Entry restrictions applied')
    .replace(/final eligibility:/gi, 'Entry restriction:');
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
  if (row.entry_blocked && row.signal_status !== 'unavailable') items.push({kind:'caution', text:'Long entries blocked by the engine. Inspect the entry checks for the blocking condition.'});
  for (const raw of messages) {
    if (/core context unavailable/i.test(raw)) continue;
    const text = friendlyReason(raw);
    let kind = 'info';
    // Restrictions take precedence over directional words inside the same message.
    if ((row.strong_long_blockers || []).includes(raw) || /blocked|downgrade|risk|overextension|escalation|euphoria|may not sustain|cascade|contracting|capped|limit|unstable|outside strict|waiting for|demoted|forced exit|extreme funding: \+/.test(text.toLowerCase())) kind = 'caution';
    else if (/unavailable|missing|pipeline failed/i.test(text)) kind = 'missing';
    else if (/bearish|BEAR-DIV|heavy_short/i.test(text)) kind = 'bearish';
    else if (/bullish|BULL-DIV|Floor confirmed|Absorption detected|spot_led_demand|smart_money_long|rally fuel|potential bottom/i.test(text)) kind = 'bullish';
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
