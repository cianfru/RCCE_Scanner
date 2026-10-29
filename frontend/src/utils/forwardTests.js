// The forward test of funding and whales (/api/market-history/forward; docs/reviews/funding-whales-forward-test.md):
// one quiet line under the Chart view, with the rules behind an (i). Collecting under 180 forward days, interim from
// 180 (numbers, no verdict), the verdict on the first 365.

export const FWCOPY = {
  title: "Forward tests",
  since: "from 30 Oct 2026",
  names: { funding: "Funding", whales: "Whales" },
  status: t => {
    if (!t) return "—";
    const r = t.partial == null ? "" : ` · ${t.partial > 0 ? "+" : ""}${t.partial.toFixed(2)}`;
    if (t.status === "verdict") return `${t.verdict === "met" ? "bar met" : "bar not met"}${r}`;
    return `${t.days} of ${t.needed} days${t.status === "interim" ? r : ""}`;
  },
  pop: () => [
    "Each day from 30 October 2026, the reading against what the typical coin did over the next 30 days, with its last 30 days held fixed. Funding passes at -0.15 or lower, whales at +0.15 or higher, with a 90% interval clear of zero.",
    "Numbers show from 180 days; the verdict is taken once, on the first 365. Rules fixed before the first day. Context, not a signal.",
  ],
};
