export type AgentStatus = 'idle' | 'working' | 'error' | 'offline';

export type RoomType = 'ops' | 'break' | 'agent' | 'system';

export type Agent = {
  id: string;
  name: string;
  role: string;
  status: AgentStatus;
  lastSeen: number; // unix ms
  currentTask: string;
  parentAgentId?: string | null;
  workingWithAgentId?: string | null;
};

export type Room = {
  id: string;
  name: string;
  type: RoomType;
  // Permissions are simple strings for now; expand later (RBAC)
  permissions: {
    morpheus: 'admin';
    agents: 'limited' | 'roomOnly' | 'none';
  };
};

export type MessageTag = 'ALERT' | 'FILL' | 'RISK' | 'SYSTEM';

export type Message = {
  id: string;
  roomId: string;
  senderId: string;
  senderName: string;
  ts: number; // unix ms
  text: string;
  tags: MessageTag[];
  pinned?: boolean; // optional UI hint
};

export type EventType =
  | 'agent_joined'
  | 'agent_left'
  | 'status_update'
  | 'task_update'
  | 'message'
  | 'error'
  | 'system_event'
  | 'hired'
  | 'fired'
  | 'cooldown_queued'
  | 'cooldown_released';

export type Event = {
  id: string;
  type: EventType;
  ts: number;
  payload: any;
};
