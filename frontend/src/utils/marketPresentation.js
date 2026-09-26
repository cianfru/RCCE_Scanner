import { ENTRY_SIGNALS } from "./opportunities.js";
import { REGIME_META } from "../theme.js";
// API contracts: signal_confidence/confidence are 0–100; smart-money confidence is 0–1.
export function formatPercent(value, { ratio = false, digits = 0 } = {}) {
  if (value == null || !Number.isFinite(Number(value))) return '—';
  return `${(Number(value) * (ratio ? 100 : 1)).toFixed(digits)}%`;
}
// Prices: two decimals with thousands separators from $1 up; four significant digits below.
const PRICE_2DP = new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const PRICE_SIG = new Intl.NumberFormat('en-US', { maximumSignificantDigits: 4 });
export function formatPrice(value) {
  const v = Number(value);
  if (value == null || !Number.isFinite(v)) return '—';
  return `$${Math.abs(v) >= 1 ? PRICE_2DP.format(v) : PRICE_SIG.format(v)}`;
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
