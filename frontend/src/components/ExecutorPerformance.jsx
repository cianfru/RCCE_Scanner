import HelpTip from './HelpTip.jsx';
const money = v => v == null ? '—' : new Intl.NumberFormat('en-US', {style:'currency',currency:'USD',maximumFractionDigits:2}).format(v);
const tone = v => v == null || v === 0 ? '' : v > 0 ? 'positive' : 'negative';
export default function ExecutorPerformance({ performance: p, mode }) {
  if (!p) return <div className="executor-performance"><h2>Engine performance</h2><p>Performance attribution is not available from this backend yet.</p></div>;
  const curve = p.realized_curve || [];
  const values = [0, ...curve.map(x=>x.pnl_usd)];
  const min = Math.min(...values), span = Math.max(...values)-min || 1;
  const start = p.first_entry_at || p.as_of;
  const x = t => 12 + (t-start)/Math.max(1,p.as_of-start)*776;
  const y = v => 132 - (v-min)/span*116;
  const path = `M12 ${y(0)} ` + curve.map(point=>`H${x(point.time)} V${y(point.pnl_usd)}`).join(' ') + ` H788`;
  return <section className="executor-performance">
    <div className="executor-performance-heading"><div><span className="executor-eyebrow">{mode === 'paper' ? 'Paper engine' : 'Tracked execution ledger'}</span><h2>Engine performance</h2><p>{p.first_entry_at ? `Since ${new Date(p.first_entry_at*1000).toLocaleDateString()} · ${p.history_days} days of recorded history` : 'Waiting for the first recorded trade'}</p></div>
    <HelpTip title="Performance accounting"><p>{p.basis}</p><p>Win rate counts profitable closed trades divided by all closed trades, including break-even exits. Open positions are not wins or losses yet. Return uses starting capital, not cumulative traded volume.</p></HelpTip></div>
    <div className="executor-performance-grid">
      <Metric label="Realized P&L" value={money(p.realized_pnl_usd)} amount={p.realized_pnl_usd} note={`${p.closed_trades} completed trades`} />
      <Metric label={p.valuation_complete ? 'Unrealized P&L' : 'Unrealized P&L · partial'} value={money(p.unrealized_pnl_usd)} amount={p.unrealized_pnl_usd} note={`${p.priced_positions} of ${p.open_positions} open positions valued`} />
      <Metric label="Combined P&L" value={money(p.combined_pnl_usd)} amount={p.combined_pnl_usd} note={p.valuation_complete ? `${p.return_on_starting_capital_pct?.toFixed(2) ?? '—'}% on starting capital` : 'Awaiting complete valuation'} />
      <Metric label="Closed win rate" value={p.closed_win_rate == null ? '—' : `${p.closed_win_rate.toFixed(1)}%`} note={`${p.wins} wins / ${p.losses} losses / ${p.breakeven} flat`} />
    </div>
    {!p.valuation_complete && <p className="executor-data-note">Valuation is incomplete. {p.open_positions-p.priced_positions} positions cannot be priced reliably ({money(p.unpriced_cost_usd)} recorded entry cost). Combined return and equity remain unavailable. Review the marked positions below.</p>}
    {!p.accounting_reconciled && <p className="executor-data-note">The paper cash balance differs from the trade ledger by {money(p.cash_reconciliation_difference_usd)}. Historical holdings need reconciliation before these figures can represent account equity. {p.unmatched_holdings?.length > 0 && `Tracked positions absent from paper holdings: ${p.unmatched_holdings.join(", ")}.`}</p>}
    <div className="executor-history-grid"><div><h3>Realized P&L over time</h3><p>Closed trades only. Open gains and losses are excluded.</p>
      {curve.length ? <svg viewBox="0 0 800 154" role="img" aria-label={`Cumulative realized P&L ending at ${money(p.realized_pnl_usd)}`}><line x1="12" x2="788" y1={y(0)} y2={y(0)} stroke="currentColor" opacity=".2"/><path d={path} fill="none" stroke="var(--t-accent)" strokeWidth="2" vectorEffect="non-scaling-stroke"/></svg> : <p>No closed trades yet.</p>}
      <div className="executor-history-axis"><span>{new Date(start*1000).toLocaleDateString()}</span><span>{money(p.realized_pnl_usd)} now</span></div>
    </div><div><h3>Monthly realized results</h3><table><thead><tr><th>Month</th><th>Closed</th><th>P&L</th></tr></thead><tbody>{p.monthly_realized.map(m=><tr key={m.month}><td>{m.month}</td><td>{m.closed}</td><td className={tone(m.pnl_usd)}>{money(m.pnl_usd)}</td></tr>)}</tbody></table></div></div>
    <details className="executor-method"><summary>Exit breakdown and accounting details</summary><p>Starting capital {money(p.initial_balance_usd)}. {p.profit_factor == null ? 'Profit factor is not defined without gross losses.' : `Closed-trade profit factor: ${p.profit_factor.toFixed(2)}.`} Recorded P&L has not been adjusted to make historical trades look better.</p><dl>{Object.entries(p.exit_reasons).map(([name,count])=><div key={name}><dt>{name.replaceAll('_',' ')}</dt><dd>{count}</dd></div>)}</dl><p>{p.basis}</p></details>
  </section>;
}
function Metric({label,value,amount,note}) {return <div><span>{label}</span><strong className={tone(amount)}>{value}</strong><small>{note}</small></div>;}
