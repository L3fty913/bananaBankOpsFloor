# Improvement Cycle — 2026-02-12 — API Reliability Guardrails

## Goal
Reduce easy API abuse paths that could degrade OpsFloor server reliability under malformed or oversized requests.

## Changes shipped
File: `opsfloor/server/src/index.js`

1. **Request body size limit**
   - Added `MAX_BODY_BYTES` env var (default `1_000_000` bytes).
   - `readBody()` now tracks total request bytes and aborts when over limit.
   - Oversized payloads now return `413` with a clear error.

2. **Bounded `/workspace/state` limit param**
   - Added `parseBoundedInt()` helper.
   - `limit` query param is now clamped to `1..500` (default `200`).
   - Prevents excessive per-room message scans from huge `limit` values.

3. **Error mapping hardening**
   - Added explicit handling for body overflow sentinel (`BODY_TOO_LARGE`) in global request handler.

## Why this matters
- Prevents accidental or malicious giant JSON payloads from consuming memory and destabilizing the process.
- Caps expensive state fetches that could otherwise induce high DB/CPU load.
- Improves API behavior predictability with explicit `413` responses.

## Operational notes
- Tune body limit with `MAX_BODY_BYTES` if future endpoints require larger payloads.
- If UI needs >500 messages/room in one call, use pagination endpoint(s) instead of increasing this hard cap globally.
