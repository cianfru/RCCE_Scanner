import { useState, useEffect, useCallback } from "react";
import { T, SIGNAL_META } from "../theme.js";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function timeAgo(ts) {
  if (!ts) return "\u2014";
  const diff = (Date.now() / 1000) - ts;
  if (diff < 60)   return `${Math.round(diff)}s ago`;
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
  if (diff < 86400) return `${(diff / 3600).toFixed(1)}h ago`;
  return `${(diff / 86400).toFixed(1)}d ago`;
}

function fullDate(ts) {
  if (!ts) return "";
  return new Date(ts * 1000).toLocaleString();
}

function fmtPct(pct) {
  if (pct == null) return "\u2014";
  const sign = pct >= 0 ? "+" : "";
  return `${sign}${pct.toFixed(2)}%`;
}

function pctColor(pct) {
  if (pct == null) return T.text4;
  return pct >= 0 ? "#34d399" : "#f87171";
}

function signalColor(sig) {
  return (SIGNAL_META[sig] || SIGNAL_META.WAIT).color;
}

function signalLabel(sig) {
  return (SIGNAL_META[sig] || { label: sig }).label;
}

function fmtPrice(p) {
  if (!p && p !== 0) return "\u2014";
  if (p >= 1000) return `$${p.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  if (p >= 1)    return `$${p.toFixed(4)}`;
  return `$${p.toFixed(6)}`;
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const S = {
  panel: { padding: 0 },
  section: {
    background: T.glassBg,
    border: `1px solid ${T.border}`,
    borderRadius: 14,
    padding: "20px 24px",
    marginBottom: 16,
    boxShadow: T.glassShadow,
  },
  sectionTitle: {
    fontSize: 11,
    fontWeight: 700,
    color: T.text3,
    letterSpacing: "0.1em",
    textTransform: "uppercase",
    marginBottom: 16,
    fontFamily: "'JetBrains Mono', monospace",
  },
  card: (borderColor) => ({
    flex: "1 1 180px",
    minWidth: 160,
    maxWidth: 260,
    background: T.surface,
    border: `1px solid ${borderColor}30`,
    borderRadius: 10,
    padding: "14px 16px",
    display: "flex",
    flexDirection: "column",
    gap: 6,
  }),
  cardSignal: (color) => ({
    fontSize: 11,
    fontWeight: 700,
    color: color,
    letterSpacing: "0.06em",
    fontFamily: "'JetBrains Mono', monospace",
  }),
  cardStat: {
    fontSize: 22,
    fontWeight: 700,
    color: T.text1,
    fontFamily: "'Inter', sans-serif",
  },
  cardLabel: {
    fontSize: 10,
    color: T.text4,
    letterSpacing: "0.06em",
    fontFamily: "'JetBrains Mono', monospace",
  },
  filterBar: {
    display: "flex",
    flexWrap: "wrap",
    gap: 8,
    marginBottom: 14,
    alignItems: "center",
  },
  select: {
    background: T.surface,
    color: T.text2,
    border: `1px solid ${T.border}`,
    borderRadius: 8,
    padding: "6px 10px",
    fontSize: 12,
    fontFamily: "'JetBrains Mono', monospace",
    cursor: "pointer",
  },
  input: {
    background: T.surface,
    color: T.text2,
    border: `1px solid ${T.border}`,
    borderRadius: 8,
    padding: "6px 10px",
    fontSize: 12,
    fontFamily: "'JetBrains Mono', monospace",
    width: 140,
    outline: "none",
  },
  table: {
    width: "100%",
    borderCollapse: "collapse",
    fontSize: 12,
    fontFamily: "'JetBrains Mono', monospace",
  },
  th: {
    textAlign: "left",
    padding: "8px 10px",
    borderBottom: `1px solid ${T.border}`,
    color: T.text3,
    fontSize: 10,
    fontWeight: 600,
    letterSpacing: "0.08em",
    textTransform: "uppercase",
    whiteSpace: "nowrap",
  },
  td: {
    padding: "7px 10px",
    borderBottom: `1px solid ${T.overlay04}`,
    color: T.text2,
    whiteSpace: "nowrap",
  },
  badge: (bg, color, border) => ({
    display: "inline-block",
    padding: "2px 8px",
    borderRadius: 6,
    fontSize: 10,
    fontWeight: 600,
    letterSpacing: "0.04em",
    background: bg,
    color: color,
    border: `1px solid ${border}`,
  }),
  pagination: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginTop: 12,
    gap: 8,
  },
  pageBtn: (disabled) => ({
    background: disabled ? T.overlay04 : T.surface,
    color: disabled ? T.text4 : T.text2,
    border: `1px solid ${T.border}`,
    borderRadius: 8,
    padding: "6px 14px",
    fontSize: 11,
    fontFamily: "'JetBrains Mono', monospace",
    cursor: disabled ? "default" : "pointer",
    opacity: disabled ? 0.5 : 1,
  }),
  empty: {
    textAlign: "center",
    padding: "40px 20px",
    color: T.text4,
    fontSize: 13,
    fontFamily: "'JetBrains Mono', monospace",
  },
};

// ---------------------------------------------------------------------------
// Scorecard
// ---------------------------------------------------------------------------

function Scorecard({ cards }) {
  if (!cards || cards.length === 0) {
    return (
      <div style={S.empty}>
        No signal data yet. Signals will appear after scan cycles detect transitions.
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
      {cards.map((c) => {
        const color = signalColor(c.signal);
        const borderColor = c.win_rate != null
          ? (c.win_rate >= 60 ? "#34d399" : c.win_rate < 40 ? "#f87171" : T.text4)
          : T.text4;

        return (
          <div key={c.signal} style={S.card(borderColor)}>
            <div style={S.cardSignal(color)}>{signalLabel(c.signal)}</div>
            <div style={S.cardStat}>
              {c.win_rate != null ? `${c.win_rate}%` : "\u2014"}
            </div>
            <div style={S.cardLabel}>
              {c.win_rate != null ? "WIN RATE (7D)" : "PENDING"}
            </div>

            <div style={{ display: "flex", gap: 12, marginTop: 4 }}>
              <div>
                <div style={{ fontSize: 10, color: T.text4 }}>COUNT</div>
                <div style={{ fontSize: 13, color: T.text2, fontWeight: 600 }}>{c.count}</div>
              </div>
              <div>
                <div style={{ fontSize: 10, color: T.text4 }}>AVG 1D</div>
                <div style={{ fontSize: 13, color: pctColor(c.avg_1d), fontWeight: 600 }}>
                  {fmtPct(c.avg_1d)}
                </div>
              </div>
              <div>
                <div style={{ fontSize: 10, color: T.text4 }}>AVG 7D</div>
                <div style={{ fontSize: 13, color: pctColor(c.avg_7d), fontWeight: 600 }}>
                  {fmtPct(c.avg_7d)}
                </div>
              </div>
            </div>

            {c.has_outcomes > 0 && (
              <div style={{ fontSize: 9, color: T.text4, marginTop: 2 }}>
                {c.wins}/{c.has_outcomes} wins &bull; {c.direction}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// History table
// ---------------------------------------------------------------------------

function HistoryTable({ events, total, offset, limit, onPage, isMobile }) {
  if (!events || events.length === 0) {
    return (
      <div style={S.empty}>
        No signal history yet. Events are logged when signals change between scan cycles.
      </div>
    );
  }

  const page = Math.floor(offset / limit) + 1;
  const totalPages = Math.ceil(total / limit);

  return (
    <>
      <div style={{ overflowX: "auto" }}>
        <table style={S.table}>
          <thead>
            <tr>
              <th style={S.th}>TIME</th>
              <th style={S.th}>SYMBOL</th>
              <th style={S.th}>SIGNAL</th>
              <th style={S.th}>PREV</th>
              <th style={S.th}>REGIME</th>
              <th style={S.th}>PRICE</th>
              {!isMobile && <th style={S.th}>Z</th>}
              {!isMobile && <th style={S.th}>HEAT</th>}
              <th style={{ ...S.th, textAlign: "right" }}>1D</th>
              <th style={{ ...S.th, textAlign: "right" }}>3D</th>
              <th style={{ ...S.th, textAlign: "right" }}>7D</th>
            </tr>
          </thead>
          <tbody>
            {events.map((e, i) => {
              const sigColor = signalColor(e.signal);
              const prevColor = e.prev_signal ? signalColor(e.prev_signal) : T.text4;
              return (
                <tr key={e.id || i} style={{ transition: "background 0.15s" }}
                    onMouseEnter={(ev) => ev.currentTarget.style.background = T.overlay04}
                    onMouseLeave={(ev) => ev.currentTarget.style.background = "transparent"}>
                  <td style={S.td} title={fullDate(e.timestamp)}>
                    {timeAgo(e.timestamp)}
                  </td>
                  <td style={{ ...S.td, color: T.text1, fontWeight: 600 }}>
                    {(e.symbol || "").replace("USDT", "")}
                  </td>
                  <td style={S.td}>
                    <span style={S.badge(`${sigColor}18`, sigColor, `${sigColor}40`)}>
                      {signalLabel(e.signal)}
                    </span>
                  </td>
                  <td style={S.td}>
                    {e.prev_signal ? (
                      <span style={{ color: prevColor, fontSize: 10 }}>
                        {signalLabel(e.prev_signal)}
                      </span>
                    ) : (
                      <span style={{ color: T.text4, fontSize: 10 }}>NEW</span>
                    )}
                  </td>
                  <td style={{ ...S.td, color: T.text3, fontSize: 10 }}>{e.regime}</td>
                  <td style={S.td}>{fmtPrice(e.price)}</td>
                  {!isMobile && (
                    <td style={{ ...S.td, color: T.text3 }}>
                      {e.zscore != null ? e.zscore.toFixed(2) : "\u2014"}
                    </td>
                  )}
                  {!isMobile && (
                    <td style={{ ...S.td, color: T.text3 }}>
                      {e.heat != null ? e.heat : "\u2014"}
                    </td>
                  )}
                  <td style={{ ...S.td, textAlign: "right", color: pctColor(e.outcome_1d_pct) }}>
                    {fmtPct(e.outcome_1d_pct)}
                  </td>
                  <td style={{ ...S.td, textAlign: "right", color: pctColor(e.outcome_3d_pct) }}>
                    {fmtPct(e.outcome_3d_pct)}
                  </td>
                  <td style={{ ...S.td, textAlign: "right", color: pctColor(e.outcome_7d_pct) }}>
                    {fmtPct(e.outcome_7d_pct)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div style={S.pagination}>
          <button
            style={S.pageBtn(page <= 1)}
            disabled={page <= 1}
            onClick={() => onPage(Math.max(0, offset - limit))}
          >
            &larr; PREV
          </button>
          <span style={{ fontSize: 11, color: T.text3, fontFamily: "'JetBrains Mono', monospace" }}>
            PAGE {page} / {totalPages} &bull; {total} events
          </span>
          <button
            style={S.pageBtn(page >= totalPages)}
            disabled={page >= totalPages}
            onClick={() => onPage(offset + limit)}
          >
            NEXT &rarr;
          </button>
        </div>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Main panel
// ---------------------------------------------------------------------------

export default function SignalLogPanel({ api, isMobile }) {
  const [timeframe, setTimeframe] = useState("4h");
  const [signalFilter, setSignalFilter] = useState("");
  const [symbolFilter, setSymbolFilter] = useState("");
  const [offset, setOffset] = useState(0);
  const LIMIT = 50;

  const [scorecard, setScorecard] = useState([]);
  const [history, setHistory] = useState({ events: [], total: 0 });
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    try {
      const params = new URLSearchParams({ timeframe, limit: LIMIT, offset });
      if (signalFilter) params.set("signal", signalFilter);
      if (symbolFilter) params.set("symbol", symbolFilter.toUpperCase());

      const [scRes, hRes] = await Promise.all([
        fetch(`${api}/api/signals/scorecard?timeframe=${timeframe}`).then(r => r.json()),
        fetch(`${api}/api/signals/history?${params}`).then(r => r.json()),
      ]);

      setScorecard(scRes.cards || []);
      setHistory({ events: hRes.events || [], total: hRes.total || 0 });
    } catch (err) {
      console.error("Signal log fetch failed:", err);
    } finally {
      setLoading(false);
    }
  }, [api, timeframe, signalFilter, symbolFilter, offset]);

  useEffect(() => {
    setLoading(true);
    fetchData();
    const iv = setInterval(fetchData, 60_000); // refresh every 60s
    return () => clearInterval(iv);
  }, [fetchData]);

  // Reset offset when filters change
  useEffect(() => {
    setOffset(0);
  }, [timeframe, signalFilter, symbolFilter]);

  const allSignals = [
    "STRONG_LONG", "LIGHT_LONG", "ACCUMULATE", "REVIVAL_SEED",
    "TRIM", "TRIM_HARD", "RISK_OFF", "NO_LONG", "LIGHT_SHORT",
  ];

  return (
    <div style={S.panel}>
      {/* Scorecard */}
      <div style={S.section}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
          <div style={S.sectionTitle}>SIGNAL SCORECARD</div>
          <div style={{ display: "flex", gap: 6 }}>
            {["4h", "1d"].map(tf => (
              <button
                key={tf}
                onClick={() => setTimeframe(tf)}
                style={{
                  background: timeframe === tf ? T.accent : T.surface,
                  color: timeframe === tf ? "#000" : T.text3,
                  border: `1px solid ${timeframe === tf ? T.accent : T.border}`,
                  borderRadius: 6,
                  padding: "4px 12px",
                  fontSize: 11,
                  fontWeight: 600,
                  fontFamily: "'JetBrains Mono', monospace",
                  cursor: "pointer",
                  letterSpacing: "0.06em",
                }}
              >
                {tf.toUpperCase()}
              </button>
            ))}
          </div>
        </div>
        {loading && scorecard.length === 0 ? (
          <div style={S.empty}>Loading scorecard...</div>
        ) : (
          <Scorecard cards={scorecard} />
        )}
      </div>

      {/* History */}
      <div style={S.section}>
        <div style={S.sectionTitle}>SIGNAL HISTORY</div>

        <div style={S.filterBar}>
          <select
            style={S.select}
            value={signalFilter}
            onChange={e => setSignalFilter(e.target.value)}
          >
            <option value="">ALL SIGNALS</option>
            {allSignals.map(s => (
              <option key={s} value={s}>{signalLabel(s)}</option>
            ))}
          </select>
          <input
            style={S.input}
            type="text"
            placeholder="SYMBOL..."
            value={symbolFilter}
            onChange={e => setSymbolFilter(e.target.value)}
          />
          <span style={{ fontSize: 10, color: T.text4, fontFamily: "'JetBrains Mono', monospace" }}>
            {history.total} events
          </span>
        </div>

        {loading && history.events.length === 0 ? (
          <div style={S.empty}>Loading history...</div>
        ) : (
          <HistoryTable
            events={history.events}
            total={history.total}
            offset={offset}
            limit={LIMIT}
            onPage={setOffset}
            isMobile={isMobile}
          />
        )}
      </div>
    </div>
  );
}
