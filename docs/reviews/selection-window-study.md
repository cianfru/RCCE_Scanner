# Selection window study: 30, 60 or 90 days (declared 31 October 2026)

The profitable traders are chosen on Hyperliquid's leaderboard by their return over the last 30 days (rolling). The owner asked on 31 October 2026 whether a longer window picks better traders: "we can check the best way to track those winning wallets and winning traders with 30, 60, 90 days windows and see what the numbers give us."

**Declared before any result was computed.** These rules and the code (`backend/backtest/selection_window_study.py`, tests in `backend/tests/test_selection_window_study.py`) were committed before the wallets' histories were read. A window replaces 30 days only if it meets the bar below; otherwise the result is context, not a signal, and the list keeps its 30-day window.

## Question

With the list's other rules unchanged, does ranking by return over 60 or 90 days pick wallets that make money over the next 30 days more often than ranking over 30 days?

## Data

- **Wallets.** Today's leaderboard (`stats-data.hyperliquid.xyz/Mainnet/leaderboard`, read once at the start of the run), without market makers (monthly volume over 100x the account value, as the live list). The leaderboard keeps accounts that lost everything (3,935 of its 48,238 rows had $0 on 31 October 2026), so wallets that blew up after a date are in.
- **Sample.** A fixed hash of the address (the first 8 hex digits of its SHA-256, modulo 10,000, under 3,000) picks 30% of them. Reading every wallet would take about 15 hours of Hyperliquid's per-IP allowance; the sample about 4. The list size scales with it (below).
- **History.** Hyperliquid's `portfolio` for each sampled wallet: all-time account value and PnL (net of deposits and withdrawals), total and perps only. Points are about a week apart (two weeks in the oldest accounts' early history, daily or closer in young accounts and the last days); values between points are interpolated linearly, as the market history rebuild does (`docs/reviews/wallet-history.md`). Before a wallet's first point its account value and PnL are 0.
- **Not the leaderboard's own numbers.** The leaderboard's monthly PnL differs from the same span of the account history by a few percent for some wallets (it is taken at another moment and its spot treatment is not documented). Every window here is measured the same way, from the account history.

## Method

- **Dates.** 1 October 2026 00:00 UTC and every 30 days before it: 12 dates, back to 5 November 2025. The 30 days after each date are its outcome; they do not overlap.
- **Window measures** at date t over d days (d = 30, 60, 90): PnL = all-time PnL(t) - all-time PnL(t - d). Net deposits = change in account value - PnL. ROI = PnL / (account value at t - d + net deposits when positive). A deposit enlarges the base; a withdrawal does not shrink it. No ROI when that base is under $1,000 (as the live list, which drops ROIs from nearly empty starts).
- **The list's rules at t** (as `hl_intelligence.build_cohorts`, except the window): account value $10K+, perps equity $5K+, PnL over the window $10K+, all-time PnL at t at least the window's PnL; ranked by ROI over the window.
- **Arms.** For each window, the top K by ROI. K = 400 for the whole leaderboard (about today's 431), so **120 in the 30% sample**. Equal sizes make the windows comparable; today's minimum ROI (30%) is left out of the primary arms because a longer window passes far more wallets and the lists would differ in size.
- **Outcome** of each wallet: its PnL over the 30 days after t (the same account-history measure). A hit is a PnL above 0. A wallet that stopped trading counts with its PnL (0: not a hit); the share of such wallets (under $100 either way) is reported.

## The bar (declared)

For each date, the hit rate (share of the arm with a profit over the next 30 days) of the 60-day arm and of the 90-day arm minus that of the 30-day arm, in percentage points. A longer window meets the bar only if all three hold:

1. the mean difference over the 12 dates is **+3 points or more**;
2. the difference is above 0 on **at least 10 of the 12 dates** (one-sided sign test p = 0.019, under 0.025 for two comparisons);
3. a bootstrap of the 12 dates (10,000 resamples, seed 20261031) puts the **2.5th percentile** of the mean difference **above 0**.

If both meet it, the one with the larger mean difference. If neither, the list keeps 30 days, and the numbers below are context, not a signal.

## Also reported (context only, no verdict)

- Per date and arm: hit rate, median ROI over the next 30 days, capital-weighted return (summed PnL over summed base), share that stopped trading.
- **Everyone** eligible at t (account value $10K+, perps $5K+), unranked: whether any ranking beats the crowd.
- **Today's rules as they are** for each window: ROI 30%+, at most 600 (180 in the sample).
- **Other list sizes:** half and double K.
- **Fine points only:** the wallets whose every interpolation span at the five times used (t - 90, t - 60, t - 30, t, t + 30 days) is two days or less, ranked among themselves (K scaled to their number). This checks that weekly points do not handicap the 30-day window, which they blur most.
- **Turnover:** the share of each arm's list replaced 30 days later.

## Known limits

- **Wallets that left the leaderboard.** Accounts whose value fell under its threshold and that traded little are not in today's leaderboard, so not in the sample (every row has either $1M+ of all-time volume or a $10K+ account today). They affect all three windows; how much each, unknown.
- **Market makers** are flagged by today's monthly volume, not as they stood at each date.
- **Weekly points** blur each window's ends by up to a few days, the 30-day window the most. The fine-points check reports it; the bar uses all wallets.
- **One year, twelve dates.** The months are the market's, all sharing its moves; the bootstrap over dates is the honest count, and twelve is few.
- **Profit is not the signal.** The list is used for its positioning; a list that keeps making money is a list worth reading, but this does not test whether its long/short counts lead price.

## Results

Not computed yet.

## Deviations

None.
