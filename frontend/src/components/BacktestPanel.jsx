import { useState, useEffect, useRef, useCallback } from "react";
import { T, SIGNAL_META, fmt } from "../theme.js";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";

// ─── EQUITY CURVE CHART ──────────────────────────────────────────────────────

function EquityChart({ equity, btcEquity, height = 260 }) {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !equity?.length) return;
    const ctx = canvas.getContext("2d");
    const W = canvas.width = canvas.parentElement.clientWidth;
    const H = canvas.height = height;
    ctx.clearRect(0, 0, W, H);

    const pad = { t: 24, b: 36, l: 60, r: 16 };
    const cw = W - pad.l - pad.r;
    const ch = H - pad.t - pad.b;

    // Merge all values for Y bounds
    const allVals = [...equity.map(p => p[1])];
    if (btcEquity?.length) allVals.push(...btcEquity.map(p => p[1]));
    const yMin = Math.min(...allVals) * 0.98;
    const yMax = Math.max(...allVals) * 1.02;

    const toX = (i, len) => pad.l + (i / (len - 1)) * cw;
    const toY = (v) => pad.t + ch - ((v - yMin) / (yMax - yMin)) * ch;

    // Grid
    ctx.strokeStyle = "rgba(255,255,255,0.04)";
    ctx.lineWidth = 1;
    const gridLines = 5;
    for (let i = 0; i <= gridLines; i++) {
      const y = pad.t + (ch / gridLines) * i;
      ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(W - pad.r, y); ctx.stroke();
      const val = yMax - (yMax - yMin) * (i / gridLines);
      ctx.fillStyle = "rgba(255,255,255,0.25)";
      ctx.font = "9px JetBrains Mono, monospace";
      ctx.textAlign = "right";
      ctx.fillText(`$${val.toFixed(0)}`, pad.l - 6, y + 3);
    }

    // Date labels
    if (equity.length > 2) {
      const dates = equity.map(p => new Date(p[0]));
      const labelCount = Math.min(6, equity.length);
      ctx.fillStyle = "rgba(255,255,255,0.2)";
      ctx.font = "8px JetBrains Mono, monospace";
      ctx.textAlign = "center";
      for (let i = 0; i < labelCount; i++) {
        const idx = Math.floor((i / (labelCount - 1)) * (dates.length - 1));
        const d = dates[idx];
        const label = `${d.getMonth() + 1}/${d.getDate()}`;
        ctx.fillText(label, toX(idx, equity.length), H - pad.b + 16);
      }
    }

    // Draw line helper
    const drawLine = (data, color, dashed = false) => {
      if (!data?.length || data.length < 2) return;
      ctx.beginPath();
      ctx.strokeStyle = color;
      ctx.lineWidth = dashed ? 1 : 1.5;
      if (dashed) ctx.setLineDash([4, 4]);
      else ctx.setLineDash([]);
      data.forEach((p, i) => {
        const x = toX(i, data.length);
        const y = toY(p[1]);
        i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
      });
      ctx.stroke();

      // Fill area under strategy line
      if (!dashed) {
        const lastIdx = data.length - 1;
        ctx.lineTo(toX(lastIdx, data.length), pad.t + ch);
        ctx.lineTo(toX(0, data.length), pad.t + ch);
        ctx.closePath();
        ctx.fillStyle = color.replace(")", ",0.06)").replace("rgb", "rgba");
        ctx.fill();
      }
    };

    // BTC benchmark (dashed orange)
    drawLine(btcEquity, "rgb(251,146,60)", true);
    // Strategy (solid cyan)
    drawLine(equity, "rgb(34,211,238)", false);

    // Legend
    ctx.setLineDash([]);
    const legendY = 12;
    ctx.font = "9px JetBrains Mono, monospace";

    ctx.fillStyle = "rgb(34,211,238)";
    ctx.fillRect(pad.l, legendY - 4, 12, 2);
    ctx.fillText("Strategy", pad.l + 16, legendY);

    ctx.fillStyle = "rgb(251,146,60)";
    ctx.setLineDash([3, 3]);
    ctx.beginPath(); ctx.moveTo(pad.l + 80, legendY - 3); ctx.lineTo(pad.l + 92, legendY - 3); ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillText("BTC B&H", pad.l + 96, legendY);

  }, [equity, btcEquity, height]);

  if (!equity?.length) return null;
  return <canvas ref={canvasRef} style={{ width: "100%", display: "block" }} />;
}

// ─── METRIC CARD ────────────────────────────────────────────────────────────

function MetricCard({ label, value, suffix = "", positive, isMobile }) {
  const color = positive === true ? "#34d399" : positive === false ? "#f87171" : T.text1;
  return (
    <div style={{
      flex: 1, minWidth: isMobile ? 100 : 120,
      background: T.surface, border: `1px solid ${T.border}`, borderRadius: T.radiusSm,
      padding: isMobile ? "10px 12px" : "12px 16px",
    }}>
      <div style={{ fontSize: 8, color: T.text4, fontFamily: T.mono, letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 4 }}>
        {label}
      </div>
      <div style={{ fontSize: isMobile ? 16 : 20, fontWeight: 700, fontFamily: T.mono, color }}>
        {value}{suffix}
      </div>
    </div>
  );
}

// ─── PROGRESS BAR ───────────────────────────────────────────────────────────

function ProgressBar({ progress, status }) {
  return (
    <div style={{ marginTop: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
        <span style={{ fontSize: 10, color: T.text3, fontFamily: T.mono }}>{status}</span>
        <span style={{ fontSize: 10, color: T.accent, fontFamily: T.mono }}>{progress.toFixed(0)}%</span>
      </div>
      <div style={{ height: 4, background: "rgba(255,255,255,0.04)", borderRadius: 2, overflow: "hidden" }}>
        <div style={{
          width: `${progress}%`, height: "100%",
          background: `linear-gradient(90deg, ${T.accent}, ${T.accent}cc)`,
          borderRadius: 2, transition: "width 0.5s ease",
        }} />
      </div>
    </div>
  );
}

// ─── MAIN PANEL ────────────────────────────────────────────────────────────

export default function BacktestPanel({ isMobile }) {
  const [config, setConfig] = useState({
    start_date: "2025-01-01",
    end_date: "",
    initial_capital: 10000,
    symbols: [],
    use_confluence: true,
    use_fear_greed: true,
  });
  const [btId, setBtId] = useState(null);
  const [result, setResult] = useState(null);
  const [polling, setPolling] = useState(false);
  const [error, setError] = useState(null);
  const [showTrades, setShowTrades] = useState(false);
  const pollRef = useRef(null);

  // Poll for results
  const poll = useCallback(async (id) => {
    try {
      const resp = await fetch(`${API}/api/backtest/${id}`);
      if (!resp.ok) throw new Error("Poll failed");
      const data = await resp.json();
      setResult(data);
      if (data.status === "complete" || data.status === "error") {
        setPolling(false);
        if (data.error) setError(data.error);
      }
    } catch (e) {
      setError(e.message);
      setPolling(false);
    }
  }, []);

  useEffect(() => {
    if (polling && btId) {
      pollRef.current = setInterval(() => poll(btId), 2000);
      return () => clearInterval(pollRef.current);
    }
  }, [polling, btId, poll]);

  const startBacktest = async () => {
    setError(null); setResult(null); setShowTrades(false);
    try {
      const resp = await fetch(`${API}/api/backtest`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(config),
      });
      if (!resp.ok) throw new Error("Failed to start backtest");
      const data = await resp.json();
      setBtId(data.id);
      setPolling(true);
      setResult({ status: "fetching", progress: 0 });
    } catch (e) {
      setError(e.message);
    }
  };

  const isRunning = result && !["complete", "error"].includes(result.status);
  const m = result?.metrics;
  const isDone = result?.status === "complete";

  return (
    <div style={{ padding: isMobile ? 12 : 0 }}>

      {/* ── CONFIG FORM ── */}
      <div style={{
        background: T.surface, border: `1px solid ${T.border}`, borderRadius: T.radius,
        padding: isMobile ? 16 : 20, marginBottom: 16,
      }}>
        <div style={{ fontSize: 11, fontFamily: T.mono, color: T.text2, fontWeight: 600, marginBottom: 14, letterSpacing: "0.08em" }}>
          BACKTEST CONFIGURATION
        </div>
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "flex-end" }}>
          <InputField label="START" type="date" value={config.start_date}
            onChange={v => setConfig(c => ({ ...c, start_date: v }))} isMobile={isMobile} />
          <InputField label="END" type="date" value={config.end_date} placeholder="today"
            onChange={v => setConfig(c => ({ ...c, end_date: v }))} isMobile={isMobile} />
          <InputField label="CAPITAL" type="number" value={config.initial_capital}
            onChange={v => setConfig(c => ({ ...c, initial_capital: Number(v) }))} isMobile={isMobile} />
          <button
            onClick={startBacktest}
            disabled={isRunning}
            style={{
              padding: "8px 24px", borderRadius: "20px", border: "none",
              background: isRunning ? T.text4 : T.accent,
              color: "#000", fontFamily: T.mono, fontSize: 11, fontWeight: 700,
              cursor: isRunning ? "not-allowed" : "pointer",
              letterSpacing: "0.06em",
            }}
          >
            {isRunning ? "RUNNING..." : "RUN BACKTEST"}
          </button>
        </div>
        <div style={{ fontSize: 9, color: T.text4, marginTop: 8, fontFamily: T.mono }}>
          10 symbols (BTC, ETH, SOL, BNB, XRP, ADA, AVAX, DOGE, DOT, LINK) | 4H primary + 1D confluence
        </div>
      </div>

      {/* ── ERROR ── */}
      {error && (
        <div style={{
          padding: 12, marginBottom: 16, borderRadius: T.radiusSm,
          background: "rgba(248,113,113,0.08)", border: "1px solid rgba(248,113,113,0.2)",
          color: "#f87171", fontSize: 11, fontFamily: T.mono,
        }}>
          {error}
        </div>
      )}

      {/* ── PROGRESS ── */}
      {isRunning && result && (
        <div style={{
          background: T.surface, border: `1px solid ${T.border}`, borderRadius: T.radius,
          padding: 20, marginBottom: 16,
        }}>
          <ProgressBar progress={result.progress || 0} status={result.status?.toUpperCase() || "STARTING"} />
          {result.symbols_loaded > 0 && (
            <div style={{ fontSize: 9, color: T.text4, fontFamily: T.mono, marginTop: 8 }}>
              {result.symbols_loaded} symbols loaded | {result.bar_count || 0} bars processed
            </div>
          )}
        </div>
      )}

      {/* ── RESULTS ── */}
      {isDone && m && (
        <>
          {/* Metrics cards */}
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
            <MetricCard label="Total Return" value={fmt(m.total_return_pct, 1)} suffix="%" positive={m.total_return_pct > 0} isMobile={isMobile} />
            <MetricCard label="BTC Return" value={fmt(m.btc_return_pct, 1)} suffix="%" positive={m.btc_return_pct > 0} isMobile={isMobile} />
            <MetricCard label="Alpha" value={fmt(m.alpha_pct, 1)} suffix="%" positive={m.alpha_pct > 0} isMobile={isMobile} />
            <MetricCard label="Win Rate" value={fmt(m.win_rate, 0)} suffix="%" positive={m.win_rate > 50} isMobile={isMobile} />
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
            <MetricCard label="Sharpe" value={fmt(m.sharpe_ratio, 2)} positive={m.sharpe_ratio > 1} isMobile={isMobile} />
            <MetricCard label="Sortino" value={fmt(m.sortino_ratio, 2)} positive={m.sortino_ratio > 1} isMobile={isMobile} />
            <MetricCard label="Max DD" value={fmt(m.max_drawdown_pct, 1)} suffix="%" positive={m.max_drawdown_pct > -15} isMobile={isMobile} />
            <MetricCard label="Trades" value={m.total_trades} isMobile={isMobile} />
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
            <MetricCard label="Profit Factor" value={fmt(m.profit_factor, 2)} positive={m.profit_factor > 1} isMobile={isMobile} />
            <MetricCard label="Avg Win" value={fmt(m.avg_win_pct, 2)} suffix="%" isMobile={isMobile} />
            <MetricCard label="Avg Loss" value={fmt(m.avg_loss_pct, 2)} suffix="%" isMobile={isMobile} />
            <MetricCard label="Avg Bars" value={fmt(m.avg_bars_held, 0)} isMobile={isMobile} />
          </div>

          {/* Equity curve */}
          <div style={{
            background: T.surface, border: `1px solid ${T.border}`, borderRadius: T.radius,
            padding: 16, marginBottom: 16,
          }}>
            <div style={{ fontSize: 9, fontFamily: T.mono, color: T.text4, letterSpacing: "0.1em", marginBottom: 8 }}>
              EQUITY CURVE
            </div>
            <EquityChart
              equity={result.equity_curve}
              btcEquity={result.btc_equity_curve}
              height={isMobile ? 200 : 280}
            />
          </div>

          {/* Signal accuracy table */}
          {result.signal_stats && Object.keys(result.signal_stats).length > 0 && (
            <div style={{
              background: T.surface, border: `1px solid ${T.border}`, borderRadius: T.radius,
              padding: 16, marginBottom: 16, overflowX: "auto",
            }}>
              <div style={{ fontSize: 9, fontFamily: T.mono, color: T.text4, letterSpacing: "0.1em", marginBottom: 10 }}>
                SIGNAL ACCURACY
              </div>
              <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: T.mono, fontSize: 10 }}>
                <thead>
                  <tr style={{ borderBottom: `1px solid ${T.border}` }}>
                    {["SIGNAL", "COUNT", "WIN RATE", "AVG RETURN", "TOTAL P&L", "AVG BARS"].map(h => (
                      <th key={h} style={{ padding: "6px 10px", textAlign: "left", color: T.text4, fontSize: 8, letterSpacing: "0.1em" }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(result.signal_stats).map(([sig, s]) => {
                    const sm = SIGNAL_META[sig] || { color: T.text3 };
                    const wrColor = s.win_rate >= 60 ? "#34d399" : s.win_rate >= 50 ? "#fbbf24" : "#f87171";
                    return (
                      <tr key={sig} style={{ borderBottom: `1px solid ${T.border}` }}>
                        <td style={{ padding: "6px 10px", color: sm.color, fontWeight: 600 }}>{sig}</td>
                        <td style={{ padding: "6px 10px", color: T.text2 }}>{s.count}</td>
                        <td style={{ padding: "6px 10px", color: wrColor, fontWeight: 600 }}>{s.win_rate.toFixed(0)}%</td>
                        <td style={{ padding: "6px 10px", color: s.avg_return_pct >= 0 ? "#34d399" : "#f87171" }}>{s.avg_return_pct.toFixed(2)}%</td>
                        <td style={{ padding: "6px 10px", color: s.total_pnl_pct >= 0 ? "#34d399" : "#f87171" }}>{s.total_pnl_pct.toFixed(2)}%</td>
                        <td style={{ padding: "6px 10px", color: T.text3 }}>{s.avg_bars_held.toFixed(0)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* Condition analysis */}
          {result.condition_analysis?.length > 0 && (
            <div style={{
              background: T.surface, border: `1px solid ${T.border}`, borderRadius: T.radius,
              padding: 16, marginBottom: 16, overflowX: "auto",
            }}>
              <div style={{ fontSize: 9, fontFamily: T.mono, color: T.text4, letterSpacing: "0.1em", marginBottom: 10 }}>
                CONDITION PREDICTIVE VALUE
              </div>
              <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: T.mono, fontSize: 10 }}>
                <thead>
                  <tr style={{ borderBottom: `1px solid ${T.border}` }}>
                    {["CONDITION", "TRUE", "FALSE", "AVG RET (TRUE)", "AVG RET (FALSE)", "VALUE"].map(h => (
                      <th key={h} style={{ padding: "6px 10px", textAlign: "left", color: T.text4, fontSize: 8, letterSpacing: "0.1em" }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {result.condition_analysis.map((ca, i) => (
                    <tr key={i} style={{ borderBottom: `1px solid ${T.border}` }}>
                      <td style={{ padding: "6px 10px", color: T.text2, maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis" }}>{ca.name}</td>
                      <td style={{ padding: "6px 10px", color: T.text3 }}>{ca.times_true}</td>
                      <td style={{ padding: "6px 10px", color: T.text3 }}>{ca.times_false}</td>
                      <td style={{ padding: "6px 10px", color: ca.avg_return_true >= 0 ? "#34d399" : "#f87171" }}>{ca.avg_return_true.toFixed(3)}%</td>
                      <td style={{ padding: "6px 10px", color: ca.avg_return_false >= 0 ? "#34d399" : "#f87171" }}>{ca.avg_return_false.toFixed(3)}%</td>
                      <td style={{
                        padding: "6px 10px", fontWeight: 700,
                        color: ca.predictive_value > 0 ? "#34d399" : ca.predictive_value < 0 ? "#f87171" : T.text3,
                      }}>{ca.predictive_value > 0 ? "+" : ""}{ca.predictive_value.toFixed(3)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Trade log (collapsible) */}
          {result.trades?.length > 0 && (
            <div style={{
              background: T.surface, border: `1px solid ${T.border}`, borderRadius: T.radius,
              padding: 16, marginBottom: 16,
            }}>
              <div
                onClick={() => setShowTrades(v => !v)}
                style={{
                  fontSize: 9, fontFamily: T.mono, color: T.text4, letterSpacing: "0.1em",
                  cursor: "pointer", display: "flex", justifyContent: "space-between", alignItems: "center",
                }}
              >
                <span>TRADE LOG ({result.trades.length} trades)</span>
                <span style={{ color: T.accent }}>{showTrades ? "\u25B2" : "\u25BC"}</span>
              </div>
              {showTrades && (
                <div style={{ overflowX: "auto", marginTop: 10 }}>
                  <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: T.mono, fontSize: 10 }}>
                    <thead>
                      <tr style={{ borderBottom: `1px solid ${T.border}` }}>
                        {["DATE", "SYMBOL", "ENTRY SIG", "EXIT SIG", "ENTRY", "EXIT", "P&L%", "BARS", "SIZE"].map(h => (
                          <th key={h} style={{ padding: "5px 8px", textAlign: "left", color: T.text4, fontSize: 8, letterSpacing: "0.1em", whiteSpace: "nowrap" }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {result.trades.map((t, i) => {
                        const d = t.entry_time ? new Date(t.entry_time).toLocaleDateString("en-US", { month: "short", day: "numeric" }) : "";
                        const entrySm = SIGNAL_META[t.entry_signal] || { color: T.text3 };
                        const exitSm = SIGNAL_META[t.exit_signal] || { color: T.text3 };
                        return (
                          <tr key={i} style={{ borderBottom: `1px solid ${T.border}` }}>
                            <td style={{ padding: "5px 8px", color: T.text3, whiteSpace: "nowrap" }}>{d}</td>
                            <td style={{ padding: "5px 8px", color: T.text2, fontWeight: 600 }}>{t.symbol?.replace("/USDT", "")}</td>
                            <td style={{ padding: "5px 8px", color: entrySm.color }}>{t.entry_signal}</td>
                            <td style={{ padding: "5px 8px", color: exitSm.color }}>{t.exit_signal || ""}</td>
                            <td style={{ padding: "5px 8px", color: T.text3 }}>{t.entry_price}</td>
                            <td style={{ padding: "5px 8px", color: T.text3 }}>{t.exit_price || ""}</td>
                            <td style={{ padding: "5px 8px", color: (t.pnl_pct ?? 0) >= 0 ? "#34d399" : "#f87171", fontWeight: 600 }}>{t.pnl_pct != null ? `${t.pnl_pct > 0 ? "+" : ""}${t.pnl_pct}%` : ""}</td>
                            <td style={{ padding: "5px 8px", color: T.text3 }}>{t.bars_held}</td>
                            <td style={{ padding: "5px 8px", color: T.text3 }}>{t.size_pct}%</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {/* Signal distribution */}
          {result.signal_distribution && (
            <div style={{
              background: T.surface, border: `1px solid ${T.border}`, borderRadius: T.radius,
              padding: 16,
            }}>
              <div style={{ fontSize: 9, fontFamily: T.mono, color: T.text4, letterSpacing: "0.1em", marginBottom: 10 }}>
                SIGNAL DISTRIBUTION ({result.bar_count} total bars)
              </div>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                {Object.entries(result.signal_distribution)
                  .sort((a, b) => b[1] - a[1])
                  .map(([sig, count]) => {
                    const sm = SIGNAL_META[sig] || { color: T.text3 };
                    const pct = result.bar_count > 0 ? (count / result.bar_count * 100).toFixed(1) : 0;
                    return (
                      <div key={sig} style={{
                        padding: "6px 12px", borderRadius: T.radiusXs,
                        background: "rgba(255,255,255,0.02)", border: `1px solid ${T.border}`,
                        display: "flex", gap: 8, alignItems: "center",
                      }}>
                        <span style={{ color: sm.color, fontFamily: T.mono, fontSize: 10, fontWeight: 600 }}>{sig}</span>
                        <span style={{ color: T.text4, fontFamily: T.mono, fontSize: 9 }}>{count} ({pct}%)</span>
                      </div>
                    );
                  })}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ─── INPUT FIELD ────────────────────────────────────────────────────────────

function InputField({ label, value, onChange, type = "text", placeholder, isMobile }) {
  return (
    <div style={{ flex: isMobile ? "1 1 100%" : undefined }}>
      <div style={{ fontSize: 8, color: T.text4, fontFamily: T.mono, letterSpacing: "0.1em", marginBottom: 4 }}>{label}</div>
      <input
        type={type}
        value={value}
        placeholder={placeholder}
        onChange={e => onChange(e.target.value)}
        style={{
          padding: "7px 12px", borderRadius: T.radiusSm,
          border: `1px solid ${T.border}`, background: "rgba(0,0,0,0.3)",
          color: T.text1, fontFamily: T.mono, fontSize: 11,
          width: type === "number" ? 100 : type === "date" ? 140 : 120,
          outline: "none",
        }}
      />
    </div>
  );
}
