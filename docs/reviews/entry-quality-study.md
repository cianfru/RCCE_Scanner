# Entry quality: which entries earn? (declared 26 September 2026, before running)

Question: the stop and sizing studies found little to gain in exits and position size, so the edge, or its absence, sits in the entries. Which of the engine's long entries are followed by gains, which by losses, and does skipping the losing kinds improve results on coins it was not chosen on?

## Data

The 4H replays of today's live logic (Overheated switch off, cool-off off), windows 1-9 only. The holdout after 29 March 2026 is not touched.
- **Primary set:** 10 coins. This is where any choice is made.
- **Confirmation set:** 30 coins. This is where the choice is tested.

## Stage A: describe (both sets)

**An entry event** is a bar whose signal is Strong long, Light long, Accumulate or Revival, when the coin's previous bar had a different signal.

**Forward return** from that bar's close, 6, 18 and 42 bars later (1, 3 and 7 days):
- **raw:** the coin's own return;
- **excess:** the coin's return minus the average return of all coins in the set over the same bars. This takes out the market's move.

Reported as the event count, mean and median return, and the share positive, split by:
- signal;
- signal × regime;
- entry checks met (below 60%, 60-80%, 80% or more);
- confluence;
- heat (below 30, 30-60, 60 or more);
- z-score (below 0, 0-1, 1-2, 2 or more);
- whether the BTC weekly band blocks entries at that moment.

Many cells are shown, so Stage A is description. No cell is a finding by itself.

## Stage B: one declared filter, chosen on the primary set, tested on the confirmation set

**Blacklist, fixed now.** A cell is blacklisted when, on the primary set only, it meets all of:
- it is a signal × regime cell with at least 30 entry events;
- its mean 7-day excess return is below zero;
- its median 7-day excess return is also below zero.

**Variants**, scored with the costed PositionManager exactly as in the stop and sizing studies (exits, sizing, BTC band block unchanged):
- **E0:** today's backtest rules (baseline).
- **E1:** E0, but entries in blacklisted cells are not taken.
- **E2 (executor parity):** E0 plus Accumulate entries, sized as the live executor sizes them (15-25% of a slot, and it can add to an open position). The backtest leaves Accumulate out; the live executor trades it.

**Decision rule (fixed now):**
- **E1** is recommended as an entry filter only if, on the confirmation set:
  - its compounded return is at least 5 points above E0's;
  - its median Sharpe is at least E0's;
  - its worst-window drawdown is no more than 2 points deeper.

  Its primary-set result is shown but does not count, since the blacklist was chosen there. A filter that passes would go through a forward test before touching the live signal.
- **E2:** if it is at least 5 points below E0 on both sets, the recommendation is to stop the executor's Accumulate entries. Otherwise nothing changes.

## Stage C: the live signal log (description only)

Production's recorded signals and their measured outcomes are compared, where available, with Stage A. The live rules changed over the months the log covers, so this is a cross-check, not a test.
