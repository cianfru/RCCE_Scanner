# The Radar: context or signal? Forward test (declared 29 September 2026, before any outcome is recorded)

Question: when the Radar shows a coin as an early setup with profitable traders behind it, did that coin do better than the other coins over the next two weeks? And does buying near where those traders bought (the entry zone) do better than buying the same coins elsewhere?

Nothing in the signals uses the Radar. It is a map for research. Until a hypothesis below clears its bar, the Radar is **context, not a signal**.

Everything below is fixed before the logging code is written and before any reading exists. The only data looked at so far is today's live map (how many coins it holds and how many have 3 or more profitable traders long), to size the table.

Code: logging in `backend/radar_log.py` (table `radar_readings`); scoring in `backend/research/radar_forward.py`, run as `python -m research.radar_forward score`; status at `GET /api/radar/forward-test`.

## Unit: one reading per coin per daily close

- **Close:** the 1D candle close at 00:00 UTC. Day D is the close at 00:00 UTC that ends day D − 1.
- **Reading:** the Radar's 1D state (`setup_map.build` with `tf=1d`, the same code as `/api/setup-map?tf=1d`) taken once per close, after the close is processed:
  - taken at the first check from 30 minutes after the close at which at least 90% of the map's coins have their daily candle ending at D in the stored candles, or at 2 hours after the close, whichever comes first;
  - a close for which no reading was taken within 6 hours is missing. It is never back-filled.
- **Coins:** every perpetual on the map with a z-score (the Radar's "All coins" view). Each reading also records whether the coin is on the default view ("Setups with traders").
- **One reading per coin per close.** A second attempt for the same close writes nothing.
- **Which readings count:** from the first close logged after this code is deployed, and only readings stamped `roster_version` 2 (the roster since PR #183). Readings under another roster version are reported apart and never count.

## What each reading records

| Field | Meaning |
|---|---|
| zone | `watch` (the Early setups box), `late`, `crowded`, `quiet`, `outside` (`setup_map.zone`) |
| stage | forming, fresh, running, stretched, leaving, waiting |
| crowd | quiet, early, crowded, against, holding |
| long, short | profitable traders long and short in the coin; wallets that trade as one (lockstep entities) count once, on the side of their combined dollars |
| net change 24h | (long − short) now minus (long − short) at the stored 4H close nearest 24 hours earlier (within 3 hours); empty when the record has no such close |
| gross USD | the profitable cohort's dollars in the coin, long plus short, valued at entry |
| band state, ring fill | the coin's weekly bull market support band (`setup_map.weekly_band`): `closed_under`, `under_now`, `inside`, `above`, and the ring fill (1 inside, under or closed under; above: clamp(1 − d / 0.30, 0, 1), d = price / band top − 1) |
| z | the engine's z-score on 1D |
| price | the map's price at the reading |
| close | the coin's stored daily candle close for day D (outcomes use this) |
| entry zone | average long entry, distance, in zone (below) |
| shown | on the Radar's default view |
| roster_version, schema_version | the roster rules (2) and the table layout (1) |

## Entry zone (the same rule the Radar draws)

- **Average long entry:** over the profitable traders whose combined dollars in the coin are long (lockstep entities once), the dollar-weighted average of the entry prices of their long positions. Dollars are position sizes valued at entry, as Hyperliquid reports them.
- **Distance:** price / average long entry − 1.
- **In the entry zone:** at least 3 profitable traders long, and the distance within ±3% (inclusive).
- Fewer than 3 traders long: never in the zone. The constants (3 traders, 3%) do not change during this test.

## Outcome

- **Return:** the coin's close at D + 14 over its close at D, minus 1. Secondary: D + 7.
- **Closes:** the logged daily close. Where the reading at D + 14 is missing (a missed close), the stored daily candle for that day. If neither exists (the coin was delisted, or its candles stopped), the event has no outcome: it is listed as unscored and does not count.
- **Benchmark:** the median return over the same window of all coins with a close at both D and D + 14 (at least 20 coins, else the event is unscored). This is "the median coin".
- **Excess:** the coin's return minus the benchmark.
- An event counts once its D + 14 close exists. Before that it is pending.

## Hypotheses

### H1 (primary): an early setup with support

An **event** on coin X at close D when, at D, all of these hold:
1. zone is `watch` (inside the Early setups box);
2. at least 3 profitable traders long;
3. net change 24h is above 0 (long minus short rose against 24 hours earlier);
4. the coin has a weekly band, its state is not `closed_under`, and its ring fill is at least 0.5 (inside or under it now, or at most 15% above its top).

- **First day only:** all four held at D and did not all hold at the coin's previous reading (D − 1; if that close is missing, the latest reading within the 3 days before D; with no such reading D only sets the baseline). At the first counted close nothing is an event: it only sets the baseline.
- **Spacing:** at least 14 days since the coin's previous H1 event. A first day inside 14 days is skipped and not reconsidered later.
- **Measure:** 14-day excess (7-day reported).

### H2: the entry zone

- **Entry-zone events:** coins in the entry zone at D.
- **Comparison:** coins with at least 3 profitable traders long that are not in the entry zone at D.
- **Sampling (same for both groups):** a coin gives an event in a group at the first counted close at which it meets that group's condition, then again at the first close at least 14 days after its previous event in that group at which it meets it.
- **Measure:** 14-day excess of each group; the test is the difference of the group medians (entry zone minus comparison).

### H3 (control, description only): late

- **Event:** z at least 2 and crowd `crowded` at D; first day only and 14-day spacing, as in H1.
- Reported next to H1 to see whether late, crowded coins trail the early ones. No verdict.

## Decision rule (fixed now)

**Minimum before any verdict:** at least 30 scored events, from at least 15 distinct coins. Under that the verdict is "too few". For H2 both groups need 30 scored events, and the entry-zone group 15 distinct coins.

**H1:**
- **fails** if the median 14-day excess is 0 or below;
- **holds** if the median is above 0, the 90% interval of the median lies entirely above 0, and more than 55% of events beat the median coin (excess above 0);
- otherwise **undecided**.

**H2:** the same bars on the difference d = median excess (entry zone) − median excess (comparison):
- **fails** if d is 0 or below;
- **holds** if d is above 0, the 90% interval of d lies entirely above 0, and more than 55% of entry-zone events have an excess above the comparison group's median excess;
- otherwise **undecided**.

**H3:** median excess, its interval and the share above 0; no verdict.

**Interval:** circular moving-block bootstrap over whole calendar days, from the first to the last scored event day, block length 14 days, 2,000 draws, seed 20260929. A draw keeps every event (and for H2 every comparison event) whose close D falls on a drawn day, as many times as that day is drawn; draws with no events are skipped. The 5th and 95th percentiles give the 90% interval.

**7-day figures** are reported and never decide.

## Reports

- Reports at 30, 60 and 90 days after the first counted close. Each applies the rules above to every event scored by then.
- The 90-day report decides. A "holds" at 30 or 60 days stands only if the 90-day report also says "holds".
- If the minimum is not met at 90 days, collection continues with a report every 30 days; the first report that meets the minimum decides.
- The live status (`/api/radar/forward-test`, and one line in the Radar's (i)) shows days logged and events so far. Its running figures are not a verdict.
- No rule changes after the first outcome is seen. Anything added later is labelled exploratory. Every deviation is listed under "Deviations" with its date.

## Honesty notes

- **Survivorship:** the coins are today's Hyperliquid perpetuals and whatever is listed later. A coin delisted inside a window has no outcome and drops out; delistings tend to follow falls, so results can look better than they were.
- **Overlapping windows:** 14-day windows of different coins overlap in time and share market moves. Excess returns remove the common move only in part; the interval draws whole 14-day blocks of days so that overlapping events stay together.
- **Lockstep entities:** wallets that trade as one count as one trader. The grouping is recomputed from their trades, so the same wallets can count as two traders one day and one the next.
- **Roster changes:** who counts as a profitable trader changes as the leaderboard moves. Each reading carries `roster_version`; a change of roster rules splits the record.
- **One snapshot a day:** the reading is a snapshot at the close. What happens between closes is not seen.
- **Not a trading signal** unless its bar is met. Even then it says how Radar events did on average, not what any one coin will do.
- **The owner trades discretionarily.** The Radar is a shortlist for research. This test measures the map's states, not the owner's trades or timing.

## Deviations

31 October 2026, counting by net exposure (owner decision). From the first complete reading of the tracked wallets' Hyperliquid spot and staked holdings after this date, a profitable trader's short covered by the same coin held on spot or staked is not counted, and a partly covered one counts for its uncovered part (`backend/hl_hedges.py`). It changes the map's long/short counts, most of all on HYPE. Readings from then on carry `roster_version` 3. This run counts `roster_version` 2 readings only, so it ends at that date and its reports use the version 2 readings. A run on version 3 readings needs its own declaration before any of its outcomes are seen.

Clarification, 29 September 2026, before any reading was logged: "all coins" in the benchmark means the coins read at close D (the unit above), each with a close at D and D + 14.

## Results

To be added at each report. Nothing above changes.
