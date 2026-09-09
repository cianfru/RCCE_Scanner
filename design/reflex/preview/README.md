# Reflex design preview

Complete landing page, interactive scanner refresh, and hold-to-access proposal preview for RCCE_Scanner.

Routes: `/`, `/scanner`, `/access`.

This standalone preview uses React with the Sites/Vinext scaffold. The original GitHub application is unchanged. Port the shared design tokens and presentation components into its existing React/Vite frontend after design review; the backend signal engine is outside this preview's scope.

All market data is illustrative. Wallet access scenarios are simulations. X and the canonical token remain unconfigured. There are no trading, balance-checking, token-sale, or wallet-signing actions. Watchlist preferences are stored only on the current device.

Development: `npm install` and `npm run dev`. Production build: `npm run build`.

Validation: production build, TypeScript, server route responses, and scanner data/filter/sort assertions. Browser interaction and visual QA were not run. Optional WebMCP filtering support is feature-detected but was not contract-verified because no supported validation context was available.
