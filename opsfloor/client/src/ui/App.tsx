import React, { useEffect, useMemo, useState } from 'react';
import { Virtuoso } from 'react-virtuoso';
import type { Agent, Room, Message } from '../../../shared/types';
import { API_BASE, jget, jpost } from './api';

type StateResp = {
  agents: Agent[];
  rooms: Array<any>;
  messages: Record<string, any[]>;
  cooldownMs: number;
};

type Lane = 'queue' | 'agents' | 'alerts' | 'audit';

function fmtAgo(ms: number) {
  const s = Math.max(0, Math.floor((Date.now() - ms) / 1000));
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  return `${h}h ago`;
}

function summarizeTask(task: string, maxLen = 90) {
  const t = (task || '').trim();
  if (!t) return 'No active task assigned.';
  if (t.length <= maxLen) return t;
  return `${t.slice(0, maxLen - 1)}…`;
}

function initials(name: string) {
  const parts = (name || '').trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return 'AG';
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0] || ''}${parts[1][0] || ''}`.toUpperCase();
}

const AGENT_AVATARS: Record<string, string> = {
  caesar: '📈',
  aegis: '🛡️',
  keystone: '🧭',
  vector: '⚙️',
  mint: '💹',
  switchboard: '🔌',
  caliper: '📏',
};

const FLOOR_ORDER = ['caesar', 'aegis', 'keystone', 'vector', 'mint', 'switchboard', 'caliper'];
const DESK_LAYOUT: Array<{ id: string; row: 1 | 2; col: 1 | 2 | 3 | 4; center?: boolean }> = [
  { id: 'aegis', row: 1, col: 1 },
  { id: 'caesar', row: 1, col: 2, center: true },
  { id: 'keystone', row: 1, col: 3 },
  { id: 'vector', row: 1, col: 4 },
  { id: 'mint', row: 2, col: 1 },
  { id: 'switchboard', row: 2, col: 2 },
  { id: 'caliper', row: 2, col: 3 },
];

const QUICK_TEMPLATES = [
  'Status check: post your current task + blocker in one line.',
  'Escalation: summarize issue, impact, and next step.',
  'QA ping: validate latest UI change and report regressions only.',
];

export function App() {
  const [state, setState] = useState<StateResp | null>(null);
  const [activeRoomId, setActiveRoomId] = useState<string>('ops');
  const [activeLane, setActiveLane] = useState<Lane>('agents');
  const [text, setText] = useState('');
  const [cooldownInfo, setCooldownInfo] = useState('');
  const [agentFilter, setAgentFilter] = useState<'all' | 'online' | 'working' | 'offline'>('all');
  const [agentQuery, setAgentQuery] = useState('');

  const rooms: Room[] = useMemo(() => {
    if (!state) return [] as any;
    return state.rooms.map((r: any) => ({
      id: r.id,
      name: r.name,
      type: r.type,
      permissions: r.permissions,
    }));
  }, [state]);

  const agents = state?.agents || [];
  const sortedAgents = [...agents].sort((a, b) => {
    const ai = FLOOR_ORDER.indexOf((a.id || '').toLowerCase());
    const bi = FLOOR_ORDER.indexOf((b.id || '').toLowerCase());
    const av = ai === -1 ? 999 : ai;
    const bv = bi === -1 ? 999 : bi;
    if (av !== bv) return av - bv;
    return (a.name || '').localeCompare(b.name || '');
  });

  const agentCounts = sortedAgents.reduce(
    (acc, a) => {
      const st = deskStatus(a);
      acc.all += 1;
      if (st === 'offline') acc.offline += 1;
      else acc.online += 1;
      if (st === 'working') acc.working += 1;
      return acc;
    },
    { all: 0, online: 0, working: 0, offline: 0 }
  );

  const query = agentQuery.trim().toLowerCase();
  const filteredAgents = sortedAgents.filter((a) => {
    const st = deskStatus(a);
    const filterMatch =
      agentFilter === 'all' ||
      (agentFilter === 'online' && st !== 'offline') ||
      (agentFilter === 'working' && st === 'working') ||
      (agentFilter === 'offline' && st === 'offline');
    if (!filterMatch) return false;
    if (!query) return true;
    const hay = `${a.name || ''} ${a.id || ''} ${a.role || ''} ${a.currentTask || ''}`.toLowerCase();
    return hay.includes(query);
  });
  const messages: Message[] = (state?.messages?.[activeRoomId] || []) as any;
  const announcements: Message[] = (state?.messages?.['announcements'] || []) as any;
  const pinnedAnnouncements = announcements.filter((m: any) => (m.tags || []).includes('SYSTEM') || m.pinned).slice(-6);

  const agentById = useMemo(() => {
    const m = new Map<string, Agent>();
    for (const a of filteredAgents) m.set((a.id || '').toLowerCase(), a);
    return m;
  }, [filteredAgents]);
  const overflowAgents = filteredAgents.filter((a) => !DESK_LAYOUT.some((s) => s.id === (a.id || '').toLowerCase()));

  async function refresh() {
    const s = await jget<StateResp>(`/workspace/state?limit=400`);
    setState(s);
  }

  useEffect(() => {
    refresh();
    const es = new EventSource(`${API_BASE}/workspace/events`);
    es.addEventListener('message', () => refresh());
    es.addEventListener('status_update', () => refresh());
    es.addEventListener('cooldown_queued', (e: any) => {
      try {
        const data = JSON.parse(e.data);
        setCooldownInfo(`Cooldown: queued (${Math.ceil(data.payload?.remainingMs / 1000)}s left)`);
      } catch {}
    });
    return () => es.close();
  }, []);

  function deskStatus(a: Agent) {
    if (Date.now() - a.lastSeen > 60_000) return 'offline';
    return a.status;
  }

  const agentRooms = agents.map((a) => ({ id: `agent-${a.id}`, name: `#agent-${a.name}`, type: 'agent' as const }));

  async function sendMorpheus() {
    const t = text.trim();
    if (!t) return;
    setCooldownInfo('');
    try {
      await jpost('/workspace/message', { roomId: activeRoomId, text: t, tags: [] });
      setText('');
      await refresh();
    } catch (e: any) {
      setCooldownInfo(`Send failed (${e?.message || 'error'})`);
    }
  }

  const onComposerKeyDown: React.KeyboardEventHandler<HTMLTextAreaElement> = async (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      await sendMorpheus();
    }
  };

  function applyTemplate(t: string) {
    setText((prev) => (prev ? `${prev}\n${t}` : t));
  }

  const activeRoom = rooms.find((r) => r.id === activeRoomId) || {
    id: activeRoomId,
    name: activeRoomId,
    type: 'ops',
    permissions: { morpheus: 'admin', agents: 'limited' },
  };

  const alertsCount = (state?.messages?.announcements || []).length;
  const queueCount = messages.length;

  const breadcrumb = `Desk / ${activeLane.toUpperCase()} / ${activeRoom.name}`;

  return (
    <div className="shell">
      <div className="panel">
        <div className="panelHeader">
          <div>
            <div className="hdr">BANANA BANK OPS FLOOR</div>
            <div className="kv">Operations workspace • desks • rooms • terminal</div>
          </div>
          <div className="pill">v0.2</div>
        </div>
        <div className="sidebarList">
          <div className={`item ${activeRoomId === 'ops' ? 'active' : ''}`} onClick={() => setActiveRoomId('ops')}>
            Ops Floor<br /><small>Desks + terminal</small>
          </div>
          <div className={`item ${activeRoomId === 'break' ? 'active' : ''}`} onClick={() => setActiveRoomId('break')}>
            Break Room<br /><small>Watercooler</small>
          </div>
          <div className={`item ${activeRoomId === 'announcements' ? 'active' : ''}`} onClick={() => setActiveRoomId('announcements')}>
            Announcements<br /><small>Pinned + briefs</small>
          </div>
          <div className="item" style={{ cursor: 'default' }}>
            Agents<br /><small>Channels</small>
          </div>
          {agentRooms.map((r) => (
            <div key={r.id} className={`item ${activeRoomId === r.id ? 'active' : ''}`} onClick={() => setActiveRoomId(r.id)}>
              {r.name}
            </div>
          ))}
        </div>
      </div>

      <div className="panel">
        <div className="panelHeader laneHeader">
          <div>
            <div className="hdr">MAIN WORK FLOOR</div>
            <div className="kv breadcrumb">{breadcrumb}</div>
          </div>
          <div className="pill">desks: {agents.length}</div>
        </div>

        <div className="laneTabs">
          <button className={`tab ${activeLane === 'queue' ? 'active' : ''}`} onClick={() => setActiveLane('queue')}>Queue <span>{queueCount}</span></button>
          <button className={`tab ${activeLane === 'agents' ? 'active' : ''}`} onClick={() => setActiveLane('agents')}>Agents <span>{agents.length}</span></button>
          <button className={`tab ${activeLane === 'alerts' ? 'active' : ''}`} onClick={() => setActiveLane('alerts')}>Alerts <span>{alertsCount}</span></button>
          <button className={`tab ${activeLane === 'audit' ? 'active' : ''}`} onClick={() => setActiveLane('audit')}>Audit</button>
        </div>

        <div className="mainBody">
          {activeRoomId === 'break' ? (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 10 }}>
              <div className="desk" style={{ background: 'var(--panel2)' }}>
                <div className="deskName">BREAK ROOM</div>
                <div className="kv">watercooler threads (placeholder)</div>
                <div className="kv">Pinned announcements appear below.</div>
              </div>
              <div className="desk" style={{ background: 'var(--panel2)' }}>
                <div className="deskName">PINNED ANNOUNCEMENTS</div>
                {pinnedAnnouncements.length === 0 ? (
                  <div className="kv">—</div>
                ) : (
                  pinnedAnnouncements.map((m: any) => (
                    <div key={m.id} style={{ padding: '8px 0', borderTop: '1px solid var(--border)' }}>
                      <div className="kv">{new Date(m.ts).toISOString().slice(11, 19)}Z {m.senderName}</div>
                      <div style={{ fontFamily: 'var(--mono)', whiteSpace: 'pre-wrap' }}>{m.text}</div>
                    </div>
                  ))
                )}
                <div style={{ marginTop: 8 }}>
                  <button className="btn" onClick={() => setActiveRoomId('announcements')}>open announcements channel</button>
                </div>
              </div>
            </div>
          ) : activeLane === 'agents' || activeRoomId === 'ops' ? (
            <div className="floorMap">
              <div className="floorTitle">OPS FLOOR DESK MAP</div>
              <div className="deskGrid">
              <div className="commandBar">
                <div className="countPills">
                  <button className={`miniPill ${agentFilter === 'all' ? 'active' : ''}`} onClick={() => setAgentFilter('all')}>All {agentCounts.all}</button>
                  <button className={`miniPill ${agentFilter === 'online' ? 'active' : ''}`} onClick={() => setAgentFilter('online')}>Online {agentCounts.online}</button>
                  <button className={`miniPill ${agentFilter === 'working' ? 'active' : ''}`} onClick={() => setAgentFilter('working')}>Working {agentCounts.working}</button>
                  <button className={`miniPill ${agentFilter === 'offline' ? 'active' : ''}`} onClick={() => setAgentFilter('offline')}>Offline {agentCounts.offline}</button>
                </div>
                <input
                  className="agentSearch"
                  value={agentQuery}
                  onChange={(e) => setAgentQuery(e.target.value)}
                  placeholder="Search agent, role, or task…"
                />
              </div>
              {filteredAgents.length === 0 ? (
                <div className="desk emptyDesk">
                  <div className="deskName">NO MATCHING AGENT DESKS</div>
                  <div className="kv">No desks match current filter/search.</div>
                  <div className="kv">Try clearing search or switching filter to All.</div>
                  <div className="kv">If still empty, ask agents to post `/workspace/status` heartbeat.</div>
                </div>
              ) : (
                <>
                  {DESK_LAYOUT.map((slot) => {
                    const a = agentById.get(slot.id);
                    if (!a) {
                      return (
                        <div
                          key={slot.id}
                          className={`desk deskCard deskSlotEmpty ${slot.center ? 'managerAnchor' : ''}`}
                          style={{ gridColumn: slot.col, gridRow: slot.row }}
                        >
                          <div className="deskName">{slot.id.toUpperCase()} DESK</div>
                          <div className="kv">No matching agent for current filter/search.</div>
                        </div>
                      );
                    }

                    const st = deskStatus(a);
                    const disabledReason = st === 'offline' ? 'Missing Role: AgentOnline' : '';
                    const avatar = AGENT_AVATARS[(a.id || '').toLowerCase()] || initials(a.name || a.id || 'Agent');
                    return (
                      <div
                        key={a.id}
                        className={`desk deskCard ${slot.center ? 'managerAnchor' : ''}`}
                        style={{ gridColumn: slot.col, gridRow: slot.row }}
                      >
                        <div className="deskHeaderRow">
                          <div className="agentAvatar" aria-hidden>{avatar}</div>
                          <div className="deskIdentity">
                            <div className="deskName">{a.name}</div>
                            <div className="kv">desk: {a.id}</div>
                            <div className="kv">role: {a.role}</div>
                          </div>
                          <div className={`status ${st}`}>{st}</div>
                        </div>

                        <div className="deskSection">
                          <div className="sectionLabel">Agent Status</div>
                          <div className="kv">lastSeen: {fmtAgo(a.lastSeen)}</div>
                        </div>

                        <div className="deskSection">
                          <div className="sectionLabel">Task Summary</div>
                          <div className="taskSummary">{summarizeTask(a.currentTask || '')}</div>
                        </div>

                        <div className="quickActions">
                          <button className="btn primary" onClick={() => setActiveRoomId(`agent-${a.id}`)} title="Assign to desk">⚑ Assign</button>
                          <button className="btn" title={disabledReason || 'Escalate'} disabled={!!disabledReason}>⇪ Escalate</button>
                          <button className="btn" onClick={() => setActiveRoomId(`agent-${a.id}`)}>✉ Message</button>
                          <button className="btn" title={disabledReason || 'Hold'} disabled={!!disabledReason}>⏸ Hold</button>
                        </div>
                        {disabledReason ? <div className="kv warn">{disabledReason}</div> : null}
                      </div>
                    );
                  })}

                  {overflowAgents.map((a) => {
                    const st = deskStatus(a);
                    const disabledReason = st === 'offline' ? 'Missing Role: AgentOnline' : '';
                    const avatar = AGENT_AVATARS[(a.id || '').toLowerCase()] || initials(a.name || a.id || 'Agent');
                    return (
                      <div key={a.id} className="desk deskCard overflowDesk">
                        <div className="deskHeaderRow">
                          <div className="agentAvatar" aria-hidden>{avatar}</div>
                          <div className="deskIdentity">
                            <div className="deskName">{a.name}</div>
                            <div className="kv">desk: {a.id}</div>
                            <div className="kv">role: {a.role}</div>
                          </div>
                          <div className={`status ${st}`}>{st}</div>
                        </div>
                        <div className="deskSection">
                          <div className="sectionLabel">Task Summary</div>
                          <div className="taskSummary">{summarizeTask(a.currentTask || '')}</div>
                        </div>
                        <div className="quickActions">
                          <button className="btn primary" onClick={() => setActiveRoomId(`agent-${a.id}`)}>⚑ Assign</button>
                          <button className="btn" title={disabledReason || 'Escalate'} disabled={!!disabledReason}>⇪ Escalate</button>
                          <button className="btn" onClick={() => setActiveRoomId(`agent-${a.id}`)}>✉ Message</button>
                          <button className="btn" title={disabledReason || 'Hold'} disabled={!!disabledReason}>⏸ Hold</button>
                        </div>
                      </div>
                    );
                  })}
                </>
              )}
              </div>
            </div>
          ) : activeLane === 'alerts' ? (
            <div className="desk" style={{ background: 'var(--panel2)' }}>
              <div className="deskName">ALERTS LANE</div>
              <div className="kv">Monitoring announcements and system events.</div>
              <div className="kv">Current alerts: {alertsCount}</div>
            </div>
          ) : activeLane === 'audit' ? (
            <div className="desk" style={{ background: 'var(--panel2)' }}>
              <div className="deskName">AUDIT LANE</div>
              <div className="kv">Action badges + permission denials + critical ops timeline.</div>
            </div>
          ) : (
            <div className="desk" style={{ background: 'var(--panel2)' }}>
              <div className="deskName">QUEUE LANE</div>
              <div className="kv">Queued interactions: {queueCount}</div>
            </div>
          )}
        </div>
      </div>

      <div className="panel chat">
        <div className="panelHeader">
          <div>
            <div className="hdr">CHAT TERMINAL</div>
            <div className="kv">channel: {activeRoom.name}</div>
          </div>
          <div className="pill">live</div>
        </div>
        <div className="chatLog">
          <Virtuoso
            data={messages}
            followOutput="smooth"
            itemContent={(_i, m: any) => {
              const isSystem = (m.tags || []).includes('SYSTEM') || m.senderName?.toLowerCase()?.includes('system');
              return (
                <div className={`chatRow ${isSystem ? 'system' : ''}`}>
                  <div className="kv rowHead">
                    <div>
                      <span style={{ color: 'var(--muted)' }}>{new Date(m.ts).toISOString().slice(11, 19)}Z</span>{' '}
                      <strong style={{ fontFamily: 'var(--mono)' }}>{m.senderName}</strong>
                    </div>
                    <div>
                      {(m.tags || []).slice(0, 3).map((t: string) => (
                        <span key={t} className="tag">[{t}]</span>
                      ))}
                    </div>
                  </div>
                  <div className="chatText">{m.text}</div>
                </div>
              );
            }}
          />
        </div>
        <div className="composer">
          <div className="row">
            <div className="kv">You are Morpheus (admin). {cooldownInfo}</div>
            <div className="kv">server cooldown: {Math.round((state?.cooldownMs || 12000) / 1000)}s</div>
          </div>
          <div className="templateRow">
            {QUICK_TEMPLATES.map((t) => (
              <button key={t} className="btn" onClick={() => applyTemplate(t)}>template</button>
            ))}
          </div>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={onComposerKeyDown}
            placeholder="Type to speak… (Enter=send, Shift+Enter=new line)"
          />
          <div className="row stickyActions">
            <button className="btn primary" onClick={sendMorpheus}>send</button>
            <button className="btn" onClick={refresh}>refresh</button>
          </div>
        </div>
      </div>
    </div>
  );
}
