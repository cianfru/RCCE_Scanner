> Superseded: the user requested historical reconstruction instead. The executor hook and frontend panel were removed; no forward experiment starts on deployment. The isolated simulation library is retained for research/testing.

# Forward shadow study: re-entry discipline and stop placement

Implements the approved next experiment, separately from historical executor
performance. No strategy variant calls a trading engine, places an exchange
order, alters active positions or imports old trades into the new study.

## Three comparable virtual portfolios

Each starts empty with the executor's starting capital on the first eligible
scan after deployment. Every variant receives the same scan prices, whitelist,
pair map and confluence-based sizing. The current whitelist count remains the
allocation denominator, matching the active executor; this experiment does not
also change allocation policy. Available virtual cash, including estimated
costs, bounds new entries. The study is long-only.

1. Baseline: existing entry behavior, fixed 8% hard stop.
2. Reset + 4h: require a non-entry signal after the portfolio's own exit (or at
   that exit), and at least four hours since that exit. Keep the 8% stop.
3. Reset + 4h + volatility stop: same re-entry gate, with distance equal to twice
   the arithmetic mean true range of 14 completed 4H candles, divided by entry
   price and bounded to 4–12%. This is not Wilder-smoothed ATR. Missing/gapped
   candles block this variant's entry rather than substituting a fixed stop.

The volatility stop and size are frozen at entry. If distance exceeds 8%, reduce
notional by 8% / stop distance. If it is tighter, do not increase notional.
Planned dollar stop risk is therefore at or below the baseline allocation risk.
This does not guarantee fills or a maximum realized loss when prices gap.

Every variant retains the current break-even rule: arm after a 5% observed gain
and close at/below entry. Stop checks precede signal exits. A position exiting
on a scan cannot reopen on the same scan. Baseline may reopen on the next scan;
filtered portfolios wait for their own reset and cooldown.

## Accounting and presentation

The executor page includes a separate forward-study table with closed/open
counts, realized/unrealized/combined P&L, an estimated-cost result, and observed
maximum drawdown. The open-stop inspector displays actual entry stop price,
distance, notional and planned dollar risk for each virtual position.

Cost assumption: 0.05% per executed side. Open positions do not reserve an exit
fee; costs are estimates, not verified venue fees. Funding, slippage and market
impact are not included. Drawdown is sampled only when all open marks are fresh
and includes incurred estimated costs. It cannot represent intrabar drawdown.
Marks over six hours old withhold combined P&L. Invalid/future/stale observations
cannot trigger entries or exits. The dormant view shows dashes, not sample gains.

## Operational isolation

`executor_shadow.py` has no exchange client or network dependency. The active
executor passes existing cached observations and candle data before processing
its own orders. A shadow error pauses the study and is reported without stopping
active execution. No extra OHLCV or scanner requests are made.

State is saved independently in `executor_shadow_v1.json` beside the executor
state file. Atomic replacement occurs on virtual trade events and otherwise at
most once a minute. The latest 200 closures per variant are retained for detailed
inspection; cumulative accounting is retained for all closures. Recent waiting
reasons are stored per symbol, not inflated into counts on repeated scans.

Version and sizing/capital fingerprints prevent silently mixing configuration
changes into an existing experiment. Corrupt or incompatible state is not reset
or overwritten. Changes to the active fixed-stop or break-even constants pause
the study. It does not resume by destroying previous results.

The backend must be deployed for the ongoing production scan stream to start
this experiment. A frontend-only deployment or the historical read-only local
proxy cannot gather new shadow results.

## Validation

Tests cover fixed stop placement, volatility bounds and dollar-risk reduction,
re-entry/reset timing, restart continuity, break-even observed fills, estimated
costs, stale marks, missing/gapped/open candles, virtual cash, corrupt/config
state, and isolation of a shadow failure from active execution. The research
rules are provisional hypotheses from the previous replay, not optimized or
validated settings. Compare new net performance, drawdown, turnover and missed
winners before considering any active stop change.
