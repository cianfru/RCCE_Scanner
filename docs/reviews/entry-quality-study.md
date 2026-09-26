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

## Results

### Stage A (1,061 entry events on the primary set, 2,628 on the confirmation set)

**The replays produce only two kinds of long entry: Light long, in Uptrend, and Accumulate, in Re-accumulating or Accumulation.** Strong long and Revival never fire in the historical replay; they need inputs that only exist live (funding, open interest, flow). **None of the replay-based studies has tested Strong long.**

7-day forward returns, as mean, median and share beating the set's average coin:

| | Primary: raw mean | Primary: excess mean / median / share | Confirmation: raw mean | Confirmation: excess mean / median / share |
|---|---:|---|---:|---|
| Light long (n 843 / 2,146) | +1.4% | +0.2% / -0.5% / 46% | +0.9% | -0.4% / -1.6% / 40% |
| Accumulate (n 218 / 479) | -2.1% | -1.3% / -2.0% / 39% | -1.3% | +0.5% / -1.0% / 43% |

- **Light long, the only entry the backtest trades, earns about the market's own move and no more.** Excess return is near zero, and fewer than half of entries beat the average coin.
- The backtest's profits therefore come from being invested when markets rise and from its exits and filters (the 8% stop, decay, the BTC weekly band), not from choosing coins that outperform.
- **No other split holds up on both sets.** Heat of 60 or more is +3.8% excess on the primary set but has a -3.1% median on the confirmation set. Entry checks, confluence and z-score each flip sign or fade between the sets.
- Entries the BTC weekly band blocks are down in raw terms on both sets (-2.2% and -1.2%). The block keeps the backtest out of falling markets, as intended.

### Stage B

**Blacklist chosen on the primary set:** Accumulate in Re-accumulating only (188 events, mean -1.4%, median -2.3% excess). The backtest does not trade Accumulate, so **E1 equals E0 on both sets**: no change, and it does not pass.

| | Primary: compounded / worst DD / median Sharpe | Confirmation: compounded / worst DD / median Sharpe |
|---|---|---|
| E0 (today's backtest) | +43.1% / -10.4% / 0.32 | +45.3% / -14.6% / -0.80 |
| E1 (blacklist) | +43.1% / -10.4% / 0.32 | +45.3% / -14.6% / -0.80 |
| **E2 (+ Accumulate, as the live executor)** | **+24.1% / -16.0% / 0.19** | **+26.9% / -18.3% / -0.73** |

**E2 is 19 and 18 points below E0 on the two sets, with deeper drawdowns.** It meets the declared rule, so the recommendation is to **stop the executor's Accumulate entries.** The backtest has always left them out, and adding them costs return on both coin sets.

### Stage C: the live signal log (description only; the rules changed over the period it covers)

| Production 4H signals | Count with outcomes | Win rate | Avg 1d | Avg 3d | Avg 7d |
|---|---:|---:|---:|---:|---:|
| Accumulate | 3,172 | 36% | +1.2% | -0.4% | -1.4% |
| Light long | 2,167 | 41% | +0.7% | -0.3% | -0.4% |
| Strong long | 1,936 | 43% | -0.2% | 0.0% | -0.4% |
| Trim (price after the exit) | 67 | 84% | -1.6% | -6.6% | **-18.0%** |
| No long (price after) | 641 | 79% | +7.5% | -1.5% | **-8.0%** |

- On the live record, every kind of long entry averaged a small loss over 7 days, over a period that included long declines. Strong long does no better than Light long.
- The exits are what looks informative: price fell 18% on average in the 7 days after a 4H Trim, and 8% after No long.

## Reading

- **The engine's value shows up in when to be out** (the exits, the BTC band, decay), not in picking which coins to buy.
- Its long entries are close to buying the market.
- That fits the stop and sizing studies. Tuning stops or sizes cannot add much, because the entries carry little edge of their own.
- **Next places to look:**
  - treat the engine as a market-timing and risk tool, for example holding a broad basket or BTC when the engine is risk-on and stepping aside when it is not, and test that against today's coin-by-coin trading;
  - study the exits as signals in their own right (Trim and No long look strong), including shorts after them.
