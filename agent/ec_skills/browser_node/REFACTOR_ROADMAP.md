# Browser Automation Node Refactor Roadmap

Status: **Phase 5b.3 complete** (2026-04-24). This document records the
audit findings needed to plan Phase 5b.4 and Phase 6.

## Current state snapshot

- `build_node.py`: 10,084 lines (–15.5% from 11,937 start-of-session)
- `browser_node/runner.py`: 3,558 lines, 44 module-level definitions
- `_run_browser_use`: 13-line thin delegator
- `_BrowserRunSession`: 1,106-line class nested inside
  `build_browser_automation_node`, body at lines 8025–9116 of
  `build_node.py`

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
