# Morpheus Equity-Only Terminal

## What it does
- Single line chart: Total Wallet Equity vs Time
- Current Equity, Session Change, 24h Change, Max Drawdown (session), High Water Mark
- Stale-data indicator
- 1h / 6h / 24h / 7d / All timeframe selectors
- Append-only snapshot store with replay on restart

## Files
- `collector.py` -> computes authoritative equity snapshots every 1-5s
- `server.py` -> FastAPI + SSE stream + chart UI

## Run on VPS
```bash
cd /opt/polybot
python3 -m pip install fastapi uvicorn python-dotenv py-clob-client eth-account
mkdir -p /opt/polybot/rag
python3 collector.py
# in another shell
uvicorn server:app --host 0.0.0.0 --port 8787
```

## Data model emitted
- `timestamp_et`
- `equity_total_usd`
- `realized_pnl_usd`
- `unrealized_pnl_usd`
- `open_exposure_usd`
- `health` fields persisted: `latency_ms`, `api_ok`, `last_trade_ts`, `safe_mode`, `stale_data`
