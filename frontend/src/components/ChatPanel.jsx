import { useState, useEffect, useRef, useCallback } from "react";
import { T, m } from "../theme.js";
import { useWallet } from "../WalletContext.jsx";
import { useTheme } from "../ThemeContext.jsx";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

/** Lightweight markdown→JSX for assistant messages (no deps). */
function MdText({ text, isMobile }) {
  const lines = text.split("\n");
  const elements = [];
  let key = 0;
  const baseFz = isMobile ? 15 : 14;

  for (const raw of lines) {
    const line = raw;
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
  { label: "My Positions", msg: "How are my positions doing? Give me a full breakdown with scanner context." },
  { label: "Top Signals", msg: "What are the strongest signals right now?" },
  { label: "Risk Check", msg: "Are there any risk warnings I should know about?" },
];

export default function ChatPanel({ isMobile, selectedSymbol }) {
  const { address: walletAddress } = useWallet();
  const { mode: themeMode } = useTheme();
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const endRef = useRef(null);
  const sessionId = useRef(getSessionId());
  const inputRef = useRef(null);

  // Model selection state
  const [models, setModels] = useState([]);
  const [currentModel, setCurrentModel] = useState("");
  const [providerMode, setProviderMode] = useState("");
  const [modelPickerOpen, setModelPickerOpen] = useState(false);
  const [modelSearch, setModelSearch] = useState("");
  const modelPickerRef = useRef(null);
  const modelSearchRef = useRef(null);

  // Scroll window to top on mount
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "instant" });
  }, []);

  // Fetch available models on mount
  useEffect(() => {
    fetch(`${API_BASE}/api/models`)
      .then((r) => r.json())
      .then((d) => {
        setModels(d.models || []);
        setCurrentModel(d.current || "");
        setProviderMode(d.mode || "");
      })
      .catch(() => {});
  }, []);

  // Close model picker on outside click
  useEffect(() => {
    if (!modelPickerOpen) return;
    const handler = (e) => {
      if (modelPickerRef.current && !modelPickerRef.current.contains(e.target)) {
        setModelPickerOpen(false);
        setModelSearch("");
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [modelPickerOpen]);

  // Auto-focus search when picker opens
  useEffect(() => {
    if (modelPickerOpen && modelSearchRef.current) {
      modelSearchRef.current.focus();
    }
  }, [modelPickerOpen]);

  const handleModelChange = useCallback(async (modelId) => {
    try {
      const res = await fetch(`${API_BASE}/api/models`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model_id: modelId }),
      });
      const d = await res.json();
      if (d.success) {
        setCurrentModel(d.current);
        setModelPickerOpen(false);
        setModelSearch("");
      }
    } catch (e) {
      // silent fail
    }
  }, []);

  // Derive short display label from current model
  const currentModelLabel = (() => {
    const md = models.find((mod) => mod.id === currentModel);
    if (md) return md.label;
    return currentModel.split("/").pop() || "Model";
  })();

  // Filter models by search term
  const filteredModels = models.filter((mod) => {
    if (!modelSearch) return true;
    const q = modelSearch.toLowerCase();
    return mod.label.toLowerCase().includes(q) || mod.id.toLowerCase().includes(q) || mod.provider.toLowerCase().includes(q);
  });

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
    }}>
      {/* ── Top bar: model + clear ── */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: isMobile ? "4px 4px" : "10px 0",
        flexShrink: 0,
        position: "relative", zIndex: modelPickerOpen ? 999 : "auto",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          {providerMode === "openrouter" && models.length > 0 ? (
            <div ref={modelPickerRef} style={{ position: "relative" }}>
              <button
                onClick={() => setModelPickerOpen(!modelPickerOpen)}
                style={{
                  fontSize: m(T.textSm, isMobile), fontFamily: T.font, color: T.text3,
                  padding: isMobile ? "6px 14px" : "5px 12px", borderRadius: 8,
                  background: T.overlay06, border: `1px solid ${T.border}`,
                  fontWeight: 500, cursor: "pointer", outline: "none",
                  display: "flex", alignItems: "center", gap: 6,
                  transition: "all 0.15s",
                }}
              >
                {currentModelLabel}
                <span style={{ fontSize: 8, opacity: 0.5, marginLeft: 2 }}>{modelPickerOpen ? "\u25B2" : "\u25BC"}</span>
              </button>

              {modelPickerOpen && (
                <div style={{
                  position: "absolute", top: "calc(100% + 6px)", left: 0,
                  width: isMobile ? "calc(100vw - 32px)" : 340,
                  maxHeight: 400, zIndex: 9999,
                  background: "#16161e", border: `1px solid rgba(255,255,255,0.15)`,
                  borderRadius: 10, overflow: "hidden",
                  boxShadow: "0 8px 30px rgba(0,0,0,0.6)",
                }}>
                  <div style={{ padding: "8px 10px", borderBottom: "1px solid rgba(255,255,255,0.08)" }}>
                    <input
                      ref={modelSearchRef}
                      type="text"
                      value={modelSearch}
                      onChange={(e) => setModelSearch(e.target.value)}
                      placeholder="Search..."
                      style={{
                        width: "100%", fontSize: m(12, isMobile), fontFamily: T.font,
                        color: "#e0e0e4", background: "#1e1e28",
                        border: "1px solid rgba(255,255,255,0.1)", borderRadius: 6,
                        padding: isMobile ? "8px 10px" : "6px 8px", outline: "none",
                        boxSizing: "border-box",
                      }}
                    />
                  </div>
                  <div style={{ overflowY: "auto", maxHeight: 340 }}>
                    {filteredModels.length === 0 && (
                      <div style={{
                        padding: 14, textAlign: "center",
                        color: T.text4, fontSize: m(12, isMobile), fontFamily: T.font,
                      }}>
                        No models found
                      </div>
                    )}
                    {filteredModels.map((mod) => {
                      const active = mod.id === currentModel;
                      return (
                        <div
                          key={mod.id}
                          onClick={() => handleModelChange(mod.id)}
                          style={{
                            display: "flex", alignItems: "center", justifyContent: "space-between",
                            padding: isMobile ? "8px 12px" : "6px 10px", cursor: "pointer",
                            background: active ? "rgba(34,211,238,0.08)" : "transparent",
                            borderLeft: active ? "2px solid #22d3ee" : "2px solid transparent",
                            transition: "background 0.1s",
                            minHeight: isMobile ? 40 : 32,
                          }}
                          onMouseEnter={(e) => {
                            if (!active) e.currentTarget.style.background = "rgba(255,255,255,0.04)";
                          }}
                          onMouseLeave={(e) => {
                            if (!active) e.currentTarget.style.background = "transparent";
                          }}
                        >
                          <div style={{ minWidth: 0 }}>
                            <div style={{
                              fontSize: m(12, isMobile), fontFamily: T.font, fontWeight: 500,
                              color: active ? "#22d3ee" : "#d1d1d6",
                              whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
                            }}>
                              {mod.label}
                            </div>
                          </div>
                          <div style={{
                            fontSize: m(10, isMobile), fontFamily: T.font, color: "#6e6e73",
                            flexShrink: 0, marginLeft: 8, textAlign: "right",
                          }}>
                            {mod.context_length ? `${(mod.context_length / 1000).toFixed(0)}K` : ""}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <span style={{
              fontSize: m(T.textSm, isMobile), fontFamily: T.font, color: T.text4,
              padding: isMobile ? "6px 14px" : "5px 12px", borderRadius: 8,
              background: T.overlay06, fontWeight: 500,
            }}>
              {providerMode === "anthropic" ? "Haiku (Direct)" : "Haiku"}
            </span>
          )}
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
      }}>
        {messages.length === 0 && (
          <div style={{
            display: "flex", flexDirection: "column",
            alignItems: "center",
            justifyContent: isMobile ? "flex-start" : "center",
            height: "100%",
            padding: isMobile ? "20px 20px 0" : "40px 20px", textAlign: "center",
          }}>
            <div style={{ position: "relative", width: "min(90%, 550px)", margin: "0 auto", marginBottom: isMobile ? 8 : 20 }}>
              <img
                src={themeMode === "light" ? "/AI_Agent_white.png" : "/AI_Agent_dark.png"}
                alt="Reflex AI"
                style={{
                  width: "100%",
                  borderRadius: 16,
                  display: "block",
                }}
              />
              <div style={{
                position: "absolute",
                bottom: isMobile ? 10 : 20,
                left: 0, right: 0,
                textAlign: "center",
              }}>
                <div style={{
                  color: T.text1, fontSize: m(16, isMobile), fontFamily: T.font,
                  fontWeight: 500, lineHeight: 1.6,
                }}>
                  Ask about any signal, symbol, or market condition.
                </div>
                {walletAddress && (
                  <div style={{
                    display: "inline-flex", alignItems: "center", gap: 6,
                    marginTop: 8, padding: "4px 12px", borderRadius: 20,
                    background: "rgba(34, 197, 94, 0.12)",
                    border: "1px solid rgba(34, 197, 94, 0.25)",
                  }}>
                    <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#22c55e", display: "inline-block" }} />
                    <span style={{ color: "#22c55e", fontSize: m(11, isMobile), fontFamily: T.font, fontWeight: 600, letterSpacing: "0.04em" }}>
                      Position-aware context is active
                    </span>
                  </div>
                )}
              </div>
            </div>

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
                ? "rgba(34,211,238,0.2)" : T.border}`,
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
          style={{
            flex: 1, resize: "none",
            padding: isMobile ? "12px 16px" : "10px 16px",
            borderRadius: isMobile ? 20 : 12,
            border: `1px solid ${T.border}`,
            background: T.overlay04, color: T.text1,
            fontFamily: T.font, fontSize: m(T.textBase, isMobile), lineHeight: 1.5,
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
            color: loading || !input.trim() ? "rgba(34,211,238,0.45)" : undefined,
            background: loading || !input.trim() ? "rgba(34,211,238,0.06)" : undefined,
            border: loading || !input.trim() ? "1px solid rgba(34,211,238,0.15)" : undefined,
            opacity: 1,
            transition: "all 0.15s ease",
            boxShadow: loading || !input.trim() ? "none" : "0 0 16px rgba(34,211,238,0.25)",
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
