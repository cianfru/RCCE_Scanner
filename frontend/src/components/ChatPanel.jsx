import { useState, useEffect, useRef, useCallback } from "react";
import { T } from "../theme.js";
import GlassCard from "./GlassCard.jsx";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

/** Lightweight markdown→JSX for assistant messages (no deps). */
function MdText({ text }) {
  const lines = text.split("\n");
  const elements = [];
  let key = 0;

  for (const raw of lines) {
    const line = raw;
    // Headings
    if (/^#{1,3}\s/.test(line)) {
      const level = line.match(/^(#+)/)[1].length;
      const content = line.replace(/^#+\s*/, "");
      const sz = level === 1 ? 13 : level === 2 ? 12 : 11;
      elements.push(
        <div key={key++} style={{
          fontSize: sz, fontWeight: 700, color: T.accent,
          marginTop: level === 1 ? 10 : 8, marginBottom: 4,
          letterSpacing: "0.03em",
        }}>
          {renderInline(content)}
        </div>
      );
    // Horizontal rule
    } else if (/^---+$/.test(line.trim())) {
      elements.push(
        <hr key={key++} style={{
          border: "none", borderTop: `1px solid ${T.border}`,
          margin: "8px 0",
        }} />
      );
    // List item
    } else if (/^\s*[-•]\s/.test(line)) {
      const indent = (line.match(/^(\s*)/)[1].length / 2) | 0;
      const content = line.replace(/^\s*[-•]\s*/, "");
      elements.push(
        <div key={key++} style={{
          paddingLeft: 12 + indent * 12,
          position: "relative", marginBottom: 2,
        }}>
          <span style={{ position: "absolute", left: indent * 12, color: T.text4 }}>•</span>
          {renderInline(content)}
        </div>
      );
    // Numbered list
    } else if (/^\s*\d+\.\s/.test(line)) {
      const match = line.match(/^(\s*)(\d+)\.\s(.*)/);
      const indent = (match[1].length / 2) | 0;
      elements.push(
        <div key={key++} style={{
          paddingLeft: 12 + indent * 12,
          position: "relative", marginBottom: 2,
        }}>
          <span style={{ position: "absolute", left: indent * 12, color: T.text4 }}>{match[2]}.</span>
          {renderInline(match[3])}
        </div>
      );
    // Empty line
    } else if (line.trim() === "") {
      elements.push(<div key={key++} style={{ height: 6 }} />);
    // Regular text
    } else {
      elements.push(<div key={key++}>{renderInline(line)}</div>);
    }
  }
  return <>{elements}</>;
}

/** Render inline markdown: **bold**, *italic*, `code`, ✓/✗ markers */
function renderInline(text) {
  const parts = [];
  let remaining = text;
  let i = 0;
  // Match **bold**, *italic*, `code`
  const re = /(\*\*(.+?)\*\*|\*(.+?)\*|`(.+?)`)/g;
  let lastIdx = 0;
  let match;
  while ((match = re.exec(remaining)) !== null) {
    if (match.index > lastIdx) {
      parts.push(<span key={i++}>{remaining.slice(lastIdx, match.index)}</span>);
    }
    if (match[2]) {
      // **bold**
      parts.push(<span key={i++} style={{ fontWeight: 700, color: T.text1 }}>{match[2]}</span>);
    } else if (match[3]) {
      // *italic*
      parts.push(<span key={i++} style={{ fontStyle: "italic", color: T.text2 }}>{match[3]}</span>);
    } else if (match[4]) {
      // `code`
      parts.push(
        <span key={i++} style={{
          background: T.overlay08, padding: "1px 5px",
          borderRadius: 4, fontSize: "0.95em", color: T.accent,
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
  { label: "BRIEFING", msg: "Give me a daily market briefing." },
  { label: "TOP SIGNALS", msg: "What are the strongest signals right now?" },
  { label: "RISK CHECK", msg: "Are there any risk warnings I should know about?" },
  { label: "WARMING UP", msg: "Which symbols are closest to upgrading their signal?" },
];

export default function ChatPanel({ isMobile, selectedSymbol }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const endRef = useRef(null);
  const sessionId = useRef(getSessionId());
  const inputRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
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
  }, [selectedSymbol, loading]);

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

  return (
    <div style={{ maxWidth: 820, margin: "0 auto", padding: isMobile ? "0 8px" : 0 }}>
      {/* Header */}
      <GlassCard style={{ padding: "12px 20px", marginBottom: 12 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{
              fontSize: 11, fontWeight: 700, fontFamily: T.mono,
              letterSpacing: "0.08em", color: T.text1,
            }}>
              RCCE ASSISTANT
            </span>
            <span style={{
              fontSize: 9, fontFamily: T.mono, color: T.text4,
              padding: "2px 8px", borderRadius: T.radiusXs,
              background: T.overlay06, letterSpacing: "0.06em",
            }}>
              HAIKU
            </span>
          </div>
          <button onClick={clearChat} style={{
            background: "none", border: "none", cursor: "pointer",
            color: T.text4, fontSize: 10, fontFamily: T.mono,
            padding: "4px 8px", borderRadius: T.radiusXs,
          }}>
            CLEAR
          </button>
        </div>
      </GlassCard>

      {/* Quick actions */}
      <div style={{
        display: "flex", gap: 6, marginBottom: 12, flexWrap: "wrap",
      }}>
        {QUICK_ACTIONS.map((qa, i) => (
          <button
            key={i}
            onClick={() => send(qa.msg)}
            disabled={loading}
            style={{
              padding: "5px 12px", fontSize: 9, fontFamily: T.mono,
              letterSpacing: "0.05em", fontWeight: 600,
              background: T.overlay06, border: `1px solid ${T.border}`,
              borderRadius: T.radiusXs, color: T.text3, cursor: "pointer",
              transition: "all 0.15s ease",
              opacity: loading ? 0.5 : 1,
            }}
            onMouseEnter={(e) => {
              e.target.style.background = T.overlay12;
              e.target.style.color = T.accent;
            }}
            onMouseLeave={(e) => {
              e.target.style.background = T.overlay06;
              e.target.style.color = T.text3;
            }}
          >
            {qa.label}
          </button>
        ))}
      </div>

      {/* Messages area */}
      <GlassCard style={{
        padding: 0,
        minHeight: isMobile ? 350 : 450,
        maxHeight: isMobile ? "60vh" : "65vh",
        display: "flex", flexDirection: "column",
      }}>
        <div style={{
          flex: 1, padding: "16px 18px", overflowY: "auto",
          scrollbarWidth: "thin",
          scrollbarColor: `${T.scrollThumb} transparent`,
        }}>
          {messages.length === 0 && (
            <div style={{
              color: T.text4, fontSize: 11, fontFamily: T.mono,
              textAlign: "center", padding: "80px 20px", lineHeight: 1.8,
            }}>
              Ask about any signal, symbol, or market condition.
              <br />
              <span style={{ color: T.text3 }}>
                Try: "Why is BTC showing WAIT?"
              </span>
            </div>
          )}

          {messages.map((msg, i) => (
            <div key={i} style={{
              marginBottom: 14,
              display: "flex",
              justifyContent: msg.role === "user" ? "flex-end" : "flex-start",
            }}>
              <div style={{
                padding: "10px 14px",
                borderRadius: T.radiusSm,
                background: msg.role === "user" ? T.accentDim : T.overlay04,
                border: `1px solid ${msg.role === "user"
                  ? "rgba(34,211,238,0.2)" : T.border}`,
                maxWidth: "85%",
              }}>
                <div style={{
                  fontSize: 9, fontWeight: 700, fontFamily: T.mono,
                  color: msg.role === "user" ? T.accent : T.text4,
                  letterSpacing: "0.08em", marginBottom: 5,
                }}>
                  {msg.role === "user" ? "YOU" : "ASSISTANT"}
                </div>
                <div style={{
                  fontSize: 11.5, lineHeight: 1.65, fontFamily: T.mono,
                  color: T.text1, wordBreak: "break-word",
                  whiteSpace: msg.role === "user" ? "pre-wrap" : "normal",
                }}>
                  {msg.role === "assistant" ? <MdText text={msg.content} /> : msg.content}
                </div>
              </div>
            </div>
          ))}

          {loading && (
            <div style={{
              display: "flex", justifyContent: "flex-start",
              marginBottom: 14,
            }}>
              <div style={{
                padding: "10px 14px", borderRadius: T.radiusSm,
                background: T.overlay04, border: `1px solid ${T.border}`,
              }}>
                <span style={{
                  fontSize: 11, fontFamily: T.mono, color: T.text4,
                  animation: "pulse 1.5s ease-in-out infinite",
                }}>
                  Thinking...
                </span>
              </div>
            </div>
          )}

          <div ref={endRef} />
        </div>

        {/* Input */}
        <div style={{
          padding: "10px 14px",
          borderTop: `1px solid ${T.border}`,
          display: "flex", gap: 8, alignItems: "flex-end",
        }}>
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKey}
            placeholder={selectedSymbol
              ? `Ask about ${selectedSymbol}...`
              : "Ask about signals, symbols, or market conditions..."}
            rows={1}
            style={{
              flex: 1, resize: "none", padding: "9px 14px",
              borderRadius: T.radiusSm,
              border: `1px solid ${T.border}`,
              background: T.overlay04, color: T.text1,
              fontFamily: T.mono, fontSize: 11.5, lineHeight: 1.5,
              outline: "none",
              transition: "border-color 0.15s ease",
            }}
            onFocus={(e) => e.target.style.borderColor = T.accent}
            onBlur={(e) => e.target.style.borderColor = T.border}
          />
          <button
            onClick={() => send(input)}
            disabled={loading || !input.trim()}
            style={{
              padding: "9px 18px", borderRadius: T.radiusSm,
              background: loading || !input.trim() ? T.overlay06 : T.accent,
              color: loading || !input.trim() ? T.text4 : "#0a0a0c",
              border: "none", cursor: loading || !input.trim() ? "default" : "pointer",
              fontFamily: T.mono, fontSize: 10, fontWeight: 700,
              letterSpacing: "0.06em",
              transition: "all 0.15s ease",
            }}
          >
            SEND
          </button>
        </div>
      </GlassCard>

      {/* Error */}
      {error && (
        <div style={{
          marginTop: 8, padding: "8px 14px", borderRadius: T.radiusXs,
          background: "rgba(248,113,113,0.1)",
          border: "1px solid rgba(248,113,113,0.2)",
          fontSize: 10, color: "#f87171", fontFamily: T.mono,
        }}>
          Error: {error}
        </div>
      )}

      {/* Pulse animation */}
      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 0.4; }
          50% { opacity: 1; }
        }
      `}</style>
    </div>
  );
}
