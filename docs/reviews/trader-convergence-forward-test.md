# Profitable traders converging on a coin: forward test (declared 26 September 2026, before any data)

Question: when several profitable traders open the same side of a coin at about the same time and price, before the coin is crowded, does price tend to follow?

Nothing in the signals uses this. It is recorded, drawn on the coin chart and sent as a notification. Whether it means anything is measured here.

## What is recorded (backend/convergence.py)

- **Wallets:** the tracked roster.
  - Profitable traders: the HyperLens definition, the top 300 by monthly return that were also in profit before this month.
  - Large accounts: the top 300 by account value.
- **Filters:** the same as the consensus. The wallet has a fresh reading, at most 25 positions and at least $50K of account value. Builder-dex markets are excluded.
- **An open:** at a sweep reading (about every 30 minutes), a coin and side the wallet did not hold at its previous reading.
  - It is timed at the reading, at the position's entry price.
  - A wallet's first reading after a restart only sets its baseline.
- **A convergence** needs all of the following:
  - at least 2 profitable traders open the same side of one coin within 24 hours;
  - each of them still holds the position;
  - each open was seen within 2 hours of that wallet's previous reading;
  - the latest entry price is within 5% of the first;
  - at most 2 other profitable traders already hold that side.
- **Recording:** it is recorded once, and again only if more wallets join (2, then 3, and so on). Large accounts are drawn on the chart but never count toward a convergence.

## How it is judged

- **Outcome:** for each convergence (the first record of each cluster), the return in the cluster's direction 1, 3 and 7 days after detection, measured from the price at detection (Hyperliquid closes).
- **Comparison:** every profitable-trader open that is not part of a convergence, measured the same way from its own reading.
- **Verdict:** after 30 convergences, on the 3-day return:
  - **holds** if the median directional return of convergences beats the single opens' median by at least 1 point, and at least 55% of convergences are positive;
  - **fails** if their median is at or below the single opens' median;
  - anything in between keeps collecting until 60 convergences, then the same rule applies with no middle ground.
- **Also reported:** convergences of 3 or more wallets are reported separately, as description only.
- **No tuning:** the thresholds above do not change before the verdict. A new variant would need its own declaration and would start its own count.
