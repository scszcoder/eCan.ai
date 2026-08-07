# Step 1 — reference live-chat bundle hook audit

Historical audit of the reference live-chat bundle (the first external
hook bundle, under `hooks/external/`; hook/class/file names below are
that bundle's literal identifiers).

Goal: classify every hook in the reference bundle by tier
(`cloud_only` / `local_extract` / `local_reactive` / `local_only`) and
surface fields/APIs each hook touches that don't fit cleanly into a
single tier. Output drives steps 2–3 (context-shape design + protocol
extension).

## Inventory

The bundle exposes **5 hooks** across **2 dispatch systems** plus
**6 support modules**.

### HookDispatcher manifest hooks (`hook.yaml`)

| # | Hook | Stage | Class | File |
|---|---|---|---|---|
| 1 | `feige_quick_reply` | `on_event_normalized` | `FeigeQuickReplyHook` | `feige_hooks.py` |
| 2 | `feige_crosstalk_guard_ext` | `on_pre_action` | `FeigeCrosstalkGuardHook` | `feige_hooks.py` |

### Lifecycle hooks (registered via `register()` calls in `__init__.py`)

| # | Hook | Phase | File |
|---|---|---|---|
| 3 | `before_prompt_build_hook` | prompt-build | `actionable_items.py` |
| 4 | `before_session_setup_hook` | early/session-setup | `front_desk.py` |
| 5 | `before_run_hook` (PreDispatch) | late/pre-run | `front_desk.py` |

### Support modules (utility code, not hooks)

| Module | Role |
|---|---|
| `dom_assets.py` | Site-specific JS snippets, selectors, scrape helpers |
| `dispatch_state.py` | Module-level dedup caches (recent-sends, last-typed, last-msg-id) |
| `typing_lock.py` | Process-wide typing lock (race guard) |
| `hot_path.py` | Helpers for HOT-PATH-B direct-typing orchestration |
| `pre_dispatch_enrich.py` | Enrichment plugin for `frontdesk_dispatch` |
| `feige_hooks.py` | Houses hooks #1 and #2 |

## Classification

### Hook 1 — `FeigeQuickReplyHook` (`on_event_normalized`)

**Inputs:** event payload dict (`{text, customer_name|customer_id, ...}`),
`ctx.state` KV cooldown cache, `config.quick_replies` (from `hook.yaml`).

**Outputs:** `HookResult.bypass(actions)` with a single
`feige_send_message` action, OR `HookResult.cont()` if no match.

**Touches:**
- ✅ Pure: payload dict, regex-style exact match, config lookup
- ✅ Small KV: `ctx.state.get/set("last:<customer>", ts)` for cooldown
- ❌ No DOM, no agent, no mainwin, no LLM, no browser session

**Tier: `local_reactive`** ← canonical case

This is exactly what `local_reactive` was designed for: latency-critical
template typer with bounded surface. Cooldown state is per-session local
KV (no cross-customer reach). Bundle config (`quick_replies` map) is
the IP worth protecting; `local_signed` encrypts it at rest.

**Hybrid migration cost:** trivial. `ctx.state` already abstracts the
KV; just point it at a session-scoped `dict` instead of the
HookDispatcher's process-wide store.

---

### Hook 2 — `FeigeCrosstalkGuardHook` (`on_pre_action`)

**Inputs:** proposed action params (text, target customer_id), live
DOM via `evaluate_javascript` to verify the active sidebar customer
matches the action's intended target.

**Outputs:** `HookResult.cont()` (proceed) or `.drop()` (veto crosstalk).

**Touches:**
- ❌ **Live DOM read** via `browser_session.evaluate_javascript`
- ❌ Inherits from in-tree `VerifyActiveSessionHook` (Tier-0 builtin)
- ✅ Pure logic on the JS result

**Tier: `local_reactive`** (must be local — needs live DOM)

Latency-sensitive: runs before *every* tool call, must not add
round-trip latency. Reads DOM, so it can't run cloud-side. Inherits
from a **Tier-0 builtin** which is itself local-only — meaning the
parent class needs a local mirror anyway, so this hook naturally
co-locates.

**Caveat:** the parent `VerifyActiveSessionHook` (in-tree builtin) must
also be available locally. Today both are local; tier classification
of builtin hooks is a separate exercise but trivially `local_only` or
`local_reactive`.

**Hybrid migration cost:** small. The DOM-eval surface is already
narrow (one JS string return). Encode the check as
`LocalReactiveContext.eval_js(snippet) → result` primitive.

---

### Hook 3 — `actionable_items.before_prompt_build_hook` (prompt-build)

**Inputs:**
- `prompt_ctx.compact_items` (already-extracted DOM items)
- `prompt_ctx.actionable_raw` (full DOM rows)
- `prompt_ctx.event_type`
- `hook_ctx.mainwin` (for agent registry lookups)
- `hook_ctx.calling_agent_id`
- `inputs.autoDispatch` config block
- `inputs.protocolOverride`, `inputs.taskHint` template strings

**Outputs:** `PromptBuildResult` with task-hint block + protocol-override
block + injected `agent_list`, OR a `state` dict that **short-circuits
the LLM** if auto-dispatch fired.

**Touches:**
- ✅ Operates on **already-extracted** `compact_items` (cloud-safe)
- ❌ `mainwin.agents` list iteration (agent registry — cloud-side state)
- ❌ Calls `_list_chat_agents(mainwin, ...)` to enumerate worker agents
- ❌ Calls `_auto_send_chat(mainwin, send_config)` for fan-out dispatch
- ❌ Reads `_get_agent_load(agent_id, mainwin)` for queue depth
- ❌ Calls `_inflight_check_and_set` (cross-customer dispatch dedup)
- ✅ No DOM access, no browser session, no JS eval

**Tier: `cloud_only`**

This hook does **dispatch decisions** — exactly the kind of logic the
user said belongs cloud-side. The DOM extraction has already happened
upstream (it operates on `compact_items`). Every external dependency
(`mainwin.agents`, agent registry, send_chat to Q&A) lives cloud-side
in the hybrid model.

**Migration:** straightforward port. The `hook_ctx.mainwin` reference
becomes a `CloudHookContext.agent_registry` proxy. `_auto_send_chat`
becomes an in-cloud call (Q&A agents are cloud-only). Zero round-trips
to local during this hook's execution.

---

### Hook 4 — `front_desk.before_session_setup_hook` (early phase)

**Inputs:**
- `state.prompt_refs.events`, `state.events`, `state.input` (event payload sources, with stale-bleed detection logic)
- `inputs.hotPathActions` config block
- `hook_ctx.get_or_create_browser_session` ← **acquires a real local browser**
- `hook_ctx.mainwin`
- `hook_ctx.normalize_dispatch_identity_key`
- `hook_ctx.clear_dispatch_inflight`

**Outputs:** Either:
- `HOOK_HANDLED` (HOT-PATH-B fired — typed reply directly via DOM), OR
- `None` (no hot-path match; let LLM proceed)

**Touches:**
- ❌ **Live browser session** acquisition + `evaluate_javascript`
- ❌ DOM reads via `dom_assets` JS snippets (active customer, latest bubble)
- ❌ DOM writes via `extension_tools_service` controller (typing actions)
- ❌ Process-wide `typing_lock` (`_typing_lock.try_acquire/release`)
- ❌ Module-level `dispatch_state` (recent-sends dedup, last-typed cache)
- ❌ Cross-cycle bleed detection on `state.events` / `state.input`

**Tier: `local_reactive`** ← but with sub-structure

This is the most complex hook and the most interesting case. It's
**fundamentally local** (browser session + DOM + typing lock), but
internally it does:

1. **Event payload extraction** from messy state (cloud-side concern)
2. **Hot-path rule matching** (template logic — IP)
3. **DOM scrape + privacy-OK customer-name verification** (must be local)
4. **Typing-lock acquisition + DOM type** (must be local)
5. **Dedup write to `dispatch_state`** (local cache, fine)

Steps 1–2 *could* run cloud-side; steps 3–5 must run local. As written,
the hook is monolithic — splitting it requires either:

- **(A)** Keep monolithic, classify whole hook as `local_reactive`. Ship
  the entire hook including step-1 logic in the encrypted bundle. Pro:
  no refactor needed. Con: more IP surface in the local bundle than
  necessary.
- **(B)** Split into two hooks: `early_payload_normalize` (cloud_only,
  produces a clean event payload from `state.events`/`prompt_refs`) and
  `early_hotpath_typer` (local_reactive, takes the clean payload + DOM
  scrape result, decides if/what to type). Pro: less local IP. Con:
  refactor cost; cloud→local round-trip adds ~200ms before HOT-PATH-B
  even starts evaluating its rules.

**Recommendation:** start with (A) for simplicity. The "stale-bleed
detection" + payload extraction is ~80 lines of defensive Python that
is genuinely useful IP-bundled with the rule-matching logic. Revisit if
local bundle size becomes a concern.

---

### Hook 5 — `front_desk.before_run_hook` (PreDispatch, late phase)

**Inputs:**
- `agent` (live `browser_use.Agent` instance with `browser_session`)
- `state`, `inputs`
- `hook_ctx.mainwin`
- `hook_ctx.calling_agent_id`
- Built-in helpers: `safe_format_dict`, `extract_runtime_invocation_input`, etc.
- `_typing_lock.holder` (process-wide lock state)

**Outputs:** dispatch result dict (which Q&A agents got which messages),
or `None` to let the LLM run.

**Touches:**
- ❌ **Live `agent.browser_session`** — full browser-use Agent
- ❌ DOM walk: scrapes the entire customer sidebar via JS eval
- ❌ Per-customer enrichment (clicks each row, scrapes msg, extracts ID)
- ❌ Dispatch fan-out to Q&A agents via `mainwin` agent registry + `send_chat`
- ❌ Module-level dispatch_state writes (last-msg-id, last-typed-reply)
- ❌ Cross-customer affinity / dispatch dedup

**Tier: split — `local_extract` + `cloud_only`** ← biggest refactor

This is the user's exact described scenario:

> "the local side, the hot path analyze dom and gather all the info,
> and then send these raw info to the cloud side"

The hook today is one closure that does DOM-walk → enrich → decide →
dispatch. To fit the hybrid model it splits into:

**Local part (`local_extract`):**
- Walk customer sidebar DOM
- For each row: click into it, scrape latest bubble, extract identity keys
- Apply privacy filter
- Return list of `{customer_id, customer_name, last_msg, msg_id, identity_keys, scrape_ok, scrape_error}` dicts

**Cloud part (`cloud_only`):**
- Receive enriched list
- Run dedup (`dispatch_state.last_msg_id_by_customer`)
- Match each customer to a Q&A agent (affinity rules)
- Call `send_chat` for each match (cloud-side, since Q&A is cloud-only)
- Update affinity / dedup state

**Migration cost: HIGH.** This is the single biggest refactor in the
audit. The current monolithic implementation passes a live `agent`
object around through multiple layers of `frontdesk_dispatch.run()` →
`pre_dispatch_enrich.enrich_item()`. Splitting it cleanly requires:

1. Define the wire-format for the local→cloud enriched-list message
2. Refactor `frontdesk_dispatch.run()` to accept pre-enriched data
   instead of a live `agent`
3. Move dispatch-decision logic out of `frontdesk_dispatch` into a
   cloud-side equivalent
4. Keep `pre_dispatch_enrich` local-side, returning serializable dicts
   instead of mutating shared state

Today the user already noted this hook is **silently skipped in cloud
mode** (`_handle_pre_dispatch` runs only on the local branch in
`runner.py`). So the refactor is not just for hybrid — it's required
for the hook to function at all in any cloud mode.

## Summary table

| Hook | Tier | DOM? | Decisions? | Migration |
|---|---|---|---|---|
| 1 — `FeigeQuickReplyHook` | `local_reactive` | no | template match | trivial |
| 2 — `FeigeCrosstalkGuardHook` | `local_reactive` | yes (read) | veto | small |
| 3 — `actionable_items.before_prompt_build_hook` | `cloud_only` | no | dispatch | straightforward |
| 4 — `front_desk.before_session_setup_hook` (HOT-PATH-B) | `local_reactive` | yes (read+write) | template + lock | medium (consider future split) |
| 5 — `front_desk.before_run_hook` (PreDispatch) | **split** `local_extract` + `cloud_only` | yes (heavy walk) | dispatch fan-out | **high** |

## Tier validation

The tier scheme holds up against real code:

- **`cloud_only`** cleanly fits #3. ✅
- **`local_reactive`** fits #1, #2, #4. ✅
- **`local_extract`** fits the DOM-scrape half of #5. ✅
- **`local_only`** is unused in this audit (no hooks target full-local
  mode exclusively). It exists as the legacy escape hatch only. ✅

No hook resists the classification. The only real complexity is **#5's
required split**, which validates that the tier boundaries are at the
right place — they expose a refactor that the current
"silently-skip-in-cloud-mode" architecture has been hiding.

## Cross-cutting concerns surfaced

### State that crosses the boundary

Three module-level state stores in `dispatch_state.py` and
`typing_lock.py` are accessed by both local and (post-split) cloud
hooks:

1. `_recent_sends` (HOT-PATH-B dedup) — written by hook #4 (local),
   read by hook #4 (local). **Stays local.** ✅

2. `last_agent_reply_by_customer` — written by hook #4 (local),
   read by hook #5's local_extract part to skip stale DOM echoes.
   **Stays local** (both readers/writers local). ✅

3. `last_dispatched_msg_id_by_customer` — written by hook #5's
   cloud_only dispatch step, read by hook #5's local_extract step
   (DOM dedup). **Crosses boundary** — cloud must push invalidations
   to local, OR local does optimistic dedup and cloud reconciles.

`typing_lock` is purely local (process-wide, single browser session).
**Stays local.** ✅

So **only one state field genuinely crosses** the boundary: the
last-dispatched-msg-id map. That's a manageable scope for the state-sync
layer in step 4. (Earlier I worried about CRDTs; we don't need them.)

### Live `agent` object (hook #5)

The current `before_run_hook` signature passes `agent: Any` (live
browser-use Agent). In hybrid mode, this object doesn't exist on the
cloud side. Two options:

- **Option X:** cloud-side hook receives a serialized "agent state
  snapshot" `{browser_url, current_page_dom_summary, ...}` instead.
- **Option Y:** cloud-side hook is structured as a callback that
  *requests* primitive operations and awaits results. (Closer to
  Alternative D from earlier.)

Option Y is what step 2's `CloudHookContext` design needs to nail down.

### `mainwin` ubiquity

`hook_ctx.mainwin` is referenced by **3 of 5 hooks** (#3, #4, #5) for:
- agent registry enumeration (`mainwin.agents`)
- queue-depth lookup (`agent.runner.task_queue`)
- send_chat invocation (`mainwin.channel_bridge`)
- bridge-routed reply delivery

In hybrid mode, all of these are cloud-side concerns (they're about
agent orchestration, not browser interaction). The `CloudHookContext`
should expose a narrow `agent_registry` + `send_chat` proxy and **not
expose `mainwin` at all**. This forces hooks to declare what
orchestration capabilities they actually need, rather than relying on
the kitchen-sink `mainwin` reference.

## Output → step 2

For step 2 (`LocalHookContext` / `CloudHookContext` split), the audit
yields these concrete field requirements:

### `CloudHookContext` must expose

- `node_name: str`
- `calling_agent_id: str`
- `agent_registry`: enumerate worker agents, get queue depth
- `send_chat(target_agent_id, message)`: dispatch to Q&A agent
- `dispatch_state`: cross-customer dedup KV (last_msg_id, affinity)
- `inflight_locks`: cross-customer dispatch inflight lock
- `safe_format_dict`: template helper (pure)
- `normalize_dispatch_identity_key`: pure helper

### `LocalReactiveContext` must expose

- `node_name: str`
- `state: SessionKV` (per-session, ephemeral)
- `eval_js(snippet) → result`: bounded JS-eval primitive
- `type(selector, text)`: typing primitive
- `click(selector)`: click primitive
- `read_dom(selector, depth) → tree`: DOM read primitive (privacy-filtered)
- `typing_lock`: process-local lock (try_acquire, release, holder)
- `local_state`: module-level `dispatch_state` access for local writes

### `LocalExtractContext` must expose

- `read_dom(selector, depth) → tree`: privacy-filtered DOM read
- `eval_js(snippet) → result`: scoped JS eval (scrape-only)
- `click(selector)`: needed for "click row to open then scrape" pattern
- `wait_for(selector, condition)`: stability helper
- (no state access — extracts are pure functions of DOM state)

### Things `BrowserUseHookContext` exposes today that should NOT cross the boundary

- `mainwin`: split into `agent_registry` + `send_chat` (cloud-side only)
- `cached_browser_sessions`: implementation detail, hide behind
  `get_or_create_browser_session`
- raw `browser_session` object: replace with primitive proxies

## Recommendation

Proceed to step 2 — context-shape design. The audit confirms the tier
scheme is sound and identifies hook #5's split as the biggest engineering
task. Suggest scheduling the refactor in this order:

1. **Step 2a:** define the 3 context dataclasses based on this audit
2. **Step 2b:** port hook #1 to `local_reactive` first (simplest, validates tier)
3. **Step 2c:** port hook #3 to `cloud_only` (validates cloud tier)
4. **Step 2d:** port hook #2 (validates DOM-eval primitive)
5. **Step 2e:** port hook #4 monolithically to `local_reactive`
6. **Step 2f:** split hook #5 into `local_extract` + `cloud_only`

At each step, run the reference bundle end-to-end in `full_local` mode to
prove no regression before touching hybrid mode wire-up (steps 3–4).
