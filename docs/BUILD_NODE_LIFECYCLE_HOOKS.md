# `build_node.py` Lifecycle Hooks

A lightweight, in-tree hook system that lets **site-specific business-case
patterns** (e.g. Feige's front-desk + Q&A-worker fan-out) extend the generic
`browser_automation` node at three well-defined points in its lifecycle —
**without editing `build_node.py`**.

> **Not to be confused with `HOOK_BUNDLES.md`**, which describes a separate,
> more elaborate system (`HookDispatcher`, `hook.yaml` manifests, signing,
> runtime lanes) that operates *inside* the browser-use agent loop.  The
> two systems are orthogonal; a single site bundle (e.g. `feige_chat`) can
> and does use both.  See [*Relationship to `HookDispatcher` bundles*](#relationship-to-hookdispatcher-bundles).

- [When to use this system](#when-to-use-this-system)
- [The three phases](#the-three-phases)
- [Context types](#context-types)
- [Registering a site bundle](#registering-a-site-bundle)
- [Reference: `feige_chat` bundle](#reference-feige_chat-bundle)
- [Design rationale](#design-rationale)
- [Relationship to `HookDispatcher` bundles](#relationship-to-hookdispatcher-bundles)

## When to use this system

Use a lifecycle hook when you need to:

- **Short-circuit the whole node** based on the incoming event (skip the LLM
  entirely — e.g. a pre-computed reply that just needs typing into the page).
- **Enrich the LLM's task prompt** with business-case rules, pre-resolved
  data, or protocol overrides before the agent is constructed.
- **Wrap the LLM run** with site-specific pre-flight (e.g. deterministic
  tab dispatch to a worker-agent pool that fires *before* the LLM reads the
  DOM).

If you only need to intercept tool calls, DOM events, or per-step page
state *during* the LLM run, use the `HookDispatcher` bundle system instead
(see [`HOOK_BUNDLES.md`](./HOOK_BUNDLES.md)).

## The three phases

```
                    ┌─ node entry
                    │
                    │  [DOM event normalisation, compact_items extraction]
                    │
   before_prompt_build ──── PromptBuildContext in, PromptBuildResult out
                    │  (may short-circuit the whole node)
                    │
                    │  [task prompt finalisation, override block glue-on]
                    │
 before_browser_session_setup ──── BrowserUseHookContext, agent=None
                    │  (may short-circuit; a live browser session is
                    │   acquirable via hook_ctx.get_or_create_browser_session)
                    │
                    │  [browser-use agent construction]
                    │
     before_browser_use_run ──── BrowserUseHookContext, agent is live
                    │  (may short-circuit; reads live DOM via agent.browser_session)
                    │
                    ▼  agent.run() ... node returns
```

### 1. `before_prompt_build` *(Phase 7)*

Runs **after** DOM event items have been extracted and compacted but
**before** the task prompt / override block are finalised and before the
browser-use agent is constructed.

```python
async def my_hook(
    state: dict,
    inputs: dict,
    hook_ctx: BrowserUseHookContext,
    prompt_ctx: PromptBuildContext,
) -> PromptBuildResult | None: ...
```

- Returning `None` is a no-op (pass-through).
- Returning a `PromptBuildResult` lets the hook request any of three effects:
  * `short_circuit_state: dict` — skip the LLM entirely, return this as the
    node's state.
  * `task_hint_append: str` — append to `_new_msg_hint` (task body).
  * `override_prepend: str` — prepend to the protocol override block (glued
    onto the front of the final task).
- If any hook appends non-empty text (or short-circuits), `build_node`
  skips its generic "compact_items snapshot" fallback injection.

Typical use: data-driven item filtering, protocol-override text injection,
pre-resolved agent list, deterministic auto-dispatch with LLM short-circuit.
Reference: `feige_chat.actionable_items.before_prompt_build_hook`.

### 2. `before_browser_session_setup` *(early phase)*

Runs **before** the (expensive) browser-use agent is constructed.  This is
a fast-path intercept point for patterns that can decide on the incoming
event alone.

```python
async def my_hook(
    agent: None,          # always None at this phase
    state: dict,
    inputs: dict,
    hook_ctx: BrowserUseHookContext,
) -> dict | None: ...
```

- Returning a non-None state dict short-circuits the node (caller returns
  that dict as the node's state).
- Returning `None` lets the next early-phase hook run, or lets the node
  proceed to construct the agent and invoke the late phase.
- Acquire a browser session via `hook_ctx.get_or_create_browser_session(
  mainwin, state=..., calling_agent_id=...)` if you need one before the
  agent is built.

Typical use: "HOT-PATH-B"-style fast-path — type a pre-computed reply into
the page directly without paying for agent setup.  Reference:
`feige_chat.front_desk.before_session_setup_hook`.

### 3. `before_browser_use_run` *(late phase)*

Runs **after** the browser-use agent is constructed and its browser
session is ready, **before** `agent.run()` is invoked.

```python
async def my_hook(
    agent: Agent,         # live browser-use Agent with .browser_session
    state: dict,
    inputs: dict,
    hook_ctx: BrowserUseHookContext,
) -> dict | None: ...
```

- Returning a non-None state dict short-circuits the LLM (caller returns
  that dict).
- Returning `None` lets the next late-phase hook run, or the LLM.
- Use this when you need to read live DOM via `agent.browser_session`
  before the LLM does.

Typical use: PreDispatch — scan the page, deterministically dispatch work
to a pool of worker agents, then skip the LLM.  Reference:
`feige_chat.front_desk.before_run_hook`.

## Context types

All three phases receive a `BrowserUseHookContext`; the prompt-build phase
additionally receives a `PromptBuildContext`.

### `BrowserUseHookContext`

Generic infrastructure handles the node needs.  No business-case state
lives here — site bundles own their own state in their own modules (see
`feige_chat/dispatch_state.py` for the reference pattern).  17 fields,
all business-case-neutral:

```python
@dataclass
class BrowserUseHookContext:
    # Identifiers
    node_name: str
    calling_agent_id: str
    mainwin: Any
    # Closure-scoped helpers (capture per-invocation locals)
    resolve_scope_key: Callable[[dict], str]
    extract_runtime_invocation_input: Callable[[dict | None], str]
    # Module-level helpers (safe to call anywhere)
    parse_json_input: Callable[[dict, str], Any]
    send_log: Callable[[str, str], None]
    normalize_dispatch_identity_key: Callable[[str], str]
    safe_format_dict: type
    # Generic shared state owned by build_node module scope
    cached_browser_sessions: dict
    dispatch_state_by_agent: dict
    # Inflight-lock trio (prevents double-dispatch of the same item across scopes)
    is_dispatch_inflight: Callable[[str], float]
    mark_dispatch_inflight: Callable[[str], None]
    clear_dispatch_inflight: Callable[[str], None]
    inflight_ttl_s: float
    # Template renderer for `{{field}}` / `{{a || b}}` substitution
    resolve_template: Callable[[str, dict], str]
    # Acquire a live browser session (for early-phase hooks)
    get_or_create_browser_session: Callable[..., Awaitable[Any]]
```

### `PromptBuildContext`

```python
@dataclass
class PromptBuildContext:
    compact_items: list       # DOM snapshot with heavy fields stripped
    actionable_raw: list      # items where `actionable_field` is non-empty
    actionable_field: str     # the node-config field name (may be "")
    event_type: str           # "browser_event", "chat_message", ...
    event_label: str          # event sub-type (may be "")
```

### `PromptBuildResult`

```python
@dataclass
class PromptBuildResult:
    short_circuit_state: dict | None = None
    task_hint_append: str = ""
    override_prepend: str = ""
```

When `short_circuit_state` is set, the text mutations are ignored.

## Registering a site bundle

A bundle is a Python package with an `__init__.py` that imports the
modules owning hooks and calls each module's `register()`.
`build_node.py` **auto-discovers** every bundle under any of three
search roots at process start via `_discover_external_hook_bundles()`
and imports it, which triggers registration.

### Search locations (in order)

| # | Root | Purpose | Loader |
|---|---|---|---|
| 1 | `agent/ec_skills/browser_use_extension/hooks/external/<name>/` | **In-tree** — ships with the app (e.g. `feige_chat`). | Regular `importlib.import_module` as a subpackage. |
| 2 | `<app_info.appdata_path>/hooks/external/<name>/` | **User data home** — field-deployed customers drop bundles here without touching the installed app.  On Windows: `%LOCALAPPDATA%\eCan\hooks\external\`; on macOS: `~/Library/Application Support/eCan/hooks/external/`; on Linux: `~/.local/share/eCan/hooks/external/`. | `importlib.util.spec_from_file_location` under synthesized top-level package name `ecan_user_hook__<name>` (relative imports inside the bundle still work). |
| 3 | Any path listed in `ECAN_EXTRA_HOOK_DIRS` env var | **Power-user / CI** — OS-path-sep separated (`;` on Windows, `:` elsewhere).  Each listed dir is treated like root (2): its subdirectories become bundles. | Same as (2). |

**First-wins on name collisions.**  A user-home or env-var bundle
cannot shadow an in-tree bundle of the same name — the shadowing copy
logs a warning and is skipped.

### Drop-in contract for third-party authors

- **No edits to `build_node.py` required.**  Create
  `<some_root>/hooks/external/<your_site>/__init__.py` that calls the
  `register_before_*_hook` APIs; it is picked up on next process start.
  Field-deployed users: use the OS-specific user data home path listed
  above.
- **Failure isolation.**  A bundle whose import raises is logged at
  `WARNING` level and skipped; other bundles still load.  Check
  `runlogs/eCan.log` for
  `[build_node] External hook bundle '<name>' (...) failed to load`.
- **Ordering.**  Within each root, discovery order is
  filesystem-dependent (pkgutil / `sorted(os.listdir)`).  Do not rely
  on inter-bundle ordering — write idempotent, commutative hooks.
- **Private / scaffold folders.**  Any bundle whose name starts with
  `_` or `.` is skipped, so you can stage work-in-progress bundles as
  `_my_new_site/` without them loading.
- **Disable discovery entirely.**  Set
  `ECAN_DISABLE_EXTERNAL_HOOK_DISCOVERY=1` in the environment (useful
  for isolated tests or locked-down deployments).  `build_node` then
  runs with an empty registry and all nodes take their generic fallback
  paths.

### Minimal skeleton

```
hooks/external/my_site/
    __init__.py              ← triggers registration on import
    hooks.py                 ← one or more hook functions + register()
```

```python
# hooks/external/my_site/__init__.py
_REGISTERED = globals().get("_REGISTERED", False)
if not _REGISTERED:
    from . import hooks as _hooks
    _hooks.register()
    _REGISTERED = True
```

```python
# hooks/external/my_site/hooks.py
from agent.ec_skills.build_node import (
    BrowserUseHookContext,
    PromptBuildContext,
    PromptBuildResult,
    register_before_prompt_build_hook,
    register_before_browser_session_setup_hook,
    register_before_browser_use_run_hook,
)

async def my_prompt_hook(state, inputs, hook_ctx, prompt_ctx):
    if not prompt_ctx.actionable_field:
        return None   # not our round
    # ... build override text or short-circuit state ...
    return PromptBuildResult(task_hint_append="...", override_prepend="...")

def register() -> None:
    register_before_prompt_build_hook(my_prompt_hook)
```

### Idempotent registration

All three `register_*_hook` functions are no-ops if the callable is
already registered.  This lets packages be re-imported under hot-reload
without duplicating hooks.

### Site state

Put per-bundle state (dicts, TTLs, caches) **in a sibling module**, not
in `BrowserUseHookContext`.  The `feige_chat` bundle demonstrates this
pattern:

```
feige_chat/
    dispatch_state.py        ← HOT-PATH-B dedup cache, last-reply-by-customer
    typing_lock.py           ← Feige active-session race guard
    actionable_items.py      ← RR index, affinity, cooldown, identity-key dedup
```

Hooks in `front_desk.py` and `actionable_items.py` import these as
siblings: `from . import dispatch_state as _ds`.

## Reference: `feige_chat` bundle

The in-tree reference bundle at
`agent/ec_skills/browser_use_extension/hooks/external/feige_chat/`
registers **three** lifecycle hooks (one per phase):

| Module | Phase | Hook function | Responsibility |
|---|---|---|---|
| `front_desk.py` | `before_browser_session_setup` | `before_session_setup_hook` | HOT-PATH-B: type a pre-computed reply into Feige directly, short-circuit the LLM |
| `actionable_items.py` | `before_prompt_build` | `before_prompt_build_hook` | Front-desk pattern: filter actionable items, inject protocol override + pre-resolved agent list, attempt deterministic auto-dispatch short-circuit |
| `front_desk.py` | `before_browser_use_run` | `before_run_hook` | PreDispatch: customer-message fan-out reading live sidebar DOM |

Plus three state/helper modules:

| Module | Contents |
|---|---|
| `dispatch_state.py` | HOT-PATH-B recent-send dedup cache; `last_agent_reply_by_customer`; `last_dispatched_msg_id_by_customer`; Feige-sidebar reply-text normaliser |
| `typing_lock.py` | Active-session race guard (held by HOT-PATH-B and the PreDispatch enrich plugin) |
| `actionable_items` (module-level state) | Round-robin index, affinity table, cooldown dict, identity-key dedup, auto-dispatch cooldown TTL |

And one DOM-scrape plugin:

| Module | Used by |
|---|---|
| `pre_dispatch_enrich.py` | PreDispatch's customer-enrich stage |
| `dom_assets.py` | Shared selectors / JS snippets |

## Design rationale

- **Three distinct phases, not one generic "pre-run" hook.**  The timing
  matters: a fast-path that can decide on the event alone shouldn't pay
  for agent construction; a prompt-build enricher needs access to the
  compacted event items but must run before agent construction; a
  PreDispatch scan needs the live browser session.  Collapsing any two
  of these would force hooks to either pay unnecessary setup cost or
  solve their problem at the wrong layer.

- **`build_node.py` owns only the registry + generic contracts.**  It
  has zero knowledge of what any hook does.  Adding a new site bundle
  does not require editing `build_node.py` at all — auto-discovery
  (`_discover_external_hook_bundles`) imports every subpackage under
  `hooks/external/` at process start.

- **Site-specific state lives in site bundles, not in `build_node`.**
  `BrowserUseHookContext` is deliberately slim (17 fields, all
  business-neutral).  The `feige_chat` bundle demonstrates the pattern:
  put your dedup caches, affinity tables, and typing locks in sibling
  modules and have hooks import them directly.

- **Registration is idempotent and opt-in.**  A node that doesn't run a
  registered hook's intended path (e.g. no `actionable_field` config)
  sees the hook return `None` and falls through to the generic path.

## Relationship to `HookDispatcher` bundles

The `HookDispatcher` system (documented in [`HOOK_BUNDLES.md`](./HOOK_BUNDLES.md))
is a separate, more elaborate system that operates at a **different
layer**:

| Aspect | `build_node` lifecycle hooks | `HookDispatcher` bundles |
|---|---|---|
| **Scope** | Wraps the entire browser-automation node | Fires inside the browser-use agent loop |
| **Phases** | 3 fixed phases (before prompt / before agent / before run) | 9 stages (`on_event_*`, `on_pre_step`, `on_pre_action`, `on_post_*`, ...) |
| **Manifest** | None — just Python-level registration | `hook.yaml` with stage/tier/priority/permissions |
| **Trust model** | In-tree Python only | Signed bundles, trust modes, tier system |
| **Runtime lanes** | Python only | Python, JS-injected (CDP), subprocess |
| **Use case** | Business-case orchestration (who runs, what data) | Per-event / per-action intercepts (what to send, what to block) |

A single bundle directory can serve **both** systems.  `feige_chat`, for
example, has a `hook.yaml` + `feige_hooks.py` pair for the
`HookDispatcher` system (quick-reply rules, crosstalk guard extension)
alongside the lifecycle-hook modules described above.  They coexist
because they solve non-overlapping problems.

## File map

| Path | Purpose |
|---|---|
| `agent/ec_skills/build_node.py` | Hook registries + lifecycle plumbing + `BrowserUseHookContext` / `PromptBuildContext` / `PromptBuildResult` |
| `agent/ec_skills/browser_use_extension/hooks/external/feige_chat/` | Reference lifecycle-hook bundle (Feige front-desk pattern) |
| `agent/ec_skills/node_runtime/frontdesk_dispatch.py` | Generic front-desk dispatch state machine consumed by `feige_chat.front_desk.before_run_hook` |
