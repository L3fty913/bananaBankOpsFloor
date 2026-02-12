# Improvement Cycle — DB Resilience + Safer Shutdown

Date (UTC): 2026-02-12
Area: OpsFloor platform reliability / maintainability

## What I changed
Updated `server/src/index.js` with one focused reliability hardening pass:

1. Added SQLite runtime pragmas for resilience under concurrent writes:
   - `busy_timeout = 5000` (reduces transient `database is locked` failures)
   - `synchronous = NORMAL` (better WAL performance tradeoff)
   - `foreign_keys = ON` (integrity guardrail)
   - kept WAL mode

2. Upgraded `/healthz` from static ping to actionable readiness signal:
   - Executes `SELECT 1` against DB
   - Returns `ok`, `uptimeMs`, active `sseClients`, and `queuedAgents`
   - Emits HTTP 500 if DB check fails

3. Added graceful shutdown handling:
   - SIGINT/SIGTERM now close HTTP server and DB cleanly
   - includes 10s hard-exit fallback to avoid hung shutdowns

## Why this is meaningful
- Improves uptime stability during lock contention bursts.
- Makes health checks useful for alerting/orchestration (not just liveness).
- Prevents abrupt process exits from leaving resources in undefined states.

## Validation
- Syntax check passed: `node --check src/index.js`

## Files touched
- `opsfloor/server/src/index.js`
- `opsfloor/IMPROVEMENT-2026-02-12-db-resilience.md`
