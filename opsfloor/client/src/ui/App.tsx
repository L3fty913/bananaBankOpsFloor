import React, { useEffect, useMemo, useState } from 'react';
import type { Agent } from '../../../shared/types';
import { API_BASE, jget, jpost } from './api';
import { ChatPanel } from './ChatPanel';
import { OfficeStage } from './OfficeStage';

export type StateResp = {
  agents: Agent[];
  rooms: Array<unknown>;
  messages: Record<string, unknown[]>;
  cooldownMs: number;
};

const MOCK_AGENTS: Agent[] = (() => {
  const now = Date.now();
  return [
    { id: 'caesar', name: 'Caesar', role: 'Manager', status: 'working', lastSeen: now - 2000, currentTask: 'Reviewing Q4 forecasts', parentAgentId: null, workingWithAgentId: null },
    { id: 'aegis', name: 'Aegis', role: 'Security', status: 'working', lastSeen: now - 5000, currentTask: 'Audit access logs', parentAgentId: null, workingWithAgentId: null },
    { id: 'keystone', name: 'Keystone', role: 'Routing', status: 'idle', lastSeen: now - 8000, currentTask: 'No active task.', parentAgentId: null, workingWithAgentId: null },
    { id: 'vector', name: 'Vector', role: 'Ops', status: 'working', lastSeen: now - 1000, currentTask: 'Deploying v2.1', parentAgentId: null, workingWithAgentId: null },
    { id: 'mint', name: 'Mint', role: 'Finance', status: 'idle', lastSeen: now - 15000, currentTask: 'Reconciling ledger', parentAgentId: null, workingWithAgentId: null },
    { id: 'switchboard', name: 'Switchboard', role: 'Dispatch', status: 'working', lastSeen: now - 3000, currentTask: 'Routing alerts', parentAgentId: 'caesar', workingWithAgentId: null },
    { id: 'caliper', name: 'Caliper', role: 'QA', status: 'idle', lastSeen: now - 4000, currentTask: 'Regression pass', parentAgentId: 'caesar', workingWithAgentId: null },
    { id: 'router', name: 'Router', role: 'Dispatch', status: 'idle', lastSeen: now - 2000, currentTask: 'Standby', parentAgentId: 'switchboard', workingWithAgentId: null },
  ];
})();

export function App() {
  const [state, setState] = useState<StateResp | null>(null);
  const [activeRoomId, setActiveRoomId] = useState<string>('ops');
  const [text, setText] = useState('');
  const [cooldownInfo, setCooldownInfo] = useState('');

  const agents = useMemo(() => {
    const fromApi = state?.agents ?? [];
    if (fromApi.length > 0) return fromApi;
    return MOCK_AGENTS;
  }, [state?.agents]);
  const leads = agents.filter((a) => !a.parentAgentId || a.parentAgentId === '');
  const pods = React.useMemo(() => {
    const m = new Map<string, Agent[]>();
    for (const a of agents) {
      const pid = a.parentAgentId ?? '';
      if (!pid) continue;
      const list = m.get(pid) ?? [];
      list.push(a);
      m.set(pid, list);
    }
    return m;
  }, [agents]);

  async function refresh() {
    const s = await jget<StateResp>(`/workspace/state?limit=400`);
    setState(s);
  }

  useEffect(() => {
    refresh();
    const es = new EventSource(`${API_BASE}/workspace/events`);
    es.addEventListener('message', () => refresh());
    es.addEventListener('status_update', () => refresh());
    es.addEventListener('cooldown_queued', (e: MessageEvent) => {
      try {
        const data = JSON.parse((e as MessageEvent & { data?: string }).data ?? '{}');
        setCooldownInfo(`Cooldown: queued (${Math.ceil(data.payload?.remainingMs / 1000)}s left)`);
      } catch {
        // ignore
      }
    });
    return () => es.close();
  }, []);

  async function sendMorpheus() {
    const t = text.trim();
    if (!t) return;
    setCooldownInfo('');
    try {
      await jpost('/workspace/message', { roomId: activeRoomId, text: t, tags: [] });
      setText('');
      await refresh();
    } catch (e: unknown) {
      setCooldownInfo(`Send failed (${e instanceof Error ? e.message : 'error'})`);
    }
  }

  function onMessageAgent(agentId: string) {
    setActiveRoomId(`agent-${agentId}`);
  }

  return (
    <div className="shell">
      <div className="panel shellStage">
        <div className="panelHeader">
          <div>
            <div className="hdr">BANANA BANK OPS FLOOR</div>
            <div className="kv">Office stage • agents • chat</div>
          </div>
          <div className="pill">v0.3</div>
        </div>
        <OfficeStage
          agents={agents}
          leads={leads.length > 0 ? leads : agents}
          pods={pods}
          onMessageAgent={onMessageAgent}
        />
      </div>
      <ChatPanel
        state={state}
        activeRoomId={activeRoomId}
        onRoomChange={setActiveRoomId}
        text={text}
        setText={setText}
        onSend={sendMorpheus}
        cooldownInfo={cooldownInfo}
        refresh={refresh}
      />
    </div>
  );
}
