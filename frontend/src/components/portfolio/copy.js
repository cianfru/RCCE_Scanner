// Every visible string and (i) text on the Portfolio page (Portfolio v2, section 7). copy.test.js scans
// this file and every portfolio/*.jsx for the words the page never uses.

export const TITLE = "Portfolio";

export const LABELS = {
  equity: "EQUITY", liquidation: "LIQUIDATION", exposure: "EXPOSURE", reflex: "REFLEX",
  position: "POSITION", levels: "LEVELS", scanner: "SCANNER", held: "WHILE HELD", traders: "TRADERS",
  tradfi: "TRADFI", other: "OTHER VENUES", since: "SINCE", toLiq: "TO LIQ",
};

export const INFO = {
  clock: "Time to the next 4H, daily and weekly candle closes (UTC). Signals are rechecked after each 4H close; the band reads weekly closes.",
  equity: "Everything this address holds on Hyperliquid: perps on every venue (cross and isolated), spot at mid, Earn, staked HYPE and vaults. 24h is Hyperliquid's own P&L for the day; deposits and withdrawals are left out.",
  liquidation: "Margin is maintenance margin over account value; Hyperliquid liquidates at 100%. Above: the position nearest its liquidation price, from Hyperliquid's mark, in % and in daily ATRs (14-day average daily range).",
  exposure: "One block per position. Width is notional, colour its open P&L; longs right, shorts left, TradFi hatched. Leverage is gross notional over equity.",
  reflex: "Share of open notional where the scanner's 4H (or 1D) signal points your way. Short signals have no measured edge; read shorts as context. Map: your positions on the Radar, stretch across and profitable traders long minus short up. Context, not a signal; the forward test has run since 29 Sep 2026.",
  since: "Compared with what this browser saw on your last visit, kept on this device only. Fills and funding from Hyperliquid; signal changes from the scanner.",
  since24: "Compared with 24 hours ago: Hyperliquid's P&L for the day, fills and positions from Hyperliquid, signal changes from the scanner's log, trader counts from a day ago.",
  levels: "Your entry (circle), nearest stop and take-profit (triangles; +n more), and liquidation (red tick, hatched) on one price line, with the weekly band (violet), the trend line (grey tick), profitable traders' median entry on your side (diamond) and, faint, where the mark was on your last visit.",
  toLiq: "From Hyperliquid's mark to the liquidation price, in % and in daily ATRs (14-day average daily range).",
  scanner: "4H signal and how long it has held; \"1D\" names the daily signal when it is behind an exit or 1D against. Bar: heat, stretch above the weekly band, 0-100; the tick is 95, where the signal turns to Trim; a faint tick is where heat was before the last scan.",
  held: "What the scanner showed since you opened: 4H regime colours (hover for the key) and signal changes.",
  traders: "Profitable tracked traders long · short, linked wallets counted once. Context, not a signal.",
  chart: "Hyperliquid's own history for the whole account. P&L leaves out deposits and withdrawals.",
  calendar: "Realised P&L per UTC day: closed trades net of fees, plus funding. The total beside the month is the same sum. The period tabs count open P&L as well, so the two differ by the open P&L. Hatched days are before the fills on hand.",
  funding: "Negative is paid, positive received.",
};

export const CHECKS = {
  exit: { label: "Exit signal", info: "Trim, Trim hard, Risk off or No long on a long, 4H or 1D. After past Trims, the median coin trailed the market by 3-5% over 7 days (n = 75 and 89)." },
  d1against: { label: "1D against", info: "The daily signal points the other way. On shorts the scanner is context only." },
  underband: { label: "Under band", info: "Last weekly close was under the support band." },
  nostop: { label: "No stop", info: "No stop order on this position." },
  stoppastliq: { label: "Stop past liq", info: "The stop sits beyond the liquidation price." },
  liq2atr: { label: "Liq < 2 ATR", info: "Liquidation is less than two average daily ranges from the mark (15% where no ATR)." },
  liqaboveband: { label: "Liq above band", info: "Liquidation sits between price and the weekly support band." },
  tradersleft: { label: "Traders left", info: "Profitable tracked traders on your side, linked wallets counted once. Context, not a signal." },
};

export const STRIP = {
  partial: "partial", h24: "24h", margin: "Margin", atr: "ATR", netLong: "Net long", netShort: "Net short", gross: "Gross",
  with: "with", against: "Against", noSignal: "No signal", notCovered: "Not covered", tf4h: "4H", tf1d: "1D",
  openPnl: "Open P&L", withdrawable: "Withdrawable", share: "Share", sinceVisit: d => `since ${d}`, carry: "/d",
  partialInfo: names => `Not answering now: ${names}.`,
  parts: { perps: "Perps", tradfi: "TradFi", other: "Other venues", spot: "Spot", earn: "Earn", staked: "Staked", vaults: "Vaults" },
};

export const RAIL = {
  liq: "Liq", sl: "SL", tp: "TP", entry: "Entry", mark: "Mark", band: "Band", trend: "Trend", tradersEntry: "Traders' entry",
  swingLow: "Swing low", swingHigh: "Swing high", atr: "Daily ATR", noStop: "no stop", none: "none",
  bandState: { above: "above", inside: "inside", under_now: "under now", closed_under: "closed under" },
};

export const ROWS = {
  long: "Long", short: "Short", iso: "iso", tradfi: "TradFi", watch: "Watch", watching: "Watching", radar: "Radar",
  close: "Close", closing: "Closing…", more: n => `+${n} more`, nearestLiq: p => `nearest liq ${p}`,
  noPositions: "No open positions",
  lastClosed: (coin, side, pnl, a) => `last closed ${coin} ${side} ${pnl} · ${a}`,
  preview: "preview", dismiss: "Dismiss", notCovered: "Not covered by the scanner",
};

export const SINCE = {
  lastVisit: "Last visit", h24: "24H", nothing: "Nothing changed", fills: n => `${n} ${n === 1 ? "fill" : "fills"}`,
  changes: n => `${n} ${n === 1 ? "change" : "changes"}`,
  opened: "Opened", closed: "Closed",
  heat: "heat", liq: "liq", band: "band", traders: "traders", regime: "regime",
};

export const SORTS = [{ key: "closest", label: "Closest" }, { key: "size", label: "Size" }, { key: "pnl", label: "P&L" }];

export const DETAIL = {
  d7: "7D", trip: "Trip",
  size: "SIZE", value: "VALUE", entry: "ENTRY", mark: "MARK", liq: "LIQ", margin: "MARGIN", funding: "FUNDING", carry: "CARRY",
  opened: "OPENED", addsTrims: "ADDS · TRIMS", realised: "REALISED", fees: "FEES", atOpen: "AT OPEN",
  tradersEntry: "TRADERS' ENTRY", inProfit: "IN PROFIT", cross: "cross", isolated: "isolated",
  ordersOn: (coin, n) => `Orders on ${coin} · ${n}`,
  stopMarket: "Stop market", stopLimit: "Stop limit", takeProfit: "Take profit", limit: "Limit", cap: "cap", reduce: "reduce", cancel: "Cancel",
  bids: n => `${n} bids`, asks: n => `${n} asks`, before: d => `before ${d}`, moreOrders: n => `+${n} more`,
  cols: { type: "Type", price: "Price", size: "Size", fromMark: "From mark" },
  perDay: "/day", you: "you", of: "of", pnlShare: "P&L share",
};

export const SHEET = {
  title: (coin, side) => `Close ${coin} ${side}`,
  detail: (size, coin, usd) => `${size} ${coin} · ${usd} · market, up to 2% slippage`,
  go: "Close at market", keep: "Keep", preview: "Preview: no order is sent from this page.",
};

export const CAL = { closes: "Closes", funding: "Funding", fees: "Fees", prev: "Previous month", next: "Next month", week: "W", days: ["M", "T", "W", "T", "F", "S", "S"] };

export const PERF = {
  periods: [{ key: "1d", label: "1D", src: "day" }, { key: "1w", label: "1W", src: "week" }, { key: "1m", label: "1M", src: "month" }, { key: "all", label: "All", src: "allTime" }],
  pnl: "P&L", equity: "Equity", high: "High", low: "Low", lastVisit: "Last visit", maxDd: "Max drawdown",
};

export const TABS = {
  orders: "Orders", fills: "Fills", funding: "Funding", older: "Older", newer: "Newer", total30: v => `30d ${v}`, d30: "30d",
  cols: { type: "Type", side: "Side", trigger: "Trigger", limit: "Limit", size: "Size", reduce: "Reduce", fromMark: "From mark",
    time: "Time", coin: "Coin", dir: "Direction", price: "Price", closedPnl: "Closed P&L", fee: "Fee", total: "Total" },
  buy: "Buy", sell: "Sell", tp: n => `${n} TP`, sl: n => `${n} SL`, stops: n => `${n} stop`, limits: n => `${n} limit`, nearest: p => `nearest ${p}`,
  none: { orders: "No open orders", fills: "No fills in the last 30 days", funding: "No funding in the last 30 days" },
};

export const IDENTITY = {
  readOnly: "read-only", stopViewing: "Stop viewing", copied: "Copied", close4h: "4H close",
  failed: f => `${f} failed`, nFailed: n => `${n} feeds failed`, retry: "Retry", stale: "Stale",
  asOf: t => `as of ${t}`,
};

export const FEEDS = {
  main: "Perps", xyz: "TradFi", other: "Other venues", spot: "Spot", orders: "Orders", ordersXyz: "Orders",
  fills: "Fills", portfolio: "Portfolio", funding: "Funding", staking: "Staking", vaults: "Vaults", earn: "Earn",
  context: "Scanner", events: "Scanner", mids: "Spot", meta: "Spot",
};

export const CONNECT = {
  prompt: "Connect your wallet to view your Hyperliquid portfolio",
  connect: "Connect wallet",
  viewLabel: "or view an address (read-only)",
  view: "View",
  invalid: "Not a Hyperliquid address (0x and 40 hex characters).",
};
