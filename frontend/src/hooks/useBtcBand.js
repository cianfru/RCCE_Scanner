import { useEffect, useState } from "react";
import { apiJson } from "../edge.js";
import { pollWhileVisible } from "../utils/visiblePoll.js";

// The BTC weekly-band entry block (/api/btc-band, backend btc_band_block.py): the executor takes no new long while
// BTC's weekly close has been under its band for 2+ weeks. Read on load and hourly while visible.
export default function useBtcBand() {
  const [band, setBand] = useState(null);
  useEffect(() => {
    let alive = true;
    const load = () => apiJson("/api/btc-band").then(d => { if (alive) setBand(d); }).catch(() => {});
    load();
    const stop = pollWhileVisible(load, 3_600_000);
    return () => { alive = false; stop(); };
  }, []);
  return band;
}
