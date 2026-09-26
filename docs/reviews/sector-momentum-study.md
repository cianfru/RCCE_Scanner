# Sector momentum study (declared 26 September 2026, before running)

Question: when a sector or ecosystem has beaten BTC recently, does it keep beating BTC over the next 10 days? If yes, relative strength could become a ranking input (Best setups, priority). If not, the race chart and pockets stay descriptive.

## Data

- Coins: every coin in `backend/sectors.py` with a Binance USDT spot pair (k-prefixed Hyperliquid tickers map to the plain ticker, e.g. kPEPE to PEPEUSDT). BTC is the benchmark and is not in any group.
- Daily closes, 2021-01-01 to 2026-03-29 (walk-forward windows 1 to 9). The holdout window (W10) is not touched.
- Groups: the curated sector and ecosystem labels of today. A group counts on a day only when at least 3 of its members have prices that day.
- Known bias: the coin list is today's Hyperliquid universe, so coins that died before 2026 are missing (survivorship). This flatters every group about equally; it does not by itself create momentum, but results should be read as optimistic.

## Measures

For each day t and each group, the group's move is the median daily log return of its members, chained. Its relative move is that minus BTC's log return.

- Past strength: relative move over the L days to t, for L = 7 and L = 30.
- Outcome: relative move over the next 10 days (t to t+10).

Tests, each on non-overlapping 10-day steps (so every observation is independent in time), sectors and ecosystems separately:

1. Rank correlation (Spearman) across groups between past strength and outcome, averaged over steps; t-statistic of the mean.
2. Leader minus laggard: the outcome of the strongest group minus the weakest; mean, share positive, t-statistic.
3. Leader against BTC: the strongest group's outcome alone; mean and share positive.
4. Per window (1 to 9): the mean leader-minus-laggard spread, to see whether any effect is stable or one regime.

## Decision rule (fixed now)

Relative strength becomes a candidate ranking input only if, for at least one of L = 7 or 30, on sectors or ecosystems: the mean rank correlation is positive with t >= 2, the leader-minus-laggard spread is positive with t >= 2, and the spread is positive in at least 6 of the 9 windows. A candidate would still need a separate test inside the signal replay before it touches rankings. Otherwise the views remain descriptive, and the UI keeps saying so.

## Results (run 26 September 2026, windows 1-9)

149 of 183 listed coins had Binance daily history. Groups with 3+ members: 11 sectors (Majors has only ETH besides BTC and drops out), 7 ecosystems. Non-overlapping 10-day steps: ~190 for sectors (2021 onward), ~78 for ecosystems (most chains only have 3+ listed members from late 2023).

| Test | Rank corr. (t) | Leader minus laggard, 10d (t) | Windows positive | Rule |
|---|---:|---:|---:|---|
| Sectors, 7-day strength | 0.02 (0.6) | +1.6% (1.5) | 6/9 | fails |
| **Sectors, 30-day strength** | **0.13 (4.3)** | **+3.8% (3.7)**, positive 59% | **8/9** | **passes** |
| Ecosystems, 7-day | -0.04 (-0.7) | +0.5% (0.5) | 2/5 | fails |
| Ecosystems, 30-day | -0.02 (-0.3) | +1.1% (1.4) | 4/5 | fails |

Per window, sectors 30-day spread (%): 6.0, 4.2, 1.1, 2.3, 8.2, 1.9, 6.9, 0.0, 7.9.

Against BTC, as a trade (equal-weight basket of the leading sector, simple returns, before costs and funding):

| | Sectors 30-day leader | Average sector |
|---|---:|---:|
| Mean 10-day return minus BTC | +2.7% | +0.2% |
| Median | -1.9% | |
| Share of 10-day periods beating BTC | 42% | |

(The median-log index used for ranking understates basket returns by volatility drag, so it reads lower against BTC: leader -2.6%, average -4.6%. The basket numbers are the ones a trade would see.)

## Reading

- **30-day sector leadership persists against other sectors.** The strongest sector over the last 30 days beat the weakest over the next 10 days by 3.8% on average, in 8 of 9 windows. It meets the declared rule, so relative strength is a candidate ranking input for choosing *between* altcoins.
- **It is not a reliable long-sector / short-BTC trade.** The leading sector beat BTC in only 42% of 10-day periods. The positive mean comes from a few large runs; the typical period lost about 2% to BTC before costs and funding.
- **7-day strength and ecosystems show nothing.** Short bursts reverse as often as they continue; ecosystems have too little history and too few members per chain.
- Survivorship: the coin list is today's universe, so absolute returns are flattering. The ranking result (leader against laggard, both drawn from the same survivors) is less affected.

## Next step

Per the declared rule, the candidate is sector 30-day strength as a tilt inside the signal replay (e.g. prefer setups in the top-third sectors, avoid the bottom third), scored by the same costed PositionManager. Until that passes, rankings are unchanged and the race chart and pockets stay descriptive; their help text notes the 30-day persistence finding.

# Sector tilt inside the signal replay (declared 26 September 2026, before running)

The follow-up named above: does leaning entries toward strong sectors improve the tested strategy?

## Setup

- **Replay:** today's live logic (4h, what the executor trades) through the same replay engine and costed PositionManager as the signal integrity audit, windows 1-9, holdout untouched.
- **Universe:** a new, sector-balanced set chosen by a fixed rule, not by results: BTC and ETH, plus for each other sector the 4 coins with the highest average daily USDT volume among those listed on Binance before July 2022 (stablecoin and gold tokens excluded). About 40 coins. The replay is run once; every variant is scored on the same signals.
- **Sector strength at each bar:** as in the study: median daily log return of each sector's members minus BTC's, summed over the last 30 closed daily candles, using all 149 coins with history (not only the traded ones). Sectors need 3+ members that day. Ranked; top third and bottom third (rounded up).
- **Variants** (exits, stops and open positions untouched; only new entries are filtered):
  - B: no tilt.
  - T1, avoid laggards: new entries in bottom-third sectors are skipped.
  - T2, leaders only: new entries only in top-third sectors.
  - BTC and ETH (Majors, not ranked) are always allowed.

## Decision rule (fixed now)

A variant passes if, against B: higher compounded return over windows 1-9, a worst-window drawdown no more than 2 points worse, and a return at least equal to B's in 6 or more of the 9 windows. A passing variant would first be shown in the product (e.g. Best setups preferring leading sectors) and run as a forward shadow before the executor uses it. If neither passes, sector strength stays descriptive.

## Tilt results (run 26 September 2026, windows 1-9)

38 coins (37 in W1, 34 by W9 as MATIC and RNDR were renamed on Binance), 4h replay of today's live logic, same costed PositionManager and BTC weekly block for every variant.

| Variant | Compounded | Worst window DD | Trades | Windows at least B | Rule |
|---|---:|---:|---:|---:|---|
| B: no tilt | **+65.5%** | -13.3% | 955 | | |
| T1: skip entries in bottom-third sectors | +59.0% | -11.3% | 774 | 4/9 | fails |
| T2: entries only in top-third sectors | +42.3% | **-8.3%** | 576 | 4/9 | fails |

Per window (%):

| | W1 | W2 | W3 | W4 | W5 | W6 | W7 | W8 | W9 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| B | 0.6 | 0.0 | 9.6 | -4.5 | 42.8 | -2.2 | 15.0 | -1.7 | -0.4 |
| T1 | -0.7 | 0.0 | 9.5 | -2.3 | 40.3 | -0.7 | 9.6 | -2.0 | -0.1 |
| T2 | -0.6 | 0.0 | 5.9 | -1.3 | 33.1 | 0.1 | 4.6 | -2.0 | 0.3 |

## Reading

- **Neither tilt passes.** Filtering entries by sector strength lowers compounded return (-6.5 and -23 points) and wins only 4 of 9 windows.
- What it does is cut exposure: fewer trades, smaller losses in the weak windows (W4, W6, W9), much smaller gains in the strong ones (W5, W7). T2 has the lowest drawdown, but for the return given up that is simply trading less, not better selection.
- So the persistence found above (leaders beat laggards by 3.8% over 10 days) does not add to the RCCE signals: the engine's own entry conditions already select much of the same strength, and blocking the rest mostly removes good trades along with bad ones.
- Decision (per the declared rule): sector strength stays descriptive. Rankings, Best setups and the executor are unchanged. The race chart and pockets remain a view of where the market is moving, not an input.
