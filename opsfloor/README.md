# OpsFloor (Banana Bank Operations Floor)

Boxy retro "office workspace" UI + local event bus + agent endpoints.

## Layout
- `server/` Node HTTP server + SSE event stream + persistence
- `client/` SPA UI (Vite + React + TS)
- `shared/` Shared types (TS) for Agent/Room/Message/Event

## Quickstart (dev)
1) In one terminal:
   ```bash
   cd opsfloor/server
   npm i
   npm run dev
   ```
2) In another terminal:
   ```bash
   cd opsfloor/client
   npm i
   npm run dev
   ```

Server: http://localhost:8790
Client: http://localhost:5173

## API
- `POST /workspace/status`
- `POST /workspace/message`
- `GET /workspace/state`
- `GET /workspace/events` (SSE)

## Notes
- Message cooldown enforced server-side: 10–15s (configurable).
- Per-room cap with archival table.
