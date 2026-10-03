# Reflex (RCCE Scanner)

Crypto scanner for Hyperliquid perps: FastAPI backend on Railway (`backend/`), React + Vite frontend on Vercel (`frontend/`). The repo is private (since 3 Oct 2026); still keep secrets and security details out of code comments and docs.

## Before a public launch

Read `docs/public-launch-plan.md`. It lists what must be done before many users use the app at once (edge cache, stored trader fills, user accounts, rate limits, graceful degradation, scan row deltas) and the cost reasoning behind it.

## Owner's standing rules

- Minimal visible text; visuals first; explanations behind (i) popovers.
- No emojis. No pills: tabs are underlined text.
- No blinking or pulsing status dots. Price flashes and loading spinners are fine.
- No forecast words in the UI (will, expect, likely, predict, target, probability, odds): show what happened, not what will.
- Never show the word "Larsson" in the UI. The paid data it refers to lives only in `backend/data/private/` (tracked in this private repo, excluded from the Docker image); never serve it from the API, the app or public pages.
- The login screen stays as it is.
- Research follows a declared-study protocol: rules committed before results are computed; verdicts only when the declared bar is met, otherwise "context, not a signal".
- Costs stay low (Railway bill is mostly network egress; see `/api/net-stats`). Live or paper trading changes need the owner's explicit approval; the executor stays as it is.
- Wallet tracking is documented in `docs/hyperlens-wallet-tracking.md`.
