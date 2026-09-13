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

### The three blockers are cleared

All three were server-side and all three are gone (2026-09-12):

1. **Credential.** `turn_enqueue` now accepts a **user session** under the same
   action name, deriving `owner` from the verified identity and ignoring the
   body — so a desktop can only ever enqueue for itself. That is the right
   shape: a client should not have to know which credential the server wants.
   The desktop uses its ordinary session bearer (CloudBase access token, or the
   eCan session token for WeChat logins), the same selection as its payment and
   coupon calls. `ECAN_FLEET_INTERNAL_TOKEN` still wins where a trusted
   server-side caller sets it, and **a desktop build must never ship with it**:
   that token mints end-user sessions for *any* owner.
2. **`task_id` is a field on the turn**, resolved and stored at enqueue time
   (server S0). The smuggling inside the input JSON is gone; `input` is now just
   what the customer said. The worker's half of the same seam landed in
   `cloud-worker` — it prefers `turn.taskId` over `ECAN_TASK_ID` — so both ends
   meet.
3. **A turn may have no conversation** (server S2), which is what a scheduled
   task produces. `conversation_id` is nullable rather than synthetic — a fake
   conversation would have filled the end-user-facing `conversation_list` with
   rows no end user owns. A conversation-less turn must name a `task_id` or an
   `agent_id`, which this payload always does.

What remains before the flip is thrown is coordination, not code: a task must
move on both sides at once, which is what `server_flipped: true` forces the
operator to confirm.

## C6 — queue depth and live state, via `fleet_status` (partly done)

`fleet_status` (owner-authenticated) is the fleet's own view, and the pods panel
now reads it alongside the desired state it already had.

**It renders `live`, never `status`.** A pod that dies keeps `status='online'`
until the reaper notices — up to six minutes of showing a green pod that is gone
— so the server computes `live` from the heartbeat age and that is the only
thing the UI trusts. A pod the fleet has never seen reads "not registered"; when
`fleet_status` itself is unreachable the stored status is shown and explicitly
marked unconfirmed, because a pod list that cannot reach the control plane
should still show what was asked for.

The panel header also carries the queue: how many turns are waiting, how many
are running, and how old the oldest queued turn is — turning red past half the
server's own `maxQueuedSeconds`. If turns are backing up, the customer sees that
before they see slow replies.

Still missing for full C6: the **per-agent / per-conversation cost rollup**. The
data is there (`turns.cost_usd`, `usage_stages`, written per turn) but nothing
aggregates it for a client yet, and rolling it up here would mean pulling every
turn down to the desktop to add numbers.

## C5 — not built

Waits on server S8: sending an A2A message should enqueue a turn for the
recipient agent. The client side is a one-line producer call once the server
accepts it; building it now means writing against an undeployed contract. No pod
registry was built for addressing, as instructed — a registry used for *routing*
recreates the binding problem this design removed.

## Open questions from the TODO, answered here

1. **Can a task be both scheduled and served?** Not from this client: one field,
   one path, and a refusal rather than a fallback. If the product wants both, it
   needs a rule about which trigger wins *before* the UI can represent it.
2. **Where does `hybrid_cloud_mode` fit?** It reads as `residency=cloud` +
   `requires=['browser_local']`, and the placement fields can already express
   exactly that. The collapse is deliberately deferred to the per-task flip so
   there is a consumer to verify it against.
3. **What does the customer see when no pod satisfies `requires[]`?** Partly
   answered now: the pods panel shows queue depth and the oldest queued age from
   `fleet_status`, so a turn nothing can claim shows up as a queue that is not
   draining. Warning at *edit* time — "no pod advertises what this skill
   requires" — is the remaining piece, and both halves of the comparison are now
   in the client.
