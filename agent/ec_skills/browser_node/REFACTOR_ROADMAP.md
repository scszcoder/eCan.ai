# Browser Automation Node Refactor Roadmap

Status: **Phases 5b.4 + 6 (incl. 6.5 / 6.6 / 6.7) complete** (2026-04-24).

## Current state snapshot (post Phase 6.7)

- `build_node.py`: **8,353 lines** (–30% from 11,937 start-of-session)
- `build_browser_automation_node`: **1,124 lines** (–67% from 3,400 mid-session)
- `browser_node/runner.py`: hosts `BrowserRunSession` + `RunContext`
- `browser_node/contexts.py`: 4 hook-context dataclasses (Phase 6.5)
- `browser_node/build_helpers.py`: 9 lifted helpers + 4 state dicts (Phase 6.7)
- `_run_browser_use`: 13-line thin delegator in `build_node.py`
- `BrowserRunSession`: 18 phase methods, no closure refs
- `RunContext`: **31 fields** (–30% from 44 post-6.3, settings + hooks only)

## Phase 5b.4 — split `run()` into phase methods (complete)

`run()` body shrunk from 1,086 → 206 lines (–81%) by extracting 13 named
phase methods. See git log around 2026-04-24 for the commit-by-commit
breakdown.

| Phase method | Lines |
|---|---|
| `_build_hook_ctx` | 41 |
| `_inject_event_context` | 143 |
| `_invoke_early_hooks` | 28 |
| `_extract_assignment_and_scope` | 138 |
| `_resolve_run_mode` | 51 |
| `_run_passive_branch` | 108 |
| `_resolve_agent_class` | 56 |
| `_build_local_llm_and_kwargs` | 99 |
| `_build_browser_profile_and_callbacks` | 106 |
| `_apply_post_kwargs_extensions` | 48 |
| `_acquire_browser_and_agent` | 182 |
| `_finalize_agent_setup` | 108 |
| `_run_cloud_branch` | 32 |
| `_handle_pre_dispatch` | 88 |
| `_run_agent_dispatch` | 63 |
| `_finalize_result` | 83 |
| `_cleanup` | 25 |
| `run` (orchestrator) | 206 |

### Lessons learned during 5b.4

The dominant bug class was **run-local closure leakage**: names imported
or unpacked inside `run()` (`BUAgent`, `custom_controller`, `mainwin`,
`assignment_*`, `_asg_cfg`) are *not* visible to sibling phase methods
of the same class — Python's closure rules give methods access to
*enclosing-function* locals, not to *another method's* locals. Four
production NameError regressions before the pattern was understood.
Fixes: lazy-import inside each method that needs them; route per-call
state through `self.*`; pass typed contexts (`asg_ctx`) explicitly
rather than relying on unpacked locals.

## Phase 6 — lift `BrowserRunSession` to `runner.py` (complete)

Sub-steps, each committed separately:

- **6.1** — Audit closure refs (64 names → 16 module-level / 44 build-scope)
  + define `RunContext` dataclass in `runner.py`
- **6.2** — AST-based mass-rewrite: 143 bare closure refs in the class
  body converted to `self.ctx.<name>`. Field naming preserves underscores
  to make the rewrite a pure symbol substitution.
- **6.3** — Lift the (now portable) class verbatim from `build_node.py`
  to `runner.py`. Bug fixed: `nonlocal _last_known_focus_target_ids` was
  invalid at module scope — replaced with comment (the dict lives on
  `self.ctx._last_known_focus_target_ids`, shared by reference).
- **6.4** — Cleanup: docstring updates, this roadmap.

`build_node.py` keeps a six-line import alias so historical references
to `_BrowserRunSession` continue to resolve:

```python
from agent.ec_skills.browser_node.runner import BrowserRunSession as _BrowserRunSession
```

## Phase 6.5 — context dataclasses to `contexts.py` (complete)

Moved `BrowserUseHookContext`, `PromptBuildContext`, `PromptBuildResult`,
`_AssignmentContext` from `build_node.py` to
`browser_node/contexts.py` to break the runner→build_node cycle.
`build_node.py` re-exports for back-compat so external hook bundles
(e.g. `feige_chat`) continue to work without changes.

## Phase 6.6 — strip underscores from `RunContext` (complete)

19 fields had leading underscores (preserved during 6.2 to make the
mass-rewrite a pure symbol substitution). Renamed via AST-aware
script: 47 call-site replacements + 19 field-def renames in
`runner.py`, 19 kwarg renames in `build_node.py`'s `_run_ctx`
construction.

## Phase 6.7 — lift helpers + state to `build_helpers.py` (complete)

Created `browser_node/build_helpers.py` with **9 lifted helpers** + **4
state dicts** previously closures of `build_browser_automation_node`:

| Helper | Lines | Closure refs (before lift) |
|---|---|---|
| `extract_runtime_invocation_input` | 58 | 0 |
| `get_browser_profile_settings` | 17 | 0 |
| `is_session_started` | 22 | 0 |
| `is_session_alive` | 43 | 1 |
| `extract_assignment_scope` | 11 | 0 |
| `resolve_browser_scope_key` | 30 | 1 (`node_name`) |
| `cleanup_stale_browser_sessions` | 23 | 1 (state dict) |
| `patch_browser_session_lifecycle_debug` | 73 | 1 (state dict) |
| `get_or_create_browser_session` | 316 | 13 (settings + helpers + state) |

The big function (`get_or_create_browser_session`) takes `ctx:
RunContext` — call sites use `_bh.get_or_create_browser_session(...,
ctx=self.ctx)`. Two pass-as-callable sites (hook context, passive
step) wrap with a lambda binding `ctx`.

State dicts moved to module-level singletons: `cached_browser_sessions`,
`cached_bu_agents`, `last_known_focus_target_ids`, `browser_start_locks`.
Behavior change: previously per-build-call (one dict per
`build_browser_automation_node` invocation), now shared across all
compiled nodes. Safe because every key includes node identity
(`node:<name>` or `chat:<id>`) so collisions are structurally impossible.

Latent bug found in `_clear_module_caches` — but it turned out to be
*load-bearing dead code*. The original function at L390 referenced
`_cached_browser_sessions` (a build-scope local) which raised
`NameError` on every call, silently swallowed by `executor.py`'s
`except Exception as e: logger.debug(...)`. The `NameError`
short-circuited the function so the worker-stop block at L402-416
**never ran in production** despite shipping for months.

The 6.7 lift fixed the `NameError` (rewiring to the new module-level
dicts), which inadvertently *activated* the worker-stop loop. Every
task completion then called `_PersistentAsyncWorkerThread.stop()` on
**all** running workers — including ones executing concurrent browser-
automation work — causing `CancelledError` mid-await. **Hotfix
2026-04-24**: deleted the entire dead-code block. Browser-session
caches and persistent workers are intentionally long-lived; neither
should be torn down per-task. The first-customer-message-after-task-
completion failure (`23:08:24` log) confirmed the issue.

`RunContext` shrank from **44 → 31 fields**:
- Dropped 9 helpers (now in `build_helpers.py`)
- Dropped 5 state dicts (3 to `build_helpers`, 2 already module-level
  in `build_node.py`: `_cached_passive_agents`, `_dispatch_state_by_agent`)
- Dropped 4 module-level redirects (`normalize_dispatch_identity_key`,
  `resolve_template`, `cached_passive_agents`, `dispatch_state_by_agent`)
- Dropped `max_browser_cache_size` (now `MAX_BROWSER_CACHE_SIZE` in
  `build_helpers`)
- Added 2 fields used by lifted `get_or_create_browser_session`:
  `cdp_port_setting`, `downloads_path`

`build_browser_automation_node` shrank from **1,735 → 1,124 lines** (–35%).

## Hotfix #2 — `mainwin` recovery on auto-resume (2026-04-24 23:35)

After fixing the persistent-worker `CancelledError` (hotfix #1), a
**second** failure surfaced: customer messages still went unanswered
because the auto-resumed `browser_automation` re-entry aborted with

```
[build_browser_automation_node] Cannot create browser_use LLM:
mainwin not available. Please ensure agent is properly initialized.
```

### Root cause

On `pend_event` auto-resume after a chat_message arrives, the LangGraph
loop scaffolding (`update_loop_*_condition` → `check_loop_*_condition`
→ `browser_automation_*`) re-enters the node with a stripped-down
state — observed `state.keys() == ['attributes', 'result', 'tool_result']`
where the first run had 27 keys. Critically, `state['attributes']`
no longer carries `agent_id`, so the standard `agent_id → get_agent_by_id
→ agent.mainwin` resolution chain returns `None`. The node aborts before
reaching the LLM/PreDispatch logic.

This is a **pre-existing latent bug** that only surfaced after hotfix
#1 fixed the persistent-worker cancellation; previously the cancel
killed the second iteration before mainwin resolution mattered.

### Fix

Added a defensive fallback at `@/Users/songc/PycharmProjects/eCan.ai/agent/ec_skills/build_node.py:7944-7970`:

```python
# Fallback: AppContext singleton (2026-04-24 hotfix)
if not mainwin and not is_cloud_mode:
    from app_context import AppContext
    _ctx_mw = AppContext.get_main_window()
    if _ctx_mw is not None:
        mainwin = _ctx_mw
        logger.warning("Recovered mainwin from AppContext singleton ...")
```

`AppContext.get_main_window()` is the process-wide singleton populated
at startup; it's already used by ~30 call sites elsewhere in the
codebase. Using it as a last-resort fallback restores execution
without altering the primary lookup path.

The recovery log is at `WARNING` level so persistent reliance on the
fallback is visible. Long-term, the state-stripping in the auto-resume
path should be investigated (separate from this refactor).

## Hotfix #3 — InMemorySaver wiped between interrupt and auto-resume (2026-04-25 00:10)

After hotfix #2, the front-desk dispatch worked (customer message reached
the Q&A worker via `send_chat`), but the customer still saw no reply.
Investigation showed the Q&A worker received the message and entered its
graph, but **never ran its LLM body** — the workflow ping-ponged between
`update_loop_KcQ3-_condition → check_loop_KcQ3-_condition →
pend_event_sVz3K (interrupt)` repeatedly without ever advancing along the
designed inner edge `pend_event_sVz3K → llm_7xz6k → mcp_PN5P3`.

### Root cause

`@/Users/songc/PycharmProjects/eCan.ai/agent/ec_tasks/executor.py:69-100`
defines `TaskExecutor._clear_skill_module_caches`, which is called from
the `finally` block of every `stream_run`/`astream_run`. It clears the
skill's `InMemorySaver.{storage, writes, blobs}` to prevent memory growth.

Problem: it ran **after every run, including interrupted ones**. The
auto-resume path in
`@/Users/songc/PycharmProjects/eCan.ai/agent/ec_tasks/runner.py:3914-3935`
calls `execute_task_hybrid(task, Command(resume=resume_payload), ...)`
expecting LangGraph to look up the saved checkpoint by `thread_id` and
feed `resume_payload` as the return value of the original `interrupt(...)`
call.

But the `finally` from the initial run had already wiped that checkpoint,
so LangGraph treated `Command(resume=...)` as a fresh invocation, ran the
graph from `START` again, hit `pend_event` again, and interrupted —
silently swallowing the resume payload. The chat message never reached
the LLM node.

Symptom in logs (Q&A worker `feige_chat_1`):

```
23:40:23,229  pend_event_sVz3K  ENTER  (1st time, interrupts)
23:40:23,553  EXECUTOR Initial run interrupted at pend_event - auto-resuming
23:40:23,568  update_loop_KcQ3-_condition  ENTER  (graph restarted!)
23:40:23,621  check_loop_KcQ3-_condition   ENTER
23:40:23,681  pend_event_sVz3K  ENTER  (2nd time, interrupts AGAIN)
23:40:24,006  Auto-resume completed: success=False
```

`[pend_event_node] RESUMED:` (logged immediately after `interrupt(info)`
returns) **never appears** because `interrupt()` never returned — the
graph started fresh.

This was introduced by commit `c0f3a485a` ("fix: fix run listing bug and
optimize thread manager"). The intent (preventing unbounded checkpoint
growth) was correct but the implementation was too aggressive — it cleared
mid-execution between an interrupt and its resume.

### Fix

Gate the `InMemorySaver` clearing on the task **not** being parked on an
interrupt (`TaskState.input_required`):

```python
if _is_interrupted:
    logger.debug("Skipping InMemorySaver clear: task parked on interrupt; "
                 "checkpoints are required for auto-resume")
elif self.task and ...:
    # original clear logic
```

Module-level cache clearing (LLM cache, etc.) still runs in all cases —
only the InMemorySaver clear is gated.

### Impact

This single fix should restore end-to-end Q&A: customer → front desk
PreDispatch → `send_chat` → Q&A worker `pend_event` interrupt → auto-resume
with chat payload → LLM responds → MCP delivers reply → customer sees it.

The phantom front-desk loop iterations observed earlier likely have the
same root cause (loop body never advanced past `pend_event`, kept getting
re-entered as fresh runs), so this fix should resolve them too.

## Future work

- Test `_clear_module_caches` properly — was latently broken before 6.7
  (NameError on every call), now silently swallowed by `except
  Exception`. Should add coverage that the dicts actually get cleared.
- Lift `_run_browser_use` thin delegator (13 lines) and the remaining
  cleanup helpers (`_is_matching_control_url`, `_reset_bu_agent_for_next_round`,
  `_clear_module_caches`, `_clear_module_caches`, etc.) — would shrink
  `build_browser_automation_node` further toward a true thin builder.
- Move `RunContext` to its own module (currently in `runner.py`) once
  it's fully decoupled.

---

## Historical (Phase 5b.3 and earlier)

## Audit: `BrowserUseRunner` class (runner.py:86–900)

**Finding: `BrowserUseRunner` is internally referenced and CANNOT be
deleted as a unit.**  My initial audit (which claimed it was dead code)
was wrong — corrected here after a deletion attempt was reverted.

### Usage audit
- **External**: zero references outside `runner.py` itself.  No import
  from `build_node.py`, no test invocations.
- **Internal**: 4 references inside `runner.py` from module-level
  functions:
  - `run_skill_passive_step` (L163) calls `BrowserUseRunner._publish_passive_result`
  - `run_browser_passive_step` (L314) calls `BrowserUseRunner._publish_passive_result`
  - `build_local_llm` (L2477) instantiates `BrowserUseRunner(cfg, shim)`
    to call `._build_local_llm`
  - `run_cloud_agent` (L2743) instantiates `BrowserUseRunner(cfg, shim)`
    to call `._run_cloud_agent`

The pattern is "module-level wrapper delegates to class method".
Deleting the class breaks all four.

### Correct cleanup path (Phase 6 prerequisite)

To remove `BrowserUseRunner`, three sub-steps are needed in order:

1. **Inline `_publish_passive_result`** — make it a free function in
   `runner.py`.  Two call sites already exist; the body is ~33 lines.
2. **Inline `_build_local_llm` and `_build_local_llm_from_node_config`** —
   the `build_local_llm` module function already wraps these via the
   `_NoSessionsShim` instantiation hack.  Refactor to remove the shim:
   the body becomes a free function taking the same args.
3. **Inline `_run_cloud_agent` and its 4 cloud helpers** (`_build_cloud_llm`,
   `_build_cloud_transport`, `_resolve_cloud_run_id`, `_resolve_acct_site_id`).
   The `run_cloud_agent` module function already wraps via the shim
   pattern.  Same refactor: remove shim, inline body.

After all three, `BrowserUseRunner` will have no remaining method bodies
referenced and can be deleted.  Estimated effort: ~1 hour, low risk.

### Duplication within `runner.py`
Every method on `BrowserUseRunner` has a counterpart as a module-level
function in the same file:

| Class method | Module function | Observation |
|---|---|---|
| `_run_skill_passive_step` | `run_skill_passive_step` (L927) | Identical — the method just delegates |
| `_run_browser_passive_step` | `run_browser_passive_step` (L1030) | Near-identical; function version is more complete |
| `_run_cloud_agent` | `run_cloud_agent` (L3515) | Same logic, different surface |
| `_build_local_llm` | `build_local_llm` (L3262) | Same |
| `_log_step_budget` | `log_step_budget` (L1308) | Same |
| `_extract_actions_from_state` | `_extract_passive_actions` (L982) | Same |
| `_build_cloud_llm` | (inline in `run_cloud_agent`) | Only in class |
| `_build_cloud_transport` | (inline in `run_cloud_agent`) | Only in class |
| `_resolve_cloud_run_id` | (inline in `run_cloud_agent`) | Only in class |
| `_resolve_acct_site_id` | (inline in `run_cloud_agent`) | Only in class |
| `extract_runtime_invocation_input` | `_extract_runtime_invocation_input` in build_node.py | Nearly identical |

**Recommendation: delete `BrowserUseRunner` entirely.**  The module-level
functions are the canonical implementations.  Before deletion, verify
each class-only method (`_build_cloud_llm`, `_build_cloud_transport`,
`_resolve_cloud_run_id`, `_resolve_acct_site_id`) is either equivalent
to its inline counterpart in `run_cloud_agent` or no longer needed.

## Phase 5b.4: split `_BrowserRunSession.run()` into phase methods

### Variable analysis
Running `runlogs/_phase_var_audit.py` identifies **30 cross-phase local
variables** (span > 100 lines), the largest being:

| Variable | Span | First L | Last L |
|---|---|---|---|
| `state` | 1044 | 8030 | 9074 |
| `_runtime_had_response_text` | 979 | 8096 | 9075 |
| `calling_agent_id` | 898 | 8031 | 8929 |
| `task` | 835 | 8028 | 8863 |
| `_evt_type` | 822 | 8120 | 8942 |
| `_browser_scope_key` | 780 | 8326 | 9106 |

### Phase boundaries (from source markers)

| Phase | Starts at | Scope |
|---|---|---|
| 1. Setup | L8025 | Entry log, `_build_hook_ctx` factory |
| 2. Inject event context | L8111 | Triggering event hints, override block |
| 3. Invoke early hooks | L8232 | `before_browser_session_setup_hooks` |
| 4. Assignment scope + gate | L8250 | `_extract_assignment_scope`, gate check |
| 5. Agent construction | L8653 | kwargs assembly, `_acquire_agent` |
| 6. First-invocation check | L8934 | Short-circuit for first-invocation skip |
| 7. Before-run hooks | L8952 | `before_browser_use_run_hooks` |
| 8. Run agent | L8990 | `run_agent_with_dispatch` |
| 9. Finally cleanup | L9093 | `_stop_non_cached` |

### Approach

Two options considered:

**Option A: `self.x` rewrite** — convert all 30 cross-phase vars to
`self.x`.  Each var has 5–30 references; ~300 mechanical edits total.
High risk of typos/missed references.

**Option B: explicit pass-through** — phases are methods that take
their inputs as parameters and return their outputs.  Requires
introducing small dataclasses (`_PrepResult`, `_AcquireResult`, etc.)
to group related return values.  Body of each phase stays verbatim.
Lower risk, more scaffolding.

**Recommendation: Option B for first pass**, focusing on the two
lowest-risk extractions:

1. **`_cleanup` method** — finally block (L9093–L9109, 17 lines) —
   takes `agent` and `browser_scope_key` as params.  Trivial.
2. **`_finalize_result` method** — post-run extraction (~30 lines) —
   takes `agent`, `history`, `state` params, returns dict.

Leave phases 1–7 as a single inline block until Phase 6 is scoped.

### Latent bug noted

`_BrowserRunSession.run()` has no `agent = None` init before `try:`.
If an exception occurs between try-entry (~L8040) and the first
`agent = ...` assignment at L8732, the finally block at L9104
would `UnboundLocalError` on `agent`.  Has not been observed in
practice (exceptions in that range are rare), but is a latent
correctness bug.  Fix is a one-line init: `agent = None` before the
try.  **Out of scope for Phase 5b.4** — track separately.

## Phase 6: body lift to `browser_node/runner.py`

### Prerequisites (do these first, in separate commits)

1. Delete `BrowserUseRunner` class.  Verify no regressions by pyflakes
   + import + live smoke.
2. Complete Phase 5b.4 extractions (at minimum `_cleanup`, `_finalize_result`).
3. Add a CI smoke test for the `customer_front_desk` skill live flow.
   **Without this, every Phase 6 move is a roll of the dice** — this
   session's two NameError regressions were caught only by the user's
   manual live run.

### Proposed API

```python
# browser_node/runner.py (new)
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

@dataclass
class RunContext:
    """All build-scope state a single run needs.

    Populated once per node build (by `build_browser_automation_node`)
    and reused across pend_event-loop iterations.
    """
    # Identifiers
    node_name: str
    skill_name: str
    owner: str

    # Config (from inputs)
    inputs: dict
    task_text: str
    actionable_field: str
    system_prompt_id: str
    user_prompt_id: str
    # ... ~20 more fields from NodeConfig ...

    # Mutable shared state (passed by ref)
    cached_browser_sessions: dict
    cached_bu_agents: dict
    last_known_focus_target_ids: dict
    event_monitor_configs: list

    # Closure callables still captured in build_node scope
    resolve_browser_scope_key: Callable[[dict | None], str]
    extract_runtime_invocation_input: Callable[[dict | None], str]
    extract_assignment_scope: Callable[[str], dict]
    get_or_create_browser_session: Callable[..., Awaitable[Any]]


class BrowserRunSession:
    """Phase-6 runner: lifted from `_BrowserRunSession`."""

    def __init__(self, ctx: RunContext, *, task, mainwin, state, calling_agent_id):
        self.ctx = ctx
        self.task = task
        self.mainwin = mainwin
        self.state = state
        self.calling_agent_id = calling_agent_id

    async def run(self) -> dict:
        # Phase methods set self.x for cross-phase data.
        try:
            await self._prepare()
            if (early := await self._invoke_early_hooks()) is not None:
                return early
            if (gate := await self._extract_assignment_and_check_gate()) is not None:
                return gate
            await self._construct_agent()
            if (sc := self._check_first_invocation_short_circuit()) is not None:
                return sc
            if (hooked := await self._invoke_before_run_hooks()) is not None:
                return hooked
            await self._run_agent_body()
            return self._finalize_result()
        finally:
            await self._cleanup()
```

`build_browser_automation_node` in `build_node.py` becomes:

```python
def build_browser_automation_node(config_metadata, node_name, skill_name, owner, bp_manager):
    cfg = parse_node_config(config_metadata, node_name, skill_name, owner)
    # ... parse all inputs into ctx fields ...

    # Still need closure-captured helpers (they access build-scope state):
    def _resolve_browser_scope_key(state): ...
    def _get_or_create_browser_session(mainwin, state, calling_agent_id): ...
    # ... etc ...

    ctx = RunContext(
        node_name=node_name,
        skill_name=skill_name,
        # ... 30+ fields ...
        resolve_browser_scope_key=_resolve_browser_scope_key,
        get_or_create_browser_session=_get_or_create_browser_session,
    )

    async def _run_browser_use(task, mainwin, state=None, calling_agent_id=None):
        return await BrowserRunSession(
            ctx, task=task, mainwin=mainwin, state=state, calling_agent_id=calling_agent_id,
        ).run()
    ...
```

### Estimated effort

Phase 5b.4 (2 minimal extractions): ~30 min, low risk.
Phase 5b.4 (all 9 phases, `self.x` rewrite): ~3 hours, medium risk.
Phase 6 (with all prereqs done): ~4–6 hours, medium-high risk.

Total: **~1 focused day of work** once CI smoke tests exist.

## Why stop before doing the full lift in this session

1. Two NameError regressions already occurred this session in smaller
   extractions, caught only by the user's live runs.
2. The current state (Phase 5b.3 class wrapper) is a **clean, committed,
   validated architectural seam** — a natural pause point.
3. Phase 6 done without CI smoke tests materially increases regression
   risk.  One bad exception path missed = broken production flow.
4. Phase 6 done *with* smoke tests is a straightforward mechanical move.
