# The Uptrend share against its own weekly band (declared 6 November 2026, before running)

The owner's question (6 November 2026): "We have a bull market support band that is designed to be on the Bitcoin chart, but did we test it over the uptrend share instead to see if there is something there that we can extract?" It had not been tested. Today the band is drawn on BTC only.

This study builds the same band on the share of coins in uptrend and asks two things:

1. When the share crosses under its band (or back over it), what followed for BTC and the typical alt over 30 and 60 days, against ordinary days at the same share?
2. How do the crossings line up in time with the 55% rule's broad uptrend starts and ends: earlier or later, and by how many days?

This describes the past and runs outside the production server. Everything below is fixed before any outcome is computed. Only counts and a data check were looked at; both are quoted below. Unless a result clears its bar, it reads **context, not a signal**.

Code: `backend/research/uptrend_band.py` (tests `backend/tests/test_uptrend_band.py`), run from `backend/`:

- `python -m research.uptrend_band fetch --out CLOSES.json` (public daily candles, below)
- `python -m research.uptrend_band check --snapshot MH.json --closes CLOSES.json` (the data check)
- `python -m research.uptrend_band shape --snapshot MH.json` (counts only)
- `python -m research.uptrend_band power --n-under 10 --n-over 9` (the bar on simulated data)
- `python -m research.uptrend_band run --snapshot MH.json --closes CLOSES.json` (the study)

## Data

- **The market history.** A saved `/api/market-history` response from 6 November 2026, SHA-256 `6954f924cde373d2958c3f59e7578485be6ca9ed79fad2fe9b6420e433fa3e19`. 2,015 days, 2021-05-01 to 2026-11-05, every day with 40 or more coins, none missing. Like the other studies' inputs, it is not kept in the repository; the hash identifies it.
- **The share** = Uptrend + Overheated, as the page reads it. Overheated is 0 on every day.
- **BTC**: the daily close in the same file.
- **The typical alt**, as on the page and in the late-uptrends study: the median simple return of the coins other than BTC, with 20 or more coins having both closes.
  - For days to 2026-01-28: the seed's typical-alt paths (`backend/seeds/market_history_seed.json`, whole %, at 5-day steps to 60 days).
  - For later days, the earlier studies read the server's per-coin closes (`market_history_live.json`). This study makes no call to the server. It rebuilds those closes from Binance's public daily candles of the seed's 151 pairs, at the URL the server itself uses (`data-api.binance.vision`), one request per pair, one a second, fetched 6 November 2026. A coin counts on a day once it has 200 daily candles, the server's rule (`market_history.day_closes`).
- **The data check**, run before this declaration (`check`). The rebuilt typical alt against the snapshot's own numbers:
  1. its last 90 days against the last day (the page's `alt_recent`): every day within 0.5 points;
  2. every scored drawer episode starting from 2026-01-29, at 10, 30 and 60 days: every value within 1 point;
  3. the join: origins 2025-11-28 to 2026-01-28 at 30 and 60 days, against the seed's whole-% paths: a median difference of 0.5 points or less, and none over 1.5.

  If the check had failed, the typical alt after 2026-01-28 would have been left out. **It passed.** All 151 pairs answered. The 91 days of `alt_recent` and the 51 scored episode values match exactly (largest difference 0.0 points). The 124 values at the join differ by a median of 0.3 points and at most 0.5, the seed's rounding to whole %. The candles file used has SHA-256 `f03a57b3f260db6d7b7d858742ae380c46283d582eff12960abd36991caf3949`; like the snapshot, it is not kept in the repository.

## Known before running

- The share, BTC and the typical alt have been seen on the page and in the earlier studies: the broad uptrends and their dates (docs/reviews/risk-on-cycles-study.md, late-uptrends-study.md, turning-points-study.md), BTC's band breaks against breadth (the risk-on cycles study's 3b and 3c, docs/reviews/btc-band-breadth-forward-test.md), breadth topping early and rolling over late, and the typical coin turning before the share did.
- The band on the share has not been computed or drawn before: no code or document in the repository builds it.
- So the numbers below are description, checked against a declared bar. New crossings from 7 November 2026 are the only clean test.
- **Counts** (`shape`, no outcome):
  - The band exists from 2021-09-20 (the day after the 21st Sunday from 2 May 2021).
  - Under: 13 stretches, 13 crossings (9 on a day a broad uptrend was under way, 4 outside one), 11 events after the 30-day rule, 10 of them with 60 days after them.
  - Over: 11 stretches, one of them from the band's first days (start unknown), so 10 crossings (4 during a broad uptrend, 6 outside), 9 events, all 9 with 60 days after them.
  - 13 broad uptrends start after the band exists, from 2021-11-06 to 2026-08-20. All 13 have ended; the last ended on 2026-10-22.

## Definitions

- **The share's weekly band.** BTC's band from the app (`market_history.btc_band`; "BTC band" in the risk-on cycles study), fed with the share instead of BTC's close, by the same code (`backtest.risk_on_cycles.weekly_rows` and `expand_weekly`):
  - the share on each Sunday;
  - the 20-week SMA and the 21-week EMA of those Sunday values;
  - a Sunday's band is used from the next day (completed weeks only);
  - lower edge = the smaller of the two, upper edge = the larger.
  - Days before 1 May 2021 (fewer than 40 coins) are not used, so the first band is on 2021-09-20.
- **Side.** Under: the share below the lower edge. Over: above the upper edge. Inside: otherwise (an edge itself is inside).
- **Crossing under**: the first day of a stretch of days under the band. Days under with gaps of up to 5 days form one stretch, so a crossing has no day under in the 6 days before it. This is BTC's band break in the risk-on cycles study.
- **Crossing over**: the mirror, with days over the upper edge.
- Both are known on the day. A stretch that begins in the band's first 6 days has an unknown start and is not a crossing.
- **Broad uptrend**: the page's rule (frontend `broadRuns`, `research/late_uptrends.py`). It starts on the first day at 55% or more and ends when the share has been under 55% for 5 days in a row. Its end day is the first of those 5 days, known on the 5th (end + 4). Dips of 1 to 4 days stay inside. The run under way on 1 May 2021 has no known start and ended before the band exists, so it is left out.
- **Outcomes** from a day's close: BTC over 30 and 60 days, the typical alt over 30 and 60 days, and the share's change over 30 days (points). A window that runs past 2026-11-05 is not counted.

## Part A. Prices after a crossing

- **Events**: crossings with no crossing of the same kind (counted or not) in the 30 days before. Crossings within 30 days of an earlier one are listed, not counted.
- **Comparison days** for each event: days with a band, the share within 10 points of the event day's, the outcome known, and not a crossing of the same kind nor within 30 days after one.
- **Excess** = the event's outcome minus the median of its comparison days.
- **Declared side**: lower after crossing under (as BTC under its band reads as weakness), higher after crossing over.
- **Deciding**: the 60-day outcomes, for BTC and for the typical alt, for each kind: four rows. The 30-day outcomes and the share's 30-day change are reported with the same checks and never decide (edges 5 points for 30-day prices, 10 points for the share).

**The bar.** A row meets it only if all of these hold, on unrounded values:

1. at least 8 events with the outcome;
2. at least 75% of them on the declared side of their comparison median;
3. a median excess of 10 points or more on the declared side;
4. random draws: 10,000 draws, each taking one comparison day per event at random. The events' median outcome is beaten (at or beyond it, on the declared side) by no more than 5% of the draws' medians;
5. the median excess is on the declared side in both the first and the second half of the events by date (the first half is the first ⌊n/2⌋).

A row that meets it reads, for example, "after the share crossed under its band, the typical alt was lower over the next 60 days than on days at the same share, in k of n". Otherwise: context, not a signal. A result on the other side, however large, is reported only.

## Part B. Against the 55% rule

For each broad uptrend that starts after the band exists:

- **Its end** (end day E), the first case that applies:
  1. a stretch under the band contains E and began during the run: **band first**, lead = E minus the stretch's first day (0 = the same day, not first);
  2. that stretch began before the run's start: **under since before the run**;
  3. no stretch under contains E: the first crossing under within 60 days after E, **band later** (a negative lead);
  4. none: **none within 60 days**, or **not known yet** if E + 60 is past the data.

  Leads are also shown against E + 4, the day the 55% rule knows the end.
- **Its start** (start day S), the mirror with stretches over the band: **band first** when the stretch over that contains S began on or after the previous run's end; **over since before the dip** when it began earlier; then **band later** and **none within 60 days** as above.
- **False alarms.** Every crossing under on a day a broad uptrend was under way, by the rule's own state that day (its 1-4 dip days included): was the run's end day within 60 days? A crossing on a dip day comes after the end day the rule later names, and counts as followed by it. The mirror for starts: every crossing over on a day with no broad uptrend under way, and whether a run started within 60 days.
- **Reported, never deciding:** per run, BTC from the earlier signal to the later one; and BTC and the typical alt over 30 and 60 days from the band's crossing and from the 55% rule's day (E + 4 for ends, S for starts).

**The bar**, separately for ends and starts. "The share crossed under its band before the 55% rule's end" (or "over its band before the start") needs all of:

1. at least 8 runs with both signals (band first, same day or band later);
2. band first in at least 75% of them;
3. a median lead of 10 days or more, against the end (or start) day, later crossings counting as negative;
4. few false alarms: at least 75% of the crossings in the false-alarm count, where known, were followed by an end (or a start) within 60 days.

Otherwise: context, not a signal.

## Also reported (no verdict)

- Every crossing, with its share, its band, whether a broad uptrend was under way and whether it counts as an event.
- Every day with a band, by side (over, inside, under) and by whether a broad uptrend was under way: BTC and the typical alt over 30 and 60 days. The days overlap, so this is description.
- The last day: the share, its band, its side and the latest crossings.

## What the bar can see

- **Part A.** Simulated with `power` on made-up numbers: independent events, outcomes with a normal spread of 26 or 28 points (about the spread of 60-day BTC and typical-alt changes on all days, from the quartiles in the risk-on cycles study), 4,000 runs each, at this study's counts (10 events under, 9 over).
  - With no true gap, 1.5% to 2.0% of runs meet the bar.
  - A true gap of 10 points: 13% to 15%. 20 points: 44% to 51%. 30 points: 77% to 85%.
  - So the bar sees only a gap of about one typical spread, 25 to 30 points over 60 days. A smaller gap is not excluded: a fail reads "not shown".
  - There are four deciding rows. With no gap anywhere, the chance that at least one meets the bar is at most about 8%, and less since the rows move together.
  - Real events from the same cycle are not independent, so with no true gap a row meets the bar more often than simulated.
- **Part B.** There are at most 13 ends and 13 starts. With 12 runs with both, 75% means 9.
  - 9 crossings under came on a day a broad uptrend was under way. So the end bar needs nearly every one of them to come before its own run's end, and the false-alarm check needs 7 of those 9.
  - 6 crossings over came outside broad uptrends. So at most about 6 starts can show the band first (more only from crossings on a run's 1-4 dip days). With 8 runs with both, the start bar needs 6 of them.
  - Part of any lead is built in. The band is a 20-week average of the share. After a long broad uptrend it sits high, so the share falls under it before reaching 55%. After a short one it sits low, and the share falls under 55% first. Starts mirror this after long and short downturns. So the timing bar measures how regular this is, not whether prices followed; Part A asks that.

## Out of sample

From 7 November 2026, the same code on later saved responses, with `run --oos`. Crossings, starts and ends on or after that day count toward each bar, scored once their 60 days are over. At the in-sample pace (about two crossings of each kind a year), 8 new events take about four years.

## Limits

- About 10 events of each kind and 13 broad uptrends, over about two cycles plus 2026. Events in one cycle are not independent.
- The band is an average of the share itself, so the two are not independent readings, and part of any lead is mechanical (above).
- The band's first months, September to December 2021, still carry the EMA's start on 2 May 2021.
- A weekly band against a daily share: the share's day-to-day moves cross a slow band.
- Today's coin list: coins that died are missing, so the typical alt reads better than it was. Binance spot closes, not Hyperliquid perps. Fewer coins early on: 40 in May 2021, 145 now.
- The typical alt after 2026-01-28 is rebuilt from public candles (see the data check).
- The 2026-08-20 run's start rests on one coin (the risk-on cycles study): without it, that run would continue the one from 2026-03-20.

## Results

To be added below after the run. Nothing above changes. Any later change is listed under Deviations, with its reason and whether it came before or after the first result.

Computed once on 6 November 2026 by `run` at commit 3f38b06, the commit that holds this declaration. Inputs: the snapshot and the candles file named above (same SHA-256). The data check passed. Every number is in sample, so this is description against the declared bar.

**Verdict: no row meets its bar.** Not the prices after a crossing (four rows), and not the timing against the 55% rule (ends and starts). The numbers below are **context, not a signal**.

### Part A. Prices after a crossing

The deciding rows (60 days). "Excess" is the event's change minus the median of days at the same share.

| Bar | Under: typical alt | Under: BTC | Over: typical alt | Over: BTC | Needed |
|---|---|---|---|---|---|
| 1. Events | 10 | 10 | 9 | 9 | 8 or more |
| 2. On the declared side | 5 of 10 | 5 of 10 | 6 of 9 | 7 of 9 | 75% or more |
| 3. Median excess | -7.0 points | +9.8 points (the other side) | +22.0 points | +14.0 points | 10 or more, declared side |
| 4. Draws at or beyond | 20.1% | 83.5% | 12.1% | 16.9% | 5% or less |
| 5. Halves by date | +5.0 / -19.0 | +26.6 / -7.0 | +23.5 / +16.4 | +19.4 / +14.0 | both on the declared side |
| Events' median (median of their same-share medians) | -19.5% (-13.0%) | +10.4% (-0.2%) | +2.0% (-15.0%) | +11.4% (-2.1%) | |
| Verdict | not met | not met | not met | not met (only check 4 fails) | |

Reported with the same checks, never deciding:

| Reported | Events | Declared side | Median excess | Draws at or beyond | Halves |
|---|---:|---|---:|---:|---|
| Under: typical alt, 30 days | 10 | 7 of 10 | -14.2 | 6.1% | -8.0 / -20.5 |
| Under: BTC, 30 days | 10 | 6 of 10 | -2.0 | 36.7% | +0.3 / -3.2 |
| Under: the share's change, 30 days | 10 | 8 of 10 | -29.8 points | 0.6% | -23.6 / -49.5 |
| Over: typical alt, 30 days | 9 | 7 of 9 | +13.4 | 8.9% | +24.0 / +2.8 |
| Over: BTC, 30 days | 9 | 7 of 9 | +4.8 | 22.1% | +17.2 / +3.7 |
| Over: the share's change, 30 days | 9 | 7 of 9 | +15.0 points | 14.7% | +26.9 / +15.0 |

The events. Each change is followed by the median of its same-share days in brackets.

| Crossed under | Share (band) | Broad uptrend | BTC 60 days | Typical alt 60 days | Typical alt 30 days | Share, 30 days |
|---|---|---|---|---|---|---|
| 2022-01-11 | 44% (46-50%) | no | -9.2% (+8.6) | -34% (+6.0) | -19% (+5.0) | 0.0 (+35.9) |
| 2022-04-30 | 41% (44.5-45%) | no | -46.5% (+7.9) | -52% (+8.0) | -31% (+10.0) | -28.8 (+42.2) |
| 2022-11-20 | 75.8% (75.8-80.7%) | day 123 | +29.4% (-3.0) | +17% (-14.0) | -3% (-4.0) | -33.6 (-10.0) |
| 2023-02-25 | 70% (70-71%) | day 43 | +22.7% (-3.9) | -13% (-18.0) | -16% (-8.0) | -39.5 (-18.0) |
| 2023-09-04 | 12% (12-18.5%) | no | +34.4% (+2.3) | +21% (-12.0) | +1% (-7.0) | +15.8 (+5.8) |
| 2024-01-26 | 66% (69-70%) | day 96 | +67.3% (-2.8) | +57% (-16.0) | +18% (-9.3) | -16.2 (-15.4) |
| 2024-03-25 | 64.0% (64.0-74.8%) | day 28 | -1.9% (+5.1) | -26% (-7.0) | -29% (-5.6) | -56.0 (-3.1) |
| 2025-01-14 | 72% (73.5-75.6%) | day 111 | -12.7% (-5.5) | -50% (-17.0) | -33% (-6.6) | -61.7 (-12.2) |
| 2025-10-14 | 56% (77-78.5%) | day 95 | -20.2% (+7.0) | -37% (+1.2) | -22% (-1.5) | -44.4 (+11.2) |
| 2026-07-03 | 67% (67.6-70.8%) | day 105 | +23.7% (-3.9) | +1.0% (-18.0) | -11.2% (-9.0) | -10.9 (-17.3) |
| 2026-10-18 | 70% (72-74%) | day 59 | 60 days not over | | | |

Not counted (within 30 days of the crossing before): 2022-01-25 and 2023-09-14.

| Crossed over | Share (band) | Broad uptrend | BTC 60 days | Typical alt 60 days | Typical alt 30 days | Share, 30 days |
|---|---|---|---|---|---|---|
| 2022-03-30 | 52% (38-49%) | no | -37.4% (+11.7) | -61% (+11.0) | -32% (+10.5) | -5.4 (+18.5) |
| 2022-06-29 | 31% (28-30%) | no | -2.8% (-4.8) | +2% (-20.0) | +23% (-5.0) | +59.0 (-1.0) |
| 2023-01-18 | 78% (64-73%) | day 5 | +35.3% (-1.5) | +11% (-14.0) | +24% (-6.0) | -3.1 (-12.2) |
| 2023-09-24 | 18% (11-17%) | no | +42.1% (-2.1) | +40% (-15.0) | +11% (-9.0) | +48.1 (+3.3) |
| 2024-03-03 | 75% (60-74%) | day 6 | -6.4% (+4.1) | -28% (-13.0) | -7% (-8.0) | -28.0 (-12.9) |
| 2024-08-22 | 16% (8-16%) | no | +11.6% (-2.4) | +9% (-15.0) | +4% (-9.4) | +23.5 (+3.0) |
| 2025-05-13 | 39% (25-26%) | no | +12.8% (-1.8) | -20% (-15.0) | -25% (-3.0) | +9.5 (+1.3) |
| 2026-03-14 | 29% (15-24.5%) | no | +11.4% (-5.1) | +10.6% (-19.1) | -3.2% (-6.0) | +53.8 (-3.9) |
| 2026-08-27 | 79% (65-77%) | day 7 | -0.1% (-2.8) | +1.4% (-15.0) | +21.5% (-6.0) | +2.8 (-12.2) |

Not counted: 2026-09-24 (28 days after 2026-08-27). The share was over its band from the band's first day (2021-09-20) to 2022-01-24, so that stretch's start is unknown and it is no crossing.

### Part B. Against the 55% rule

Ends. Lead = days from the band's crossing under to the run's end day (negative: the band came later). The 55% rule knows the end 4 days after its end day. "BTC between" runs from the earlier signal to the later one (the rule's day here is end + 4).

| Broad uptrend | Days | Case | Crossed under | Lead: end day / known day | BTC between | Typical alt 30 days: from the band / from the rule |
|---|---:|---|---|---|---|---|
| 2021-11-06 to 2021-12-17 | 41 | band later | 2022-01-11 | -25 / -21 | rule first, -12.6% | -19% / -16% |
| 2021-12-23 to 2022-01-03 | 11 | band later | 2022-01-11 | -8 / -4 | rule first, +2.8% | -19% / -16% |
| 2022-01-17 to 2022-01-25 | 8 | same day | 2022-01-25 | 0 / 4 | band first, +3.3% | -8% / +1% |
| 2022-04-02 to 2022-04-21 | 19 | band later | 2022-04-30 | -9 / -5 | rule first, -6.9% | -31% / -49% |
| 2022-07-20 to 2022-12-10 | 143 | band first | 2022-11-20 | 20 / 24 | band first, +9.4% | -3% / +8% |
| 2023-01-13 to 2023-03-07 | 53 | band first | 2023-02-25 | 10 / 14 | band first, -11.7% | -16% / +23% |
| 2023-10-22 to 2024-01-31 | 101 | band first | 2024-01-26 | 5 / 9 | band first, +1.8% | +18% / +40% |
| 2024-02-26 to 2024-03-27 | 30 | band first | 2024-03-25 | 2 / 6 | band first, +2.0% | -29% / -36% |
| 2024-09-25 to 2025-01-22 | 119 | band first | 2025-01-14 | 8 / 12 | band first, +6.3% | -33% / -35% |
| 2025-05-15 to 2025-05-21 | 6 | none within 60 days | | | | |
| 2025-07-11 to 2025-10-15 | 96 | band first | 2025-10-14 | 1 / 5 | band first, -3.9% | -22% / -20% |
| 2026-03-20 to 2026-08-15 | 148 | band first | 2026-07-03 | 43 / 47 | band first, +10.8% | -11% / +22% |
| 2026-08-20 to 2026-10-22 | 63 | band first | 2026-10-18 | 4 / 8 | band first, -2.4% | not over |

Starts. Lead = days from the band's crossing over to the run's start (known on the day).

| Broad uptrend starts | Case | Crossed over | Lead | BTC between | Typical alt 30 days: from the band / from the rule |
|---|---|---|---:|---|---|
| 2021-11-06, 2021-12-23, 2022-01-17 | start unknown (over since the band's first day) | | | | |
| 2022-04-02 | band first | 2022-03-30 | 3 | band first, -2.7% | -32% / -35% |
| 2022-07-20 | band first | 2022-06-29 | 21 | band first, +15.4% | +23% / -4% |
| 2023-01-13 | band later | 2023-01-18 | -5 | rule first, +3.8% | +24% / +14% |
| 2023-10-22 | band first | 2023-09-24 | 28 | band first, +14.3% | +11% / +20% |
| 2024-02-26 | band later | 2024-03-03 | -6 | rule first, +15.9% | -7% / +19% |
| 2024-09-25 | band first | 2024-08-22 | 34 | band first, +4.6% | +4% / -9% |
| 2025-05-15 | band first | 2025-05-13 | 2 | band first, -0.3% | -25% / -19% |
| 2025-07-11 | over since before the dip (crossed over 2025-05-13) | | | | |
| 2026-03-20 | band first | 2026-03-14 | 6 | band first, -1.0% | -3% / -3% |
| 2026-08-20 | band later | 2026-08-27 | -7 | rule first, +9.9% | +21.5% / +18.5% |

| Bar | Ends | Starts | Needed |
|---|---|---|---|
| 1. Runs with both | 12 | 9 | 8 or more |
| 2. Band first | 8 of 12 (67%) | 6 of 9 (67%) | 75% or more |
| 3. Median lead | 3 days | 3 days | 10 days or more |
| 4. Crossings followed within 60 days | 9 of 9 | 6 of 6 | 75% or more |
| Verdict | not met | not met | |

### Also reported

Every day with a band (2021-09-20 to 2026-11-05), by side and by whether a broad uptrend was under way. The days overlap, so this is description. Medians, with the share of days that rose:

| Share against its band | Broad uptrend | Days | BTC 30 days | Typical alt 30 days | BTC 60 days | Typical alt 60 days |
|---|---|---:|---|---|---|---|
| over | yes | 719 | -1.0% (46%) | -8.0% (29%) | -3.0% (44%) | -17.0% (28%) |
| over | no | 199 | +9.7% (79%) | +12.0% (68%) | +8.9% (68%) | +7.0% (62%) |
| inside | yes | 39 | +1.8% (66%) | -8.5% (29%) | +3.8% (70%) | -8.5% (43%) |
| inside | no | 81 | +1.4% (58%) | -4.0% (26%) | +13.9% (69%) | +8.0% (60%) |
| under | yes | 132 | +5.7% (71%) | -4.5% (42%) | +26.6% (81%) | +17.0% (68%) |
| under | no | 703 | -1.2% (47%) | -9.0% (30%) | -2.6% (45%) | -16.0% (21%) |
| every day with a band | | 1,873 | +0.8% (53%) | -6.7% (34%) | +0.6% (51%) | -13.0% (34%) |

The 132 days under the band during a broad uptrend come from 9 runs, 47 of them from July and August 2026 and 19 from November and December 2022.

**The last day, 2026-11-05.** The share is 22.1%, under its band (66.8-68.0%) since the crossing of 2026-10-18, 4 days before the 55% rule's end of 2026-10-22. No broad uptrend is under way. The band sits high because of the two long runs of 2026.

**Checked.** A separate script, written from this declaration without the study code, rebuilt the band, the 13 stretches under and the 10 crossings over, and the 14 broad uptrends: all agree. It also rebuilt one event (2025-10-14): BTC -20.2% over 60 days, and the typical alt's same-share median of +1.25% over 186 days (the run shows +1.2 and an excess of -38.2).

### Reading (in sample; context, not a signal)

- **Prices: nothing to separate from the share's level.**
  - After the share crossed under its band, the typical alt over 60 days was below days at the same share in 5 of 10 cases (median 7 points below). BTC was above them (median 10 points).
  - Over 30 days, the typical alt was lower in 7 of 10 (median 14 points). That is a reported row, and it also stops short of its own checks (7 of 10, draws 6.1%).
  - After the share crossed back over, both were higher than at the same share more often than not: the typical alt in 6 of 9 (median +22 points) and BTC in 7 of 9 (+14 points). But days drawn at random at the same share gave a median as high in 12% and 17% of the draws. With 9 events, that is not separable from chance. 2022-03-30, a bear-market rally that failed, is the large exception (BTC -37%, typical alt -61% over 60 days).
- **What the crossing does show is the share itself.** After a crossing under, the share fell a median 30 points further in 30 days than at the same share (8 of 10; draws 0.6%). A reported row: the share's own momentum, which the 55% rule then reads.
- **Timing: the band and the 55% rule mostly agree within days.**
  - Ends: the band crossed under first in 8 of 12 runs, by 1 to 43 days (median 6.5). It came after the end in three runs of 2021-22 (41, 11 and 19 days long) and on the same day once. Counting all 12, the median lead is 3 days.
  - Against the day the rule knows an end (4 days after its end day), the band was earlier in 9 of 12, by a median of 7 days. This is reported, not declared.
  - The two long leads were the 2022-07 run (20 days) and the 2026 spring run (43 days). Over the 43 days of 2026, BTC rose 10.8% and the typical alt was 11% lower 30 days after the band's crossing, against 22% higher 30 days after the rule's.
  - Starts: the band crossed over first in 6 of 9, by 2 to 34 days; the three later ones came 5 to 7 days after the start. Median lead 3 days.
- **No false alarms in this record.** All 9 crossings under during a broad uptrend came on or before that run's end day (0 to 43 days before it), and all 6 crossings over outside one came 2 to 34 days before the next start. This check passed for both. The verdicts fail on the order (8 of 12 and 6 of 9 first, against 9 of 12 and 7 of 9 needed) and on the lead (3 days against 10).
- **Why it lines up.** The band is a 20-week average of the share. When the months before were mostly high readings, it sits high and the share falls through it on the way down to 55%. When they were low, it sits far under 55% and the 55% line comes first. That is what the tables show: band first at the ends of runs that followed long high stretches, band later at the three ends of 2021-22, when the band was young and built on the low readings of mid-2021.
- **Days under the band during a broad uptrend** were followed by gains (BTC +27% over 60 days, 81% of days up). Half of these days (66 of 132) come from July and August 2026 and from late 2022, out of 9 runs. The days overlap, so this is a few episodes, not a pattern.
- **What this means for the app.** The band on the share adds little to the 55% rule in this record: its crossings come within days of the rule's starts and ends, and the prices after them were not separable from days at the same share. Nothing here calls for a change.

Caveats that go with every number above: 10 and 9 events, 13 broad uptrends, about two cycles plus 2026, with events in one cycle not independent. Today's coin list, so the typical alt reads better than it was. Binance spot closes, not Hyperliquid perps.

**The crossing of 2026-10-18** has no outcome yet. It falls before the out-of-sample line (7 November 2026), so as declared it counts in neither sample. Its 30 and 60 days close on 17 November and 17 December 2026, and can then be shown as context.

## Deviations

**6 November 2026, after the first result: wording only, no rule or code changed.**

- Part B's list of start cases does not name "start unknown". The code applies the Definitions' rule (a stretch that begins in the band's first 6 days has an unknown start and is no crossing), so the three starts of 2021-22 that fall in the stretch over from 2021-09-20 are left out of "runs with both". The same rule left one stretch over out of Part A.
- "What the bar can see" used 12 runs with both as its example. The run found 12 for ends (9 needed first) and 9 for starts (7 needed first).
- The crossing of 2026-10-18 falls between the in-sample data's end and the out-of-sample line, so it counts in neither (above). The declaration did not say this.
