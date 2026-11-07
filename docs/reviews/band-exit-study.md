# The exit above the weekly band: heat or band z? (declared 7 November 2026, before running)

The owner's request (7 November 2026), after the stretch-at-tops study: should the engine use the band stretch for tops? The plan agreed was to change only the top side and leave entries as they are, replayed on the usual harness with return and drawdown bars fixed beforehand, and nothing changed in live or paper trading until the owner has seen the results and approved.

## What the engine does at tops today (checked before this declaration)

- **The z-score's exits never fire.** The Overheated (BLOWOFF) phase never wins: MARKUP's weight beats it at every z (`docs/reviews/overheated-regime.md`). So TRIM and TRIM_HARD on z, which run only inside BLOWOFF, are dead, and so is the EUPHORIA rule, which needs coins in BLOWOFF. That study's fix to make BLOWOFF fire cost 7.9 to 12.9 points of return and did not ship.
- **The only exit at tops is heat** (`signal_synthesizer.py`, rule 1a). It fires TRIM when heat ≥ 95 (85 in BLOWOFF, 100 in CAP and ACCUM). Heat is the distance from the weekly band mid in units of weekly ATR (`engines/heatmap_engine.py`), capped at 100. The same rule acts as a crash exit far below the band.
- In the replay, TRIM closes the whole position (`backtest/position_manager.py`).

So "use the band stretch for tops" means one thing in today's engine: **the exit above the band on band z instead of heat.** The stretch-at-tops study compared band z with the engine's z, not with heat; which of the two marks a better exit is open.

## Variants

- **C:** today's live logic.
- **V:** C with `signal_synthesizer.TOP_EXIT = "band"`. Above the band (heat direction not negative), outside CAP and ACCUM, and where band z is known, the exit is **band z ≥ 1.61**, the stretch-at-tops study's guide, instead of heat ≥ the force-trim level. Below the band, in CAP and ACCUM, and wherever band z is unknown, the heat rule is unchanged. Nothing else changes: entries, heat's entry block (heat < 85), the macro block, the position manager.

The switch is in the engine, off (`TOP_EXIT = "heat"`), with tests (`tests/test_signal_reliability.py`).

**Band z at a bar** (`band_stretch.bar_state` / `band_z_at`, tests in `tests/test_band_stretch.py`):
- Binance daily closes from 1 January 2017 (completed days before the bar's day only).
- The bar's own close stands for the day's close so far.
- The band is the 20-week SMA and 21-week EMA of weekly closes, with Thursday weeks and the week under way at the bar's close; its mid is their average.
- Band z is the log of the bar's close over the mid, divided by the root mean square of the daily stretch over the 730 completed days before the bar's day.
- It is unknown until the band exists and 180 days of stretch are there.
- The replay gives each row its band z just before synthesis (`backtest/replay_engine.BAR_HOOK`): 4H rows at their bar's close, daily rows at their last completed day.

## Harness (windows 1-9 only, ending 29 March 2026; the holdout is never replayed)

`backend/backtest/live_logic_replay.py` (new switch `--topexit band`), then `backend/backtest/live_logic_check.py`. This is the same harness as the overheated-regime and z-baseline studies: Binance history, the costed PositionManager (10 bps a side all in), and the BTC weekly-band entry block.

Runs, C and V each:
1. **Deciding:** the 10 primary coins (BTC ETH SOL BNB XRP ADA AVAX DOGE DOT LINK), 4H.
2. **Guard:** the 30 secondary coins, 4H. The list is recreated with `python -m backtest.larsson_scenarios select-secondary`; it matches the earlier studies' list exactly.
3. **Reported:** both coin sets on 1D (`--tf 1d`).

## Decision rule (fixed now)

V ships (the switch is turned on, after the owner approves) only if all three hold:
1. on the deciding run, the compounded return over windows 1-9 is at least **5 points above** C's;
2. on the deciding run, the worst-window drawdown is no more than **1 point deeper** than C's;
3. on the guard run, the compounded return is no more than **5 points below** C's.

Otherwise nothing ships: the switch stays off, and the result reads context, not a signal. The 1D runs are reported in full and do not change the verdict.

Reported per run: compounded return, per-window returns, worst-window drawdown, median Sharpe, trades, TRIM bars, regime and signal mix.

## Known before running

- **C's results are published:**
  - primary 4H: +43.1%, worst window −10.4%, 314 trades;
  - secondary 4H: +45.3%, −14.6%, 725 trades;
  - primary 1D: +36.6%, −14.0%;
  - secondary 1D: +4.9%, −20.0%.

  C is re-run here with the same code to confirm the harness; any difference is reported.
- **V has never been run, on any coin.**
- **The 1.61 guide** was set in the stretch-at-tops study on Binance daily closes from 2019 to October 2026. That study's calibration coins include 4 of the primary coins (ADA DOGE SOL XRP) and 15 of the secondary coins, over the same years as the windows. The level is fixed here without any trading outcome, but it is not independent of these coins' price histories.
- **Data check** (no outcome): band z is defined from the first window on for all 10 primary and all 30 secondary coins.

## Limits

- The windows are 2021-2026; the holdout stays unread.
- The replay's daily rows read the last completed day; live, the scanner reads the latest bar.
- Band z here comes from Binance spot closes, while live Reflex trades Hyperliquid perps. If V ships, the live engine needs band z from its own daily candles; that is a separate change for the owner to approve.
- A replay tests the rule on one path of history, with this manager's sizing and exits.

## Results (windows 1-9, costed PositionManager, run 7 November 2026, after the declaration was committed)

| Run | | Compounded return | Worst window | Median Sharpe | Trades | TRIM bars |
|---|---|---:|---:|---:|---:|---:|
| **Primary 4H (deciding)** | C | **+43.1%** | −10.4% | 0.32 | 314 | 4,036 |
| | V | **+23.8%** (−19.4) | −10.5% (−0.1) | 0.23 | 334 | 6,743 |
| **Secondary 4H (guard)** | C | **+45.3%** | −14.6% | −0.80 | 725 | 8,975 |
| | V | **+30.9%** (−14.4) | −9.7% (+4.9) | −0.56 | 820 | 17,776 |
| Primary 1D (reported) | C | +36.5% | −13.9% | −0.30 | 138 | 617 |
| | V | +22.6% (−13.9) | −12.4% (+1.5) | −0.30 | 170 | 1,196 |
| Secondary 1D (reported) | C | +4.9% | −20.0% | −0.42 | 398 | 1,384 |
| | V | +4.4% (−0.5) | −18.0% (+2.0) | −0.38 | 518 | 2,989 |

Per-window returns, C / V (%):

| Run | W1 | W2 | W3 | W4 | W5 | W6 | W7 | W8 | W9 |
|---|---|---|---|---|---|---|---|---|---|
| Primary 4H | +1.2 / +1.6 | 0 / 0 | +5.0 / +5.0 | −1.9 / −0.8 | +35.6 / +28.6 | −9.9 / −9.9 | +11.8 / +1.1 | +6.4 / +6.7 | −5.6 / −6.4 |
| Secondary 4H | −3.8 / −2.5 | 0 / 0 | +2.7 / +3.0 | −2.6 / −3.2 | +40.9 / +41.9 | −8.5 / −8.2 | +24.4 / +8.6 | −3.6 / −2.7 | −2.3 / −2.3 |
| Primary 1D | −8.8 / −8.8 | 0 / 0 | −1.9 / −1.9 | −5.9 / −5.9 | +50.2 / +37.0 | −4.0 / −3.4 | +14.8 / +11.0 | +9.1 / +9.0 | −10.1 / −9.2 |
| Secondary 1D | −17.0 / −16.3 | 0 / 0 | +0.7 / +0.6 | −0.5 / −0.4 | +36.0 / +34.2 | −2.7 / −2.8 | +6.7 / +5.9 | −7.9 / −7.1 | −3.0 / −3.0 |

C reproduces the published runs on primary 4H, secondary 4H and secondary 1D exactly. Primary 1D reads +36.5% / −13.9% / 138 trades against the published +36.6% / −14.0% / 138; the difference is reported, not explained, and moves no verdict.

## Verdict: nothing ships. Context, not a signal.

- **Condition 1 fails:** on the deciding run V returns 19.4 points less than C; the bar was 5 points more.
- Condition 2 holds: the worst window is 0.1 points deeper, within 1.
- **Condition 3 fails:** on the guard run V returns 14.4 points less than C; the limit was 5.

The switch stays off (`TOP_EXIT = "heat"`); live and paper trading are unchanged.

## Reading

- **Band z exits about twice as often as heat** (TRIM bars 1.7 to 2.2 times C's) and gives up return in every run, most of it in the two rally windows: W5 (October 2023 to April 2024) and W7 (October 2024 to April 2025). The 4H runs lose 7.0 and 10.7 points there (primary), 15.8 in W7 (secondary).
- **It does soften the worst window** in three runs of four (by 1.5 to 4.9 points), but not by enough to pay for the return it gives up.
- **Why:** band z at 1.61 is each coin's top 5% of stretch. The stretch-at-tops study found that about 4 in 10 of its alarm episodes did not end at a top. As an exit, those are the trends that kept going. Heat at 95 (about 7.6 weekly ATRs from the band) lets a strong trend run further. This repeats the overheated-regime study's lesson: an earlier exit at tops cuts winners in trends that are not over.
- **Band z stays useful as a reading of how stretched a coin and the market are** (the coin page and the Market page's share of stretched coins). Whether a stricter band z (a higher level, or band z with the divergence mark) would beat heat as an exit is a new hypothesis. It needs its own declared study, judged on windows other than these.
