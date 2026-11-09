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
- The backtest manager is not the live executor: the executor has no decay exit, has a breakeven stop and enters on Accumulate. Results describe the rules, not the account.
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
