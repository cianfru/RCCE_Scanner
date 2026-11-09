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

## Results (windows 1–9, costed PositionManager, run 9 November 2026, after the declaration was committed)

| Run | | Compounded return | Worst window | Median Sharpe | Trades | TRIM bars |
|---|---|---:|---:|---:|---:|---:|
| **Primary 4H (deciding)** | C | **+43.1%** | −10.4% | 0.32 | 314 | 4,036 |
| | D30 | **+44.3%** (+1.2) | −9.4% (+1.0) | 0.10 | 305 | 8,301 |
| | D90 | **+52.3%** (+9.2) | −8.4% (+2.0) | 0.71 | 273 | 16,351 |
| **Secondary 4H (guard)** | C | **+45.3%** | −14.6% | −0.80 | 725 | 8,975 |
| | D30 | **+41.9%** (−3.4) | −14.6% (0.0) | −0.80 | 720 | 14,445 |
| | D90 | **+42.9%** (−2.4) | −14.7% (−0.1) | −0.80 | 681 | 25,669 |
| Primary 1D (reported) | C | +36.5% | −13.9% | −0.30 | 138 | 617 |
| | D30 | +43.5% (+7.0) | −12.9% (+1.0) | −0.30 | 141 | 1,393 |
| | D90 | +47.6% (+11.1) | −12.2% (+1.7) | −0.30 | 125 | 2,772 |
| Secondary 1D (reported) | C | +4.9% | −20.0% | −0.42 | 398 | 1,384 |
| | D30 | +1.0% (−3.9) | −20.2% (−0.2) | −0.42 | 399 | 2,350 |
| | D90 | +5.5% (+0.6) | −20.4% (−0.4) | −0.42 | 365 | 4,339 |

Per-window returns, C / D30 / D90 (%):

| Run | W1 | W2 | W3 | W4 | W5 | W6 | W7 | W8 | W9 |
|---|---|---|---|---|---|---|---|---|---|
| Primary 4H | +1.2 / +0.2 / +2.6 | 0 / 0 / 0 | +5.0 / +5.0 / +5.0 | −1.9 / −1.9 / −1.9 | +35.6 / +35.1 / +35.5 | −9.9 / −9.4 / −7.2 | +11.8 / +11.8 / +11.9 | +6.4 / +7.2 / +7.2 | −5.6 / −4.8 / −4.6 |
| Secondary 4H | −3.8 / −3.8 / −3.5 | 0 / 0 / 0 | +2.7 / +2.7 / +2.7 | −2.6 / −2.6 / −2.6 | +40.9 / +37.8 / +35.8 | −8.5 / −8.4 / −6.5 | +24.4 / +24.1 / +23.9 | −3.6 / −3.6 / −3.6 | −2.3 / −2.3 / −2.3 |
| Primary 1D | −8.8 / −7.8 / −5.8 | 0 / 0 / 0 | −1.9 / −1.9 / −1.9 | −5.9 / −5.9 / −5.9 | +50.2 / +51.5 / +51.5 | −4.0 / −4.0 / −4.0 | +14.8 / +16.4 / +15.5 | +9.1 / +9.8 / +10.7 | −10.1 / −9.2 / −8.7 |
| Secondary 1D | −17.0 / −17.0 / −12.2 | 0 / 0 / 0 | +0.7 / +0.7 / +0.7 | −0.5 / −0.5 / −0.5 | +36.0 / +32.2 / +32.4 | −2.7 / −2.7 / −2.3 | +6.7 / +5.7 / +3.9 | −7.9 / −7.9 / −7.9 | −3.0 / −3.0 / −3.0 |

**Harness checks.**
- C re-run on primary 4H with today's code gives the 7 November run exactly (+43.1%, −10.4%, 314 trades).
- On the other runs C is the 7 November run. The Strong long study re-ran it on primary 1D with today's code, and it is identical too (+36.5%, −13.9%, 138 trades).

## Verdict: D90 passes all three conditions. It is the variant to ship, after the owner approves.

| Condition | D30 | D90 |
|---|---|---|
| 1. Deciding run at least 5 points above C | **fails** (+1.2) | holds (+9.2) |
| 2. Deciding worst window no more than 1 point deeper | holds (1.0 shallower) | holds (2.0 shallower) |
| 3. Guard run no more than 5 points below C | holds (−3.4) | holds (−2.4) |

- **What shipping takes.** Turning the switch on live needs the top divergence computed from the live engine's own daily candles: today nothing live sets `top_div_window`. That is a separate change, made only with the owner's approval.
- **Until then:** the switch stays off (`DIV_EXIT = False`); live and paper trading are unchanged.

## Reading

- **Where the gain comes from.**
  - It is spread over four windows of the deciding run: W1 +1.3, W6 +2.7, W8 +0.9, W9 +0.9 points; the others move by less than 0.2.
  - It is not carried by the coins whose marks were seen. Summed P&L per window's starting capital, D90 minus C:
    - BTC +0.2, ETH +0.8, SOL −2.9: −1.9 together;
    - the other seven +7.7, mostly BNB +2.9, ADA +1.8 and XRP +1.7; DOGE and DOT unchanged (no marks).
- **What it costs.**
  - On the guard run D90 gives up 5.1 points in W5 (October 2023 to April 2024), the rally window, and gets back 2.0 in W6.
  - FET is −2.3 of it, then QTUM −0.8 and BCH −0.8: exits in trends that kept going, the band-exit study's lesson again.
  - The guard's −2.4 is within the declared 5.
- **The exit holds a coin out for 90 days after a mark.**
  - TRIM bars go from 4,036 to 16,351 on the deciding run, and trades from 314 to 273.
  - Stops and decay exits fall (123 to 100, and 167 to 143): fewer re-entries after a top.
- **The daily runs agree in direction on the primary coins** (+11.1 points, worst window 1.7 shallower). On the secondary coins they are about level (+0.6 points, worst window 0.4 deeper).
- **A small base.** 17 marks decide the primary runs and 13 the secondary runs. The pass rests on a handful of exits. Live, it should be watched as a new rule, not taken as proven.

## The live mark (built 9 November 2026; the switch stays off)

The owner's go-ahead (9 November 2026): "yes" to building the live mark before deciding on the switch.

**How it is computed** (`backend/band_marks_live.py`, tests `backend/tests/test_band_marks_live.py`):
- The market-history job runs once a day, 18 minutes after the daily close. It now also computes the band model's marks for its 151 coins with the studies' own code (`research/band_marks.model`).
- **Same data as the study:** Binance USDT spot daily candles, completed days only. About 2,000 days per coin (two pages of 1,000).
  - That is enough for every input of a recent day to match a computation on the full history.
  - Checked on 8 coins at 158 end days: every top divergence and capitulation turn of the last 120 days is the same.
- **Recorded:** each coin's marks of the last 120 days (`band_mark_events`) and the day they were computed (`band_mark_coverage`).
- **Read by the scanner:** each row gets `top_div_window`, true when the coin had a top divergence within the last 90 completed days. The engine acts on it only when `signal_synthesizer.DIV_EXIT` is on.
- **Capitulation turns are recorded too.** The layers study's candidate (a capitulation turn while the market's median z is in its high half) can then be looked at with the market history's daily median z. Nothing reads them yet.

**Coverage and timing.**
- 146 of the scanner's 212 coins on 9 November map to one of the 151 pairs. Hyperliquid's per-1,000 markets (KPEPE) take the token's pair; the marks do not depend on the price's unit.
- On the other 66 coins the exit never fires.
- A day's mark is known once the job has run, about 18 minutes after the close. In the replay, it counted from the close.

**What it would do on 9 November 2026** (last completed day 8 November):
- **One coin is inside its window:** ZEC, top divergence on 21 August 2026, day 80 of 90.
- ZEC is Light long on 4H and Strong long on the daily chart. With the switch on, it would be Trim on both for 10 more days.
- No other covered coin had a top divergence in the last 120 days.

**Cost:** about 0.15 to 0.45 seconds of CPU per coin once a day, 5 MB at most per coin while it runs, with at most 6 coins' older pages held at once. The extra Binance requests are ingress, which is free.

## Shipped (9 November 2026)

The owner approved turning it on ("Merge it yes. Clear improvements"), after the check of the capped engine with this exit (KD in `docs/reviews/strong-long-replay-study.md`).
- `signal_synthesizer.DIV_EXIT = True`, with the 90-day window computed by `band_marks_live.py`.
- The replay harness keeps it off unless run with `--divexit`, so earlier runs reproduce.
