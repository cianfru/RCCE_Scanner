# Strong long in the replay: the live engine's top entry, tested for the first time (declared 9 November 2026, before running)

The owner's go-ahead (9 November 2026): "yes" to the second improvement proposed, letting the backtests see funding so Strong long can be tested.

## Why

- **Live, the engine gives Strong long.** On 9 November 2026 at 4H, 8 of 208 coins showed it.
- **No backtest has ever produced it.** The replay passes only consensus and Fear & Greed, so two of the nine core checks are always unknown:
  - "Funding OK" (not crowded long);
  - "Liquidity" (stablecoins not contracting).

  An unknown core check adds the blocker "core context unavailable", which caps Strong long at Light long (`signal_synthesizer.py`; `docs/reviews/entry-quality-study.md`).
- **So every engine study so far tested an engine without its top entry.** Strong long is sized at twice Light long in the position manager.
- Live there is no CoinGlass data: no coin has the CoinGlass conditions. Funding was known on 179 of the 208 coins; stablecoins on all of them.

## Variants

- **C:** today's harness. Strong long cannot fire.
- **S:** C plus the two live inputs, rebuilt from history (`backend/backtest/live_context.py`, `--context live`; tests `backend/tests/test_live_context.py`):
  - **Funding.** Live reads Binance's rate first and divides it by 8 to get an hourly rate; crowded long is above +0.0001 an hour.

    Here: the last settled payment of the coin's Binance USDT-M perpetual at or before the bar's close (public archives), divided by 8 the same way. It counts as missing when older than 16 hours.

    Open interest, top traders' long/short, CVD and HyperLens stay unavailable. They are not core checks, and live has no CoinGlass either.
  - **Stablecoins.** Live compares USDT + USDC supply now with a week ago (DefiLlama): expanding above +1%, contracting below −1%.

    Here: DefiLlama's daily history, the last completed day against the day 7 before it.

Both inputs are passed with the bar's close as their observation time, so the decision's freshness checks keep them, as they would live. Nothing else changes.

## Harness (windows 1–9 only, ending 29 March 2026; the holdout is never replayed)

`backend/backtest/live_logic_replay.py --context live`, then `backend/backtest/live_logic_check.py`. This is the harness of the band-exit and top-divergence studies.

Runs, S against C:
1. **Deciding:** the 10 primary coins, 4H.
2. **Guard:** the 30 secondary coins, 4H.
3. **Reported:** both coin sets on 1D.

C is the band-exit study's run of 7 November 2026. The replay engine gained a hook for this study that does nothing when off. To check that, C is re-run on the primary 1D chart with today's code and compared with 7 November (+36.5%).

## Decision rule (fixed now)

- **Strong long hurts:** on the deciding run, S's compounded return is at least **5 points below** C's, and on the guard run S is below C.

  The recommendation to the owner is then to cap Strong long at Light long live. That is a signal change, made only with the owner's approval.
- **Strong long holds:** on the deciding run, S's return is at least **5 points above** C's, with a worst-window drawdown no more than **2 points deeper**. On the guard run, S is no more than **5 points below** C.

  The live engine's top entry then has backtest support. S becomes the harness's default for later engine studies, with C reported beside it.
- **Otherwise:** no change. S is reported, and the harness keeps C as its default.

The 1D runs are reported and do not change the verdict.

Reported per run:
- compounded return, per-window returns, worst-window drawdown, median Sharpe, trades;
- bars and entries by signal, including how many Strong long entries there were and how the trades opened by each kind of entry did.

## Known before running

- **C's results are published:**
  - primary 4H +43.1% (−10.4%, 314 trades);
  - secondary 4H +45.3% (−14.6%, 725 trades);
  - primary 1D +36.5% (−13.9%);
  - secondary 1D +4.9% (−20.0%).
- **S has never been run.** An estimate from C's own bars (signals and checks only, no outcome) suggests many bars could change:
  - about 5,500 Light long bars in Uptrend with 0 < z < 1 and most checks met;
  - about 3,300 Accumulation bars above the band that end as Wait.
- **Data check** (no outcome), windows 1–9:
  - **Funding** is known on every day for all 10 primary coins. On the secondary coins it is known on every day for 24 of 30; the rest are FTM 83%, OMG 83%, FTT 72%, FET 72%, BTT 6%, WIN 0%.
  - **Crowded long is rare:** 0% to 0.25% of days on the primary coins, at most 1% on the secondary coins. So "Funding OK" almost always passes. This study mostly measures **Strong long becoming reachable**, not funding as a filter.
  - **Stablecoins** read stable on 1,191 days, expanding on 364 and contracting on 65.

## Limits

- Settled Binance funding, not the live real-time estimate. Hyperliquid's own funding, used live for coins not on Binance, is not rebuilt.
- The HyperLens checks live (up to 1 point of a 10 or 11 total) cannot be rebuilt, so Strong long's score is out of 9 here, as live for coins without HyperLens data.
- The windows are 2021–2026; the holdout stays unread. A replay tests the rule on one path of history, with this manager's sizing and exits.

## Results (windows 1–9, costed PositionManager, run 9 November 2026, after the declaration was committed)

| Run | | Compounded return | Worst window | Median Sharpe | Trades |
|---|---|---:|---:|---:|---:|
| **Primary 4H (deciding)** | C | **+43.1%** | −10.4% | 0.32 | 314 |
| | S | **+34.8%** (−8.4) | −17.5% (−7.2) | 0.00 | 373 |
| **Secondary 4H (guard)** | C | **+45.3%** | −14.6% | −0.80 | 725 |
| | S | **+30.2%** (−15.1) | −19.6% (−5.0) | −1.15 | 787 |
| Primary 1D (reported) | C | +36.5% | −13.9% | −0.30 | 138 |
| | S | +50.2% (+13.7) | −21.4% (−7.4) | −0.43 | 174 |
| Secondary 1D (reported) | C | +4.9% | −20.0% | −0.42 | 398 |
| | S | −4.9% (−9.8) | −30.4% (−10.4) | −0.88 | 448 |

Per-window returns, C / S (%):

| Run | W1 | W2 | W3 | W4 | W5 | W6 | W7 | W8 | W9 |
|---|---|---|---|---|---|---|---|---|---|
| Primary 4H | +1.2 / −7.7 | 0 / 0 | +5.0 / +0.7 | −1.9 / −5.1 | +35.6 / +65.8 | −9.9 / −15.3 | +11.8 / +23.4 | +6.4 / +0.8 | −5.6 / −12.6 |
| Secondary 4H | −3.8 / −12.4 | 0 / 0 | +2.7 / −0.2 | −2.6 / −4.9 | +40.9 / +60.6 | −8.5 / −11.2 | +24.4 / +22.9 | −3.6 / −7.1 | −2.3 / −3.9 |
| Primary 1D | −8.8 / −13.9 | 0 / 0 | −1.9 / −4.1 | −5.9 / −14.5 | +50.2 / +93.8 | −4.0 / −8.3 | +14.8 / +20.5 | +9.1 / +18.8 | −10.1 / −16.5 |
| Secondary 1D | −17.0 / −20.4 | 0 / 0 | +0.7 / −0.5 | −0.5 / −6.2 | +36.0 / +56.9 | −2.7 / −9.1 | +6.7 / +2.0 | −7.9 / −8.0 | −3.0 / −4.3 |

Bars by signal, C → S:

| Run | Strong long | Light long | Accumulate | Wait | Trim |
|---|---:|---:|---:|---:|---:|
| Primary 4H | 0 → 9,581 | 16,800 → 14,400 | 2,381 → 2,687 | 90,912 → 83,425 | 4,036 → 4,036 |
| Secondary 4H | 0 → 20,410 | 39,131 → 33,731 | 6,349 → 6,684 | 267,119 → 251,833 | 8,975 → 8,975 |
| Primary 1D | 0 → 2,387 | 3,609 → 2,820 | 416 → 426 | 14,704 → 13,096 | 617 → 617 |
| Secondary 1D | 0 → 5,343 | 9,599 → 7,780 | 756 → 727 | 44,933 → 41,438 | 1,384 → 1,384 |

Trades by the signal that opened them (`backtest/live_logic_trades.py`). P&L is summed as % of a window's starting capital; the median trade is the price move from entry to exit.

| Run | | Opened by | Trades | Wins | Summed P&L | Median trade |
|---|---|---|---:|---:|---:|---:|
| Primary 4H | C | Light long | 314 | 132 | +44.3% | −3.5% |
| | S | Light long | 209 | 100 | +53.4% | −1.2% |
| | S | **Strong long** | **164** | 47 | **−0.8%** | **−8.1%** |
| Secondary 4H | C | Light long | 725 | 251 | +48.3% | −8.0% |
| | S | Light long | 447 | 155 | +37.6% | −8.0% |
| | S | **Strong long** | **340** | 84 | **+8.0%** | **−8.3%** |
| Primary 1D | C | Light long | 138 | 43 | +44.0% | −8.6% |
| | S | Light long | 93 | 27 | +20.0% | −8.6% |
| | S | **Strong long** | **81** | 19 | **+57.2%** | **−8.4%** |
| Secondary 1D | C | Light long | 398 | 82 | +12.9% | −9.6% |
| | S | Light long | 266 | 57 | +36.0% | −9.5% |
| | S | **Strong long** | **182** | 25 | **−24.6%** | **−9.3%** |

**Harness check.** C re-run on primary 1D with today's code (hook off) gives +36.5%, −13.9%, 138 trades and the same per-window returns as the 7 November run. The hook changes nothing when off.

## Verdict: Strong long hurts

- **On the deciding run** S returns 8.4 points less than C; the bar was at least 5 less.
- **On the guard run** S is below C, by 15.1 points.
- **Its worst window is deeper in every run:** by 5.0 to 10.4 points.

**The declared recommendation:** cap Strong long at Light long live. That is a signal change, made only with the owner's approval. Until then nothing changes live; the harness keeps C as its default.

## Reading

- **What S changes.** Knowing funding and stablecoins does two things at once:
  - **Strong long becomes reachable.** It takes over about 2,400 Light long bars on the primary 4H chart and 5,400 on the secondary.
  - **More bars pass the entry checks.** About 7,500 Wait bars become entries on primary 4H and 15,300 on secondary. Unknown checks had counted as unmet, so with them known, more bars clear the thresholds.

  So S has more trades (314 → 373 and 725 → 787), and its Strong long entries are sized twice Light long.
- **What it does to returns: it amplifies both ways.**
  - S makes more in the rally window W5 (October 2023 to April 2024) in every run: +65.8% against +35.6% on primary 4H. It also makes more in W7 (October 2024 to April 2025), but on the primary coins only.
  - It loses more in almost every other window.
  - Over the nine windows the losses outweigh the gains on three runs of four; the primary 1D run is the exception, with a much deeper worst window.
- **Strong long's own trades are not better entries.**
  - On the deciding run, its median trade is −8.1% against −1.2% for Light long in the same run.
  - On the other runs the medians are about level (−8.3% to −9.3% against −8.0% to −9.5%).
  - Its summed P&L is negative on two runs, about flat on one, and positive only on primary 1D.
  - The extra size buys more exposure, not better selection.
- **What the recommendation would test, and what it would not.**
  - The cap keeps the context: live, funding and stablecoins are known for most coins. So a capped engine is S with Strong long sized as Light long, not C.
  - That engine was not one of the declared variants. A run of it on the same windows would be seen data: a check of the recommendation, not a new verdict.
- **Why the live scorecard may read differently.**
  - Live Strong long has its own record (the comments in `signal_synthesizer.py` cite 40.7% wins in MARKUP and 68.4% in ACCUM, from a small sample).
  - This replay's Strong long fires on Binance spot history with no CoinGlass and no HyperLens, scored by one position manager with its own stops and sizing. The two are not the same measurement.

## Check of the recommendation (set down 9 November 2026, before running)

The owner's go-ahead (9 November 2026): "yes" to a check run of the engine the recommendation would put live, before deciding.

- **Why.** Live knows funding and stablecoins for most coins, so capping Strong long live gives S with Strong long sized as Light long, not C. That engine was not a declared variant.
- **Variants:**
  - **K:** S with `signal_synthesizer.STRONG_LONG_CAP` on (`--context live --cap on`). Every row that would be Strong long is Light long.
  - **KD:** K plus the 90-day top-divergence exit (`--divexit 90`). This is the engine both pending changes would make; the two were tested apart.
- **Runs:** both coin sets, 4H and 1D, against C and S above. The harness is unchanged.
- **How it is read.** This is a check on windows already seen, not a new verdict; nothing in it re-decides either study.
  - It answers whether K is worse than C. If it is not, the cap alone covers the harm found here.
  - If it is (by more than 5 points on primary 4H, or on both 4H runs), the extra entries that known context lets through are a problem too. That needs its own declared study before any change beyond the cap.

## Check results (run 9 November 2026; windows already seen: a check, not a verdict)

| Run | C (today's replay) | S (context, Strong long) | K (context, capped) | KD (K + 90-day exit) |
|---|---:|---:|---:|---:|
| **Primary 4H** | +43.1% (−10.4%) | +34.8% (−17.5%) | **+46.4%** (−11.8%) | **+57.3%** (−9.8%) |
| **Secondary 4H** | +45.3% (−14.6%) | +30.2% (−19.6%) | **+33.9%** (−14.7%) | **+35.1%** (−14.7%) |
| Primary 1D | +36.5% (−13.9%) | +50.2% (−21.4%) | +36.1% (−16.1%) | +43.9% (−14.1%) |
| Secondary 1D | +4.9% (−20.0%) | −4.9% (−30.4%) | +12.2% (−22.1%) | +13.3% (−22.4%) |

Compounded return over windows 1–9, worst window in brackets. Trades on primary 4H: C 314, S 373, K 373, KD 321.

Per-window returns, K / KD (%):

| Run | W1 | W2 | W3 | W4 | W5 | W6 | W7 | W8 | W9 |
|---|---|---|---|---|---|---|---|---|---|
| Primary 4H | −1.4 / +1.6 | 0 / 0 | +3.1 / +3.1 | −4.3 / −4.3 | +49.8 / +47.1 | −11.0 / −7.8 | +19.8 / +19.6 | +2.0 / +3.5 | −7.5 / −6.5 |
| Secondary 4H | −8.6 / −5.9 | 0 / 0 | +1.3 / +1.3 | −2.8 / −2.8 | +40.9 / +36.5 | −9.2 / −7.7 | +25.7 / +25.2 | −4.9 / −4.9 | −2.7 / −2.7 |
| Primary 1D | −8.6 / −5.3 | 0 / 0 | −1.8 / −1.8 | −8.7 / −8.7 | +62.5 / +60.6 | −6.3 / −6.3 | +12.1 / +13.1 | +9.7 / +10.5 | −11.2 / −9.8 |
| Secondary 1D | −13.6 / −8.3 | 0 / 0 | +0.5 / +0.5 | −3.5 / −3.5 | +51.0 / +45.5 | −5.6 / −4.2 | +4.6 / +1.8 | −7.3 / −7.3 | −3.2 / −3.2 |

**Reading, as set down.**
- K is 3.3 points above C on primary 4H, and below it on one 4H run only (secondary, −11.4). By the reading set down before running, K is not worse than C: the cap alone covers the harm found here.
- **Not explained away:** on the secondary coins at 4H, the entries that known context lets through cost 11.4 points against C. On the daily runs they do not (secondary +7.3, primary −0.4). This is context, not a finding, and changes nothing by itself.

**What the two changes would do to the engine as it runs live.**
- Live already knows funding and stablecoins for most coins and gives Strong long, so the closest replay of today's live engine is S, not C.
- Turning on the cap and the 90-day exit moves it from S to KD:

| Run | S | KD | Return | Worst window |
|---|---:|---:|---:|---:|
| Primary 4H | +34.8% (−17.5%) | +57.3% (−9.8%) | +22.5 | 7.7 shallower |
| Secondary 4H | +30.2% (−19.6%) | +35.1% (−14.7%) | +4.9 | 4.9 shallower |
| Primary 1D | +50.2% (−21.4%) | +43.9% (−14.1%) | −6.3 | 7.3 shallower |
| Secondary 1D | −4.9% (−30.4%) | +13.3% (−22.4%) | +18.2 | 8.0 shallower |

- KD returns more than S on three runs of four and has a shallower worst window on all four.
- These are windows already seen, and live is not the replay (no CoinGlass; HyperLens live; funding from the live sources).

## Shipped (9 November 2026)

The owner approved the cap ("Merge it yes. Clear improvements").
- `signal_synthesizer.STRONG_LONG_CAP = True`: every row that would be Strong long is Light long, live and in paper trading.
- The 90-day top-divergence exit went on at the same time (`docs/reviews/top-divergence-exit-study.md`).
- The replay harness keeps the cap off unless run with `--cap on`, so earlier runs reproduce. Later engine studies on the live engine run `--context live --cap on --divexit 90`.
