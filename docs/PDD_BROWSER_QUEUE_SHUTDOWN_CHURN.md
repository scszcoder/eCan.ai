# PDD front-desk `QueueShutDown` churn — root cause & fix

**Build:** 0.9.99yao · **Reported:** 2026-10-17 (customer running a 抖店 store + a
拼多多 store in one app process) · **Symptom:** "二个店铺同时打开还是会卡" — and the
拼多多 front desk never actually answered.

## What the log showed

`customer_logs/eCan.log` (build yao):

- **41×** `bubus.service.QueueShutDown` on `task=拼多多客服前台001` in ~2 minutes
  (14:32:36 → 14:34:40) vs **1×** on the 抖店 front desk.
- Each failure was preceded, every ~12 s, by the same cycle:

  ```
  [BrowserAutomation] Applied keep_alive=True to reused browser session profile
  [BrowserAutomation] Passing cancellation_event to agent.run()
  browser_use Agent run failed with exception: bubus.service.QueueShutDown
      File "browser_use/agent/service.py", line 2520, in run
  [BrowserAutomation] browser-use run failed: Browser automation failed: QueueShutDown()
  ```

- The PDD monitor sat at `PreDispatch skipped: monitor not ready
  (status=starting, current_url='')`, so PDD runs were cancelled early.

> **Correction (later investigation, rotated logs `eCan.log.1/.2`):** the page
> *did* load and the store *was* logged in. The single `Launching fingerprint
> profile: pdd_main` in `eCan.log` belongs to a *later* process (18:58) where PDD
> worked; the failures are in an earlier process that attached at 09:51 and
> served normally until 14:24. See "Why PDD's monitor was stuck in starting".

## Root cause

`bubus` (browser-use's event bus) backs each `BrowserSession` with an
`event_queue` that raises `QueueShutDown` once `shutdown()` has been called
(`bubus/service.py`: `_is_shutdown`). `browser_session.start()` dispatches a
`BrowserStartEvent` on that queue, so starting a session whose bus is already
shut raises `QueueShutDown` immediately.

The sequence that poisons the session:

1. PDD's monitor reports not ready (frozen at `starting` — see below), so its
   `agent.run()` is cancelled (via the `cancellation_event`). A cancelled run's teardown shuts the session's bubus
   `event_queue`.
2. The session is kept-alive (event-monitored front desk), so it **stays in
   `cached_browser_sessions`** under its scope key even though its bus is dead.
   (`Applied keep_alive=True to reused browser session profile` precedes every
   failure.)
3. The next invocation reuses the cached session. `get_or_create_browser_session`
   (`browser_node/build_helpers.py`) *does* guard reuse with `is_session_alive()`
   — which checks `event_queue._is_shutdown` — but the shutdown happens
   concurrently relative to that check, so the poisoned session still gets reused
   and `start()` re-dispatches on the dead queue.
4. The run fails with `QueueShutDown`, **nothing evicts the session**, and the
   front desk retries → it reuses the *same* dead session again → churn forever.

An existing monkey-patch (`patch_eventbus_dispatch_for_shutdown`) only *swallows*
the exception on dispatch; it does not break the reuse loop, so the churn
continued.

### Why it matters (resource impact)

Each failed attempt still constructs a browser-use `Agent` (history + per-step
pydantic models). 41 attempts in 2 minutes is sustained CPU churn and feeds the
per-run agent allocation that the browser-agent memory leak fix
(`project_mem_leak_crash_fix_merged`) addresses. It is both a correctness bug
(PDD never answers) and a resource drain.

## Fix

`agent/ec_skills/browser_node/runner.py`:

- `_exc_chain_has_queue_shutdown(exc)` — detects a `QueueShutDown` anywhere in an
  exception's `__cause__` / `__context__` chain (and, as a fallback for a chain
  broken by `raise … from None`, by message substring).
- `_force_recreate_cached_session(scope_key, agent)` — sets `_ecan_force_recreate`
  on the scope's cached `BrowserSession`. `get_or_create_browser_session` already
  skips reuse and rebuilds a fresh session when that flag is set (the eviction
  path at `build_helpers.py` also preserves the focus target), so this reuses the
  existing designed mechanism rather than inventing a new one.
- In `_BrowserRunSession.run()`'s outer `except Exception`, when the failure is a
  `QueueShutDown` we flag the cached session before re-raising.

Net effect: a dead-bus session now fails **once**, is flagged, and the next run
builds a fresh session — instead of reusing the poisoned one on every retry.

This does **not** change what gets sent or any happy-path behaviour; it only adds
recovery on a specific failure. The pre-existing dispatch-swallow patch is left in
place (belt and suspenders).

## Why PDD's monitor was stuck in `starting`

Not a login or page-load problem. Reconstructed from `eCan.log.2` → `.1` →
`eCan.log` (one process, pid 22196):

1. **09:51** `pdd_main` attached, monitor set `b2ce1bc2` started, first
   heartbeat `status=ok url=…/chat-merchant/…`, `[PDD-WS] observer live`.
   Normal operation until 14:19.
2. **14:23–14:24** the 拼多多 front-desk task restarted in the same process. A
   responder's `a2a_response` resumed it under a new **per-customer scope**
   (`chat:<uid>:拼多多客服前台01`), which created a new BrowserSession and a new
   monitor set (`1ed0d968`) **on the same chat tab**.
3. Starting that set **replaced the working socket observer** (`[PDD-WS] replacing
   the observer already on tab …` → old observer stopped after 413 frames / 25
   dispatches). More per-customer scopes (14:25, 14:26) replaced it again. **Every
   replacement observer received 0 frames** for the rest of the run.
4. While an observer claims dispatch (`ws_session.is_dispatch_live`),
   `event_monitor.check_now` skips the DOM poll, and the readiness snapshot
   (`last_status`, `last_current_url`) is only written by that poll. So the new
   sets stayed at their initial `starting` / `''` forever, PreDispatch refused
   them, and replies fell back to slow multi-step LLM browser runs — whose
   cancellations then produced the `QueueShutDown` churn above.

Why the replacement observers got no frames is **not provable from the log**. It
was silent at INFO level, which is why diagnostic logging was added (below).

### Diagnostic logging added

| Where | What it logs |
|---|---|
| `event_monitor.py` `check_now` (WS-pause branch) | `[EventMonitor] DOM poll paused: WS dispatch live … set=… target=… last_status=… last_url=… age=…s` — at most once a minute per set. This alone would have explained the incident. |
| `event_monitor.py` state init | new `started_at` stamp per monitor set |
| `frontdesk_dispatch._validate_monitor_ready` | "monitor not ready" now includes `set=`, `target=`, `monitor_age=` |
| `pdd_chat/ws_observer._watch_list` | one WARNING when an observer has had **0 socket frames for ≥120 s** while still claiming dispatch |
| `pdd_chat/ws_observer.start_ws_shadow_observer` | "observer live" now says `session=` and `replaced_previous=` |
| `browser_node/runner.py` store pre-navigation | logs the focused tab's URL when it is *not* blank (once per URL per session); WARNING when it is off the store's site (login-redirect signature) |

### Not fixed here (follow-ups, need a decision)

- **Per-customer scopes start a second monitor set + replace the observer on the
  same tab.** That is the trigger. Candidate fixes: don't start a monitor set for a
  `chat:` scope on a profile that already has a live set; and/or have an observer
  with 0 frames for N seconds stop claiming dispatch (`set_dispatch_live(False)`)
  so the DOM monitor resumes. Both touch the hot path, so they wait for the new logs
  to confirm the mechanism on the next customer run.
- `event_monitor` opens a "dedicated detection tab" even though PDD's bridge
  declares `single_chat_page = True`, then fails on `PddRunnerBridge.tab_pool`;
  PDD then closes the extra chat tab. Unproven contributor (PDD allows one chat
  session per account).
- Noise: `drift-recovery signal mark failed (non-fatal): 'PddRunnerBridge' object
  has no attribute 'drift_recovery'` (WARNING, 45× across the logs) — PDD
  intentionally lacks that capability; the caller should `getattr(…, None)` and
  skip quietly.
- Preventing the event-bus shutdown race at the source (keep-alive teardown vs.
  cancel) would be a deeper change in a battle-tested concurrency path;
  recovery-on-failure was chosen as the low-risk fix.

## Tests

`tests/unit/test_browser_session_queue_shutdown_recovery.py` (4):
chain + wrapped + `from None` detection, cache-flagging, agent-session fallback,
and the best-effort no-raise contract.
