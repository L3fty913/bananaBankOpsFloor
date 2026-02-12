# Implementation Status (Selene Checklist)

## Completed now
- Added `polymarket/reconcile_dry_run.py`
  - Computes wallet USDC, BUY reserved USDC, free USDC
  - Computes per-token wallet balance, SELL reserved, free balance
  - Flags `POSITION_MISMATCH`, `UNEXITABLE_INVENTORY`, `BUY_USDC_OVERCOMMIT`
  - Checks token orderbook availability (dry-run only)
  - Emits JSON state with `state_clean`

## Next (queued)
1. Wire this checker into a 2-5s reconcile loop service (paused mode)
2. Add strict preflight gate function returning `NO_TRADE(reason_codes[])`
3. Add state_version + intent idempotency hash
4. Add high-frequency reconcile burst on divergence
5. Add explicit status filter for reserving (`LIVE` only unless proven otherwise)
