// Close and cancel, moved verbatim from TradingPanel.jsx (Portfolio v2, section 5). Only the
// presentation changes: the same guard, the same calls and arguments, the same journal request and
// notice texts. The one exception: with PF_CONFIRM_SHEET on, the confirm is the close sheet
// (CloseConfirm.jsx) instead of window.confirm. It stays off until the owner approves it.
// Never from this page: placeMarketOrder or setLeverage, or a close or cancel on a builder-dex row.
import { kKey } from "../../utils/tickerRenames.js";

export const PF_CONFIRM_SHEET = false;

// Once the exchange has accepted an action, a journal failure cannot undo it (from Codex).
export async function executeAndJournal(execute, journal) {
  const execution = await execute();
  try {
    const response = await journal(execution);
    if (response && !response.ok) throw new Error(`Journal HTTP ${response.status}`);
    return { execution, journalPending: false };
  } catch {
    return { execution, journalPending: true };
  }
}

export function parseNum(v) {
  if (v == null) return 0;
  const n = typeof v === "string" ? parseFloat(v) : v;
  return isNaN(n) ? 0 : n;
}

// The arguments a close is sent with: Hyperliquid's raw coin, |szi| as Hyperliquid reported it (never
// the display-rounded size) and the side.
export const closeArgs = position => ({ coin: position.coin, size: Math.abs(parseNum(position.szi)), isLong: parseNum(position.szi) > 0 });

// A row that can be closed or cancelled from this page: main-dex perps only (hlOrder.assetFor throws
// for builder-dex coins).
export const tradable = coin => typeof coin === "string" && !coin.includes(":") && !coin.startsWith("@");

// deps: { api, hlClient, readOnly, walletClient, setClosing, setCancelling, setActionNotice, fetchFast,
// confirm(coin) -> boolean | Promise<boolean>, fetch }.
export function makeTradeActions(deps) {
  const { api, hlClient, readOnly, walletClient, setClosing, setCancelling, setActionNotice, fetchFast } = deps;
  const confirm = deps.confirm || (coin => window.confirm(`Close ${coin} position?`));
  const fetch = deps.fetch || globalThis.fetch;

  const closePosition = async (coin, size, isLong) => {
    if (readOnly || !walletClient) return;
    if (!(await confirm(coin))) return;
    setClosing(coin);
    setActionNotice(null);
    try {
      const outcome = await executeAndJournal(
        () => hlClient.closePosition(walletClient, { coin, size, isLong, slippage: 0.02 }),
        result => fetch(`${api}/api/trade/log-close`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            symbol: `${kKey(coin)}/USDT`,
            exit_price: result.avgPx,
            close_order_id: String(result.oid || ""),
          }),
        }),
      );
      setActionNotice({ section: "positions", coin, tone: "ok", text: `${coin} closed. Order ${outcome.execution?.oid || "accepted"}.${outcome.journalPending ? " Journal sync pending; do not close again." : " Journal synced."}` });
      await fetchFast();
    } catch (e) {
      console.error("Close error:", e);
      setActionNotice({ section: "positions", coin, tone: "error", text: `Close could not be confirmed: ${e.message || "connection failed"}. Refresh positions and check the exchange before trying again.` });
    }
    setClosing(null);
  };

  const cancelOrd = async (coin, oid) => {
    if (readOnly || !walletClient) return;
    setCancelling(oid);
    setActionNotice(null);
    try {
      await hlClient.cancelOrder(walletClient, { coin, oid });
      await fetchFast();
    } catch (e) {
      console.error("Cancel error:", e);
      setActionNotice({ section: "orders", coin, tone: "error", text: `Cancellation could not be confirmed: ${e.message || "connection failed"}. Refresh orders before trying again.` });
    }
    setCancelling(null);
  };

  return { closePosition, cancelOrd };
}
