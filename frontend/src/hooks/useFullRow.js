// A coin's full scan row (/api/scan/row) laid over its list row. The scanner lists carry only
// what the grid, Radar and search read (backend/scan_view.py); the coin page and the detail
// panel need the rest (condition cards, positioning detail...). Until the full row arrives the
// list row is shown as it is; each new scan pass (evaluated_at) loads it again.
import { useEffect, useMemo, useState } from "react";
import { apiFetch } from "../edge.js";
import { rowQuery, withFullRow } from "../utils/scanRows.js";

export default function useFullRow(row) {
  const [full, setFull] = useState(null);
  const symbol = row?.symbol;
  const timeframe = row?.timeframe;
  const market = row?.market_kind;
  const version = row?.evaluated_at;
  useEffect(() => {
    if (!symbol) { setFull(null); return undefined; }
    let cancelled = false;
    apiFetch(rowQuery({ symbol, timeframe, market_kind: market }, version))
      .then(r => (r.ok ? r.json() : null))
      .then(d => { if (!cancelled && d?.row) setFull(d.row); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [symbol, timeframe, market, version]);
  return useMemo(() => withFullRow(row, full && (!timeframe || full.timeframe === timeframe) ? full : null),
    [row, full, timeframe]);
}
