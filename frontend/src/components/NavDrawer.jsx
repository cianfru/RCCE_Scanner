import { useState, useEffect, useRef, useCallback } from "react";
import { T } from "../theme.js";

// Simple 16x16 SVG icons for nav items
const NAV_ICONS = {
  "1d": (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <path d="M2 12L5 7L8 9L14 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
      <path d="M2 14h12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
    </svg>
  ),
  chat: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <path d="M3 3h10a1 1 0 011 1v6a1 1 0 01-1 1H6l-3 3V4a1 1 0 011-1z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/>
    </svg>
  ),
  signals: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <path d="M3 13V8M6 13V5M9 13V7M12 13V3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
    </svg>
  ),
  onchain: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <circle cx="8" cy="8" r="5.5" stroke="currentColor" strokeWidth="1.5"/>
      <path d="M5 8h6M8 5v6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
    </svg>
  ),
  backtest: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <rect x="2" y="2" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.5"/>
      <rect x="9" y="2" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.5"/>
      <rect x="2" y="9" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.5"/>
      <rect x="9" y="9" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.5"/>
    </svg>
  ),
  executor: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <path d="M5 2l8 6-8 6V2z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/>
    </svg>
  ),
  trading: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <path d="M2 8h3l2-5 2 10 2-5h3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  ),
  tradfi: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <rect x="2" y="6" width="3" height="7" rx="0.5" stroke="currentColor" strokeWidth="1.5"/>
      <rect x="6.5" y="3" width="3" height="10" rx="0.5" stroke="currentColor" strokeWidth="1.5"/>
      <rect x="11" y="5" width="3" height="8" rx="0.5" stroke="currentColor" strokeWidth="1.5"/>
    </svg>
  ),
};

const NAV_SECTIONS = [
  {
    label: "Markets",
    items: [
      { key: "tradfi", label: "TradFi", desc: "Commodities, equities, indices (HIP-3)" },
    ],
  },
  {
    label: "Intelligence",
    items: [
      { key: "chat", label: "AI Assist", desc: "Ask about any asset" },
      { key: "signals", label: "Signal Log", desc: "Historical signal events" },
      { key: "onchain", label: "On-Chain", desc: "On-chain analytics" },
    ],
  },
  {
    label: "Trading",
    items: [
      { key: "backtest", label: "Backtest", desc: "Strategy backtesting" },
      { key: "executor", label: "Executor", desc: "Signal execution engine" },
      { key: "trading", label: "Portfolio", desc: "Hyperliquid portfolio" },
    ],
  },
];

export default function NavDrawer({ isOpen, onClose, activeTab, onTabChange, isMobile, groups, activeGroupId, onGroupChange, onGroupCreate, onGroupEdit, onWatchlistSelect, scanData }) {
  const [mounted, setMounted] = useState(false);
  const [visible, setVisible] = useState(false);
  const navRef = useRef(null);
  const touchStart = useRef(null);

  useEffect(() => {
    if (isOpen) {
      setMounted(true);
      // Delay the visible state so the drawer starts off-screen then slides in
      requestAnimationFrame(() => {
        requestAnimationFrame(() => setVisible(true));
      });
    } else {
      setVisible(false);
      const t = setTimeout(() => setMounted(false), 300);
      return () => clearTimeout(t);
    }
  }, [isOpen]);

  // Swipe left to close (works with 1 finger on mobile, 2 on trackpad)
  const handleTouchStart = useCallback((e) => {
    touchStart.current = { x: e.touches[0].clientX, y: e.touches[0].clientY };
  }, []);

  const handleTouchEnd = useCallback((e) => {
    if (!touchStart.current) return;
    const dx = e.changedTouches[0].clientX - touchStart.current.x;
    const dy = e.changedTouches[0].clientY - touchStart.current.y;
    // Swipe left: negative dx, more horizontal than vertical
    if (dx < -60 && Math.abs(dx) > Math.abs(dy) * 1.5) {
      onClose();
    }
    touchStart.current = null;
  }, [onClose]);

  if (!mounted && !isOpen) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        onClick={onClose}
        style={{
          position: "fixed", inset: 0, zIndex: 199,
          background: "rgba(0,0,0,0.5)",
          backdropFilter: "blur(4px)", WebkitBackdropFilter: "blur(4px)",
          opacity: visible ? 1 : 0,
          transition: "opacity 0.3s ease",
          cursor: "pointer",
        }}
      />
      {/* Drawer */}
      <nav
        ref={navRef}
        onTouchStart={handleTouchStart}
        onTouchEnd={handleTouchEnd}
        style={{
        position: "fixed", top: 0, left: 0, bottom: 0,
        width: isMobile ? "85vw" : 300,
        maxWidth: 320,
        zIndex: 200,
        background: T.drawerBg,
        backdropFilter: "blur(32px) saturate(1.6)",
        WebkitBackdropFilter: "blur(32px) saturate(1.6)",
        borderRight: `1px solid ${T.border}`,
        boxShadow: `4px 0 40px ${T.shadowHeavy}`,
        transform: visible ? "translateX(0)" : "translateX(-100%)",
        transition: "transform 0.3s cubic-bezier(0.32, 0.72, 0, 1)",
        display: "flex", flexDirection: "column",
        overflowY: "auto",
      }}>
        {/* Drawer header */}
        <div style={{
          padding: "20px 20px 16px",
          borderBottom: `1px solid ${T.border}`,
          display: "flex", alignItems: "center", justifyContent: "space-between",
        }}>
          <span style={{
            fontFamily: T.font, fontSize: 15, fontWeight: 700,
            color: T.text1, letterSpacing: "-0.01em",
          }}>
            Navigation
          </span>
          <button
            onClick={onClose}
            style={{
              width: 32, height: 32, borderRadius: 8,
              border: `1px solid ${T.border}`,
              background: T.surface,
              color: T.text3, fontSize: 16,
              cursor: "pointer", display: "flex",
              alignItems: "center", justifyContent: "center",
              transition: "all 0.15s ease",
            }}
            onMouseEnter={e => { e.currentTarget.style.background = T.surfaceH; e.currentTarget.style.color = T.text1; }}
            onMouseLeave={e => { e.currentTarget.style.background = T.surface; e.currentTarget.style.color = T.text3; }}
          >
            {"\u2715"}
          </button>
        </div>

        {/* Scanner + Watchlists + Nav sections */}
        <div style={{ padding: "12px 12px 24px", flex: 1 }}>
          {/* ── Scanner section (All Assets + Watchlists) ── */}
          <div style={{ marginBottom: 20 }}>
            <div style={{
              fontSize: 11, fontWeight: 700, color: T.text4,
              fontFamily: T.font, letterSpacing: "0.1em",
              textTransform: "uppercase",
              padding: "0 8px 8px",
              display: "flex", alignItems: "center", justifyContent: "space-between",
            }}>
              <span>Scanner</span>
              <button
                onClick={() => { onGroupCreate?.(); onClose(); }}
                style={{
                  background: T.surface, border: `1px solid ${T.border}`,
                  borderRadius: 8, color: T.text3,
                  cursor: "pointer", fontSize: 20, fontWeight: 500,
                  width: 32, height: 32,
                  display: "flex", alignItems: "center", justifyContent: "center",
                  transition: "all 0.15s ease",
                }}
                onMouseEnter={e => { e.currentTarget.style.background = T.surfaceH; e.currentTarget.style.color = T.accent; e.currentTarget.style.borderColor = T.accent + "40"; }}
                onMouseLeave={e => { e.currentTarget.style.background = T.surface; e.currentTarget.style.color = T.text3; e.currentTarget.style.borderColor = T.border; }}
              >+</button>
            </div>

            {/* All Assets */}
            {(() => {
              const SCANNER_TABS = ["4h", "1d", "split"];
              const isAllActive = !activeGroupId && SCANNER_TABS.includes(activeTab);
              return (
                <button
                  onClick={() => { onWatchlistSelect?.(null); onClose(); }}
                  style={{
                    display: "flex", alignItems: "center", gap: 8,
                    width: "100%", textAlign: "left",
                    padding: "10px 12px", borderRadius: 10,
                    border: isAllActive ? `1px solid ${T.accent}30` : "1px solid transparent",
                    background: isAllActive ? T.accentDim : "transparent",
                    cursor: "pointer", transition: "all 0.15s ease",
                    marginBottom: 2,
                  }}
                  onMouseEnter={e => { if (!isAllActive) e.currentTarget.style.background = T.surface; }}
                  onMouseLeave={e => { if (!isAllActive) e.currentTarget.style.background = isAllActive ? T.accentDim : "transparent"; }}
                >
                  <div style={{
                    width: 20, height: 20,
                    display: "flex", alignItems: "center", justifyContent: "center",
                    color: isAllActive ? T.accent : T.text3,
                    flexShrink: 0,
                  }}>
                    {NAV_ICONS["1d"]}
                  </div>
                  <span style={{
                    fontFamily: T.font, fontSize: 14,
                    fontWeight: isAllActive ? 600 : 500,
                    color: isAllActive ? T.accent : T.text1,
                  }}>All Assets</span>
                  <span style={{
                    fontSize: 11, color: T.text4, fontFamily: T.mono,
                    marginLeft: "auto",
                  }}>{scanData?.length || 0}</span>
                </button>
              );
            })()}

            {/* Watchlists */}
            {groups && groups.map(g => {
              const isActive = g.id === activeGroupId;
              const gColor = g.color || T.accent;

              // Compute group performance vs BTC
              const btcMom = scanData?.find(r => r.symbol === "BTC/USDT")?.momentum ?? 0;
              const members = scanData?.filter(r => g.symbols?.includes(r.symbol)) || [];
              const beating = members.filter(r => (r.momentum ?? 0) > btcMom).length;
              const total = members.length;

              return (
                <div key={g.id} style={{ display: "flex", alignItems: "center", gap: 4, marginBottom: 2 }}>
                  <button
                    onClick={() => { onWatchlistSelect?.(g.id); onClose(); }}
                    style={{
                      flex: 1, display: "flex", alignItems: "center", gap: 8,
                      padding: "10px 12px", borderRadius: 10, textAlign: "left",
                      border: isActive ? `1px solid ${gColor}40` : "1px solid transparent",
                      background: isActive ? `${gColor}12` : "transparent",
                      cursor: "pointer", transition: "all 0.15s ease",
                    }}
                    onMouseEnter={e => { if (!isActive) e.currentTarget.style.background = T.surface; }}
                    onMouseLeave={e => { if (!isActive) e.currentTarget.style.background = isActive ? `${gColor}12` : "transparent"; }}
                  >
                    <span style={{
                      width: 8, height: 8, borderRadius: "50%",
                      background: gColor, flexShrink: 0,
                      opacity: isActive ? 1 : 0.4,
                    }} />
                    <span style={{
                      fontFamily: T.font, fontSize: 14,
                      fontWeight: isActive ? 600 : 500,
                      color: isActive ? gColor : T.text1,
                    }}>{g.name}</span>
                    <span style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 6 }}>
                      {total > 0 && (
                        <span style={{
                          fontSize: 10, fontFamily: T.mono, fontWeight: 600,
                          color: beating > total / 2 ? T.green : beating > 0 ? T.yellow : T.text4,
                          letterSpacing: "0.02em",
                        }}>
                          {beating}/{total} {"\u25B2"}BTC
                        </span>
                      )}
                      <span style={{
                        fontSize: 11, color: T.text4, fontFamily: T.mono,
                      }}>{g.symbols?.length || 0}</span>
                    </span>
                  </button>
                  <button
                    onClick={() => { onGroupEdit?.(g); onClose(); }}
                    style={{
                      width: 32, height: 32, borderRadius: 8,
                      border: `1px solid ${T.border}`, background: T.surface,
                      color: T.text3, cursor: "pointer", fontSize: 16,
                      display: "flex", alignItems: "center", justifyContent: "center",
                      flexShrink: 0, transition: "all 0.15s ease",
                    }}
                    onMouseEnter={e => { e.currentTarget.style.background = T.surfaceH; e.currentTarget.style.color = T.text1; }}
                    onMouseLeave={e => { e.currentTarget.style.background = T.surface; e.currentTarget.style.color = T.text3; }}
                  >{"\u2699"}</button>
                </div>
              );
            })}
          </div>

          {/* ── Other nav sections ── */}
          {NAV_SECTIONS.map((section) => (
            <div key={section.label} style={{ marginBottom: 20 }}>
              <div style={{
                fontSize: 11, fontWeight: 700, color: T.text4,
                fontFamily: T.font, letterSpacing: "0.1em",
                textTransform: "uppercase",
                padding: "0 8px 8px",
              }}>
                {section.label}
              </div>
              {section.items
                .filter(item => !item.desktopOnly || !isMobile)
                .map((item) => {
                  const isActive = activeTab === item.key;
                  return (
                    <button
                      key={item.key}
                      onClick={() => { onTabChange(item.key); onClose(); }}
                      style={{
                        display: "flex", alignItems: "center", gap: 12,
                        width: "100%", textAlign: "left",
                        padding: "12px 12px",
                        borderRadius: 10,
                        border: isActive ? `1px solid ${T.accent}30` : "1px solid transparent",
                        background: isActive ? T.accentDim : "transparent",
                        cursor: "pointer",
                        transition: "all 0.15s ease",
                        marginBottom: 2,
                      }}
                      onMouseEnter={e => { if (!isActive) e.currentTarget.style.background = T.surface; }}
                      onMouseLeave={e => { if (!isActive) e.currentTarget.style.background = "transparent"; }}
                    >
                      <div style={{
                        width: 20, height: 20,
                        display: "flex", alignItems: "center", justifyContent: "center",
                        color: isActive ? T.accent : T.text3,
                        flexShrink: 0,
                      }}>
                        {NAV_ICONS[item.key] || null}
                      </div>
                      <div style={{ minWidth: 0 }}>
                        <div style={{
                          fontFamily: T.font, fontSize: T.textLg, fontWeight: isActive ? 600 : 500,
                          color: isActive ? T.accent : T.text1,
                          letterSpacing: "-0.01em",
                        }}>
                          {item.label}
                        </div>
                        <div style={{
                          fontFamily: T.font, fontSize: T.textSm, color: T.text4,
                          marginTop: 1,
                        }}>
                          {item.desc}
                        </div>
                      </div>
                    </button>
                  );
                })}
            </div>
          ))}
        </div>
      </nav>
    </>
  );
}
