# Agent Discovery & A2A Routing

> Status: shipped in 5 staged phases between 2026-05-15 and 2026-05-16.
> Replaces the legacy `agent/network/network.py` Commander/Platoon UDP
> protocol with zeroconf (LAN) + AppSync (WAN) for both peer discovery
> and agent-to-agent messaging.

---

## TL;DR for users

- Every `AgentCard` on the Agents page now shows a small tag indicating
  which machine the agent runs on:
  - 🟢 green "this PC" — local agent
  - 🔵 blue "on `<machine>`" — peer on your LAN
  - 🟣 purple "on `<machine>`" + tooltip "via cloud relay" — peer
    reachable only over the internet (you're traveling, peer is at the
    office, etc.)
- At the top right of the Agents page there's a "Find agent by skill"
  search. Type a skill name; results show every agent (local or remote)
  that advertises it. Click → opens a chat with that agent.
- Group sends are available programmatically: a single call can fan
  out to "every manager," "any one of these agents," or "the first
  agent on the LAN that can do X."

---

## TL;DR for developers

- **Backend:** all the moving parts live under `agent/a2a/discovery/`.
  Public API is in `agent/a2a/discovery/__init__.py`.
- **Front-end:** typed IPC bindings in
  `gui_v2/src/services/api/discoveryApi.ts`; a Zustand store in
  `gui_v2/src/stores/domain/discoveryStore.ts`; the host-tag widget in
  `gui_v2/src/pages/Agents/components/AgentHostTag.tsx`; the skill
  search in `gui_v2/src/pages/Agents/components/SkillFinder.tsx`.
- **Schema:** added to `agent/cloud_api/appsync_schema.graphql`
  (search for `# A2A WAN discovery + relay (Phase 2)`). The client
  gracefully degrades if the schema isn't deployed yet — it logs one
  warning and falls back to LAN-only operation.
- **Migration knob:** set `ECAN_LEGACY_LAN_DISCOVERY=0` to disable the
  legacy Commander/Platoon protocol once all your machines are on the
  new code.

---

## Architecture

```
                 ┌──────────────────────────────────────────┐
                 │              one eCan instance            │
                 │                                          │
                 │  Local agents (with allocated A2A port)  │
                 │              │                           │
                 │              ▼                           │
                 │   AgentDirectory  ◄── LAN ─── zeroconf   │
                 │   (in-process)    ◄── WAN ─── AppSync    │
                 │              │                           │
                 │              ▼                           │
                 │   router.send_to_agent(agent_id, ...)    │
                 │       │                                  │
                 │       ├── LAN HTTP POST                  │
                 │       └── WAN: AppSync sendA2AMessage    │
                 │                       │                  │
                 └───────────────────────┼──────────────────┘
                                         │
                          ┌──────────────┼──────────────┐
                          │                             │
                          ▼                             ▼
                   another LAN peer            another WAN peer
                   (zeroconf-visible)          (cloud-relayed)
```

Two parallel discovery channels populate the same in-process
`AgentDirectory`:

1. **Zeroconf / DNS-SD** (LAN). Each eCan instance advertises:
   - one `_ecan-node._tcp.local.` per install
   - one `_ecan-agent._tcp.local.` per agent
   TXT records carry `agent_id`, `machine_id`, `org`, `skills`,
   `a2a_port`, `auth_fp`, and a few other fields. The browser feeds
   discovered peers into the directory.

2. **AppSync cloud directory** (WAN). Each agent is upserted into the
   `AgentEndpoint` cloud table with a 60 s heartbeat. Each agent also
   subscribes to `onA2AMessage(toAgentId=<self>)` so it can receive
   relayed messages no matter where the sender is.

`router.send_to_agent(agent_id, payload)` looks up the agent in the
directory and picks:

1. **LAN-direct HTTP POST** if `lan_url` is set and was recently
   reachable (30 s probe cache).
2. **WAN relay via AppSync** if LAN isn't viable.
3. **Error `UnreachableAgent`** otherwise.

The receiving side runs a tiny bridge that converts incoming WAN
messages into a local HTTP POST to the agent's `a2a_port` — the
existing A2A handler chain processes them exactly the same as a LAN
call.

---

## Deployment requirements

| Component | Where | Notes |
|---|---|---|
| `zeroconf==0.148.0` | already in `requirements-base.txt` | nothing to install |
| Multicast UDP `224.0.0.251:5353` open on the LAN | network admin | corporate VPNs and some Wi-Fi APs block multicast — the WAN relay is the fallback there |
| New GraphQL types | `agent/cloud_api/appsync_schema.graphql` | deploy via your usual AppSync push pipeline. Required for WAN. Without it, only the warning `Phase 2 schema (AgentEndpoint / A2AMessage) hasn't been deployed yet` appears and LAN keeps working. |
| Cognito auth | already configured for AppSync | the new mutations/subscriptions reuse the same auth as everything else under AppSync |

---

## Migration phases (history)

| # | What | Status | Memory note |
|---|---|---|---|
| 1 | Per-node + per-agent LAN advertising via zeroconf; `AgentDirectory` populated | shipped 2026-05-16 | `project-discovery-phase1` |
| 2 | AppSync cloud directory + `A2AMessage` relay; `router.send_to_agent`; WAN→local bridge | shipped 2026-05-16 (needs schema deploy) | `project-discovery-phase2` |
| 3 | `find_agents` filtered queries; `send_to_group` / `send_to_skill` / `broadcast_to_role` fanout; IPC handlers (`discovery.*`) | shipped 2026-05-16 | `project-discovery-phase3` |
| 4 | `UnifiedMessenger` falls back to `AgentDirectory` for LAN URLs; legacy protocol gated by `ECAN_LEGACY_LAN_DISCOVERY` env var (default ON); deprecation log; `network.py` NOT deleted yet | shipped 2026-05-16 | `project-discovery-phase4` |
| 5 | Front-end: `<AgentHostTag>` inline on every AgentCard + Orgs/AgentList; `<SkillFinder>` widget; `useDiscoveryStore` Zustand store; full IPC bindings | shipped 2026-05-16 | `project-discovery-phase5` |

### When to flip `ECAN_LEGACY_LAN_DISCOVERY=0`

1. Confirm every customer machine logs `[discovery.zeroconf] starting` at startup (= the new LAN code is live everywhere).
2. Confirm the cloud directory works (no `Phase 2 schema hasn't been deployed yet` warnings).
3. Set the env var to `0` on one or two machines. Verify they still see and are seen by other peers (`discovery.list_agents` returns the same set as before).
4. Roll the env var (or flip the default in code) to every machine.
5. After one more release cycle without issues, physically delete `agent/network/network.py` and the references in `gui/MainGUI.py`.

---

## API reference

### Python — backend

```python
from agent.a2a.discovery import (
    get_machine_id, get_directory,
    find_agents, find_one_agent, list_skills,
    send_to_agent, send_to_group, send_to_skill, broadcast_to_role,
    SendResult, SendOutcome, GroupSendReport,
    transport_for, list_known_agents,
)

# Discovery state
get_directory().list_agents(exclude_self=True)       # all known peers
list_skills(org="songc_yahoo_com")                   # {skill_name: count}
transport_for("agent_xxx")                           # "lan" | "wan" | "lan+wan" | "none"

# Search
find_agents(skill="find_air_ticket", reachable=True)
find_agents(skill_all=("find_air_ticket", "coordinate"))
find_agents(role="manager", machine_id="<id>")
find_one_agent(skill="email")

# Send
outcome = await send_to_agent("agent_xxx", {...payload...})
report  = await send_to_group(["agent_a", "agent_b"], {...})
report  = await send_to_skill("find_air_ticket", {...}, mode="any")   # first reachable
report  = await send_to_skill("notify_managers", {...}, mode="all")   # broadcast
report  = await send_to_skill("scrape_x", {...}, mode="n=3")          # top 3 by transport pref
report  = await broadcast_to_role("manager", {...})
```

`SendOutcome` fields: `transport` (`"lan"|"wan"|"unreachable"`),
`success` (bool), `error` (str|None), `response` (dict|None).

`GroupSendReport`: `targets`, `per_agent`, helpers `succeeded`,
`failed`, `all_succeeded`, `any_succeeded`, `summary()`.

### TypeScript — front-end

```ts
import { discoveryApi } from '@/services/api/discoveryApi';
import { useDiscoveryStore } from '@/stores/domain/discoveryStore';

// Subscribe to the directory from a React component
const agents = useDiscoveryStore(s => s.agents);
const lanActive = useDiscoveryStore(s => s.lanActive);
const wanActive = useDiscoveryStore(s => s.wanActive);

// Imperative calls
const { data } = await discoveryApi.listAgents();
const { data } = await discoveryApi.findAgents({ skill: 'find_air_ticket', reachable: true });
const { data } = await discoveryApi.sendToSkill('notify_managers', { event: 'x' }, { mode: 'all' });

// Bootstrap (already done on the Agents page)
useDiscoveryStore.getState().startAutoRefresh(15000);
```

### IPC handlers (Python ↔ JS)

| IPC method | Purpose |
|---|---|
| `discovery.list_agents` | All known peer agents (LAN + WAN merged) |
| `discovery.list_nodes` | All known peer nodes |
| `discovery.find_agents` | Filtered search (skill / role / name_contains / transport / limit) |
| `discovery.list_skills` | `{skill_name: count_of_agents}` across the org |
| `discovery.transport_for` | Which transport would be used for an `agent_id` right now |
| `discovery.get_status` | LAN/WAN active flags + full directory snapshot |
| `discovery.send_to_agent` | Send one A2A payload (router picks transport) |
| `discovery.send_to_group` | Parallel fanout to an explicit list of agent_ids |
| `discovery.send_to_skill` | Find + send (`mode = "any" | "all" | "n=K"`) |

---

## TXT record schema (zeroconf)

`_ecan-node._tcp.local.`:

```
v=1
machine_id=<UUID>
machine_name=SCHOME
org=<sanitized email>
role=Commander|Platoon|Staff_Officer
os=Windows|Mac|Linux
arch=x86_64
ecan_ver=0.7.0
agent_count=12
api_port=4668
auth_fp=<8-char HMAC fingerprint>
ts=<unix seconds>
```

`_ecan-agent._tcp.local.`:

```
v=1
agent_id=agent_xxxx
machine_id=<UUID>
org=<sanitized email>
name=<display name>
role=manager|specialist|...
skills=skill1,skill2,...        # truncated if > 200 chars; use skills_hash fallback
tasks=task1,task2,...
a2a_port=3608
a2a_path=/a2a/
auth_fp=<8-char HMAC fingerprint>
ts=<unix seconds>
```

`auth_fp` is `HMAC-SHA256(org_secret, target_id)[:8]` where `org_secret`
is derived from the org slug in v1. It's a weak filter — prevents
accidental cross-account discovery on shared LANs, not a real auth
boundary. v2 will replace the derivation with a per-org Cognito secret.

## GraphQL schema (WAN)

```graphql
type AgentEndpoint {
  id: ID!                    # = agent_id
  machineId: String!
  org: String!
  name: String
  role: String
  skills: String             # CSV
  a2aRelayChannel: String!
  lanHint: String            # JSON: {host, port, path}
  ecanVer: String
  os: String
  lastSeen: AWSTimestamp
  ttl: Int
}

type A2AMessage {
  id: ID!
  toAgentId: String!
  fromAgentId: String!
  org: String!
  payload: AWSJSON!
  timestamp: AWSDateTime!
}

mutation upsertAgentEndpoint(input: AgentEndpointInput!): AgentEndpoint
mutation deleteAgentEndpoint(id: ID!): AgentEndpoint
mutation sendA2AMessage(input: A2AMessageInput!): A2AMessage
query    queryAgentEndpoints(org: String!): [AgentEndpoint]!

subscription onA2AMessage(toAgentId: String!): A2AMessage
  @aws_subscribe(mutations: ["sendA2AMessage"])
subscription onAgentEndpointChanged(org: String!): AgentEndpoint
  @aws_subscribe(mutations: ["upsertAgentEndpoint", "deleteAgentEndpoint"])
```

---

## Troubleshooting

### "I don't see any peer agents in the host tag"

1. Check that zeroconf is running:
   `grep '\[discovery.zeroconf\] starting' runlogs/eCan.log`
   If absent → look for import errors above that point.
2. Check that the directory has peers:
   in DevTools console, `await window.__ipc_api.call('discovery.list_agents', {})`.
   If `agents: []` → the peer machine isn't being seen.
3. Check that the other machine is advertising:
   on the peer, `grep '\[discovery.zeroconf\] registered node service' runlogs/eCan.log`.
4. If both sides log advertising/browsing but see nothing →
   multicast is likely blocked on the network. Verify with
   `dns-sd -B _ecan-node._tcp local.` on macOS or
   `Get-Service Bonjour` on Windows.

### "WAN routing doesn't work"

1. Schema deployed?
   `grep "Phase 2 schema.*hasn't been deployed" runlogs/eCan.log`.
   If present → push the new schema additions in
   `agent/cloud_api/appsync_schema.graphql` to your AppSync stage.
2. Cloud directory running?
   `grep "CloudDirectoryClient started" runlogs/eCan.log`.
3. Inbox subscription started?
   `grep "inbox subscription started for" runlogs/eCan.log`.
4. On the sending side, check the router decision:
   `grep "router.*to .* failed" runlogs/eCan.log` for fallback chains.

### "Slow startup"

The discovery system has near-zero startup cost (zeroconf
advertisement and the cloud subscription start in the background).
If startup is slow, see the separate memory note
`project-startup-apphang` for the agent-skill-build investigation
that produced the modal overlay + tracemalloc forensics work.

### "Two agents with the same name appear twice"

Either an `agent_id` was reused on two machines (intentional?), or
zeroconf and the cloud directory both happen to return the same
agent. The directory deduplicates on `agent_id` — same id from both
sources collapses to one entry with both `lan_url` and
`wan_relay_channel` set, and `<AgentHostTag>` shows the LAN-preferred
indicator. If you genuinely have two different agents with the same
id on different machines, fix the id generation.

---

## Files of interest

### Backend (Python)

| File | Role |
|---|---|
| `agent/a2a/discovery/__init__.py` | Public API surface |
| `agent/a2a/discovery/machine_id.py` | Persistent per-install UUID |
| `agent/a2a/discovery/auth.py` | `auth_fp` HMAC helper |
| `agent/a2a/discovery/directory.py` | `AgentDirectory` + `AgentEndpoint` / `NodeEndpoint` dataclasses |
| `agent/a2a/discovery/zeroconf_service.py` | LAN advertiser + listener |
| `agent/a2a/discovery/cloud_directory.py` | AppSync upsert + heartbeat + per-agent inbox subscription |
| `agent/a2a/discovery/wan_relay.py` | `sendA2AMessage` / `onA2AMessage` thin wrappers |
| `agent/a2a/discovery/router.py` | `send_to_agent` — LAN-vs-WAN routing decision |
| `agent/a2a/discovery/query.py` | `find_agents`, `list_skills` |
| `agent/a2a/discovery/group.py` | `send_to_group`, `send_to_skill`, `broadcast_to_role` |
| `gui/ipc/w2p_handlers/discovery_handler.py` | IPC handlers exposed to the front-end |
| `agent/cloud_api/appsync_schema.graphql` | GraphQL schema additions (must be deployed) |
| `agent/network/network.py` | Legacy protocol — gated by `ECAN_LEGACY_LAN_DISCOVERY`, NOT yet deleted |
| `agent/chats/unified_messenger.py` | `_discover_lan_url_fallback()` — legacy LAN sends now consult `AgentDirectory` |

### Front-end (TypeScript / React)

| File | Role |
|---|---|
| `gui_v2/src/services/api/discoveryApi.ts` | Typed IPC bindings |
| `gui_v2/src/stores/domain/discoveryStore.ts` | Zustand store with 15 s auto-refresh |
| `gui_v2/src/pages/Agents/components/AgentHostTag.tsx` | Inline machine indicator on every AgentCard |
| `gui_v2/src/pages/Agents/components/SkillFinder.tsx` | "Find agent by skill" search widget |
| `gui_v2/src/pages/Agents/OrgNavigator.tsx` | Hosts the SkillFinder above the agent grid |
| `gui_v2/src/pages/Agents/Agents.tsx` | Bootstraps the discovery store auto-refresh on page mount |
| `gui_v2/src/pages/Agents/components/AgentCard.tsx` | Renders `<AgentHostTag>` |
| `gui_v2/src/pages/Orgs/components/AgentList.tsx` | Renders `<AgentHostTag compact>` in the org tree view |
| `gui_v2/src/i18n/locales/en-US.json` + `zh-CN.json` | i18n keys: `hostPrefix`, `hostLocal`, `hostViaCloud`, `findBySkillTitle`, etc. |

---

## How to verify it's working

See [`agent-discovery-test-plan.md`](./agent-discovery-test-plan.md) — a
ladder of three tests (single-process smoke, two-machine LAN,
two-machine WAN) with exact commands, expected output, and the most
common failure modes.

The single-process smoke test can be run with one command on any
machine that has the codebase checked out:

```bash
PYTHONIOENCODING=utf-8 python tests/_smoke_discovery.py
```

Expected: 15 checks PASS, exit code 0.

## Internal-memory notes (for future sessions)

If you're a future agent working on this codebase, see:

- `~/.claude/projects/.../memory/project_discovery_phase1.md` … `phase5.md`
- `~/.claude/projects/.../memory/MEMORY.md` (index)

They cover the decision history and dead-ends already attempted
(don't re-try the per-creator executor offload in `_create_skills_batch`
or `await asyncio.sleep(0)` per skill — both were tried and reverted
the same day; both made startup 10–25× slower).
