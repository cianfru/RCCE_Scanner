# Choosing the profitable traders: steady, risk-adjusted or dollar profit over 180 days (declared 15 November 2026, before running)

The owner's request (15 November 2026): "How can we improve the profitable traders cohort?", then "Sure go ahead" to a two-step plan.
- Step 1, this study: does any of three selection rules pick wallets that keep making money?
- Step 2, declared separately and only if a rule passes: does that cohort's positioning lead price?

Today's list is the top of Hyperliquid's leaderboard by return over the last 30 days. The selection window study (`selection-window-study.md`, 1 November 2026) found that this list, and lists ranked over 60 or 90 days, made money over the next 30 days about as often as every active wallet meeting the same rules (48.0% against 46.6%).

**Question:** does a rule built on profit over 180 days (in dollars, steady month after month, or measured against its worst drop) pick wallets that make money over the next 30 days more often than every wallet of the same age meeting the list's base rules? It must hold on two separate halves of the leaderboard, one of which no study has read.

This describes the past and runs outside the production server. Everything below is fixed before any outcome is computed. Unless a rule meets the bar on both halves, the result reads **context, not a signal**. Nothing in the app, the engine or the executor changes before then.

Code: `backend/backtest/cohort_selection_study.py`, tests in `backend/tests/test_cohort_selection_study.py`. Data, measures and base rules are imported unchanged from `backend/backtest/selection_window_study.py`.

## Known before running

**From the selection window study, on the read half only.** All of it was computed on the read half.
- Ranking by return over 30, 60 or 90 days did not beat everyone eligible.
- The 200 highest returns made money less often than the rest of their own pool: 48.0 against 51.9 (30 days).
- Wallets younger than the window made money less often: 33-40%, against about 49-51%.
- Which way a list leaned set most of each month's result. Today's list against everyone swung by about 15 points from month to month (standard deviation of the 12 differences).
- Today's list replaced 85% of its wallets each month.

**Not computed on any data:**
- the three rules below;
- the 180-day window;
- the monthly blocks;
- the drawdown measure.

The age rule and the longer window are partly motivated by the read-half findings above. That is why the unread half is the confirmation.

**Counts only (no outcome), read half:** wallets meeting each rule's pool conditions at each date.

| Date | Everyone eligible | 180+ days old (comparison) | Dollars | Steady | Risk |
|---|---|---|---|---|---|
| 2026-10-01 | 3,274 | 2,450 | 878 | 415 | 877 |
| 2026-09-01 | 3,207 | 2,361 | 828 | 332 | 828 |
| 2026-08-02 | 2,845 | 2,001 | 670 | 158 | 670 |
| 2026-07-03 | 2,836 | 1,980 | 705 | 277 | 705 |
| 2026-06-03 | 2,987 | 2,182 | 749 | 137 | 748 |
| 2026-05-04 | 3,031 | 2,185 | 446 | 115 | 445 |
| 2026-04-04 | 3,000 | 2,080 | 413 | 127 | 412 |
| 2026-03-05 | 2,866 | 1,958 | 372 | 107 | 371 |
| 2026-02-03 | 2,963 | 2,063 | 446 | 99 | 445 |
| 2026-01-04 | 2,683 | 1,787 | 390 | 102 | 390 |
| 2025-12-05 | 2,905 | 1,919 | 571 | 168 | 570 |
| 2025-11-05 | 3,119 | 1,959 | 779 | 367 | 779 |

The steady pool is under 200 on 8 of the 12 dates. On those dates its list is the whole pool.

## Data

**Leaderboard snapshot.** Same as the selection window study: 31 October 2026, 48,238 rows, SHA-256 `31abadebc58cb61e7956e6be694b9425faac2ac612dc370c1bacd5d594871b1e`. The market-maker flag and the $10M volume flag come from it, for both halves.

**Two halves, split by the same address hash** (`skey`, the first 8 hex digits of the address's SHA-256, modulo 10,000):
- **Read half** (`skey` under 5,000): 24,075 wallets, read on 31 October and 1 November 2026 for the selection window study, and read again for this study right after the unread half (see Changes: the stability check).
- **Unread half** (`skey` 5,000 or more): the other 24,163 rows, read for this study from 15 November 2026. They are read the same way: the whole Hyperliquid `portfolio` reply is kept, and a wallet still unreadable after three fetch runs is left out and counted.

**The halves are read two weeks apart.** A stored reply has weekly points (Wednesdays) up to about 31 days before it was fetched and near-daily points after.
- For the read half, near-daily points run from about 29 September 2026.
- For the unread half, they run from about 15 October 2026. So around the 1 October date the unread half reads weekly points: the activity rule spans a week instead of a day for some wallets, and the 1 October outcome's deposit base reads fewer points.
- Each rule is compared with its comparison group within the same half, from the same replies, so this cannot favour a rule within a half. It can make the halves' numbers differ slightly.

**Stability check**, before any result:
- 200 wallets of the read half (lowest `skey`, then address) are read again.
- Their all-time and perps-only account value and PnL points **before 29 September 2026** must be identical to the stored ones. **If more than 5% of the 200 differ there, the run stops** and this is reported before anything else.
- Points from 29 September to 31 October are compared and counted, and so are wallets whose readings change (base rules, age, each rule's rank key; no outcome). These are reported, separately for the wallets eligible on some date.

**Code check**, before any result:
- Today's list (top 200 by 30-day ROI) and everyone eligible are computed on the read half and must reproduce the selection window study's published hit rates exactly, to one decimal.
- Both were published, so nothing new is seen. The analysis refuses to run until this matches, the stability check has passed and the snapshot's SHA-256 is the declared one.
- If the check fails, the run stops, the code is fixed, and the fix is listed under Deviations.

**BTC.**
- Hyperliquid's BTC daily opens give, for each date, whether BTC rose over the next 30 days, as in the selection window study.
- BTC 4h closes from May 2025 to October 2026 are used for the exposure context below.

**As of, never interpolated.** A value at a time is the wallet's last point at or before it. Nothing after a date enters that date's selection.

## Definitions

- **Dates:** 1 October 2026 and every 30 days before it, 12 dates back to 5 November 2025. The outcome is the 30 days after each date. These are the selection window study's dates.
- **Base rules at t,** applied to every list and to the comparison group (as `selection_window_study.eligible_base`):
  - account value $10K+;
  - perps account $5K+;
  - perps PnL moved between the last two perps points (an active trader);
  - not a market maker.
- **Everyone eligible:** all wallets of the half meeting the base rules at t (context).
- **The comparison group:** everyone eligible whose first point is at least 180 days before t. Every candidate is at least that old, and younger wallets made money less often, so comparing with everyone would credit the age rule to the ranking.
- **Shared rules of the three candidates**, all at t:
  - the base rules;
  - the wallet's first point is at least 180 days before t;
  - PnL over the 180 days before t is $10K+;
  - all-time PnL at t is at least that 180-day PnL (not down before it).

  PnL, ROI and the ROI base over 180 days are measured as in the selection window study: deposits enlarge the base, withdrawals never shrink it.
- **Month blocks:** block i runs from t - 30(i+1) days to t - 30i days. Its PnL is the change in all-time PnL between those two times. A block that starts before the wallet's first point does not count. A block is profitable at +$100 or more.
- **The three candidates.** Each list is the top 200 of the half by its rank key, ties by address, or the whole pool when it is smaller.
  - **Dollars:** ranked by PnL over the 180 days, in dollars.
  - **Steady:** profitable in at least 5 of the last 6 blocks. Ranked by the number of profitable blocks among the last 12, then by 180-day PnL in dollars.
  - **Risk:** ranked by the 180-day ROI divided by the worst drop over the 180 days. The worst drop is the largest fall of cumulative PnL from a running peak, read at t - 180 days and at every point up to t, as a share of the ROI base, floored at 5%. A wallet with no ROI (a base under $1K) cannot be ranked and is left out.
- **Outcome:** each wallet's PnL over the 30 days after t, measured as in the selection window study. A **hit** is +$100 or more. The mean ROI is clipped to plus or minus 100% per wallet.

## The bar (fixed now)

For a candidate on one half, the per-date difference is its hit rate minus the comparison group's hit rate, in points.

The candidate meets the bar on that half only if all of these hold:
1. the mean difference over the 12 dates is **+5 points or more**;
2. the difference is above 0 on **at least 9 of the 12 dates**;
3. an **exact sign-flip test** of the mean (all 4,096 sign patterns, one-sided) gives **p of 0.01 or less**;
4. averaged over the dates, **both of these are above 0**:
   - its mean clipped ROI over the next 30 days minus the comparison group's (it made money per dollar, not just more often);
   - its hit rate among wallets that traded (PnL of +$100 or more, or -$100 or less) minus the comparison group's (bigger, busier accounts sit in the $0-100 band less often, which alone raises a hit rate);
5. the mean difference is **above 0 both over the dates BTC rose and over those it fell** over the next 30 days.

A candidate **passes only if it meets the bar on both halves.** If more than one passes, the one with the highest mean difference on the unread half is chosen. A rule whose list is empty on any date, or a half without the BTC record, gets no verdict (not met).

**What the bar can see.** Simulated on conditions 1-3 for one half: 12 dates, per-date differences normally distributed, 4,000 draws each.

| True difference | Spread 5 points | Spread 10 points | Spread 15 points |
|---|---|---|---|
| 0 | 0% | 1% | 1% |
| +5 | 50% | 19% | 9% |
| +8 | 98% | 53% | 22% |
| +10 | 100% | 74% | 37% |
| +12 | 100% | 90% | 51% |
| +15 | 100% | 98% | 74% |

- The table is for one half. Both halves share the same months, so their results are correlated. With a 15-point spread of which months make up 50-80%, a true +12 passes both halves 35-42% of the time and +15 about 60-65%; conditions 4 and 5 lower that further.
- With today's list's month-to-month spread (about 15 points), only a rule clearly better than the comparison passes. A fail reads "not shown": differences under about 10 to 15 points are not excluded.
- The unread half guards against chance among wallets, not among months: both halves cover the same 12 months, whose hit rates and BTC directions are already published.

## Also reported (context, no verdict)

Per date, half and list:
- hit rate;
- hit rate among wallets that traded;
- median ROI;
- mean clipped ROI;
- capital-weighted return (summed PnL over summed base);
- the share that stopped trading.

Also reported:
- **Today's list** (top 200 by 30-day ROI, the selection window study's 30-day arm) and **everyone eligible**, against the comparison group.
- Pool and list sizes, and each list's overlap with today's list.
- **Turnover:** the share of each list replaced 30 days later.
- **Exposure to BTC.** Each wallet's PnL changes between consecutive points over the 180 days before t, correlated with BTC's return over the same spans (4h closes; 8+ pairs needed). Wallets are grouped as:
  - with BTC (above +0.2);
  - against BTC (under -0.2);
  - little exposure (between);
  - unknown.

  Steady profit can come from funding collection or hedged books, which are not directional views. Step 2 must leave those out using the wallets' actual positions.

## What follows

**A rule passes:**
- Step 2 is declared before any of it is computed: does that cohort's net positioning, by coin and for the market, lead price, against everyone's and today's list's? Step 2 leaves out non-directional books (funding collection, hedges) using the wallets' actual positions.
- If the passing list is mostly "little exposure" to BTC, the result reads "keeps making money, mostly not by direction", and step 2 says whether anything directional is left.
- The Traders tab's list switches to the rule only after step 2, and after a cost check: the rule needs each eligible wallet's 180-day history, a `portfolio` read each, refreshed weekly.
- Nothing in the signals, the scanner or the executor uses the cohort before step 2 passes.

**None passes:**
- On Hyperliquid's leaderboard, past profit did not pick wallets that kept making money more often than the crowd. This covers 30-, 60- and 90-day returns (read half) and these three 180-day rules (both halves).
- The profitable list stays a viewing tool in the Traders tab, and no further selection studies are planned.

## Limits

- **Same months.** The halves are split by wallet, not by time: both cover the same 12 months, which mostly fell (BTC fell over 8 of the 12 outcome months).
- **Survivorship.** The snapshot lists wallets with $10M+ of volume or a $100K+ account on 31 October 2026. Wallets that lost or withdrew before then and traded under $10M are missing. Such survivors are a larger share of the comparison groups than of the lists (in the last study, 15% of everyone eligible against 9-10% of the lists), so this most likely lifts the comparison and works against a pass.
- **Market makers** are flagged from the snapshot, not as they stood at each date.
- **Weekly points.** History points are about a week apart, so blocks and windows start and end up to a week early, by the same rule for every list.
- **Profit is not positioning.** This step asks whether the wallets keep making money. Whether their positions lead price is step 2.
- **Three rules, two halves.** The bar asks every condition on both halves. The p threshold (0.01) allows for three candidates.

## Changes before the first result

- 15 November 2026: the declaration and code were committed (6f951c4) with only the pool counts computed.
- The same day, an independent review of the declaration, the code and the tests, with no outcome read, found nine issues. The changes below were made before any outcome was computed:
  1. The comparison group is everyone eligible of 180+ days, not everyone eligible, so the age rule cannot pass for the ranking.
  2. Condition 4 also requires a higher hit rate among wallets that traded, so bigger, busier accounts do not pass by sitting in the $0-100 band less often.
  3. The stability check requires identity only before 29 September (the weekly grid). It counts later points and changed readings, and covers the perps series. The halves' October grid difference is stated above.
  4. A code check reproduces the published hit rates before the analysis can run. The analysis also checks the stability result and the snapshot's SHA-256.
  5. The Traders tab waits for step 2. A passing list that is mostly "little exposure" is read as such.
  6. Two-half power and the shared months are stated.
  7. Survivorship's likely direction is stated.
  8. The stability re-read only keeps valid replies.
  9. The exposure context uses BTC 4h closes.
- The review confirmed no look-ahead in eligibility, age, blocks, the 180-day window, drawdown, ranking, today's list or exposure.
- **15 November 2026, the stability check (no outcome read).**
  - Result: 22 of the 200 re-read wallets (11%) differ before 29 September, over the 5% limit, so the run stopped as declared.
  - What differs is points only. In all 22, older points were dropped: 94-95 points became 56-79. Each wallet's all-time history keeps a limited number of points, spaced more widely as the account ages. In 11 of them, a few points also sit on other weeks. No value at a time present in both replies changed.
  - Readings changed for 8 of the 200, and for 8 of the 64 eligible on some date. Readings here means the base rules, the age rule and each rule's rank key; no outcome is read.
  - Spacing already differed between wallets: in the study's months, about 7 days for some wallets and 14 for others. That applies to every list and the comparison alike within a half.
  - **Change:** the read half is read again on the same days as the unread half (`reread`). The analysis uses those replies for both halves, so both come from the same thinning. The stored replies serve only for the code check.
  - The re-read meets the stop rule's purpose (both halves read the same way), so the analysis no longer waits on its 5% limit. The stability numbers are reported with the results.

## Results

Not yet computed.
