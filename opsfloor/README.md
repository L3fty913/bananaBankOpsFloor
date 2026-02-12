# OpsFloor (Banana Bank Operations Floor)

Office-style game world UI: pixel-character agents on desks and pods, with chat for bot integration.

## Layout
- `server/` Node HTTP server + SSE event stream + persistence (agents support optional `parentAgentId`, `workingWithAgentId`)
- `client/` SPA: office stage (desks, pods, moving sprites) + chat panel (rooms, messages, composer)
- `shared/` Shared types (TS) for Agent/Room/Message/Event

## Host locally (single-command)

From the `opsfloor/` directory:

```bash
cd opsfloor
npm install
npm run start
```

Then open **http://localhost:8790**. The server builds the client and serves both API and UI on one port.

- **Dev (hot reload):** `npm run dev` — starts server + Vite; open **http://localhost:5173** (API is proxied to 8790).
- **Production-style:** `npm run build` then `npm run start:server` — serve only from port 8790.

## API
- `POST /workspace/status` — body: `agentId`, `name` required; optional: `role`, `status`, `currentTask`, `parentAgentId` (sub-agent's lead), `workingWithAgentId` (agent they're working with).
- `POST /workspace/message`
- `GET /workspace/state`
- `GET /workspace/events` (SSE)

## Connect from Clawdbot

Set your dashboard’s OpsFloor base URL (e.g. `http://localhost:8790`) and have agents POST `/workspace/status` and `/workspace/message` to it; they will appear on the floor and in chat. See [INTEGRATION.md](INTEGRATION.md) for the full contract, example payloads, and the coordinate system (exec row on top, non-execs scattered, RAG desk position).

## Notes
- Message cooldown enforced server-side: 10–15s (configurable).
- Per-room cap with archival table.
- If the server fails to start with a `better_sqlite3.node` / `ERR_DLOPEN_FAILED` error, rebuild native deps: `cd server && npm rebuild better-sqlite3`.
