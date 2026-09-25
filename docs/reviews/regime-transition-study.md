# Early entry on a pending regime change (25 September 2026)

Question: when a coin shows a pending change from Accumulation or Re-accumulation into Uptrend (the squares in the grid), does entering at square k beat waiting for the confirmed change?

Method (`backend/backtest/transition_study.py`): at every closed candle the live engine runs on the trailing 600-bar window, exactly as the scanner does, so each square is what the grid would have shown at the time. Entry at the next candle's open, exit at the close 10/20 candles later (1D) or 30/60 candles later (4H), 10 bps per side. Binance data to 2026-03-29 (walk-forward windows 1-9; holdout untouched). 1D: 40 coins (study primary + secondary sets), 692 episodes. 4H: 10 primary coins, 1,314 episodes.

## 1D

| Entry point | Episodes | Reaches confirmed Uptrend | Mean 10d | Mean 20d | Median 20d | Win 20d | Median move from here to confirmation |
|---|---:|---:|---:|---:|---:|---:|---:|
| Square 1 | 676 | 50% | +1.9% | +2.7% | -1.5% | 47% | +3.5% |
| Square 2 | 494 | 68% | +2.0% | +3.7% | -1.3% | 47% | +2.2% |
| Square 3 | 420 | 81% | +2.6% | +4.5% | -0.7% | 49% | +1.1% |
| Square 4 | 373 | 91% | +2.8% | +4.9% | +0.1% | 50% | +0.1% |
| Confirmed | 347 | 100% | +3.1% | +5.8% | +0.2% | 50% | - |
| Any Accumulation / Re-accumulation bar | 30,343 | | | -0.5% | -3.1% | 42% | |
| Any Uptrend bar | 28,212 | | | +0.3% | -3.9% | 40% | |

## 4H

| Entry point | Episodes | Reaches confirmation | Mean 30 bars | Mean 60 bars | Median 60 | Win 60 |
|---|---:|---:|---:|---:|---:|---:|
| Square 1 | 1,297 | 50% | +0.7% | +0.7% | -0.8% | 47% |
| Square 2 | 959 | 67% | +0.6% | +1.1% | -0.8% | 47% |
| Square 3 | 805 | 80% | +0.5% | +0.5% | -1.2% | 46% |
| Square 4 | 721 | 90% | +0.2% | +0.4% | -1.5% | 44% |
| Confirmed | 659 | 100% | +0.4% | +0.2% | -1.7% | 44% |
| Any Uptrend bar | 52,726 | | | +1.2% | -0.6% | 48% |

## Reading

- The squares are a real probability: on both timeframes about half of square-1 changes complete, four in five at square 3, nine in ten at square 4.
- On 1D, entering early does not pay. The price you save by not waiting (median 3.5% from square 1, 1.1% from square 3) is smaller than what the false starts cost, so returns rise steadily toward confirmation. A freshly confirmed daily Uptrend is the best entry measured, well above an average Uptrend bar (+5.8% vs +0.3% mean over 20 days), though the median is near zero: the gain comes from a minority of large moves.
- On 4H the squares carry little: no entry point beats simply being in an Uptrend.
- Limits: overlapping episodes, no significance test, mean driven by a few large moves; 2021-2026 only.
