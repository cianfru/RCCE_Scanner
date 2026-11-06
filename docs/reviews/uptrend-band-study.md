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

## Deviations

None so far.
