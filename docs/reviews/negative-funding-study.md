# Extreme negative funding and price spikes (declared 19 November 2026, before running)

The owner's question (19 November 2026), about INIT on Hyperliquid at about -1,800% a year of funding: "when there is such an extreme case of negative funding rates lately, has this led to spikes ... maybe it's just coincidence that the last two rounds, this is what happened."

**Question:** after a perp's funding first turns extremely negative, does its price spike up within the next 7 days more often than at ordinary times on the same coins?

This describes the past and runs outside the production server. Everything below is fixed before any outcome is computed. Unless the bar is met on both venues, the result reads **context, not a signal**. Nothing in the app, the engine or the executor changes.

Code: `backend/research/negative_funding.py`, tests in `backend/tests/test_negative_funding.py`.

## Known before running

- INIT on Hyperliquid, looked at on 19 November with the owner:
  - **February 2026.** Funding went deeply negative from 11 February, with a low of -1.83% an hour on 15 February. Price went from $0.071 to a high of $0.149 on 16 February, then fell back to about $0.08 by the end of the month.
  - **November 2026.** Funding turned negative at 09:00 UTC on 9 November. Price went from $0.128 to $0.283 on 10 November, then fell to $0.088 by 17 November, while funding stayed negative.
- The February episode is inside the window below. The November one is not: the window ends with October 2026.
- No other coin or venue has been looked at.

## Data

- **Window.** Data from 1 November 2025 to 31 October 2026, the twelve months Binance's monthly archive covers.
  - Events from 8 November 2025: each needs 7 days of funding before it.
  - Events before 25 October 2026: each needs 7 days of price after it.
- **Hyperliquid** (`hl`): every perp in the main dex's meta, listed and delisted. Hourly funding from `fundingHistory`, 4-hour candles from `candleSnapshot`.
- **Binance** (`bn`): every USDT-margined perpetual in the public archive (data.binance.vision), listed and delisted. Funding prints with their interval, and 4-hour klines, from the monthly files.
- A coin with no candles in the window is left out and counted.

## Definitions

- **Funding per hour:** each print's rate divided by its interval in hours. Hyperliquid prints every hour. Binance prints every 8, 4 or 1 hours, depending on the contract and the time.
- **Event:** a funding print at **-0.1% an hour or lower** (about -876% a year), with no print at or below that in the 7 days before it.
  - The 7-day rule makes each event the start of an episode. Prints in the same episode do not count again.
  - **Secondary threshold, reported but not judged:** -0.2% an hour (about -1,750% a year), INIT's level on 19 November.
- **Entry:** the close of the first 4-hour candle that closes at or after the print. Funding for an hour is known at the end of that hour, so the entry comes up to 4 hours after it.
- **Outcomes, measured from the entry:**
  - the return to the close 24 hours, 3 days and 7 days later;
  - the highest high and lowest low within the 7 days;
  - a **spike**: a high 30% or more above the entry within 7 days;
  - a **drop**: a low 30% or more below the entry within 7 days;
  - the funding a long would have received over the 7 days.

  A coin whose candles end within the 7 days (delisted) uses its last close and is flagged.
- **Comparison ("ordinary times"):** every 4-hour close of the same coins (those with at least one event on that venue), in the event window, with no print at or below -0.1% an hour in the 7 days up to it. The same outcomes are measured.
- **Mirror (context, no verdict):** the same with funding at **+0.1% an hour or higher**.

## The bar (fixed now)

On one venue, the events meet the bar only if all of these hold:
1. there are at least **30 events**;
2. the share of events followed by a spike is **at least twice the comparison's share**;
3. an exact one-sided binomial test of that share, against the comparison's share, gives **p of 0.01 or less**;
4. the **median 7-day return after events is above 0** and above the comparison's median;
5. splitting the events at their median date, **each half's spike share is above the comparison's**.

The result reads "extreme negative funding was followed by spikes more often than ordinary times" **only if both venues meet the bar**. Otherwise it reads **context, not a signal**.

Binance's data is complete first and may be reported first. The verdict waits for Hyperliquid.

## Also reported (context, no verdict)

For events, the comparison, the secondary threshold and the mirror:
- the share up and the median return at 24 hours, 3 days and 7 days;
- the spike and drop shares;
- the median highest high and lowest low;
- the median funding a long would have received;
- the median 7-day return plus that funding.

Also: the list of events (coin, date, rate, outcomes), the number of coins and of distinct days.

## Limits

- **Events cluster.** A market-wide move can push many coins' funding past the threshold on the same day. Their outcomes are not independent, so the binomial p is optimistic. The number of distinct days is reported, and condition 5 asks for both halves of the period.
- **Spikes are measured on highs.** A 4-hour high can come from a wick a trader could not have sold into.
- **Entry lag.** Entering at the next 4-hour close misses a move that came within those hours.
- **What the comparison means.** Coins with extreme funding are volatile, which is why the comparison is the same coins at other times. It does not hold everything else equal: an event can follow a crash or come during a pump.
- **This does not test cause.** Funding follows positioning. The study can show whether spikes followed, not why, or whether anyone arranged them.
- **Twelve months, two venues.** The same coins often trade on both, so the venues are not fully independent.
