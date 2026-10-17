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

- `Launching fingerprint profile: pdd_main` appears **exactly once** in the whole
  log — the PDD browser launched once and every retry **reused that one session**.
- The PDD monitor never became ready (`PreDispatch skipped: monitor not ready
  (status=starting, current_url='')`), so PDD runs were cancelled early.

## Root cause

`bubus` (browser-use's event bus) backs each `BrowserSession` with an
`event_queue` that raises `QueueShutDown` once `shutdown()` has been called
(`bubus/service.py`: `_is_shutdown`). `browser_session.start()` dispatches a
`BrowserStartEvent` on that queue, so starting a session whose bus is already
shut raises `QueueShutDown` immediately.

The sequence that poisons the session:

1. PDD's page is not ready, so its `agent.run()` is cancelled (via the
   `cancellation_event`). A cancelled run's teardown shuts the session's bubus
   `event_queue`.
2. The session is kept-alive (event-monitored front desk), so it **stays in
   `cached_browser_sessions`** under its scope key even though its bus is dead.
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

### Not fixed here (follow-ups)

- **Why PDD's page never becomes ready** (`monitor status=starting,
  current_url=''`) — likely a login/launch issue for the 拼多多 store; needs its
  own trace. The fix above stops the churn but PDD still won't answer until the
  page loads.
- Preventing the shutdown race at the source (keep-alive teardown vs. cancel)
  would be a deeper change in a battle-tested concurrency path; recovery-on-failure
  was chosen as the low-risk fix.

## Tests

`tests/unit/test_browser_session_queue_shutdown_recovery.py` (4):
chain + wrapped + `from None` detection, cache-flagging, agent-session fallback,
and the best-effort no-raise contract.
