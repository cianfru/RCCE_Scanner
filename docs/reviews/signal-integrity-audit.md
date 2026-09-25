# Signal integrity audit (25 September 2026)

Question: do the signals the product shows and trades match the logic that produced the tested returns, and is that logic applied to every market?

## Which signal produces the returns

| Consumer | Signal it reads |
|---|---|
| Executor (198-day paper record) | the **4H** timeframe `signal` (`scanner.py`, executor fed `results["4h"]`) |
| Study baselines (B1) and exit shadow log | the timeframe `signal` (1D) |
| Outcome tracker (`signal_outcomes.py`) | `unified_signal` |
| Scanner grid, counters, best setups (before this change) | `unified_signal` |

The combined 4H+1D `unified_signal` was what users saw, but nothing that produced returns trades it. The grid, counters, best setups, filters and assistant now read each timeframe's own `signal`; the combined decision stays as a labelled "4H+1D" chip on the coin page.

## Production defects found (live API, 16:32–16:43 UTC)

1. **4H signals withheld for up to an hour after every candle close.** 208 of 210 4H rows had `signal_status=unavailable` ("Candle snapshot stale"). The staleness limit (one bar + 5 min, #130) was shorter than the drip refresh interval (1h for most markets, 4h for deep-cold ones, #117/#118). The fetch cache also returned pre-close data for up to 30 minutes. With the executor fed from 4H, it saw WAIT for most of each hour.
   *Fix:* every market is refreshed once after each 4H close (BTC and ETH first); the fetch cache expires at candle closes; the idle loop wakes for closes; the staleness grace is one bar + 20 min.
2. **Combined signal WAIT on 206 of 209 rows** as a consequence of (1): it requires both timeframes to be usable. It also ignored `entry_blocked` and reported a stale timeframe as "Cross-timeframe entry disagreement".
   *Fix:* respects entry blocks; `unified_complete` records whether both timeframes were usable, and only then is WAIT a disagreement.
3. **Strong Long impossible everywhere.** Fear & Greed came only from CoinGlass, whose calls fail in production (sentiment endpoint returned the placeholder 50/Neutral). Since #130 a missing core input blocks Strong Long; 30 rows reached Strong Long and were capped. The Signal Log shows Strong Longs until 23 September and none from the 24th, when #130 was merged.
   *Fix:* alternative.me first (the series the backtests replay), CoinGlass as fallback. A missing reading is no longer replaced by 50 in the accumulation and revival paths.
4. **False MARKDOWN on leaders consolidating near their highs** (HYPE 1–8 Sep, INJ 3–9 Sep; VVV was two bars from it on 25 Sep). MARKDOWN's weight scales with volatility and needs only z slightly below the regression line. The persistence latch (#125) was fixed earlier; the generation defect was not.
   *Fix:* MARKDOWN's weight is gated on a falling 30-bar trend (`MARKDOWN_TREND_GATE`), mirrored in the Pine script. Validated below.

## Smaller findings

- BLOWOFF is never the resolved regime (0 of 228k historical bars): MARKUP's weight always exceeds it. Its TRIM paths are dead code; exits come from heat. Left unchanged: enabling it would change the tested exits.
- The heat forced trim fires far *below* the weekly band as well as above it. It is part of every backtest and acts as a crash exit, so the behaviour stays; its wording no longer says "overextension" when price is below the band.
- The synthesizer's `Z_BLOWOFF = 2.0` is an entry cap for MARKUP (entries only below z 2.0), distinct from the engine's regime threshold of 2.5. Not a defect; unchanged.
- Whale consensus note mixed a size-weighted direction with a wallet-count ratio ("BEARISH, ratio=+0.33"). Reworded; HyperLens labels the two columns.

## Presentation fixes

Signal context icons classify demotions, forced exits and crowded positive funding as cautions; stale candles read as a paused signal; a market-wide missing input is one banner instead of an icon on every row; conflicting evidence is orange, caution amber; a z-score above 2 is orange (stretched) instead of red; light theme hues are readable on white; Signal Log, Analytics and HyperLens share the scanner's tab style.

## Access control

The login screen checked a code shipped in the browser bundle, and the API was open. `backend/access.py` adds a server-side login (`/api/auth/login`, signed 30-day tokens) enforced on the API and the scan WebSocket once `REFLEX_ACCESS_CODE` is set on Railway. Health checks and the landing page's five-coin preview (`/api/public/preview`) stay public. External callers (e.g. the `rcce-entry-confirm` skill) need `Authorization: Bearer <token>` once enforcement is on.

## Validation of the logic against returns

See "Replay results" below: the same 4H Binance history (10 primary coins, walk-forward windows 1–9, holdout untouched) replayed through (A) the engine before #130, (B) today's live logic, (C) today's logic with the MARKDOWN gate, all scored by the same costed PositionManager (`backtest/live_logic_replay.py`, `backtest/live_logic_check.py`).
