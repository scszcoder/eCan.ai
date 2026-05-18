/**
 * Discovery API — Phase 3+ bindings for the eCan A2A discovery system.
 *
 * Backed by handlers in `gui/ipc/w2p_handlers/discovery_handler.py`. See
 * design memory notes `project-discovery-phase1` .. `phase4`.
 */
import { apiRouter } from './api-router';

// ---- types shared with the Python side (mirror dataclasses in
//      agent/a2a/discovery/directory.py) ------------------------------------

export interface DiscoveredAgent {
  agent_id: string;
  machine_id: string;
  org: string;
  name: string;
  role: string;
  skills: string[];
  lan_url: string | null;
  lan_last_seen: number;
  wan_relay_channel: string | null;
  wan_last_seen: number;
}

export interface DiscoveredNode {
  machine_id: string;
  machine_name: string;
  host: string | null;
  role: string;
  os: string;
  arch: string;
  ecan_ver: string;
  agent_count: number;
  api_port: number | null;
  last_seen: number;
}

export type DiscoveryTransport = 'lan' | 'wan' | 'lan+wan' | 'none';

export interface DiscoverySendOutcome {
  transport: string;
  success: boolean;
  error: string | null;
  response: unknown;
}

export interface DiscoveryStatus {
  self_machine_id: string | null;
  lan_active: boolean;
  wan_active: boolean;
  nodes_known: number;
  agents_known: number;
  snapshot: {
    self_machine_id: string | null;
    nodes: DiscoveredNode[];
    agents: DiscoveredAgent[];
  };
}

export interface FindAgentsParams {
  skill?: string;
  skill_any?: string[];
  skill_all?: string[];
  role?: string;
  name_contains?: string;
  machine_id?: string;
  org?: string;
  reachable?: boolean;
  transport?: 'lan' | 'wan';
  exclude_self?: boolean;
  limit?: number;
}

export interface GroupSendResult {
  summary: string;
  succeeded: string[];
  failed: string[];
  per_agent: Record<string, DiscoverySendOutcome>;
  targets: DiscoveredAgent[];
}

// ---- read-side -------------------------------------------------------------

export const discoveryApi = {
  /** All known peer agents (LAN + WAN merged). */
  listAgents(includeSelf = false) {
    return apiRouter.execute<{ agents: DiscoveredAgent[]; total: number }>(
      { method: 'discovery.list_agents' },
      { include_self: includeSelf },
    );
  },

  /** All known peer nodes (each running eCan instance). */
  listNodes(includeSelf = false) {
    return apiRouter.execute<{ nodes: DiscoveredNode[]; total: number }>(
      { method: 'discovery.list_nodes' },
      { include_self: includeSelf },
    );
  },

  /** Filtered search (skill, role, name_contains, transport, …). */
  findAgents(params: FindAgentsParams) {
    return apiRouter.execute<{ agents: DiscoveredAgent[]; total: number }>(
      { method: 'discovery.find_agents' },
      params,
    );
  },

  /** "What skills are available across the fleet right now?" → `{name: count}`. */
  listSkills(org?: string) {
    return apiRouter.execute<{ skills: Record<string, number>; total: number }>(
      { method: 'discovery.list_skills' },
      { org },
    );
  },

  /** Which transport would the router use for this agent_id right now? */
  transportFor(agentId: string) {
    return apiRouter.execute<{ agent_id: string; transport: DiscoveryTransport }>(
      { method: 'discovery.transport_for' },
      { agent_id: agentId },
    );
  },

  /** LAN/WAN active, counts, full directory snapshot. */
  getStatus() {
    return apiRouter.execute<DiscoveryStatus>(
      { method: 'discovery.get_status' },
      {},
    );
  },

  // ---- write-side ---------------------------------------------------------

  /** Send one A2A payload — router picks LAN-direct or WAN-relay. */
  sendToAgent(agentId: string, payload: unknown, opts?: { fromAgentId?: string; timeout?: number }) {
    return apiRouter.execute<DiscoverySendOutcome>(
      { method: 'discovery.send_to_agent' },
      {
        agent_id: agentId,
        payload,
        from_agent_id: opts?.fromAgentId,
        timeout: opts?.timeout,
      },
    );
  },

  /** Fanout to an explicit list of agent_ids. */
  sendToGroup(agentIds: string[], payload: unknown, opts?: {
    fromAgentId?: string; timeout?: number; maxConcurrency?: number;
  }) {
    return apiRouter.execute<GroupSendResult>(
      { method: 'discovery.send_to_group' },
      {
        agent_ids: agentIds,
        payload,
        from_agent_id: opts?.fromAgentId,
        timeout: opts?.timeout,
        max_concurrency: opts?.maxConcurrency,
      },
    );
  },

  /** Find-then-send. mode = "any" | "all" | "n=K". */
  sendToSkill(skill: string, payload: unknown, opts?: {
    mode?: 'any' | 'all' | `n=${number}`;
    fromAgentId?: string;
    timeout?: number;
    role?: string;
  }) {
    return apiRouter.execute<GroupSendResult>(
      { method: 'discovery.send_to_skill' },
      {
        skill,
        payload,
        mode: opts?.mode || 'any',
        from_agent_id: opts?.fromAgentId,
        timeout: opts?.timeout,
        role: opts?.role,
      },
    );
  },
};
