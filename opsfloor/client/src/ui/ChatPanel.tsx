import React from 'react';
import { Virtuoso } from 'react-virtuoso';
import type { Room, Message } from '../../../shared/types';

const QUICK_TEMPLATES = [
  'Status check: post your current task + blocker in one line.',
  'Escalation: summarize issue, impact, and next step.',
  'QA ping: validate latest UI change and report regressions only.',
];

export type ChatPanelProps = {
  state: {
    agents: Array<{ id: string; name: string }>;
    rooms: Array<Room & { permissions: unknown }>;
    messages: Record<string, unknown[]>;
    cooldownMs: number;
  } | null;
  activeRoomId: string;
  onRoomChange: (roomId: string) => void;
  text: string;
  setText: (v: string) => void;
  onSend: () => Promise<void>;
  cooldownInfo: string;
  refresh: () => Promise<void>;
};

export function ChatPanel({
  state,
  activeRoomId,
  onRoomChange,
  text,
  setText,
  onSend,
  cooldownInfo,
  refresh,
}: ChatPanelProps) {
  const rooms = state?.rooms ?? [];
  const agentRooms = (state?.agents ?? []).map((a: { id: string; name: string }) => ({
    id: `agent-${a.id}`,
    name: `#agent-${a.name}`,
  }));
  const messages: Message[] = (state?.messages?.[activeRoomId] ?? []) as Message[];
  const activeRoom = rooms.find((r: { id: string }) => r.id === activeRoomId) ?? {
    id: activeRoomId,
    name: activeRoomId,
    type: 'ops',
  };

  const onComposerKeyDown: React.KeyboardEventHandler<HTMLTextAreaElement> = async (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      await onSend();
    }
  };

  function applyTemplate(t: string) {
    setText((prev: string) => (prev ? `${prev}\n${t}` : t));
  }

  return (
    <div className="panel chat">
      <div className="panelHeader">
        <div>
          <div className="hdr">CHAT TERMINAL</div>
          <div className="kv">channel: {activeRoom.name}</div>
        </div>
        <div className="pill">live</div>
      </div>
      <div className="chatRoomList">
        <div className={`item ${activeRoomId === 'ops' ? 'active' : ''}`} onClick={() => onRoomChange('ops')}>
          Ops Floor<br /><small>Desks + terminal</small>
        </div>
        <div className={`item ${activeRoomId === 'break' ? 'active' : ''}`} onClick={() => onRoomChange('break')}>
          Break Room<br /><small>Watercooler</small>
        </div>
        <div className={`item ${activeRoomId === 'announcements' ? 'active' : ''}`} onClick={() => onRoomChange('announcements')}>
          Announcements<br /><small>Pinned + briefs</small>
        </div>
        <div className="item" style={{ cursor: 'default' }}>
          Agents<br /><small>Channels</small>
        </div>
        {agentRooms.map((r: { id: string; name: string }) => (
          <div key={r.id} className={`item ${activeRoomId === r.id ? 'active' : ''}`} onClick={() => onRoomChange(r.id)}>
            {r.name}
          </div>
        ))}
      </div>
      <div className="chatLog">
        <Virtuoso
          data={messages}
          followOutput="smooth"
          itemContent={(_i, m: Message & { tags?: string[]; senderName?: string }) => {
            const isSystem = (m.tags || []).includes('SYSTEM') || (m.senderName ?? '').toLowerCase().includes('system');
            return (
              <div className={`chatRow ${isSystem ? 'system' : ''}`}>
                <div className="kv rowHead">
                  <div>
                    <span style={{ color: 'var(--muted)' }}>{new Date(m.ts).toISOString().slice(11, 19)}Z</span>{' '}
                    <strong style={{ fontFamily: 'var(--mono)' }}>{m.senderName ?? m.senderId}</strong>
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
          <div className="kv">server cooldown: {Math.round((state?.cooldownMs ?? 12000) / 1000)}s</div>
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
          <button className="btn primary" onClick={onSend}>send</button>
          <button className="btn" onClick={refresh}>refresh</button>
        </div>
      </div>
    </div>
  );
}
