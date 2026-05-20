# Feige Multi-Tab Architecture — design + adaptation guide

This document describes the multi-tab refactor that landed in May 2026
on the `feige_multitab` branch.  It serves two audiences:

1. **Maintainers** working on the Feige `external hook bundle` —
   architecture reference and rationale.
2. **Future customer onboarding** — when we ingest another platform
   that has the same single-tab-bottleneck pattern, this is the
   template to follow.

---

## Why this exists

Through 2026-05-19 the Feige (飞鸽) integration used a single Chrome
tab for everything: EventMonitor polling, sidebar scraping, customer
chat focus, message typing.  A single typing-lock serialised all
sends.  On a 20-customer flood that meant ~10s/customer × 20 = 200s
tail latency, well past Feige's 30-second red-flag deadline.  Around
half of the customers in a flood were silently dropped or flagged.

Manually verified on 2026-05-20: Chrome can host multiple tabs of the
same Feige store, each tab independently focused on a different
customer's chat thread.  This unlocks **per-tab parallelism**:

| Tabs | Worst-case 20-customer flood latency |
|------|--------------------------------------|
| 1 (single-tab, today) | ~200s |
| 2                     | ~100s |
| 4                     | ~50s  |
| 6                     | ~33s  (just fits 30s deadline) |
| 8                     | ~25s  (none flagged) |

---

## The split: monitor tab + typing-tab pool

```
┌─────────────────────────────────────────────────────────────┐
│ Chrome                                                       │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐ │
│  │ Monitor tab    │  │ Typing tab #1  │  │ Typing tab #N  │ │
│  │ (designated)   │  │ (in pool)      │  │ (in pool)      │ │
│  │                │  │                │  │                │ │
│  │ EventMonitor   │  │ pinned to      │  │ pinned to      │ │
│  │ PreDispatch    │  │ customer X     │  │ customer Y     │ │
│  │ sidebar scrape │  │ types reply    │  │ types reply    │ │
│  │ (read-only)    │  │                │  │                │ │
│  └────────────────┘  └────────────────┘  └────────────────┘ │
└─────────────────────────────────────────────────────────────┘
        ▲                    ▲                    ▲
        │                    │                    │
        │ designate_monitor  │ allocate_for_typing │ allocate_for_typing
        │                    │                    │
        └────────────────┐   │   ┌────────────────┘
                         ▼   ▼   ▼
                  ┌──────────────────────┐
                  │  FeigeTabPool        │   (process-singleton)
                  │  ─ monitor_tab_id    │
                  │  ─ typing_tabs[…]    │
                  │  ─ customer_to_tab[] │
                  └──────────────────────┘
```

### Monitor tab — 1 dedicated, never types

* All EventMonitor + PreDispatch DOM polling lands here.
* Read-only operations.  Typing lock never held by this tab.
* PreDispatch's sidebar scrape always has a clear CDP window —
  fixes the Bug 2 starvation pattern (客户17, 客户16) we saw
  through 2026-05-19.

### Typing tab pool — N tabs, each pinned-then-released

* Each typing tab carries one customer's reply at a time.
* `allocate_for_typing(customer)` picks a free tab; sticky-preferred
  (same customer's prior tab reused → skips `feige_open_session`
  sidebar-click cost).
* `release(target_id, succeeded)` returns the tab to the pool;
  sticky retained on success, cleared on failure.
* When all tabs are busy, allocation returns `None` and the caller
  falls back to monitor-tab typing (today's serialized behaviour) —
  graceful degradation, never silent drop.

---

## Files in this bundle

| File | Role |
|------|------|
| `tab_pool.py` | Process-singleton registry.  Customer↔tab mappings, allocation/release, health flags. |
| `tab_lifecycle.py` | CDP-level operations: open new tabs, close, health-check, background sweep. |
| `dom_assets.py` | (modified) `resolve_feige_tab_target_id(customer_key=)` consults the pool first; falls back to monitor tab.  `ensure_feige_tab_focused` calls `pool.designate_monitor` after picking the Feige tab and one-shot kicks off `tab_lifecycle.initialize_typing_pool`. |
| `tunables.py` | New tunables `DEFAULT_FEIGE_TYPING_TAB_COUNT` (default 0 → single-tab) and `DEFAULT_FEIGE_TYPING_TAB_HEALTH_SWEEP_S` (default 0 → disabled). |
| `../extension_tools_service.py` | (modified) `_evaluate_feige_js(customer_key=)` and `_resolve_feige_tab_target_id_bounded(customer_key=)` thread the customer name through so the pool can route. |
| `../../ec_tasks/runner.py` | (modified) `_do_guarded_direct_delivery` allocates from pool before invoking `feige_send_message`; releases in finally. |

---

## Lifecycle of one customer reply

```
[1]  customer sends message
[2]  EventMonitor (monitor tab) detects DOM mutation
[3]  PreDispatch scrapes sidebar (monitor tab, lock-free)
     → dispatches Q&A to bot
[4]  Q&A bot reply arrives at front-desk via a2a_response
[5]  runner._do_guarded_direct_delivery picks it up
[6]  → pool.allocate_for_typing(customer)
        a) sticky: same tab as last reply? reuse
        b) else LRU pick a free, healthy tab
        c) else None → fall back to monitor (degraded)
[7]  feige_open_session on the assigned tab (only if not already focused)
[8]  feige_send_message types the reply
[9]  → pool.release(target_id, succeeded=ok, customer_key=...)
        success → sticky retained
        failure → sticky cleared, next attempt picks fresh tab
```

---

## Tunables (controls)

| Tunable | Env var | Default | Effect |
|---------|---------|---------|--------|
| `FEIGE_TYPING_TAB_COUNT` | `ECAN_FEIGE_TYPING_TAB_COUNT` | `0` | Pool size.  `0` = single-tab (today).  `1+` = open that many additional tabs at startup.  Recommended: `2-4` for moderate load, `6-8` for heavy flood. |
| `FEIGE_TYPING_TAB_HEALTH_SWEEP_S` | `ECAN_FEIGE_TYPING_TAB_HEALTH_SWEEP_S` | `0.0` | Background health-check interval.  `0` = disabled (failed tabs detected on next use).  `30` recommended for production. |
| `DIRECT_FEIGE_BYPASS_ON_BACKPRESSURE` | (env) | `True` | Pre-existing.  Less relevant once pool is active because the bypass path triggers less often. |

### Phased rollout safety

Phase 2-4 code ships with `FEIGE_TYPING_TAB_COUNT=0` — zero behaviour
change vs. Phase 1.  Operator flips the env var to `2`, `4`, etc. and
restarts eCan to enable the pool.  No code changes needed to scale.

---

## PROD-VERIFY markers

Search `tab_lifecycle.py` for `PROD-VERIFY:` to find every spot that
needs validation against the real Feige site (vs. our local
emulation):

* URL fragment / pattern (`DEFAULT_FEIGE_URL_FRAGMENT`)
* CDP debug port discovery fallback (default `9228`)
* Sidebar-ready selector (`[data-qa-id="qa-conversation-chat-item"]`)
* Tab navigation timeout budget (`_DEFAULT_NAV_READY_TIMEOUT_S = 8.0`)
* Whether Feige's server rate-limits parallel sends per session

The diagnostic IPC handler `gui/ipc/w2p_handlers/feige_tab_test_handler.py`
("Test Feige Tabs (Inventory)" and "(Concurrent Send)" buttons on the
Tests page) collects the data needed to confirm these.  See its
docstring for what each experiment answers.

---

## Adapting to a future customer platform

When we ingest the next customer-chat platform that has the same
single-tab bottleneck, the multi-tab pattern is essentially identical.
The pieces that change:

### 1. Platform-specific selectors / JS

| Platform-specific bit | Where it lives in this bundle |
|-----------------------|-------------------------------|
| URL fragment / pattern | `tab_lifecycle.DEFAULT_FEIGE_URL_FRAGMENT` |
| Sidebar-ready signal (DOM selector + readiness probe) | `tab_lifecycle._FEIGE_READY_JS` |
| Open-session JS (sidebar click) | `extension_tools_service._FEIGE_OPEN_SESSION_JS` |
| Send-message JS (type + send button) | `extension_tools_service._FEIGE_SEND_MESSAGE_JS` |
| Customer-row selector for scrape | `dom_assets.py` (multiple JS constants near the top) |

For the next platform, copy the `feige_chat/` directory to
`<platform>_chat/`, swap selectors + JS, register the new bundle in
the hook loader.  The multi-tab pool itself is platform-agnostic.

### 2. Generalize the pool out of `feige_chat/` (deferred)

In the long run the pool (`tab_pool.py`) and lifecycle helpers
(`tab_lifecycle.py`) belong **outside** `feige_chat/` — they're not
Feige-specific.  Proposed future location:

```
agent/ec_skills/browser_use_extension/
  multitab/
    pool.py          # was feige_chat/tab_pool.py
    lifecycle.py     # was feige_chat/tab_lifecycle.py — minus DEFAULT_FEIGE_URL_FRAGMENT
  hooks/external/
    feige_chat/      # passes a "ChatPlatformDescriptor" to multitab.lifecycle.initialize_pool
    <next_platform>/ # similar
```

`ChatPlatformDescriptor` would carry:

```python
@dataclass
class ChatPlatformDescriptor:
    url_fragment: str                 # for tab discovery
    ready_signal_js: str              # injected by lifecycle to detect tab-ready
    open_session_action: str          # tool name to focus a customer
    send_message_action: str          # tool name to type+send
```

We're not generalising yet because:
* Only one customer (Feige) currently uses the pattern — generalising
  speculatively risks the wrong abstraction.
* The code is already factored cleanly enough (selectors and JS are
  module constants) that a copy-paste-and-edit takes ~30 minutes.

When the **second** platform lands, refactor.  YAGNI until then.

---

## Known limitations / future work

1. **Monitor tab promotion on crash** — if the monitor tab dies,
   nothing currently promotes a typing tab to monitor.  Process
   restart recovers.  Phase 4+ work.

2. **Typing-tab pre-warming during idle** — pool is populated once
   at startup.  If a typing tab dies mid-session and we hit
   capacity, the next allocator gets `None`.  A background "ensure
   pool size" sweep could recover.  Currently degraded mode just
   uses monitor tab.

3. **Per-tab typing-lock** — Phase 3 uses the pool's `in_use` flag
   for exclusion within a tab.  The global `typing_lock.py` module
   is still acquired by `feige_send_message` (re-entrant on the
   same customer, so harmless under pool routing).  A future
   cleanup could fully remove the global lock once we're confident
   the pool path is the only typing path.

4. **HOT-PATH-B vs pool** — the HOT-PATH-B recovery path (in
   `front_desk.py`) currently types directly on the monitor tab and
   uses the global lock.  Phase 3 doesn't touch this.  Under heavy
   flood with the pool active, HOT-PATH-B firing on the monitor tab
   competes with PreDispatch's read operations there.  Acceptable
   for now (HOT-PATH-B fires rarely after the drift-recovery fixes
   from 2026-05-19); revisit if logs show contention.

5. **Memory cost** — each typing tab is ~80-150 MB of Chrome
   process memory.  6 tabs ≈ 500-900 MB additional.  On lower-end
   machines (8 GB RAM), keep `FEIGE_TYPING_TAB_COUNT` ≤ 2-3.

---

## Quick-start operator guide

To enable multi-tab on a customer install:

```powershell
# Windows: set the tunable BEFORE launching eCan
$env:ECAN_FEIGE_TYPING_TAB_COUNT = "4"   # start with 4 tabs
# (optional) enable background health sweep
$env:ECAN_FEIGE_TYPING_TAB_HEALTH_SWEEP_S = "30"
# Launch eCan as usual
```

On startup, eCan will discover the existing Feige tab (designating
it as monitor), then open 4 additional Feige tabs and load them in
the background.  Watch the log for `[tab_lifecycle] initializing
typing pool: target=4 …` and `[tab_lifecycle] typing pool
initialized: N/4 new tabs opened …`.

After a successful flood test, raise to 8 if the machine has the
RAM budget.  If Chrome OOMs or starts swapping, lower it.

To **disable** and revert to single-tab behaviour, set
`ECAN_FEIGE_TYPING_TAB_COUNT=0` and restart.
