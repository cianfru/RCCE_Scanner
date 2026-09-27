const COPY = {
  hyperlens: ["Read the positioning behind the move.", "Trader participation, position value and engine signals, with clear cohort and update context."],
  signals: ["Follow the setup through time.", "Daily signal snapshots, changes and wallet disagreements. Select a reading to inspect its evidence."],
  analytics: ["Measure the evidence.", "Historical outcomes and sample strength across the recorded signal history."],
  tradfi: ["A broader market perspective.", "Commodities and indices through the cycle framework, with instrument sources and history coverage."],
  backtest: ["Put the strategy in context.", "Configure a historical run, inspect its assumptions and return to saved results."],
  executor: ["An accountable execution record.", "Closed outcomes and open exposure, with execution mode and valuation coverage."],
  trading: ["Your account, in perspective.", "Positions, orders and performance in one place, with scanner context alongside your exposure."],
  admin: ["Workspace administration.", "Server-wide controls for administrators. These settings affect collection and scanning for everyone using this deployment."],
};
export default function WorkspaceIntro({section}) {
 const copy=COPY[section]; if(!copy)return null;
 return <div className="workspace-intro"><div><h2>{copy[0]}</h2><p>{copy[1]}</p></div><div className="metal-mark" aria-hidden="true"><img src="/brand/reflex-ribbon-transparent.svg" alt="" width="58" height="58"/></div></div>;
}
