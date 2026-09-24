import { T } from '../theme.js';
import { strategyLabel, researchNumber as number, researchTime as stamp } from '../utils/researchSetups.js';
export default function TradingSetupCards({ records }) {
  if (!records?.length) return null;
  return <section aria-label="Defined trading setups" style={{ border: `1px solid ${T.border}`, padding: 16, borderRadius: 12, marginBottom: 14, color: T.text2 }}>
    <h3>Defined 4h setups · paper research</h3>
    <p>Unvalidated strategy rules. These setups do not place orders. CTO is a reference.</p>
    {records.filter(r => r.contract.strategy !== 'trend_comparator').map(({ contract: c, state: s }) => <article key={c.id} style={{ borderTop: `1px solid ${T.border}`, padding: '12px 0' }}>
      <strong>{strategyLabel(c.strategy)} · {s.status.replaceAll('_', ' ')}</strong>
      <p>{s.reason}{s.paused_reason ? ` · Paused: ${s.paused_reason}` : ''}</p>
      <dl style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
        <dt>Trigger: completed 4h close above</dt><dd>{number(c.trigger)}</dd>
        <dt>Planned opening entry zone</dt><dd>{c.entry_zone?.map(number).join(' – ') || 'Unavailable'}</dd>
        <dt>Structural stop / target</dt><dd>{number(c.stop)} / {number(c.target)}</dd>
        <dt>Planned reward / risk</dt><dd>{number(c.reward_r)} R</dd>
        <dt>Untriggered expiry</dt><dd>{stamp(c.expires_at)}</dd>
        <dt>Maximum holding period</dt><dd>{c.parameters.max_hold_bars * 4} hours</dd>
      </dl>
      <p>Execution: {c.execution.reason}. Assumed costs: {c.parameters.fee_bps} bps fee + {c.parameters.slippage_bps} bps slippage per side, plus observed half-spread.</p>
      <details><summary>Frozen context and paper commitment</summary>
        <p>{c.context_reasons.join('. ')}</p>
        <p>{c.trigger_rule}</p>
        <p>Observed: {stamp(c.observed_at)} · Reference candle: {stamp(c.reference_close)}<br/>Paper entry scheduled: {stamp(s.entry_due)} · Filled: {stamp(s.entry_at)}</p>
        <p>CTO: {c.cto_reference?.state || 'Unavailable'} · Definition {c.version} · {c.id}</p>
      </details>
    </article>)}
  </section>;
}
