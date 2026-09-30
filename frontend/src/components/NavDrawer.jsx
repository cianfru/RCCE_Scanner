import { useState, useEffect, useRef, useCallback } from "react";
import { T } from "../theme.js";
import { NAV_ICONS } from "./navIcons.jsx";
import { getAdminKey } from "../auth.js";
import { useAccount } from "../account.js";

// More: the rarely used pages, one tap from the hamburger. The four main pages live in the
// header tabs (and the phone tab bar), so they are not repeated here. The theme switch is in
// the header; /settings is the owner's page, opened by its address, so it is not listed.
const NAV_SECTIONS = [
  {
    label: "Research",
    items: [
      { key: "signals", label: "Signal Log", desc: "Historical signal events" },
      { key: "analytics", label: "Analytics", desc: "Signal performance attribution" },
      { key: "bridge", label: "Bridge", desc: "USDC in and out of Hyperliquid" },
    ],
  },
  {
    label: "Tools",
    items: [
      { key: "backtest", label: "Backtest", desc: "Strategy backtesting" },
      { key: "executor", label: "Executor", desc: "Signal execution engine" },
      { key: "chat", label: "AI Assist", desc: "Explain the scanner’s market data · limited daily use" },
    ],
  },
];
// "(HIP-3)" never breaks across lines.
const TRADFI = { key: "tradfi", label: "TradFi", desc: <>Commodities, equities, indices <span style={{ whiteSpace: "nowrap" }}>(HIP-3)</span></> };
// Listed only in the owner's browser (the admin key, or the owner's wallet signed in).
const OWNER_ITEMS = [{ key: "intel", label: "Intel", desc: "Who uses Reflex, how and from where" }];
const MARKETS = [
  { kind: "perpetual", icon: "perps", label: "Perpetuals" },
  { kind: "spot", icon: "spot", label: "Spot markets" },
];

// Section labels: sentence case, Geist 12/600, text3 (as in the gear popover).
const sectionLabel = {
  fontSize: 12, fontWeight: 600, color: T.text3, fontFamily: T.font, letterSpacing: 0,
  padding: "0 8px 8px",
};

// The 16px glyph in a 20px slot, so every label in the drawer starts on the same column.
function RowIcon({ name, active }) {
  return (
    <div style={{
      width: 20, height: 20,
      display: "flex", alignItems: "center", justifyContent: "center",
      color: active ? T.accent : T.text3,
      flexShrink: 0,
    }}>
      {NAV_ICONS[name] || null}
    </div>
  );
}

// A scanner market: glyph, label and the number of markets scanned, one line.
function MarketRow({ market, count, active, onSelect }) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-current={active ? "page" : undefined}
      style={{
        display: "flex", alignItems: "center", gap: 12,
        width: "100%", textAlign: "left",
        padding: "14px 12px",
        border: 0,
        borderLeft: `2px solid ${active ? T.accent : "transparent"}`,
        background: active ? T.accentDim : "transparent",
        cursor: "pointer",
        transition: "all 0.15s ease",
        marginBottom: 2,
      }}
      onMouseEnter={e => { if (!active) e.currentTarget.style.background = T.surface; }}
      onMouseLeave={e => { if (!active) e.currentTarget.style.background = "transparent"; }}
    >
      <RowIcon name={market.icon} active={active} />
      <span style={{ flex: 1, minWidth: 0, display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 8 }}>
        <span style={{
          fontFamily: T.font, fontSize: T.textLg, fontWeight: active ? 600 : 500,
          color: active ? T.accent : T.text1,
          letterSpacing: "-0.01em",
        }}>
          {market.label}
        </span>
        <span title="markets scanned" style={{ fontFamily: T.font, color: T.text3, fontSize: 12, fontVariantNumeric: "tabular-nums" }}>
          {count}
        </span>
      </span>
    </button>
  );
}

function NavRow({ item, active, onSelect }) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-current={active ? "page" : undefined}
      style={{
        display: "flex", alignItems: "center", gap: 12,
        width: "100%", textAlign: "left",
        padding: "12px 12px",
        border: 0,
        borderLeft: `2px solid ${active ? T.accent : "transparent"}`,
        background: active ? T.accentDim : "transparent",
        cursor: "pointer",
        transition: "all 0.15s ease",
        marginBottom: 2,
      }}
      onMouseEnter={e => { if (!active) e.currentTarget.style.background = T.surface; }}
      onMouseLeave={e => { if (!active) e.currentTarget.style.background = "transparent"; }}
    >
      <RowIcon name={item.key} active={active} />
      <div style={{ minWidth: 0 }}>
        <div style={{
          fontFamily: T.font, fontSize: T.textLg, fontWeight: active ? 600 : 500,
          color: active ? T.accent : T.text1,
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
}

// Watch-group props (groups, activeGroupId, onGroupChange, onGroupCreate, onGroupEdit,
// onWatchlistSelect) are still accepted; the Lists section stays dormant (owner decision).
export default function NavDrawer({ isOpen, onClose, activeTab, onTabChange, isMobile, scanData, marketKind, onMarketChange }) {
  const [mounted, setMounted] = useState(false);
  const [visible, setVisible] = useState(false);
  const navRef = useRef(null);
  const touchStart = useRef(null);
  const account = useAccount();
  const owner = !!getAdminKey() || !!account?.owner;

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

  // Keyboard and scroll: focus moves in and stays in (Tab wraps), the page behind does not
  // scroll, Escape closes, and focus returns to what opened the drawer (the More button).
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  useEffect(() => {
    if (!isOpen || !mounted) return;
    const previous = document.activeElement;
    const bodyOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    navRef.current?.focus();
    const onKey = (e) => {
      if (e.key === "Escape") { e.preventDefault(); onCloseRef.current(); }
      if (e.key !== "Tab") return;
      const nodes = [...(navRef.current?.querySelectorAll('button:not([disabled]),a[href],input,[tabindex="0"]') || [])].filter(n => n.getClientRects().length);
      const first = nodes[0], last = nodes.at(-1);
      if (!first) { e.preventDefault(); return; }
      if (e.shiftKey && (document.activeElement === first || document.activeElement === navRef.current)) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && (document.activeElement === last || !navRef.current?.contains(document.activeElement))) { e.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = bodyOverflow;
      const back = previous && previous !== document.body && previous.isConnected ? previous : document.querySelector(".header-more");
      back?.focus?.();
    };
  }, [isOpen, mounted]);

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

  const go = key => () => { onTabChange(key); onClose(); };

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
        tabIndex={-1}
        aria-label="More"
        className="more-drawer"
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
        overscrollBehavior: "contain",
        outline: "none",
      }}>
        {/* Drawer header: the ribbon mark, "More", close */}
        <div style={{
          padding: "20px 20px 16px",
          borderBottom: `1px solid ${T.border}`,
          display: "flex", alignItems: "center", justifyContent: "space-between",
        }}>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 10 }}>
            <img src="/brand/reflex-ribbon-transparent.svg" width={24} height={24} alt="" />
            <span style={{
              fontFamily: T.font, fontSize: 15, fontWeight: 700,
              color: T.text1, letterSpacing: "-0.01em",
            }}>
              More
            </span>
          </span>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close More"
            title="Close"
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
            {"✕"}
          </button>
        </div>

        <div style={{ padding: "12px 12px 24px", flex: 1 }}>
          {/* ── Markets: the scanner's two markets, then TradFi ── */}
          <div style={{ marginBottom: 20 }}>
            <div style={sectionLabel}>Markets</div>

            {MARKETS.map(market => (
              <MarketRow key={market.kind} market={market}
                count={scanData?.filter(r => r.market_kind === market.kind).length || 0}
                active={["4h", "1d"].includes(activeTab) && marketKind === market.kind}
                onSelect={() => { onMarketChange?.(market.kind); onClose(); }} />
            ))}

            {/* Watchlists */}

            <NavRow item={TRADFI} active={activeTab === TRADFI.key} onSelect={go(TRADFI.key)} />
          </div>

          {/* ── Research, Tools ── */}
          {NAV_SECTIONS.map((section) => (
            <div key={section.label} style={{ marginBottom: 20 }}>
              <div style={sectionLabel}>{section.label}</div>
              {section.items.map(item => (
                <NavRow key={item.key} item={item} active={activeTab === item.key} onSelect={go(item.key)} />
              ))}
            </div>
          ))}

          {owner && (
            <div style={{ marginBottom: 20 }}>
              <div style={sectionLabel}>Owner</div>
              {OWNER_ITEMS.map(item => (
                <NavRow key={item.key} item={item} active={activeTab === item.key} onSelect={go(item.key)} />
              ))}
            </div>
          )}
        </div>
      </nav>
    </>
  );
}
