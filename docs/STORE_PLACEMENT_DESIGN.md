# Store placement — the assignment decides where a store runs

_Status: design sketch, 2026-09-24. Not implemented. Supersedes nothing; extends
the Phase D store registry (`agent/cloud_api/store_api.py`, Settings → Stores)._

## The two problems

1. **Duplicate runs across machines.** `agent_launch_allowed`
   (`agent/ec_agents/vehicle_affinity.py`) starts an agent when it is pinned
   here, has **no** pin ("no-affinity"), or has a pin naming no machine this
   host knows ("stale-pin-adopt"). The last two are true on *every* machine of
   the account, so a second machine starts the same agents and a customer gets
   two replies. Unforgivable on 飞鸽.
2. **Assignment is display-only.** `store_assign` writes
   `stores.assigned_vehicle_id`; nothing on a machine reads it. Assigning store
   X to machine B changes the Stores tab and nothing else.

One mechanism fixes both: **for a store-bound agent, the store's assignment is
the only thing that decides which machine runs it.**

## Rule

An agent is **store-bound** when any of its tasks carries an explicit
`task_vars.store_id` (Fast Deploy writes it on every task of a store's front
desk + Q&A group). Everything else is **unbound** and keeps today's vehicle-pin
rules unchanged.

For a store-bound agent of store S, on machine M:

| S's assignment (cloud, or cached)  | Decision on M |
|---|---|
| assigned to M                      | run |
| assigned to another machine        | **do not run** — whatever its vehicle pin says |
| unassigned                         | **claim** S for M (atomic, below); run only if the claim wins |
| unknown: cloud unreachable, no cache | run, WARNING (see D2) |

The vehicle pin is ignored for store-bound agents. Fail-open "no-affinity" and
"stale-pin-adopt" no longer apply to them, which removes the duplicate source.

The worker-placement gate (`agent/ec_tasks/worker_placement.py`) stays where
it is, *after* this one: this gate answers "which machine", that one "which
process on it". An agent spanning two stores is refused with an ERROR, matching
how worker placement treats two isolation domains.

## Components

### Client (eCan.ai)

1. **`agent/ec_agents/store_placement.py`** — `store_of_agent(agent)`,
   `placement_for_store(store_id) -> run | skip | claim`, reading a local
   assignment cache. Pure, testable, no network.
2. **Assignment cache** — last `store_list(vehicle_id=me)` result persisted in
   the user data dir (`store_assignments.json`, owner-scoped). This is what lets
   a machine keep serving its stores through a cloud outage — the design doc's
   "machines are autonomous workers" rule.
3. **Gate in `EC_Agent.start()`** — ahead of the vehicle gate; store-bound
   agents skip the vehicle gate entirely.
4. **Reconciler, on each heartbeat after `store_report`** —
   `store_list(vehicle_id=me)` → desired set D; running store set R.
   * `D − R`: start that store's agents (and `WorkerSupervisor.reconcile` with
     their isolation keys — this is the missing trigger W2 recorded).
   * `R − D`: **drain then stop** that store's agents, then report the release.
   Needs an `EC_Agent.stop()` that does not exist today: stop taking new
   events, finish the in-flight turn, close the A2A server and the store's
   browsers.
5. **`store_report` reports what is RUNNING**, not what is allowed, and marks
   stores it has released.

### Server (eCan_lambda, CN)

1. **`store_claim`** — `UPDATE stores SET assigned_vehicle_id=$me WHERE
   store_id=$s AND owner=$o AND assigned_vehicle_id IS NULL`, returning whether
   it won. Two machines racing for one unassigned store: exactly one wins.
2. **Release** — a `store_report` item with `running: false` clears
   `reported_vehicle_id` when it equals the caller.
3. **Desktop liveness** — the desktop heartbeat must set `last_heartbeat`, and
   the reaper (`reapDeadVehicles`, today `vehicle_type='cloud'` only) must also
   offline stale desktop rows. Without it a dead machine's stores can never be
   taken over.

## Moving a store: gap over duplicate

Owner reassigns S from A to B. B must not start while A still runs S.

1. A's reconciler sees S ∉ D → drains, stops, reports release.
2. B's reconciler sees S ∈ D, but starts it only once S's
   `reportedVehicleId` is empty or B — **or** A is offline (heartbeat stale).
3. Worst case the store is unanswered for ~2 heartbeat intervals. A few minutes
   of silence is recoverable; two bots answering one customer is not.

The Stores tab already shows the in-between state ("Assigned elsewhere"). A
move to a machine that has never logged in to that store lands as
`needs_login` — the session is local by design and cannot follow.

## Migration

No step for the operator. On first start of this version every store is
unassigned; whichever machine runs it claims it. A single-machine user sees no
change. An account already running the same agents on two machines (the bug
today) converges: one claim wins, the loser's reconciler stops its copy.

## Decisions for the owner

* **D1 — unassigned stores: auto-claim (recommended) or never run until
  assigned?** Never-run is simplest and safest but stops every existing user's
  stores on upgrade until they assign each one.
* **D2 — cloud unreachable and no cache: run (recommended, WARNING) or not?**
  Not-run makes a first boot during a cloud outage silent. Run risks a
  duplicate only if two machines both first-boot during the same outage.
* **D3 — heartbeat cadence for the reconciler.** Today ~3 min (and firing twice
  per 256 ticks — fix alongside). A move gap is ~2 intervals; 60s would make it
  ~2 min.

## Build order

1. Server: `store_claim`, release, desktop liveness (+ tests, deploy).
2. Client: placement module + cache + `EC_Agent.start()` gate + claim — this
   alone closes the duplicate hole (problem 1).
3. Client: `EC_Agent.stop()` + reconciler + release — makes moves work
   (problem 2).
4. Live check on two machines: assign, move, kill the owner mid-run, cloud
   outage.
