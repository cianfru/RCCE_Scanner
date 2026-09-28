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


## In-sample results (outcomes up to 2026-03-29)

Run on 28 September 2026 with `python -m backtest.risk_on_cycles insample`, using the code at commit 980a0bc. The sample is 1,794 days, from 2021-05-01 to 2026-03-29, and every window below ends by 2026-03-29. The latest reading came from the production API, fetched on 28 September with a last day of 2026-09-27. Its 1,974 days that overlap the rebuild match exactly (the largest difference is 0 points), and 26 and 27 September were appended. The out-of-sample stage has not been run.

**Revised on 28 September after an independent review, before the out-of-sample stage.** What changed:

- **A display bug.** The report rounded a share twice (to 3 decimals, then to a whole percent), so 5 of 11 read 46%. It is 45%. The 3a medians went through the same double rounding. Their Sunday values were already right; the Wednesday check's "above" median (50.5%) now reads 51%. No other declared number changed: the rerun, on the same API snapshot, matches the first run in every declared field.
- **Added, labelled exploratory:** how many runs the set B episodes and the 3c events come from, with a one-episode-per-run cut of set B; the next band break after each run's end; 3b with the first run counted. These add fields and change none of the declared ones.
- **The reading was corrected** where it said more than the numbers: 3b's "never in the 60 days after", set B's independence, and the cut by cycle. The notes on today's run age, the survival convention and the Wednesday band were completed.
- The code for this revision is the frozen commit recorded in the out-of-sample section.

**One difference from the declaration: the band's weekday.** The declaration names `market_history.btc_band` and says weekly closes fall on Sundays, but that function's filter `(d + 4) % 7 == 3` picks Wednesday closes. This study follows the declared Sunday closes, using the same arithmetic (`weekly_band`). As a check, it also ran on the Wednesday band. Among the numbers shown, only these move:

- 3c, the band breaks while risk-on: 5 events become 6. 2024-10-01 becomes 2024-10-02, and 2024-10-09 is added. They still come from 4 runs, so the row stays too few to read.
- The timeline: run 1's lag goes from 3 to 2 days; run 19's breaks from 1 to 2 and its lead from 113 to 105 days; the holding days at the end of run 8 from 10 to 7 and of run 18 from 8 to 9.
- 3a: the day counts shift by 1 to 3 days, and the median share with BTC below its band goes from 22% to 23%.

Runs, the run summaries, survival, 3b's case counts and both analog sets are identical. The drawer's band and the forward test's code also use Wednesday closes, while the forward test's declared rule says Sunday. Its exploratory table of 9 episodes matches the Wednesday band. On Sunday closes it would read 8 episodes, with 2024-10-01 lasting 10 days instead of 2024-10-02 and 2024-10-09, and 2025-09-25 lasting 1 day instead of 3. Nothing is changed here, and the forward test is not disturbed. This is for the owner to decide.

Owner decision, 28 Sep 2026: the drawer and the forward test now use Sunday closes.

### Today's state (the one reading taken from after the holdout line)

| | |
|---|---|
| Day | 2026-09-27 |
| Uptrend share | 82.1% (bucket 80-90%) |
| Current risk-on run | began 2026-08-20; 38 days old (age bucket 30-60 days) |
| BTC | 84,472, above its band: 70,254-72,617 on the declared Sunday closes, 69,624-72,874 on the Wednesday closes the drawer uses |
| Percentile | higher than 79% of in-sample days. The drawer, counting every day up to today, shows 77% |

The current run's peak so far, and any band breaks since 20 August, are after the holdout line. They are left to the out-of-sample stage.

**The run's age rests on one coin.** Today's run began right after a risk-off stretch of exactly the minimum 5 days: 2026-08-15 to 08-19, at 53.5% to 54.9%. On 08-19, 79 of 144 coins were in Uptrend; 80 would have made 55%. With that one coin the stretch would have lasted 4 days, it would not have ended the run before it, and today would be day 191 of a run that began 2026-03-20. The declared rule was applied as written. Every age-based number below (the survival row at 38 days, set A's age bucket, "6 of 11 lasted this long") depends on that one coin. The out-of-sample section reports the other age, labelled exploratory.

### 1. The runs

| Run type | Runs (ended / censored / first) | Length, days: median (quartiles) |
|---|---|---|
| Risk-on | 13 (11 / 1 / 1) | 41 (11 to 96), n = 11 |
| Risk-off | 12 (12 / 0 / 0) | 78.5 (26 to 156), n = 12 |

| Risk-on runs (ended) | All ended | Lasted 30+ days |
|---|---|---|
| Reached 85% | 5 of 11 (45%, 90% range 24-68%) | 5 of 7 (71%, 90% range 41-90%) |
| Reached 95% | 4 of 11 (36%, 90% range 18-61%) | 4 of 7 (57%, 90% range 29-81%) |

| Risk-on runs (ended) | Median (quartiles) |
|---|---|
| Days from start to peak | 16 (4 to 19), n = 11 |
| BTC, start to end | -5.8% (-12.4% to +11.4%), n = 11 |
| Typical alt, start to end | -5.2% (-24.5% to +6.6%), n = 11 |
| BTC, peak to end | -6.5% (-12.7% to +6.3%), n = 11 |
| Typical alt, peak to end | -10.6% (-29.1% to -3.8%), n = 11 |

| Risk-off runs (ended) | |
|---|---|
| Uptrend share fell to 15% or less | 7 of 12 (58%, 90% range 36-78%) |
| Uptrend share fell to 5% or less | 5 of 12 (42%, 90% range 22-64%) |
| Days from start to low | 22 (8 to 54), n = 12 |
| BTC, start to end | +8.7% (-9.1% to +23.3%), n = 12 |
| Typical alt, start to end | -21.7% (-44.7% to +4.3%), n = 12 |
| BTC, low to end | +5.8% (-11.6% to +18.5%), n = 12 |
| Typical alt, low to end | +3.6% (-23.3% to +22.1%), n = 12 |

The timeline of the waves: every run, with fields as declared. Returns run from the start day to the end day, or to 2026-03-29 for the censored run. The first run's start is unknown: it is listed, but it counts in no run statistic.

| # | Type | Start | End | Days | Extreme | Days to it | BTC | Alt | BTC at start | BTC during / at end |
|---:|---|---|---|---:|---:|---:|---:|---:|---|---|
| 1 | on (start unknown) | 2021-05-01 | 2021-05-14 | 13 | 62.5% | 0 | -13.8% | +8.1% | above | 0 break(s); breadth first, lag 3d |
| 2 | off | 2021-05-14 | 2021-11-06 | 176 | 0.0% | 32 | +23.3% | -31.2% | above | above at end, holding 46d |
| 3 | on | 2021-11-06 | 2021-12-17 | 41 | 83.7% | 18 | -25.0% | -33.3% | above | 1 break(s); btc first, lead 13d |
| 4 | off | 2021-12-17 | 2021-12-23 | 6 | 50.0% | 4 | +10.2% | +14.3% | below | below at end, holding 0d |
| 5 | on | 2021-12-23 | 2022-01-03 | 11 | 71.2% | 4 | -8.6% | -5.2% | below | 0 break(s); already below |
| 6 | off | 2022-01-03 | 2022-01-17 | 14 | 44.2% | 8 | -9.1% | -12.2% | below | below at end, holding 0d |
| 7 | on | 2022-01-17 | 2022-01-25 | 8 | 65.4% | 1 | -12.4% | -30.2% | below | 0 break(s); already below |
| 8 | off | 2022-01-25 | 2022-04-02 | 67 | 13.5% | 2 | +24.0% | +22.9% | below | above at end, holding 10d |
| 9 | on | 2022-04-02 | 2022-04-21 | 19 | 65.5% | 5 | -11.6% | -21.2% | above | 1 break(s); btc first, lead 15d |
| 10 | off | 2022-04-21 | 2022-07-20 | 90 | 7.1% | 24 | -42.6% | -53.9% | below | below at end, holding 0d |
| 11 | on | 2022-07-20 | 2022-12-10 | 143 | 98.3% | 20 | -26.2% | -24.0% | below | 0 break(s); already below |
| 12 | off | 2022-12-10 | 2023-01-13 | 34 | 40.6% | 11 | +16.4% | +4.3% | below | above at end, holding 2d |
| 13 | on | 2023-01-13 | 2023-03-07 | 53 | 85.9% | 16 | +11.4% | +6.6% | above | 0 break(s); no break 60d |
| 14 | off | 2023-03-07 | 2023-10-22 | 229 | 1.5% | 101 | +35.1% | -32.7% | above | above at end, holding 7d |
| 15 | on | 2023-10-22 | 2024-01-31 | 101 | 97.2% | 27 | +42.0% | +52.7% | above | 0 break(s); no break 60d |
| 16 | off | 2024-01-31 | 2024-02-26 | 26 | 29.3% | 15 | +27.9% | +24.4% | above | above at end, holding 134d |
| 17 | on | 2024-02-26 | 2024-03-27 | 30 | 78.7% | 19 | +27.5% | +19.3% | above | 0 break(s); no break 60d |
| 18 | off | 2024-03-27 | 2024-09-25 | 182 | 0.0% | 54 | -9.1% | -44.7% | above | above at end, holding 8d |
| 19 | on | 2024-09-25 | 2025-01-22 | 119 | 97.9% | 55 | +64.2% | +12.3% | above | 1 break(s); btc first, lead 113d |
| 20 | off | 2025-01-22 | 2025-05-15 | 113 | 1.9% | 86 | +0.1% | -39.1% | above | above at end, holding 25d |
| 21 | on | 2025-05-15 | 2025-05-21 | 6 | 57.6% | 2 | +5.7% | +0.5% | above | 0 break(s); no break 60d |
| 22 | off | 2025-05-21 | 2025-07-11 | 51 | 45.4% | 20 | +7.2% | -10.7% | above | above at end, holding 82d |
| 23 | on | 2025-07-11 | 2025-10-15 | 96 | 98.2% | 15 | -5.8% | -24.5% | above | 2 break(s); btc first, lead 4d |
| 24 | off | 2025-10-15 | 2026-03-20 | 156 | 4.7% | 61 | -36.3% | -57.5% | below | below at end, holding 0d |
| 25 | on | 2026-03-20 | censored | 10+ | 63.0% | 9 | -6.4% | -10.2% | below | 0 break(s) |

### 2. Survival of risk-on runs

The last two rows use today's run age (38 days).

| Lasted at least d days | At risk | Known | Lasted d+30 | Left out (censored) |
|---:|---:|---:|---|---:|
| 10 (+30) | 10 | 9 | 6 of 9 (67%, 90% range 40-86%) | 1 |
| 20 (+30) | 7 | 7 | 5 of 7 (71%, 90% range 41-90%) | 0 |
| 30 (+30) | 7 | 7 | 4 of 7 (57%, 90% range 29-81%) | 0 |
| 45 (+30) | 5 | 5 | 4 of 5 (80%, 90% range 44-95%), too few to read | 0 |
| 60 (+30) | 4 | 4 | 4 of 4 (100%, 90% range 60-100%), too few to read | 0 |
| 90 (+30) | 4 | 4 | 1 of 4 (25%, 90% range 6-64%), too few to read | 0 |
| 120 (+30) | 1 | 1 | 0 of 1 (0%, 90% range 0-73%), too few to read | 0 |
| 38 (+30) | 6 | 6 | 4 of 6 (67%, 90% range 35-88%) | 0 |
| 38 (+60) | 6 | 6 | 3 of 6 (50%, 90% range 22-78%) | 0 |

Convention: a row counts runs whose length (end day minus start day) is at least d, as declared. A run still open at age 38 already has 39 days, so "lasted beyond today's age" would be length 39 or more. No ended run had a length of exactly 38, so both give the same rows.

### 3. BTC band and breadth

**3a. Days** (in-sample, 2021-05-01 to 2026-03-29; the days overlap, so no intervals):

| BTC side | Days | Uptrend share 55%+ | Below 55% | Median Uptrend share |
|---|---:|---:|---:|---:|
| above | 932 | 434 | 498 | 51% |
| inside | 68 | 11 | 57 | 26% |
| below | 794 | 204 | 590 | 22% |

**3b. How risk-on runs ended** (11 ended runs; the first run is not counted):

| How risk-on runs ended | Runs |
|---|---:|
| btc first | 4 |
| already below | 3 |
| breadth first | 0 |
| no break 60d | 4 |
| not known yet | 0 |

BTC broke first: 4 of 11 (36%, 90% range 18-61%). Ended without BTC breaking first: 4 of 11 (36%, 90% range 18-61%). Lead: 14 (4 to 15), n = 4, too few to read. Lag: none.

Exploratory (added after review). The declared case order puts a run in "BTC broke first" as soon as a break starts inside it, which hides a break that came after breadth's end. Days from each run's end to the next band break that started after it:

| Risk-on run | Declared case | Next band break after the end |
|---|---|---:|
| 2021-05-01 (first run, not counted) | breadth first, lag 3d | 3 days |
| 2021-11-06 | btc first, lead 13d | 110 days |
| 2021-12-23 | already below | 93 days |
| 2022-01-17 | already below | 71 days |
| 2022-04-02 | btc first, lead 15d | 410 days |
| 2022-07-20 | already below | 177 days |
| 2023-01-13 | no break 60d | 90 days |
| 2023-10-22 | no break 60d | 145 days |
| 2024-02-26 | no break 60d | 89 days |
| 2024-09-25 | btc first, lead 113d | 34 days |
| 2025-05-15 | no break 60d | 127 days |
| 2025-07-11 | btc first, lead 4d | none by 2026-03-29 |

- The 2024-09 run counts as "BTC broke first" because of the break on its day 6 (2024-10-01), 113 days before its end. The next break started on 2025-02-25, 34 days after breadth's end.
- Counting the first run, whose start is unknown but whose end is known: BTC broke first in 4 of 12 (90% range 16-57%), breadth ended first in 1 of 12 (2-30%), BTC already below in 3 of 12, no break within 60 days in 4 of 12.

**3c. After a band break while breadth is risk-on.** These events overlap the forward test's exploratory table, so they are not new evidence for it. The 5 events come from 4 runs: 2025-09-25 and 2025-10-11 both fall in the 2025-07 run and share its end. Too few to read.

| Band break while risk-on | Day | Share | Change 10d | Change 30d | Ended 30d | Ended 60d | BTC 30d | Alt 30d | BTC 60d | Alt 60d |
|---|---|---:|---:|---:|---|---|---:|---:|---:|---:|
| 1 | 2021-12-04 | 76.9% | -11.5 | -23.1 | yes | yes | -5.5% | -4.4% | -24.9% | -34.9% |
| 2 | 2022-04-06 | 63.6% | -2.9 | -27.9 | yes | yes | -16.6% | -27.8% | -30.7% | -54.7% |
| 3 | 2024-10-01 | 83.2% | -0.9 | +1.1 | no | no | +15.6% | -1.2% | +58.6% | +64.0% |
| 4 | 2025-09-25 | 89.0% | +0.0 | -66.3 | yes | yes | +2.4% | -20.2% | -19.0% | -40.4% |
| 5 | 2025-10-11 | 85.7% | -55.5 | -70.6 | yes | yes | -4.2% | -1.2% | -16.8% | -27.1% |

| After a band break while risk-on | Events | All days 55%+ with BTC holding (days overlap) |
|---|---|---|
| Run ended within 30 days | 4 of 5 (80%, 90% range 44-95%), too few to read | 187 of 445 (42%) |
| BTC 30d | -4.2% (-5.5% to +2.4%), n = 5, too few to read | +1.6% (-4.6% to +12.6%), n = 445 |
| Typical alt 30d | -4.4% (-20.2% to -1.2%), n = 5, too few to read | -8.2% (-22.2% to +6.7%), n = 445 |
| Run ended within 60 days | 4 of 5 (80%, 90% range 44-95%), too few to read | 314 of 445 (71%) |
| BTC 60d | -19.0% (-24.9% to -16.8%), n = 5, too few to read | +6.1% (-8.3% to +24.0%), n = 445 |
| Typical alt 60d | -34.9% (-40.4% to -27.1%), n = 5, too few to read | -12.4% (-38.3% to +10.1%), n = 445 |
| Uptrend share change 10d (points) | -2.9 (-11.5 to -0.9), n = 5, too few to read | |
| Uptrend share change 30d (points) | -27.9 (-66.3 to -23.1), n = 5, too few to read | |

### 4. Moments like today (analogs)

- Set A: Uptrend share 80-90%, day 30-60 of a risk-on run, BTC holding its band.
- Set B: Uptrend share 80-90% only.
- "Run ended" means a risk-on run's end day fell inside the window. In the all-days column this includes days that were already risk-off.

| Analogs | Set A (full match) | Set B (breadth bucket only) | All in-sample days (overlap) |
|---|---|---|---|
| 30d: episodes | 4 | 13 | 1760 days |
| 30d: Uptrend share reached 90% | 3 of 4 (75%, 90% range 36-94%), too few to read | 5 of 13 (38%, 90% range 20-61%) | 386 of 1760 (22%) |
| 30d: run ended | 1 of 4 (25%, 90% range 6-64%), too few to read | 5 of 13 (38%, 90% range 20-61%) | 322 of 1760 (18%) |
| 30d: BTC | +8.4% (+0.2% to +13.3%), n = 4, too few to read | +0.5% (-2.8% to +5.8%), n = 13 | +0.3% (-8.5% to +11.0%), n = 1760 |
| 30d: typical alt | +0.9% (-6.3% to +4.8%), n = 4, too few to read | -3.9% (-9.1% to +4.0%), n = 13 | -7.4% (-20.3% to +6.3%), n = 1760 |
| 60d: episodes | 4 | 13 | 1730 days |
| 60d: Uptrend share reached 90% | 3 of 4 (75%, 90% range 36-94%), too few to read | 7 of 13 (54%, 90% range 32-74%) | 527 of 1730 (30%) |
| 60d: run ended | 3 of 4 (75%, 90% range 36-94%), too few to read | 8 of 13 (62%, 90% range 39-80%) | 588 of 1730 (34%) |
| 60d: BTC | +21.8% (-2.4% to +39.4%), n = 4, too few to read | -1.6% (-16.8% to +21.3%), n = 13 | +1.4% (-13.2% to +22.4%), n = 1730 |
| 60d: typical alt | +0.2% (-29.4% to +1.4%), n = 4, too few to read | -4.6% (-29.4% to +5.1%), n = 13 | -13.1% (-28.0% to +9.5%), n = 1730 |

| Set A episode | Share | Reached 90% 30d | Ended 30d | BTC 30d | Alt 30d | Reached 90% 60d | Ended 60d | BTC 60d | Alt 60d |
|---|---:|---|---|---:|---:|---|---|---:|---:|
| 2023-02-12 | 85.9% | no | yes | +13.3% | -2.9% | no | yes | +39.4% | +1.4% |
| 2023-12-05 | 87.7% | yes | no | +0.2% | +4.8% | yes | yes | -2.4% | -1.0% |
| 2024-10-25 | 85.1% | yes | no | +46.8% | +52.4% | yes | no | +47.9% | +41.9% |
| 2025-08-29 | 88.0% | yes | no | +3.5% | -6.3% | yes | yes | +4.2% | -29.4% |

| Set B episode | Share | Reached 90% 30d | Ended 30d | BTC 30d | Alt 30d | Reached 90% 60d | Ended 60d | BTC 60d | Alt 60d |
|---|---:|---|---|---:|---:|---|---|---:|---:|
| 2021-11-23 | 81.6% | no | yes | -11.6% | -18.3% | no | yes | -39.0% | -48.6% |
| 2022-07-22 | 81.4% | yes | no | -5.2% | -1.8% | yes | no | -16.8% | -13.8% |
| 2022-09-17 | 88.3% | no | no | -2.8% | -8.8% | yes | no | -17.2% | -26.7% |
| 2022-11-13 | 87.1% | no | yes | +8.8% | +4.0% | no | yes | +15.4% | +5.1% |
| 2023-01-24 | 81.2% | no | no | +5.8% | +14.6% | no | yes | +21.3% | -4.6% |
| 2023-10-26 | 81.4% | yes | no | +10.6% | +25.8% | yes | no | +27.6% | +59.4% |
| 2023-12-05 | 87.7% | yes | no | +0.2% | +4.8% | yes | yes | -2.4% | -1.0% |
| 2024-01-05 | 89.0% | no | yes | -3.5% | -9.1% | no | yes | +44.4% | +31.1% |
| 2024-09-30 | 80.7% | no | no | +14.2% | -3.9% | yes | no | +53.9% | +48.4% |
| 2024-12-25 | 89.7% | no | yes | +5.5% | -16.9% | no | yes | -3.2% | -38.4% |
| 2025-07-15 | 81.1% | yes | no | +0.5% | -3.7% | yes | no | -1.6% | +3.9% |
| 2025-08-29 | 88.0% | yes | no | +3.5% | -6.3% | yes | yes | +4.2% | -29.4% |
| 2025-09-23 | 89.0% | no | yes | -1.7% | -26.8% | no | yes | -24.3% | -46.6% |

**Set B is 13 episodes from 6 runs** (noted after review). Three runs gave 3 episodes each (2022-07, 2023-10 and 2025-07), one gave 2 (2024-09), and two gave 1 (2021-11 and 2023-01). Episodes from one run share its end and most of their windows. The 5 "run ended within 30 days" are 5 distinct run ends. The 8 within 60 days are 6: the ends of the 2023-10 and 2025-07 runs are each counted twice. The 90% ranges treat the 13 episodes as independent, so they understate the uncertainty. The independent sample is about 6 runs, right at the too-few bar.

Exploratory cut, one episode per run (its first day in the 80-90% bucket):

| Set B, first episode of each run (exploratory) | 30 days | 60 days |
|---|---|---|
| Episodes (runs) | 6 | 6 |
| Uptrend share reached 90% | 3 of 6 (50%, 90% range 22-78%) | 4 of 6 (67%, 90% range 35-88%) |
| Run ended | 1 of 6 (17%, 90% range 4-50%) | 2 of 6 (33%, 90% range 12-65%) |
| BTC | +3.1% (-5.2% to +5.8%), n = 6 | +9.8% (-16.8% to +21.3%), n = 6 |
| Typical alt | -2.8% (-3.9% to -1.8%), n = 6 | -0.3% (-13.8% to +3.9%), n = 6 |

A run's first reading in the bucket usually comes early in the run, so this cut is not "moments like today" either. It shows how much the 13-episode figures depend on the unit.

### 5. Where we are now

- **Today's run:** began 2026-08-20 and is 38 days old. BTC is above its band. The Uptrend share is 82.1%, higher than 79% of in-sample days.
- **That age rests on one coin** (see "Today's state"): with one more coin in Uptrend on 2026-08-19, today would be day 191 of a run that began 2026-03-20, and no ended in-sample run lasted that long.
- **Age:** 6 of the 11 ended in-sample runs lasted at least 38 days.
- **Survival at 38 days:** of the 6 past runs that reached 38 days,
  - 4 lasted at least 30 more (90% range 35-88%);
  - 3 lasted at least 60 more (22-78%).
- **Analogs:** in section 4. Set A has 4 episodes, too few to read.

### Reading (in-sample; market context, not a signal)

- **In this history, risk-on runs fell into two groups.** Of the 11 ended runs:
  - 4 were short (6-19 days), with peaks of 58-71%;
  - 7 lasted 30 days or more. Of those 7, 5 reached 85% and 4 reached 95%.
  - Across all 11 ended runs, 5 reached 85% (90% range 24-68%) and 4 reached 95% (18-61%). All 5 that reached 85% lasted at least 53 days. Median length was 41 days (quartiles 11-96).
  - These are run-level peaks, and they include highs reached before today's age: of the 6 runs that reached day 38, 5 first touched their peak before day 38 (on days 15-27). The only counts taken forward from a reading like today's are sets A and B (section 4).
- **The high came early.** The first day at a run's peak came at a median of day 16 (quartiles 4-19). Only 1 of 11 runs, 2024-09, first touched its peak after day 30.
  - From that peak to the run's end, the typical alt fell in 8 of 11 runs (median -10.6%) and BTC in 7 of 11 (median -6.5%). Both points are known only in hindsight (the highest breadth reading, and breadth's collapse), so some decline over this span is built into the definitions.
  - The long runs sat near their peak for weeks, so "early" means the first touch.
- **How long after 38 days.** Of the 6 runs that reached today's age, 4 lasted at least another 30 days and 3 another 60. The ranges are wide (35-88% and 22-78%). The survival rows from 45 days on hold 5 runs or fewer, too few to read. Today's age of 38 rests on one coin (see "Today's state").
- **BTC's band and breadth moved together, loosely.**
  - With BTC above its band, breadth was 55% or more on 434 of 932 days (median share 51%). With BTC below, it was 204 of 794 (median 22%).
  - BTC above the band still left breadth under 55% on 498 of those 932 days.
- **How runs ended (3b).** Under the declared case order, of the 11 ended runs:
  - in 4, a band break started during the run ("BTC broke first"). In 3 of them (the runs that ended in December 2021, April 2022 and October 2025) the latest break came 4-15 days before breadth's end. The fourth, the 2024-09 run, counts only because of a brief break on its day 6 (October 2024), 113 days before its end. Its next band break came on 2025-02-25, 34 days after breadth ended;
  - in 3, all in the 2021-22 bear market, BTC was already below;
  - in 4 (March 2023, January 2024, March 2024, May 2025), there was no band break during the run or within 60 days after. The next breaks came 89-145 days after those ends;
  - no counted run fell in "breadth ended first". The first run, left out because its start is unknown, did: it ended on 2021-05-14, 3 days before the May 2021 break. Counting it (exploratory), breadth ended first in 1 of 12 and BTC broke first in 4 of 12.
  - So a band break a few days to two weeks before breadth's end happened in 3 of 11 runs. It was not the rule: 4 of 11 ended with no band break within 60 days.
- **Band breaks while risk-on:** 5 events from 4 runs, too few to read.
- **Moments like today:**
  - Set A has 4 episodes, too few to read. They are listed above: 2023-02-12, 2023-12-05, 2024-10-25, 2025-08-29.
  - Set B has 13 episodes from only 6 runs, so its ranges understate the uncertainty. Within 30 days, breadth touched 90% or more in 5 of 13 (90% range 20-61%) and the run ended in 5 of 13 (20-61%). Within 60 days, the counts were 7 of 13 (32-74%) and 8 of 13 (39-80%); the 8 hold 6 distinct run ends. Both can happen in one window.
  - With one episode per run (exploratory), the run ended within 30 days in 1 of 6 and within 60 days in 2 of 6, and breadth reached 90% in 3 of 6 and 4 of 6. The answer moves with the unit. Set B shows the range of what followed moments like today, not a rate to lean on.
  - The typical alt's 30-day median in set B was -3.9% (quartiles -9.1% to +4.0%), against -7.4% on all days. Over 60 days it was -4.6% (-29.4% to +5.1%), against -13.1%.
  - Both directions occurred: 2021-11-23 was followed by -49% over 60 days, and 2023-10-26 by +59%.
- **Where in the waves (the cut by cycle is exploratory).** The in-sample record holds about two cycles.
  - In 2021-22, 4 of 5 risk-on runs lasted 8-41 days. The exception, 2022-07 (143 days), began and ended with BTC below its band.
  - In 2023-25, 5 of 6 runs lasted 30-119 days, and all 6 began with BTC above its band.
  - BTC above its band at a run's start did not separate long runs from short ones. 2 of the 5 runs in 2021-22 also began with BTC above it (2021-11, 41 days; 2022-04, 19 days). Across the 11 ended runs, those that began with BTC above lasted 6-119 days, and those that began below lasted 8-143.
  - Risk-off runs had a median of 78.5 days (quartiles 26-156). The last one before the holdout line ran from 2025-10-15 to 2026-03-20, 156 days, with breadth falling to 4.7%.
  - Today's run is at day 38 by the declared rule, and 6 of 11 ended runs lasted that long.

Caveats that go with every number above:

- The universe is today's coin list. Coins that died are missing, so the typical alt looks better than it was.
- There were fewer coins early on: 40 in May 2021 and 135 by March 2026.
- The rebuild's universe is not the live scanner's: 81% against 77% on 25 September.
- Prices are Binance spot closes, not Hyperliquid perps.
- The units are runs and episodes: 11 ended runs, and 13 set B episodes from 6 runs. Runs from the same cycle are not independent, and the history holds about two cycles.
- The broad shape of this history had been seen before (see "What was already known"). These in-sample numbers are description; the out-of-sample check is the only clean test.

**Out-of-sample stage (not run yet).** The run censored in-sample is the risk-on run that began 2026-03-20, 10 or more days old on 2026-03-29. In the out-of-sample stage it is marked, and it counts only where its outcome was unknown in-sample. The analog buckets stay those above: 80-90%, 30-60 days, BTC holding its band.

## Out-of-sample check (Apr-Sep 2026)

Run on 28 September 2026 with `python -m backtest.risk_on_cycles oos --insample in.json`. **Frozen code: commit 590c45d** (590c45dd5ad6b97cec6f0f84eec3c070d85081ff), the commit that also produced the revised in-sample numbers above. The in-sample JSON it compares against was rerun at that commit and matches the in-sample section.

- **Data:** the rebuild to 2026-09-25, the last day with per-coin closes, as declared. The production API was fetched again on 28 September. Its last day is 2026-09-27, and its 1,974 days that overlap the rebuild match exactly. Its 26 and 27 September are used only for today's state.
- **Counted, as declared:** runs, events and analog days that start after 2026-03-29, plus the run censored in-sample, marked "began in-sample".
- **Buckets:** the analogs keep the in-sample buckets (80-90%, day 30-60, BTC holding its band).

**The out-of-sample runs.** Returns run from start to end, or to 2026-09-25 for the censored run.

| # | Type | Start | End | Days | Extreme | Days to it | BTC | Alt | BTC at start | BTC during / at end |
|---:|---|---|---|---:|---:|---:|---:|---:|---|---|
| 25 | on (began in-sample, marked) | 2026-03-20 | 2026-08-15 | 148 | 95.8% | 56 | -10.5% | -25.0% | below | 1 break (2026-05-22); btc first, lead 85d; below at end |
| 26 | off | 2026-08-15 | 2026-08-20 | 5 | 53.5% | 1 | +15.8% | +10.9% | below | above at end, holding 2d |
| 27 | on | 2026-08-20 | censored | 37+ | 81.4% | 20 | +15.2% | +33.0% | above | 0 breaks |

What happened:

- **The run that began on 2026-03-20 lasted 148 days.** That is longer than any in-sample run; the longest was 143 days, in 2022, and it also began with BTC below its band. Breadth first touched its peak of 95.8% on 2026-05-15, day 56.
- **BTC broke its band on 2026-05-22, with breadth at 94.4%** (on the Wednesday band the drawer uses, on 2026-05-18). From then to 2026-08-18, BTC closed below its band on 85 of 89 days. Breadth stayed around 85-89% until late June, faded through July, and the run ended on 2026-08-15, 85 days after the break. In the 3 comparable in-sample runs, the latest break came 4-15 days before breadth's end.
- **Returns.** From start to end, BTC returned -10.5% and the typical alt -25.0%. From the May peak to the end, they returned -20.3% and -31.7%.
- **After the run.** The risk-off run that followed lasted the minimum 5 days, with a low of 53.5%. BTC reclaimed its band on 2026-08-19, and a new risk-on run began the next day.

**Verdicts** (declared rule: "consistent" when the out-of-sample share lies inside the in-sample 90% range, or its median inside the in-sample quartiles):

| Pattern | In-sample | Out-of-sample | Verdict |
|---|---|---|---|
| Risk-on run length, days | 41 (11 to 96), n = 11 | 148, n = 1 | did not hold out of sample (n = 1, too few to read) |
| Risk-off run length, days | 78.5 (26 to 156), n = 12 | 5, n = 1 | did not hold out of sample (n = 1, too few to read) |
| Risk-on runs reaching 85% | 5 of 11 (45%, 90% range 24-68%) | 1 of 1 (100%) | did not hold out of sample (n = 1, too few to read) |
| Risk-on runs reaching 95% | 4 of 11 (36%, 90% range 18-61%) | 1 of 1 (100%) | did not hold out of sample (n = 1, too few to read) |
| Survival: lasted 10 days, then 30 more | 6 of 9 (67%, 90% range 40-86%) | 1 of 1 (100%) | did not hold out of sample (n = 1, too few to read) |
| Survival: lasted 20 days, then 30 more | 5 of 7 (71%, 90% range 41-90%) | 1 of 1 (100%) | did not hold out of sample (n = 1, too few to read) |
| Survival: lasted 30 days, then 30 more | 4 of 7 (57%, 90% range 29-81%) | 1 of 1 (100%) | did not hold out of sample (n = 1, too few to read) |
| Survival: lasted 38 days, then 30 more | 4 of 6 (67%, 90% range 35-88%) | 1 of 1 (100%) | did not hold out of sample (n = 1, too few to read) |
| Survival: lasted 38 days, then 60 more | 3 of 6 (50%, 90% range 22-78%) | 1 of 1 (100%) | did not hold out of sample (n = 1, too few to read) |
| How runs ended: BTC broke first | 4 of 11 (36%, 90% range 18-61%) | 1 of 1 (100%) | did not hold out of sample (n = 1, too few to read) |
| How runs ended: lead, days | 14 (4 to 15), n = 4, too few to read | 85, n = 1 | did not hold out of sample (n = 1, too few to read) |
| How runs ended: lag, days | none | none | no out-of-sample case |
| Band break while risk-on: run ended within 30d | 4 of 5 (80%, 90% range 44-95%), too few to read | 0 of 1 (0%) | did not hold out of sample (n = 1, too few to read) |
| Band break while risk-on: typical alt 30d | -4.4% (-20.2% to -1.2%), n = 5, too few to read | -18.5%, n = 1 | consistent (n = 1, too few to read) |
| Band break while risk-on: run ended within 60d | 4 of 5 (80%, 90% range 44-95%), too few to read | 0 of 1 (0%) | did not hold out of sample (n = 1, too few to read) |
| Band break while risk-on: typical alt 60d | -34.9% (-40.4% to -27.1%), n = 5, too few to read | -20.8%, n = 1 | did not hold out of sample (n = 1, too few to read) |
| Set A, 30d: reached 90% | 3 of 4 (75%, 90% range 36-94%), too few to read | 1 of 1 (100%) | did not hold out of sample (n = 1, too few to read) |
| Set A, 30d: run ended | 1 of 4 (25%, 90% range 6-64%), too few to read | 0 of 1 (0%) | did not hold out of sample (n = 1, too few to read) |
| Set A, 30d: BTC | +8.4% (+0.2% to +13.3%), n = 4, too few to read | -3.4%, n = 1 | did not hold out of sample (n = 1, too few to read) |
| Set A, 30d: typical alt | +0.9% (-6.3% to +4.8%), n = 4, too few to read | -1.8%, n = 1 | consistent (n = 1, too few to read) |
| Set A, 60d: reached 90% | 3 of 4 (75%, 90% range 36-94%), too few to read | 1 of 1 (100%) | did not hold out of sample (n = 1, too few to read) |
| Set A, 60d: run ended | 3 of 4 (75%, 90% range 36-94%), too few to read | 0 of 1 (0%) | did not hold out of sample (n = 1, too few to read) |
| Set A, 60d: BTC | +21.8% (-2.4% to +39.4%), n = 4, too few to read | -19.0%, n = 1 | did not hold out of sample (n = 1, too few to read) |
| Set A, 60d: typical alt | +0.2% (-29.4% to +1.4%), n = 4, too few to read | -19.4%, n = 1 | consistent (n = 1, too few to read) |
| Set B, 30d: reached 90% | 5 of 13 (38%, 90% range 20-61%) | 2 of 2 (100%) | did not hold out of sample (n = 2, too few to read) |
| Set B, 30d: run ended | 5 of 13 (38%, 90% range 20-61%) | 0 of 2 (0%) | did not hold out of sample (n = 2, too few to read) |
| Set B, 30d: BTC | +0.5% (-2.8% to +5.8%), n = 13 | +5.4%, n = 2 (+11.9%, -1.2%) | consistent (n = 2, too few to read) |
| Set B, 30d: typical alt | -3.9% (-9.1% to +4.0%), n = 13 | +8.5%, n = 2 (+21.8%, -4.8%) | did not hold out of sample (n = 2, too few to read) |
| Set B, 60d: reached 90% | 7 of 13 (54%, 90% range 32-74%) | 2 of 2 (100%) | did not hold out of sample (n = 2, too few to read) |
| Set B, 60d: run ended | 8 of 13 (62%, 90% range 39-80%) | 0 of 2 (0%) | did not hold out of sample (n = 2, too few to read) |
| Set B, 60d: BTC | -1.6% (-16.8% to +21.3%), n = 13 | -8.2%, n = 2 (-15.8%, -0.6%) | consistent (n = 2, too few to read) |
| Set B, 60d: typical alt | -4.6% (-29.4% to +5.1%), n = 13 | -18.0%, n = 2 (-20.3%, -15.7%) | consistent (n = 2, too few to read) |

Out-of-sample episodes behind the rows above:

- Set A: 2026-04-22 (85.9%, day 33 of the March run, BTC inside its band).
- Set B: 2026-04-11 (82.0%) and 2026-06-04 (89.6%), both from the March run.
- Band break while risk-on (3c): 2026-05-22 (94.4%). The run did not end within 60 days. The typical alt returned -18.5% over 30 days and -20.8% over 60.

**Reading the verdicts.** Every out-of-sample row has 1 or 2 cases, so every verdict carries "too few to read". Six months held:

- one full risk-on run and one risk-off run;
- one band break while risk-on;
- one set A episode and two set B episodes, all from the same run.

The check can neither confirm nor overturn any in-sample frequency. What it adds is one more case, at the edge of the in-sample range: the longest run in the record, and a band break 85 days before breadth's end. The in-sample lead row, 4 cases, was itself too few to read.

After this check, April to September 2026 is no longer a clean holdout for questions about breadth cycles.

## Where we are today

As of 2026-09-27, the API's latest day. The frequencies below pool the in-sample and out-of-sample data, from 2021-05-01 to 2026-09-25, and come from `python -m backtest.risk_on_cycles --sample all` at 590c45d. Pooled figures are description, not a test: the out-of-sample check above is the only test, and it was too small to read. They are market context, not a signal.

| | |
|---|---|
| Current risk-on run | began 2026-08-20; day 38 by the declared rule |
| Breadth | 82.1% in Uptrend (119 of 145 coins), bucket 80-90%. This run's peak so far is 82.1% (2026-09-26); it has not reached 85% |
| Percentile | higher than 77% of days since 2021-05-01 (as the drawer shows) |
| BTC against its band | 84,472. Sunday band (declared) 70,254-72,617: 16.3% above the upper edge and 20.2% above the lower. Wednesday band (drawer) 69,624-72,874: 15.9% and 21.3% above |
| BTC since the run began | reclaimed its band on 2026-08-19, the day before the run began; no band break since |
| Before this run | a 5-day risk-off run (2026-08-15 to 08-19), after the 148-day run from 2026-03-20 |

**The age caveat (exploratory).** On the 5 dip days, 78, 77, 77, 77 and 79 of 144 coins were in Uptrend; 55% needed 80. On its last day, 2026-08-19, the dip was one coin short of merging.

- With that coin, today would be day 191 of the run that began 2026-03-20. Breadth's lowest reading since 20 March was 53.5% (77 of 144 coins).
- No ended run in the record lasted 191 days; the longest is that same March run, at 148. So at 191 days the survival row has no runs at risk, and set A's 120+ day bucket has no comparable history.
- Everything below that uses today's age (day 38) depends on that one coin.

**How long runs lasted (pooled).** 12 ended risk-on runs: median 47 days (quartiles 11-101). 13 ended risk-off runs: median 67 days (26-156). The five longest risk-on runs lasted 148, 143, 119, 101 and 96 days.

| Of runs that lasted at least d days | In-sample | Pooled (in and out of sample) |
|---|---|---|
| 10: lasted 30 more | 6 of 9 (67%, 90% range 40-86%) | 7 of 10 (70%, 90% range 44-87%) |
| 20: lasted 30 more | 5 of 7 (71%, 90% range 41-90%) | 6 of 8 (75%, 90% range 46-91%) |
| 30: lasted 30 more | 4 of 7 (57%, 90% range 29-81%) | 5 of 8 (63%, 90% range 35-84%) |
| **38 (today): lasted 30 more** | 4 of 6 (67%, 90% range 35-88%) | **5 of 7 (71%, 90% range 41-90%)** |
| **38 (today): lasted 60 more** | 3 of 6 (50%, 90% range 22-78%) | **4 of 7 (57%, 90% range 29-81%)** |
| 45: lasted 30 more | 4 of 5, too few to read | 5 of 6 (83%, 90% range 50-96%) |
| 60, 90, 120: lasted 30 more | 4 of 4, 1 of 4, 0 of 1, too few to read | 5 of 5, 2 of 5, 0 of 2, too few to read |
| Ended runs at least as long as today's | 6 of 11 | 7 of 12 |

In each pooled row, the censored run (today's) is left out: its outcome is not known. No ended run had a length of exactly 38 days.

**Moments like today (pooled analogs).** Set A matches on breadth 80-90%, day 30-60 of a risk-on run and BTC holding its band. Set B matches on breadth 80-90% only. Windows had to close by 2026-09-25, so today's own run adds no outcome.

| Over the next 30 / 60 days | Set A (full match) | Set B (breadth only) | Set B, first episode of each run (exploratory) | All days (overlap) |
|---|---|---|---|---|
| Episodes | 5 / 5 (5 runs), too few to read | 15 / 15 (7 runs) | 7 / 7 | 1,940 / 1,910 days |
| Breadth reached 90% | 4 of 5 / 4 of 5 | 7 of 15 (47%, 90% range 28-67%) / 9 of 15 (60%, 39-78%) | 4 of 7 (57%, 29-81%) / 5 of 7 (71%, 41-90%) | 23% / 33% |
| Run ended | 1 of 5 / 3 of 5 | 5 of 15 (33%, 17-54%) / 8 of 15 (53%, 33-72%) | 1 of 7 (14%, 3-45%) / 2 of 7 (29%, 10-59%) | 18% / 33% |
| BTC, median (quartiles) | +3.5% (+0.2 to +13.3) / +4.2% (-2.4 to +39.4) | +0.5% (-2.8 to +5.8) / -1.6% (-16.8 to +15.4) | +5.8% (-5.2 to +10.6) / -1.6% (-16.8 to +21.3) | +0.6% / +1.5% |
| Typical alt, median (quartiles) | -1.8% (-2.9 to +4.8) / -1.0% (-19.4 to +1.4) | -3.9% (-9.1 to +4.0) / -13.8% (-29.4 to +3.9) | -1.8% (-3.9 to +14.6) / -4.6% (-20.3 to +3.9) | -6.8% / -12.4% |

- Set B's 15 episodes come from 7 runs, and its "run ended within 60 days" count of 8 holds only 6 distinct run ends. Its 90% ranges treat the episodes as independent, so they understate the uncertainty. The one-per-run column shows how much the unit matters.
- Set A has 5 episodes from 5 runs, too few to read: 2023-02-12, 2023-12-05, 2024-10-25, 2025-08-29 and 2026-04-22.
- Breadth touching 90% and the run ending often fell in the same 60-day window. Peaks came early (median day 16, in-sample) and then faded.

**BTC's band and breadth (pooled days).** With BTC above its band, breadth was 55% or more on 486 of 985 days. With BTC below, it was 55% or more on 311 of 907 days, against 204 of 794 in-sample. Most of the difference is 2026's run, which spent 85 days risk-on with BTC below its band.

**Where in the waves.** The record since 2025:

| Wave | Dates | Days | Breadth | BTC and its band |
|---|---|---:|---|---|
| Risk-on | 2025-07-11 to 2025-10-15 | 96 | peak 98.2% | broke its band 4 days before the end |
| Risk-off | 2025-10-15 to 2026-03-20 | 156 | low 4.7% | below its band at the end |
| Risk-on | 2026-03-20 to 2026-08-15 | 148 | peak 95.8% (May) | broke its band on 22 May; breadth faded over the next 85 days |
| Risk-off | 2026-08-15 to 2026-08-20 | 5 | low 53.5% | reclaimed its band on 19 August |
| Risk-on (today) | since 2026-08-20 | 38 so far | 82.1% | 16% above its band |

There are two ways to read today:

- **By the declared rule,** today is day 38 of a new run that began as BTC reclaimed its band.
- **Without the one-coin dip,** today is day 191 of a run that began on 20 March, longer than any run in the record, with breadth above 53% throughout.

The study uses the declared rule. The survival rows and set A above hold only under it.

### Summary for the owner (market context, not a signal)

- **Where we are.** Breadth is risk-on at 82% (119 of 145 coins), on day 38 of a run that began on 2026-08-20. That was the day after BTC reclaimed its weekly bull market support band. BTC is now 16% above the band's upper edge and has not broken it since. "Day 38" hangs on one coin: a 5-day dip in mid-August missed 55% by one coin on its last day. Counted without that dip, today is day 191 of a run that began on 20 March, longer than any run in the record, with breadth above 53% throughout.
- **How long runs lasted.** Across the 12 ended risk-on runs since 2021, the median lasted 47 days (quartiles 11-101). Of the 7 that reached 38 days, 5 lasted at least 30 more and 4 at least 60 more (90% ranges 41-90% and 29-81%). The 4 short runs (6-19 days) peaked at 58-71%. Every run that reached 85% lasted 53 days or more.
- **Grinding toward 100%, or rolling over.** After readings of 80-90%, breadth touched 90% within 60 days in 9 of 15 past episodes. The run ended within 60 days in 8 of 15. Both often happened in the same window, because peaks came early and then faded. The 15 episodes come from only 7 runs. Counting one per run, 5 of 7 touched 90% and 2 of 7 ended within 60 days. So the record gives a wide range, not a number.
- **BTC's band.** In-sample, breadth's run ended 4-15 days after a BTC band break in 3 of 11 runs, and 4 of 11 ended with no band break within 60 days. 2026 was the outlier. BTC broke its band on 22 May with breadth at 94% and stayed below it for almost three months. Breadth took 85 days to roll over, and the typical alt fell 32% from the May peak to the run's end. BTC being above its band at a run's start did not separate long runs from short ones.
- **What the out-of-sample check says.** April to September 2026 added one full risk-on run (148 days, peak 95.8%), one 5-day risk-off run and three analog episodes, all from that run. Every out-of-sample verdict rests on 1 or 2 cases, too few to read, so the check neither confirms nor overturns the in-sample frequencies. The record holds about two market cycles plus 2026, and 12 ended risk-on runs. These are counts of what happened, not odds.
