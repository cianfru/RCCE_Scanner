"""Hyperliquid wallet cohorts: how the crowd is positioned, by account size and by all-time PnL.

assign.py  cohort rules and aggregation (pure)
source.py  where wallet states come from (API poller now; an hl-node snapshot reader can replace it)
store.py   SQLite tables (registry, latest state, cohort time series, sweep audit)
sweeper.py the Tier 2 sweep: rate-limited, resumable, adaptive
"""
