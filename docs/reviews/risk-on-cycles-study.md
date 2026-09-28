# Risk-on and risk-off cycles in market breadth (declared 28 September 2026, before running)

Question: once the share of coins in Uptrend crosses 55% (RISK-ON), how long has it usually stayed above? How often did it keep climbing toward 100%, and how often did it roll over? How does BTC's weekly bull market support band fit in: does BTC break it before breadth turns? And given today's reading, what followed similar moments in the past?

This is market context, not a signal. Answers are historical frequencies with their counts ("in 7 of 12 past runs"), never forecasts. It changes no scanner rule.

Everything below is fixed before any analysis code runs. Only data shape and counts were looked at, and the counts quoted come from that check. No run has been detected and no outcome computed.

Code: `backend/backtest/risk_on_cycles.py`, run from `backend/` as `python -m backtest.risk_on_cycles insample`. After the in-sample results are committed, the same code runs as `python -m backtest.risk_on_cycles oos`. Tests: `backend/tests/test_risk_on_cycles.py`.

## What was already known

- The market-breadth study (docs/reviews/market-breadth-study.md) and the forward test's exploratory table (docs/reviews/btc-band-breadth-forward-test.md) were both read on the same in-sample data.
- So the broad shape of this history has been seen before. The in-sample numbers here are description. The out-of-sample check is the only clean test.

## Data

- **Breadth.** The market history rebuild (`data/larsson_runs/breadth_history.json`, the numbers behind the drawer's seed): 151 coins, the live engine on Binance daily closes.
- **Days used:** those with 40 or more coins. That is 1,974 days, 2021-05-01 to 2026-09-25, none missing: 1,794 up to 2026-03-29 and 180 after.
- **Coins per day:** 40 on 2021-05-01, 135 on 2026-03-29, 145 on 2026-09-25.
- **Uptrend share** = Uptrend + Overheated, as in the forward test. Overheated is 0 on every rebuilt day, so this equals the drawer's Uptrend share. It keeps the rule the same if Overheated starts firing.
- **BTC band.** `market_history.btc_band` on BTC's daily closes from 2019-07-19. Weekly closes on Sundays; 20-week SMA and 21-week EMA of completed weeks, used from the next day. Lower edge = the smaller of the two, upper edge = the larger. It exists on every day studied.
- **BTC side.** "Below its band" = a daily close below the lower edge. Otherwise BTC is "holding its band". Where three states are shown: above (close above the upper edge), inside, below.
- **Band break.** Days below the band, with gaps of up to 5 days merged, form one break stretch. Its first day is a band break. So a break has no below-band close in the 6 days before it.
- **Latest reading (today).** The production API (`/api/market-history`) on the run day: its last day's Uptrend share and BTC close, and its days after 2026-09-25 appended to the rebuild. On overlapping days the two must agree within 1 point of Uptrend share, or the run stops.

## Samples and the holdout

The owner's standing rule keeps data after 2026-03-29 as a holdout. He approved using it once: for this study's out-of-sample check, and then to score recent episodes in the history drawer.

- **In-sample.** The code sees days up to 2026-03-29 only. Every window must end on or before that day: run ends (including the 4 days needed to confirm an end), analog outcomes, band-break reactions. A run still open on 2026-03-29 is censored there.
- **One exception.** To choose the analog buckets, the in-sample stage reads today's state: the latest Uptrend share, BTC's side, and the current run's start. No outcome after 2026-03-29 is used.
- **Out-of-sample.** After the in-sample results are committed, the same code (commit hash recorded) runs with data to 2026-09-25. Only runs, events and analog days that start after 2026-03-29 count, plus the run censored in-sample, which is marked. Nothing in-sample is re-run or changed.
- After this, April to September 2026 is no longer a clean holdout for questions about breadth cycles.

## Definitions

### Runs

- **Risk-on run.** Starts on the first day with Uptrend share of 55% or more after at least 5 consecutive days below 55%. Ends on the first day of a stretch of 5 or more consecutive days below 55%. Dips below 55% of 4 days or less stay inside the run.
- **Risk-off run.** The days in between: from a risk-on run's end day to the next start. By construction it is at least 5 days long, while a risk-on run can be 1 day long.
- **Length** = end day minus start day, i.e. the number of days in the run.
- **Censored.** An end is confirmed only when its 4 following days are in the sample. A run with no confirmed end by the sample's last day is censored. It lasted at least (its last day at 55% or more, minus its start, plus 1) days.
- **The first run** (in progress on 2021-05-01) has no known start. Detection begins as if the days before were of the same type as 2021-05-01. That run is listed, but left out of lengths, survival, peak timing and anything that needs its age.

### Fields per run

| Field | Risk-on run | Risk-off run |
|---|---|---|
| Start, end, length | as above | as above |
| Extreme | peak Uptrend share | lowest Uptrend share |
| Reached | 85% or more; 95% or more | 15% or less; 5% or less |
| Days to extreme | start to the first day at the peak | start to the first day at the low |
| BTC return | start to end day; peak day to end day | start to end day; low day to end day |
| Typical alt return | the same days | the same days |
| BTC at start | above, inside or below the band | the same |
| BTC during the run | band breaks starting on a run day: how many; days from the first and from the last to the end day; below the band on the end day? | side on the end day; days BTC had been holding its band by the end day (0 if below) |

Censored runs get the same fields up to their censor day, labelled "censored".

### Outcomes

- **BTC:** simple return between two daily closes.
- **Typical alt:** the median simple return over coins other than BTC with a close on both days, at least 20 coins (else missing), as in the market-breadth study.
- Days are calendar days on daily closes, measured from the close of the first day.
- **Quartiles:** the value at position ⌊p·(n−1)⌋ of the sorted list, as in the market-breadth study. Medians are ordinary medians.
- **Frequency intervals:** Wilson 90% (z = 1.645).

## Measures

### 1. The runs (how long, how far)

- Every risk-on and risk-off run listed with its fields: the timeline of the waves.
- For each type: number of runs, and length median and quartiles.
- Risk-on runs:
  - share reaching 85% and 95%, for all ended runs and for runs that lasted at least 30 days;
  - days from start to peak (median, quartiles);
  - BTC and typical alt during the run, and from peak to end (median, quartiles).

### 2. Survival of risk-on runs

For d = 10, 20, 30, 45, 60, 90 and 120: of the risk-on runs that lasted at least d days, the share that lasted at least 30 days more (d + 30 in all).

- A censored run is at risk at d if it lasted at least d days. It counts in the share only if its outcome is known, i.e. it had already lasted d + 30. Otherwise it is left out of that row, and the number left out is shown.
- One extra row at today's run age A (section 4): of runs that lasted at least A days, the share that lasted A + 30, and A + 60.
- Each row: runs at risk, runs with a known outcome, runs that lasted, the share, its Wilson 90% interval.

### 3. BTC band and breadth

**3a. Days.** Every in-sample day by BTC side (above, inside, below) and by Uptrend share (55% or more, or below): day counts, and the median Uptrend share for each BTC side. Days overlap, so no intervals.

**3b. How risk-on runs end.** Each ended risk-on run falls in the first case that applies:

1. A band break starts between the run's start and its end day: "BTC broke first". Lead = end day minus the latest such break (0 = the same day).
2. BTC is below its band on the end day, from a break that began before the run: "BTC already below".
3. A band break starts within 60 days after the end day: "breadth ended first". Lag = break day minus end day.
4. None of these: "no band break within 60 days". This needs the end day plus 60 inside the sample; otherwise "not known yet".

Reported: the count in each case, each run's lead or lag, and their median and quartiles. "Ended without BTC breaking first" = cases 3 and 4.

**3c. After a band break while breadth is risk-on.** Events: band breaks on a day with Uptrend share of 55% or more. For each (window plus 4 days inside the sample):

- the change in Uptrend share after 10 and 30 days (points);
- whether the risk-on run ended within 30 and within 60 days;
- BTC and typical alt return over 30 and 60 days.

For comparison, over all days with Uptrend share of 55% or more and BTC holding its band: the share of days whose run ended within 30 and 60 days, and the median returns. Days overlap, so no intervals.

3c overlaps the forward test's exploratory table (same data, a close definition), so it is not new evidence for that test. The forward test is not changed: its rule, its history and its counting of episodes after 26 September 2026 stay as they are. April to September 2026 is before its declaration and does not count toward it.

### 4. Moments like today (analogs)

Today's state, from the latest reading:

- **Breadth bucket:** the 10-point bucket of the Uptrend share (80-90% for a reading of 81%).
- **Run age:** days since the current risk-on run began, start day = 0. (If the latest reading were below 55%: days since the current stretch below 55% began, and analog days must also be below 55%.)
- **Age buckets:** 0-15, 15-30, 30-60, 60-120, 120 days or more (lower edge included).
- **BTC side:** below its band, or holding it.

Two analog sets:

- **A, full match:** same breadth bucket, same age bucket, same BTC side, same side of 55%. One episode per run: its first matching day. All matching days of one run sit inside one age bucket and share most of their future, so they are one case.
- **B, breadth only:** same breadth bucket. Matching days with gaps of up to 5 days merged form one episode, measured from its first day (the market-breadth study's rule).

Days of the first run are left out of A (their age is unknown) but can count in B.

For each set, over the next 30 and 60 days from the episode's first day (window plus 4 days inside the sample):

- the share where the Uptrend share reached 90% or more on any day;
- the share where the run ended (5 or more days below 55%, the end day inside the window);
- BTC and typical alt return: median and quartiles.

Each with the number of episodes, and Wilson 90% intervals for the shares. For comparison, the same measures over all in-sample days (days overlap, so no intervals).

### 5. Where we are now

- Today's run: start, age, peak so far, whether it reached 85% or 95%, BTC's side, and any band breaks since it began.
- Its age against ended in-sample risk-on runs: how many lasted at least as long.
- Today's Uptrend share percentile, as the drawer computes it.
- The survival row at today's age (section 2) and the analogs (section 4).

## Honesty rules (fixed now)

- Every frequency comes with its count, e.g. "in 7 of 12 past episodes (90% range 36-78%)".
- A row with fewer than 6 independent episodes or runs is labelled "too few to read". Its numbers are shown but not described.
- No result is phrased as a forecast: no "will", "likely", "expected" or "probability of". Results say what happened before: "historically, in k of n cases".
- The units of evidence are runs and episodes, not days. Runs from the same cycle are not independent either: the history holds roughly two market cycles.
- The caveats go with the results:
  - today's coin list: coins that died are missing, so the typical alt looks better than it was;
  - fewer coins early on (40 in May 2021, 135 by March 2026);
  - the rebuild's universe is not the live scanner's (81% against 77% on 25 September);
  - Binance spot closes, not Hyperliquid perps.
- No threshold, bucket or window changes after results are seen. Any extra cut is labelled exploratory.

## Out-of-sample check (fixed now)

The frozen code runs on data to 2026-09-25. Only cases that start after 2026-03-29 count, plus the censored run, marked. For each pattern below it reports the out-of-sample value, its count, and one verdict:

- **"consistent"**: for a share, the out-of-sample share lies inside the in-sample Wilson 90% interval. For a return, length, lead or lag, the out-of-sample median (a single case: its value) lies inside the in-sample interquartile range.
- **"did not hold out of sample"**: otherwise.
- With fewer than 6 out-of-sample cases, the verdict is shown with "(n = k, too few to read)". With none: "no out-of-sample case".
- Runs still open on 2026-09-25 are listed as censored. They count only in survival rows where their outcome is already known.

Patterns checked:

1. Risk-on and risk-off run lengths (ended runs).
2. The share of risk-on runs reaching 85% and 95%.
3. Survival rows with at least 6 in-sample runs.
4. How runs end (3b): the share where BTC broke first, and the lead and lag.
5. After a band break while risk-on (3c): run ended within 30 and 60 days; typical alt over 30 and 60 days.
6. Analogs A and B: all four measures, at 30 and 60 days.

## In the product (after the out-of-sample check)

The history drawer:

- **Scores the episodes after 2026-03-29** in "Last times we were here", with the market-breadth study's outcomes (BTC and typical alt over 10, 30 and 60 days from the first day), marked "after the study window". An outcome appears once its window has closed; before that the row says how many days are left instead of "not scored".
- **Adds cycle context:** the current run's start and age, how many past runs lasted that long, the survival row for today's age, and the analog frequencies. Each is worded "in k of n past cases", with "too few to read" where it applies and the out-of-sample verdict beside it.
- The market-breadth study's rules stay for its bands: no direction below its bar, no probabilities. This study's frequencies appear only as counts of past cases, never as a chance of what comes next.

## Results

To be added below after each stage. Nothing above changes.
