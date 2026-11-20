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

## Results (run 19 November 2026)

**Verdict: context, not a signal.** The bar is not met on either venue. On Binance, spikes came about twice as often as at ordinary times, but just under the declared ratio, and the median coin was lower a week later. On Hyperliquid, spikes came barely more often than at ordinary times.

What happened after a coin's funding first went to -0.1% an hour or lower:
- **Spikes:** a high 30% or more above the entry within 7 days came 18.8% of the time on Binance (ordinary times 9.9%) and 10.4% on Hyperliquid (ordinary times 9.1%).
- **Drops:** a low 30% or more below the entry came 20.2% of the time on Binance (ordinary times 3.4%) and 9.9% on Hyperliquid (ordinary times 2.4%).
- **Direction:** the median coin was 10.6% lower after 7 days on Binance and 10.0% lower on Hyperliquid. About one in four was higher (23.8% and 21.4%), against about four in ten at ordinary times.
- **Funding:** a long collected a median 2.5% (Binance) and 2.0% (Hyperliquid) over the 7 days, and was still down a median 7.1% and 7.4% after it.

INIT's February 2026 spike is one of the minority cases. On Hyperliquid, INIT had five episodes in the window: February went 124% above the entry within the week; the other four did not spike, and one went 47% below the entry and ended the week 36% lower.

### Data

- **Binance:** 924 USDT perpetuals in the archive, 850 with funding prints in the window, 846 with candles. Primary events: 1,105 on 403 coins and 323 distinct days.
- **Hyperliquid:** 235 perps in the meta, all with funding prints, 199 with candles. The 36 without candles were delisted before the window; none had a print at or below the threshold. Primary events: 355 on 89 coins and 205 distinct days.
- The coins with the most Hyperliquid events: ACE 14, ANIME 11, LAYER 11, MOVE 11, SOPH 9, SUPER 9.

### The bar (primary threshold, -0.1% an hour)

| Condition | Binance | Hyperliquid |
|---|---|---|
| Events (at least 30) | 1105 | 355 |
| Spike share, events | 18.8% | 10.4% |
| Spike share, comparison | 9.9% | 9.1% |
| Ratio (at least 2.0) | 1.90 not met | 1.14 not met |
| Binomial p (0.01 or less) | 1.9e-19 met | 2.2e-01 not met |
| Median 7-day return, events (above 0 and the comparison) | -10.6% not met | -10.0% not met |
| Median 7-day return, comparison | -0.9% | -2.2% |
| Spike share, first and second half (each above the comparison) | 18.8% and 18.8% met | 14.7% and 6.2% not met |
| Bar | **not met** | **not met** |

### Binance

**Primary, -0.1% an hour or lower** (1105 events on 403 coins and 323 days)

| | Events | Comparison |
|---|---|---|
| Higher after 24 hours | 26.2% | 43.8% |
| Median 24-hour return | -6.0% | +0.0% |
| Higher after 3 days | 25.6% | 42.0% |
| Median 3-day return | -7.9% | -0.3% |
| Higher after 7 days | 23.8% | 40.1% |
| Median 7-day return | -10.6% | -0.9% |
| Spike (high 30% or more above entry) | 18.8% | 9.9% |
| Drop (low 30% or more below entry) | 20.2% | 3.4% |
| Median highest high | +7.9% | +6.9% |
| Median lowest low | -18.1% | -7.5% |
| Median funding a long received | +2.5% | -0.1% |
| Median 7-day return plus that funding | -7.1% | -0.9% |

**Secondary, -0.2% an hour or lower (not judged)** (620 events on 295 coins and 265 days)

| | Events | Comparison |
|---|---|---|
| Higher after 24 hours | 25.0% | 43.9% |
| Median 24-hour return | -8.0% | -0.0% |
| Higher after 3 days | 22.9% | 42.0% |
| Median 3-day return | -10.9% | -0.4% |
| Higher after 7 days | 19.2% | 40.1% |
| Median 7-day return | -13.9% | -1.1% |
| Spike (high 30% or more above entry) | 20.3% | 10.9% |
| Drop (low 30% or more below entry) | 28.5% | 3.9% |
| Median highest high | +7.7% | +7.2% |
| Median lowest low | -21.3% | -7.8% |
| Median funding a long received | +4.7% | -0.1% |
| Median 7-day return plus that funding | -8.1% | -1.0% |

**Mirror, +0.1% an hour or higher (not judged)** (74 events on 55 coins and 62 days)

| | Events | Comparison |
|---|---|---|
| Higher after 24 hours | 47.3% | 35.8% |
| Median 24-hour return | -0.5% | +0.0% |
| Higher after 3 days | 40.5% | 34.3% |
| Median 3-day return | -5.3% | +0.0% |
| Higher after 7 days | 41.9% | 33.0% |
| Median 7-day return | -5.8% | +0.0% |
| Spike (high 30% or more above entry) | 36.5% | 12.3% |
| Drop (low 30% or more below entry) | 35.1% | 7.8% |
| Median highest high | +14.9% | +5.2% |
| Median lowest low | -17.7% | -6.2% |
| Median funding a long received | -0.7% | -0.2% |
| Median 7-day return plus that funding | -6.5% | +0.0% |

### Hyperliquid

**Primary, -0.1% an hour or lower** (355 events on 89 coins and 205 days)

| | Events | Comparison |
|---|---|---|
| Higher after 24 hours | 22.0% | 45.9% |
| Median 24-hour return | -5.3% | -0.3% |
| Higher after 3 days | 22.3% | 43.6% |
| Median 3-day return | -7.3% | -1.0% |
| Higher after 7 days | 21.4% | 41.1% |
| Median 7-day return | -10.0% | -2.2% |
| Spike (high 30% or more above entry) | 10.4% | 9.1% |
| Drop (low 30% or more below entry) | 9.9% | 2.4% |
| Median highest high | +7.4% | +7.4% |
| Median lowest low | -15.6% | -8.2% |
| Median funding a long received | +2.0% | -0.1% |
| Median 7-day return plus that funding | -7.4% | -2.0% |

**Secondary, -0.2% an hour or lower (not judged)** (232 events on 73 coins and 161 days)

| | Events | Comparison |
|---|---|---|
| Higher after 24 hours | 21.1% | 45.9% |
| Median 24-hour return | -6.4% | -0.3% |
| Higher after 3 days | 21.6% | 43.5% |
| Median 3-day return | -8.9% | -1.0% |
| Higher after 7 days | 18.1% | 41.0% |
| Median 7-day return | -12.3% | -2.2% |
| Spike (high 30% or more above entry) | 12.1% | 9.3% |
| Drop (low 30% or more below entry) | 12.9% | 2.4% |
| Median highest high | +6.8% | +7.5% |
| Median lowest low | -17.5% | -8.2% |
| Median funding a long received | +2.9% | -0.0% |
| Median 7-day return plus that funding | -8.9% | -2.0% |

**Mirror, +0.1% an hour or higher (not judged)** (21 events on 12 coins and 19 days)

| | Events | Comparison |
|---|---|---|
| Higher after 24 hours | 33.3% | 44.1% |
| Median 24-hour return | -1.9% | -0.5% |
| Higher after 3 days | 42.9% | 41.3% |
| Median 3-day return | -1.0% | -1.3% |
| Higher after 7 days | 47.6% | 39.1% |
| Median 7-day return | -2.2% | -2.8% |
| Spike (high 30% or more above entry) | 38.1% | 12.7% |
| Drop (low 30% or more below entry) | 28.6% | 5.8% |
| Median highest high | +15.9% | +7.8% |
| Median lowest low | -18.5% | -9.5% |
| Median funding a long received | -1.5% | -0.2% |
| Median 7-day return plus that funding | -5.5% | -2.9% |

### By depth of the first print (described after the run)

| Venue | First print (per hour) | Events | Spike | Drop | Median 7-day return |
|---|---|---|---|---|---|
| Binance | -0.1% to -0.2% | 707 | 19.4% | 17.3% | -8.9% |
| Binance | -0.2% to -0.5% | 318 | 17.0% | 23.6% | -14.1% |
| Binance | -0.5% or lower | 80 | 21.2% | 32.5% | -10.0% |
| Hyperliquid | -0.1% to -0.2% | 242 | 8.7% | 8.7% | -8.7% |
| Hyperliquid | -0.2% to -0.5% | 95 | 12.6% | 12.6% | -12.6% |
| Hyperliquid | -0.5% or lower | 18 | 22.2% | 11.1% | -12.2% |

### INIT

| Venue | Event (UTC) | Rate per hour | Highest high | Lowest low | 7-day return |
|---|---|---|---|---|---|
| Binance | 2025-12-27 00:00 | -0.102% | +3.2% | -17.8% | -8.7% |
| Binance | 2026-02-11 12:00 | -0.110% | +117.4% | -3.8% | +61.3% |
| Hyperliquid | 2025-12-26 09:00 | -0.183% | +14.7% | -8.6% | -1.9% |
| Hyperliquid | 2026-01-11 03:00 | -0.110% | +12.5% | -13.0% | -0.5% |
| Hyperliquid | 2026-01-31 07:00 | -0.140% | +0.6% | -47.0% | -36.1% |
| Hyperliquid | 2026-02-11 07:00 | -0.100% | +123.9% | -0.1% | +61.1% |
| Hyperliquid | 2026-03-24 20:00 | -0.111% | +1.0% | -16.6% | -14.4% |

### Other counts

Events on a coin whose candles ended within the 7 days: Binance 1, Hyperliquid 1.

Primary events by month:

| Month | Binance | Hyperliquid |
|---|---|---|
| 2025-11 | 97 | 38 |
| 2025-12 | 116 | 48 |
| 2026-01 | 107 | 37 |
| 2026-02 | 124 | 49 |
| 2026-03 | 117 | 47 |
| 2026-04 | 127 | 49 |
| 2026-05 | 67 | 25 |
| 2026-06 | 84 | 19 |
| 2026-07 | 75 | 10 |
| 2026-08 | 68 | 12 |
| 2026-09 | 73 | 11 |
| 2026-10 | 50 | 10 |

### Two prints at one time (Binance; described after the run)

Binance's archive holds two funding prints at the same minute, with different rates, on 56 symbols (88 times), nearly all stock and index perps (AAPL, NVDA, SPY and others). 62 primary events start at such a time. Hyperliquid has none.

Without those 56 symbols (events and comparison): 1,042 events on 363 coins; spike share 20.0% against 10.4% (ratio 1.93); median 7-day return -12.0% against -1.0%; drop share 21.4% against 3.6%. The same two conditions fail; the reading does not change.

### Independent check

A separate script, written from this doc rather than the module, recomputed the event count, comparison count, both spike shares and both median 7-day returns on each venue. All twelve numbers match the module exactly.

### What follows

Nothing changes in the app, the engine or the executor. Extreme negative funding marks a coin in a violent phase, both ways: on Binance a 30% spike within a week came twice as often as usual, and a 30% drop six times as often. The more common path was lower. The study cannot say whether anyone arranged a spike.

### Deviations

1. **Binance symbol names.** One archive symbol is not ASCII; the URLs are now percent-encoded. Fixed before any result was computed (f042203).
2. **Binomial tail.** The first Binance run stopped with an overflow before printing any result; the tail is now computed in logs (f042203). Neither fix changes a rule.
3. **Event list.** After the first Binance run, 62 events showed a rate above the threshold: where two prints share a time, the list recorded the second. It now records the print that met the threshold (1a20d2d). Detection, outcomes and the verdict are unchanged; the "by depth" table uses the corrected rates.
4. **Order of reporting.** Binance was reported to the owner first, as declared, before Hyperliquid's data was complete.
5. **Hyperliquid download.** It ran in two parts (a time limit on background jobs); the second part read only the coins the first had not.
