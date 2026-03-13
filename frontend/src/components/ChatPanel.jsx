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
      const sz = level === 1 ? 16 : level === 2 ? 15 : 14;
      elements.push(
        <div key={key++} style={{
          fontSize: sz, fontWeight: 700, color: T.accent,
          fontFamily: T.font,
          marginTop: level === 1 ? 14 : 10, marginBottom: 6,
          letterSpacing: "-0.01em",
        }}>
          {renderInline(content)}
        </div>
      );
    // Horizontal rule
    } else if (/^---+$/.test(line.trim())) {
      elements.push(
        <hr key={key++} style={{
          border: "none", borderTop: `1px solid ${T.border}`,
          margin: "10px 0",
        }} />
      );
    // List item
    } else if (/^\s*[-•]\s/.test(line)) {
      const indent = (line.match(/^(\s*)/)[1].length / 2) | 0;
      const content = line.replace(/^\s*[-•]\s*/, "");
      elements.push(
        <div key={key++} style={{
          paddingLeft: 16 + indent * 14,
          position: "relative", marginBottom: 3,
        }}>
          <span style={{ position: "absolute", left: indent * 14, color: T.text4 }}>•</span>
          {renderInline(content)}
        </div>
      );
    // Numbered list
    } else if (/^\s*\d+\.\s/.test(line)) {
      const match = line.match(/^(\s*)(\d+)\.\s(.*)/);
      const indent = (match[1].length / 2) | 0;
      elements.push(
        <div key={key++} style={{
          paddingLeft: 16 + indent * 14,
          position: "relative", marginBottom: 3,
        }}>
          <span style={{ position: "absolute", left: indent * 14, color: T.text4 }}>{match[2]}.</span>
          {renderInline(match[3])}
        </div>
      );
    // Empty line
    } else if (line.trim() === "") {
      elements.push(<div key={key++} style={{ height: 8 }} />);
    // Regular text
    } else {
      elements.push(<div key={key++}>{renderInline(line)}</div>);
    }
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
          background: T.overlay08, padding: "1px 6px",
          borderRadius: 4, fontSize: "0.9em", color: T.accent,
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
  { label: "Top Signals", msg: "What are the strongest signals right now?" },
  { label: "Risk Check", msg: "Are there any risk warnings I should know about?" },
  { label: "Warming Up", msg: "Which symbols are closest to upgrading their signal?" },
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
    <div style={{ maxWidth: 820, margin: "0 auto", padding: isMobile ? "0 4px" : 0 }}>
      {/* Header */}
      <GlassCard style={{ padding: isMobile ? "14px 16px" : "16px 22px", marginBottom: 14 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{
              fontSize: T.textBase, fontWeight: 700, fontFamily: T.font,
              letterSpacing: "-0.01em", color: T.text1,
            }}>
              Reflex Assistant
            </span>
            <span style={{
              fontSize: T.textXs, fontFamily: T.mono, color: T.text4,
              padding: "3px 10px", borderRadius: T.radiusXs,
              background: T.overlay06, letterSpacing: "0.06em",
              fontWeight: 600,
            }}>
              HAIKU
            </span>
          </div>
          <button onClick={clearChat} className="apple-btn" style={{
            padding: "6px 14px", fontSize: T.textSm, fontFamily: T.font,
            fontWeight: 600, color: T.text3, cursor: "pointer",
          }}>
            Clear
          </button>
        </div>
      </GlassCard>

      {/* Quick actions */}
      <div style={{
        display: "flex", gap: 8, marginBottom: 14, flexWrap: "wrap",
      }}>
        {QUICK_ACTIONS.map((qa, i) => (
          <button
            key={i}
            onClick={() => send(qa.msg)}
            disabled={loading}
            className="apple-btn"
            style={{
              padding: "8px 16px", fontSize: T.textSm, fontFamily: T.font,
              fontWeight: 600, color: T.text2, cursor: "pointer",
              opacity: loading ? 0.5 : 1,
              transition: "all 0.15s ease",
            }}
          >
            {qa.label}
          </button>
        ))}
      </div>

      {/* Messages area */}
      <GlassCard style={{
        padding: 0,
        minHeight: isMobile ? 350 : 460,
        maxHeight: isMobile ? "60vh" : "65vh",
        display: "flex", flexDirection: "column",
      }}>
        <div style={{
          flex: 1, padding: isMobile ? "16px 14px" : "20px 22px", overflowY: "auto",
          scrollbarWidth: "thin",
          scrollbarColor: `${T.scrollThumb} transparent`,
        }}>
          {messages.length === 0 && (
            <div style={{
              color: T.text4, fontSize: T.textBase, fontFamily: T.font,
              textAlign: "center", padding: "80px 20px", lineHeight: 1.8,
            }}>
              Ask about any signal, symbol, or market condition.
              <br />
              <span style={{ color: T.text3, fontSize: T.textSm }}>
                Try: "Why is BTC showing WAIT?"
              </span>
            </div>
          )}

          {messages.map((msg, i) => (
            <div key={i} style={{
              marginBottom: 16,
              display: "flex",
              justifyContent: msg.role === "user" ? "flex-end" : "flex-start",
            }}>
              <div style={{
                padding: isMobile ? "12px 14px" : "14px 18px",
                borderRadius: T.radiusSm,
                background: msg.role === "user" ? T.accentDim : T.overlay04,
                border: `1px solid ${msg.role === "user"
                  ? "rgba(34,211,238,0.2)" : T.border}`,
                maxWidth: "85%",
              }}>
                <div style={{
                  fontSize: T.textXs, fontWeight: 700, fontFamily: T.mono,
                  color: msg.role === "user" ? T.accent : T.text4,
                  letterSpacing: "0.08em", marginBottom: 6,
                  textTransform: "uppercase",
                }}>
                  {msg.role === "user" ? "You" : "Assistant"}
                </div>
                <div style={{
                  fontSize: T.textBase, lineHeight: 1.7, fontFamily: T.font,
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
              marginBottom: 16,
            }}>
              <div style={{
                padding: "14px 18px", borderRadius: T.radiusSm,
                background: T.overlay04, border: `1px solid ${T.border}`,
              }}>
                <span style={{
                  fontSize: T.textBase, fontFamily: T.font, color: T.text4,
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
          padding: isMobile ? "12px 14px" : "14px 18px",
          borderTop: `1px solid ${T.border}`,
          display: "flex", gap: 10, alignItems: "flex-end",
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
              flex: 1, resize: "none", padding: "10px 16px",
              borderRadius: T.radiusSm,
              border: `1px solid ${T.border}`,
              background: T.overlay04, color: T.text1,
              fontFamily: T.font, fontSize: T.textBase, lineHeight: 1.5,
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
              padding: "10px 22px", borderRadius: T.radiusSm,
              fontFamily: T.font, fontSize: T.textSm, fontWeight: 700,
              letterSpacing: "0.02em",
              cursor: loading || !input.trim() ? "default" : "pointer",
              opacity: loading || !input.trim() ? 0.5 : 1,
              transition: "all 0.15s ease",
            }}
          >
            Send
          </button>
        </div>
      </GlassCard>

      {/* Error */}
      {error && (
        <div style={{
          marginTop: 10, padding: "10px 16px", borderRadius: T.radiusXs,
          background: "rgba(248,113,113,0.1)",
          border: "1px solid rgba(248,113,113,0.2)",
          fontSize: T.textSm, color: "#f87171", fontFamily: T.font,
        }}>
          Error: {error}
        </div>
      )}
    </div>
  );
}
