# RCCE Scanner

A standalone signal dashboard for the Reflexive Crypto Cycle Engine.
Scans 60+ coins on 4H and 1D simultaneously, no TradingView chart-hopping needed.

## Architecture

```
rcce-scanner/
├── backend/
│   ├── main.py          FastAPI app + scheduler
│   ├── scanner.py       Scan orchestrator + cache
│   ├── rcce_engine.py   RCCE logic ported to Python
│   ├── data_fetcher.py  CCXT / Binance OHLCV
│   └── requirements.txt
└── frontend/
    ├── src/App.tsx      Dashboard UI
    └── ...
```

## Quick Start

### Backend
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev        # opens on http://localhost:5173
```

The frontend proxies /api → localhost:8000 automatically.

## Deploy

**Backend** → Railway
- Set start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`

**Frontend** → Vercel
- Build command: `npm run build`
- Output dir: `dist`
- Set env var `VITE_API_URL` to your Railway backend URL.

### Access control (recommended)

The API is unauthenticated unless you set a token. To lock it:

- **Railway**: set `API_AUTH_TOKEN` to a random secret, and `ALLOWED_ORIGINS`
  to your Vercel URL (e.g. `https://your-app.vercel.app`).
- **Vercel**: set `VITE_API_TOKEN` to the *same* value as `API_AUTH_TOKEN`.

The frontend then sends the token on every API call and WebSocket connection.
`/health` stays public for uptime checks.

### Cost / idle mode

The app runs at full cadence while a dashboard is open and drops to a slow
heartbeat when idle (no dashboard, no recent API traffic), so it costs
close to nothing at rest and wakes instantly on reload. Tunable via env:
`IDLE_AFTER_SECONDS` (default 900), `IDLE_DRIP_PAUSE_S`,
`IDLE_COINGLASS_PAUSE_S`, `IDLE_HYPERLENS_PAUSE_S`, `IDLE_SYNTHESIS_S`.
Pin it awake from the Settings gear ("Keep Awake") while actively trading.

## Signals

| Signal    | Meaning                                      |
|-----------|----------------------------------------------|
| ▲ BUY     | Regime entered MARKUP from ACCUM/CAPITUL     |
| ▼ SELL    | Regime entered MARKDOWN                      |
| ◆ TRIM    | Regime entered DISTRIBUTION (take some off)  |
| ◆◆ HTRIM  | Z-score ≥ 3.5 — blowoff extreme             |

## Regimes

Classified from Z-score (200-period) + EMA energy ratio:

- **MARKUP** — trending up, energy positive, Z 0.5–2.0
- **BLOWOFF** — Z ≥ 3.5, extreme extension
- **DISTRIBUTION** — Z 2.0–3.5, fading energy
- **ACCUMULATION** — flat, Z neutral
- **MARKDOWN** — trending down, energy negative
- **CAPITULATION** — Z ≤ −1.0, energy strongly negative

## Customising the Watchlist

POST to `/api/watchlist` with `{ "symbols": ["BTC/USDT", ...] }`.
