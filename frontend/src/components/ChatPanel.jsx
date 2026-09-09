import { useState, useEffect, useRef, useCallback } from "react";
import { T, m } from "../theme.js";
import { useWallet } from "../WalletContext.jsx";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

/** Parse markdown table lines into { headers, alignments, rows } or null */
function parseTable(lines, startIdx) {
  if (startIdx + 1 >= lines.length) return null;
  const headerLine = lines[startIdx];
  const sepLine = lines[startIdx + 1];
  // Header must have pipes and separator must be |---|---|
  if (!headerLine.includes("|") || !/^\|?[\s:]*-{2,}/.test(sepLine)) return null;
  const parseCells = (line) =>
    line.replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
  const headers = parseCells(headerLine);
  const sepCells = parseCells(sepLine);
  // Validate separator row
  if (!sepCells.every((c) => /^:?-{2,}:?$/.test(c))) return null;
  const alignments = sepCells.map((c) => {
    if (c.startsWith(":") && c.endsWith(":")) return "center";
    if (c.endsWith(":")) return "right";
    return "left";
  });
  const rows = [];
  let i = startIdx + 2;
  while (i < lines.length && lines[i].includes("|") && lines[i].trim() !== "") {
    rows.push(parseCells(lines[i]));
    i++;
  }
  return { headers, alignments, rows, endIdx: i };
}

/** Lightweight markdown→JSX for assistant messages (no deps). */
function MdText({ text, isMobile }) {
  const lines = text.split("\n");
  const elements = [];
  let key = 0;
  const baseFz = m(T.textBase, isMobile);
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // ── Table detection ──
    const table = parseTable(lines, i);
    if (table) {
      const cellPad = isMobile ? "6px 8px" : "7px 12px";
      const cellFz = isMobile ? baseFz - 1 : baseFz;
      elements.push(
        <div key={key++} style={{
          overflowX: "auto", margin: "10px 0",
          WebkitOverflowScrolling: "touch",
          borderRadius: 8,
          border: `1px solid ${T.border}`,
        }}>
          <table style={{
            width: "100%", borderCollapse: "collapse",
            fontFamily: T.mono, fontSize: cellFz,
          }}>
            <thead>
              <tr>
                {table.headers.map((h, ci) => (
                  <th key={ci} style={{
                    padding: cellPad, textAlign: table.alignments[ci] || "left",
                    fontWeight: 700, color: T.accent,
                    borderBottom: `2px solid ${T.border}`,
                    background: T.overlay06,
                    whiteSpace: "nowrap",
                  }}>
                    {renderInline(h)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {table.rows.map((row, ri) => (
                <tr key={ri}>
                  {row.map((cell, ci) => (
                    <td key={ci} style={{
                      padding: cellPad,
                      textAlign: (table.alignments[ci] || "left"),
                      color: T.text1,
                      borderBottom: `1px solid ${T.overlay08}`,
                      whiteSpace: isMobile ? "normal" : "nowrap",
                    }}>
                      {renderInline(cell)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
      i = table.endIdx;
      continue;
    }

    // ── Headings ──
    if (/^#{1,3}\s/.test(line)) {
      const level = line.match(/^(#+)/)[1].length;
      const content = line.replace(/^#+\s*/, "");
      const sz = level === 1 ? baseFz + 4 : level === 2 ? baseFz + 2 : baseFz + 1;
      elements.push(
        <div key={key++} style={{
          fontSize: sz, fontWeight: 700, color: T.accent,
          fontFamily: T.font,
          marginTop: level === 1 ? 16 : 12, marginBottom: 8,
          letterSpacing: "-0.01em",
        }}>
          {renderInline(content)}
        </div>
      );
    } else if (/^---+$/.test(line.trim())) {
      elements.push(
        <hr key={key++} style={{
          border: "none", borderTop: `1px solid ${T.border}`,
          margin: "12px 0",
        }} />
      );
    } else if (/^\s*[-•]\s/.test(line)) {
      const indent = (line.match(/^(\s*)/)[1].length / 2) | 0;
      const content = line.replace(/^\s*[-•]\s*/, "");
      elements.push(
        <div key={key++} style={{
          paddingLeft: 18 + indent * 16,
          position: "relative", marginBottom: 4, fontSize: baseFz,
        }}>
          <span style={{ position: "absolute", left: indent * 16, color: T.text4 }}>•</span>
          {renderInline(content)}
        </div>
      );
    } else if (/^\s*\d+\.\s/.test(line)) {
      const match = line.match(/^(\s*)(\d+)\.\s(.*)/);
      const indent = (match[1].length / 2) | 0;
      elements.push(
        <div key={key++} style={{
          paddingLeft: 18 + indent * 16,
          position: "relative", marginBottom: 4, fontSize: baseFz,
        }}>
          <span style={{ position: "absolute", left: indent * 16, color: T.text4 }}>{match[2]}.</span>
          {renderInline(match[3])}
        </div>
      );
    } else if (line.trim() === "") {
      elements.push(<div key={key++} style={{ height: 10 }} />);
    } else {
      elements.push(<div key={key++} style={{ fontSize: baseFz }}>{renderInline(line)}</div>);
    }
    i++;
  }
  return <>{elements}</>;
}

/** Render inline markdown: **bold**, *italic*, `code` */
function renderInline(text) {
  const parts = [];
  let remaining = text;
  let i = 0;
  const re = /(\*\*(.+?)\*\*|\*(.+?)\*|`(.+?)`)/g;
  let lastIdx = 0;
  let match;
  while ((match = re.exec(remaining)) !== null) {
    if (match.index > lastIdx) {
      parts.push(<span key={i++}>{remaining.slice(lastIdx, match.index)}</span>);
    }
    if (match[2]) {
      parts.push(<span key={i++} style={{ fontWeight: 700, color: T.text1 }}>{match[2]}</span>);
    } else if (match[3]) {
      parts.push(<span key={i++} style={{ fontStyle: "italic", color: T.text2 }}>{match[3]}</span>);
    } else if (match[4]) {
      parts.push(
        <span key={i++} style={{
          background: T.overlay08, padding: "2px 7px",
          borderRadius: 5, fontSize: "0.9em", color: T.accent,
          fontFamily: T.mono,
        }}>{match[4]}</span>
      );
    }
    lastIdx = match.index + match[0].length;
  }
  if (lastIdx < remaining.length) {
    parts.push(<span key={i++}>{remaining.slice(lastIdx)}</span>);
  }
  return parts.length > 0 ? parts : text;
}

function getSessionId() {
  let id = sessionStorage.getItem("rcce-chat-session");
  if (!id) {
    id = "web-" + Math.random().toString(36).slice(2, 10);
    sessionStorage.setItem("rcce-chat-session", id);
  }
  return id;
}

const QUICK_ACTIONS = [
  { label: "Briefing", msg: "Give me a daily market briefing." },
  { label: "Entry conditions", msg: "Explain what the entry conditions mean for BTC and which currently pass." },
  { label: "Top Signals", msg: "What are the strongest signals right now?" },
  { label: "Risk Check", msg: "Are there any risk warnings I should know about?" },
];

export default function ChatPanel({ isMobile, selectedSymbol }) {
  const { address: walletAddress } = useWallet();
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const endRef = useRef(null);
  const sessionId = useRef(getSessionId());
  const inputRef = useRef(null);

  // Scroll window to top on mount
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "instant" });
  }, []);

  // Scroll chat to bottom only when new messages arrive
  useEffect(() => {
    if (messages.length > 0) {
      endRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages]);

  const send = useCallback(async (text) => {
    if (!text.trim() || loading) return;
    const userMsg = { role: "user", content: text };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);
    setError(null);

    try {
      const res = await fetch(`${API_BASE}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: text,
          session_id: sessionId.current,
          symbol: selectedSymbol || null,
          timeframe: "1d",
          wallet_address: walletAddress || null,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `API error ${res.status}`);
      }
      const data = await res.json();
      setMessages((prev) => [...prev, { role: "assistant", content: data.reply }]);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [selectedSymbol, walletAddress, loading]);

  const handleKey = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send(input);
    }
  };

  const clearChat = () => {
    setMessages([]);
    setError(null);
    sessionStorage.removeItem("rcce-chat-session");
    sessionId.current = getSessionId();
  };

  // ── Full-immersion chat layout ──────────────────────────────────────────────

  return (
    <div style={{
      display: "flex", flexDirection: "column",
      ...(isMobile
        ? { position: "fixed", top: 65, left: 0, right: 0, bottom: 0, zIndex: 10 }
        : { height: "calc(100vh - 120px)" }),
      maxWidth: isMobile ? "100%" : 860, margin: "0 auto", width: "100%",
      padding: 0,
      background: T.bg,
      overflow: "hidden",
    }}>
      {/* ── Top bar: model + clear ── */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: isMobile ? "4px 4px" : "10px 0",
        flexShrink: 0,
        position: "relative",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{color:T.text3,fontSize:13}}>AI Assist · Scanner analysis · 1D</span>
        </div>
        <button onClick={clearChat} className="apple-btn" style={{
          padding: isMobile ? "8px 16px" : "6px 14px",
          fontSize: m(T.textSm, isMobile), fontFamily: T.font,
          fontWeight: 600, color: T.text3, cursor: "pointer",
        }}>
          Clear
        </button>
      </div>

      {/* ── Messages area (fills available space) ── */}
      <div style={{
        flex: 1, overflowY: "auto", minHeight: 0,
        padding: isMobile ? "8px 2px" : "12px 0",
        scrollbarWidth: "thin",
        scrollbarColor: `${T.scrollThumb} transparent`,
        WebkitOverflowScrolling: "touch",
        overscrollBehavior: "contain",
      }}>
        {messages.length === 0 && (
          <div style={{
            display: "flex", flexDirection: "column",
            alignItems: "center",
            justifyContent: isMobile ? "flex-start" : "center",
            height: "100%",
            padding: isMobile ? "20px 20px 0" : "40px 20px", textAlign: "center",
          }}>
            <img src="/brand/reflex-ribbon-transparent.svg" alt="Reflex AI" style={{width:100,height:120,objectFit:"contain",marginBottom:24}} />
            <h2 style={{fontSize:24,fontWeight:500,color:T.text1,lineHeight:1.3}}>Understand the setup.</h2>
            <p style={{fontSize:14,color:T.text3,lineHeight:1.7,maxWidth:390,marginTop:12}}>Ask about a Hyperliquid signal, its entry conditions, or the evidence that disagrees.</p>

            {/* Quick actions */}
            <div style={{
              display: "flex", gap: isMobile ? 8 : 10, marginTop: isMobile ? 8 : 24,
              flexWrap: "wrap", justifyContent: "center",
            }}>
              {QUICK_ACTIONS.map((qa, i) => (
                <button
                  key={i}
                  onClick={() => send(qa.msg)}
                  disabled={loading}
                  className="apple-btn"
                  style={{
                    padding: isMobile ? "10px 18px" : "8px 16px",
                    fontSize: m(T.textSm, isMobile), fontFamily: T.font,
                    fontWeight: 600, color: T.text2, cursor: "pointer",
                    opacity: loading ? 0.5 : 1,
                    transition: "all 0.15s ease",
                  }}
                >
                  {qa.label}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <div key={i} style={{
            marginBottom: isMobile ? 18 : 16,
            display: "flex",
            justifyContent: msg.role === "user" ? "flex-end" : "flex-start",
            padding: isMobile ? "0 6px" : "0 4px",
          }}>
            <div style={{
              padding: isMobile ? "14px 16px" : "14px 18px",
              borderRadius: isMobile ? 18 : 16,
              background: msg.role === "user" ? T.accentDim : T.overlay04,
              border: `1px solid ${msg.role === "user"
                ? "rgba(151,252,228,0.2)" : T.border}`,
              maxWidth: isMobile ? "90%" : "82%",
            }}>
              <div style={{
                fontSize: m(T.textXs, isMobile), fontWeight: 700, fontFamily: T.mono,
                color: msg.role === "user" ? T.accent : T.text4,
                letterSpacing: "0.08em", marginBottom: 6,
                textTransform: "uppercase",
              }}>
                {msg.role === "user" ? "You" : "Assistant"}
              </div>
              <div style={{
                fontSize: m(T.textBase, isMobile), lineHeight: 1.75, fontFamily: T.font,
                color: T.text1, wordBreak: "break-word",
                whiteSpace: msg.role === "user" ? "pre-wrap" : "normal",
              }}>
                {msg.role === "assistant" ? <MdText text={msg.content} isMobile={isMobile} /> : msg.content}
              </div>
            </div>
          </div>
        ))}

        {loading && (
          <div style={{
            display: "flex", justifyContent: "flex-start",
            marginBottom: 16, padding: isMobile ? "0 6px" : "0 4px",
          }}>
            <div style={{
              padding: isMobile ? "14px 18px" : "14px 18px",
              borderRadius: isMobile ? 18 : 16,
              background: T.overlay04, border: `1px solid ${T.border}`,
            }}>
              <span style={{
                fontSize: m(T.textBase, isMobile), fontFamily: T.font, color: T.text4,
                animation: "pulse 1.5s ease-in-out infinite",
              }}>
                Thinking...
              </span>
            </div>
          </div>
        )}

        <div ref={endRef} />
      </div>

      {/* ── Input bar (pinned to bottom) ── */}
      <div style={{
        padding: isMobile ? "10px 8px 12px" : "12px 0 4px",
        borderTop: `1px solid ${T.border}`,
        display: "flex", gap: isMobile ? 8 : 10, alignItems: "flex-end",
        flexShrink: 0,
        background: T.bg,
      }}>
        <textarea
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKey}
          placeholder={selectedSymbol
            ? `Ask about ${selectedSymbol}...`
            : "Ask anything..."}
          rows={1}
          inputMode="text"
          enterKeyHint="send"
          style={{
            flex: 1, resize: "none",
            padding: isMobile ? "12px 16px" : "10px 16px",
            borderRadius: isMobile ? 20 : 12,
            border: `1px solid ${T.border}`,
            background: T.overlay04, color: T.text1,
            fontFamily: T.font, fontSize: isMobile ? 16 : T.textBase, lineHeight: 1.5,
            outline: "none",
            transition: "border-color 0.15s ease",
          }}
          onFocus={(e) => e.target.style.borderColor = T.accent}
          onBlur={(e) => e.target.style.borderColor = T.border}
        />
        <button
          onClick={() => send(input)}
          disabled={loading || !input.trim()}
          className={loading || !input.trim() ? "apple-btn" : "apple-btn apple-btn-accent"}
          style={{
            padding: isMobile ? "12px 24px" : "10px 26px",
            borderRadius: isMobile ? 20 : 12,
            fontFamily: T.font, fontSize: m(T.textBase, isMobile), fontWeight: 700,
            letterSpacing: "0.02em",
            cursor: loading || !input.trim() ? "default" : "pointer",
            color: loading || !input.trim() ? "rgba(151,252,228,0.45)" : undefined,
            background: loading || !input.trim() ? "rgba(151,252,228,0.06)" : undefined,
            border: loading || !input.trim() ? "1px solid rgba(151,252,228,0.15)" : undefined,
            opacity: 1,
            transition: "all 0.15s ease",
            boxShadow: loading || !input.trim() ? "none" : "0 0 16px rgba(151,252,228,0.25)",
          }}
        >
          Send
        </button>
      </div>

      {/* Error */}
      {error && (
        <div style={{
          marginTop: 8, padding: isMobile ? "10px 14px" : "10px 16px",
          borderRadius: T.radiusXs,
          background: "rgba(248,113,113,0.1)",
          border: "1px solid rgba(248,113,113,0.2)",
          fontSize: m(T.textSm, isMobile), color: "#f87171", fontFamily: T.font,
          flexShrink: 0,
        }}>
          Error: {error}
        </div>
      )}
    </div>
  );
}
