// One set of definitions for the groups of wallets the app names. Two systems feed them:
// the tracked list (profitable traders, large accounts; rebuilt daily from the Hyperliquid
// leaderboard) and the wider cohort sweep (all-time winners and losers, whales; about 2,300
// large or long-profitable wallets). Copy only: what each group is, never what it means next.

const n = v => (v ? Number(v).toLocaleString("en-US") : null);    // 0: lists not built yet, so unknown

// counts: /api/hyperlens/status ({ money_printer_count, smart_money_count, elite_count }), optional.
export function groupDefinitions(counts = {}) {
  const mp = n(counts.money_printer_count), sm = n(counts.smart_money_count), elite = n(counts.elite_count);
  return {
    profitable: `Profitable traders: Hyperliquid wallets up 30%+ and $10K+ over the last month and not down before it; up to 600, best monthly return first${mp ? ` (${mp} on the list now)` : ""}. Rebuilt daily.`,
    large: `Large accounts: ${sm ? `${sm} ` : "about 60 "}Hyperliquid accounts of $1M and up: the profitable traders among the 300 largest accounts${elite ? ` (${elite} now)` : ""}, then the largest of the rest, whose profit is not checked.`,
    tracked: `All tracked wallets: both lists together${mp && sm ? `, ${n(Number(counts.money_printer_count) + Number(counts.smart_money_count) - Number(counts.elite_count || 0))} wallets` : ""}.`,
    winners: "All-time winners: up $100K+ over their whole Hyperliquid history.",
    losers: "All-time losers: a net loss over it.",
    whales: "Whales: $1M+ in their perp account.",
    windows: "Profitable traders is about this month; all-time winners about every month since the wallet started. A wallet can be in several groups.",
    sweep: "All-time winners, losers and whales: about 2,300 wallets with $100K+ in perps, or $100K+ all-time profit and $10K+ in perps; market makers left out.",
  };
}

// The groups on a coin page's long/short chart, in display order.
export const COIN_GROUPS = [
  { key: "profitable", name: "Profitable traders", sub: "best monthly return" },
  { key: "winners", name: "All-time winners", sub: "$100K+ profit" },
  { key: "losers", name: "All-time losers", sub: "net loss" },
  { key: "whales", name: "Whales", sub: "$1M+ account" },
];
