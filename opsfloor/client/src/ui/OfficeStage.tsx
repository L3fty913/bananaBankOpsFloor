import React, { useEffect, useRef, useState, useMemo } from 'react';
import type { Agent } from '../../../shared/types';

const DESK_WIDTH = 120;
const DESK_HEIGHT = 80;
const EMPLOYEE_DESK_WIDTH = 72;
const EMPLOYEE_DESK_HEIGHT = 48;
const POD_PADDING = 50;
const TASK_MAX_LEN = 60;

// Ops floor coordinate plot: container is STAGE_WIDTH x STAGE_HEIGHT; origin (0,0) top-left.
const STAGE_WIDTH = 1400;
const STAGE_HEIGHT = 500;
const CENTER_X = STAGE_WIDTH / 2;
const CENTER_Y = STAGE_HEIGHT / 2;
const EXEC_ROW_TOP_Y = 70; // Exec desks sit in a row along the top.
const EXEC_ROW_MARGIN_X = 80;
const SCATTER_MARGIN_Y = 170; // Start of floor region below exec row.
const SCATTER_MARGIN_BOTTOM = 60;
const SCATTER_MARGIN_X = 80;
const SCATTER_CELL_W = 110;
const SCATTER_CELL_H = 90;
const RAG_DESK_WIDTH = 100;
const RAG_DESK_HEIGHT = 60;
const RAG_DESK_X = 80;
const RAG_DESK_Y = STAGE_HEIGHT - SCATTER_MARGIN_BOTTOM - RAG_DESK_HEIGHT;

function simpleHash(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) {
    h = ((h << 5) - h + s.charCodeAt(i)) | 0;
  }
  return Math.abs(h);
}

const PALETTES = [
  ['#59a1ff', '#0f1728', '#21c07a'],
  ['#ffcc66', '#0f1728', '#ff5a7a'],
  ['#9ad7ff', '#0b1120', '#59a1ff'],
  ['#21c07a', '#0b1120', '#ffcc66'],
  ['#a4b6e6', '#0f1728', '#4864a5'],
  ['#ff5a7a', '#0b1120', '#59a1ff'],
];

function getPalette(agent: Agent): string[] {
  const h = simpleHash(agent.id + agent.name + agent.role);
  return PALETTES[h % PALETTES.length];
}

function getVariant(agent: Agent): number {
  const h = simpleHash(agent.role + agent.id);
  return h % 3;
}

function deskStatus(a: Agent): string {
  if (Date.now() - a.lastSeen > 60_000) return 'offline';
  return a.status;
}

function summarizeTask(task: string, maxLen = TASK_MAX_LEN): string {
  const t = (task || '').trim();
  if (!t) return 'No active task.';
  if (t.length <= maxLen) return t;
  return `${t.slice(0, maxLen - 1)}…`;
}

export type OfficeStageProps = {
  agents: Agent[];
  leads: Agent[];
  pods: Map<string, Agent[]>;
  onMessageAgent?: (agentId: string) => void;
};

function getLeadDeskPositions(leads: Agent[]): Map<string, { x: number; y: number }> {
  const m = new Map<string, { x: number; y: number }>();
  if (leads.length === 0) return m;
  const caesar = leads.find((l) => l.id.toLowerCase() === 'caesar');
  const others = leads.filter((l) => l.id.toLowerCase() !== 'caesar');
  const half = Math.floor(others.length / 2);
  const order: Agent[] = [...others.slice(0, half), ...(caesar ? [caesar] : []), ...others.slice(half)];
  const n = order.length;
  const span = STAGE_WIDTH - 2 * EXEC_ROW_MARGIN_X;
  order.forEach((lead, i) => {
    const x = n <= 1 ? CENTER_X : EXEC_ROW_MARGIN_X + (i / (n - 1)) * span;
    m.set(lead.id, { x, y: EXEC_ROW_TOP_Y });
  });
  return m;
}

/** Execs on top row; non-execs scattered in a grid on the floor (no overlap). One cell reserved for RAG. */
function getAgentDeskPositions(
  agents: Agent[],
  leads: Agent[],
  leadToDesk: Map<string, { x: number; y: number }>
): Map<string, { x: number; y: number }> {
  const out = new Map<string, { x: number; y: number }>();
  const leadIds = new Set(leads.map((l) => l.id));
  leads.forEach((l) => out.set(l.id, leadToDesk.get(l.id)!));

  const nonLeads = agents.filter((a) => !leadIds.has(a.id)).sort((a, b) => a.id.localeCompare(b.id));
  const floorW = STAGE_WIDTH - 2 * SCATTER_MARGIN_X;
  const floorH = STAGE_HEIGHT - SCATTER_MARGIN_Y - SCATTER_MARGIN_BOTTOM;
  const cols = Math.max(1, Math.floor(floorW / SCATTER_CELL_W));
  const rows = Math.max(1, Math.floor(floorH / SCATTER_CELL_H));
  const totalCells = cols * rows;
  const reservedCell = totalCells > 1 ? (rows - 1) * cols : -1;
  const validSlots = reservedCell < 0 ? totalCells : totalCells - 1;
  nonLeads.forEach((a, i) => {
    const idx = validSlots <= 0 ? 0 : i % validSlots;
    const cellIndex = reservedCell < 0 ? idx : (idx < reservedCell ? idx : idx + 1);
    const cell = cellIndex;
    const row = Math.floor(cell / cols);
    const col = cell % cols;
    const x = SCATTER_MARGIN_X + col * SCATTER_CELL_W + SCATTER_CELL_W / 2;
    const y = SCATTER_MARGIN_Y + row * SCATTER_CELL_H + SCATTER_CELL_H / 2;
    out.set(a.id, { x, y });
  });
  agents.forEach((a) => {
    if (!out.has(a.id)) out.set(a.id, { x: CENTER_X, y: CENTER_Y });
  });
  return out;
}

export function OfficeStage({ agents, leads, pods, onMessageAgent }: OfficeStageProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);

  const leadToDesk = useMemo(() => getLeadDeskPositions(leads.length > 0 ? leads : [{ id: 'default', name: 'Desk', role: '', status: 'idle', lastSeen: 0, currentTask: '' } as Agent]), [leads]);
  const deskPositions = useMemo(() => leads.map((l) => leadToDesk.get(l.id) ?? { x: CENTER_X, y: CENTER_Y }), [leads, leadToDesk]);

  const agentToDesk = useMemo(
    () => getAgentDeskPositions(agents, leads.length > 0 ? leads : [], leadToDesk),
    [agents, leads, leadToDesk]
  );

  const subAgents = useMemo(() => agents.filter((a) => a.parentAgentId), [agents]);
  const employeeDeskPositions = useMemo(() => {
    const list: Array<{ agent: Agent; x: number; y: number }> = [];
    for (const a of subAgents) {
      const pos = agentToDesk.get(a.id);
      if (!pos) continue;
      list.push({ agent: a, x: pos.x, y: pos.y });
    }
    return list;
  }, [subAgents, agentToDesk]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const updateScale = () => {
      const w = el.clientWidth;
      const h = el.clientHeight;
      if (w <= 0 || h <= 0) return;
      const s = Math.min(w / STAGE_WIDTH, h / STAGE_HEIGHT, 1);
      setScale(s);
    };
    updateScale();
    const ro = new ResizeObserver(updateScale);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  return (
    <div className="officeStage" ref={containerRef}>
      <div
        className="officeStageInner"
        style={{
          width: STAGE_WIDTH,
          height: STAGE_HEIGHT,
          transform: `scale(${scale})`,
          transformOrigin: '0 0',
        }}
      >
        <div className="officeStageTitle">OPS FLOOR</div>
      {leads.map((lead, i) => {
        const pos = deskPositions[i] ?? deskPositions[0];
        return (
          <div
            key={lead.id}
            className="stageDesk"
            style={{
              left: pos.x - DESK_WIDTH / 2,
              top: pos.y - DESK_HEIGHT / 2,
              width: DESK_WIDTH,
              height: DESK_HEIGHT,
            }}
          >
            <div className="stageDeskLabel">{lead.name}</div>
          </div>
        );
      })}
      {leads.map((lead, i) => {
        const pos = deskPositions[i] ?? deskPositions[0];
        const w = DESK_WIDTH + POD_PADDING * 2;
        const h = DESK_HEIGHT + POD_PADDING * 2;
        return (
          <div
            key={`pod-${lead.id}`}
            className="stagePod"
            style={{
              left: pos.x - w / 2,
              top: pos.y - h / 2,
              width: w,
              height: h,
            }}
          />
        );
      })}
      <div
        className="stageDesk stageRagDesk"
        style={{
          left: RAG_DESK_X,
          top: RAG_DESK_Y,
          width: RAG_DESK_WIDTH,
          height: RAG_DESK_HEIGHT,
        }}
        aria-label="RAG desk"
      >
        <div className="stageDeskLabel">RAG</div>
      </div>
      {employeeDeskPositions.map(({ agent, x, y }) => (
        <div
          key={`emp-desk-${agent.id}`}
          className="stageDesk stageDeskEmployee"
          style={{
            left: x - EMPLOYEE_DESK_WIDTH / 2,
            top: y - EMPLOYEE_DESK_HEIGHT / 2,
            width: EMPLOYEE_DESK_WIDTH,
            height: EMPLOYEE_DESK_HEIGHT,
          }}
        >
          <div className="stageDeskLabel">{agent.name}</div>
        </div>
      ))}
      {agents.map((a) => {
        const pos = agentToDesk.get(a.id) ?? { x: CENTER_X, y: CENTER_Y };
        const palette = getPalette(a);
        const variant = getVariant(a);
        const status = deskStatus(a);
        return (
          <div
            key={a.id}
            className="agentSpriteWrap"
            style={{
              left: pos.x - 12,
              top: pos.y - 20,
            }}
            tabIndex={0}
            role="button"
            aria-label={`${a.name}, ${status}. ${summarizeTask(a.currentTask ?? '')}`}
            onKeyDown={(e) => {
              if ((e.key === 'Enter' || e.key === ' ') && onMessageAgent) {
                e.preventDefault();
                onMessageAgent(a.id);
              }
            }}
            onClick={() => onMessageAgent?.(a.id)}
          >
            <div
              className="agentSprite"
              style={{
                backgroundColor: palette[0],
                borderColor: palette[2],
              }}
              data-variant={variant}
            >
              <div className="agentSpriteProp" style={{ backgroundColor: palette[1], borderColor: palette[2] }} />
            </div>
            <div className="agentLabel">
              <div className="agentLabelName">{a.name}</div>
              <div className={`agentLabelStatus status ${status}`}>{status}</div>
              <div className="agentLabelTask" title={a.currentTask ?? ''}>{summarizeTask(a.currentTask ?? '')}</div>
            </div>
          </div>
        );
      })}
      </div>
    </div>
  );
}
