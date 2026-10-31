# Market heat (the market history page's Chart view)

Asked by the owner (29 October 2026): one large chart in the manner of a trading terminal, indicators added on the price or in panes under it, zoom into any stretch, less busy than the other views; and the share of coins in uptrend, Fear & Greed and the number of profitable traders long "combined should fire some sort of signal", so that "now things are starting rolling over" reads at a glance.

Built as `/market?view=chart` (`frontend/src/components/MarketChartView.jsx`, `MarketChart.jsx`, rules in `frontend/src/utils/marketHeat.js` with tests). Context, not a signal: nothing below has been tested against what followed.

## Definition

- **Heat:** the plain average of the readings a day has, each on 0 to 100: the share of coins in uptrend (the market history's MARKUP share), Fear & Greed, and the share of the profitable traders' positions that are long (`crowd`, all markets, from 1 October 2025). Before October 2025 only the first two exist, so heat is their average. The Uptrend share is required; one reading alone is not a heat.
- **Hot** at 75 or more, **cold** at 25 or less. Round numbers, the same bands Fear & Greed calls extreme.
- **Turns:** "cooling" on the first day the heat is 10 points under the peak of a hot episode (a run that reached 75), counted only within 21 days of that peak; "lifting" on the first day it is 10 points over a cold episode's trough (25 or less), within 21 days. One turn per episode; the next needs the heat back at 75 (or 25) first.
- **State** (the word beside the number): Cooling or Lifting for 30 days after a turn, until the heat passes the peak (or trough) it turned from; otherwise Hot or Cold by zone, with the day the run began; otherwise Neutral.

All thresholds were set as round numbers before any forward return was computed. The turns were seen on the chart against BTC while building the view; no number about what followed them was computed.

## Counts (shape only)

1 May 2021 to 27 October 2026 (the page's daily rows): 2,005 days, three readings on 392 of them (from 1 October 2025).

- Hot on 270 days (47 of them with three readings), cold on 343 (79). Highest 94 (22 November 2024), lowest 6 (June and July 2021).
- 12 cooling turns: 17 Nov 2021, 23 Mar 2024, 27 Nov 2024, 23 Dec 2024, 10 Jan 2025, 2 Aug 2025, 20 Aug 2025, 30 Aug 2025, 11 Oct 2025, 16 May 2026, 8 Oct 2026, 17 Oct 2026; 29 lifting turns (most in 2021-2022, summer 2024 and spring 2025, when cold readings bounced often).
- On 27 October 2026: heat 40 (Uptrend 42, Fear & Greed 48, traders long 30), Cooling since 17 October 2026 (from 76 on 11 October).

## Limits

- The three readings move with price. The share in uptrend and Fear & Greed both rise after a rally; over the rebuilt year the traders' reading tracked BTC's previous 30 days (correlation 0.77) and not the next 30 (-0.05) (docs/reviews/positioning-extremes-study.md). Heat describes the run behind it.
- Two definitions in one line: two readings before October 2025, three after. The traders' reading can move the level by itself (on 27 October 2026 it pulled heat from 45 to 40).
- A turn comes after its peak by construction: it needs the heat 10 points down first.
- The Overheated share (BLOWOFF) is 0 on every day of the history (the engine never names that regime on daily closes, docs/reviews/overheated-regime.md), so it is not offered as an indicator.

## Indicators

On the price: BTC's weekly band, hot and cold days (shaded), heat turns (orange arrows down for cooling, blue up for lifting). In panes under it: Market heat, Uptrend share, Profitable traders, Fear & Greed, Smart money, Whales, Median z, Derive Smart wallets (BTC options). The first three of each group show the first time; the reader's picks are kept in the browser. Scroll or pinch to zoom, drag to move, the range buttons to jump; each pane names its value at the crosshair.

## Proposed declared study (draft, not run; needs the owner's approval)

Question: after a cooling turn, did BTC fall more over the next 30 days than comparable days did; after a lifting turn, did it rise more?

- Turns as defined above, from the page's rows; BTC close to close over 7, 30 and 60 days from the turn's close; a window past the newest close is censored.
- Comparison: the window's days in the same fifth of BTC's previous-30-day change as the turn (as in the positioning study), and 10,000 random draws of as many days from those fifths.
- Verdict ("cooling turns were followed by weaker 30 days than the past month explains", and the mirror for lifting) only with at least 8 turns with a complete 30 days, the median 30-day change at least 5 points below the comparison's (above, for lifting), beyond the 10th (90th) percentile of the random draws, and the same direction in the first and second half of the turns by date. Otherwise "in k of n": context, not a signal.
- In sample is description only (the turns were seen on the chart). Out of sample from 30 October 2026, rerun whenever a turn's 60 days complete.

## Breadth leads (29 October 2026)

Owner's feedback: the share of coins in uptrend matters as much as BTC and should weigh more than an equal third of an average. The headline now leads with the share of coins in uptrend, the broad uptrend's day count and high, and four marks (day 60 or later, greed at 70 or more, traders 86% or more long, rolled over 20 points under the run's high), all as declared in docs/reviews/late-uptrends-study.md; Market heat sits beside it. On the price, broad uptrends are shaded with their day 60 and roll-over marked; the Uptrend share's pane is taller; hot and cold days and the Market heat pane are off by default. The study's in-sample answer for the arrows above: the share fell further than at the same share after 7 of 10 cooling arrows, one check short of the bar, so they stay context.
