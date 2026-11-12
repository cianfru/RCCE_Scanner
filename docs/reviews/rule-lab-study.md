# Rule lab: which entry and decay rules does the data support? (declared 9 November 2026, before running)

The owner's go-ahead (9 November 2026): "Go ahead with all the tests. You can test different variations to find the optimal set of rules ... review the possible flaws and implement corrections."

## Why

- The entry rules were written before the replay harness had funding, stablecoin supply, the top-divergence exit and six years of data. Their thresholds were never tested one by one.
- Two changes went live on 9 November 2026 (Strong long capped to Light long; the top-divergence exit, 90 days). Both were chosen on windows 1–9. Window 10 has never been replayed on the live logic.
- Testing many variants on the same data finds winners by chance. So the variants, the bar and the one holdout read are fixed here, before any variant result exists.

## Method

1. `backend/backtest/rule_capture.py` runs the live-logic replay once per data set and records every input of the decision pipeline (engine row, context, metadata). The engines do not depend on the synthesizer's rules.
2. `backend/backtest/rule_lab.py` re-runs only the decision pipeline on those inputs, once per variant, and scores each with the costed position manager of `backtest/live_logic_check.py` (10 bps a side, the BTC weekly-band entry block).
3. Checks before any variant is read:
   - the lab's `live` rows equal the capture's own replay rows, row for row;
   - the `live` totals on windows 1–9 equal the check run KD of `docs/reviews/strong-long-replay-study.md` (+57.3%, +35.1%, +43.9%, +13.3%);
   - the rules before the two changes (`STRONG_LONG_CAP` off, `DIV_EXIT` off) reproduce that study's column C.

Data sets (four): the 10 primary coins and the 30 secondary coins, each on 4H and 1D. Binance history to 25 September 2026; windows 1–9 end 29 March 2026.

## Variants (one switch each against the live rules)

The switches are in `backend/signal_synthesizer.py`. Their defaults are the rules as they run; tests in `backend/tests/test_rule_switches.py`.

| Name | Switch | Question |
|---|---|---|
| A50, A60, A70 | `LIGHT_LONG_MIN` 0.50, 0.60, 0.70 (today 0.40) | Does a Light long need more of the entry checks? |
| B15, B10 | `MARKUP_ENTRY_Z_MAX` 1.5, 1.0 (today: the blow-off z, 2.0) | Are late Uptrend entries worth taking? |
| C | `MODERATE_MIXED_OK` off | Should the plain Uptrend entry need a risk-on market? |
| D_greed60, D_greed80 | `FNG_GREED` 60, 80 (today 70) | Is the Fear & Greed greed level right? |
| D_fear30, D_fear50 | `FNG_FEAR` 30, 50 (today 40) | Is the fear level right? |
| E | `MARKUP_FADE_BLOCK` on | No Uptrend entry while heat is Fading or Exhaustion. |
| G | `STRONG_LONG_CAP` off, `MARKUP_STRONG_OK` off | Strong long only outside Uptrend (in Accumulation). |
| H | `CROWDED_BLOWOFF_OK` off | A flaw found in review: with crowded funding, the Uptrend Light long has no upper z bound; with neutral funding it stops at the blow-off z. H gives both the same bound. |

**Family F (position manager, scored on the live rows):** a position closes after N days of Wait: 3.3, 7, 10, 20, 40, or never. Today the rule is 20 bars: 3.3 days on 4H and 20 days on 1D. F is judged per timeframe (both coin sets of that timeframe).

Not tested again (earlier declared studies stand): stops (`stop-rules-study.md`), re-entry (`reentry-replay.md`), sizing (`position-sizing-study.md`).

## Bar (fixed now)

**Selection, windows 1–6.** A variant is selected only if all hold, on the compounded return over windows 1–6 against `live`:
1. the mean gain across the four data sets is at least **+3 points**;
2. at least **3 of the 4** sets gain;
3. in no set is the worst window more than **3 points** worse than `live`'s worst window;
4. where the variant has a neighbouring level (A, B, D, F), the nearest level has the same sign of mean gain.

For F the same four rules apply over the two sets of the timeframe (rule 2: both sets gain).

**Confirmation, windows 7–9.** A selected variant is confirmed only if its mean gain over windows 7–9 is above zero and at least 3 of 4 sets (F: both) do not lose.

**Combination.** The confirmed variants together are one set of rules. It must beat `live` on windows 1–9 by rules 1–3. If it does not, the single confirmed variant with the largest mean gain stands alone.

**Holdout, window 10 (29 March to 25 September 2026), read once per data set.** Three sets of rules: `before` (the two changes of 9 November off), `live`, and the chosen set if there is one. `rule_lab --holdout` writes a marker file before it reads and refuses a second read.
- The chosen set ships (after the owner approves) only if it does not lose to `live` on window 10 in at least 3 of 4 sets and its mean gain there is not negative.
- `live` against `before` on window 10 is reported as the out-of-sample check of the 9 November changes. It is one window: a loss there is reported, not acted on automatically.

**If nothing clears the bar:** context, not a signal. Earlier studies make this the most probable outcome for most variants.

## What can change

- Synthesizer rules that clear the bar: switched on behind their switch, with the owner's approval.
- Family F and anything else in the backtest manager or the executor: reported as recommendations only. The executor stays as it is.

## Known limits, stated before the results

- Windows 1–9 have been used by many earlier studies. Splitting them into selection and confirmation reduces chance findings but does not remove them; window 10 is the only untouched data.
- The backtest manager is not the live executor: the executor has no decay exit and no weekly-band entry block, has a breakeven stop, and closes one coin on Risk-off (corrected 10 November; see `executor-gap-study.md`). Results describe the rules, not the account.
- Historical funding and stablecoin context are reconstructions (`backtest/live_context.py`).

## Round 2 (declared 9 November 2026, after the round 1 results on three data sets, before any round 2 result)

What was seen when this was written: the round 1 variant results and a trade breakdown of the live rules on windows 1–9 for primary 4H, primary 1D and secondary 1D. Secondary 4H was still being captured. Window 10 was unread.

The breakdown showed that entries taken in the Accumulation regime are flat or negative in all three sets (−$191 over 81 trades, −$282 over 29, −$34 over 76), while Uptrend entries carry all the profit. These entries come from one path: the Strong long for Accumulation and Capitulation (capped to Light long since 9 November). A comment in the code credits that path with a 68% win rate; the replay shows 18% to 36%.

| Name | Switch | Question |
|---|---|---|
| J | `ACCUM_STRONG_OK` off (today on) | Does the engine do better with no entry from the Accumulation / Capitulation Strong long path? |

- J was chosen by looking at windows 1–9, windows 7–9 included. Its selection and confirmation results are therefore not independent evidence; only window 10 is a clean test of it.
- The bar is unchanged: J must pass selection, confirmation and then window 10, as written above. The one holdout read per data set is still one read.
- Entries with Fear & Greed below 40 also lost in all three sets, but on 8 to 26 trades per set. That is too few to judge, so no variant is declared for it; it is reported as context.

## Results (9 November 2026)

**Verdict: no variant clears the bar. Context, not a signal. The live rules stay as they are.**

### Checks

All four captures pass: the lab's `live` rows equal the capture's replay rows and the earlier check run, row for row (primary 4H 115,290 rows; secondary 4H 323,050; secondary 1D 56,756).

Correction to the Method section: `before` (cap off, divergence exit off) reproduces column S of the Strong long study (the run with live context), not column C.

| Windows 1–9, compounded (worst window) | Primary 4H | Secondary 4H | Primary 1D | Secondary 1D |
|---|---|---|---|---|
| `live` | +57.3% (−7.8) | +35.1% (−7.7) | +43.9% (−9.8) | +13.3% (−8.3) |
| `before` | +34.8% (−15.3) | +30.2% (−12.4) | +50.2% (−16.5) | −4.9% (−20.4) |

### Variants: gain against `live`, in points

| Variant | Selection W1–6: P4H, S4H, P1D, S1D | Mean | Confirmation W7–9 mean | W1–9 mean | Bar |
|---|---|---|---|---|---|
| A50 | 0.0, 0.0, 0.0, 0.0 | 0.0 | 0.0 | 0.0 | fails (no change) |
| A60 | −2.4, −0.6, 0.0, 0.0 | −0.8 | 0.0 | −0.8 | fails |
| A70 | −2.4, −1.0, −5.4, −0.6 | −2.3 | +0.1 | −2.5 | fails |
| B15 | −2.2, −0.7, −6.1, −10.1 | −4.8 | −4.0 | −9.4 | fails |
| B10 | −12.6, −5.0, −13.3, −16.2 | −11.8 | −6.5 | −20.1 | fails |
| C | 0.0, +1.1, −0.4, +0.1 | +0.2 | 0.0 | +0.2 | fails (mean below +3) |
| D_greed60 | +1.3, 0.0, +0.8, −0.2 | +0.5 | +0.2 | +0.8 | fails (mean below +3) |
| D_greed80 | +1.6, +0.9, −0.2, +0.6 | +0.7 | +0.1 | +0.9 | fails (mean below +3) |
| D_fear30, D_fear50 | 0.0 everywhere | 0.0 | 0.0 | 0.0 | fails (no change) |
| E | −2.0, −0.4, −1.4, −1.9 | −1.4 | −0.1 | −1.7 | fails |
| G | −1.2, +2.3, −6.8, −1.5 | −1.8 | −1.8 | −4.1 | fails |
| H | −0.3, 0.0, 0.0, 0.0 | −0.1 | 0.0 | −0.1 | fails |
| J (round 2) | +1.3, +1.5, +2.2, −5.5 | −0.1 | −0.1 | −0.2 | fails (mean; secondary 1D worst window 5.5 points worse) |

What this says:
- Stricter entries cost return. Late Uptrend entries (z above 1.0 or 1.5) are where much of the return is: B15 and B10 are the largest losses in the table.
- The Light long threshold of 0.40 is not binding at 0.50 and costs return above it.
- The greed level is nearly neutral between 60 and 80.
- The fear level has no effect in this backtest: only Accumulate signals use it, and the backtest manager does not enter on Accumulate.
- J: the trade breakdown showed Accumulation-regime entries flat or negative, yet removing them helps two sets and hurts two. The breakdown was a misleading guide; the declared test caught it.

### Family F (decay), compounded return in %

| Days of Wait | Primary 4H: W1–6, W7–9 | Secondary 4H: W1–6, W7–9 | Primary 1D: W1–6, W7–9 | Secondary 1D: W1–6, W7–9 |
|---|---|---|---|---|
| 3.3 | **+36.0, +15.6** | **+16.7, +15.8** | +12.0, +9.6 | +14.7, −11.6 |
| 7 | +32.4, +21.0 | +5.3, +14.4 | +16.2, +14.0 | +17.4, −13.1 |
| 10 | +30.6, +19.5 | +5.3, +9.4 | +15.0, +13.8 | +18.1, −8.4 |
| 20 | +34.6, +16.5 | +10.7, +5.1 | **+27.6, +12.7** | **+24.0, −8.7** |
| 40 | +28.6, +13.9 | +15.6, +1.1 | +31.8, +12.7 | +27.1, −11.1 |
| never | +28.3, +13.9 | +15.6, +1.1 | +31.8, +12.7 | +25.7, −11.1 |

Bold is today's rule (20 bars).
- 4H: no level beats today's 3.3 days on windows 1–6 in both sets. Nothing selected.
- 1D: 40 days passes selection (+4.2 and +3.1 points; "never" has the same sign) and fails confirmation (0.0 and −2.4). Not confirmed.
- So 20 bars on each timeframe stands, although it means 3.3 days on one and 20 days on the other. A decay exit helps on 4H: without it primary 4H falls from +57.3% to +46.1% and secondary 4H from +35.1% to +16.8% over windows 1–9.

### Holdout, window 10 (read once per data set, 9 November 2026 23:40–23:43 UTC)

No chosen set, so the read covered `before` and `live` only. The marker file is in a git-ignored folder; this section is the record. Window 10 must not be read again on these data sets.

| Window 10 return | Primary 4H | Secondary 4H | Primary 1D | Secondary 1D |
|---|---|---|---|---|
| `before` | −2.8% | −4.0% | +2.2% | +0.8% |
| `live` | −2.3% | −3.2% | +2.4% | +0.4% |
| Difference | +0.5 | +0.8 | +0.2 | −0.4 |

- The 9 November changes (Strong long capped, top-divergence exit) do not lose out of sample: better in 3 of 4 sets, mean +0.3 points.
- The window was quiet: 17 to 66 trades per set and the same trades and exits under both sets of rules (the difference is position size from the cap). No trim exit fired, so the top-divergence exit was not exercised. This is a weak confirmation, not a strong one.

### Trade breakdown of the live rules, windows 1–9 (context only; in-sample, not a declared test)

- Stop losses are the cost centre: 137 of 321 exits on primary 4H (−$6,592), 100 of 154 on primary 1D (−$5,555), 301 of 417 on secondary 1D (−$5,818). Trim exits carry the gains (+$6,254, +$7,300, +$4,762). Stops were tested in `stop-rules-study.md` and are not reopened here.
- Entries at higher z do better than entries near zero, in agreement with B15 and B10.
- Entries with Fear & Greed below 40 lost in three sets, on 8 to 26 trades each: too few to judge.
- Funding is neutral at nearly every entry (316 of 321 on primary 4H), so the funding rules decide almost nothing in the replay.

### Flaws found in review

| Flaw | Status |
|---|---|
| A code comment credited the Accumulation Strong long path with a 68.4% win rate (n=38). The replay shows 18–36%. | Comment corrected. The path stays (J failed). |
| The Light long block lists the Accumulation regime but has no branch for it. | Harmless; left as is. |
| With crowded funding the Uptrend Light long has no upper z bound. | Tested (H): no measurable effect. Left as is. |
| The fear level has no effect in the backtest: only Accumulate uses it and neither the backtest manager nor the executor enters on Accumulate. | None needed. (Corrected 10 November: an earlier version of this row said the executor enters on Accumulate. It does not; see `entry-quality-study.md`.) |
| The executor has no decay exit; the backtest closes after 20 bars of Wait, which is worth 11 to 18 points on 4H over windows 1–9. | Recommendation for the owner; the executor stays as it is without explicit approval. |
| Decay is counted in bars, so it means 3.3 days on 4H and 20 days on 1D. | Tested (F): today's level is the best supported on each timeframe. |
