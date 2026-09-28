# Past paths on the market history chart: method (declared 28 September 2026, before the calibration was run)

## What this is

The market history drawer draws, on the chart itself, what the Uptrend share, BTC and the typical alt did in the 60 days after past days that looked like today. It is a record of what followed, shown for reference.

- It is not a forecast and not a trading signal.
- It does not count toward any forward test, including docs/reviews/btc-band-breadth-forward-test.md.
- This file fixes every rule before the official walk-forward check runs. No rule or threshold changes after that run: whatever it gives is what ships.

## Data

- **Uptrend share:** `share = uptrend + overheated`, the share behind the 55% risk-on line (days with 40 or more coins, from 1 May 2021; see docs/reviews/market-breadth-study.md).
- **BTC:** BTC's daily close.
- **Typical alt:** median simple return of every coin except BTC with a close on both days. At least 20 coins, otherwise missing.
- **BTC band:** the weekly bull market support band on Sunday closes, as declared in the forward-test doc.
- **Period:** all history, including days after 29 March 2026. The owner approved using that data for descriptive market context; the risk-on cycles study already used it once as an out-of-sample check.
- Only aggregates (typical-alt paths, the ordinary path, the check counts) go into the committed seed. Per-coin closes stay in the local cache.

## Which past days match today

**Run state at close (point in time).** Walk the days in order. The state is `on` from the first day with share of 55% or more, and turns `off` on the 5th day in a row below 55%. The run id changes at every flip, so dip days 1 to 4 still count as `on`. Hindsight labels are not used.

**A candidate day d for today T** is in the history (40+ coins, from 1 May 2021), has its 60 days closed (`d + 60 <= cutoff`, cutoff = T), has the same run state as T, and belongs to a different run (T's own run is left out).

**Ladder.** The first step whose matches come from 6 or more distinct runs wins.

| Step | Uptrend share within | BTC side of the band |
|---|---|---|
| 0 | 5 points of today | same as today (on or above the lower edge = holding; under it = below); days without a band do not match |
| 1 | 10 points | same as today |
| 2 | 10 points | either side |
| 3 | 15 points | either side |

If no step reaches 6 runs, step 3's set is used: 3 to 5 runs draw paths only; under 3 runs there is no fan ("Too few similar days").

## Episodes and weighting

- Matching days in date order join one episode when they are at most 6 days apart (gaps of up to 5 days) and share a run id.
- Each path starts on the episode's first day. Every episode weighs 1.

## Horizons and anchoring

- Knots every 5 days: 0, 5, 10, ... 60 (13 knots). +30 and +60 are marked.
- Each past path starts at today's value, for an origin t and a knot k:
  - Uptrend: `clip(share(T) + share(t+k) - share(t), 0, 1)`
  - BTC: `btc(T) * btc(t+k) / btc(t)`
  - Typical alt: `100 * alt_ret(t, t+k)`, % from today (0 at k = 0)
- A missing value is dropped at that knot only.

## Quantiles and minimum counts

- Levels 10, 25, 50, 75 and 90%, per knot, over the episodes with a value there.
- Hazen rule: sort the n values, place them at (i - 0.5)/n, interpolate linearly, clamp at the ends.
- A series gets a median and quantiles at a knot only if its values there come from 6 or more runs.
- **Ordinary line:** medians over all days of the study window (1 May 2021 to 29 Mar 2026), the same "ordinary" as the drawer. BTC: `btc(T) * (1 + ordinary %)`; typical alt: the ordinary % itself. Uptrend has no ordinary line.

## Walk-forward check

**Test units.** The first day T of every drawer episode (the six Uptrend bands, gaps of up to 5 days joined), with T on or after 1 May 2021 and T + 60 on or before the last cached close (25 Sep 2026). One test per episode.

**For each T.**
- Build the fan with the same code and `cutoff = T`: matches need `d + 60 <= T`, T's run at close is left out, same ladder and 6-run minimum.
- Skip T if there is no fan. A series and horizon without quantiles at that T (too few runs) is not scored there.
- For each series and h in {30, 60}, compare the actual value (anchored `share(T+h)`, `btc(T+h)`, `alt_ret(T, T+h)`) with the fan's quantiles at knot h:
  - middle half hit: `p25 <= y <= p75`
  - outer hit: `p10 <= y <= p90` (inclusive)
- Benchmark: the median of all earlier days (`d + 60 <= T`, T's run left out, each day weight 1), anchored the same way. Record the absolute error of both medians.

**Enough tests.** At least 30 tested episodes from at least 8 distinct runs. Otherwise every series is "untested".

**Pass, per series.** At both 30 and 60 days:
- the Wilson 90% interval (z = 1.645) of the middle-half hit rate contains 0.50, and
- the Wilson 90% interval of the outer hit rate contains 0.80.

`wilson(k, n) = (p + z²/2n ± z·sqrt(p(1-p)/n + z²/4n²)) / (1 + z²/n)`, with p = k/n.

**Display (the fallback).**

| Result | What the chart draws |
|---|---|
| Pass | Shaded middle half and 10-90 band, median, landing dots at +30 and +60 |
| Fail or untested | Every episode's path, plus median and dots; no shading. The readout shows lowest-highest instead of the middle half |
| 3-5 runs | Paths and dots only; no median, no bands |

**Median against all days.** `median_vs_all` = mean over the 6 series x horizon pairs of (fan median error / all-days median error). Under 0.9: "closer than"; 0.9 to 1.1: "about as close as"; over 1.1: "further off than".

## What was seen before this declaration

While designing, two proposals ran walk-forward checks on this same history. Those numbers were seen before these rules were fixed and count as exploration only. Recorded so nobody tunes afterwards:

- 52 of 118 episodes tested, 12 runs: the typical alt passed; BTC missed on the 30-day outer band (60% held); Uptrend missed on the 30-day middle half (37%); `median_vs_all` about 1.2.
- The first-day origin was chosen over a smoothed (kernel) origin partly on these numbers (Uptrend 30-day outer band 75% vs 65%).
- Today's fan (12 episodes from 8 runs, at step 0) was also seen.

## Clean check from this date

- From this file's commit date, the daily update logs the fan on the first day of each new drawer episode: `[day, {series: {30: [p10, p25, p50, p75, p90], 60: [...]}}]`, anchored numbers, null where there is no band.
- Entries are scored only after their 60 days close. The drawer adds one line about it once 12 or more are scored, and nothing before.
- This checks the drawing only. It is not a trading test.

## Caveats

- Today's coin list: coins that died are missing (survivorship), so past alts look better than they were.
- About 40 coins in May 2021 against about 145 now.
- A rebuilt universe, not the live scanner's; Binance spot closes, not Hyperliquid perps.
- About 12 ended runs in the whole history, and episodes inside one run are not independent.

## Official run

Run once on 28 September 2026, after this file was committed (declaration commit 508702f), with `python -m backtest.breadth_history export` (it calls `backtest.market_paths.calibrate`; `python -m backtest.market_paths calibrate --dry` prints the same table). Cache: the local rebuild, 151 coins, last close 25 Sep 2026 (day 20721). The typical alt's past paths come from the seed's `alt_paths` (whole %) for origins up to 29 Jan 2026 and from per-coin closes after, as in production.

```
fan_check through 20721: 82 of 118 episodes with a fan (16 runs), 52 scored with quantiles (12 runs), untested=False, median_vs_all=1.13
series   h   middle half (hits/n, Wilson 90%)     10-90 (hits/n, Wilson 90%)      MAE fan / all   pass
uptrend   30   18/52    35%  [0.25, 0.46]        39/52    75%  [0.64, 0.83]      0.2765 / 0.278   False
uptrend   60   22/52    42%  [0.32, 0.54]        37/52    71%  [0.60, 0.80]      0.3513 / 0.3532   False
btc       30   24/52    46%  [0.35, 0.57]        31/52    60%  [0.48, 0.70]      1.095e+04 / 9246   False
btc       60   23/52    44%  [0.33, 0.56]        39/52    75%  [0.64, 0.83]      1.788e+04 / 1.589e+04   False
alt       30   26/52    50%  [0.39, 0.61]        39/52    75%  [0.64, 0.83]      22.6 / 17.94   True
alt       60   22/52    42%  [0.32, 0.54]        40/52    77%  [0.66, 0.85]      31.29 / 26.14   True
```

(The pass column is per series: both horizons must hold. The Uptrend 60-day outer interval's upper end is 0.802, so it contains 0.80.)

**Per series and horizon**

| Series | 30 days: middle half / 10-90 | 60 days: middle half / 10-90 | Result |
|---|---|---|---|
| Uptrend share | 35% (fails: interval 0.25-0.46 misses 0.50) / 75% (holds) | 42% (holds) / 71% (holds) | Fail |
| BTC | 46% (holds) / 60% (fails: interval 0.48-0.70 misses 0.80) | 44% (holds) / 75% (holds) | Fail |
| Typical alt | 50% (holds) / 75% (holds) | 42% (holds) / 77% (holds) | Pass |

- Enough tests: 52 episodes scored with quantiles from 12 runs (82 had a fan, 30 of them from only 3-5 runs, which draw paths and are not scored). Both readings clear the 30-episode, 8-run bar.
- `median_vs_all` = 1.13: the matched median was **further off than** the median of all earlier days. The fan's median is a description of what followed similar days, not a better guess than an ordinary stretch.

**What the drawer shows as a result**

- Typical alt: shaded middle half and 10-90 band, median, landing dots.
- BTC and Uptrend share: every episode's path, median and landing dots, no shading; the readout shows lowest-highest instead of the middle half.
- These modes are in the payload (`fan.show`), taken from the seed's `fan_check`, so they change only if the seed is rebuilt.

**Today (27 Sep 2026, from the production days and closes)**: step 0 (within 5 points, BTC holding its band), 12 episodes from 8 runs.

| | +30 days: median (middle half) | +60 days: median (middle half) |
|---|---|---|
| Uptrend share | 72% (33-89%) | 45% (6-90%) |
| BTC | 84,836 (78,515-90,001) | 78,441 (67,572-109,775) |
| Typical alt | -7.5% (-24.5% to +5.0%) | -22.7% (-37.5% to +29.5%) |
| Ordinary stretch | BTC 84,725, alt -7.4% | BTC 85,486, alt -13.1% |

**Deviations**

- No rule or threshold changed. The counts above are what the first run gave.
- After the first run, two count fields were added to `fan_check` (`scored`, `scored_runs`) because "tested" can be read two ways (days with any fan, or days with quantiles). The export was re-run once to write them; every other number in the seed came out identical.
- Review fixes on 28 September 2026, after the official run. None changes a rule, a threshold or a number above; the export was re-run and wrote an identical `fan_check`.
  - **Enough tests.** The bar now counts the scored test episodes (with quantiles from 6+ runs: 52 from 12 runs), the ones the hit rates are made of, not every test day with a fan (82 from 16 runs). "Tested episodes" could be read either way; the stricter reading is used. Both clear the 30-episode, 8-run bar, so the result is the same.
  - **Clean check.** The code scored a logged fan's 30-day values before its 60 days had closed, against "Entries are scored only after their 60 days close" above. It now skips an entry until T + 60 has closed. The drawer's line about it pools only the series drawn with bands.
  - **Popover.** The fan's popover now states the median result (`median_vs_all`) whenever the check ran, not only when every series passed, and names the test's size as scored episodes and runs.
- The exploratory numbers seen before the declaration (52 of 118, 12 runs; alt passes, BTC 60% on the 30-day outer band, Uptrend 37% on the 30-day middle half, `median_vs_all` about 1.2) came out close to the official ones (Uptrend 35%, `median_vs_all` 1.13). Today's typical alt at +60 reads -22.7% against -22.6% seen earlier, because the seed stores past alt paths in whole percent.
