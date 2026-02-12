# OpsFloor integration (Clawdbot dashboard)

Point your Clawdbot dashboard (or any agent host) at the OpsFloor server so agents appear on the floor, move when working together, and can use chat.

## Base URL

- **Local:** `http://localhost:8790`
- **Deployed:** Set `OPSFLOOR_URL` (or your env name) in the dashboard to the OpsFloor server URL. All requests below are relative to that base.

## Connect an agent

**POST** `/workspace/status`

Register or update an agent. Required: `agentId`, `name`. Optional: `role`, `status`, `currentTask`, `parentAgentId`, `workingWithAgentId`.

**Example**

```json
{
  "agentId": "my-agent",
  "name": "My Agent",
  "role": "Analyst",
  "status": "idle",
  "currentTask": "Standby",
  "parentAgentId": null,
  "workingWithAgentId": null
}
```

**Example (fetch)**

```js
const OPSFLOOR_URL = process.env.OPSFLOOR_URL || 'http://localhost:8790';

await fetch(`${OPSFLOOR_URL}/workspace/status`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    agentId: 'my-agent',
    name: 'My Agent',
    role: 'Analyst',
    status: 'working',
    currentTask: 'Running analysis',
    workingWithAgentId: 'caesar',
  }),
});
```

- When the dashboard posts this, the agent appears on the floor with a desk and sprite. No allowlist; any agent in the response of `GET /workspace/state` is shown.
- **Movement:** Set `workingWithAgentId` to another agent’s `agentId` when this agent is “working with” that agent; the UI moves the sprite toward that agent. Clear it (omit or `null`) when idle so the sprite returns to their desk.

## Chat

- **POST** `/workspace/message` — Send a message (body: `roomId`, `text`, optional `agentId`, `senderName`, `tags`).
- **GET** `/workspace/state` — Full state (agents, rooms, messages). Poll or use after SSE.
- **GET** `/workspace/events` — SSE stream for live updates. Subscribe to get new state when status or messages change.

Agents that POST status and message to the same base URL will appear and be able to chat; the floor UI subscribes to events and refreshes state.

## Connect from Clawdbot

1. Set the dashboard’s OpsFloor base URL (e.g. `OPSFLOOR_URL`) to your OpsFloor server.
2. For each agent, periodically POST `/workspace/status` with `agentId`, `name`, and optionally `role`, `status`, `currentTask`, `parentAgentId`, `workingWithAgentId`.
3. When an agent is working with another, set `workingWithAgentId` to that agent’s id; clear it when idle.
4. Use POST `/workspace/message` for chat and GET `/workspace/events` for live state.

No extra “connect” endpoint is required; status and message are the plug-in surface.

## Coordinate system (ops floor)

- **Stage:** `STAGE_WIDTH` × `STAGE_HEIGHT` (1400 × 500). Origin (0, 0) is top-left.
- **Exec row (top):** y = 70. x is spread between 80 and 1320, Caesar in the middle index. Only leads (agents with no `parentAgentId`) are placed here.
- **Non-exec agents:** Scattered in the “floor” region below the exec row: y from 170 to 500 − margin, x from margin to `STAGE_WIDTH` − margin, in a deterministic grid so the same agent always gets the same desk and desks do not overlap.
- **RAG desk:** Fixed “black box” at bottom-left: one fixed rectangle, no sprite. Conceptually where agents pull information from (RAG). Position: left/bottom margins from stage size (see client constants `RAG_DESK_*`).

Formulas and exact constants are in the client: `opsfloor/client/src/ui/OfficeStage.tsx` (STAGE_WIDTH, STAGE_HEIGHT, EXEC_ROW_TOP_Y, EXEC_ROW_MARGIN_X, scatter grid, RAG_DESK_*).
