# Shared Skill / Multi-Task Plan

**Goal:** multiple tasks — across multiple agents, and across multiple host
machines under one user account — reference a **single** skill instead of
per-agent copies. Tasks carry all per-run variable data; the skill is the
immutable, shareable definition. This is a prerequisite for the skill-store
business model.

**Decision (confirmed 2026-08-23): shared skills support CONCURRENT runs
across agents from day one.** No per-skill run lock. All Phase-1 work must be
correct under true parallel `astream` invocations of one compiled graph.

_Status: Phase 1 IMPLEMENTED 2026-08-23 (see per-phase notes below).
Design review completed 2026-08-23 (runner.py / executor.py / ec_skill.py /
build_node.py / hooks / bundles)._

---

## Background: what the review found

### Already per-task (no work needed)

- **LangGraph state is per-run.** Each `ManagedTask` gets its own
  `thread_id` (uuid, cached in `task.metadata["config"]`,
  `agent/ec_tasks/executor.py:203`). `messages`, `history` (LLM conversation
  memory via `add_to_history`), `prompt_refs`, `attributes`, `tool_result`
  all live in per-invocation state seeded from `task.metadata["state"]`.
  A compiled LangGraph is a stateless runnable; concurrent invocations with
  distinct thread_ids are supported by design.
- **Prompt variables are state-driven.** Template text is fixed at build
  time from the skill JSON; every `{{var}}` resolves per invocation through
  `resolve_prompt_variables` (`prompt_variable_providers.py`): `prompt_refs`
  → upstream `tool_result` → prompt/skill declarations → builtins.
  `prep_skills_run` deep-merges `task.metadata["state"]` into the baseline,
  so a task can already carry its own variables.
- **LLM pre/post hooks are shared-safe.** Dispatch tables key by
  `"public:<skill>:<node>"` (the right scope for a shared skill); the
  `agent` argument resolves at runtime from `state["messages"][0]`
  (`build_node.py:3776`), and all effects go into per-run state. No module
  mutable state in `llm_hooks.py`.
- **Execution is serialized per task** (one execution future per task);
  different tasks run concurrently on the shared thread pool.
- **Browser sessions default to chat-id scope keys** — per-chat isolation
  even when cache dicts are shared per skill object.

### Blockers / hazards

| # | Item | Location | Why it blocks |
|---|------|----------|---------------|
| B1 | Executor cleanup clears the **entire** shared `InMemorySaver` after every run | `executor.py:122` `_clear_skill_module_caches` | Task A completing wipes task B's checkpoints on the same skill → breaks B's parked `pend_event` auto-resume and mid-run `get_state` |
| B2 | Browser identity frozen at build time (`node_profile`, `user_data_dir`, CDP port, headless) | `build_node.py:10136`+ closure captures | Two agents sharing one skill share one browser profile/fingerprint — wrong for multi-shop; this is the real reason copy-per-agent exists |
| B3 | `_last_known_agent_id_by_node` keyed by **node name only** | `build_node.py:9455` | Two agents on one skill (same node names): A's cached agent_id back-fills into B's run when B's state momentarily loses `agent_id` → misdispatch. (Latent even with unrenamed copies.) |
| B4 | Task-state merge only happens for `message` triggers | `runner.py` `_execute_skill` (`initial_current_state` guard) | Schedule/auto-triggered tasks never receive task-carried variables |
| B5 | No host affinity: every host starts worker loops for **all** synced tasks | `ec_agent.py:425` `EC_Agent.start()` | Same account on two hosts → schedule tasks double-fire. Independent of skill sharing, but must be fixed for the multi-host shop pattern |
| B6 | Pinned browser scope key `node:<node_name>` collides across agents | `browser_node/build_helpers.py:391` | Two agents on a pin-to-node skill fight over one cached session |
| B7 | `bp_manager` (dev breakpoints) is one per skill object | `build_agent_skills.py:1247` | A breakpoint set while debugging pauses every task using the skill. Accepted for now (dev-mode only) |
| B8 | Live-chat site bundles assume ONE site session per process | `feige_chat/typing_lock.py` (process-wide holder), runner bridge (last-write-wins), WS lane, `_dispatch_inflight` (customer-key only) | Only bites for N same-site *browser sessions* in one process. Orthogonal to skill sharing — copies collide identically. Deferred (Phase 5); supported pattern is one process per shop |

Notes on B8 / multi-shop topologies (reviewed 2026-08-23):
- **Multiple shops in tabs of one browser: not possible** — tabs share the
  profile cookie jar; the second shop login evicts the first. CDP browser
  contexts / separate profiles give isolated cookie jars but land exactly on
  the same Phase-5 session-scoping work, plus platform account-association
  risk-control concerns (shared fingerprint/IP).
- **Multiple hosts, one account: the supported pattern.** Process isolation
  makes every B8 singleton correct again. Multi-device login is not blocked
  by auth; `machine_id` (`agent/a2a/discovery/machine_id.py`), the WAN agent
  directory host tags, and the `DBAgentVehicle` model already exist — only
  the startup affinity filter (B5) is missing.

---

## Phase list

### Phase 1 — Concurrent shared-skill execution safety (core) ✅ 2026-08-23

1. ✅ **Per-thread checkpoint cleanup (B1).** `_clear_skill_module_caches`
   now deletes only the finishing task's `thread_id`
   (`checkpointer.delete_thread(...)`, with a manual storage/writes/blobs
   pop fallback for older langgraph). Interrupted-task skip retained.
   No lock added: `delete_thread` snapshots key lists before deleting, so
   concurrent deletes of *different* threads are GIL-safe (verified against
   langgraph-checkpoint 2.1.2 source).
2. ✅ **Re-keyed the mt068 agent-id recovery cache (B3).** Now keyed by
   `(node_name, task scope)` where scope = state.attributes
   thread_id/run_id/task_id/chat_id (first non-empty). Degraded states that
   also lost the scope fall back to the bare node ONLY while a single
   agent_id has ever been recorded for it (exact old behaviour in the
   single-agent world); with 2+ known agents recovery declines with a
   warning instead of guessing. Helpers: `_agent_recovery_scope`,
   `_record_or_recover_agent_id` (`build_node.py`); cache capped in
   `_cleanup_build_node_caches`.
3. ✅ **Shared-object mutation audit.** Grep audit found no per-run
   mutation of shared `EC_Skill` attributes in
   runner.py / executor.py / prep_skills_run.py / agent_converter.py
   (skill-editor recompiles via `set_work_flow` are edit actions, not
   runs). `bp_manager` sharing (B7) documented as accepted — dev-mode only.
4. ✅ **Concurrency regression tests** —
   `tests/unit/test_shared_skill_phase1.py` (10 tests):
   per-thread delete spares siblings; interrupted task keeps its own
   thread; sibling parked on interrupt survives a completion; no-thread_id
   cleanup touches nothing; mt068 record/recover per scope, no
   cross-contamination, single-agent degraded recovery preserved,
   multi-agent degraded recovery declines; parallel invokes of ONE
   compiled graph + ONE InMemorySaver with distinct thread_ids have
   independent results and per-thread deletes.

### Phase 1.5 — Host/vehicle affinity filter (B5) ✅ 2026-08-23

Implemented in `agent/ec_agents/vehicle_affinity.py`, gated at the top of
`EC_Agent.start()` (`agent/ec_agent.py`) — the single choke point every
launch path goes through, so gui/ needed no changes.

1. ✅ **Local vehicle registration.** `register_local_vehicle(mainwin)`
   upserts a `DBAgentVehicle` row with id = the persistent discovery
   `machine_id` (imported from `agent.a2a.discovery.machine_id` submodule —
   the package `__init__` needs zeroconf, the submodule doesn't), hostname +
   platform as metadata, status online. Idempotent per process; runs lazily
   on the first agent start. `EcDBManager` gained a `vehicle_service`.
2. ✅ **Startup filter.** `agent_launch_allowed(agent)`: empty `vehicle_id`
   → start everywhere (back-compat, INFO log — softened from the planned
   WARNING to avoid per-agent startup noise for single-host users);
   matching id → start; mismatch → skip with INFO log. Every failure path
   fails OPEN (unresolvable machine_id, gate exception) — affinity can
   never brick startup. Kill switch: `ECAN_DISABLE_VEHICLE_AFFINITY=1`.
   Cloud workers (no mainwin) resolve to fail-open automatically.
3. ✅ (CLI) / ⏳ (GUI) **Assignment surface.** `ecan agents update
   --vehicle <id>|this|none` (`this` resolves the local machine_id via the
   MainGUI-compatible per-user data-home derivation; CN WeChat logins may
   derive a different path in CLI — use the explicit id from
   `ecan vehicles list` there). gui_v2 assignment UI deferred to a
   follow-up (host tag display already exists).
4. ✅ **Tests.** `tests/unit/test_vehicle_affinity.py` (13 tests): gate
   allow/skip/fail-open/kill-switch, `vehicle` attr fallback, machine-id
   persistence across cache resets, vehicle-row upsert (new/existing/
   idempotent/missing-service). The two-host schedule scenario is covered
   at the gate level: a mismatched agent's `start()` returns before any
   task worker loop is submitted.

Known cosmetic gap: MainGUI's `_sync_agent_db_status_active` still marks a
skipped agent 'active' in the DB after `start()` returns early — harmless
(the assigned host sets the same status) but worth cleaning when gui_v2
takes over launch status display.

### Phase 2 — First-class per-task variables (skill-store enabler) ✅ 2026-08-23

1. ✅ **`task.metadata["task_vars"]` contract.**
   `apply_task_vars(task, state)` (`agent/ec_skills/prep_skills_run.py`)
   seeds the task's variables into `state["prompt_refs"]` (first stop of
   the resolution cascade) plus a diagnostic copy at
   `state["attributes"]["task_vars"]`. Called from `_execute_skill`
   (`runner.py`) right after state prep, for EVERY trigger type — fixes B4
   without widening the message-only full-state merge that chat tasks rely
   on for conversation continuity. Never raises; no-op without vars.
2. ✅ **Persistence + load paths.** Values live in the DB task's
   `settings`/metadata JSON under `task_vars`. Load paths covered:
   `create_agent_tasks._convert_db_agent_task_to_object` already passes DB
   settings into runtime metadata (free); `agent_converter.
   _convert_dict_to_task` now copies the `task_vars` key (only that key —
   runtime metadata also holds executor-owned `state`/`config`).
3. ✅ (CLI) / ⏳ (GUI) **Creation surface.**
   `ecan tasks add --skill <id|name> --var k=v` (repeatable; `--skill`
   binds via the task-skill relationship; skill resolution added to
   `cli/base/resolve.py`) and `ecan tasks update --var k=v` (merges into
   existing vars, preserving unrelated settings keys). gui_v2 task-create
   form rendering the skill's `need_inputs` is deferred to a frontend
   follow-up.
4. ✅ **Resolution precedence (documented).** At run start, `task_vars`
   overwrite same-named `prompt_refs` carried from a previous run (task
   intent wins); during the run, upstream node writes may overwrite (their
   output is more current). Full cascade per
   `resolve_prompt_variables`: `prompt_refs` (seeded from task_vars) →
   implicit upstream `tool_result` → prompt declarations → skill mapping →
   builtins → "".
5. ✅ **Tests.** `tests/unit/test_task_vars_phase2.py` (12): seeding /
   overwrite / preserve semantics, tolerance of bad inputs, resolution-
   cascade pickup, `_convert_dict_to_task` propagation, CLI add/update
   var handling incl. merge semantics and skill binding.

Note: the hybrid-cloud execution path (`_execute_hybrid_cloud_task`) does
not yet apply task_vars — revisit when cloud workers adopt shared skills.

### Phase 3 — Per-task browser identity (B2, B6) ✅ 2026-08-23

1. ✅ **Per-task browser identity (B2).** Discovery: a state-override
   channel already existed for `cdp_port`/`browser_profile`/
   `browser_slot_id` in `get_or_create_browser_session` (state root →
   attributes → params, "state wins over config"). Built on it instead of
   inventing a parallel mechanism:
   - `build_helpers.resolve_state_browser_identity(state)` — one resolver
     for `browser_profile`, `cdp_port`, `browser_slot_id`,
     `user_data_dir`, `headless` (bool-coerced), reading the same state
     locations.
   - Task-carried source: `task.metadata["browser_identity"]` (persisted
     in DB task settings; aliases `profile`/`slot` accepted) is seeded
     into state attributes at run start by `apply_task_vars` — so the
     pre-existing runtime channel now has a per-task feeder.
   - `_BrowserRunSession` profile prep (`browser_node/runner.py`) now
     resolves profile / user_data_dir / headless per run (state → node
     config); `get_or_create_browser_session` uses the effective profile
     for profile-settings lookup, and the `acquire_browser` profile
     precedence was fixed to state-first (`_state_browser_profile or
     ctx.node_profile` — the old config-first order contradicted the
     documented "state takes priority" intent of the slot mechanism).
   - CLI: `ecan tasks add/update --browser k=v` (repeatable; keys
     profile, cdp_port, user_data_dir, headless, slot; canonicalized at
     the CLI). `_convert_dict_to_task` carries `browser_identity`
     alongside `task_vars`.
2. ✅ **Agent-namespaced pinned scopes (B6).** All pin-to-node returns in
   `resolve_browser_scope_key` now emit `node:<node>:<agent_id>` via
   `_agent_pin_suffix` (agent from state attributes/messages[0], kept
   sticky on degraded re-entries by the mt068 recovery cache from Phase
   1). Falls back to the legacy bare scope when no agent is determinable.
   Chat-id scopes unchanged. Existing contract tests in
   `tests/test_front_desk_browser_scope.py` updated to the new pinned-key
   shape (+ per-test mt068 cache isolation).
3. ✅ **Tests.** `tests/unit/test_browser_identity_phase3.py` (16):
   resolver precedence/coercion, task-identity seeding end-to-end into
   the resolver, pinned-scope agent suffix incl. degraded-state
   stickiness and two-agent distinctness, chat-scope unchanged, CLI
   parse/canonicalize/merge, converter propagation.

Note: `tests/test_front_desk_hot_path_v2.py::test_pre_record_reply_
before_executor` fails pre-existing (whitespace-normalized ledger vs raw
assertion) — verified unrelated by stashing Phase 3 changes.

### Phase 4 — Retire copy-per-agent; skill-store readiness ✅ 2026-08-23

1. ✅ **Migration tooling.** `DBSkillService.find_duplicate_skills(owner)`
   (groups skills with identical `diagram` JSON — canonical-JSON compare;
   code skills and diagram-less skills excluded; earliest-created wins) and
   `merge_skill_references(dup_id, canonical_id)` (re-points
   `agent_skill_rels` + `agent_task_skill_rels`, deleting rows that would
   violate the unique constraints). CLI: `ecan skills dedupe` (dry-run
   report) / `--apply` (merge references) / `--apply --delete` (also delete
   duplicate rows, with cloud-sync of the deletion). Duplicate rows are
   never deleted implicitly.

   **Migration playbook** (per user):
   1. `ecan skills dedupe` — review the groups.
   2. `ecan skills dedupe --apply` — agents/tasks now reference one
      canonical skill each.
   3. Move per-copy differences onto the tasks:
      `ecan tasks update <task> --var shop_name=... --browser profile=...`.
   4. `ecan skills dedupe --apply --delete` (or `ecan skills remove <id>`)
      once satisfied.
2. ✅ **Author prompt resolution fixed + verified.** The wiring gap item 2
   anticipated was real: `_compile_skill_workflow_from_flow` passed the
   flow's local `owner` (re-stamped to the RUNNER on download) into the
   converter, so `build_llm_node → _resolve_prompt_templates(skill_owner=…)`
   resolved prompts under the buyer, not the author.
   `EC_Skill.skill_owner` (populated from skill JSON/extra_data, falls back
   to owner) is now injected as the flow owner at compile time — no-op for
   self-authored skills. Downstream was already correct:
   `_load_prompt_data` prefers `skill_owner` in cloud context and has a
   local-miss → cloud-fetch-under-author fallback (free-skill
   auto-download); flowgram v2 preserves top-level flow keys when
   delegating to v1.
3. ✅ **Tests.** `tests/unit/test_skill_dedupe_phase4.py` (9): duplicate
   grouping / canonical pick / exclusions / owner scoping; rel re-pointing
   incl. unique-constraint drops; author-owner compile injection (override,
   self-authored no-op, empty fallback).

Remaining for full store readiness (out of scope here): purchase/download
flow must persist the author into the local row's `skill_owner`
(skill_handler already round-trips the field), and a live two-account
end-to-end run of a purchased skill.

### Phase 5 — DEFERRED: same-process multi-session live-chat (B8)

Only needed if N same-site browser sessions must share one app process.
Until then the supported pattern is **one process (host) per shop**
(Phase 1.5 makes this operational).

- `typing_lock` → `{session_key: holder}` (its docstring already
  anticipates this migration).
- `_dispatch_inflight` and dispatch identity keys gain a shop/session
  component.
- Runner-bridge capabilities (direct-delivery worker, typing semaphores,
  dedicated CDP loop, WS reader) become per-session or pooled — this is
  performance-sensitive territory (see FEIGE_COLDSTART_POSTMORTEM,
  PLATFORM_FEIGE_DECOUPLING_2026_08); do not start casually.

---

## Log markers (what to grep when something breaks)

| Symptom | Grep in eCan.log | Emitted by |
|---|---|---|
| Parked task lost its resume / checkpoint gone | `Deleted checkpoints for thread_id` and `Skipping checkpoint delete` (INFO — shows which task deleted which thread, and skill name) | `executor._clear_skill_module_caches` |
| Agent didn't start on this host / started on wrong host | `[AGENT_START] Skipping` / `no vehicle affinity` / `[VehicleAffinity]` (INFO skips + registration; WARNING on every failure, all fail-open) | `ec_agent.start` + `vehicle_affinity.py` |
| Task vars didn't reach the prompt | `[apply_task_vars]` (INFO: task name + var NAMES seeded into prompt_refs; values withheld) | `prep_skills_run.apply_task_vars` |
| Wrong browser profile/port/headless used | `Per-run browser identity overrides` (INFO: state overrides vs node config), `Using profile: ... (from=state\|config)`, `Resolved cdp_port=... (from=state\|config)` | `browser_node/runner.py` prep + `get_or_create_browser_session` |
| Two agents fighting over one pinned browser | `Pinned scope ... legacy shared scope` (DEBUG: agent unresolvable → bare scope) + mt068 `declining ambiguous recovery` (WARNING) | `_agent_pin_suffix` + `_record_or_recover_agent_id` |
| PreDispatch misattributed to wrong agent | `mt068: agent_id empty ... recovered` / `declining ambiguous recovery` (WARNING, includes node + task scope) | `build_node._record_or_recover_agent_id` |
| Store skill answered with wrong prompts | `Compiling '<skill>' with author owner` (INFO: fires only when author ≠ local row owner) + `[prompts]` cloud-loading warnings | `_compile_skill_workflow_from_flow` + `_load_prompt_data` |
| Dedupe merged the wrong thing | `[SkillDedupe]` (INFO: every group found + every merge with per-table counts; ERROR on failed merge) — durable in the app log, not just CLI stdout | `DBSkillService.find_duplicate_skills` / `merge_skill_references` |

## Test matrix (added incrementally per phase)

| Scenario | Phase | Expectation |
|---|---|---|
| 2 agents × 1 skill, parallel runs | 1 | independent histories, both complete |
| A completes while B parked on interrupt | 1 | B's checkpoint survives, resume works |
| Same skill, different `task_vars` | 2 | different rendered prompts per task |
| Schedule task with vehicle affinity, 2-host DB | 1.5 | fires once, on the assigned host |
| Pin-to-node skill, 2 agents | 3 | two distinct browser sessions |
