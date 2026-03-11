# RCCE Scanner API Reference

## Confirmation Endpoints

### GET /api/confirm/{symbol}
Confirm a single symbol entry. Combines scanner technical analysis + AIXBT social intelligence.

**Parameters:**
- `symbol` (path) — Symbol to confirm (e.g., BTC, ETH, SOL)
- `timeframe` (query, default: "4h") — "4h" or "1d"

**Response:**
```json
{
  "symbol": "ETH/USDT",
  "timestamp": 1710000000,
  "scanner": {
    "signal": "STRONG_LONG",
    "regime": "MARKUP",
    "confidence": 78.5,
    "conditions_met": 9,
    "conditions_total": 10,
    "effective_conditions": 9,
    "zscore": 1.2,
    "heat": 45,
    "heat_phase": "Neutral",
    "exhaustion_state": "NEUTRAL",
    "floor_confirmed": false,
    "is_absorption": false,
    "divergence": null,
    "price": 3450.25,
    "vol_scale": 1.05,
    "signal_warnings": []
  },
  "aixbt": {
    "project_name": "ethereum",
    "found": true,
    "momentum_score": 8.5,
    "popularity_score": 18,
    "signal_count": 12,
    "risk_alert_count": 0,
    "bullish_signal_count": 5,
    "whale_signals": 2,
    "narrative_strength": "STRONG",
    "risk_level": "LOW",
    "confirmation": "CONFIRMED",
    "top_signals": [
      {
        "category": "WHALE_ACTIVITY",
        "description": "Large ETH accumulation detected across multiple wallets",
        "clusters": 4,
        "reinforced_at": "2025-03-10T14:30:00Z"
      }
    ],
    "error": "",
    "cached": false
  },
  "verdict": {
    "action": "GO",
    "reason": "Scanner says STRONG_LONG + AIXBT narrative CONFIRMED (momentum 8.5, 5 bullish signals)",
    "scanner_signal": "STRONG_LONG",
    "aixbt_confirmation": "CONFIRMED"
  }
}
```

### GET /api/confirm
Batch confirmation for all symbols with active entry signals.

**Parameters:**
- `timeframe` (query, default: "4h")
- `signals_only` (query, default: true) — Only confirm entry signals

**Response:**
```json
{
  "confirmations": [/* array of confirmation reports */],
  "count": 3
}
```

## Core Scanner Endpoints

### GET /api/scan
Full scan results.

**Parameters:**
- `timeframe` — "4h" or "1d"
- `regime` (optional) — Filter: MARKUP, BLOWOFF, MARKDOWN, ACCUM, CAP, REACC
- `signal` (optional) — Filter: STRONG_LONG, LIGHT_LONG, TRIM, etc.

### GET /api/consensus
Market consensus.

**Parameters:**
- `timeframe` — "4h" or "1d"

**Response:** `{ "consensus": "RISK-ON", "strength": 72.5, "timeframe": "4h" }`

### GET /api/sentiment
Fear and Greed Index.

**Response:** `{ "fear_greed_value": 35, "fear_greed_label": "Fear" }`

### GET /api/alt-season
Alt-season gauge.

**Response:** `{ "score": 65, "label": "ACTIVE", "alts_up": 28, "total_alts": 40, "btc_dominance": 48.2 }`

### GET /api/global-metrics
Market-wide data (BTC dominance, total market cap, etc.)

### GET /api/stablecoin
Stablecoin supply trends.

## Verdict Logic

The confirmation system produces these verdicts:

| Verdict | When | Action |
|---------|------|--------|
| GO | Scanner entry signal + AIXBT CONFIRMED | Enter position |
| LEAN_GO | Scanner entry signal + AIXBT NEUTRAL | Enter with reduced size |
| WAIT | Scanner entry but AIXBT CAUTION, or WAIT signal | Hold off |
| NO | AIXBT DENIED (risk alerts) | Do not enter |
| EXIT | Scanner exit signal (TRIM, RISK_OFF, etc.) | Close/reduce position |
| MANUAL | AIXBT unavailable | Confirm via other sources |

## 10-Point Condition Checklist

Entry signals require these conditions:

1. Bullish regime (MARKUP or ACCUM)
2. Confidence > 60%
3. Market consensus RISK-ON or ACCUMULATION
4. Z-score between -0.5 and 2.5
5. No bearish divergence vs BTC
6. Heat < 85 (regime-adaptive)
7. No exhaustion climax
8. Funding not CROWDED_LONG
9. Fear and Greed < 70
10. Stablecoin supply not contracting

STRONG_LONG = all 10 met (or effective >= 10 after boosts)
LIGHT_LONG = 5+ effective conditions
