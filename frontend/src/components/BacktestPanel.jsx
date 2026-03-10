import { useState, useEffect, useRef, useCallback } from "react";
import { T, SIGNAL_META, fmt, resolveToken } from "../theme.js";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";

const DEFAULT_SYMBOLS = [
  "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
  "ADA/USDT", "AVAX/USDT", "DOGE/USDT", "DOT/USDT", "LINK/USDT",
];

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
    ctx.strokeStyle = resolveToken("overlay04");
    ctx.lineWidth = 1;
    const gridLines = 5;
    for (let i = 0; i <= gridLines; i++) {
      const y = pad.t + (ch / gridLines) * i;
      ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(W - pad.r, y); ctx.stroke();
      const val = yMax - (yMax - yMin) * (i / gridLines);
      ctx.fillStyle = resolveToken("overlay25");
      ctx.font = "9px JetBrains Mono, monospace";
      ctx.textAlign = "right";
      ctx.fillText(`$${val.toFixed(0)}`, pad.l - 6, y + 3);
    }

    // Date labels
    if (equity.length > 2) {
      const dates = equity.map(p => new Date(p[0]));
      const labelCount = Math.min(6, equity.length);
      ctx.fillStyle = resolveToken("overlay20");
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

function ProgressBar({ progress, status, startedAt }) {
  const isReplaying = status === "REPLAYING";
  const elapsed = startedAt ? Math.floor((Date.now() / 1000) - startedAt) : 0;
  const elapsedStr = elapsed > 0 ? `${Math.floor(elapsed / 60)}m ${elapsed % 60}s` : "";
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!isReplaying) return;
    const iv = setInterval(() => setTick(t => t + 1), 1000);
    return () => clearInterval(iv);
  }, [isReplaying]);

  const displayLabel = isReplaying ? "REPLAYING \u2014 engines running..." : status;
  const displayProgress = isReplaying ? `${elapsedStr}` : `${progress.toFixed(0)}%`;

  return (
    <div style={{ marginTop: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
        <span style={{ fontSize: 10, color: T.text3, fontFamily: T.mono }}>{displayLabel}</span>
        <span style={{ fontSize: 10, color: T.accent, fontFamily: T.mono }}>{displayProgress}</span>
      </div>
      <div style={{ height: 4, background: T.overlay04, borderRadius: 2, overflow: "hidden" }}>
        {isReplaying ? (
          <div style={{
            width: "30%", height: "100%",
            background: `linear-gradient(90deg, transparent, ${T.accent}, transparent)`,
            borderRadius: 2,
            animation: "replayPulse 1.5s ease-in-out infinite",
          }} />
        ) : (
          <div style={{
            width: `${progress}%`, height: "100%",
            background: `linear-gradient(90deg, ${T.accent}, ${T.accent}cc)`,
            borderRadius: 2, transition: "width 0.5s ease",
          }} />
        )}
      </div>
      <style>{`@keyframes replayPulse { 0%,100% { opacity: 0.3; transform: translateX(0); } 50% { opacity: 1; transform: translateX(230%); } }`}</style>
    </div>
  );
}

// ─── SYMBOL PICKER ──────────────────────────────────────────────────────────

function SymbolPicker({ symbols, onChange, isMobile }) {
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState([]);
  const [showSearch, setShowSearch] = useState(false);
  const [loading, setLoading] = useState(false);
  const searchRef = useRef(null);
  const debounceRef = useRef(null);

  // Search for symbols with debounce
  useEffect(() => {
    if (!searchQuery || searchQuery.length < 1) {
      setSearchResults([]);
      return;
    }
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      setLoading(true);
      try {
        const resp = await fetch(`${API}/api/watchlist/search?q=${encodeURIComponent(searchQuery)}`);
        if (resp.ok) {
          const data = await resp.json();
          // Filter out already-selected symbols
          const filtered = (data.results || []).filter(r => !symbols.includes(r.symbol));
          setSearchResults(filtered.slice(0, 15));
        }
      } catch (e) { /* ignore */ }
      setLoading(false);
    }, 300);
    return () => clearTimeout(debounceRef.current);
  }, [searchQuery, symbols]);

  // Close dropdown on outside click
  useEffect(() => {
    if (!showSearch) return;
    const handler = (e) => {
      if (searchRef.current && !searchRef.current.contains(e.target)) {
        setShowSearch(false);
        setSearchQuery("");
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [showSearch]);

  const addSymbol = (sym) => {
    if (!symbols.includes(sym)) {
      onChange([...symbols, sym]);
    }
    setSearchQuery("");
    setSearchResults([]);
  };

  const removeSymbol = (sym) => {
    onChange(symbols.filter(s => s !== sym));
  };

  const loadWatchlist = async () => {
    try {
      const resp = await fetch(`${API}/api/watchlist`);
      if (resp.ok) {
        const data = await resp.json();
        onChange(data.symbols || []);
      }
    } catch (e) { /* ignore */ }
  };

  const formatChip = (sym) => {
    if (sym.endsWith("/BTC")) return sym.replace("/BTC", "/\u20bf");
    return sym.replace("/USDT", "");
  };

  const chipBg = (sym) => {
    if (sym.endsWith("/BTC")) return "rgba(251,146,60,0.1)";
    return T.overlay04;
  };

  const chipBorder = (sym) => {
    if (sym.endsWith("/BTC")) return "rgba(251,146,60,0.25)";
    return T.border;
  };

  return (
    <div style={{ marginTop: 10 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
        <div style={{ fontSize: 8, color: T.text4, fontFamily: T.mono, letterSpacing: "0.1em" }}>
          SYMBOLS ({symbols.length})
        </div>
        <div style={{ display: "flex", gap: 4, marginLeft: "auto" }}>
          <button onClick={() => onChange([...DEFAULT_SYMBOLS])} style={quickBtnStyle}>
            DEFAULT 10
          </button>
          <button onClick={loadWatchlist} style={quickBtnStyle}>
            WATCHLIST
          </button>
          <button onClick={() => onChange([])} style={{ ...quickBtnStyle, color: "#f87171" }}>
            CLEAR
          </button>
        </div>
      </div>

      {/* Symbol chips */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginBottom: 8 }}>
        {symbols.map(sym => (
          <div key={sym} style={{
            display: "inline-flex", alignItems: "center", gap: 4,
            padding: "3px 8px", borderRadius: T.radiusXs,
            background: chipBg(sym), border: `1px solid ${chipBorder(sym)}`,
            fontSize: 10, fontFamily: T.mono, color: T.text2,
          }}>
            <span>{formatChip(sym)}</span>
            <span
              onClick={() => removeSymbol(sym)}
              style={{ cursor: "pointer", color: T.text4, fontSize: 12, lineHeight: 1, marginLeft: 2 }}
            >
              {"\u00d7"}
            </span>
          </div>
        ))}

        {/* Add button / search */}
        <div ref={searchRef} style={{ position: "relative", display: "inline-block" }}>
          {showSearch ? (
            <input
              autoFocus
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value.toUpperCase())}
              placeholder="Type symbol..."
              onKeyDown={e => {
                if (e.key === "Escape") { setShowSearch(false); setSearchQuery(""); }
                if (e.key === "Enter" && searchResults.length > 0) addSymbol(searchResults[0].symbol);
              }}
              style={{
                padding: "3px 8px", borderRadius: T.radiusXs,
                border: `1px solid ${T.accent}`, background: "rgba(0,0,0,0.4)",
                color: T.text1, fontFamily: T.mono, fontSize: 10,
                width: 120, outline: "none",
              }}
            />
          ) : (
            <button
              onClick={() => setShowSearch(true)}
              style={{
                padding: "3px 10px", borderRadius: T.radiusXs,
                border: `1px dashed ${T.border}`, background: "transparent",
                color: T.text4, fontFamily: T.mono, fontSize: 10,
                cursor: "pointer",
              }}
            >
              + ADD
            </button>
          )}

          {/* Search dropdown */}
          {showSearch && searchResults.length > 0 && (
            <div style={{
              position: "absolute", top: "100%", left: 0, zIndex: 50,
              marginTop: 4, minWidth: 180, maxHeight: 200, overflowY: "auto",
              background: "#1a1a1e", border: `1px solid ${T.border}`,
              borderRadius: T.radiusSm, boxShadow: `0 8px 32px ${T.shadowDeep}`,
            }}>
              {searchResults.map(r => (
                <div
                  key={r.symbol}
                  onClick={() => addSymbol(r.symbol)}
                  style={{
                    padding: "6px 10px", cursor: "pointer",
                    fontSize: 10, fontFamily: T.mono, color: T.text2,
                    borderBottom: `1px solid ${T.border}`,
                    display: "flex", justifyContent: "space-between",
                  }}
                  onMouseEnter={e => e.currentTarget.style.background = T.overlay06}
                  onMouseLeave={e => e.currentTarget.style.background = "transparent"}
                >
                  <span>{r.symbol}</span>
                  <span style={{ color: r.quote === "BTC" ? "#fb923c" : T.text4, fontSize: 8 }}>
                    {r.quote}
                  </span>
                </div>
              ))}
            </div>
          )}
          {showSearch && loading && (
            <div style={{
              position: "absolute", top: "100%", left: 0, zIndex: 50,
              marginTop: 4, padding: "8px 12px",
              background: "#1a1a1e", border: `1px solid ${T.border}`,
              borderRadius: T.radiusSm, fontSize: 9, fontFamily: T.mono, color: T.text4,
            }}>
              Searching...
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

const quickBtnStyle = {
  padding: "2px 8px", borderRadius: "6px", border: `1px solid ${T.border}`,
  background: "transparent", color: T.text4, fontFamily: T.mono,
  fontSize: 8, cursor: "pointer", letterSpacing: "0.05em",
};

// ─── TIMEFRAME TOGGLE ───────────────────────────────────────────────────────

function TimeframeToggle({ value, onChange }) {
  const opts = ["4h", "1d"];
  return (
    <div>
      <div style={{ fontSize: 8, color: T.text4, fontFamily: T.mono, letterSpacing: "0.1em", marginBottom: 4 }}>TIMEFRAME</div>
      <div style={{ display: "flex", borderRadius: T.radiusSm, overflow: "hidden", border: `1px solid ${T.border}` }}>
        {opts.map(tf => (
          <button
            key={tf}
            onClick={() => onChange(tf)}
            style={{
              padding: "7px 14px", border: "none",
              background: value === tf ? T.accent : "rgba(0,0,0,0.3)",
              color: value === tf ? "#000" : T.text3,
              fontFamily: T.mono, fontSize: 11, fontWeight: value === tf ? 700 : 400,
              cursor: "pointer", letterSpacing: "0.04em",
            }}
          >
            {tf.toUpperCase()}
          </button>
        ))}
      </div>
    </div>
  );
}

// ─── MAIN PANEL ────────────────────────────────────────────────────────────

export default function BacktestPanel({ isMobile, onBacktestComplete }) {
  const [config, setConfig] = useState({
    start_date: "2025-01-01",
    end_date: "",
    initial_capital: 10000,
    symbols: [...DEFAULT_SYMBOLS],
    use_confluence: true,
    use_fear_greed: true,
    timeframe: "4h",
    leverage: 1.0,
  });
  const [btId, setBtId] = useState(null);
  const [result, setResult] = useState(null);
  const [polling, setPolling] = useState(false);
  const [error, setError] = useState(null);
  const [showTrades, setShowTrades] = useState(false);
  const pollRef = useRef(null);

  // Poll for results (silently retry on network errors during replay)
  const pollFailCount = useRef(0);
  const poll = useCallback(async (id) => {
    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 8000);
      const resp = await fetch(`${API}/api/backtest/${id}`, { signal: controller.signal });
      clearTimeout(timeout);
      if (!resp.ok) throw new Error("Poll failed");
      const data = await resp.json();
      setResult(data);
      pollFailCount.current = 0;
      if (data.status === "complete" || data.status === "error") {
        setPolling(false);
        if (data.error) setError(data.error);
        if (data.status === "complete" && onBacktestComplete) onBacktestComplete();
      }
    } catch (e) {
      // Server may be temporarily busy — silently retry (backtests can take 15+ min)
      pollFailCount.current += 1;
      if (pollFailCount.current > 600) {
        setError("Server unresponsive — backtest may still be running in the background");
        setPolling(false);
      }
    }
  }, []);

  useEffect(() => {
    if (polling && btId) {
      pollRef.current = setInterval(() => poll(btId), 3000);
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

  const formatSymbol = (sym) => {
    if (!sym) return "";
    if (sym.endsWith("/BTC")) return sym.replace("/BTC", "/\u20bf");
    return sym.replace("/USDT", "");
  };

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
          <InputField label="LEVERAGE" type="number" value={config.leverage}
            onChange={v => setConfig(c => ({ ...c, leverage: Math.max(0.1, Math.min(10, Number(v) || 1)) }))} isMobile={isMobile} />
          <TimeframeToggle value={config.timeframe}
            onChange={v => setConfig(c => ({ ...c, timeframe: v }))} />
          <button
            onClick={startBacktest}
            disabled={isRunning || config.symbols.length === 0}
            style={{
              padding: "8px 24px", borderRadius: "20px", border: "none",
              background: (isRunning || config.symbols.length === 0) ? T.text4 : T.accent,
              color: "#000", fontFamily: T.mono, fontSize: 11, fontWeight: 700,
              cursor: (isRunning || config.symbols.length === 0) ? "not-allowed" : "pointer",
              letterSpacing: "0.06em",
            }}
          >
            {isRunning ? "RUNNING..." : "RUN BACKTEST"}
          </button>
        </div>

        {/* Symbol picker */}
        <SymbolPicker
          symbols={config.symbols}
          onChange={syms => setConfig(c => ({ ...c, symbols: syms }))}
          isMobile={isMobile}
        />
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
          <ProgressBar progress={result.progress || 0} status={result.status?.toUpperCase() || "STARTING"} startedAt={result.started_at} />
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
                            <td style={{ padding: "5px 8px", color: T.text2, fontWeight: 600 }}>{formatSymbol(t.symbol)}</td>
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
                        background: T.overlay02, border: `1px solid ${T.border}`,
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
        step={type === "number" && label === "LEVERAGE" ? "0.5" : undefined}
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
