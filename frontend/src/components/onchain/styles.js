// Shared style constants for on-chain components
import { T } from "../../theme.js";

export const S = {
  section: { marginBottom: 16 },
  label: {
    fontSize: 10,
    color: T.text4,
    fontFamily: T.mono,
    letterSpacing: "0.06em",
    fontWeight: 600,
  },
  input: {
    padding: "8px 12px",
    borderRadius: 10,
    border: `1px solid ${T.border}`,
    background: T.overlay06,
    color: T.text1,
    fontFamily: T.mono,
    fontSize: 12,
    outline: "none",
    flex: 1,
    minWidth: 0,
  },
  select: {
    padding: "8px 12px",
    borderRadius: 10,
    border: `1px solid ${T.border}`,
    background: T.overlay06,
    color: T.text1,
    fontFamily: T.mono,
    fontSize: 12,
    outline: "none",
    appearance: "none",
    cursor: "pointer",
  },
  btn: {
    padding: "8px 16px",
    borderRadius: 10,
    border: "none",
    cursor: "pointer",
    fontFamily: T.mono,
    fontSize: 11,
    fontWeight: 700,
    letterSpacing: "0.04em",
    background: "linear-gradient(180deg, #2ee0f8 0%, #1ab8d4 100%)",
    color: "#000",
    transition: "all 0.2s",
  },
  btnDanger: {
    padding: "4px 10px",
    borderRadius: 8,
    border: "none",
    cursor: "pointer",
    fontFamily: T.mono,
    fontSize: 10,
    fontWeight: 600,
    background: "rgba(248,113,113,0.12)",
    color: "#f87171",
  },
  chip: (color) => ({
    display: "inline-flex",
    alignItems: "center",
    gap: 4,
    padding: "3px 10px",
    borderRadius: 20,
    fontSize: 9,
    fontWeight: 700,
    fontFamily: T.mono,
    letterSpacing: "0.04em",
    background: `${color}18`,
    color,
    border: `1px solid ${color}30`,
  }),
  th: {
    padding: "8px 10px",
    textAlign: "left",
    fontSize: 9,
    fontWeight: 700,
    color: T.text4,
    fontFamily: T.mono,
    letterSpacing: "0.08em",
    borderBottom: `1px solid ${T.borderH}`,
    whiteSpace: "nowrap",
  },
  td: {
    padding: "8px 10px",
    fontSize: 11,
    fontFamily: T.mono,
    whiteSpace: "nowrap",
  },
};

export const CHAIN_META = {
  ethereum: { label: "ETH", color: "#627eea", explorer: "https://etherscan.io" },
  base: { label: "BASE", color: "#0052ff", explorer: "https://basescan.org" },
  solana: { label: "SOL", color: "#9945ff", explorer: "https://solscan.io" },
};

export const ALERT_COLORS = {
  ACCUMULATING: "#22d3ee",
  DISTRIBUTING: "#f87171",
  NEW_WHALE: "#34d399",
  LARGE_BUY: "#34d399",
  LARGE_SELL: "#f87171",
};

export const ACTIVITY_COLORS = {
  ACCUMULATING: "#34d399",
  DISTRIBUTING: "#f87171",
  MIXED: "#fbbf24",
  INACTIVE: "#6b7280",
  HOLDING: "#6b7280",
  NEW: "#60a5fa",
  NET_BUYER: "#34d399",
  NET_SELLER: "#f87171",
};

export const ADDRESS_TYPE_COLORS = {
  LP: "#a78bfa",
  ROUTER: "#f59e0b",
  CEX: "#3b82f6",
  CONTRACT: "#6b7280",
  WALLET: "",  // no badge for regular wallets
};
