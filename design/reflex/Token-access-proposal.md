# Reflex — Hold-to-access proposal

## Core utility

Holding at least **X Reflex tokens** in a verified, supported wallet grants access to the platform. Tokens remain in the user's wallet. No staking, deposit, spending, or recurring token payment is required.

X is intentionally unset. No ticker, contract, launch date, sale, token price, or allocation is assumed in the design.

## User experience

1. Explore the public landing page and illustrative scanner demo without a wallet.
2. Connect a supported wallet and sign a clear authentication message.
3. The backend verifies ownership and checks the eligible token balance.
4. If the balance is at least X, unlock the platform. Equality qualifies.
5. Below X, show the balance, requirement, shortfall, and a recheck action.
6. If verification fails, show an unknown status and retry. Do not call an unavailable balance zero.

Holding access applies to platform use. It does not grant rights to profits, promised yield, or guaranteed trading outcomes. Third-party data and AI usage limits, if needed for operating costs, must be disclosed before launch.

## Recommended eligibility rules

- One verified wallet must meet X. Do not aggregate unrelated wallets by default.
- Start with directly held, transferable balances of the canonical token on the chosen network.
- Choose whether linked HyperCore and HyperEVM balances both count. If both count, reconcile canonical units and never double-count tokens in transfer.
- Do not count exchange omnibus holdings, LP positions, wrapped tokens, vesting balances or staked balances unless explicitly supported and verified.
- Verify eligibility when issuing a session, recheck at least every five minutes during active use, and gate premium API responses server-side. Five minutes is a proposed policy, not a delivered feature.
- Access stops on the next successful below-threshold check. Preserve personal settings and allow re-verification when the balance recovers.
- For provider outages, allow a proposed maximum 15-minute grace period only for recently verified existing sessions. New sessions remain pending; outages must not grant access to an unverified wallet.
- Hold-to-access is a balance check, not a commitment to hold for a minimum duration. A user can transfer tokens and lose access after revalidation. Do not describe this mechanism as preventing balance rotation or temporary acquisition.

## Implementation requirements for the real platform

The delivered design preview does not connect to wallets or verify token balances. It does not alter RCCE_Scanner.

- Replace the existing frontend access code/browser-storage gate with server-verified authentication and authorization.
- Use domain-bound, nonce-based signed messages, expiry, replay protection, and server-managed sessions. Separate authentication from trading permissions.
- Enforce entitlement on protected HTTP endpoints, downloads, and ongoing WebSocket streams; hiding frontend controls is insufficient.
- Use exact integer token units, configured decimals and an explicit contract/token identifier. Reject unsupported chains and malformed addresses.
- Revalidate on wallet changes. Maintain short-lived entitlement caches and explicit unknown/error states.
- Record verification time and access reason; rate-limit checks and protect against replay and request abuse.
- Test balances immediately below, equal to, and above X; account changes; token transfers; provider outages; recovery; and session expiry.

## Decisions required before launch

1. Exact X, evaluated against supply, distribution, liquidity, anticipated users and operating costs.
2. Canonical token identifier, launch route and supported balance locations.
3. Verification cadence, transfer behavior, outage grace period and published fair-use limits.
4. Who may change X, advance notice (suggested: at least 30 days), and treatment of existing holders.
5. Confirmed token distribution, vesting, treasury and liquidity arrangements; appropriate legal review for the intended markets.

## Design handoff

The preview includes a complete landing page, interactive scanner, and three access scenarios: eligible, below X, and verification unavailable. Prices and signals are illustrative. Wallet actions are simulations. The same holding model is used consistently across all three views.
