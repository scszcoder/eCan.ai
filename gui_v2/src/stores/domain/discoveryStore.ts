/**
 * Discovery Store — peer agents and nodes seen via the A2A discovery system.
 *
 * Populated by polling `discovery.list_agents` + `discovery.list_nodes`
 * every refresh tick. Callers can also subscribe to React updates by
 * reading the store with the standard Zustand hook pattern.
 *
 * Why polling and not push?
 *   The Python backend's directory is event-driven (zeroconf callbacks +
 *   AppSync subscriptions), but the IPC boundary is request/response. A
 *   lightweight 15 s poll keeps the UI fresh without standing up a new
 *   push channel. Switch to push-via-AppSync if peer churn ever feels
 *   slow in practice.
 */

import { create } from 'zustand';
import {
  DiscoveredAgent,
  DiscoveredNode,
  DiscoveryStatus,
  DiscoveryTransport,
  discoveryApi,
} from '../../services/api/discoveryApi';

interface DiscoveryState {
  // raw snapshot
  agents: DiscoveredAgent[];
  nodes: DiscoveredNode[];
  selfMachineId: string | null;
  lanActive: boolean;
  wanActive: boolean;
  lastRefreshed: number;
  loading: boolean;
  error: string | null;

  // derived lookups
  agentById: Record<string, DiscoveredAgent>;
  nodeById: Record<string, DiscoveredNode>;

  // actions
  refresh: () => Promise<void>;
  startAutoRefresh: (intervalMs?: number) => void;
  stopAutoRefresh: () => void;
  getTransportFor: (agentId: string) => DiscoveryTransport;
}

let _autoTimer: ReturnType<typeof setInterval> | null = null;

export const useDiscoveryStore = create<DiscoveryState>((set, get) => ({
  agents: [],
  nodes: [],
  selfMachineId: null,
  lanActive: false,
  wanActive: false,
  lastRefreshed: 0,
  loading: false,
  error: null,
  agentById: {},
  nodeById: {},

  refresh: async () => {
    set({ loading: true, error: null });
    try {
      const r = await discoveryApi.getStatus();
      if (!r.success || !r.data) {
        const errMsg = r.error?.message || 'discovery.get_status failed';
        set({ loading: false, error: errMsg });
        return;
      }
      const s: DiscoveryStatus = r.data;
      const agents = s.snapshot?.agents || [];
      const nodes = s.snapshot?.nodes || [];

      const agentById: Record<string, DiscoveredAgent> = {};
      for (const a of agents) agentById[a.agent_id] = a;
      const nodeById: Record<string, DiscoveredNode> = {};
      for (const n of nodes) nodeById[n.machine_id] = n;

      set({
        agents,
        nodes,
        agentById,
        nodeById,
        selfMachineId: s.self_machine_id,
        lanActive: !!s.lan_active,
        wanActive: !!s.wan_active,
        lastRefreshed: Date.now(),
        loading: false,
      });
    } catch (e) {
      set({ loading: false, error: e instanceof Error ? e.message : String(e) });
    }
  },

  startAutoRefresh: (intervalMs = 15000) => {
    if (_autoTimer) return;
    // Kick off immediately, then on cadence.
    void get().refresh();
    _autoTimer = setInterval(() => {
      void get().refresh();
    }, intervalMs);
  },

  stopAutoRefresh: () => {
    if (_autoTimer) {
      clearInterval(_autoTimer);
      _autoTimer = null;
    }
  },

  /** Best-effort local guess of the transport that would be used for `agentId`.
   *  Doesn't probe — uses the cached directory snapshot. */
  getTransportFor: (agentId: string): DiscoveryTransport => {
    const a = get().agentById[agentId];
    if (!a) return 'none';
    const hasLan = !!a.lan_url;
    const hasWan = !!a.wan_relay_channel;
    if (hasLan && hasWan) return 'lan+wan';
    if (hasLan) return 'lan';
    if (hasWan) return 'wan';
    return 'none';
  },
}));
