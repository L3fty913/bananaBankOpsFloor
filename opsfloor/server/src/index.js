import http from 'node:http';
import { URL } from 'node:url';
import fs from 'node:fs';
import path from 'node:path';
import Database from 'better-sqlite3';
import { nanoid } from 'nanoid';

const PORT = Number(process.env.PORT || 8790);
const DB_PATH = process.env.OPS_DB || new URL('./opsfloor.db', import.meta.url).pathname;
const COOLDOWN_MS = Number(process.env.AGENT_COOLDOWN_MS || 12_000);
const MAX_PER_ROOM = Number(process.env.MAX_PER_ROOM || 5000);
const MAX_QUEUE_PER_AGENT = Number(process.env.MAX_QUEUE_PER_AGENT || 100);
const MAX_MESSAGE_CHARS = Number(process.env.MAX_MESSAGE_CHARS || 4000);
const MAX_BODY_BYTES = Number(process.env.MAX_BODY_BYTES || 1_000_000);
const ROUTER_TIMEOUT_MS = Number(process.env.ROUTER_TIMEOUT_MS || 1500);
const ROUTER_MAX_RETRIES = Number(process.env.ROUTER_MAX_RETRIES || 2);
const ROUTER_RETRY_DELAY_MS = Number(process.env.ROUTER_RETRY_DELAY_MS || 120);

// Optional static UI serving (production): point to built client dist
const UI_DIST = process.env.UI_DIST || path.resolve(path.dirname(new URL(import.meta.url).pathname), '../../client/dist');

const db = new Database(DB_PATH);

// Reliability pragmas: tolerate short lock contention and favor WAL throughput.
db.pragma('journal_mode = WAL');
db.pragma('busy_timeout = 5000');
db.pragma('synchronous = NORMAL');
db.pragma('foreign_keys = ON');

db.exec(`
  CREATE TABLE IF NOT EXISTS agents(
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    role TEXT NOT NULL,
    status TEXT NOT NULL,
    lastSeen INTEGER NOT NULL,
    currentTask TEXT NOT NULL
  );
  CREATE TABLE IF NOT EXISTS rooms(
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    permissions_json TEXT NOT NULL
  );
  CREATE TABLE IF NOT EXISTS messages(
    id TEXT PRIMARY KEY,
    roomId TEXT NOT NULL,
    senderId TEXT NOT NULL,
    senderName TEXT NOT NULL,
    ts INTEGER NOT NULL,
    text TEXT NOT NULL,
    tags_json TEXT NOT NULL
  );
  CREATE TABLE IF NOT EXISTS events(
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    ts INTEGER NOT NULL,
    payload_json TEXT NOT NULL
  );
  CREATE INDEX IF NOT EXISTS idx_messages_room_ts ON messages(roomId, ts);
  CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
`);

const defaultRooms = [
  {
    id: 'ops',
    name: 'Ops Floor',
    type: 'ops',
    permissions: { morpheus: 'admin', agents: 'limited' },
  },
  {
    id: 'break',
    name: 'Break Room',
    type: 'break',
    permissions: { morpheus: 'admin', agents: 'limited' },
  },
  {
    id: 'announcements',
    name: 'Announcements',
    type: 'system',
    permissions: { morpheus: 'admin', agents: 'none' },
  },
];

const upsertRoom = db.prepare(
  `INSERT INTO rooms(id,name,type,permissions_json) VALUES(?,?,?,?)
   ON CONFLICT(id) DO UPDATE SET name=excluded.name, type=excluded.type, permissions_json=excluded.permissions_json`
);
for (const r of defaultRooms) upsertRoom.run(r.id, r.name, r.type, JSON.stringify(r.permissions));

// Optional agent bootstrap: provide a JSON array via OPS_AGENTS_JSON or a file path OPS_AGENTS_FILE
// Example: [{"id":"caesar","name":"Caesar","role":"Manager"}, ...]
function bootstrapAgents() {
  try {
    let raw = process.env.OPS_AGENTS_JSON;
    if (!raw && process.env.OPS_AGENTS_FILE) {
      raw = fs.readFileSync(process.env.OPS_AGENTS_FILE, 'utf8');
    }
    if (!raw) return;
    const arr = JSON.parse(raw);
    if (!Array.isArray(arr)) return;
    const now = Date.now();
    const upsertAgent = db.prepare(
      `INSERT INTO agents(id,name,role,status,lastSeen,currentTask)
       VALUES(?,?,?,?,?,?)
       ON CONFLICT(id) DO UPDATE SET
         name=excluded.name,
         role=excluded.role`
    );
    for (const a of arr) {
      if (!a?.id || !a?.name) continue;
      upsertAgent.run(a.id, a.name, a.role || 'Agent', 'idle', now, a.currentTask || '');
      // ensure agent room exists
      upsertRoom.run(`agent-${a.id}`, `#agent-${a.name}`, 'agent', JSON.stringify({ morpheus: 'admin', agents: 'roomOnly' }));
    }
    db.exec('DELETE FROM rooms WHERE id LIKE "agent-%" AND id NOT IN (SELECT "agent-"||id FROM agents)');
  } catch {
    // ignore bootstrap failures
  }
}
bootstrapAgents();

const sseClients = new Set();
const nextAllowedSpeakAt = new Map(); // agentId -> unix ms
const cooldownQueues = new Map(); // agentId -> [{msg, roomId, tags}]
const STARTED_AT = Date.now();

function json(res, code, obj) {
  res.writeHead(code, { 'content-type': 'application/json' });
  res.end(JSON.stringify(obj));
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let total = 0;
    req.on('data', (c) => {
      total += c.length;
      if (total > MAX_BODY_BYTES) {
        const err = new Error('body_too_large');
        err.code = 'BODY_TOO_LARGE';
        reject(err);
        req.destroy();
        return;
      }
      chunks.push(c);
    });
    req.on('end', () => {
      try {
        const raw = Buffer.concat(chunks).toString('utf8');
        resolve(raw ? JSON.parse(raw) : {});
      } catch (e) {
        reject(e);
      }
    });
    req.on('error', reject);
  });
}

function parseBoundedInt(value, fallback, min, max) {
  const n = Number(value);
  if (!Number.isFinite(n)) return fallback;
  const i = Math.trunc(n);
  return Math.min(max, Math.max(min, i));
}

function emitEvent(type, payload) {
  const evt = { id: nanoid(), type, ts: Date.now(), payload };
  db.prepare('INSERT INTO events(id,type,ts,payload_json) VALUES(?,?,?,?)').run(
    evt.id,
    evt.type,
    evt.ts,
    JSON.stringify(evt.payload)
  );
  const line = `event: ${evt.type}\ndata: ${JSON.stringify(evt)}\n\n`;
  for (const res of sseClients) res.write(line);
}

function capRoom(roomId) {
  const count = db.prepare('SELECT COUNT(*) c FROM messages WHERE roomId=?').get(roomId).c;
  if (count <= MAX_PER_ROOM) return;
  const toDelete = count - MAX_PER_ROOM;
  // delete oldest
  db.prepare(
    `DELETE FROM messages WHERE id IN (
       SELECT id FROM messages WHERE roomId=? ORDER BY ts ASC LIMIT ?
     )`
  ).run(roomId, toDelete);
  emitEvent('system_event', { roomId, text: `Archived ${toDelete} old messages in ${roomId}` });
}

function getRoomById(roomId) {
  const row = db.prepare('SELECT * FROM rooms WHERE id=?').get(roomId);
  if (!row) return null;
  return { ...row, permissions: JSON.parse(row.permissions_json) };
}

function canAgentPostToRoom(agentId, room) {
  const mode = room?.permissions?.agents || 'none';
  if (mode === 'none') return false;
  if (mode === 'limited') return true;
  if (mode === 'roomOnly') return room.id === `agent-${agentId}`;
  return false;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function isTransientDbError(err) {
  const msg = String(err?.message || '');
  return msg.includes('SQLITE_BUSY') || msg.includes('SQLITE_LOCKED');
}

const ROUTE_ALIASES = new Map([
  ['aegis', 'agent-aegis'],
  ['keystone', 'agent-keystone'],
  ['vector', 'agent-vector'],
  ['mint', 'agent-mint'],
  ['switchboard', 'agent-switchboard'],
  ['caliper', 'agent-caliper'],
]);

function routeTokenToRoom(token) {
  const t = String(token || '').trim().toLowerCase();
  if (!t) return null;
  if (t.startsWith('agent-') || t.startsWith('#agent-')) {
    return t.replace(/^#/, '');
  }
  if (ROUTE_ALIASES.has(t)) return ROUTE_ALIASES.get(t);
  return `agent-${t}`;
}

function resolveRoutedRoomId({ roomId, text, tags }) {
  const routeTag = tags && typeof tags === 'object' ? tags.routeTo : null;
  if (typeof routeTag === 'string' && routeTag.trim()) {
    const candidate = routeTokenToRoom(routeTag);
    if (candidate && db.prepare('SELECT 1 as ok FROM rooms WHERE id=?').get(candidate)?.ok === 1) return candidate;
  }

  if (typeof text === 'string') {
    const roomMention = text.match(/#(agent-[a-zA-Z0-9_-]+)/i);
    if (roomMention?.[1]) {
      const candidate = roomMention[1].toLowerCase();
      if (db.prepare('SELECT 1 as ok FROM rooms WHERE id=?').get(candidate)?.ok === 1) return candidate;
    }

    const mention = text.match(/@([a-zA-Z0-9_-]+)/);
    if (mention?.[1]) {
      const candidate = routeTokenToRoom(mention[1]);
      if (candidate && db.prepare('SELECT 1 as ok FROM rooms WHERE id=?').get(candidate)?.ok === 1) return candidate;
    }
  }

  return roomId;
}

async function withTimeout(promiseFactory, timeoutMs) {
  return Promise.race([
    Promise.resolve().then(promiseFactory),
    new Promise((_, reject) => setTimeout(() => reject(new Error('dispatch_timeout')), timeoutMs)),
  ]);
}

async function reliableDispatch({ agentId, senderId, senderName, baseRoomId, text, tags, room, targetRoomId }) {
  const attempts = [];
  const fallbackRoomId = baseRoomId === 'ops' ? 'break' : 'ops';
  const roomChain = [targetRoomId, fallbackRoomId].filter((v, i, arr) => v && arr.indexOf(v) === i);

  for (const tryRoomId of roomChain) {
    const tryRoom = tryRoomId === baseRoomId ? room : getRoomById(tryRoomId);
    if (!tryRoom) {
      attempts.push({ roomId: tryRoomId, ok: false, error: 'room_not_found' });
      continue;
    }

    if (agentId && !canAgentPostToRoom(agentId, tryRoom)) {
      attempts.push({ roomId: tryRoomId, ok: false, error: 'agent_not_allowed' });
      continue;
    }

    for (let n = 0; n <= ROUTER_MAX_RETRIES; n += 1) {
      try {
        const result = await withTimeout(() => {
          if (agentId) {
            return queueOrSendAgentMessage(agentId, {
              roomId: tryRoomId,
              senderId,
              senderName,
              text,
              tags,
            });
          }
          const msg = postMessage({ roomId: tryRoomId, senderId, senderName, text, tags });
          return { queued: false, id: msg.id };
        }, ROUTER_TIMEOUT_MS);

        attempts.push({ roomId: tryRoomId, ok: true, attempt: n + 1, queued: !!result?.queued, fallbackUsed: tryRoomId !== targetRoomId });
        if (tryRoomId !== targetRoomId) {
          safeRouterNotice(baseRoomId, `FALLBACK: delivered to ${tryRoomId} after primary route failure`, ['FALLBACK']);
        }
        return { ok: true, roomId: tryRoomId, result, attempts, fallbackUsed: tryRoomId !== targetRoomId };
      } catch (err) {
        const error = err?.message || 'dispatch_failed';
        attempts.push({ roomId: tryRoomId, ok: false, attempt: n + 1, error });
        const shouldRetry = n < ROUTER_MAX_RETRIES && (isTransientDbError(err) || String(error).includes('dispatch_timeout'));
        safeRouterNotice(baseRoomId, `TIMEOUT/RETRY: route ${tryRoomId} attempt ${n + 1} failed (${error})${shouldRetry ? ', retrying' : ''}`, ['RETRY']);
        if (!shouldRetry) break;
        await sleep(ROUTER_RETRY_DELAY_MS * (n + 1));
      }
    }
  }

  return { ok: false, attempts, error: 'dispatch_failed_all_routes' };
}

function postMessage({ roomId, senderId, senderName, text, tags }) {
  const msg = {
    id: nanoid(),
    roomId,
    senderId,
    senderName,
    ts: Date.now(),
    text,
    tags: Array.isArray(tags) ? tags : [],
  };
  db.prepare(
    'INSERT INTO messages(id,roomId,senderId,senderName,ts,text,tags_json) VALUES(?,?,?,?,?,?,?)'
  ).run(msg.id, msg.roomId, msg.senderId, msg.senderName, msg.ts, msg.text, JSON.stringify(msg.tags));
  capRoom(roomId);
  emitEvent('message', msg);
  return msg;
}

function postRouterNotice(roomId, text, extraTags = []) {
  return postMessage({
    roomId,
    senderId: 'system',
    senderName: 'OpsRouter',
    text,
    tags: ['SYSTEM', 'ROUTER', ...extraTags],
  });
}

function safeRouterNotice(roomId, text, extraTags = []) {
  try {
    postRouterNotice(roomId, text, extraTags);
  } catch {
    emitEvent('router_notice_failed', { roomId, text, tags: extraTags });
  }
}

function queueOrSendAgentMessage(agentId, payload) {
  const now = Date.now();
  const allowedAt = nextAllowedSpeakAt.get(agentId) || 0;
  if (now < allowedAt) {
    const q = cooldownQueues.get(agentId) || [];
    if (q.length >= MAX_QUEUE_PER_AGENT) {
      emitEvent('cooldown_dropped', { agentId, reason: 'queue_full', maxQueue: MAX_QUEUE_PER_AGENT });
      return { queued: false, dropped: true, reason: 'queue_full' };
    }
    q.push(payload);
    cooldownQueues.set(agentId, q);
    emitEvent('cooldown_queued', { agentId, remainingMs: allowedAt - now, queued: q.length });
    return { queued: true, remainingMs: allowedAt - now };
  }
  nextAllowedSpeakAt.set(agentId, now + COOLDOWN_MS);
  postMessage(payload);
  setTimeout(() => {
    const q = cooldownQueues.get(agentId);
    if (!q || q.length === 0) return;
    // release exactly one message per cooldown window
    const next = q.shift();
    if (q.length === 0) cooldownQueues.delete(agentId);
    emitEvent('cooldown_released', { agentId });
    queueOrSendAgentMessage(agentId, next);
  }, COOLDOWN_MS);
  return { queued: false };
}

function getState(limitPerRoom = 200) {
  const agents = db.prepare('SELECT * FROM agents ORDER BY name ASC').all();
  const rooms = db.prepare('SELECT * FROM rooms').all().map((r) => ({
    ...r,
    permissions: JSON.parse(r.permissions_json),
  }));
  const messages = {};
  for (const room of rooms) {
    messages[room.id] = db
      .prepare('SELECT * FROM messages WHERE roomId=? ORDER BY ts DESC LIMIT ?')
      .all(room.id, limitPerRoom)
      .reverse()
      .map((m) => ({ ...m, tags: JSON.parse(m.tags_json) }));
  }
  return { agents, rooms, messages, cooldownMs: COOLDOWN_MS };
}

const server = http.createServer(async (req, res) => {
  try {
    const u = new URL(req.url, `http://${req.headers.host}`);
    // CORS (local dev + simple VPS)
    res.setHeader('access-control-allow-origin', '*');
    res.setHeader('access-control-allow-headers', 'content-type');
    res.setHeader('access-control-allow-methods', 'GET,POST,OPTIONS');
    if (req.method === 'OPTIONS') return res.end();

    if (req.method === 'GET' && u.pathname === '/healthz') {
      const dbOk = db.prepare('SELECT 1 as ok').get()?.ok === 1;
      return json(res, dbOk ? 200 : 500, {
        ok: dbOk,
        ts: Date.now(),
        uptimeMs: Date.now() - STARTED_AT,
        sseClients: sseClients.size,
        queuedAgents: cooldownQueues.size,
      });
    }

    // Serve UI static assets if dist exists
    if (req.method === 'GET' && (u.pathname === '/' || u.pathname.startsWith('/assets/') || u.pathname === '/favicon.svg' || u.pathname.startsWith('/favicon-') || u.pathname.startsWith('/apple-touch-icon'))) {
      try {
        const filePath = u.pathname === '/' ? path.join(UI_DIST, 'index.html') : path.join(UI_DIST, u.pathname);
        const real = fs.realpathSync(filePath);
        if (!real.startsWith(fs.realpathSync(UI_DIST))) throw new Error('path escape');
        const data = fs.readFileSync(real);
        const ext = path.extname(real).toLowerCase();
        const ct = ext === '.html' ? 'text/html; charset=utf-8'
          : ext === '.js' ? 'text/javascript; charset=utf-8'
          : ext === '.css' ? 'text/css; charset=utf-8'
          : ext === '.svg' ? 'image/svg+xml'
          : ext === '.png' ? 'image/png'
          : 'application/octet-stream';
        res.writeHead(200, { 'content-type': ct, 'cache-control': ext === '.html' ? 'no-cache' : 'public, max-age=31536000, immutable' });
        return res.end(data);
      } catch {
        // fall through to API/404
      }
    }

    if (req.method === 'GET' && u.pathname === '/workspace/state') {
      const limit = parseBoundedInt(u.searchParams.get('limit') || 200, 200, 1, 500);
      return json(res, 200, getState(limit));
    }

    if (req.method === 'GET' && u.pathname === '/workspace/events') {
      res.writeHead(200, {
        'content-type': 'text/event-stream',
        'cache-control': 'no-cache',
        connection: 'keep-alive',
      });
      res.write(`event: hello\ndata: ${JSON.stringify({ ts: Date.now() })}\n\n`);
      sseClients.add(res);
      req.on('close', () => sseClients.delete(res));
      return;
    }

    if (req.method === 'POST' && u.pathname === '/workspace/status') {
      const body = await readBody(req);
      const { agentId, name, role, status, currentTask } = body;
      if (!agentId || !name) return json(res, 400, { ok: false, error: 'agentId and name required' });
      const now = Date.now();
      db.prepare(
        `INSERT INTO agents(id,name,role,status,lastSeen,currentTask)
         VALUES(?,?,?,?,?,?)
         ON CONFLICT(id) DO UPDATE SET
           name=excluded.name,
           role=excluded.role,
           status=excluded.status,
           lastSeen=excluded.lastSeen,
           currentTask=excluded.currentTask`
      ).run(agentId, name, role || 'Agent', status || 'idle', now, currentTask || '');
      emitEvent('status_update', { agentId, status, currentTask, lastSeen: now });
      return json(res, 200, { ok: true });
    }

    if (req.method === 'POST' && u.pathname === '/workspace/message') {
      const body = await readBody(req);
      const { agentId, senderName, roomId, text, tags } = body;
      if (!roomId || typeof text !== 'string' || text.length === 0) {
        return json(res, 400, { ok: false, error: 'roomId and text required' });
      }
      if (text.length > MAX_MESSAGE_CHARS) {
        return json(res, 413, { ok: false, error: `message too long (max ${MAX_MESSAGE_CHARS})` });
      }

      const room = getRoomById(roomId);
      if (!room) return json(res, 404, { ok: false, error: 'room not found' });

      const senderId = agentId || 'morpheus';
      const name = senderName || (agentId ? agentId : 'Morpheus');
      const routedRoomId = resolveRoutedRoomId({ roomId, text, tags });
      const ack = {
        accepted: true,
        route: { requestedRoomId: roomId, routedRoomId },
        policy: { timeoutMs: ROUTER_TIMEOUT_MS, maxRetries: ROUTER_MAX_RETRIES },
      };

      if (agentId && !canAgentPostToRoom(agentId, room) && routedRoomId === roomId) {
        return json(res, 403, { ok: false, error: 'agent not allowed in room', ack });
      }

      safeRouterNotice(roomId, `ACK: accepted message from ${name}; route=${routedRoomId}; timeout=${ROUTER_TIMEOUT_MS}ms retries=${ROUTER_MAX_RETRIES}`, ['ACK']);

      const dispatch = await reliableDispatch({
        agentId,
        senderId,
        senderName: name,
        baseRoomId: roomId,
        text,
        tags,
        room,
        targetRoomId: routedRoomId,
      });

      if (!dispatch.ok) {
        safeRouterNotice(roomId, `FAIL: message dispatch failed after retries; fallback exhausted`, ['FAIL']);
        emitEvent('message_dispatch_failed', { senderId, roomId, routedRoomId, attempts: dispatch.attempts });
        return json(res, 503, { ok: false, error: dispatch.error, ack, attempts: dispatch.attempts });
      }

      safeRouterNotice(roomId, `DELIVERED: routed to ${dispatch.roomId}${dispatch.fallbackUsed ? ' (fallback)' : ''}`, ['DELIVERED']);
      emitEvent('message_dispatch_ack', {
        senderId,
        requestedRoomId: roomId,
        routedRoomId: dispatch.roomId,
        fallbackUsed: dispatch.fallbackUsed,
        attempts: dispatch.attempts,
      });

      return json(res, 200, {
        ok: true,
        ack,
        routedRoomId: dispatch.roomId,
        fallbackUsed: dispatch.fallbackUsed,
        attempts: dispatch.attempts,
        ...dispatch.result,
      });
    }

    json(res, 404, { ok: false, error: 'not_found' });
  } catch (err) {
    const isParseError = err instanceof SyntaxError;
    const isBodyTooLarge = err?.code === 'BODY_TOO_LARGE';
    return json(res, isBodyTooLarge ? 413 : (isParseError ? 400 : 500), {
      ok: false,
      error: isBodyTooLarge ? `body too large (max ${MAX_BODY_BYTES} bytes)` : (isParseError ? 'invalid_json' : 'internal_error'),
    });
  }
});

server.listen(PORT, '0.0.0.0', () => {
  console.log(`opsfloor-server listening on :${PORT} db=${DB_PATH}`);
});

function shutdown(signal) {
  console.log(`received ${signal}, shutting down`);
  server.close(() => {
    try {
      db.close();
    } finally {
      process.exit(0);
    }
  });
  setTimeout(() => process.exit(1), 10_000).unref();
}

process.on('SIGINT', () => shutdown('SIGINT'));
process.on('SIGTERM', () => shutdown('SIGTERM'));
