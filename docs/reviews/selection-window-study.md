# Selection window study: 30, 60 or 90 days (declared 31 October 2026)

The profitable traders are chosen on Hyperliquid's leaderboard by their return over the last 30 days (rolling). The owner asked on 31 October 2026 whether a longer window picks better traders: "we can check the best way to track those winning wallets and winning traders with 30, 60, 90 days windows and see what the numbers give us."

**Declared before any result was computed.** These rules and the code (`backend/backtest/selection_window_study.py`, tests in `backend/tests/test_selection_window_study.py`) were committed before the wallets' histories were read; any later change is listed under Deviations with its reason and whether it came before or after the first result. A first draft was reviewed the same day by four independent critics (bias, statistics, code, Hyperliquid data), each finding checked by a verifier; the version below adopts their confirmed fixes, still before any history was read. A window replaces 30 days only if it meets the bar below; otherwise the result is context, not a signal, and the list keeps its 30-day window.

## Question

With the list's other rules unchanged, does ranking by return over 60 or 90 days pick wallets that make money over the next 30 days more often than ranking over 30 days?

## Data

- **Wallets.** One leaderboard snapshot (`stats-data.hyperliquid.xyz/Mainnet/leaderboard`, saved 31 October 2026 19:57 UTC): 48,238 rows, SHA-256 `31abadebc58cb61e7956e6be694b9425faac2ac612dc370c1bacd5d594871b1e`. A row is listed when it has $10M+ of all-time volume or a $100K+ account today; rows that lost everything stay listed if they traded $10M+.
- **Sample.** A fixed hash of the address (the first 8 hex digits of its SHA-256, modulo 10,000, under 5,000) picks half: 24,075 wallets, market makers included (they are set aside in the analysis, below). Reading every wallet would take about 15 hours of Hyperliquid's per-IP allowance; half takes about 7. A wallet still unreadable after three fetch runs is left out and counted.
- **History.** Each sampled wallet's Hyperliquid `portfolio` reply, kept whole: all-time account value and PnL (net of deposits and withdrawals), total and perps only. Points are about a week apart (up to two weeks in the oldest accounts, daily or closer in young accounts and the last days), at times of each wallet's own.
- **As of, never interpolated.** A value at a time is the wallet's last point at or before it (0 before its first point). Nothing after a date enters that date's selection, and a selection and its outcome never share a span between two points. Each window and outcome therefore starts and ends up to one point gap early, by the same rule in every arm.
- **Not the leaderboard's own numbers.** The leaderboard's monthly PnL is exactly 0 for 26,549 rows, so it is neither used nor compared. Every window here is measured the same way, from the account history, as the live list would see it if it ranked on that history.
- **BTC.** Hyperliquid's BTC daily candles: the open at each date and 30 days later, for the market check below.

## Method

- **Dates.** 1 October 2026 00:00 UTC and every 30 days before it: 12 dates, back to 5 November 2025. The 30 days after each date are its outcome; they do not overlap.
- **Window measures** at date t over d days (d = 30, 60, 90): PnL = all-time PnL as of t minus as of t - d. Base = account value as of t - d plus the largest cumulative net deposit (change in account value minus PnL since t - d) at any point in the window, when positive: deposits enlarge the base, withdrawals never shrink it, and money deposited and withdrawn again still counts. ROI = PnL / base; no ROI when the base is under $1,000 (the live list drops ROIs from nearly empty starts). A wallet younger than the window is measured from its first point.
- **The list's rules at t** (as `hl_intelligence.build_cohorts`, except the window): account value $10K+; perps account value $5K+ and perps PnL moved between the wallet's last two perps points (an active trader, not idle money); PnL over the window $10K+; all-time PnL at t at least the window's PnL; not a market maker; ranked by ROI over the window, ties by address.
- **Market makers**: monthly volume over 100x the account value, both from the snapshot, applied only to accounts of $10K+ today (952 in the sample). A trader drained in October has a tiny account and high October volume; the live rule's ratio would call it a market maker and drop it, though it could not be on the live list anyway.
- **Arms.** For each window, the top K by ROI. K = 400 for the whole leaderboard (about today's 431), so **200 in the half sample**. Equal sizes make the windows comparable: if a window's pool is short of K on some date, all three take the shortest pool's size that date. Today's minimum ROI (30%) is left out of the primary arms because a longer window passes far more wallets.
- **Outcome** of each wallet: its PnL over the 30 days after t, by the same measure. **A hit is a PnL of +$100 or more**; a wallet that stopped trading (under $100 either way) is never a hit, and that share is reported.

## The bar (declared)

For each date, the hit rate of the 60-day arm and of the 90-day arm minus that of the 30-day arm, in percentage points. A longer window meets the bar only if all of these hold:

1. the mean difference over the 12 dates is **+3 points or more**;
2. the difference is above 0 on **at least 10 of the 12 dates** (a tie is not above 0);
3. an **exact sign-flip test** of the mean (all 4,096 sign patterns on the 12 differences, one-sided) gives **p of 0.025 or less** (0.05 split over the two comparisons);
4. the same direction holds where it could fail for other reasons: the mean difference is above 0 both over the dates whose next 30 days BTC rose and over those it fell (when each side has 3 or more dates; otherwise reported only); above 0 among the wallets with $10M+ of all-time volume (the rows listed whatever happened to their account), ranked again with the same K; above 0 when selection and outcome use perps-only PnL and account value; and the arm's mean next-30-day ROI (each wallet clipped to +-100%) is not lower than the 30-day arm's on average.

If both longer windows meet the bar, 60 days, unless 90 days meets conditions 1-3 against 60 days. If neither meets it, the list keeps 30 days, and the numbers are context, not a signal.

**What the bar can see.** Simulated on conditions 1-3 with K = 200, half of each arm shared with the 30-day arm and a 50% hit rate (a per-date spread of 3.5 points), adding 0, 3 or 5 points of month-to-month spread: a true +3 passes 39%, 28% or 18% of the time; +5 93%, 76% or 56%; +8 100%, 100% or 90%; no difference about 0-1%. +3 is the minimum that counts, not one the bar reliably detects. A fail reads "not shown"; differences under about +5 to +8 points are not excluded.

## Also reported (context only, no verdict)

- Per date and arm: hit rate, hit rate among wallets that traded, median ROI over the next 30 days, mean clipped ROI, capital-weighted return (summed PnL over summed base), share that stopped trading, share with under $10M of volume, share of sub-account rows, pool sizes, the median age of each arm's last point at t.
- **Everyone** eligible at t (the list's rules without a window), unranked: whether any ranking beats the crowd.
- **Today's rules as they are** for each window: ROI 30%+, at most 600 (300 in the sample).
- **Other list sizes:** half and double K. **Market makers kept**, **no activity rule**, **sub-account rows left out** (rows whose portfolio volume is under 90% of the leaderboard's, or with no portfolio volume this month against leaderboard volume: the leaderboard adds sub-accounts the portfolio does not cover; they are measured on the master account's own history, which is what the app follows).
- **By point age at t** (2 days or less, 2 to 7, over 7): each group ranked among itself, K scaled to its share of the eligible wallets. This shows whether wallets with stale points behave differently.
- **Turnover:** the share of each arm's list replaced 30 days later. The lag-1 autocorrelation of the per-date differences.
- **90 against 60** per date.

## Known limits

- **Wallets that left the leaderboard.** A wallet under $10M of volume whose account later fell under $100K is not in today's leaderboard, so not in the sample; such wallets are mostly ones that lost or withdrew. About a fifth of the sample (4,907 rows) is under $10M of volume. The $10M+ check in the bar is the guard; the share of such picks per arm is reported.
- **Market makers** are flagged from today's snapshot, not as they stood at each date.
- **Weekly points** shift each window's ends back by up to a week, by the same rule in every arm, and move a 30-day window's length most in relative terms.
- **Twelve dates, one market.** The months share the market's moves and are assumed independent; a lag-1 autocorrelation of 0.3 to 0.5 would raise the false-positive rate of conditions 1-3 from about 1% to 3-6%. The BTC check guards against one window simply suiting a rising or a falling year.
- **Profit is not the signal.** The list is used for its positioning; a list that keeps making money is a list worth reading, but this does not test whether its long/short counts lead price.
- **The live list's perps reading** (clearinghouseState on the main dex) cannot be reproduced for past dates; the perps account value in the history is the proxy, with the activity rule.

## Results

Not computed yet.

## Deviations

None.
