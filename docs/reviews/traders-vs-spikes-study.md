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

## Results (run 26 September 2026)

**Data.**
- 577 wallets (278 profitable traders, 299 large accounts) and 17,320 fresh opens.
- 193 perpetual coins with hourly prices over the last 180 days. Outcome markets and spot pairs were dropped: they have no perpetual candles.
- Headline figures use spikes and opens older than 30 days: 469 up and 285 down spikes.

### Q1: before or after the spike?

Opens in the spike's direction, as a multiple of the coin's normal rate:

| | 72h before the move | During the move | 72h after the spike hour |
|---|---:|---:|---:|
| Profitable traders (older than 30 days) | **1.39×** | 4.29× | 4.31× |
| Profitable traders (all, biased) | 1.60× | 4.05× | 4.01× |
| Large accounts (older than 30 days) | 6.24× (one wallet) | 3.18× | 5.84× |

Profitable traders, 12-hour bins before the move: 1.2×, 1.3×, 1.3×, 1.5×, 1.7× and 1.3×. After the spike hour: 6.4×, 4.2×, 3.4×, 4.2×, 4.3× and 3.5×.

- Only 11% of spikes had any profitable trader open in their direction in the 72 hours before the move started.
- 14% had opens only after the spike.
- No single wallet accounts for more than a quarter of any bin's opens.

**Reading, against the rule fixed before looking.**
- The profitable traders' rate before the move (1.39×) is below the 1.5× line. Their opens concentrate during and after the move, at 4× the normal rate.
- **They mostly follow the spike.** A mild rise in the 36 hours before is there, but it is small and covers few spikes.
- The large-account control cannot be read. In the bins that stand out, one wallet makes 96-100% of the opens, a single account opening dozens of coins at once next to clustered market-wide spikes.
- On all opens, including the month that selected these wallets, the before-ratio is 1.60×. That is the selection bias the headline excludes.

### Q2: historical convergences

The forward test's rule on the reconstructed opens: 2 or more profitable traders on the same side within 24 hours, within 5% of each other's entry, at most 2 others already holding.

| Older than 30 days | Events | 1 day | 3 days | 7 days |
|---|---:|---|---|---|
| Convergences | 109 | -0.05% (49% up) | **-0.82% (42% up)** | -1.91% (43% up) |
| Single opens | 4,008 | -0.08% (49% up) | -0.24% (48% up) | -0.09% (50% up) |

The values are the median return in the traders' direction, with the share positive in brackets.

- Only 4 of the 109 convergences came in the 72 hours before a spike on that coin.
- Only 1 involved 3 or more wallets.
- On all opens (biased), convergences again trail single opens: -0.32% against +0.34% at 3 days, and -1.97% against +0.97% at 7 days.

**Reading.**
- In the past, two profitable traders converging on a coin did not lead price. It did slightly worse than one trader opening alone.
- This is descriptive and does not replace the forward test's verdict. The forward test keeps running as declared.
- It does mean the convergence alert should be treated as information, not as a trade signal.

### What this says about the product

- The coin chart and the trader grid are the right tools for seeing who came in and when.
- The data says that, most of the time, these traders are reacting to the same move you see, not anticipating it.
- The minority who were in early (like 2Z's trader A on 19 September) are visible there, but being early is not a trait of the group.
