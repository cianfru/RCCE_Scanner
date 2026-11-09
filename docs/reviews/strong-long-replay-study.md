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
