import { useState, useEffect, useRef, useCallback } from "react";
import { T, m } from "../theme.js";
import { useWallet } from "../WalletContext.jsx";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

// ── Inline markdown helpers (shared with ChatPanel) ─────────────────────────

function renderInline(text) {
  const parts = [];
  let remaining = text;
  let i = 0;
  const re = /(\*\*(.+?)\*\*|\*(.+?)\*|`(.+?)`)/g;
  let lastIdx = 0;
  let match;
  while ((match = re.exec(remaining)) !== null) {
    if (match.index > lastIdx)
      parts.push(<span key={i++}>{remaining.slice(lastIdx, match.index)}</span>);
    if (match[2])
      parts.push(<span key={i++} style={{ fontWeight: 700, color: T.text1 }}>{match[2]}</span>);
    else if (match[3])
      parts.push(<span key={i++} style={{ fontStyle: "italic", color: T.text2 }}>{match[3]}</span>);
    else if (match[4])
      parts.push(
        <span key={i++} style={{
          background: T.overlay08, padding: "2px 6px",
          borderRadius: 4, fontSize: "0.9em", color: T.accent, fontFamily: T.mono,
        }}>{match[4]}</span>
      );
    lastIdx = match.index + match[0].length;
  }
  if (lastIdx < remaining.length)
    parts.push(<span key={i++}>{remaining.slice(lastIdx)}</span>);
  return parts.length > 0 ? parts : text;
}

function MdText({ text, isMobile }) {
  const lines = text.split("\n");
  const elements = [];
  let key = 0;
  const fz = m(T.textSm, isMobile);

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (/^#{1,3}\s/.test(line)) {
      const level = line.match(/^(#+)/)[1].length;
      const content = line.replace(/^#+\s*/, "");
      elements.push(
        <div key={key++} style={{
          fontSize: fz + (level === 1 ? 3 : level === 2 ? 2 : 1),
          fontWeight: 700, color: T.accent, fontFamily: T.mono,
          marginTop: 10, marginBottom: 4,
        }}>{renderInline(content)}</div>
      );
    } else if (/^\s*[-\u2022]\s/.test(line)) {
      const content = line.replace(/^\s*[-\u2022]\s*/, "");
      elements.push(
        <div key={key++} style={{ paddingLeft: 14, position: "relative", marginBottom: 3, fontSize: fz }}>
          <span style={{ position: "absolute", left: 0, color: T.text4 }}>{"\u2022"}</span>
          {renderInline(content)}
        </div>
      );
    } else if (line.trim() === "") {
      elements.push(<div key={key++} style={{ height: 6 }} />);
    } else {
      elements.push(<div key={key++} style={{ fontSize: fz }}>{renderInline(line)}</div>);
    }
  }
  return <>{elements}</>;
}

// ── Quick action chips ──────────────────────────────────────────────────────

const QUICK_ACTIONS = [
  { label: "Signal analysis", prompt: "Analyze the current signal and conditions" },
  { label: "Risk check", prompt: "What are the risks of entering a position right now?" },
  { label: "Entry setup", prompt: "If I wanted to enter, what's the ideal setup?" },
];

// ── Session management ──────────────────────────────────────────────────────

function getCoinSessionId(symbol) {
  const base = (symbol || "").replace("/USDT", "").replace("/USD", "");
  const key = `rcce-coin-chat-${base}`;
  let id = sessionStorage.getItem(key);
  if (!id) {
    id = `coin-${base}-${Math.random().toString(36).slice(2, 8)}`;
    sessionStorage.setItem(key, id);
  }
  return id;
}

// ── Component ───────────────────────────────────────────────────────────────

export default function CoinChat({ symbol, isMobile }) {
  const { address: walletAddress } = useWallet();
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const endRef = useRef(null);
  const inputRef = useRef(null);
  const panelRef = useRef(null);
  const btnRef = useRef(null);
  const sessionId = useRef(getCoinSessionId(symbol));

  const coin = (symbol || "").replace("/USDT", "").replace("/USD", "");

  // Reset session when symbol changes
  useEffect(() => {
    sessionId.current = getCoinSessionId(symbol);
    setMessages([]);
    setInput("");
  }, [symbol]);

  // Auto-scroll
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  // Focus input on open
  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 100);
  }, [open]);

  // Close on outside click (but not on the floating button itself)
  useEffect(() => {
    if (!open) return;
    const handler = (e) => {
      if (btnRef.current && btnRef.current.contains(e.target)) return;
      if (panelRef.current && !panelRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const send = useCallback(async (text) => {
    if (!text?.trim() || loading) return;
    const userMsg = text.trim();
    setMessages(prev => [...prev, { role: "user", content: userMsg }]);
    setInput("");
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: userMsg,
          session_id: sessionId.current,
          symbol: symbol || null,
          wallet_address: walletAddress || null,
        }),
      });
      if (!res.ok) throw new Error(`${res.status}`);
      const data = await res.json();
      setMessages(prev => [...prev, { role: "assistant", content: data.reply }]);
    } catch (e) {
      setMessages(prev => [...prev, { role: "assistant", content: `Error: ${e.message}` }]);
    } finally {
      setLoading(false);
    }
  }, [symbol, walletAddress, loading]);

  const handleKey = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send(input);
    }
  };

  return (
    <>
      {/* Floating button */}
      <button
        ref={btnRef}
        onClick={() => setOpen(!open)}
        style={{
          position: "fixed", bottom: 24, right: 24,
          width: 56, height: 56, borderRadius: "50%",
          background: "rgba(10, 10, 20, 0.5)",
          backdropFilter: "blur(20px) saturate(1.5)",
          WebkitBackdropFilter: "blur(20px) saturate(1.5)",
          border: "2px solid rgba(34, 211, 238, 0.4)",
          cursor: "pointer",
          display: "flex", alignItems: "center", justifyContent: "center",
          boxShadow: "0 2px 16px rgba(0,0,0,0.3)",
          transition: "all 0.25s ease",
          zIndex: 1000,
          overflow: "visible",
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.background = "#22d3ee";
          e.currentTarget.style.boxShadow = "0 4px 24px rgba(34,211,238,0.4)";
        }}
        onMouseLeave={(e) => {
          if (!open) {
            e.currentTarget.style.background = "rgba(10, 10, 20, 0.5)";
            e.currentTarget.style.boxShadow = "0 2px 16px rgba(0,0,0,0.3)";
          }
        }}
      >
        {open ? (
          <span style={{ color: T.text2, fontSize: 20, lineHeight: 1 }}>{"\u2715"}</span>
        ) : (
          <img
            src="/Robot.png"
            alt="AI Assistant"
            style={{ width: 66, height: 66, objectFit: "contain", opacity: 0.5 }}
          />
        )}
      </button>

      {/* Chat popover */}
      {open && (
        <div
          ref={panelRef}
          style={{
            position: "fixed",
            bottom: 92,
            right: 24,
            width: isMobile ? "calc(100vw - 32px)" : 400,
            height: isMobile ? "60vh" : 520,
            background: T.popoverBg,
            border: `1px solid ${T.border}`,
            borderRadius: 16,
            boxShadow: T.shadowHeavy,
            zIndex: 999,
            display: "flex",
            flexDirection: "column",
            overflow: "hidden",
          }}
        >
          {/* Header */}
          <div style={{
            padding: "12px 16px",
            borderBottom: `1px solid ${T.border}`,
            display: "flex", alignItems: "center", gap: 10,
            flexShrink: 0,
          }}>
            <img
              src="/Robot.png"
              alt="AI"
              style={{ width: 32, height: 32, objectFit: "contain" }}
            />
            <span style={{
              fontSize: T.textBase, fontFamily: T.mono, fontWeight: 700,
              color: T.text1, flex: 1, letterSpacing: "0.04em",
            }}>
              {coin} AI
            </span>
            <button
              onClick={() => setOpen(false)}
              style={{
                fontSize: T.textSm, color: T.text4, background: "transparent",
                border: "none", cursor: "pointer", padding: "4px 6px",
                borderRadius: 4, transition: "color 0.15s",
              }}
              onMouseEnter={(e) => e.currentTarget.style.color = T.text2}
              onMouseLeave={(e) => e.currentTarget.style.color = T.text4}
            >{"\u2715"}</button>
          </div>

          {/* Messages */}
          <div style={{
            flex: 1, overflowY: "auto", padding: "12px 14px",
          }}>
            {messages.length === 0 && !loading && (
              <div style={{ textAlign: "center", padding: "24px 0" }}>
                <div style={{
                  fontSize: T.textSm, color: T.text4, fontFamily: T.mono,
                  marginBottom: 16, lineHeight: 1.6,
                }}>
                  Ask anything about {coin}
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8, justifyContent: "center" }}>
                  {QUICK_ACTIONS.map(qa => (
                    <button
                      key={qa.label}
                      onClick={() => send(qa.prompt)}
                      style={{
                        padding: "6px 12px", borderRadius: 8,
                        border: `1px solid ${T.border}`,
                        background: T.overlay04, color: T.text2,
                        fontSize: T.textXs, fontFamily: T.mono, fontWeight: 600,
                        cursor: "pointer", transition: "all 0.15s",
                      }}
                      onMouseEnter={(e) => { e.currentTarget.style.borderColor = T.accent; e.currentTarget.style.color = T.accent; }}
                      onMouseLeave={(e) => { e.currentTarget.style.borderColor = T.border; e.currentTarget.style.color = T.text2; }}
                    >
                      {qa.label}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((msg, i) => (
              <div
                key={i}
                style={{
                  marginBottom: 12,
                  display: "flex",
                  justifyContent: msg.role === "user" ? "flex-end" : "flex-start",
                }}
              >
                <div style={{
                  padding: "10px 14px",
                  borderRadius: 14,
                  background: msg.role === "user" ? T.accentDim : T.overlay04,
                  border: `1px solid ${msg.role === "user" ? "rgba(34,211,238,0.2)" : T.border}`,
                  maxWidth: "88%",
                }}>
                  <div style={{
                    fontSize: T.textXs, fontWeight: 700, fontFamily: T.mono,
                    color: msg.role === "user" ? T.accent : T.text4,
                    letterSpacing: "0.06em", marginBottom: 4,
                    textTransform: "uppercase",
                  }}>
                    {msg.role === "user" ? "You" : `${coin} AI`}
                  </div>
                  <div style={{
                    fontSize: T.textSm, lineHeight: 1.7, fontFamily: T.font,
                    color: T.text1, wordBreak: "break-word",
                    whiteSpace: msg.role === "user" ? "pre-wrap" : "normal",
                  }}>
                    {msg.role === "assistant" ? <MdText text={msg.content} isMobile={isMobile} /> : msg.content}
                  </div>
                </div>
              </div>
            ))}

            {loading && (
              <div style={{ display: "flex", justifyContent: "flex-start", marginBottom: 12 }}>
                <div style={{
                  padding: "10px 14px", borderRadius: 14,
                  background: T.overlay04, border: `1px solid ${T.border}`,
                }}>
                  <div style={{
                    fontSize: T.textSm, color: T.text4, fontFamily: T.mono,
                    animation: "pulse 1.5s ease-in-out infinite",
                  }}>
                    Thinking...
                  </div>
                </div>
              </div>
            )}

            <div ref={endRef} />
          </div>

          {/* Input */}
          <div style={{
            padding: "10px 14px",
            borderTop: `1px solid ${T.border}`,
            display: "flex", gap: 8,
            flexShrink: 0,
          }}>
            <input
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKey}
              placeholder={`Ask about ${coin}...`}
              style={{
                flex: 1, padding: "8px 12px",
                fontSize: T.textSm, fontFamily: T.mono,
                background: T.overlay04, color: T.text1,
                border: `1px solid ${T.border}`, borderRadius: 10,
                outline: "none",
              }}
            />
            <button
              onClick={() => send(input)}
              disabled={loading || !input.trim()}
              style={{
                padding: "8px 14px", borderRadius: 10,
                background: input.trim() ? T.accent : T.overlay06,
                color: input.trim() ? "#0a0a0f" : T.text4,
                border: "none", cursor: input.trim() ? "pointer" : "default",
                fontSize: T.textSm, fontFamily: T.mono, fontWeight: 700,
                transition: "all 0.15s",
              }}
            >
              Send
            </button>
          </div>
        </div>
      )}
    </>
  );
}
