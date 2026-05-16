# Agent Discovery — Test Plan

Companion to [`agent-discovery.md`](./agent-discovery.md). This doc covers
how to verify the discovery + A2A routing system is working end-to-end,
from cheapest test (one machine, no real agents) to most realistic
(two machines on different networks).

## Test ladder

| # | Test | Setup cost | What it catches |
|---|---|---|---|
| 1 | Single-process smoke test | seconds | Code-level regressions in zeroconf advertise/browse/router |
| 2 | Two-machine LAN | ~5 min | Real multicast on your network; UI host-tag colors |
| 3 | Two-machine WAN | ~10 min | AppSync schema deploy; cloud relay end-to-end |

Run them in order. Each builds on the previous.

---

## 1. Single-process smoke test

`tests/_smoke_discovery.py` spins up two `LanDiscoveryService` instances
in one Python process, on different machine_ids, and validates discovery
+ querying + routing without needing a second machine.

### Run it

```bash
PYTHONIOENCODING=utf-8 python tests/_smoke_discovery.py
```

(The `PYTHONIOENCODING=utf-8` is only needed on Windows cp1252 default
codepages so emoji/arrows in the output don't crash the print stream.)

### Expected output

15 checks, all PASS, exit code 0. The tail of a healthy run looks like:

```
[PASS] Alice sees Bob's hotel agent
[PASS] Alice sees Bob's email agent
[PASS] Alice does NOT see her own air agent (exclude_self)
[PASS] Bob sees Alice's air agent
[PASS] Bob sees Alice's manager agent
[PASS] Bob does NOT see his own hotel agent
[PASS] Alice sees Bob's node
[PASS] Bob sees Alice's node
[PASS] find_agents(skill='find_hotel') from Alice -> ['agent_bob_hotel']
[PASS] find_agents(skill='currency_convert') from Alice -> ['agent_bob_hotel']
[PASS] find_agents(role='utility') from Alice -> ['agent_bob_email']
[PASS] transport_for(agent_bob_hotel) -> 'lan' (expected 'lan')
[PASS] transport_for(missing) -> 'none' (expected 'none')
[PASS] send_to_agent (LAN-attempt-then-fail-with-no-WAN) -> transport='unreachable' success=False
[PASS] send_to_agent(missing) -> 'unreachable' (expected unreachable)

PASSES: 15   FAILURES: 0
ALL PASS
```

### What's covered

- Zeroconf advertise + browse over loopback multicast
- Per-node and per-agent record types
- `exclude_self` filter
- `find_agents` filtering by skill / role
- Router transport selection (`transport_for`)
- Router LAN attempt with failover (verified via log line
  `[discovery.router] LAN to ... failed; falling back to WAN`)

### What's NOT covered

- The Python ↔ JS IPC layer
- The React UI components (`<AgentHostTag>`, `<SkillFinder>`)
- AppSync cloud directory + WAN relay (those need a deployed schema
  and at least one round trip through AWS)
- Real cross-machine network behavior (NAT, firewall, multicast
  filtering on real WiFi)

For those, see tests 2 and 3.

---

## 2. Two-machine LAN test

Two boxes on the same physical LAN, same eCan user account. Verifies
real zeroconf and cross-machine A2A.

### Prerequisites

| Item | Why | Verify |
|---|---|---|
| Both machines on the same subnet | Routers don't forward multicast between subnets without IGMP snooping | On each box: `ipconfig` (Win) / `ip addr` (Linux). First three octets should match, e.g. both `192.168.1.x` |
| Same eCan user account on both | Discovery filters by `org` slug = sanitized user email. Cross-account peers are invisible by design | Both signed in as the same email (e.g. `songc@yahoo.com`) |
| OS-level mDNS responder running | Multicast plumbing | macOS: built in. Windows 10+: built in. Test independently: `ping <peer-hostname>.local` from one machine to the other |
| Firewall allows UDP 5353 (mDNS) + the A2A ports (3600-3611) | Without this, machines discover but can't actually send | Windows Defender Firewall: allow inbound for `python.exe` / your eCan installer. Or temporarily disable for the test |
| Latest eCan build on both | Old builds don't run the new discovery stack | Grep the log: `grep "\[discovery.zeroconf\] starting" runlogs/eCan.log` should hit at least once per launch |

### Step-by-step

**1. Start machine A and wait for the GUI to be up.**

Verify discovery is running:
```bash
grep "discovery.zeroconf.*starting\|registered node service\|LAN discovery advertising" runlogs/eCan.log | tail -5
```
Expected output:
```
[discovery.zeroconf] starting — machine_id=<uuid> org=<your_email_slug> ip=192.168.1.x role=<role>
[discovery.zeroconf] registered node service '<machine-name>-<id>._ecan-node._tcp.local.' on port 4668
[MainWindow] 🌐 LAN discovery advertising N agent(s)
```

**2. Start machine B.** Same checks on B's `runlogs/eCan.log`.

**3. Verify they see each other.** Within ~5–10 s of B starting, A's log should show:
```bash
grep "node up\|agent up" runlogs/eCan.log | tail -10
```
Expected output on A:
```
[discovery.zeroconf] node up: '<B-name>' machine_id=xxxxxxxx.. at 192.168.1.42:4668 role=Platoon
[discovery.zeroconf] agent up: agent_xxxx name='<some agent on B>' at 192.168.1.42:3601
```
And B's log should show the same about A.

**4. Visual check in the UI.** On the Agents page on machine A,
agents running on B should show a 🔵 blue tag `on <B-name>` instead of
the 🟢 green `this PC` of local agents. Hover for the tooltip showing
the agent's LAN URL.

**5. One-liner directory check.** From DevTools console on either machine:
```js
const r = await window.__ipc_api.call('discovery.get_status', {});
console.log({
  self: r.data.self_machine_id?.slice(0, 8),
  lan: r.data.lan_active,
  wan: r.data.wan_active,
  peers: r.data.agents_known,
  nodes: r.data.nodes_known,
});
```
Healthy output (with at least one peer running):
```
{ self: 'a1b2c3d4', lan: true, wan: <true|false>, peers: 4, nodes: 1 }
```

**6. Cross-machine A2A send (LAN-direct).** From DevTools console on A:
```js
const r = await window.__ipc_api.call('discovery.find_agents', {
  machine_id: '<machine-B-uuid-from-step-3>'
});
console.log('Agents on B:', r.data.agents.map(a => a.agent_id));

// Send a ping to one of B's agents
const send = await window.__ipc_api.call('discovery.send_to_agent', {
  agent_id: '<one of B's agent_ids>',
  payload: { jsonrpc: '2.0', method: 'ping', params: {} },
});
console.log(send.data);
```
Expected: `{ transport: 'lan', success: true, response: ... }`.
On machine B's log:
```bash
grep "incoming HTTP POST\|_a2a_via\|bridged" runlogs/eCan.log | tail -5
```

**7. SkillFinder UI check.** On machine A, click the "Find agent by
skill" box at the top right of the Agents page. Type a skill that
only one of B's agents has. The popover should show B's agent with
the blue LAN tag. Click → opens a chat that routes to B.

### Pass criteria

- Both machines log peer-up events for each other within ~10 s.
- `discovery.get_status` reports `nodes_known >= 1`, `agents_known >= 1`.
- Agent cards for B's agents show the blue `on <B-name>` tag on A,
  and vice versa.
- `discovery.send_to_agent` returns `{ transport: 'lan', success: true }`.

---

## 3. Two-machine WAN test (off-LAN reach)

The full "I'm on the road but want to call my office agents" test.

### Prerequisites

| Item | Why |
|---|---|
| All from test 2 prerequisites | WAN doesn't replace LAN; both layers run |
| **AppSync schema deployed** | Without the new `AgentEndpoint` + `A2AMessage` types, the cloud directory + relay fall back silently. See section "Schema deploy" below |
| Two machines on **different** networks | The whole point. Easy way: put one on your phone hotspot |
| Both machines logged in as the same eCan user | Same as LAN — `org` filtering applies to cloud too |

### Schema deploy (one-time)

The Phase 2 schema additions live in `agent/cloud_api/appsync_schema.graphql`
(search for the `# A2A WAN discovery + relay (Phase 2)` comment block).
Push them to your AppSync stage via whatever pipeline you normally use
(AWS console, Amplify CLI, CloudFormation, etc.).

After deploy, verify by grepping any machine's log on next startup:

```bash
grep "Phase 2 schema.*hasn't been deployed" runlogs/eCan.log
```

Empty output = schema is live. If the warning appears, the client is
still falling back to LAN-only operation; deploy again or check that
your AppSync stage is the one the app is pointed at
(`mainwin.getWanApiEndpoint()`).

### Step-by-step

**1. Both machines online (different networks).** Bring up A on your
office network and B on a hotspot or remote network.

**2. Verify the cloud directory client is running on both.**
```bash
grep "CloudDirectoryClient started\|inbox subscription started\|WAN cloud directory started" runlogs/eCan.log | tail -8
```
Expected output (per machine):
```
[discovery.cloud] CloudDirectoryClient started — org=<slug> machine_id=<id>.. endpoint=https://...appsync-api...
[discovery.cloud] inbox subscription started for agent_xxxx
[MainWindow] 🌐 WAN cloud directory started — N agent(s) advertised; router now LAN+WAN aware
```

**3. Verify each side sees the other via the cloud (not LAN).** On A's
log:
```bash
grep "WAN endpoint up" runlogs/eCan.log | tail -5
```
Expected:
```
[discovery.cloud] WAN endpoint up: agent_id=<id> machine_id=<B's id prefix>.. name='<B's agent>'
```

In the UI on A, agents on B should now show the 🟣 purple tag `on <B-name>`
with the tooltip "reachable via cloud relay (off-LAN)". The blue LAN tag
should NOT appear because A and B aren't on the same multicast network.

**4. Cross-machine A2A send (WAN-relayed).** From DevTools on A:
```js
const send = await window.__ipc_api.call('discovery.send_to_agent', {
  agent_id: '<one of B's agent_ids>',
  payload: { jsonrpc: '2.0', method: 'ping', params: {} },
});
console.log(send.data);
```
Expected: `{ transport: 'wan', success: true, response: ... }`.

On machine B's log:
```bash
grep "bridged WAN.*local A2A\|_a2a_via.*wan_relay" runlogs/eCan.log | tail -5
```
Expected:
```
[MainWindow] 🌐 bridged WAN->local A2A for <agent_id> (http://localhost:3601/a2a/) status=200
```

**5. SkillFinder via WAN.** Same as test 2 step 7, but the matching
agent's tag in the popover should be 🟣 purple `WAN` instead of 🔵 blue
`LAN`.

### Pass criteria

- Both machines log `CloudDirectoryClient started`.
- Per-agent inbox subscriptions started (one per local agent).
- `discovery.get_status` reports `wan_active: true`, `agents_known >= 1`.
- Off-LAN peer agents show 🟣 purple tags in the UI.
- `discovery.send_to_agent` returns `{ transport: 'wan', success: true }`.
- The receiving side's log shows the WAN-to-local bridge in action.

---

## Troubleshooting

### "Both sides log 'advertising' but see ZERO peers"

Almost always multicast blocked: corporate Wi-Fi, VPN, or some
consumer routers (especially "guest" SSIDs) filter `224.0.0.251`.

**Diagnose:** independent of eCan, test mDNS:
- macOS: `dns-sd -B _ecan-node._tcp local.` on the peer machine
- Windows: `Get-Service Bonjour` should show Running. If it doesn't,
  install Bonjour Print Services or use one of the alternatives
- Linux: `avahi-browse -a` should list things

If standard mDNS doesn't work on your LAN, deploy the AppSync schema
and rely on WAN relay even for same-LAN peers.

### "Peer's host tag stays gray 'Vehicle' instead of blue 'on <peer>'"

Discovery polling not running. Two likely causes:

1. You're on a page other than the Agents page. The poll starts on
   `Agents.tsx` mount and stops on unmount. To extend coverage to
   other pages, call `useDiscoveryStore.getState().startAutoRefresh()`
   from those pages too.

2. The Python backend isn't running discovery. Check:
   `grep "discovery.zeroconf.*starting" runlogs/eCan.log`. Absent →
   look for import errors above that point in the log.

### "`discovery.send_to_agent` returns transport='unreachable' even though LAN tag is blue"

Firewall blocking the A2A port. On machine B:
```
netstat -an | findstr 3601
```
Should show `LISTENING`. From A:
```
Test-NetConnection <B-ip> -Port 3601
```
Should succeed. If it doesn't, open the port in Windows Defender Firewall
for `python.exe` (dev) or your eCan installer (production).

### "WAN test: `discovery.get_status` shows `wan_active: false`"

Either the schema isn't deployed, or the AppSync auth is failing.
Check:
```bash
grep "discovery.cloud" runlogs/eCan.log | tail -20
```
Look for `Phase 2 schema ... hasn't been deployed yet` (deploy fix)
or `Failed to ...` errors (check Cognito token, endpoint URL).

### "Two different agents on different machines appear as one"

They're sharing an `agent_id`. The directory dedupes on `agent_id`, so
the entry collapses with both `lan_url` and `wan_relay_channel` set.
Fix the `agent_id` source so each agent has a unique id.

---

## Quick health one-liner

After both machines are up for ~30 s:

```js
const r = await window.__ipc_api.call('discovery.get_status', {});
console.log({
  self: r.data.self_machine_id?.slice(0, 8),
  lan: r.data.lan_active,
  wan: r.data.wan_active,
  peers: r.data.agents_known,
  nodes: r.data.nodes_known,
});
```

Healthy:
```
{ self: 'a1b2c3d4', lan: true, wan: true, peers: 4, nodes: 1 }
```

`peers` and `nodes` both 0 after 30 s on a known-multicast LAN means
discovery startup failed silently. Grep the log for `[discovery.`
errors and report.
