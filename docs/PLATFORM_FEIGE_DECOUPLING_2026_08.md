# Platform / Feige Decoupling — 2026-08-01 → 2026-08-02 (ws188)

**Result: the platform tree contains ZERO case-insensitive "feige" references.**
Was ~1,300 references across ~45 platform files. Everything business-specific
now lives in `agent/ec_skills/browser_use_extension/hooks/external/feige_chat/`
and is reached through neutral extension points.

Enforcement check (run before merging any future PR):

```bash
rg -c -i feige agent gui utils web_server.py main.py --no-ignore -g '*.py' -g '!__pycache__' \
  | rg -v 'feige_chat|w2p_handlers.feige'
# must print NOTHING
```

Allowed exceptions: the `feige_chat` bundle itself, and
`gui/ipc/w2p_handlers/feige_*.py` (wholly-business handler files that live in
the GUI's pkgutil auto-discovery drop-point — the designated handler extension
surface, analogous to `hooks/external/`).

---

## 1. Why

Repeated user directive: platform code (`ec_tasks/`, `build_node.py`,
`event_monitor.py`, `extension_tools_service.py`, `chat_tools.py`, `utils/`,
GUI shells, ...) must stay business-independent so new sites
(Shopify/WeChat/...) plug in as bundles without touching core. Feige-specific
code had leaked inline everywhere: lazy `feige_chat` imports (~70 sites),
`*FEIGE*` env vars, feige-branded symbols/log tags, and the four `feige_*`
browser tools defined inside the platform tools module.

## 2. Architecture introduced

### 2.1 The runner bridge (the core mechanism)

The bundle registers ONE facade object at import:

```
feige_chat/__init__.py  →  runner_bridge.register()
    → live_chat_dispatch.register_runner_bridge(FeigeRunnerBridge())
```

Platform code resolves it via:

```python
from agent.ec_skills import live_chat_dispatch
bridge = live_chat_dispatch.runner_bridge()   # None if no bundle loaded
```

`FeigeRunnerBridge` (`feige_chat/runner_bridge.py`) exposes ~40 **lazy**
module accessors under generic names (`dispatch_state`, `trace_ledger`,
`delivery_durability`, `tab_pool`, `typing_lock`, `ws_session`,
`actionable_items`, `system_message_filter`, `pre_dispatch_enrich`,
`image_store`, `ws_observer`, `bot_control`, `front_desk`, `dom`,
`placeholder_timer`, `undeliverable`, `tunables`, ...) plus typed methods
(`placeholder_timeout_s()`, `typing_concurrency()`, `tab_resolve_timeout_s()`,
`bypass_on_backpressure()`, `hot_path_drift_retry_max()`,
`cdp_health_cooldown_remaining()`, `mark_cdp_unhealthy()`,
`open_session_tool_name`, `send_message_tool_name`, `site_plugin_name`,
`tool_name_glob`, `site_adapter_preset`, `node_tunable_number/bool_fields`,
`retryable_send_reasons`, `classify_send_error()`).

**Guard-semantics invariant (the behavioral safety property):** every former
`try: from ...feige_chat.X import y ... except: <fallback>` became
`try: y = bridge().X.y ... except: <fallback>` — a missing bundle raises
(AttributeError on None) inside the SAME try/except and takes the SAME
fallback the old failed import took. Sites where the import was unguarded
(bundle required) call the bridge unguarded too. Laziness is preserved: each
bridge property does its `from . import X` on first use, so import cost and
order are identical to the old inline lazy imports.

Bundle load order is guaranteed by `build_node._discover_external_hook_bundles()`
(module-level, runs at first `build_node` import) which imports every bundle
under `hooks/external/` — so the bridge is registered before any task runs.

### 2.2 Site tools moved into the bundle

`feige_list_sessions`, `feige_open_session`, `feige_get_chat_thread`,
`feige_send_message`, `feige_ws_send_text`, `_feige_ws_try_send`, all their
JS template constants, and the four `Feige*Action` pydantic models moved
**verbatim** from `extension_tools_service.py` / `extension_tools_views.py`
into **`feige_chat/site_tools.py`** (~2,700 lines). They keep their
`@custom_controller.action` decorators; registration now happens when the
bundle imports (i.e. at process start, same as before). `site_tools` imports
the generic helpers (`_evaluate_js`, `_json_result`, renamed `live_chat_*`
health functions) FROM `extension_tools_service` — business→platform is the
allowed import direction; the platform module has no module-level import of
any bundle code.

The generic CDP machinery **stayed platform-side** under neutral names:

| old (platform) | new (platform) |
|---|---|
| `feige_cdp_health_cooldown_remaining` | `live_chat_cdp_health_cooldown_remaining` |
| `mark_feige_cdp_unhealthy` / `_healthy` | `mark_live_chat_cdp_unhealthy` / `_healthy` |
| `_record_feige_send_cdp_timeout` / `_success` | `_record_live_chat_send_cdp_timeout` / `_success` |
| `_feige_send_cdp_timeout_remaining` | `_live_chat_send_cdp_timeout_remaining` |
| `_record_feige_cdp_eval_timing` | `_record_live_chat_cdp_eval_timing` |
| `_feige_send_page_timing_fields` | `_live_chat_send_page_timing_fields` |
| `_resolve_feige_tab_target_id_bounded` | `_resolve_live_chat_tab_target_id_bounded` |
| `_evaluate_feige_js` | `_evaluate_live_chat_js` |

All bundle/test callers repointed.

### 2.3 Env vars — generic names + automatic legacy fallback

Platform reads only `DIRECT_LIVE_CHAT_*` / `ECAN_LIVE_CHAT_*` via
`live_chat_dispatch.live_chat_env()` (twin: `ec_tasks.runner._live_chat_env`).
The helper falls back to ANY legacy site-branded alias
(`DIRECT_<SITE>_X` / `ECAN_<SITE>_X`) found in the environment, so **every
existing `DIRECT_FEIGE_*` / `ECAN_FEIGE_*` operator config keeps working
unchanged** (smoke- and test-verified). Renamed knobs include (platform side):

- `DIRECT_FEIGE_*` (job timeout, retries, requeue, circuit, queue depth, ...) → `DIRECT_LIVE_CHAT_*`
- `ECAN_FEIGE_SHUTDOWN_DRAIN_TIMEOUT_S` / `_FALLBACK_WAIT_S` → `ECAN_LIVE_CHAT_...`
- `ECAN_FEIGE_QA_MAX_CONCURRENCY`, `ECAN_FEIGE_EAGER_DELIVERY_WORKER`,
  `ECAN_FEIGE_WS_SKIP_TYPING_LOCK`, `ECAN_FEIGE_WS_TRUST_EVENT`,
  `ECAN_FEIGE_TIMEOUT_ECHO_CONFIRM*`, `ECAN_FEIGE_FALLBACK_DRAIN_KICK*`,
  `ECAN_FEIGE_WS_SEND`, `ECAN_FEIGE_QA_WAITDRAIN_OFFDOM_SKIP`,
  `ECAN_FEIGE_TAB_COUNT`, `ECAN_FEIGE_WS_CAPTURE*`, event_monitor's ~18 knobs,
  `ECAN_RSS_FEIGE_PROTECT_MB` → `ECAN_RSS_LIVE_CHAT_PROTECT_MB`, etc.
- Site-branded knobs with other shapes (`FEIGE_TYPING_CONCURRENCY`,
  `FEIGE_TAB_RESOLVE_TIMEOUT_S`, `FEIGE_PLACEHOLDER_TIMEOUT_S`,
  `ECAN_FEIGE_SEND_CDP_EVALUATE_TIMEOUT_S`, ...) stay bundle-side
  (`tunables.py`) behind typed bridge methods — their spellings are unchanged.

### 2.4 Renamed platform symbols / tags / strings

- `ec_tasks/runner.py`: ~35 `_feige_*` functions → `_live_chat_*`
  (`prepare_feige_shutdown` → `prepare_live_chat_shutdown` — WebGUI caller
  updated), thread `FeigeDirectDelivery` → `LiveChatDirectDelivery`, typing-lock
  owner label `direct_feige_delivery` → `direct_live_chat_delivery`.
- Log tags emitted by platform: `[FEIGE-SHUTDOWN]` → `[LIVE-CHAT-SHUTDOWN]`,
  `[FEIGE-CUSTOMER-STATE]` → `[LIVE-CHAT-CUSTOMER-STATE]`,
  `[FEIGE-FRONTDESK-TIMING]` → `[LIVE-CHAT-FRONTDESK-TIMING]`,
  `[FEIGE-WS-CAPTURE]`/`[FEIGE-WS-CAP-JSON]`/`[FEIGE-PRODUCT-DETAIL-CAP]` →
  `[LIVE-CHAT-...]`, `[FEIGE-LEDGER]` (one build_node fallback line) →
  `[LIVE-CHAT-LEDGER]`. The bundle keeps its own `[FEIGE-*]` tags
  (`[FEIGE-LEDGER]`, `[FEIGE-SCRAPE-LOCK]`, `[FEIGE-WS-SHADOW]`,
  `[FEIGE-DURABILITY]`, ...). **`feige_log_health.py` (memory dir) greps BOTH
  spellings** for the renamed markers.
- Ledger stage/reason strings produced by platform:
  `direct_feige_send_*` → `direct_send_*`,
  `direct_feige_cdp_health_retry_scheduled` → `direct_cdp_health_retry_scheduled`,
  `feige_cdp_health_cooldown` → `cdp_health_cooldown`,
  `queued/inflight_feige_task_*` → `..._live_chat_task_*`,
  `send_chat_feige_task_suppressed_during_shutdown` → `send_chat_task_suppressed_during_shutdown`,
  `feige_focus_contention` → `site_focus_contention`,
  JS skip-reason `feige_non_current_sidebar` → `non_current_sidebar`.
- `DispatchContext.feige_typing_holder_getter` → `typing_holder_getter`
  (bundle `front_desk.py` setter updated).
- Site-specific data moved behind the bridge: builtin `typing_lock` /
  `verify_active_session` guarded-tool defaults, `bypass_actions` fallback
  glob, `site_adapter` preset (→ new `feige_chat/site_adapter_preset.py`),
  build_node's per-node tunable UI-field table
  (`feigeSendCdpEvaluateTimeoutS`, `directFeigeBypassOnBackpressure` now
  contributed by `node_tunable_number/bool_fields` — existing skill JSONs
  unchanged), `main.py`'s startup durability scan (→ bundle `__init__`,
  gated by a neutral pid-stamped env marker `ECAN_PREV_BOUNDARY_UNEXPECTED_PID`).

## 3. File-by-file (refs → 0)

| Platform file | was | notes |
|---|---|---|
| `agent/ec_tasks/runner.py` | 356 | round 1: bridge + renames + env helper |
| `agent/ec_skills/browser_use_extension/extension_tools_service.py` | 455 | tools moved out; health machinery renamed |
| `agent/ec_skills/browser_use_extension/event_monitor.py` | 161 | ~20 imports → bridge; WS-capture tags renamed |
| `agent/ec_skills/node_runtime/frontdesk_dispatch.py` | 84 | ~20 imports → bridge; enrich plugin resolved by `site_plugin_name` |
| `agent/ec_skills/build_node.py` | 47 | QA ledger + drift recovery + tunables → bridge |
| `agent/mcp/server/chat_utils/chat_tools.py` | 43 | local payload helpers renamed; ledger/durability → bridge |
| `agent/ec_skills/browser_node/runner.py` | 32 | mt053K hints renamed; ledger → bridge |
| `utils/memory_monitor.py` | 23 | RSS-protect renamed; ets getattr → bridge method |
| `agent/ec_skills/browser_use_extension/extension_tools_views.py` | 12 | Feige*Action models moved to bundle |
| ~35 further files (hook_api/loader/scaffold, builtin hooks, browser_node/*, llm_utils, logger_helper, main.py, MainGUI/WebGUI, a2a/*, resume, ec_agent, wan_a2a_chat, streamablehttp_pool, cloud_logger, ...) | 1–13 each | comments/log strings genericized; real logic → bridge |

New bundle files: `runner_bridge.py`, `site_tools.py`, `site_adapter_preset.py`.
Bundle files edited: `__init__.py` (3 new registrations), `front_desk.py`
(ctx field name), `dom_assets.py` (+generic aliases, repointed ets names),
`feige_bot_control.py` (+alias), `direct_delivery.py` / `hot_path_v2.py` /
`image_fetch.py` / `tab_pool.py` (repointed renamed ets helpers).

## 4. Verification (behavior-parity evidence)

Method: for every slice, the referencing test suites were run BEFORE the edit
(baseline failure list saved) and AFTER; the failure lists had to be
**byte-identical** (source-scan tests asserting old literals were re-pinned to
the new patterns — that is a test-text change, not a behavior change). The
final ets extraction was verified against a pristine tree snapshot.

- Round-1 runner suites: 26P/10F → identical 10F.
- mt038 source-scan mega-suite (599P/20F baseline): identical 20F at the end.
- ets tool suites (165P/18F snapshot baseline): identical 18F.
- frontdesk suites (27P/5F + parallel-dispatch): identical.
- event_monitor 9-file set (654P/28F): identical 28F.
- browser_node 14-file set: zero new failures (3 baseline failures fixed by a
  sibling slice's re-pin).
- All pre-existing failures verified to fail identically with the cleanup
  stashed (they predate this work).
- Import smoke: bundle auto-loads, bridge registers, all four `feige_*` tools
  present in the controller registry, legacy env aliases resolve
  (`DIRECT_FEIGE_JOB_TIMEOUT_S=42` → runner sees 42).

## 5. Risk analysis for the critical Feige features

The guiding invariant everywhere was **same code, same order, same guards —
only resolved through one extra attribute lookup**. Specifically:

### 5.1 1-vs-N speed (typing-lock / WS fast path / concurrency caps)

- The ws026 **WS-eligible typing-lock skip**, the mt044E **typing
  concurrency semaphore**, ws118 **QA concurrency cap**, and the
  **dedicated CDP loop / raw-WS lanes** are all either untouched bundle code
  or platform code where only the *lookup* of `ws_session.can_send` /
  `tunables` changed to a bridge attribute. Kill-switches kept their
  semantics; legacy env spellings still work (`ECAN_FEIGE_WS_SKIP_TYPING_LOCK`,
  `ECAN_FEIGE_QA_MAX_CONCURRENCY`, ... via alias fallback).
- The bridge adds one dict lookup + (first use only) a module import that
  previously happened at the same call site anyway — nanoseconds against a
  hot path measured in hundreds of ms; **no new locks, no new awaits, no
  changed loop/thread affinity** (ws175 deadlock lesson respected: nothing
  synchronous was added on the CDP-handler loop).
- `hot_path.py`, `hot_path_v2.py` logic, `ws_raw_sender`, `ws_session`,
  `dispatch_state` dedup ledgers: **unchanged** (bundle-side).

### 5.2 Cold start (ws185 milestone)

- The cold-start algorithm (dormant/live state machine, row-click open/claim
  side-channel, ws167 kill-path fixes) lives entirely in the bundle —
  **untouched**.
- The **eager direct-delivery worker** (lever-1) kept its exact trigger; only
  its kill-switch reads `ECAN_LIVE_CHAT_EAGER_DELIVERY_WORKER` with the
  legacy `ECAN_FEIGE_` spelling still honored.
- The **placeholder pipeline** (arm → sweeper → mt051C handler) is unchanged;
  frontdesk's timeout resolution now calls `bridge.placeholder_timeout_s()`
  which runs the *same* `tunables.resolve_float("FEIGE_PLACEHOLDER_TIMEOUT_S", ...)`
  bundle-side.
- Startup ordering: bundle import (and therefore tool + bridge + placeholder
  registration) still happens at first `build_node` import, i.e. before any
  skill/task starts. The relocated durability startup-scan runs at the same
  point in boot, now gated by the pid-stamped marker `main.py` sets.

### 5.3 Watch items for the first live run

1. `[Browser-Use Extension] Registered N custom actions` at boot no longer
   includes the four `feige_*` tools (they register moments later at bundle
   import). Confirm the four appear in the registry before first dispatch —
   the bundle-load log line `Loaded 1 external hook bundle(s): feige_chat`
   is the marker.
2. Renamed platform log tags: use `feige_log_health.py` as usual — it greps
   both old and new spellings for CUSTOMER-STATE etc. If any private grep
   scripts look for `[FEIGE-SHUTDOWN]`, `[FEIGE-FRONTDESK-TIMING]`,
   `[FEIGE-WS-CAPTURE]`, `FeigeDirectDelivery`, `direct_feige_send_*`, or
   `feige_focus_contention`, update them to the `LIVE-CHAT`/generic forms.
3. Env aliases: legacy `*FEIGE*` values are read via an `os.environ` scan; a
   *conflicting* pair (both old and new names set to different values) prefers
   the NEW name. Don't set both.
4. If a run shows `no live-chat bundle` style fallbacks (placeholder skipped,
   tools unavailable) the bundle import failed at boot — check the
   `Loaded ... external hook bundle(s)` line first.

Recommended validation run: a standard 1-vs-5/1-vs-8 flood + one cold-start
scenario, then `feige_log_health.py` — expect EVENT-LOOP HEALTH, ack/
placeholder/response triage, and `phase=answered` counts on par with ws187.

## 6. Deliberate leftovers

- `gui/ipc/w2p_handlers/feige_*.py` — business handlers in the designated GUI
  auto-discovery extension surface (see §0); minimal import fixes only.
- Douyin hostname/URL literals (`im.jinritemai.com`, workspace path) in
  `event_monitor.py` / `browser_node/runner.py` — no "feige" token,
  load-bearing match patterns pinned by tests; migrating them behind
  `bridge.url_detector` is a future behavioral refactor.
- `HYBRID_HOOK_AUDIT.md` keeps 8 doc mentions of the bundle's literal
  identifiers (historical audit).
- Test files' own feige literals (fixtures, legacy env spellings) — tests are
  not in the zero-match scope and double as alias-fallback regression checks.
