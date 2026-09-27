# Product design and audit implementation

Implemented on `feat/reflex-product-audit`, based on `74fb4c1` from main. The existing landing work was carried forward from the separate design checkout without modifying that checkout.

## Design direction

Keep Reflex's Bricolage/Geist typography, original ribbon artwork and Hyperliquid dark palette. Extend the brushed-metal character with a small, static R tile in section introductions; retain quiet, flat reading surfaces for charts and tables. The tile has a light-mode treatment. Shared spacing, readable section headings, restrained panel depth and persistent desktop navigation connect the secondary tools to the scanner. Watchlist controls remain accessible from desktop navigation and the mobile drawer.

## Delivered changes

- **Navigation and research continuity:** URL-backed market, timeframe, search, sector and sort; 4H survives drilldown; return restores the scanner filters and scroll position. Coin detail identifies the active context and carries it to AI Assist. Positioning links explicitly open the engine's 4H view.
- **Scanner and charts:** collapsible market/sector context, direct jump to the grid, accessible symbol links, favorite buttons and sorting. Price, Structure and Trader positioning layer presets reduce initial chart clutter.
- **Hyperlens:** scope labels distinguish cohort data from global activity; wallet counts are distinguished from size weighting. Initial loading, last-successful-read and retry states replace misleading zero readings. Cohorts explains collection cadence and missing readings.
- **Signal History:** USDC symbol formatting, WAIT distinguished from directional opposition, keyboard-selectable heatmap cells and a persistent selected-cell readout. Streak copy describes daily snapshots rather than continuous intraday state.
- **Analytics:** larger headings and explanations, wrapping combination cards, mobile table fit, sample-size qualification and explicit disclosure that the API does not report the observation date range.
- **Backtest:** persistent job references, resumable polling with timeout/backoff, recent server runs and browser-local named configurations. Model assumptions and the server's temporary scanner pause are visible before starting a run.
- **AI Assist:** visible market/timeframe context, response cancellation/timeout and prompt restoration after failure; conversations are separated by timeframe.
- **Portfolio and Executor:** last successful data is retained on refresh errors. Reads from a previous wallet cannot replace the current account's data. Initial account readings are not shown as zero balances. Exchange success and journal failure have separate outcomes, including persistent order references. Control failures are surfaced instead of silently ignored.
- **Administration/access:** server controls moved to their own page; unavailable configuration cannot masquerade as disabled flags. Keyboard navigation and focus return improved. The password gate remains; public copy explains private-preview access. No contact/request-access flow was added.
- **Public experience/performance:** preserved liquid CTA, actual icons, scanner grid and trader-positioning illustrations; added metadata, public sitemap and a 404 screen. Research tools and wallet/chart dependencies load separately from the public page. The sculpture starts near the viewport, keeps its R silhouette during motion, and uses a static mark for reduced motion. Logo and texture payloads use lossless WebP with pixel equality verified.

## Verification

- `npm run build --prefix frontend`: passed.
- `node --test frontend/src/utils/*.test.js`: 87 passing, zero failures. Added navigation/symbol/WAIT semantics and exchange-versus-journal failure cases.
- `git diff --check`: passed.
- Browser review of Scanner, coin detail, Hyperlens, Signal History, Analytics, TradFi, AI Assist, Backtest, Executor, Portfolio and Administration through a development-only visual fixture.
- Tested 4H + BTC search → BTC detail → scanner; both search and timeframe restored.
- Keyboard heatmap selection, mobile drawer Escape/focus return, mobile Analytics/Hyperlens at 390px, desktop at 1440px, light-mode Analytics, and deliberately failed Executor reads.
- Public landing and protected access screen reviewed locally. The local public data feed can be unavailable without a backend; that state is labeled and has retry.
- Public entry JS approximately 404 KB / 131 KB gzip, versus about 1.23 MB / 372 KB gzip before splitting. Three.js remains an optional 747 KB chunk and causes Vite's size warning. These are build sizes, not measured production load times.
- Ribbon embedded image and surface texture each reduced from 1,905,586 to 1,353,208 bytes with identical decoded RGBA pixels.

## Preview and verification limits

Run the frontend dev server and open `/audit-preview.html?route=/analytics` (or another app route). The page labels all data illustrative. It has no wallet provider and rejects API mutations; it is not included as a production build entry. Append `&failure=executor` to exercise a failed Executor feed.

No production deployment, real orders, cancellations, admin changes, live backtests or AI messages were submitted. Connected-wallet behavior and server-side job execution still require integration validation in an appropriate environment. The backend strategy and execution model were not changed. The existing journal endpoints are not idempotent, so this change does not automatically retry journal writes or reconcile uncertain exchange outcomes; it preserves the confirmed result and tells the user to check exchange activity before repeating an action. Full-screen charts and address-only portfolio lookup remain optional product extensions rather than changes to this design pass.
