# Browser-use and cdp_use CDP Mechanism

This note summarizes the CDP path used by our Feige browser tools, why `Runtime.evaluate` can time out during flood tests, and how to interpret the phase-level telemetry added at our `_evaluate_js` boundary.

## High-level call path

```text
Feige tool, e.g. feige_send_message
  -> _evaluate_js(...)
  -> browser_use.BrowserSession.get_or_create_cdp_session(...)
  -> cdp_session.cdp_client.send.Runtime.enable(...)
  -> cdp_session.cdp_client.send.Runtime.evaluate(...)
  -> cdp_use.CDPClient.send_raw(...)
  -> Chrome DevTools Protocol websocket
  -> Chrome / Feige renderer executes JavaScript
```

Our code does not call the Chrome websocket directly. `browser-use` owns the browser session and target/session selection. `cdp_use` owns the low-level request/response websocket transport.

## Our `_evaluate_js` wrapper

Location:

```text
agent/ec_skills/browser_use_extension/extension_tools_service.py
```

Responsibilities:

- **Serialize CDP operations** with the per-browser-session `session_cdp_operation_lock` when available.
- **Resolve a CDP session** through `BrowserSession.get_or_create_cdp_session(...)`.
- **Enable Runtime domain** through `Runtime.enable`.
- **Run JavaScript** through `Runtime.evaluate` with:
  - `awaitPromise=True`
  - `returnByValue=True`
- **Apply a hard timeout** using `asyncio.wait_for(...)`.
- **Parse returned JSON strings** into Python values when possible.

Current timeout:

```text
ECAN_CDP_EVALUATE_TIMEOUT_S, default 6.0 seconds
```

If the timeout fires, the raised error now includes the active phase:

```text
CDP Runtime.evaluate timed out after 6.0s (phase=Runtime.evaluate)
```

## browser-use session mechanism

Relevant method:

```text
browser_use.BrowserSession.get_or_create_cdp_session(target_id=None, focus=True)
```

Observed behavior:

- **Requires initialized root CDP client** and `SessionManager`.
- **When `target_id` is omitted**, validates current agent focus via `SessionManager.ensure_valid_focus(...)`.
- **Looks up target session** from the event-driven session pool.
- **Waits up to about 2 seconds** for an attach event if the target session is not present yet.
- **Validates active session** via `SessionManager.validate_session(...)`.
- **Optionally updates focus** only for page targets.
- **Optionally calls** `Runtime.runIfWaitingForDebugger(...)` with a short timeout when focus is true.
- Returns a `CDPSession` containing:
  - `cdp_client`
  - `target_id`
  - `session_id`

In our Feige send path, we normally pass a resolved Feige tab `target_id` and `focus=False`, so the evaluate runs against the Feige page session without asking `browser-use` to switch agent focus.

## cdp_use request mechanism

Relevant class:

```text
cdp_use.client.CDPClient
```

`Runtime.enable` and `Runtime.evaluate` are thin generated wrappers around `send_raw(...)`.

Simplified `send_raw(...)` behavior:

```python
self.msg_id += 1
msg = {
    "id": int(self.msg_id),
    "method": method,
    "params": params or {},
}
if session_id:
    msg["sessionId"] = session_id

future = asyncio.Future()
self.pending_requests[self.msg_id] = future

await self.ws.send(json.dumps(msg))
return await future
```

Simplified response handling:

```python
raw = await self.ws.recv()
data = json.loads(raw)

if "id" in data and data["id"] in self.pending_requests:
    future = self.pending_requests.pop(data["id"])
    if "error" in data:
        future.set_exception(RuntimeError(data["error"]))
    else:
        future.set_result(data["result"])
```

Important property:

- `cdp_use` multiplexes commands by numeric `id` over one websocket.
- The background message handler resolves matching futures when Chrome replies.
- There is no per-command timeout inside `send_raw(...)`; our `_evaluate_js` timeout is the outer guard.

## Cancellation and pending request risk

`send_raw(...)` stores a future in:

```python
cdp_client.pending_requests[msg_id]
```

Then it awaits that future.

If our outer `asyncio.wait_for(...)` times out while `send_raw(...)` is still waiting for Chrome, cancellation can interrupt the await. The inspected `cdp_use` implementation does not remove `pending_requests[msg_id]` in a `finally` block.

Expected outcomes:

- **If Chrome replies later**, `_handle_messages(...)` pops the matching entry and observes the future may already be done/cancelled.
- **If Chrome never replies**, the entry can remain until websocket close/client stop.
- **Under repeated flood timeouts**, this can become an amplifier if `pending_requests` grows.

This does not prove `cdp_use` caused the original timeout. It means `cdp_use` can preserve evidence of stalled or canceled CDP requests, and possibly worsen later behavior if pending requests accumulate.

## Where the 6 seconds can be spent

Our new telemetry separates the timeout into phases:

| Phase | Meaning | Likely implication if timeout occurs here |
| --- | --- | --- |
| `cdp_operation_lock_wait` | Waiting for our per-session CDP lock | Local concurrency/serialization bottleneck |
| `get_or_create_cdp_session` | Resolving browser-use CDP session | Target detach, focus recovery, attach delay, unstable browser session |
| `Runtime.enable` | Sending/enabling Runtime domain | CDP transport stall or browser not responding |
| `Runtime.evaluate` | Waiting for evaluated JavaScript result | Feige renderer busy, JS promise slow/hung, DOM operation/polling cost |
| `complete` | CDP command finished | Success path |

## Telemetry fields

The wrapper emits `[CDP-EVAL]` logs and Feige ledger `cdp_evaluate_trace` events for Feige-labeled tools.

Key fields:

| Field | Meaning |
| --- | --- |
| `action` | Trace label, e.g. `feige_send_message` |
| `ok` | Whether evaluate completed successfully |
| `timed_out` | Whether our outer timeout fired |
| `phase` | Active phase at success/failure/timeout |
| `phase_elapsed_ms` | Time spent in current phase when logged |
| `total_ms` | Total `_evaluate_js` elapsed time |
| `lock_wait_ms` | Time waiting for our CDP operation lock |
| `session_ms` | Time resolving browser-use CDP session |
| `runtime_enable_ms` | Time spent in `Runtime.enable` |
| `runtime_evaluate_ms` | Time spent in `Runtime.evaluate` |
| `pending_before_enable` | `len(cdp_client.pending_requests)` before `Runtime.enable` |
| `pending_before_evaluate` | Pending request count before `Runtime.evaluate` |
| `pending_after_evaluate` | Pending request count after successful evaluate |
| `pending_at_log` | Pending request count at trace emission, including timeout path |
| `current_loop_id` | Event loop running our wrapper |
| `handler_loop_id` | Event loop owning `cdp_use` message handler task, if visible |
| `cross_loop` | Whether wrapper loop and handler loop differ |
| `target_suffix` | Last 8 chars of target id |
| `session_suffix` | Last 8 chars of CDP session id |
| `expression_len` | JavaScript expression length |
| `expression_hash` | Stable hash for correlating repeated expressions without logging full JS |

Feige labels currently added:

- `feige_list_sessions`
- `feige_open_session`
- `feige_get_chat_thread`
- `feige_send_message`

## How to interpret next flood-run results

### Timeout in `cdp_operation_lock_wait`

Primary issue is local concurrency pressure before CDP command starts.

Likely optimization targets:

- Reduce concurrent Feige CDP work.
- Avoid overlapping scrapes/sends.
- Audit lock holders and long guarded sections.

### Timeout in `get_or_create_cdp_session`

Primary issue is browser-use target/session instability.

Likely optimization targets:

- Cache and validate Feige target/session more carefully.
- Reduce target/focus churn.
- Investigate detached targets and recovery logs.

### Timeout in `Runtime.enable`

Primary issue is CDP/browser responsiveness before our JS starts.

Likely optimization targets:

- Avoid redundant `Runtime.enable` when Runtime is already enabled for a session.
- Inspect websocket health and browser process load.
- Check `pending_requests` growth.

### Timeout in `Runtime.evaluate`

Primary issue is Chrome/Feige renderer execution or our JS promise.

Likely optimization targets:

- Shorten `_FEIGE_SEND_MESSAGE_JS`.
- Split send into smaller CDP calls with separate timeouts.
- Reduce DOM polling and expensive selectors.
- Add internal JavaScript timing checkpoints returned on success/failure.
- Consider lower-level DOM/Input CDP commands for click/type if stable.

### `pending_at_log` grows over time

This supports the `cdp_use` pending-request amplifier hypothesis.

Likely optimization targets:

- Add local cancellation cleanup around known timed-out request ids if feasible.
- Recreate CDP client/session after repeated timeouts.
- Add a transport health circuit breaker.
- Consider patching/forking `cdp_use.CDPClient.send_raw(...)` to clean up pending requests on cancellation.

### `cross_loop=true`

This suggests the CDP client message handler task belongs to a different event loop than the caller.

Likely optimization targets:

- Ensure all CDP use for one browser session is routed through one loop.
- Avoid calling browser/session objects from worker loops not owning the CDP websocket.

## Current diagnosis stance

Most likely original cause during the flood test:

```text
Real Feige renderer / CDP transport failed to answer Runtime.evaluate within 6 seconds.
```

Most likely amplifier to prove or disprove:

```text
cdp_use pending_requests accumulate after canceled Runtime.evaluate calls.
```

The new telemetry is designed to distinguish these cases without modifying installed site-packages.
