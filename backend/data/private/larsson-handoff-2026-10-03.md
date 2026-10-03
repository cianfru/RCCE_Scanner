# Claude Code handoff — CTO Larsson study for RCCE (Reflex)

> Paste or attach this whole file in Claude Code inside the `cianfru/RCCE_Scanner` repo. It is self-contained. Part 1 is the work order (what to do, in what order, where to stop). Part 2 is the full technical spec it refers to. Date of handoff: 3 Oct 2026.

---

# PART 1 — Work order

## 0. Context in five lines

- RCCE's existing `cto_engine.py` ("CTO Line Advanced") is a **different** indicator from the official Larsson Line, and PR #130 tested it at 4h with a 24h horizon. Its null result does not apply to Larsson's process.
- The official Larsson Line v2.51 has been reverse-engineered and verified: EMA 32/35/50/58 of close, full-order rule (Part 2 §1).
- Pro's level/pattern rules and its event history (~1,300 events, Apr–Oct 2026) have been extracted (Part 2 §2–§2c, Appendix B).
- Goal: test whether the Larsson process (trend + levels + patterns + risk sizing) improves RCCE. Use a walk-forward, then a held-out window, then live shadow. **Nothing changes live signals** until a rule passes Part 2 §4c.
- CTO line in RCCE today is display-only (no promotion artifact deployed). Keep it that way.

## 1. Setup (do first)

1. Save Part 2 of this file as `docs/reviews/larsson-study-spec.md` (verbatim).
2. Add `data/private/` to `.gitignore`. The repo is public and these files are Larsson's paid data, so never commit them. Andrea will place these files there:
   - `larsson_events_1.csv`
   - `larsson_level_history.csv`
   - `larsson_level_history_2.csv`
   - `larsson_pattern_history.csv`
   - `larsson_pro_recap_2026-09-25.csv` (optional)
3. Create a branch `feat/larsson-study`. One PR, shadow only. Do not merge without Andrea's review.

## 2. Decisions already taken (defaults)

| Topic | Decision |
|---|---|
| Timeframe | 1D decides; 4H is not used in v1 (timing only, later) |
| Existing `cto_engine` | Untouched. The Larsson engine lives alongside it under its own key (`larsson`) |
| Grey trim (variant L4) | Keep as a variant; it is not a rule |
| Pattern recognition | In scope (Module D) |
| Phase 2 selection model (§4b) | **Not** in this PR. Only after Andrea approves, based on Stage 2 results |
| Live signal path | No changes. Shadow and chart only |

## 3. Stages and stop points

### Stage 1 — Build (this PR)

Implement in this order. Each step needs its tests passing before the next.

1. **Module A** `backend/engines/larsson_engine.py` plus `tests/test_larsson_engine.py` (Part 2 §1).
   **STOP 1**: report the parity-test results against the BTC, ETH, LUNA and LTC/BTC flip dates in §1. If any vector fails, fix it before continuing. Never loosen the vectors.
2. **Module B** `backend/engines/levels_engine.py` plus tests (Part 2 §2).
3. **Module D** `backend/engines/patterns_engine.py` plus tests: one synthetic series per pattern, plus negative cases (Part 2 §2c).
4. **Module C** `backend/backtest/larsson_manager.py` plus tests: sizing math, correlation budget, gap-through-stop fills (Part 2 §3). Do not modify `position_manager.py`.
5. **Study CLI** `backend/backtest/larsson_study.py`. It must run benchmarks B0–B3 and variants L1–L5, L2P and L3X over walk-forward windows; write `report.json` and CSV summaries; and refuse to run the holdout twice (mirror `cto_study`).
6. **Chart overlay**: LL ribbon (gold/grey/blue) and active levels on the 1D chart, under a new key. `compute_cto_chart` stays unchanged.
7. **Docs**: `docs/reviews/larsson-study.md` (protocol, assumptions, results, failed criteria).

Data: Binance spot daily klines from 2019-01-01, with 600 bars of warm-up. Costs are 5 + 5 bps per side, leverage 1.

### Stage 2 — Walk-forward on windows 1–9 only

- Run the full grid declared in Part 2 §4. **Do not run the final (holdout) window.**
- **STOP 2**: give Andrea one table per window. Rows are B0–B3 and L1–L5, L2P, L3X; columns are CAGR, Sharpe, max drawdown, trades per year, win rate and expectancy in R. Highlight W4, plus the median across windows.
- Also report the diagnostics: Module B and D agreement with Pro events (B1–B3, B6), and the per-module deltas (L1→L2→L3→L4).
- Wait for Andrea to choose which candidate rules (R1–R5, §4c) continue, whether Phase 2 is justified, and the frozen parameters.

### Stage 3 — Holdout, run once

- Run only the frozen configuration plus the benchmarks on the final window.
- **STOP 3**: report pass or fail against §4 acceptance and §4c.

### Stage 4 — Live shadow

- Rules that passed are logged as shadow decisions in the scanner (same pattern as `cto_shadow`). They never act.
- A rule becomes a hard rule only through the existing promotion gate (`cto_policy` flow): at least 50 trades, at least 3 assets, positive lower bound.

### Stage 5 — Phase 2 model (separate PR, only on Andrea's go-ahead)

Follow Part 2 §4b.

## 4. Guardrails

- Don't change `cto_engine.py`, `opportunities.py` live behaviour, `position_manager.py`, or any live signal or execution path.
- Don't tune anything to agree with Pro. Tune only on trading outcome, and only within the declared grid.
- Don't touch the holdout until parameters are frozen and Andrea says go.
- Don't commit anything from `data/private/`.
- Report numbers as measured, with sample sizes. Say so when a cohort has fewer than 30 trades.

## 5. First message to send back

When Stage 1 step 1 is done, reply with:

- the parity table: vector, expected, got, pass/fail;
- the files created;
- any deviation from the spec, with the reason.

---

# PART 2 — Technical spec (save as `docs/reviews/larsson-study-spec.md`)

# Larsson Line process — RCCE implementation and study spec

Status: spec, not implemented. Target: `cianfru/RCCE_Scanner` backend. Everything ships in **shadow**, and changes nothing live until it passes the existing promotion gate (`docs/reviews/cto-study-protocol.md`).

This document is self-contained: it holds every finding, rule, number and data description from the research (25 Sep 2026) needed to implement and run the study. The background research doc (*Larsson Line Process — Study & RCCE Integration*, Claude Docs) is context only; nothing required lives only there. Data files are described in Appendix B. They are Larsson's paid data: **keep them out of this public repo** (`data/private/`, gitignored).

---

## 0. Why a new study, not a re-run of the CTO study

The existing CTO work (PR #130, `docs/reviews/cto-historical-smoke-test.md`) tested a **different indicator** under **incompatible conditions**:

| | Existing `engines/cto_engine.py` ("CTO Line Advanced") | Official Larsson Line v2.51 (verified) |
|---|---|---|
| Lines | SMMA 14/17/20/24 of HL2, then SMA(2) | **EMA 32/35/50/58 of close**, no extra smoothing |
| States | 5 (strong/weak up/down, neutral) with slope and ATR strength | 3: gold / grey / blue |
| Gold rule | v1>v2, no inner conflict, both slopes up | EMA32 > EMA35 > EMA50 > EMA58 (full order) |
| Test timeframe | 4h, 6-bar (24h) horizon | Designed for **1D crypto**, holding periods of months |
| Role | Ranking/confirmation/veto filter on RCCE entries | Position management: when to be in or out |

Verification: the official script's plotted lines were read from TradingView and match EMA32/EMA58 of the close to 1e-15 relative error. State agreement: BTC 1D 100% (3,127 bars), ETH 1D 99.9%, ETH 4H 99.96%. It also reproduces Pro 4's live flips (LTC/BTC gold flip on 2026-09-24).

A 24-hour horizon cannot measure a system that flips about 3 times a year. The null result in PR #130 therefore says nothing about the Larsson process.

---

## 1. Module A — `engines/larsson_engine.py` (version `larsson-2.51`)

Mirror the `cto_engine.py` public API so the chart, scanner and replay can share it.

```python
compute_larsson_series(close, timestamps) -> dict
compute_larsson_snapshot(ohlcv, timeframe, as_of_ms) -> dict   # completed bars only
```

**Formula**

- `ema(n)`: standard EMA of **close**, α = 2/(n+1), seeded with the SMA of the first n closes (Pine `ta.ema`).
- `e32, e35, e50, e58 = ema(32), ema(35), ema(50), ema(58)`
- `gold  = e32 > e35 > e50 > e58`
- `blue  = e32 < e35 < e50 < e58`
- `grey  = otherwise`
- Plot lines: e32 and e58; the fill takes the state colour.

**State machine (persist per symbol/timeframe)**

- `last_actionable` = last non-grey state.
- `gold_flip` on bar i: state==gold and last_actionable before i == blue.
- `blue_flip` on bar i: state==blue and last_actionable before i == gold.
- gold→grey→gold and blue→grey→blue emit **nothing**.
- `grey_after_gold`: the first grey bar after a gold run. This is a warning only; the variant in §3 tests whether to act on it.

**Snapshot fields**: `version, timeframe, state, last_actionable, flip (gold|blue|null), bars_since_flip, grey_after_gold, e32, e58, spread_pct, data_quality, candle_close_time, input_id`.

**Warm-up**: an EMA has infinite memory. Require at least 600 completed bars before emitting `ready`; with fewer, the state can differ from TradingView.

**Parity tests** (`tests/test_larsson_engine.py`, Binance spot daily closes):

| Pair | Expected actionable flips (date = bar open, UTC) |
|---|---|
| BTCUSDT | blue 2018-02-05 · blue 2020-03-13 · gold 2020-05-04 · gold 2022-04-02 · blue 2022-04-17 · gold 2026-05-01 · blue 2026-06-03 · gold 2026-08-23 |
| ETHUSDT | blue 2018-03-13 · blue 2020-03-18 · gold 2020-04-30 · gold 2022-04-04 · blue 2022-04-28 · gold 2026-05-11 · blue 2026-05-20 · gold 2026-08-19 |
| LUNAUSDT | gold 2022-03-01 · grey from 2022-05-01 (close ≈ 82) · blue 2022-05-09 (close ≈ 30) |
| LTCBTC | gold flip 2026-09-24 |

Plus property tests: grey never emits a flip, and flips alternate strictly.

---

## 2. Module B — `engines/levels_engine.py` (version `levels-1`)

Deterministic horizontal levels and the four events. Pro's level picker is AI-based and not reproducible (best rule-based agreement on 501 Pro events, Apr–Sep 2026: 23% recall, 13% precision). **Do not tune toward Pro agreement; tune on trading outcome (§4).**

**Levels at bar i (inputs: completed bars < i only)**

1. Body pivots: bar j is a pivot high if `max(open,close)` is the maximum over `[j-n, j+n]`, and a pivot low likewise on `min(open,close)`. It is confirmed only once `j+n < i`.
2. Lookback `W` bars. Sort pivots by price and cluster consecutive pivots within `tol` of the cluster's first price.
3. Level price = mean of the cluster's pivot prices. Record `touches` (pivots at least `gap` bars apart), `n_high`, `n_low`, `last_touch_age`, `span`.
4. Keep a level if `touches ≥ min_touches` and `last_touch_age ≤ max_last`.

Defaults (from calibration; declare before the study): `n=5, tol=1.5%, W=730 (1D), gap=10, min_touches=2, max_last=30`. Levels are anchored on bodies, not wicks; body pivots fit Pro's levels about twice as well as wick pivots.

**Events on the daily close (buffer b = 1%)**

| Event | Condition at bar i | Side requirement |
|---|---|---|
| breakout | close_i > L·(1+b) and close_{i-1} ≤ L·(1+b) | n_high ≥ 2 |
| breakdown | close_i < L·(1−b) and close_{i-1} ≥ L·(1−b) | n_low ≥ 2 |
| bounce | low_i ≤ L·(1+b), close_i > L·(1+b), close_{i-1} > L | n_low ≥ 2 |
| rejection | high_i ≥ L·(1+b), close_i < L | n_high ≥ 2 |

Carry `level`, `event`, `touches`, `n_high`, `n_low`, and `invalidated` (a later close back through L). Keep a fakeout counter per level: at most 3 attempts per level and direction, then ignore that level for `cooldown=30` bars.

**Range regime** (`range_state` per symbol): true when the last `R=40` closes all lie between one support level and one resistance level, each with ≥2 touches, and the band height is ≤ `k·ATR(14)` with k=8, **or** when the raw colour changes of Module A over the last 40 bars are ≥4 with net displacement < 2·ATR. It ends on a breakout or breakdown of the band.

**Compute on both charts**: ALT/USDT and ALT/BTC. The BTC pair acts as the relative-strength vote.

---

### 2b. Evidence behind the Module A/B rules

Sources: the course transcripts (23 lessons), the Pro 4 app's client code and discovery API (v4.6.3), and Pro's published event charts.

**Process rules (course)**
- Trend mode: gold flip → scale in, blue flip → scale out. Grey is "no trend" and is not actionable.
- Range mode (2025 addition): when price is distinctly boxed, ignore flips and trade the four horizontal events. A blue flip at range support is not a sell.
- Timeframes: crypto 1D, tech stocks 1W/2W, country/FX-linked 1M.
- Fakeouts: at most 3 attempts per level, walk away after the third.
- Altcoins: levels are often cleaner on ALT/BTC than on ALT/USD.
- Risk: at most 2% of equity at risk per trade. Stops are checked on the daily close; automatic stop orders are used only once already decided to sell. No rebalancing of winners. Profit-taking is 50% pro-rata of the whole portfolio at a life-changing level.
- Entry scaling: fresh flip → 50% now + 50% at the next support below. Found late → thirds at current, 1st support and 2nd support. Exit: 50% at the flip, 50% on the next rally into resistance. After a big dump, wait for the relief bounce.

**Pro 4 data model (what the live product computes)**
- Per asset per day: `alm`=1 gold, `asm`=2 blue, neither = grey. `lat` = last non-grey state. `gof`/`blf` = gold/blue flip on this bar, which only fires on a `lat` change (verified on 300 coins).
- `pevent`: 1 breakout, 2 breakdown, 3 bounce, 4 rejection; `plevel` = level price.
- `pattern`: 10 rectangle up, 11 inverse H&S, 12 cup & handle, 13 ascending triangle; 20 rectangle down, 21 H&S, 23 descending triangle. Codes pack together (11010 = 11+10). Patterns fire only on a neckline break (60/60 tags carried a breakout or breakdown event).
- Every field exists twice: on the USD chart and on the pair chart (ALT/BTC for coins, asset/index for stocks and commodities).
- An event stays "live" while the close remains beyond the level.
- Pro's position-size calculator: entry = close, stop = the event level itself (no buffer). Qty = portfolio × impact% ÷ ((entry−level)/entry × price). Median breakout distance above its level: 4.4% (n=53).
- Presets: "Gold Scan" = (breakout OR bounce) AND is-gold, on USD or pair; it is the default view.

**Calibration against Binance daily bars (150 Pro events, 17–24 Sep 2026)**
- Levels are body-anchored: body pivots fit about twice as well as wick pivots (65–71% vs 25–37% within 0.5%).
- Levels are computed, not copied: only 24/150 sit within 0.01% of any past OHLC price.
- Breakout = daily close ≥ ~1% above the level (minimum seen 0.98%). 84% are the first close above.
- Rejection = high pierces the level by 1.3–31% (median ~5%) and the close finishes back below.
- Levels often reach 6–12 months back.

**History back-fill (15 Apr–16 Sep 2026, 501 Pro events, 118 coins; re-checked 3 Oct on 1,299 events, 510 pairs, 15 Apr–2 Oct: best recall 21%, precision 8–12%, so the conclusions hold)**
- Pro fires about 0.5 events per coin per month, far more selectively than any simple rule.
- 54% of Pro levels lie within 0.5% of one of Module B's ≥2-touch levels (random prices near the close: 15%).
- Best Module B configuration matches 23% of Pro events, and 13% of its signals appear in Pro. Module B fires about 8× more often.
- Pro 3's level selection is described by Larsson as AI-based and is not reproducible exactly. Hence §4b.

**Signal quality: Pro events vs Module B (15 Apr–2 Oct 2026, 510 Binance pairs)**

The return is the median 20-bar forward return from the next open, signed in the event's direction (breakout = long, breakdown = short). The Larsson Line state is the one on the event bar. Module B config: n=5, tol=1.5%, W=730, ≥2 side touches, last touch ≤30 bars, 1% buffer.

| Event | LL state | Pro: n, median, win | Module B: n, median, win |
|---|---|---|---|
| Breakdown | blue | 300, +5.5%, 65% | 913, +2.3%, 57% |
| Breakdown | grey | 85, +14.1%, 81% | 236, +7.7%, 67% |
| Breakdown | gold | 72, +5.7%, 57% | 240, +4.2%, 60% |
| Breakout | gold | 142, −4.4%, 40% | 272, −0.2%, 50% |
| Breakout | blue | 246, −2.5%, 42% | 546, +1.0%, 52% |
| Breakout | grey | 149, −8.5%, 28% | 291, −5.0%, 38% |

Reading:
- Pro's selection adds value on **breakdowns** (exits and defence) and none on **breakouts** in this sample.
- The sample is one mostly bearish regime, with overlapping trades and event types inferred from closes. Treat it as a hypothesis.
- This is the main argument for §4b: a selection model should be tried on breakdown and exit events first.
- Breakouts while LL is grey were the worst group for both, which supports not acting on level events while LL is grey.

**LUNA (May 2022)**: LL turned grey on 2022-05-01 at ~$82 and blue only on 2022-05-09 at ~$30. Larsson's claimed "exit at 70–80" was the grey warning, not a formal flip. This is why variant L4 exists.

**Community "CTO Line" (gist)**: SMMA of HL2 at 15/19/25/29 is a near-miss. SMMA(n) ≡ EMA(2n−1), so it approximates EMA 29/37/49/57 on a different source, and it omits the m1-vs-m2 order check. Do not use it.

## 2c. Module D — `engines/patterns_engine.py` (version `patterns-1`)

**What Pro actually detects**: seven pattern types, not dozens. In the course Larsson says he went from 30+ drawn patterns down to six. Every one of them has a **horizontal neckline**, and Pro tags a pattern only on the bar where that neckline breaks: 60/60 tags in pull 1 came with a breakout or breakdown event.

| Code | Pattern | Direction | Neckline | Fires on |
|---|---|---|---|---|
| 10 | Rectangle breakout | bull | range top | breakout |
| 11 | Inverse head & shoulders | bull | peaks between the three troughs | breakout |
| 12 | Cup & handle | bull | cup rims | breakout |
| 13 | Ascending triangle | bull | flat top | breakout |
| 20 | Rectangle breakdown | bear | range bottom | breakdown |
| 21 | Head & shoulders | bear | troughs between the three peaks | breakdown |
| 23 | Descending triangle | bear | flat bottom | breakdown |

Codes combine (e.g. 11010 = inverse H&S + rectangle). The course also names double top/bottom and parabola breaks. Parabola: Larsson calls it the best pattern to find and says a broken parabola usually retraces ~80%, a short opportunity. Pro does not tag either; they are optional v2.

**Design**: build on Module B. A pattern is a geometric condition checked only when Module B emits a breakout or breakdown; the pattern code is attached to that event. It is not a separate trigger. Body pivots throughout, all parameters declared up front.

- **Rectangle (10/20)**: ≥2 pivot highs within `tol` of resistance R, and ≥2 pivot lows within `tol` of support S, interleaved. Duration ≥ 20 bars; height (R−S)/S between 5% and 60%. Breakout above R → 10, breakdown below S → 20.
- **Ascending triangle (13)**: flat top (≥2 pivot highs within `tol`) plus ≥2 pivot lows, each ≥1% higher than the previous. Duration ≥ 20 bars; breakout above the top. **Descending (23)**: mirror image.
- **Head & shoulders (21)**: pivot highs L-shoulder < head > R-shoulder. The head is ≥5% above both shoulders; the shoulders are within 12% of each other and roughly symmetric in time (ratio 0.5–2). The two troughs are within `tol` and define a horizontal neckline. Duration 30–250 bars; breakdown below the neckline. **Inverse (11)**: mirror image.
- **Cup & handle (12)**: rims within `tol` (the neckline). Cup depth 12–50% with a rounded bottom: at least 30% of the cup's bars lie in its bottom third. The handle pulls back ≤ 1/3 of cup depth within the last 5–30 bars; breakout above the rims.
- Optional feature: breakout-day volume ÷ 20-day median. The course says to check volume on breakouts.

**Diagnostic check**: Appendix B6 (Pro pattern tags). Measure recall and precision by pattern family, with the same date and level within 1%. As with levels, don't optimise toward Pro; optimise on outcome.

**Preliminary evidence** (Pro's own tags, B2 + B6, 15 Apr–16 Sep 2026). The return is median, measured from the next open, signed in the event's direction:

| Group | n | +10d | +20d | +40d | Win rate at 20d |
|---|---|---|---|---|---|
| Breakdown with a bear pattern | 19 | +7.5% | +13.5% | +14.9% | 84% |
| Breakdown, no pattern | 120–135 | +2.5% | +4.9% | +10.4% | 63% |
| Breakout with a bull pattern | 22–28 | −5.2% | −8.1% | −25.6% | 20% |
| Breakout, no pattern | 98–158 | −5.6% | −7.9% | −19.3% | 28% |

Reading:
1. This was a mostly bearish period, and breakouts failed with or without a pattern. That is the case for gating level events by trend (Larsson Line gold).
2. Bear patterns appear to improve breakdown quality. But n=19, one regime, overlapping trades and inferred event types make this a hypothesis to test, not a result.

**Uses in the study**:
- Variant **L2P**: L2, but level-event adds require a pattern tag.
- Variant **L3X**: L3, plus a bear-pattern breakdown forces a full exit even while gold. The course recommends taking 50% on a confirmed H&S or broken parabola after a run-up; test both 50% and 100%.
- Pattern code becomes a feature in the §4b model.

## 3. Module C — `backtest/larsson_manager.py`: position management

A new manager class with the same interface as `PositionManager` (`process_bar`, `mark_to_market`, `close_all_at_end`, `get_equity`), selected by a config flag. Do **not** edit the RCCE manager.

**Sizing (risk-based)**

- `risk_pct` of current equity per position; default 1%, grid {0.5, 1, 2}.
- `stop = event level × (1 − stop_buffer)`, default stop_buffer 1%. If there is no level, use `close × (1 − 12%)`.
- `allocation = risk_pct × equity / ((entry − stop)/entry)`, capped at 25% of equity per position.
- **Correlation budget**: total open risk across alts (anything with 90-day correlation to BTC > 0.6) ≤ 5% of equity. At most 2 new same-cluster entries per bar; others queue until the next bar.
- No rebalancing. Capital returns to the pool only on exit.

**Stops**: evaluated on the daily close (a "manual" stop), filled at the next open. A gap through the stop fills at the open. Trail the stop to the latest broken level once price is more than 2R in profit.

**Entries and exits by variant**

| ID | Entries | Exits |
|---|---|---|
| L1 trend-only | gold flip → 50% at next open, 50% limit at nearest support below (expires after 20 bars) | blue flip → 50% next open, 50% at the first close ≥ nearest resistance or after 10 bars |
| L2 trend + levels | L1, plus adds on breakout or bounce while gold (1/3 size each, max 2 adds) | L1, plus breakdown of a distinct range = full exit |
| L3 L2 + range mode | While `range_state`: ignore flips; enter on bounce or breakout, exit on rejection (50%) or breakdown (100%) | Blue flip at range support is **not** an exit |
| L4 L3 + grey trim | L3 | Also trim 50% on `grey_after_gold`; restore on the next gold if it arrives within 15 bars |
| L5 L3 gated by RCCE | L3, but new longs only when the RCCE regime is not RISK_OFF and BMSB is not blocked (`_is_bmsb_blocked`) | L3 |

**Benchmarks** (same data, windows and costs):

- `B0` buy & hold equal weight.
- `B1` current RCCE baseline (`runner.py` pipeline, 1D).
- `B2` existing `cto_engine` ("CTO Line Advanced") used the same way as L1: long on its up state, flat otherwise, same sizing. This isolates the indicator swap from the management changes.
- `B3` RCCE baseline with an LL veto: RCCE longs blocked while LL is blue.

---

## 4. Study protocol

- **Timeframe**: 1D decisions. 4H is used only for timing, and not in v1 (open decision §6).
- **Universe**: `DEFAULT_BACKTEST_SYMBOLS` (10) as the primary set, plus a secondary set of 30 liquid Binance USDT pairs with at least 1,000 daily bars. The BTC pair for Module B comes from Binance `ALTBTC` where listed; otherwise synthesize ALT/USDT ÷ BTC/USDT.
- **Data**: Binance spot daily, 2019-01-01 → today, with 600 bars of warm-up before the first window.
- **Windows**: existing walk-forward, 180-day non-overlapping, fresh capital per window. Report every window, with W4 (post-FTX recovery) highlighted.
- **Holdout**: the last full window (≈ 2026-03 → 2026-09) is reserved. Parameters are frozen before it is run, and it runs once.
- **Costs**: 5 bps fee + 5 bps slippage per side, spot (no funding). Leverage 1.
- **Metrics per window and aggregate**: CAGR, Sharpe, Sortino, max drawdown, time in market, trades/year, average hold, win rate, payoff ratio, expectancy per trade in R, worst month, and exposure-adjusted return.
- **Parameter grid** (declared now; nothing else gets tuned): `risk_pct {0.5,1,2}` × `tol {1%,1.5%}` × `max_last {30,60}` × `b {1%,1.5%}`. Report the full grid, and select on the median across windows, not the best one.
- **Diagnostics (not optimisation targets)**:
  - Agreement of Module B events with Pro events (`larsson_level_history*.csv`): recall and precision at 1% level tolerance.
  - LL flip parity vs the TradingView test vectors.
  - Contribution per module: L1 → L2 → L3 → L4 deltas, window by window.

**Acceptance for moving from shadow to a candidate** (in addition to the existing gate where it applies):

1. L-best beats B1 on median-window Sharpe **and** on max drawdown in ≥ 6 of 10 windows.
2. W4 result ≥ B1 W4.
3. Holdout: positive expectancy and drawdown ≤ B1's.
4. There is no single-asset dependence: removing the best asset keeps criterion 1.

---

## 4b. Phase 2 (conditional) — trade-selection model

**Only start this if** Phase 1 shows that L2 or L3 (the level layer) adds value over L1 in windows 1–9. If the level layer adds nothing, a better level filter won't rescue it; stop there.

**Problem**: Module B emits roughly 8× more level events than Pro, and most of them are noise. Train a classifier that scores each Module B candidate event and keeps only the good ones.

**Primary label (trading outcome, recommended)**: for each candidate event, compute the forward R-multiple. This is the return from the next open to the exit, divided by the stop distance (entry − level×(1−stop_buffer)), using the Module C exit rules or a fixed 20-bar horizon. Label = 1 if R ≥ 1.

**Secondary label (Pro agreement, diagnostic)**: 1 if a Pro event exists on the same pair, same date (±1 day), with level within 1%. Sources are Appendix B files B1–B3: about 1,300 events (B1 + B2 + B3), 15 Apr–2 Oct 2026. Report it as agreement, never optimise the strategy on it alone.

**Features (computed at the event bar, from completed data only)**:
- Level: touches, n_high, n_low, last_touch_age, first_touch_age, span, cluster price std / level, and whether it has touches on both sides (polarity flip).
- Event: type, close distance to level in %, and in ATR.
- Context: ATR(14)/close, volume vs 20-day median, Larsson Line state and bars_since_flip, range_state, BTC-pair LL state (relative strength), RCCE regime, and distance to the 52-week high and low.
- Volume profile: whether the level sits within 1% of a high-volume node of the 365-day volume profile. Larsson's course draws levels with VRVP; this is the main untested hypothesis for closing the gap to Pro.

**Method**: gradient-boosted trees (LightGBM) or regularised logistic regression. Keep it small.
- Split strictly by time: train on windows 1–7, validate on 8–9. The holdout window stays untouched.
- Calibrate probabilities, then choose one threshold on validation.
- Report precision/recall versus both labels, and the L2/L3 strategy metrics with the filter on vs off.

**Guardrails**:
- Freeze features and threshold before touching the holdout.
- Log feature importances.
- If the filtered strategy doesn't beat the unfiltered one on validation, discard the model.

## 4c. What becomes a hard rule in RCCE (decision rule)

Nothing from this study changes live RCCE signals until it passes §4's acceptance criteria and the existing promotion gate. Until then every module runs in shadow: computed, logged and charted, but not acting. A candidate rule is promoted only if **all** of the following hold:

1. It improves median-window Sharpe **and** max drawdown versus the current RCCE baseline (B1) in ≥ 6 of 10 walk-forward windows, including W4.
2. It passes the frozen holdout window once, with positive expectancy and drawdown ≤ B1's.
3. It holds without the single best asset.
4. Live shadow logging then accumulates the evidence the existing promotion gate requires (≥ 50 trades, 3+ assets, positive lower bound).

Candidate rules, in the order to evaluate them (simplest and most robust first):

| # | Candidate hard rule | Tested by | Prior evidence |
|---|---|---|---|
| R1 | No new RCCE longs while LL (1D) is blue | B3 | Classic trend filter; the LL formula is verified |
| R2 | Exit/trim longs on a breakdown of a ≥2-touch support level, even while gold | L2/L3 | Pro breakdowns: +5.5% median at 20d when blue |
| R3 | Bear-pattern breakdown → full exit | L3X | n=19, 84% win; weak sample |
| R4 | No level-event entries while LL is grey | L3 | Grey breakouts were the worst group for both Pro and Module B |
| R5 | Trim 50% on the first grey after gold | L4 | LUNA 2022 anecdote only |

Anything that fails stays as a dashboard annotation only (chart overlay plus alert text), never as signal logic.

## 5. Deliverables (single PR, shadow only)

- `backend/engines/larsson_engine.py` plus tests (parity vectors above).
- `backend/engines/levels_engine.py` plus tests (synthetic ranges, fakeout counter, both charts).
- `backend/engines/patterns_engine.py` plus tests (one synthetic series per pattern type, negative cases, combined codes).
- `backend/backtest/larsson_manager.py` plus tests (sizing math, correlation budget, gap-through-stop fills).
- `backend/backtest/larsson_study.py`: a CLI that runs benchmarks and variants over walk-forward windows and writes `report.json` + CSV summaries. It must refuse to re-run a used holdout, as `cto_study` does.
- Chart overlay: LL ribbon (gold/grey/blue) and active levels on the 1D chart. The existing `compute_cto_chart` path stays untouched, with the new engine under its own key.
- `docs/reviews/larsson-study.md`: protocol, assumptions, results table and failed criteria.

Pattern recognition (Module D, §2c) ships in the same PR, with variants L2P and L3X. Not in scope for this PR: double top/bottom and parabola patterns (v2), any live policy change, 4H signal generation, and the Phase 2 selection model (§4b), which is a separate PR opened only if Phase 1 justifies it.

---

## 6. Open decisions for Andrea

1. **4H role**: timing only (recommended), or a separate signal lane?
2. **LL vs the existing CTO engine**: if LL wins, should it replace `cto_engine` ("CTO Line Advanced") in the chart, scanner and shadow variants, or run alongside it under its own key?
3. **Grey trim (L4)**: this departs from Larsson's own rules, where grey is not actionable. Keep it as a variant, or drop it?

---

## Appendix A — Timeline and state of the research (25 Sep 2026)

| Item | Status |
|---|---|
| Larsson Line formula | Solved and verified against the official TradingView script v2.51 (§1) |
| Event rules (breakout, breakdown, bounce, rejection) | Reproduced from Pro data (§2b) |
| Pro level picker | Not reproducible exactly; Phase 2 model (§4b) is the fallback |
| Pattern recognition | Specified as Module D (§2c); Pro's 7 types; early evidence favours bear patterns on breakdowns |
| Pro subscription | Expires 5 Oct 2026. The 3 Oct recap pull (B4) could not run: Chrome was not connected. B3 already covers those dates from the chart archive |
| Widened history probe | Done 3 Oct: 485 Binance coins, 15 Apr–2 Oct; B2+B3 = 1,287 back-filled events |

The Phase 1 walk-forward needs **none** of the Pro data; it runs on Binance price history only. The 3 Oct pull does not validate the strategy. Validation comes from the frozen holdout window and then live shadow logging.

## Appendix B — Data files (private, not for the repo)

All dates are UTC bar-open dates of daily candles. Coins are identified by **CoinMarketCap ID**, which Pro uses as `id`.

| # | File | Rows | Content |
|---|---|---|---|
| B1 | `larsson_events_1.csv` | 297 | Pro recap 17–24 Sep 2026, coins with market cap ≥ $10M. Columns: `date (MM-DD, 2026), id, sym, side (U=USD, B=BTC pair), ev (1 breakout, 2 breakdown, 3 bounce, 4 rejection), level, close, pat, st (G/B/g), lat, mcM` |
| B2 | `larsson_level_history.csv` | 346 | Back-filled Pro events 15 Apr–16 Sep 2026, 118 liquid coins. Columns: `date, id, pair (Binance symbol), side, level, close, ev_inferred` |
| B3 | `larsson_level_history_2.csv` | 941 | Same as B2 for 367 more Binance coins (15 Apr–2 Oct 2026), plus the original 118 coins extended 17 Sep–2 Oct |
| B4 | `larsson_events_2.csv` | pending (3 Oct) | Same as B1 for about 25 Sep–2 Oct |
| B6 | `larsson_pattern_history.csv` | 56 | Pro pattern tags 15 Apr–16 Sep 2026 on the B2 event days. Columns: `date, id, side, pair, pattern (rect / hs / cup_handle / triangle)`. Up/down direction follows the event; `hs` covers both H&S and inverse |
| B5 | `larsson_pro_recap_2026-09-25.csv` | 3,508 | Full raw Pro 4 recap export (coins, stocks, commodities; all Pro fields). In Andrea's Downloads folder |

**How B2/B3 were produced**:
- Pro publishes a chart image per level event at `storage.googleapis.com/llmastery/patterns/{YYYY-MM-DD}/{coinsu|coinsb}/{cmc_id}_level.png`. The bucket is not listable, so every date × coin was probed with HEAD requests. The earliest images date from about 15 Apr 2026 (the Pro 3 launch).
- The level was read by OCR from the orange price label. The label is rounded to 3–4 significant digits; BTC-pair labels are in sats, "ks" meaning ×1,000 sats. OCR accuracy is 90% on known levels.
- `ev_inferred` is derived from Binance closes, not from Pro. Rule: close crosses above the level → 1; crosses below → 2; else 3/4. Treat it as approximate: bounces and rejections are under-counted.

**Known biases**:
- Pro's API returns at most the top 300 records per query, so small caps are missing from B1/B5.
- Sep 2026 was a strongly bullish week, so B1 is breakout-heavy.
- About 10% of B2/B3 levels were lost to OCR failures and dropped, not guessed.

**Scripts** (`level_calibration/`): the calibration code used for §2b. It is research-grade and not for the repo; reimplement properly in Module B.
