import { create } from 'zustand';

export type FleetConnection = 'idle' | 'connecting' | 'live' | 'reconnecting' | 'error' | 'unconfigured';

export interface FleetMachine {
  id: string;
  name: string;
  role: string;
}

export interface FleetAgent {
  id: string;
  name: string;
  running: boolean;
  status?: string;
  readiness?: Record<string, unknown> | null;
}

export interface FleetEvent {
  ts: number;
  kind: string;            // snapshot | agent_status | task | log
  [k: string]: unknown;
}

export interface FleetMachineState {
  machine: FleetMachine;
  lastSeen: number;
  agents: FleetAgent[];
  tasks: { task: string; status: string; ts: number }[];
  logTail: boolean;
  events: FleetEvent[];    // newest last, capped
  logs: FleetEvent[];      // newest last, capped
  logDropped: number;
}

const MAX_EVENTS = 300;
const MAX_LOGS = 800;

interface FleetFeedState {
  connection: FleetConnection;
  connectionDetail: string;
  machines: Record<string, FleetMachineState>;
  setConnection: (c: FleetConnection, detail?: string) => void;
  ingest: (body: { machine?: FleetMachine; events?: FleetEvent[]; log_dropped?: number }) => void;
  clear: () => void;
}

export const useFleetFeedStore = create<FleetFeedState>((set) => ({
  connection: 'idle',
  connectionDetail: '',
  machines: {},
  setConnection: (connection, detail = '') => set({ connection, connectionDetail: detail }),
  clear: () => set({ machines: {} }),
  ingest: (body) => set((state) => {
    const m = body?.machine;
    if (!m) return state;
    const key = m.id || m.name || 'unknown';
    const cur: FleetMachineState = state.machines[key] || {
      machine: m, lastSeen: 0, agents: [], tasks: [], logTail: false, events: [], logs: [], logDropped: 0,
    };
    const next: FleetMachineState = { ...cur, machine: m, lastSeen: Date.now() };
    const events = [...cur.events];
    const logs = [...cur.logs];
    for (const ev of body.events || []) {
      if (ev.kind === 'snapshot') {
        next.agents = (ev.agents as FleetAgent[]) || [];
        next.tasks = (ev.tasks as FleetMachineState['tasks']) || [];
        next.logTail = Boolean(ev.log_tail);
      } else if (ev.kind === 'log') {
        logs.push(ev);
      } else {
        events.push(ev);
      }
    }
    next.events = events.slice(-MAX_EVENTS);
    next.logs = logs.slice(-MAX_LOGS);
    next.logDropped = cur.logDropped + (body.log_dropped || 0);
    return { machines: { ...state.machines, [key]: next } };
  }),
}));
