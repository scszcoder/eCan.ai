# Unified execution — the client half (C1–C4)

Counterpart to `eCan_lambda/cn/tencent/UNIFIED_CLIENT_TODO.md`. Everything below
is in this repo; `agent/cloud_worker/**` is maintained from the eCan_lambda side
and is not touched here.

The shape of the change: work stops being *dispatched* and starts being
*queued*. A pod holds no agents; it claims turns. Association is a preference,
never a binding — which is what lets any eligible pod resume any conversation
from its checkpoint.

---

## C3 — placement declarations (done)

`residency` / `lifetime` / `requires[]` existed on `EC_Skill` and `ManagedTask`
with nothing reading them. They are now editable and they survive the trip.

**One reader:** `agent/placement.py`. These values live *inside the skill's
`config` JSON* because GraphQL `SkillUpdateInput` has no columns for them — the
same reason `run_in_cloud` lives there — so every load path has to look in two
places and agree on precedence. Last time a field like this was added it
silently no-op'd in three separate metadata whitelists; one reader is the fix.

The round trip, each hop tested separately in `tests/test_unified_c3_placement.py`:

```
skill editor (settings panel)
  -> skill JSON on disk (top level) + config
  -> _prepare_skill_data folds it into config          [gui/ipc/.../skill_handler.py]
  -> EC_Skill via apply_placement                      [build_agent_skills.py, 2 sites]
  -> ManagedTask inherits where it is silent           [agent_converter._inherit_skill_placement]
  -> turn_enqueue payload                              [agent/cloud_api/turn_queue.py]
```

Inheritance happens at `_attach_skills_and_triggers`, not in the dict converter:
the skill on a freshly-converted task is a name/id **stub**, so reading
placement there would have quietly produced defaults forever.

**Capability vocabulary** is duplicated in `gui_v2/src/types/domain/placement.ts`
because the two halves are different runtimes, with a test asserting they match.
A skill can only usefully require what a pod can advertise; drift means a turn
that queues forever.

**`residency` vs `run_in_cloud` / `hybrid_cloud_mode`:** not collapsed. Placement
is canonical for the queue path; the legacy flags still drive the launcher path
and are labelled as such in the editor. They collapse per task as tasks move
onto the queue (C4), when a consumer exists to verify the migration against.

## C1 — pods as a customer-visible resource (done)

A vehicle used to be a machine we discovered. A pod is something the customer
creates, sizes and pays for, so `agent_vehicles` gained three columns
(migration `3.1.5`): `lifecycle`, `idle_shutdown_minutes`, `desired_replicas`.

**Desired and observed state are never merged.** `desired_replicas` /
`lifecycle` are what the customer asked for; `status` / `last_heartbeat` are
what the fleet reports. A customer raising replicas should watch it converge,
and a form that showed only one of the two would be lying about the other.

- Handlers: `get_pods` / `save_pod` / `delete_pod` in `vehicle_handler.py`,
  DB-backed (`vehicle_type='cloud'`). The legacy machine handlers in the same
  file are untouched — they manage a different thing.
- UI: `pages/Vehicles/PodsPanel.tsx` + `PodFormModal.tsx`.

**Cost at the point of decision.** `always_on` is charged around the clock
whether or not anyone talks to the agent, so the figure sits next to the toggle.
Rates (`agent/pod_sizing.py`, twin in `types/domain/pod.ts`) reproduce the one
number the fleet design states: 2 vCPU / 4 GiB always-on ≈ ¥321/month
(`(2×0.12 + 4×0.05) × 730`). A test asserts that anchor. It is an estimate for a
form, not billing — the server is the authority, and per-turn spend already
lands on `turns.cost_usd`.

**Caps** are shown so nobody walks into a refusal, and are explicitly labelled
`enforced_by: server`. The client refuses to create past the cap, but that is a
courtesy, not enforcement — server S6 is where it counts.

## C2 — agent ↔ pod as affinity (done)

The agent form's "Vehicle" select is now **"Preferred pod"**
(`pages/Agents/components/PodAffinityField.tsx`), because the word chosen here
is what the next person implements against. Under a hard binding a dead pod
strands its conversations, draining means reassigning agents first, and a busy
pod blocks its agents; under soft affinity none of that happens.

Real isolation is the separate, explicitly-labelled **dedicate** checkbox. It
writes `dedicated:<agent-id>` into that pod's `capabilities` and the enqueue
path adds the matching requirement to the turn — a scheduling decision, not a
relationship. The UI says plainly that it costs availability: if that pod is
down, this agent waits.

Dedication is **derived, not stored twice**: an agent is dedicated to a pod
exactly when that pod advertises `dedicated:<agent-id>`. There is no second
field to disagree with the first.

## C4 — the trigger flip (mechanism done, flip not thrown)

`_execute_pure_cloud_task` now asks `_enqueue_cloud_task_turn` first. A task
marked for the queue is enqueued (`agent/cloud_api/turn_queue.py`); everything
else dispatches to the launcher exactly as before.

**One path per task, never two.** A task live on both paths executes twice, from
two processes, answering one customer from two places. Nothing upstream prevents
that, so this path is built so it cannot happen from here:

| Situation | What happens | Why |
|---|---|---|
| Task not marked | launcher, unchanged | nothing changes until a task is flipped |
| Marked, queue enabled, enqueue succeeds | turn enqueued, server's turn id kept | the turn id is the idempotency key; the client never mints one |
| Marked, enqueue **fails** | error returned, **no fallback** | the server may already consider it queued |
| Marked, queue **disabled** on this client | refuses to run | the scheduler may already have flipped; the launcher would be the second copy |

The per-task field is a single value (`metadata.execution_path`), not a pair of
booleans that could both be true. It needed its own line in
`agent_converter`'s metadata carry list — a scalar among dict-shaped keys — or
the flip would have silently never reached the runner.

Flipping is `set_task_execution_path` (IPC), which **requires**
`server_flipped: true` when moving to the queue and logs loudly. Deliberately
not a settings toggle: the desktop and the server's SCF timer have to move
together for a given task.

### What still blocks C4 from being thrown

1. **`turn_enqueue` does not accept a scheduled task** — it requires a
   conversation, and a scheduled task has none (server S2).
2. **A turn names no task** — the payload carries `task_id` inside the turn's
   input JSON as a stopgap; the durable fix is server S0.
3. **The desktop has no credential for it.** `turn_enqueue` authenticates with
   the internal shared token, which a desktop install does not hold and should
   not be given — whoever holds it can mint an end-user session for any owner
   (server S7). The client fails with that explanation rather than an
   uninterpretable 401.

## C5 / C6 — not built

- **C5 (A2A as producer)** waits on server S8: sending an A2A message should
  enqueue a turn for the recipient agent. The client side is a one-line producer
  call once the server accepts it; building it now means writing against an
  undeployed contract.
- **C6 (observability)** waits on read APIs for `turns.cost_usd` /
  `usage_stages` and queue depth per owner. The data exists per turn on the
  server; nothing exposes it to a client yet.

## Open questions from the TODO, answered here

1. **Can a task be both scheduled and served?** Not from this client: one field,
   one path, and a refusal rather than a fallback. If the product wants both, it
   needs a rule about which trigger wins *before* the UI can represent it.
2. **Where does `hybrid_cloud_mode` fit?** It reads as `residency=cloud` +
   `requires=['browser_local']`, and the placement fields can already express
   exactly that. The collapse is deliberately deferred to the per-task flip so
   there is a consumer to verify it against.
3. **What does the customer see when no pod satisfies `requires[]`?** Still
   silence, and still wrong. The pieces to fix it are now here — the editor
   knows what a skill requires and the pod form knows what each pod advertises,
   so the client can warn at edit time. It needs the server's queue-depth view
   (C6) to warn at *runtime*, which is the case that actually hurts.
