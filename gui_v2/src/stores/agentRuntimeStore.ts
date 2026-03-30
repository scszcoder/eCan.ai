import { create } from 'zustand';
import { ipcApi } from '@/services/ipc/api';

export type RuntimeStatus = 'disabled' | 'stopped' | 'standby' | 'working';

export interface AgentRuntimeInfo {
  agent_id: string;
  agent_name?: string;
  runtime_status: RuntimeStatus;
  enabled: boolean;
  active_task_count: number;
}

interface AgentRuntimeState {
  /** Map of agent_id -> runtime info */
  statusMap: Record<string, AgentRuntimeInfo>;
  /** Whether polling is active */
  polling: boolean;
  /** Interval handle */
  _intervalId: ReturnType<typeof setInterval> | null;

  /** Fetch all agent statuses from backend (batch) */
  fetchAll: () => Promise<void>;
  /** Directly update a single agent's status (optimistic / immediate) */
  setStatus: (agentId: string, status: RuntimeStatus, enabled: boolean) => void;
  /** Start polling every intervalMs (default 30000) */
  startPolling: (intervalMs?: number) => void;
  /** Stop polling */
  stopPolling: () => void;
}

export const useAgentRuntimeStore = create<AgentRuntimeState>((set, get) => ({
  statusMap: {},
  polling: false,
  _intervalId: null,

  fetchAll: async () => {
    try {
      const res = await ipcApi.getAllAgentsRuntimeStatus<{ agents: AgentRuntimeInfo[] }>();
      if (res.success && res.data?.agents) {
        const map: Record<string, AgentRuntimeInfo> = {};
        for (const info of res.data.agents) {
          map[info.agent_id] = info;
        }
        set({ statusMap: map });
      }
    } catch (e) {
      // silent — polling should not break UI
    }
  },

  setStatus: (agentId: string, status: RuntimeStatus, enabled: boolean) => {
    const current = get().statusMap;
    set({
      statusMap: {
        ...current,
        [agentId]: {
          ...(current[agentId] || { agent_id: agentId, active_task_count: 0 }),
          runtime_status: status,
          enabled,
        },
      },
    });
  },

  startPolling: (intervalMs = 30000) => {
    const state = get();
    if (state._intervalId) return;
    state.fetchAll();
    const id = setInterval(() => {
      get().fetchAll();
    }, intervalMs);
    set({ polling: true, _intervalId: id });
  },

  stopPolling: () => {
    const state = get();
    if (state._intervalId) {
      clearInterval(state._intervalId);
      set({ polling: false, _intervalId: null });
    }
  },
}));
