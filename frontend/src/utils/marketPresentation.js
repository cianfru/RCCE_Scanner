import { ENTRY_SIGNALS } from "./opportunities.js";
import { REGIME_META } from "../theme.js";
import { signalDirection } from "./signalPresentation.js";
// API contracts: signal_confidence/confidence are 0–100; smart-money confidence is 0–1.
export function formatPercent(value, { ratio = false, digits = 0 } = {}) {
  if (value == null || !Number.isFinite(Number(value))) return '—';
  return `${(Number(value) * (ratio ? 100 : 1)).toFixed(digits)}%`;
}
// Prices: two decimals with thousands separators from $1 up; four significant digits below
// (the grid's tight symbol cell). A price read on its own (coin page, Radar focus, Full detail)
// passes { sig: 5 } to match the chart and the traders' entry prices beside it.
const PRICE_2DP = new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const PRICE_SIG = { 4: new Intl.NumberFormat('en-US', { maximumSignificantDigits: 4 }), 5: new Intl.NumberFormat('en-US', { maximumSignificantDigits: 5 }) };
export function formatPrice(value, { sig = 4 } = {}) {
  const v = Number(value);
  if (value == null || !Number.isFinite(v)) return '—';
  return `$${Math.abs(v) >= 1 ? PRICE_2DP.format(v) : (PRICE_SIG[sig] || PRICE_SIG[4]).format(v)}`;
}
// The backend stores funding as an hourly fraction; exchanges quote it per 8h in percent.
export const funding8hPct = r => (r == null || !Number.isFinite(Number(r)) ? null : Number(r) * 8 * 100);
// CoinGlass-derived fields (top-trader L/S, liquidations, spot share) hold placeholders
// unless the feed is fresh and this market is covered by it.
export const hasCoinglass = row => row?.input_quality?.coinglass?.status === 'ready' && row?.positioning?.source_map?.liq === 'coinglass';
// Two WAITs neither agree nor differ: the backend sends signal_aligned null for them.
export function signalAgreement(c) {
  if (!c) return null;
  if (c.signal_aligned === null || (c.signal_4h === 'WAIT' && c.signal_1d === 'WAIT')) return 'waiting';
  return c.signal_aligned ? 'agree' : 'differ';
}
const SIGNAL_AGREEMENT_TEXT = { waiting: 'Both timeframes are waiting.', agree: 'Their signals agree.', differ: 'Their signals differ.' };
const BULLISH_FAMILY = new Set(['MARKUP', 'REACC', 'ACCUM']);
function regimeAgreement(c) {
  const n4 = REGIME_META[c.regime_4h]?.name, n1 = REGIME_META[c.regime_1d]?.name;
  if (!c.regime_aligned) return `The 4H and 1D regimes differ${n4 && n1 ? ` (${n4} and ${n1})` : ''}.`;
  if (!n4 || !n1) return 'The 4H and 1D regimes agree.';
  if (c.regime_4h === c.regime_1d) return `The 4H and 1D regimes agree (both ${n4}).`;
  return `The 4H and 1D regimes agree (both in the ${BULLISH_FAMILY.has(c.regime_4h) ? 'bullish' : 'bearish'} family: ${n4} and ${n1}).`;
}
export function evidenceSummary(data) {
  const regime = ({MARKUP:'an upward market phase', ACCUM:'a base-building phase', REACC:'a pullback within an upward phase', MARKDOWN:'a downward market phase', BLOWOFF:'an extended upward phase', CAP:'a capitulation phase', FLAT:'a neutral market phase'})[data.regime] || String(data.regime || 'an unclassified phase').toLowerCase();
  return `The scanner identifies ${regime}. ${data.conditions_total > 0 ? `${data.conditions_met} of ${data.conditions_total} entry checks are satisfied.` : 'Entry checks are not available for this snapshot.'} ${data.confluence ? `${regimeAgreement(data.confluence)} ${SIGNAL_AGREEMENT_TEXT[signalAgreement(data.confluence)]}` : ''}`;
}

// Market readings that currently argue against the signal's side, in plain words. Only
// readings the data actually has: a missing feed is never counter-evidence. Empty for WAIT
// and exit signals, which take no side.
export function counterEvidence(row = {}) {
  const dir = signalDirection(row.signal);
  if (!dir) return [];
  const p = row.positioning || {};
  const cg = hasCoinglass(row);
  const long = dir === "bullish";
  const out = [];
  const f = funding8hPct(p.funding_rate);
  const rate = f != null ? ` (${f.toFixed(4)}% per 8h)` : "";
  if (p.funding_regime === (long ? "CROWDED_LONG" : "CROWDED_SHORT")) out.push(`${long ? "Longs" : "Shorts"} are crowded: funding${rate}`);
  if (long && p.oi_trend === "LIQUIDATING") out.push("Open interest is falling with price");
  if (long && p.oi_trend === "SHORTING") out.push("Shorts are opening as price falls");
  if (row.cvd_trend === (long ? "BEARISH" : "BULLISH")) out.push(`Takers are ${long ? "selling" : "buying"}`);
  if (cg && p.spot_dominance === (long ? "FUTURES_LED" : "SPOT_LED")) out.push(long ? "The move is led by futures, not spot" : "Spot buyers are leading");
  if (cg && p.top_trader_lsr && p.top_trader_lsr !== 1 && (long ? p.top_trader_lsr < 0.8 : p.top_trader_lsr > 1.3)) out.push(`Top exchange traders lean ${long ? "short" : "long"}`);
  return out;
}

// Highest-priority setups, at most one per sector, so the shortlist is three
// different bets rather than three versions of the same market move.
export function bestEntrySetups(results, limit = 3) {
 const ranked = [...results].filter(row => (ENTRY_SIGNALS.has(row.signal) || row.signal === 'LIGHT_SHORT') && row.signal_status !== 'unavailable' && (!row.opportunity || row.opportunity.status === 'confirmed') && Number.isFinite(row.priority_score)).sort((a,b)=>b.priority_score-a.priority_score || a.symbol.localeCompare(b.symbol));
 const picked = [], sectors = new Set();
 for (const row of ranked) {
  const sector = row.sector && row.sector !== 'Other' ? row.sector : null;
  if (sector && sectors.has(sector)) continue;
  picked.push(row);
  if (sector) sectors.add(sector);
  if (picked.length === limit) break;
 }
 return picked;
}
