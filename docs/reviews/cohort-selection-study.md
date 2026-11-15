# Choosing the profitable traders: steady, risk-adjusted or dollar profit over 180 days (declared 15 November 2026, before running)

The owner's request (15 November 2026): "How can we improve the profitable traders cohort?", then "Sure go ahead" to a two-step plan.
- Step 1, this study: does any of three selection rules pick wallets that keep making money?
- Step 2, declared separately and only if a rule passes: does that cohort's positioning lead price?

Today's list is the top of Hyperliquid's leaderboard by return over the last 30 days. The selection window study (`selection-window-study.md`, 1 November 2026) found that this list, and lists ranked over 60 or 90 days, made money over the next 30 days about as often as every active wallet meeting the same rules (48.0% against 46.6%).

**Question:** does a rule built on profit over 180 days (in dollars, steady month after month, or measured against its worst drop) pick wallets that make money over the next 30 days more often than every wallet meeting the list's base rules? It must hold on two separate halves of the leaderboard, one of which no study has read.

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

| Date | Everyone eligible | 180+ days old | Dollars | Steady | Risk |
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
- **Read half** (`skey` under 5,000): 24,075 wallets, read on 31 October and 1 November 2026 for the selection window study.
- **Unread half** (`skey` 5,000 or more): the other 24,163 rows, read for this study from 15 November 2026. They are read the same way: the whole Hyperliquid `portfolio` reply is kept, and a wallet still unreadable after three fetch runs is left out and counted.

**Stability check.** The two halves are read two weeks apart.
- Before any result, 200 wallets of the read half (lowest `skey`, then address) are read again.
- Their all-time account value and PnL points before 31 October 2026 are compared with the stored ones.
- The share that differs is reported next to the verdict.
- Each rule is compared with everyone eligible within the same half, from the same replies, so a difference between the halves' sampling cannot favour a rule within a half.

**BTC.**
- Hyperliquid's BTC daily opens give, for each date, whether BTC rose over the next 30 days, as in the selection window study.
- Daily closes from May 2025 to October 2026 are used for the exposure context below.

**As of, never interpolated.** A value at a time is the wallet's last point at or before it. Nothing after a date enters that date's selection.

## Definitions

- **Dates:** 1 October 2026 and every 30 days before it, 12 dates back to 5 November 2025. The outcome is the 30 days after each date. These are the selection window study's dates.
- **Base rules at t,** applied to every list and to the comparison group (as `selection_window_study.eligible_base`):
  - account value $10K+;
  - perps account $5K+;
  - perps PnL moved between the last two perps points (an active trader);
  - not a market maker.
- **Everyone eligible:** all wallets of the half meeting the base rules at t. This is the comparison.
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
  - **Risk:** ranked by the 180-day ROI divided by the worst drop over the 180 days. The worst drop is the largest fall of cumulative PnL from a running peak, read at t - 180 days and at every point up to t, as a share of the ROI base, floored at 5%.
- **Outcome:** each wallet's PnL over the 30 days after t, measured as in the selection window study. A **hit** is +$100 or more. The mean ROI is clipped to plus or minus 100% per wallet.

## The bar (fixed now)

For a candidate on one half, the per-date difference is its hit rate minus everyone eligible's hit rate, in points.

The candidate meets the bar on that half only if all of these hold:
1. the mean difference over the 12 dates is **+5 points or more**;
2. the difference is above 0 on **at least 9 of the 12 dates**;
3. an **exact sign-flip test** of the mean (all 4,096 sign patterns, one-sided) gives **p of 0.01 or less**;
4. its mean clipped ROI over the next 30 days, minus everyone eligible's, averaged over the dates, is **above 0** (it made money per dollar, not just more often);
5. the mean difference is **above 0 both over the dates BTC rose and over those it fell** over the next 30 days.

A candidate **passes only if it meets the bar on both halves.** If more than one passes, the one with the highest mean difference on the unread half is chosen.

**What the bar can see.** Simulated on conditions 1-3 for one half: 12 dates, per-date differences normally distributed, 4,000 draws each.

| True difference | Spread 5 points | Spread 10 points | Spread 15 points |
|---|---|---|---|
| 0 | 0% | 1% | 1% |
| +5 | 50% | 19% | 9% |
| +8 | 98% | 53% | 22% |
| +10 | 100% | 74% | 37% |
| +12 | 100% | 90% | 51% |
| +15 | 100% | 98% | 74% |

- Both halves share the same months, so a real effect tends to show on both.
- With today's list's month-to-month spread (about 15 points), only a rule about 12 points better than everyone passes half the time.
- A fail reads "not shown". Differences under about 8 to 12 points are not excluded.

## Also reported (context, no verdict)

Per date, half and list:
- hit rate;
- hit rate among wallets that traded;
- median ROI;
- mean clipped ROI;
- capital-weighted return (summed PnL over summed base);
- the share that stopped trading.

Also reported:
- **Today's list** (top 200 by 30-day ROI, the selection window study's 30-day arm). On the read half it must reproduce that study's published hit rates. This checks the code.
- **Everyone 180+ days old:** the age rule alone, unranked.
- Pool and list sizes, and each list's overlap with today's list.
- **Turnover:** the share of each list replaced 30 days later.
- **Exposure to BTC.** Each wallet's PnL changes between consecutive points over the 180 days before t, correlated with BTC's return over the same spans (8+ pairs needed). Wallets are grouped as:
  - with BTC (above +0.2);
  - against BTC (under -0.2);
  - little exposure (between);
  - unknown.

  Steady profit can come from funding collection or hedged books, which are not directional views. Step 2 must leave those out using the wallets' actual positions.

## What follows

**A rule passes:**
- The Traders tab's profitable list switches to it, after a cost check. It needs each candidate wallet's 180-day history: a `portfolio` read per eligible wallet. The rule reads 180 days, so a weekly refresh is enough.
- Step 2 is declared before any of it is computed: does that cohort's net positioning, by coin and for the market, lead price, against everyone's and today's list's?
- Nothing in the signals, the scanner or the executor uses the cohort before step 2 passes.

**None passes:**
- On Hyperliquid's leaderboard, past profit did not pick wallets that kept making money more often than the crowd. This covers 30-, 60- and 90-day returns and these three 180-day rules, on two independent halves.
- The profitable list stays a viewing tool in the Traders tab, and no further selection studies are planned.

## Limits

- **Same months.** The halves are split by wallet, not by time: both cover the same 12 months, which mostly fell (BTC fell over 8 of the 12 outcome months).
- **Survivorship.** The snapshot lists wallets with $10M+ of volume or a $100K+ account on 31 October 2026. Wallets that lost or withdrew before then and traded under $10M are missing from both halves and from everyone eligible alike.
- **Market makers** are flagged from the snapshot, not as they stood at each date.
- **Weekly points.** History points are about a week apart, so blocks and windows start and end up to a week early, by the same rule for every list.
- **Profit is not positioning.** This step asks whether the wallets keep making money. Whether their positions lead price is step 2.
- **Three rules, two halves.** The bar asks every condition on both halves. The p threshold (0.01) allows for three candidates.

## Results

Not yet computed.
