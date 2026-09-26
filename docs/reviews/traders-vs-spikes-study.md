# Who comes first, the traders or the spike? (declared 26 September 2026, before collecting data)

Question: when a coin spikes, did the profitable traders open their positions before the move, or pile in after it? And when two or more of them converge on a coin, did price tend to follow?

This is a one-off reconstruction from Hyperliquid's public records. It runs outside the production server, so it costs nothing to run. It describes the past. The forward test (docs/reviews/trader-convergence-forward-test.md) stays the real test.

## Data

**Wallets.** Today's tracked roster:
- 278 profitable traders (top 300 by monthly return that were also in profit before this month);
- 299 large accounts (top 300 by account value, profit not checked). These are the control group.

**Fills.** Per wallet, the latest 2,000 fills (same-time fills merged) plus the latest 2,000 timed-order slices. Each fill carries the position size before it.

**Opens.**
- A fresh open is a fill that takes a coin from flat to a position, or flips its side.
- It is timed at the fill, at the fill price.
- Only perpetual markets count; builder-dex and spot are excluded.

**Prices.** Hyperliquid 1-hour candles. The study window is the last 180 days up to 26 September 2026.

## Selection bias, handled before looking

The profitable traders are chosen for being profitable this month, so their recent trades look good by construction. To limit this:
- The headline numbers use only opens older than 30 days, outside the month that picked them.
- Everything is also reported for the large accounts, whose selection does not look at profit.
- Results on all opens are reported alongside, labelled as biased.

## Q1: lead or lag around spikes

**A spike (up).**
- It is the first hour at which a coin's close is at least 15% above its close 24 hours earlier, with no such hour in the previous 7 days.
- The move start is the lowest close in the 24 hours before that hour.
- Down spikes mirror this at −15%, and are paired with short opens.

**Measure.** For each spike, count fresh opens on that coin in the spike's direction, in 12-hour bins from 72 hours before the move start to 72 hours after the spike hour.

**Baseline.** The same coin's average opens per 12 hours, over hours more than 7 days from any spike.

**Report.** Per cohort:
- the ratio of opens to baseline, per bin;
- the share of spikes with at least one open in the 72 hours before the move start;
- the share with one only after the spike hour.

**Reading, fixed now.** If profitable traders' open rate before the move start is above 1.5 times baseline while the large accounts' is not, that is evidence they tend to come first. If the rise appears only after the spike hour, they follow.

## Q2: historical convergences

**Rule.** The forward test's rule, applied to the reconstructed opens:
- 2 or more profitable traders open the same side within 24 hours;
- the latest entry is within 5% of the first;
- at most 2 other profitable traders already hold that side, reconstructed from their fills.

**Report.**
- The directional return 1, 3 and 7 days after the second open, against single opens measured the same way.
- The share of convergences that happened before a spike, as defined in Q1, on that coin in that direction.

These are descriptive numbers. They do not replace the forward test's verdict, and no threshold is tuned on them.
