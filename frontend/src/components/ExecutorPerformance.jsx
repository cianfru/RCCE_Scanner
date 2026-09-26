import HelpTip from './HelpTip.jsx';
import { SIGNAL_META } from '../theme.js';
// Readable names for executor exit reasons; scanner signals fall back to their label.
const EXIT_LABELS = {BE_STOP:'Break-even stop', STOP_LOSS:'Stop loss', NO_LONG:'No-long signal', TRIM:'Trim signal', TRIM_HARD:'Hard trim signal', RISK_OFF:'Risk-off signal', UNKNOWN:'Unknown'};
export const exitLabel = sig => !sig ? '—' : EXIT_LABELS[sig] ?? SIGNAL_META[sig]?.label ?? sig.replaceAll('_',' ');
const money = v => v == null ? '—' : new Intl.NumberFormat('en-US', {style:'currency',currency:'USD',maximumFractionDigits:2}).format(v);
const percent = v => v == null ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(2)}%`;
const tone = v => v == null || v === 0 ? '' : v > 0 ? 'positive' : 'negative';
export default function ExecutorPerformance({ performance: p, mode }) {
  if (!p) return <div className="executor-performance"><h2>Engine performance</h2><p>Performance attribution is not available from this backend yet.</p></div>;
  if (!Array.isArray(p.included_closed_trades)) return <div className="executor-performance"><h2>Engine performance</h2><p>The included-trade view requires the updated backend. Waiting for matching performance data.</p></div>;
  const curve = p.realized_curve || [];
  const values = [0, ...curve.map(x=>x.pnl_usd)];
  const min = Math.min(...values), span = Math.max(...values)-min || 1;
  const start = p.first_entry_at || p.as_of;
  const x = t => 12 + (t-start)/Math.max(1,p.as_of-start)*776;
  const y = v => 132 - (v-min)/span*116;
  const path = `M12 ${y(0)} ` + curve.map(point=>`H${x(point.time)} V${y(point.pnl_usd)}`).join(' ') + ` H788`;
  return <section className="executor-performance">
    <div className="executor-performance-heading"><div><span className="executor-eyebrow">{mode === 'paper' ? 'Paper engine' : 'Tracked execution ledger'}</span><h2>Engine performance</h2><p>{p.first_entry_at ? `Since ${new Date(p.first_entry_at*1000).toLocaleDateString()} · ${p.history_days} days of recorded history` : 'Waiting for the first recorded trade'}</p></div>
    <HelpTip title="Performance accounting"><p>{p.basis}</p><p>The win rate counts profitable closed trades against losing ones. Break-even-stop exits (closed at or just below entry after the stop moved up) and flat closes are listed separately and not counted as either. Including them, the rate is {p.closed_win_rate == null ? '—' : `${p.closed_win_rate.toFixed(1)}%`}. Open positions are not wins or losses yet. Return uses starting capital, not cumulative traded volume.</p></HelpTip></div>
    <div className="executor-performance-grid">
      <Metric label="Realized P&L" value={money(p.realized_pnl_usd)} amount={p.realized_pnl_usd} note={`${p.closed_trades} included closed trades`} />
      <Metric label="Unrealized P&L" value={money(p.unrealized_pnl_usd)} amount={p.unrealized_pnl_usd} note={`${p.open_positions} included positions · ${p.open_profitable_count ?? 0} in profit`} />
      <Metric label="Combined P&L · included trades" value={money(p.combined_pnl_usd)} amount={p.combined_pnl_usd} note="Realized + unrealized on included trades" />
      {p.win_rate_excluding_break_even_pct === undefined
        ? <Metric label="Closed win rate · all exits" value={p.closed_win_rate == null ? '—' : `${p.closed_win_rate.toFixed(1)}%`} note={`${p.wins} wins / ${p.losses} losses / ${p.breakeven} flat`} />
        : <Metric label="Win rate · excluding break-even stops" value={p.win_rate_excluding_break_even_pct == null ? '—' : `${p.win_rate_excluding_break_even_pct.toFixed(1)}%`} note={`${p.wins} wins / ${p.losses_excluding_break_even_stops} losses. Not counted: ${p.break_even_stops} break-even stops (${money(p.break_even_stop_pnl_usd)} in total) and ${p.breakeven} flat.`} />}
    </div>
    <div className="executor-performance-grid executor-return-grid">
      <Metric label={`Return over ${Math.floor(p.return_period_days ?? p.history_days)} days · realized + open marks`} value={percent(p.included_return_pct)} amount={p.included_return_pct} note={`${money(p.combined_pnl_usd)} combined P&L ÷ ${money(p.initial_balance_usd)} starting capital. Open marks can reverse before they are closed.`} />
      <Metric label="Return · realized only" value={percent(p.realized_return_pct ?? (p.initial_balance_usd > 0 ? p.realized_pnl_usd / p.initial_balance_usd * 100 : null))} amount={p.realized_pnl_usd} note={`${money(p.realized_pnl_usd)} from closed trades ÷ ${money(p.initial_balance_usd)} starting capital`} />
    </div>
    <details className="executor-method"><summary>How these returns are calculated</summary><p>The period return includes both realized and unrealized P&L from the included trades, divided by the original starting capital. The unrealized part is the current mark on open positions and is not locked in. The realized-only return counts closed trades alone. Excluded trades and positions are omitted, so neither is a reconciled account return. No annualized figure is shown: extending a period return that rests on open marks to a yearly rate would overstate what has been earned. Paper results exclude fees, funding and slippage.</p></details>
    <p className="executor-data-note">Included trades only. {p.excluded_closed_trades || 0} closed trades and {p.excluded_open_positions || 0} open positions are excluded because of price errors or unavailable valuations. These figures are not a full account return.</p>
    <div className="executor-history-grid"><div><h3>Realized P&L over time</h3><p>Included closed trades only. Open gains and losses are excluded.</p>
      {curve.length ? <svg viewBox="0 0 800 154" role="img" aria-label={`Cumulative realized P&L ending at ${money(p.realized_pnl_usd)}`}><line x1="12" x2="788" y1={y(0)} y2={y(0)} stroke="currentColor" opacity=".2"/><path d={path} fill="none" stroke="var(--t-accent)" strokeWidth="2" vectorEffect="non-scaling-stroke"/></svg> : <p>No closed trades yet.</p>}
      <div className="executor-history-axis"><span>{new Date(start*1000).toLocaleDateString()}</span><span>{money(p.realized_pnl_usd)} now</span></div>
    </div><div><h3>Monthly realized results</h3><table><thead><tr><th>Month</th><th>Closed</th><th>P&L</th></tr></thead><tbody>{p.monthly_realized.map(m=><tr key={m.month}><td>{m.month}</td><td>{m.closed}</td><td className={tone(m.pnl_usd)}>{money(m.pnl_usd)}</td></tr>)}</tbody></table></div></div>
    <details className="executor-method"><summary>Exit breakdown and accounting details</summary><p>Starting capital {money(p.initial_balance_usd)}. {p.profit_factor == null ? 'Profit factor is not defined without gross losses.' : `Closed-trade profit factor: ${p.profit_factor.toFixed(2)}.`} Price-error closures and unpriceable open positions are excluded consistently from these totals and lists. Original records are retained.</p><dl>{Object.entries(p.exit_reasons).map(([name,count])=><div key={name}><dt>{exitLabel(name)}</dt><dd>{count}</dd></div>)}</dl><p>{p.basis}</p>{!p.accounting_reconciled && <p>The original paper cash ledger has an unreconciled difference of {money(p.cash_reconciliation_difference_usd)}. Account equity is not reported.</p>}</details>
  </section>;
}
function Metric({label,value,amount,note}) {return <div><span>{label}</span><strong className={tone(amount)}>{value}</strong><small>{note}</small></div>;}
