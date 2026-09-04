import { create } from 'zustand';
import { ipcApi } from '@/services/ipc/api';

export type RuntimeStatus = 'disabled' | 'stopped' | 'standby' | 'working';

export interface AgentRuntimeInfo {
  agent_id: string;
  agent_name?: string;
  runtime_status: RuntimeStatus;
  enabled: boolean;
  active_task_count: number;
  /** Backend [AGENT-STATUS] readiness ledger (chrome / site_tab / monitor / dom / detection). */
  readiness?: Record<string, string | number | null | undefined>;
}

interface AgentRuntimeState {
  /** Map of agent_id -> runtime info */
  statusMap: Record<string, AgentRuntimeInfo>;
  /** Whether polling is active */
  polling: boolean;
  /** Interval handle */
  _intervalId: ReturnType<typeof setInterval> | null;
  /** Whether page is visible */
  _pageVisible: boolean;

  /** Fetch all agent statuses from backend (batch) */
  fetchAll: () => Promise<void>;
  /** Directly update a single agent's status (optimistic / immediate) */
  setStatus: (agentId: string, status: RuntimeStatus, enabled: boolean) => void;
  /** Start polling every intervalMs (default 60000) */
  startPolling: (intervalMs?: number) => void;
  /** Stop polling */
  stopPolling: () => void;
  /** Set page visibility state */
  setPageVisible: (visible: boolean) => void;
}

// Module-level visibility state for page visibility events
let _visibilityHandler: (() => void) | null = null;

export const useAgentRuntimeStore = create<AgentRuntimeState>((set, get) => ({
  statusMap: {},
  polling: false,
  _intervalId: null,
  _pageVisible: true,

  fetchAll: async () => {
    // Skip fetch when page is hidden to save resources
    if (!get()._pageVisible) return;
    
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

  startPolling: (intervalMs = 60 * 1000) => {
    const state = get();
    if (state._intervalId) return;
    
    // Setup page visibility listener if not already done
    if (!_visibilityHandler && typeof document !== 'undefined') {
      _visibilityHandler = () => {
        const visible = !document.hidden;
        get().setPageVisible(visible);
      };
      document.addEventListener('visibilitychange', _visibilityHandler);
    }
    
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
    
    // Cleanup visibility listener
    if (_visibilityHandler && typeof document !== 'undefined') {
      document.removeEventListener('visibilitychange', _visibilityHandler);
      _visibilityHandler = null;
    }
  },
  
  setPageVisible: (visible: boolean) => {
    set({ _pageVisible: visible });
    // Immediately fetch when page becomes visible again
    if (visible) {
      get().fetchAll();
    }
  },
}));
