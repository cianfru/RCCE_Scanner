// The scanner's go/no-go line for new longs, from the BTC weekly-band block (/api/btc-band). Words for what happened.
export function bandWords(b) {
  if (!b || !b.available) return null;
  if (b.blocked) return { go: false, head: "New longs paused", line: `BTC closed under its weekly band ${b.weeks_below} weeks in a row` };
  if (b.weeks_below === 1) return { go: true, head: "New longs allowed", line: "BTC closed one week under its weekly band" };
  return { go: true, head: "New longs allowed", line: "BTC's weekly close is above its band" };
}
