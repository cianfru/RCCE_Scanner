import { useState, useEffect, useRef, useCallback } from "react";
import { T, SIGNAL_META, fmt, resolveToken, col } from "../theme.js";
import { useTheme } from "../ThemeContext.jsx";
import Tabs from "./Tabs.jsx";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";

const DEFAULT_SYMBOLS = [
  "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
  "ADA/USDT", "AVAX/USDT", "DOGE/USDT", "DOT/USDT", "LINK/USDT",
];

// ─── EQUITY CURVE CHART ──────────────────────────────────────────────────────

function EquityChart({ equity, btcEquity, height = 260 }) {
  const canvasRef = useRef(null);
  const { mode } = useTheme();
  const [width, setWidth] = useState(0);

  // Redraw when the container is resized.
  useEffect(() => {
    const parent = canvasRef.current?.parentElement;
    if (!parent) return;
    const ro = new ResizeObserver(() => setWidth(parent.clientWidth));
    ro.observe(parent);
    return () => ro.disconnect();
  }, [equity?.length]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !equity?.length) return;
    const ctx = canvas.getContext("2d");
    // Draw at device resolution so text stays sharp on high-density screens.
    const dpr = window.devicePixelRatio || 1;
    const W = canvas.parentElement.clientWidth;
    const H = height;
    canvas.width = W * dpr;
    canvas.height = H * dpr;
    canvas.style.height = `${H}px`;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W, H);

    const font = `12px ${getComputedStyle(document.documentElement).getPropertyValue("--font-geist-mono") || "monospace"}`;
    const textColor = resolveToken("chartText");
    const strategyColor = resolveToken("accent");
    const btcColor = col("#fb923c");

    const pad = { t: 28, b: 36, l: 64, r: 16 };
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
    ctx.strokeStyle = resolveToken("chartGrid");
    ctx.lineWidth = 1;
    ctx.font = font;
    const gridLines = 5;
    for (let i = 0; i <= gridLines; i++) {
      const y = pad.t + (ch / gridLines) * i;
      ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(W - pad.r, y); ctx.stroke();
      const val = yMax - (yMax - yMin) * (i / gridLines);
      ctx.fillStyle = textColor;
      ctx.textAlign = "right";
      ctx.fillText(`$${val.toFixed(0)}`, pad.l - 6, y + 4);
    }

    // Date labels
    if (equity.length > 2) {
      const dates = equity.map(p => new Date(p[0]));
      const labelCount = Math.min(W < 480 ? 4 : 6, equity.length);
      ctx.fillStyle = textColor;
      ctx.textAlign = "center";
      for (let i = 0; i < labelCount; i++) {
        const idx = Math.floor((i / (labelCount - 1)) * (dates.length - 1));
        const d = dates[idx];
        const label = `${d.getMonth() + 1}/${d.getDate()}`;
        ctx.fillText(label, toX(idx, equity.length), H - pad.b + 18);
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
        ctx.globalAlpha = 0.06;
        ctx.fillStyle = color;
        ctx.fill();
        ctx.globalAlpha = 1;
      }
    };

    // BTC benchmark (dashed)
    drawLine(btcEquity, btcColor, true);
    // Strategy (solid accent)
    drawLine(equity, strategyColor, false);

    // Legend
    ctx.setLineDash([]);
    const legendY = 14;
    ctx.textAlign = "left";

    ctx.fillStyle = strategyColor;
    ctx.fillRect(pad.l, legendY - 4, 12, 2);
    ctx.fillStyle = textColor;
    ctx.fillText("Strategy", pad.l + 16, legendY);

    ctx.strokeStyle = btcColor;
    ctx.setLineDash([3, 3]);
    ctx.beginPath(); ctx.moveTo(pad.l + 96, legendY - 3); ctx.lineTo(pad.l + 108, legendY - 3); ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillText("BTC buy and hold", pad.l + 112, legendY);

  }, [equity, btcEquity, height, mode, width]);

  if (!equity?.length) return null;
  return <canvas ref={canvasRef} role="img" aria-label="Strategy equity curve against BTC buy and hold" style={{ width: "100%", display: "block" }} />;
}

// ─── METRIC CARD ────────────────────────────────────────────────────────────

function MetricCard({ label, value, suffix = "", positive, isMobile }) {
  const color = positive === true ? T.green : positive === false ? T.red : T.text1;
  return (
    <div style={{
      flex: 1, minWidth: isMobile ? 100 : 120,
      background: T.surface, border: `1px solid ${T.border}`, borderRadius: T.radiusSm,
      padding: isMobile ? "10px 12px" : "12px 16px",
    }}>
      <div style={{ fontSize: T.textXs, color: T.text3, marginBottom: 4 }}>
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

  const displayLabel = isReplaying ? "Replaying \u2014 engines running..." : status;
  const displayProgress = isReplaying ? `${elapsedStr}` : `${progress.toFixed(0)}%`;

  return (
    <div style={{ marginTop: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
        <span style={{ fontSize: T.textXs, color: T.text3, fontFamily: T.mono }}>{displayLabel}</span>
        <span style={{ fontSize: T.textXs, color: T.accent, fontFamily: T.mono }}>{displayProgress}</span>
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

  return (
    <div style={{ marginTop: 14 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8, flexWrap: "wrap" }}>
        <div style={fieldLabel}>
          Symbols ({symbols.length})
        </div>
        <div style={{ display: "flex", gap: 12, marginLeft: "auto" }}>
          <button type="button" className="terminal-status" onClick={() => onChange([...DEFAULT_SYMBOLS])} style={quickBtnStyle}>
            Default 10
          </button>
          <button type="button" className="terminal-status" onClick={loadWatchlist} style={quickBtnStyle}>
            Watchlist
          </button>
          <button type="button" className="terminal-status" onClick={() => onChange([])} style={{ ...quickBtnStyle, color: T.red }}>
            Clear
          </button>
        </div>
      </div>

      {/* Selected symbols: flat text with a remove control each */}
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "4px 0", marginBottom: 8 }}>
        {symbols.map(sym => (
          <span key={sym} style={{
            display: "inline-flex", alignItems: "center", gap: 4,
            padding: "2px 10px", borderRight: `1px solid ${T.border}`,
            fontSize: T.textXs, fontFamily: T.mono,
            color: sym.endsWith("/BTC") ? col("#fb923c") : T.text2,
          }}>
            <span>{formatChip(sym)}</span>
            <button
              type="button"
              onClick={() => removeSymbol(sym)}
              aria-label={`Remove ${formatChip(sym)}`}
              style={{ cursor: "pointer", color: T.text3, fontSize: 14, lineHeight: 1, background: "transparent", border: 0, padding: "0 2px" }}
            >
              {"\u00d7"}
            </button>
          </span>
        ))}

        {/* Add button / search */}
        <div ref={searchRef} style={{ position: "relative", display: "inline-block", marginLeft: 10 }}>
          {showSearch ? (
            <input
              autoFocus
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value.toUpperCase())}
              placeholder="Type symbol..."
              aria-label="Search symbols to add"
              onKeyDown={e => {
                if (e.key === "Escape") { setShowSearch(false); setSearchQuery(""); }
                if (e.key === "Enter" && searchResults.length > 0) addSymbol(searchResults[0].symbol);
              }}
              style={{
                padding: "4px 8px", borderRadius: 6,
                border: `1px solid ${T.accent}`, background: "transparent",
                color: T.text1, fontFamily: T.mono, fontSize: T.textXs,
                width: 140, outline: "none",
              }}
            />
          ) : (
            <button
              type="button"
              className="terminal-status"
              onClick={() => setShowSearch(true)}
              style={{ ...quickBtnStyle, color: T.accent }}
            >
              + Add
            </button>
          )}

          {/* Search dropdown */}
          {showSearch && searchResults.length > 0 && (
            <div style={{
              position: "absolute", top: "100%", left: 0, zIndex: 50,
              marginTop: 4, minWidth: 200, maxHeight: 220, overflowY: "auto",
              background: T.popoverBg, border: `1px solid ${T.border}`,
              borderRadius: T.radiusXs, boxShadow: `0 8px 32px ${T.shadowDeep}`,
            }}>
              {searchResults.map(r => (
                <button
                  type="button"
                  key={r.symbol}
                  onClick={() => addSymbol(r.symbol)}
                  style={{
                    width: "100%", padding: "8px 10px", cursor: "pointer", textAlign: "left",
                    fontSize: T.textXs, fontFamily: T.mono, color: T.text2,
                    background: "transparent", border: 0, borderBottom: `1px solid ${T.border}`,
                    display: "flex", justifyContent: "space-between", gap: 12,
                  }}
                  onMouseEnter={e => e.currentTarget.style.background = T.overlay06}
                  onMouseLeave={e => e.currentTarget.style.background = "transparent"}
                >
                  <span>{r.symbol}</span>
                  <span style={{ color: r.quote === "BTC" ? col("#fb923c") : T.text3 }}>
                    {r.quote}
                  </span>
                </button>
              ))}
            </div>
          )}
          {showSearch && loading && (
            <div style={{
              position: "absolute", top: "100%", left: 0, zIndex: 50,
              marginTop: 4, padding: "8px 12px",
              background: T.popoverBg, border: `1px solid ${T.border}`,
              borderRadius: T.radiusXs, fontSize: T.textXs, fontFamily: T.mono, color: T.text3,
            }}>
              Searching...
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

const fieldLabel = { fontSize: T.textXs, color: T.text3, marginBottom: 4 };

const quickBtnStyle = {
  color: T.text2, fontFamily: T.mono, fontSize: T.textXs, cursor: "pointer",
};

// ─── TIMEFRAME TOGGLE ───────────────────────────────────────────────────────

function TimeframeToggle({ value, onChange }) {
  return (
    <div>
      <div style={fieldLabel}>Timeframe</div>
      <Tabs small label="Timeframe" value={value} onChange={onChange}
        items={[{ key: "4h", label: "4H" }, { key: "1d", label: "1D" }]} />
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
        <div style={{ fontSize: T.textSm, color: T.text2, fontWeight: 600, marginBottom: 14 }}>
          Backtest configuration
        </div>
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "flex-end" }}>
          <InputField label="Start" type="date" value={config.start_date}
            onChange={v => setConfig(c => ({ ...c, start_date: v }))} isMobile={isMobile} />
          <InputField label="End" type="date" value={config.end_date} placeholder="today"
            onChange={v => setConfig(c => ({ ...c, end_date: v }))} isMobile={isMobile} />
          <InputField label="Capital" type="number" value={config.initial_capital}
            onChange={v => setConfig(c => ({ ...c, initial_capital: Number(v) }))} isMobile={isMobile} />
          <InputField label="Leverage" type="number" value={config.leverage}
            onChange={v => setConfig(c => ({ ...c, leverage: Math.max(0.1, Math.min(10, Number(v) || 1)) }))} isMobile={isMobile} />
          <TimeframeToggle value={config.timeframe}
            onChange={v => setConfig(c => ({ ...c, timeframe: v }))} />
          <button
            onClick={startBacktest}
            disabled={isRunning || config.symbols.length === 0}
            className="terminal-status" style={{
              color: (isRunning || config.symbols.length === 0) ? T.text4 : T.accent,
              fontFamily: T.mono, fontSize: 12, fontWeight: 700,
              cursor: (isRunning || config.symbols.length === 0) ? "not-allowed" : "pointer",
            }}
          >
            {isRunning ? "Running…" : "Run backtest"}
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
          background: "transparent", border: `1px solid ${T.red}`,
          color: T.red, fontSize: T.textXs, fontFamily: T.mono,
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
            <div style={{ fontSize: T.textXs, color: T.text3, fontFamily: T.mono, marginTop: 8 }}>
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
            <div style={sectionLabel}>
              Equity curve
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
              <div style={sectionLabel}>
                Signal accuracy
              </div>
              <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: T.mono, fontSize: T.textXs }}>
                <thead>
                  <tr style={{ borderBottom: `1px solid ${T.border}` }}>
                    {["Signal", "Count", "Win rate", "Avg return", "Total P&L", "Avg bars"].map(h => (
                      <th key={h} style={thStyle}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(result.signal_stats).map(([sig, s]) => {
                    const sm = SIGNAL_META[sig] || { color: T.text3 };
                    const wrColor = s.win_rate >= 60 ? T.green : s.win_rate >= 50 ? T.yellow : T.red;
                    return (
                      <tr key={sig} style={{ borderBottom: `1px solid ${T.border}` }}>
                        <td style={{ padding: "6px 10px", color: sm.color, fontWeight: 600 }}>{signalLabel(sig)}</td>
                        <td style={{ padding: "6px 10px", color: T.text2 }}>{s.count}</td>
                        <td style={{ padding: "6px 10px", color: wrColor, fontWeight: 600 }}>{s.win_rate.toFixed(0)}%</td>
                        <td style={{ padding: "6px 10px", color: s.avg_return_pct >= 0 ? T.green : T.red }}>{s.avg_return_pct.toFixed(2)}%</td>
                        <td style={{ padding: "6px 10px", color: s.total_pnl_pct >= 0 ? T.green : T.red }}>{s.total_pnl_pct.toFixed(2)}%</td>
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
              <div style={sectionLabel}>
                Condition predictive value
              </div>
              <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: T.mono, fontSize: T.textXs }}>
                <thead>
                  <tr style={{ borderBottom: `1px solid ${T.border}` }}>
                    {["Condition", "True", "False", "Avg return (true)", "Avg return (false)", "Value"].map(h => (
                      <th key={h} style={thStyle}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {result.condition_analysis.map((ca, i) => (
                    <tr key={i} style={{ borderBottom: `1px solid ${T.border}` }}>
                      <td style={{ padding: "6px 10px", color: T.text2, maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis" }}>{ca.name}</td>
                      <td style={{ padding: "6px 10px", color: T.text3 }}>{ca.times_true}</td>
                      <td style={{ padding: "6px 10px", color: T.text3 }}>{ca.times_false}</td>
                      <td style={{ padding: "6px 10px", color: ca.avg_return_true >= 0 ? T.green : T.red }}>{ca.avg_return_true.toFixed(3)}%</td>
                      <td style={{ padding: "6px 10px", color: ca.avg_return_false >= 0 ? T.green : T.red }}>{ca.avg_return_false.toFixed(3)}%</td>
                      <td style={{
                        padding: "6px 10px", fontWeight: 700,
                        color: ca.predictive_value > 0 ? T.green : ca.predictive_value < 0 ? T.red : T.text3,
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
              <button
                type="button"
                onClick={() => setShowTrades(v => !v)}
                aria-expanded={showTrades}
                style={{
                  width: "100%", background: "transparent", border: 0, padding: 0,
                  fontSize: T.textXs, color: T.text3,
                  cursor: "pointer", display: "flex", justifyContent: "space-between", alignItems: "center",
                }}
              >
                <span>Trade log ({result.trades.length} trades)</span>
                <span style={{ color: T.accent }}>{showTrades ? "Hide" : "Show"}</span>
              </button>
              {showTrades && (
                <div style={{ overflowX: "auto", marginTop: 10 }}>
                  <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: T.mono, fontSize: T.textXs }}>
                    <thead>
                      <tr style={{ borderBottom: `1px solid ${T.border}` }}>
                        {["Date", "Symbol", "Entry signal", "Exit signal", "Entry", "Exit", "P&L %", "Bars", "Size"].map(h => (
                          <th key={h} style={{ ...thStyle, padding: "5px 8px", whiteSpace: "nowrap" }}>{h}</th>
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
                            <td style={{ padding: "5px 8px", color: entrySm.color }}>{signalLabel(t.entry_signal)}</td>
                            <td style={{ padding: "5px 8px", color: exitSm.color }}>{t.exit_signal ? signalLabel(t.exit_signal) : ""}</td>
                            <td style={{ padding: "5px 8px", color: T.text3 }}>{t.entry_price}</td>
                            <td style={{ padding: "5px 8px", color: T.text3 }}>{t.exit_price || ""}</td>
                            <td style={{ padding: "5px 8px", color: (t.pnl_pct ?? 0) >= 0 ? T.green : T.red, fontWeight: 600 }}>{t.pnl_pct != null ? `${t.pnl_pct > 0 ? "+" : ""}${t.pnl_pct}%` : ""}</td>
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
              <div style={sectionLabel}>
                Signal distribution ({result.bar_count} total bars)
              </div>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                {Object.entries(result.signal_distribution)
                  .sort((a, b) => b[1] - a[1])
                  .map(([sig, count]) => {
                    const sm = SIGNAL_META[sig] || { color: T.text3 };
                    const pct = result.bar_count > 0 ? (count / result.bar_count * 100).toFixed(1) : 0;
                    return (
                      <div key={sig} style={{
                        padding: "2px 12px 2px 0", marginRight: 4, borderRight: `1px solid ${T.border}`,
                        display: "flex", gap: 8, alignItems: "center",
                      }}>
                        <span style={{ color: sm.color, fontFamily: T.mono, fontSize: T.textXs, fontWeight: 600 }}>{signalLabel(sig)}</span>
                        <span style={{ color: T.text3, fontFamily: T.mono, fontSize: T.textXs }}>{count} ({pct}%)</span>
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
      <div style={fieldLabel}>{label}</div>
      <input
        type={type}
        value={value}
        placeholder={placeholder}
        onChange={e => onChange(e.target.value)}
        step={type === "number" && label === "Leverage" ? "0.5" : undefined}
        aria-label={label}
        style={{
          padding: "7px 12px", borderRadius: 6,
          border: `1px solid ${T.border}`, background: "transparent",
          color: T.text1, fontFamily: T.mono, fontSize: T.textSm,
          width: type === "number" ? 100 : type === "date" ? 140 : 120,
          outline: "none",
        }}
      />
    </div>
  );
}

const sectionLabel = { fontSize: T.textXs, color: T.text3, marginBottom: 10 };
const thStyle = { padding: "6px 10px", textAlign: "left", color: T.text3, fontSize: T.textXs, fontWeight: 500 };
const signalLabel = sig => SIGNAL_META[sig]?.label ?? String(sig).replaceAll("_", " ");
