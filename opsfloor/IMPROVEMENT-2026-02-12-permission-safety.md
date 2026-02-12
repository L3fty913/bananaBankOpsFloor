# OpsFloor Improvement Cycle — 2026-02-12

## Focus
Platform reliability + permission safety hardening in `opsfloor/server/src/index.js`.

## Changes shipped
1. **Room permission enforcement for agent posts**
   - Added `getRoomById(roomId)` lookup.
   - Added `canAgentPostToRoom(agentId, room)` policy gate.
   - Agent messages now return `403` if posting to a room they are not allowed to use.
   - Prevents agent posting into restricted/system channels (e.g., announcements).

2. **Message-size guardrail**
   - Added `MAX_MESSAGE_CHARS` env var (default `4000`).
   - `/workspace/message` now returns `413` for oversized payloads.
   - Reduces memory/log spam risk and improves API resilience.

3. **Cooldown queue overflow protection**
   - Added `MAX_QUEUE_PER_AGENT` env var (default `100`).
   - If an agent exceeds queue capacity during cooldown, message is dropped with a `cooldown_dropped` event and explicit reason (`queue_full`).
   - Prevents unbounded memory growth under noisy agents.

4. **Top-level request error handling**
   - Wrapped server request handler in `try/catch`.
   - Invalid JSON now returns `400 invalid_json`.
   - Unexpected errors return `500 internal_error` instead of crashing request flow.

## Validation
- Syntax check passed:
  - `node --check opsfloor/server/src/index.js`

## Operational knobs added
- `MAX_QUEUE_PER_AGENT` (default `100`)
- `MAX_MESSAGE_CHARS` (default `4000`)

## Result
OpsFloor server now has stronger posting controls, bounded queue behavior, and safer request failure modes with explicit client-visible error responses.
