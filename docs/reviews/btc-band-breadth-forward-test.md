# Forward test: BTC below its weekly band while alt breadth is high (declared 26 September 2026)

## Origin (exploratory, not a result)

While reading the market history (docs/reviews/market-breadth-study.md), one combination looked bad for alts: BTC closes below its weekly bull market support band while 55% or more of coins are still in Uptrend. The share of coins in Uptrend reacts late and BTC's band breaks first (for example, December 2021 to January 2022). It was found by looking at the same data (windows 1-9), so it is a hypothesis. It is not a finding.

Scored episodes up to 2026-03-29 under the rule below (9):

| Start | Days | Uptrend share | BTC 30d | Typical alt 30d | Typical alt 60d |
|---|---:|---:|---:|---:|---:|
| 2021-12-04 | 13 | 77% | -6% | -4% | -35% |
| 2021-12-23 | 11 | 60% | -31% | -40% | -44% |
| 2022-01-17 | 8 | 56% | +4% | -20% | -29% |
| 2022-04-06 | 15 | 64% | -17% | -28% | -55% |
| 2022-07-20 | 143 | 68% | -10% | -4% | -14% |
| 2024-10-02 | 1 | 83% | +15% | +1% | +70% |
| 2024-10-09 | 2 | 83% | +26% | +10% | +100% |
| 2025-09-25 | 3 | 89% | +2% | -20% | -40% |
| 2025-10-11 | 1 | 86% | -4% | -1% | -27% |

An ordinary period (all days since May 2021) gives a typical alt of -7.4% over 30 days and -13.1% over 60 days (medians). Against that:

- over 30 days, 4 of 9 episodes were worse (median -4%);
- over 60 days, 7 of 9 were worse (median -29%).

Five of the nine come from the 2022 bear market. Both exceptions are October 2024, when BTC dipped just under its band and then rallied. The episode starting 2026-03-20 has no outcome inside the study window.

## Rule (fixed now)

- **Uptrend share:** the market history series (same 151 coins, Binance daily closes, the scanner's engine; days with 40+ coins). For this test it counts Uptrend and Overheated together. That is identical to the history above, where Overheated never fired, and it keeps the rule unchanged by the Overheated fix (docs/reviews/overheated-regime.md).
- **BTC band:** from BTC's daily closes, weekly closes on Sundays; 20-week SMA and 21-week EMA of completed weeks; the band's lower edge is the smaller of the two.
- **An episode day:** BTC's daily close is below the lower edge and the Uptrend share is 55% or more. Days with gaps of up to 5 days join one episode, and the outcome is measured from its first day.
- **Outcomes:** BTC and the typical alt (median simple return of the coins other than BTC, at least 20 coins) over 30 and 60 days, from the close of the first day.
- **Which episodes count:** only those that start after 26 September 2026. The historical table above never counts, and neither does data after 2026-03-29 that has already been seen.

## Decision rule (fixed now)

- The primary measure is the typical alt over 60 days against the ordinary -13.1%.
- No verdict is given before 6 new scored episodes.
- After that: "holds" if at least 75% of them are worse than ordinary over 60 days, "fails" if 50% or fewer are, otherwise "undecided". The 30-day figures are reported but do not decide.
- Until then the scanner shows the episodes and their outcomes as they complete, with no forecast.
