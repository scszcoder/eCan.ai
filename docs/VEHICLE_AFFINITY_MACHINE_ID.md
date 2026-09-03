# Vehicle Affinity & Machine Identity

_Status: design + rollout. Owner: platform. Created 2026-09-03._

How eCan decides **which host runs which agent** when one account is signed
in on several machines, and how each host identifies itself. This document
supersedes the ad-hoc "persisted random UUID" identity in
`agent/a2a/discovery/machine_id.py` for affinity purposes.

Related: [agent-discovery.md](agent-discovery.md) (zeroconf/WAN directory,
which also carries `machine_id`), SHARED_SKILL_MULTI_TASK_PLAN.md Phase 1.5
(where the affinity gate was introduced).

---

## 1. The problem this solves

With one account on multiple hosts, cloud sync gives **every host the same
agents/tasks**. Without a gate, all hosts would launch all agents — N copies
of the front-desk fighting over the same store. The **vehicle-affinity gate**
(`agent/ec_agents/vehicle_affinity.py::agent_launch_allowed`) fixes this: an
agent is pinned to a **vehicle id** (a host identifier), and a host only
starts agents whose vehicle id matches its own — or agents with no pin (which
fail open and run everywhere, for back-compat).

For this to work, two independent code paths must compute the **same** id for
the same physical machine:

- the **app** at launch (`resolve_local_vehicle_id(mainwin)`), deciding
  whether to start each agent;
- the **Fast-Deploy CLI subprocess** at create time
  (`resolve_local_vehicle_id(username=…)`), stamping the pin onto new agents.

## 2. The bug (2026-09-03, customer `1050588178@qq.com`)

All 9 deployed agents were skipped at launch:

```
[AGENT_START] Skipping '前台小张' on this host: assigned to vehicle
2417627c-fbac.., local vehicle is 6562e61b-959..
```

Root cause: the old identity was a **random UUID4** persisted to
`<user_data_home>/discovery/machine_id.json`, and the two code paths derived
**different `user_data_home` values**, so each read/generated a *different*
file → two unrelated random UUIDs:

- App read `…\eCan.cn\1050588178_qq_com\discovery\machine_id.json` → `6562e61b`.
- Fast-Deploy passed `ECAN_LOG_USER` (already the derived log-user
  `1050588178_qq_com`) into `_derive_user_data_home()`, which derived it
  **again** → `…\1050588178_qq_com_local\discovery\machine_id.json` — a
  different, freshly-generated file → `2417627c`.

The identity was file-path-derived, so any inconsistency in computing that
path produced a different machine. The gate then correctly (but uselessly)
skipped every agent.

## 3. Why not hostname or MAC (and why the old code chose a UUID)

The original `machine_id.py` deliberately avoided OS-derived ids:

- **Hostnames** change (machine rename, captive-portal WiFi rewrites).
- **MACs** are NIC-bound; laptops have several (WiFi + Ethernet + VPN), so a
  MAC-based id is unstable and multi-valued.

…and chose a persisted random UUID instead. That's stable **only if every
caller computes the same file path** — which §2 shows is fragile.

## 4. The scheme: OS-native install id, normalized

Identity is derived from the **operating system's own per-install
identifier** — which is *not* NIC-based (so multi-NIC is a non-issue by
construction) and is read identically by any process on the machine,
regardless of data-home path (so §2's divergence cannot recur).

### 4.1 Per-platform source (all readable without elevation)

| Platform | Source | Read |
|---|---|---|
| **Windows** | `MachineGuid` | registry `HKLM\SOFTWARE\Microsoft\Cryptography\MachineGuid` (world-readable) via `winreg` |
| **macOS** | `IOPlatformUUID` | `ioreg -rd1 -c IOPlatformExpertDevice`, parse the `IOPlatformUUID` line |
| **Linux** | systemd machine-id | read `/etc/machine-id`, else `/var/lib/dbus/machine-id` |

### 4.2 Normalize to a UUID

The raw OS id differs in format per platform and shouldn't be exposed raw
(privacy). Hash it into a deterministic UUID5 under an eCan namespace:

```
vehicle_id = uuid5(ECAN_MACHINE_NS, raw_os_machine_id)   # 36-char UUID
```

Deterministic → the app and the CLI subprocess on the same machine always
produce the **same** id. UUID-format → drop-in compatible with everything
already keyed on the current UUID (discovery TXT records, vehicle rows).

### 4.3 Resolution order (fingerprint chain)

```
1. OS-native id  (§4.1) → uuid5            ← primary
2. persisted machine_id.json random UUID   ← fallback (existing installs,
                                              locked-down containers)
3. "" (unresolved)                         → gate fails OPEN
```

Step 2 keeps existing single-host installs working unchanged and covers
exotic environments where the OS id can't be read.

### 4.4 Hostname stays — as a label, not the key

`socket.gethostname()` is still stored on the `DBAgentVehicle` row as the
human-readable `name`/`hostname` (see `register_local_vehicle`). Only the
**matching key** is the §4.2 UUID. The UI keeps showing a friendly name.

## 5. VM / clone handling

- **Separate VM installs** each carry their own OS machine-id → correctly
  distinct vehicles.
- **Naive disk-image clones** are the only residual risk: a raw copy carries
  the same MachineGuid / machine-id. The industry-standard expectation is
  that cloning **resets** it (Windows sysprep regenerates MachineGuid;
  removing `/etc/machine-id` + `systemd-firstboot` regenerates on Linux).
  Documented as an operator responsibility. We deliberately do **not** mix in
  the SMBIOS product UUID (`Win32_ComputerSystemProduct.UUID` /
  `/sys/class/dmi/id/product_uuid`): it adds WMI/root friction and cloned VMs
  frequently share it too, so it wouldn't actually close the gap.

## 6. Migration & resilience

Switching the id source means existing agents pinned to an old random UUID
(e.g. the customer's `2417627c`) no longer match the new OS-derived id. Two
mechanisms keep fleets healthy across the transition:

1. **Gate self-heal (fail-open on unknown pins).** In
   `agent_launch_allowed`, if an agent is pinned to a vehicle id that is
   **not a known/online vehicle for this owner** and the local host is the
   only vehicle, start it anyway (reason `stale-pin-adopt`). This unblocks
   already-stranded agents (like the customer's) with no re-deploy, and makes
   the gate resilient to any future id change. It does **not** weaken the
   real multi-host case: when another host genuinely owns the pinned vehicle
   (that vehicle row exists / is online), the agent is still skipped here.

2. **Dual-id transition.** For one release the gate accepts a match on
   **either** the new OS-derived id **or** the legacy persisted id, so
   mixed-version fleets (some hosts upgraded, some not) don't strand each
   other.

## 7. Immediate operator unblock

Independent of the code change, the gate has a kill switch:

```
ECAN_DISABLE_VEHICLE_AFFINITY=1   (accepts 1/true/yes/on)
```

Set it and relaunch → the gate returns `affinity-disabled` for every agent
and all agents start on this host. Use to unblock a customer today while a
fixed build ships.

## 8. Implementation map

| File | Change |
|---|---|
| `agent/ec_agents/machine_fingerprint.py` (new) | per-platform OS-id reader + `uuid5` normalize. Lives beside `vehicle_affinity` (not under `agent/a2a/discovery/`) so it never triggers that package's eager zeroconf import — zeroconf is desktop-only, and the fingerprint must resolve in worker/CI too |
| `agent/a2a/discovery/machine_id.py` | unchanged; remains the §4.3 step-2 fallback |
| `agent/ec_agents/vehicle_affinity.py` | `resolve_local_vehicle_id` calls the fingerprint; add gate self-heal + dual-id acceptance |
| `cli/deploy/commands.py` | (no path change needed once §4 lands — id no longer depends on data-home; keep the raw-owner arg for the fallback path) |
| `tests/unit/test_vehicle_affinity.py` | per-platform fingerprint (mock registry/ioreg/file), app-vs-CLI same-id divergence test, self-heal/dual-id gate tests |

## 9. Invariants (don't regress)

- App and Fast-Deploy MUST resolve the **same** vehicle id on one machine —
  regardless of how each computes the user-data-home. (This was the whole
  bug.) Add/keep the divergence test that asserts it.
- Multi-NIC MUST NOT affect the id — no NIC/MAC in the derivation.
- Unpinned agents (`vehicle_id` empty) MUST still fail open.
- The kill switch MUST short-circuit before any resolution.
