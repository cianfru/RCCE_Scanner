# The top divergence as an exit: does it help the engine? (declared 9 November 2026, before running)

The owner's go-ahead (9 November 2026), after the band-model marks study: "yes" to testing the top divergence as a trim or exit in the engine, first of the improvements proposed.

## Why this exit

- The engine's value is in when to be out, not in its entries: its long entries earn about the market's own move (`docs/reviews/entry-quality-study.md`).
- Its only working exit near tops is heat (≥ 95 above the band). The z-score's trims never fire, because Overheated never wins (`docs/reviews/overheated-regime.md`). The band-z exit lost 14 to 19 points of return (`docs/reviews/band-exit-study.md`).
- The top divergence of the TradingView band model was the clearest mark in `docs/reviews/band-model-marks-study.md`. On 36 coins the close 90 days after it was lower 68.1% of the time, against 46.0% for ordinary days on the same coins and eras (median −23.1% against +5.8%), in every part of the data.
- That study measured the coin's price, not the engine's trades. This study asks whether exiting on it improves the engine's results.

## Variants

- **C:** today's live logic.
- **D30:** C with `signal_synthesizer.DIV_EXIT` on and a 30-day window. A row is **TRIM** (out, and no new long) while a top divergence happened on the coin within the last 30 completed days. 30 days is the script's gap between marks.
- **D90:** the same with a 90-day window, the marks study's horizon.

Nothing else changes: the heat exit, entries, the macro block and the position manager. In the replay, TRIM closes the whole position (`backtest/position_manager.py`).

**The top divergence at a bar** (`backtest/live_logic_replay._div_exit`, tests in `tests/test_band_marks.py` and `tests/test_signal_reliability.py`):
- The band model's rules (`research/band_marks.model`, the script's default settings, checked line by line against a plain rewrite) on Binance spot daily candles from 1 January 2017.
- The data runs to the end of window 9; each day's mark uses data up to that day only.
- A mark on day d counts for bars from the close of day d: the bar whose close is d's close and later. That is the last completed day for both 4H and daily rows.
- The window covers days d to d + window − 1 as the last completed day.

## Harness (windows 1–9 only, ending 29 March 2026; the holdout is never replayed)

The same harness as the band-exit, overheated-regime and z-baseline studies: `backend/backtest/live_logic_replay.py` (new switch `--divexit 30|90`), then `backend/backtest/live_logic_check.py`. It uses Binance history, the costed PositionManager (10 bps a side all in) and the BTC weekly-band entry block.

Runs, D30 and D90 each, against C:
1. **Deciding:** the 10 primary coins (BTC ETH SOL BNB XRP ADA AVAX DOGE DOT LINK), 4H. C is re-run here to confirm the harness.
2. **Guard:** the 30 secondary coins, 4H.
3. **Reported:** both coin sets on 1D.

On runs 2 and 3, C is the band-exit study's run of 7 November 2026, with the same code. No engine, synthesizer or replay file has changed since, apart from the switch added here, which is off for C.

## Decision rule (fixed now)

A variant ships (the switch is turned on, after the owner approves) only if all three hold:
1. on the deciding run, the compounded return over windows 1–9 is at least **5 points above** C's;
2. on the deciding run, the worst-window drawdown is no more than **1 point deeper** than C's;
3. on the guard run, the compounded return is no more than **5 points below** C's.

If both D30 and D90 pass, the one with the higher deciding return ships; a tie, D30. If neither passes, nothing ships: the switch stays off and the result reads context, not a signal. The 1D runs are reported in full and do not change the verdict.

Reported per run: compounded return, per-window returns, worst-window drawdown, median Sharpe, trades and TRIM bars.

## Known before running

- **C's results are published:**
  - primary 4H: +43.1%, worst window −10.4%, 314 trades;
  - secondary 4H: +45.3%, −14.6%, 725 trades;
  - primary 1D: +36.5%, −13.9%;
  - secondary 1D: +4.9%, −20.0%.
- **D30 and D90 have never been run.** No trade outcome around a top divergence has been looked at.
- **The marks' price outcomes are known** from the marks study:
  - On ETH, BTC and SOL every mark and its 90-day move were listed there. Three primary coins, so the deciding run is not blind to them.
  - That study's 36 coins include the other 7 primary coins (BNB XRP ADA AVAX DOGE DOT LINK) and 29 of the 30 secondary coins (all but FTT), over the same years as the windows.
- **Data check** (no outcome): top divergences inside windows 1–9: **17 on the primary coins** and **13 on the secondary coins**.
  - BTC 6: 6 Nov 2024, 13 Dec 2024, 21 Jan 2025, 18 May 2025, 10 Jul 2025, 5 Oct 2025.
  - SOL 4: 22 Oct 2021, 29 Feb 2024, 10 Nov 2024, 18 Jan 2025.
  - BNB 2: 4 Jun 2024, 3 Dec 2024.
  - One each: ETH 25 Oct 2021, XRP 17 Jul 2025, ADA 1 Mar 2024, AVAX 11 Mar 2024, LINK 1 Feb 2024.
  - DOGE and DOT: none.

  With so few marks, the exit can only move results where the engine holds a coin near one.

## Limits

- 17 and 13 marks: a small test. A pass rests on a handful of exits.
- The windows are 2021–2026; the holdout stays unread.
- The marks come from Binance spot daily candles; live Reflex trades Hyperliquid perps. If a variant ships, the live engine needs the mark from its own daily candles; that is a separate change for the owner to approve.
- A replay tests the rule on one path of history, with this manager's sizing and exits.
