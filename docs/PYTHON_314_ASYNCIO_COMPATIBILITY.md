# Python 3.14 Asyncio Compatibility Fixes

## Overview

This document explains the breaking changes in Python 3.14's `asyncio` module and the patches applied to make eCan.ai compatible with Python 3.14.

---

## The Problem: Python 3.14 Stricter Timeout Context Requirements

### What Changed in Python 3.14

Starting with Python 3.14, the `asyncio.timeout()` and `asyncio.wait_for()` functions enforce a **stricter requirement**: they must be used inside an `asyncio.Task`.

In Python 3.11-3.13, this code worked fine:

```python
import asyncio

async def my_coroutine():
    await asyncio.sleep(1)

# This worked in Python 3.11-3.13
loop = asyncio.new_event_loop()
loop.run_until_complete(asyncio.wait_for(my_coroutine(), timeout=5.0))
```

In Python 3.14, this raises:

```
RuntimeError: Timeout context manager should be used inside a task
```

### Why This Matters

The issue is that `loop.run_until_complete()` does **not** create an `asyncio.Task`. It runs the coroutine directly on the event loop. Python 3.14's `asyncio.timeout()` internally calls `asyncio.current_task()` and raises an error if it returns `None`.

### The Root Cause in eCan.ai

eCan.ai uses a utility function called `run_async_in_sync()` that creates a new event loop to run async code from synchronous contexts:

```python
def run_async_in_sync(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)  # No Task context!
    finally:
        loop.close()
```

When libraries like `aiohttp`, `httpx`, `websockets`, or `bubus` use `asyncio.timeout()` or `asyncio.wait_for()` internally, they fail because there's no `Task` context.

---

## Affected Libraries and Code Paths

### 1. `aiohttp` Library
- Uses `asyncio.timeout()` internally for HTTP requests and WebSocket connections
- **Symptom**: `RuntimeError: Timeout context manager should be used inside a task`

### 2. `httpx` Library (via `httpcore`)
- Uses `asyncio.timeout()` for connection timeouts
- Also uses `sniffio` to detect async library context
- **Symptom**: `sniffio.AsyncLibraryNotFoundError: unknown async library, or not in async context`

### 3. `websockets` Library
- Uses `asyncio.timeout()` for connection and close timeouts
- **Symptom**: `RuntimeError: Timeout context manager should be used inside a task`

### 4. `bubus` Library (Event Bus)
- Uses `asyncio.wait_for()` for event handling timeouts
- **Symptom**: `RuntimeError: Timeout context manager should be used inside a task`

### 5. `browser_use` Library
- Uses `asyncio.wait_for()` in session management
- Uses `httpx.AsyncClient` for CDP URL fetching
- **Symptom**: Both timeout and sniffio errors

---

## Solutions Applied

### Strategy 1: Replace `asyncio.wait_for()` with Polling Loops

For code that uses `asyncio.wait_for()` to wait for events with a timeout, we replace it with a manual polling loop:

**Before (Python 3.11-3.13):**
```python
await asyncio.wait_for(event.wait(), timeout=30.0)
```

**After (Python 3.14 compatible):**
```python
start_time = asyncio.get_event_loop().time()
while not event.is_set():
    if asyncio.get_event_loop().time() - start_time >= 30.0:
        raise asyncio.TimeoutError()
    await asyncio.sleep(0.01)
```

**Files patched:**
- `site-packages/bubus/models.py`
- `site-packages/bubus/service.py`
- `site-packages/browser_use/browser/session_manager.py`

### Strategy 2: Use Synchronous HTTP Client in Thread

For `httpx.AsyncClient` calls that fail due to `sniffio` not detecting the async context, we use a synchronous `httpx.Client` wrapped in `asyncio.to_thread()`:

**Before (Python 3.11-3.13):**
```python
async with httpx.AsyncClient() as client:
    response = await client.get(url)
```

**After (Python 3.14 compatible):**
```python
def _sync_fetch():
    with httpx.Client() as client:
        return client.get(url)

response = await asyncio.to_thread(_sync_fetch)
```

**Files patched:**
- `site-packages/browser_use/browser/session.py`
- `agent/chats/wan_chat.py`

### Strategy 3: Force Bundled `async_timeout` in `websockets`

The `websockets` library has a bundled `async_timeout` implementation that doesn't require a Task context. We force Python 3.14 to use this bundled version instead of the stdlib `asyncio.timeout()`:

**Before:**
```python
if sys.version_info[:2] >= (3, 11):
    from asyncio import timeout as asyncio_timeout
```

**After:**
```python
if sys.version_info[:2] >= (3, 11):
    if sys.version_info[:2] >= (3, 14):
        # Use bundled async_timeout for Python 3.14+
        from .async_timeout import timeout as asyncio_timeout
    else:
        from asyncio import timeout as asyncio_timeout
```

**Files patched:**
- `site-packages/websockets/asyncio/compatibility.py`

### Strategy 4: Fix Bundled `async_timeout` Assertion Error

The bundled `async_timeout` in `websockets` had an assertion that `self._task is not None`. In Python 3.14, this can be `None` when running outside a Task context:

**Before:**
```python
def _on_timeout(self) -> None:
    assert self._task is not None
    self._task.cancel()
```

**After:**
```python
def _on_timeout(self) -> None:
    if self._task is not None:
        self._task.cancel()
    self._state = _State.TIMEOUT
```

**Files patched:**
- `site-packages/websockets/asyncio/async_timeout.py`

### Strategy 5: Disable Timeouts in WebSocket Connections

For `websockets.connect()` and `cdp_use` client, we disable the `open_timeout` and `close_timeout` parameters to prevent `asyncio.timeout()` from being used:

```python
async with websockets.connect(
    url,
    open_timeout=None,   # Disable to avoid asyncio.timeout
    close_timeout=None,
) as ws:
    ...
```

**Files patched:**
- `site-packages/cdp_use/client.py`
- `agent/chats/wan_a2a_chat.py`

### Strategy 6: Replace `aiohttp` with `websockets` Library

The `aiohttp` library internally uses `asyncio.timeout()` which cannot be easily patched. For WebSocket connections, we replaced `aiohttp` with the `websockets` library (which we already patched):

**Before:**
```python
async with aiohttp.ClientSession() as session:
    async with session.ws_connect(url) as ws:
        ...
```

**After:**
```python
async with websockets.connect(url, open_timeout=None) as ws:
    ...
```

**Files patched:**
- `agent/chats/wan_a2a_chat.py`

---

## Complete List of Patched Files

### External Libraries (site-packages)

| Library | File | Patch Description |
|---------|------|-------------------|
| `websockets` | `asyncio/compatibility.py` | Use bundled `async_timeout` on Python 3.14+ |
| `websockets` | `asyncio/async_timeout.py` | Handle `_task is None` in `_on_timeout()` |
| `cdp_use` | `client.py` | Set `open_timeout=None` in `websockets.connect()` |
| `browser_use` | `browser/session_manager.py` | Replace `asyncio.wait_for()` with polling loop |
| `browser_use` | `browser/session.py` | Use sync `httpx.Client` in thread |
| `bubus` | `models.py` | Replace `asyncio.wait_for()` with polling loop |
| `bubus` | `service.py` | Replace `asyncio.wait_for()` with polling loop |

### eCan.ai Application Code

| File | Patch Description |
|------|-------------------|
| `agent/chats/wan_chat.py` | Use sync `httpx.Client` in thread for `wanSendMessage8()` |
| `agent/chats/wan_a2a_chat.py` | Replace `aiohttp` WebSocket with `websockets` library |

---

## How to Re-Apply Patches After Library Updates

### Automated Patch Script (Recommended)

Use the automated patch script in the `patches/` directory:

```bash
# Apply all patches automatically
python -m patches.apply_patches

# Check which patches are applied
python -m patches.apply_patches --check

# Dry run (preview changes without modifying files)
python -m patches.apply_patches --dry-run --verbose
```

Run this script after:
- Fresh `pip install` of dependencies
- Updating any patched library
- Setting up a new development environment

### Manual Patch Instructions

If the automated script fails (e.g., library code structure changed), you can manually apply patches. Here's a quick reference:

### 1. `websockets` Library

**File:** `site-packages/websockets/asyncio/compatibility.py`

Find:
```python
if sys.version_info[:2] >= (3, 11):
    from asyncio import timeout as asyncio_timeout
```

Replace with:
```python
if sys.version_info[:2] >= (3, 11):
    if sys.version_info[:2] >= (3, 14):
        from .async_timeout import timeout as asyncio_timeout
    else:
        from asyncio import timeout as asyncio_timeout
```

**File:** `site-packages/websockets/asyncio/async_timeout.py`

Find:
```python
def _on_timeout(self) -> None:
    assert self._task is not None
    self._task.cancel()
```

Replace with:
```python
def _on_timeout(self) -> None:
    if self._task is not None:
        self._task.cancel()
    self._state = _State.TIMEOUT
```

### 2. `bubus` Library

**File:** `site-packages/bubus/models.py`

Replace `asyncio.wait_for(self.event_completed_signal.wait(), timeout=...)` with a polling loop.

**File:** `site-packages/bubus/service.py`

Replace `asyncio.wait_for(handler_task, timeout=...)` with a polling loop.

### 3. `browser_use` Library

**File:** `site-packages/browser_use/browser/session_manager.py`

Replace `asyncio.wait_for(ready_event.wait(), timeout=2.0)` with a polling loop.

**File:** `site-packages/browser_use/browser/session.py`

Replace `httpx.AsyncClient` with sync `httpx.Client` wrapped in `asyncio.to_thread()`.

### 4. `cdp_use` Library

**File:** `site-packages/cdp_use/client.py`

Add `open_timeout=None` to `websockets.connect()` kwargs.

---

## Alternative: Downgrade to Python 3.13

If maintaining these patches becomes burdensome, consider using Python 3.13 until the upstream libraries add native Python 3.14 support:

```bash
# Using pyenv
pyenv install 3.13.0
pyenv local 3.13.0

# Or using conda
conda create -n ecan python=3.13
conda activate ecan
```

---

## References

- [Python 3.14 Release Notes - asyncio changes](https://docs.python.org/3.14/whatsnew/3.14.html)
- [asyncio.timeout() documentation](https://docs.python.org/3/library/asyncio-task.html#asyncio.timeout)
- [websockets library](https://github.com/python-websockets/websockets)
- [httpx library](https://github.com/encode/httpx)
- [sniffio library](https://github.com/python-trio/sniffio)

---

## Document History

| Date | Author | Description |
|------|--------|-------------|
| 2026-02-06 | Cascade AI | Initial documentation of Python 3.14 compatibility fixes |
| 2026-02-06 | Cascade AI | Added detailed code patches for all modified site-packages files |

---

# Appendix: Complete Code Patches for Site-Packages

This section contains the exact code changes made to external library files in `site-packages`. These patches must be re-applied after updating any of these libraries via `pip`.

---

## 1. `websockets` Library

### File: `site-packages/websockets/asyncio/compatibility.py`

**Reason:** Python 3.14's `asyncio.timeout()` requires running inside a Task context. The bundled `async_timeout` in websockets doesn't have this restriction.

**Original Code:**
```python
if sys.version_info[:2] >= (3, 11):
    from asyncio import timeout as asyncio_timeout
```

**Patched Code:**
```python
if sys.version_info[:2] >= (3, 11):
    if sys.version_info[:2] >= (3, 14):
        # Python 3.14: asyncio.timeout requires task context, use bundled async_timeout
        from .async_timeout import timeout as asyncio_timeout
    else:
        from asyncio import timeout as asyncio_timeout
```

---

### File: `site-packages/websockets/asyncio/async_timeout.py`

**Reason:** The bundled `async_timeout` has an assertion that `self._task is not None`. In Python 3.14, when running outside a Task context, `asyncio.current_task()` returns `None`, causing an `AssertionError`.

**Original Code:**
```python
def _on_timeout(self) -> None:
    assert self._task is not None
    self._task.cancel()
```

**Patched Code:**
```python
def _on_timeout(self) -> None:
    if self._task is not None:
        self._task.cancel()
    self._state = _State.TIMEOUT
```

---

## 2. `cdp_use` Library

### File: `site-packages/cdp_use/client.py`

**Reason:** 
1. Disable `open_timeout` in `websockets.connect()` to avoid `asyncio.timeout()` usage
2. Add connection test with `Browser.getVersion` to verify CDP is working
3. Add detailed logging for debugging CDP communication issues

**Patched `start()` method (around line 269):**
```python
async def start(self):
    """Start the WebSocket connection and message handler task"""
    if self.ws is not None:
        raise RuntimeError("Client is already started")

    print(f"[CDP-CONNECT] Connecting to WebSocket URL: {self.url}")
    connect_kwargs = {
        "max_size": self.max_ws_frame_size,
        # Python 3.14: avoid asyncio.timeout in websockets by disabling open_timeout
        "open_timeout": None,
    }
    if self.additional_headers:
        connect_kwargs["additional_headers"] = self.additional_headers
    self.ws = await websockets.connect(self.url, **connect_kwargs)
    print(f"[CDP-CONNECT] WebSocket connected to {self.url}")
    self._message_handler_task = asyncio.create_task(self._handle_messages())
    print(f"[CDP-CONNECT] Message handler task created: {self._message_handler_task}")
    
    # Test the connection with a simple Browser.getVersion call
    try:
        print("[CDP-CONNECT] Testing connection with Browser.getVersion...")
        version = await self.send_raw("Browser.getVersion")
        print(f"[CDP-CONNECT] Connection test successful! Browser: {version.get('product', 'unknown')}")
    except Exception as e:
        print(f"[CDP-CONNECT] Connection test FAILED: {e}")
        # Re-raise to signal connection failure
        raise RuntimeError(f"CDP connection test failed: {e}") from e
```

**Patched `_handle_messages()` method (around line 319):**
```python
async def _handle_messages(self):
    """Continuously handle incoming messages"""
    print("[CDP] _handle_messages task started")
    try:
        while True:
            if not self.ws:
                print("[CDP] _handle_messages: ws is None, breaking")
                break

            # Simply await recv() - websockets library handles this properly
            raw = await self.ws.recv()
            print(f"[CDP] Received raw message: {raw[:200]}..." if len(raw) > 200 else f"[CDP] Received raw message: {raw}")
            data = json.loads(raw)

            # Handle response messages (with id)
            if "id" in data:
                msg_id = data["id"]
                logger.debug(f"[CDP] Message has id={msg_id} (type={type(msg_id).__name__}), pending_requests keys: {list(self.pending_requests.keys())[:5]}")
                if msg_id in self.pending_requests:
                    logger.debug(f"[CDP] Received response for id={msg_id}, resolving future")
                    future = self.pending_requests.pop(msg_id)
                    # Check if future is already done to avoid InvalidStateError
                    if not future.done():
                        if "error" in data:
                            logger.debug(f"CDP Error for request {msg_id}: {data['error']}")
                            future.set_exception(RuntimeError(data["error"]))
                        else:
                            future.set_result(data["result"])
                    else:
                        logger.warning(f"[CDP] Future for id={msg_id} already done - ignoring")
                else:
                    logger.warning(f"[CDP] Received response for unknown id={msg_id}, not in pending_requests")

            # Handle event messages (without id, but with method)
            elif "method" in data:
                method = data["method"]
                params = data.get("params", {})
                session_id = data.get("sessionId")

                # Call registered event handler if available
                handled = await self._event_registry.handle_event(method, params, session_id)
                if not handled:
                    pass

            # Handle unexpected messages
            else:
                logger.warning(f"Received unexpected message: {data}")

    except websockets.exceptions.ConnectionClosed as e:
        logger.debug(f"WebSocket connection closed: {e}")
        # Connection closed, resolve all pending futures with an exception
        for future in self.pending_requests.values():
            if not future.done():
                future.set_exception(ConnectionError("WebSocket connection closed"))
        self.pending_requests.clear()
    except Exception as e:
        logger.error(f"Error in message handler: {e}")
        # Handle other exceptions
        for future in self.pending_requests.values():
            if not future.done():
                future.set_exception(e)
        self.pending_requests.clear()
```

---

## 3. `bubus` Library

### File: `site-packages/bubus/models.py`

**Reason:** Replace `asyncio.wait_for()` with polling loop in `event_results_filtered()` method for Python 3.14 compatibility.

**Patched `event_results_filtered()` method (around line 474):**
```python
async def event_results_filtered(
    self,
    timeout: float | None = None,
    include: EventResultFilter = _event_result_is_truthy,
    raise_if_any: bool = True,
    raise_if_none: bool = True,
) -> 'dict[PythonIdStr, EventResult[T_EventResultType]]':
    """Get all results filtered by the include function"""

    # wait for all handlers to finish processing
    assert self.event_completed_signal is not None, 'EventResult cannot be awaited outside of an async context'
    # Python 3.14 fix: asyncio.wait_for/timeout requires task context
    # Use polling loop with asyncio.sleep instead
    _timeout = timeout or self.event_timeout
    print(f'[BUBUS] event_results_filtered: waiting for {self.event_type}#{self.event_id[-4:]}, timeout={_timeout}, results={len(self.event_results)}')
    if _timeout is not None:
        _start = asyncio.get_event_loop().time()
        _last_log = 0
        while not self.event_completed_signal.is_set():
            _elapsed = asyncio.get_event_loop().time() - _start
            if _elapsed >= _timeout:
                pending = [f'{r.handler_name}:{r.status}' for r in self.event_results.values() if r.status not in ('completed', 'error')]
                print(f'[BUBUS] event_results_filtered TIMEOUT: {self.event_type}#{self.event_id[-4:]}, pending handlers: {pending}')
                raise asyncio.TimeoutError()
            # Log every 5 seconds
            if _elapsed - _last_log >= 5.0:
                pending = [f'{r.handler_name}:{r.status}' for r in self.event_results.values() if r.status not in ('completed', 'error')]
                print(f'[BUBUS] event_results_filtered: waiting {_elapsed:.1f}s for {self.event_type}#{self.event_id[-4:]}, pending: {pending}')
                _last_log = _elapsed
            await asyncio.sleep(0.01)
    else:
        await self.event_completed_signal.wait()
    print(f'[BUBUS] event_results_filtered: {self.event_type}#{self.event_id[-4:]} completed!')
    
    # ... rest of method unchanged
```

---

### File: `site-packages/bubus/service.py`

**Reason:** Replace `asyncio.wait_for()` with polling loop in `execute_handler()` method for Python 3.14 compatibility.

**Patched `execute_handler()` method (around line 1144):**
```python
handler_task = None
try:
    if inspect.iscoroutinefunction(handler):
        # Create a task for the handler so we can properly cancel it on timeout
        handler_task = asyncio.create_task(handler(event))  # type: ignore
        # Python 3.14: avoid asyncio.wait_for (requires task context)
        if event_result.timeout is not None:
            start_time = asyncio.get_event_loop().time()
            _last_log = 0
            while not handler_task.done():
                _elapsed = asyncio.get_event_loop().time() - start_time
                if _elapsed >= event_result.timeout:
                    handler_task.cancel()
                    raise asyncio.TimeoutError()
                if _elapsed - _last_log >= 5.0:
                    print(f'[BUBUS] Handler {get_handler_name(handler)}#{handler_id[-4:]} still running after {_elapsed:.1f}s')
                    _last_log = _elapsed
                await asyncio.sleep(0.01)
        result_value: Any = await handler_task
    elif inspect.isfunction(handler) or inspect.ismethod(handler):
        # If handler function is sync function, run it directly in the main thread
        result_value: Any = handler(event)

        # If the sync handler returned a BaseEvent (from dispatch), DON'T await it
        if isinstance(result_value, BaseEvent):
            logger.debug(
                f'Handler {get_handler_name(handler)} returned BaseEvent, not awaiting to avoid circular dependency'
            )
    else:
        raise ValueError(f'Handler {get_handler_name(handler)} must be a sync or async function, got: {type(handler)}')

    print(f'[BUBUS] Handler {get_handler_name(handler)}#{handler_id[-4:]} returned: {type(result_value).__name__}')
    # Cancel the monitor task since handler completed successfully
    monitor_task.cancel()

    # Record successful result
    print(f'[BUBUS] Calling event_result_update for {get_handler_name(handler)}#{handler_id[-4:]} with result')
    event.event_result_update(handler=handler, eventbus=self, result=result_value)
    print(f'[BUBUS] event_result_update completed for {get_handler_name(handler)}#{handler_id[-4:]}')
    # ... rest of method
```

---

## 4. `browser_use` Library

### File: `site-packages/browser_use/browser/session_manager.py`

**Reason:** Replace `asyncio.wait_for()` with polling loops in `ensure_valid_focus()` method (2 locations).

**Patched `ensure_valid_focus()` method (around line 288):**
```python
async def ensure_valid_focus(self, timeout: float = 3.0) -> bool:
    """Ensure agent_focus_target_id points to a valid, attached CDP session."""
    if not self.browser_session.agent_focus_target_id:
        # No focus at all - might be initial state or complete failure
        if self._recovery_in_progress and self._recovery_complete_event:
            # Recovery is happening, wait for it
            # Python 3.14 fix: use polling loop instead of asyncio.wait_for
            try:
                _recovery_start = asyncio.get_event_loop().time()
                while not self._recovery_complete_event.is_set():
                    if asyncio.get_event_loop().time() - _recovery_start > timeout:
                        raise TimeoutError()
                    await asyncio.sleep(0.01)
                # Check again after recovery - simple existence check
                focus_id = self.browser_session.agent_focus_target_id
                return bool(focus_id and self._get_session_for_target(focus_id))
            except TimeoutError:
                self.logger.error(f'[SessionManager] ❌ Timed out waiting for recovery after {timeout}s')
                return False
        return False

    # ... middle section unchanged ...

    # Wait for recovery complete event
    # Python 3.14 fix: use polling loop instead of asyncio.wait_for
    if self._recovery_complete_event:
        try:
            start_time = asyncio.get_event_loop().time()
            while not self._recovery_complete_event.is_set():
                if asyncio.get_event_loop().time() - start_time > timeout:
                    raise TimeoutError()
                await asyncio.sleep(0.01)
            elapsed = asyncio.get_event_loop().time() - start_time

            # Verify recovery succeeded - simple existence check
            focus_id = self.browser_session.agent_focus_target_id
            if focus_id and self._get_session_for_target(focus_id):
                self.logger.info(
                    f'[SessionManager] ✅ Agent focus recovered to {self.browser_session.agent_focus_target_id[:8]}... '
                    f'after {elapsed * 1000:.0f}ms'
                )
                return True
            else:
                self.logger.error(
                    f'[SessionManager] ❌ Recovery completed but focus still invalid after {elapsed * 1000:.0f}ms'
                )
                return False

        except TimeoutError:
            # ... timeout handling
```

---

### File: `site-packages/browser_use/browser/watchdogs/dom_watchdog.py`

**Reason:** Replace `asyncio.wait_for()` with polling loops in `on_BrowserStateRequestEvent()` handler (2 locations for getting page title and page info).

**Patched code for getting page title (around line 423):**
```python
# Get target title safely
# Python 3.14 fix: use polling loop instead of asyncio.wait_for
try:
    self.logger.debug('🔍 DOMWatchdog.on_BrowserStateRequestEvent: Getting page title...')
    _title_task = asyncio.create_task(self.browser_session.get_current_page_title())
    _title_start = time.time()
    while not _title_task.done():
        if time.time() - _title_start > 1.0:
            _title_task.cancel()
            raise asyncio.TimeoutError()
        await asyncio.sleep(0.01)
    title = _title_task.result()
    self.logger.debug(f'🔍 DOMWatchdog.on_BrowserStateRequestEvent: Got title: {title}')
except Exception as e:
    self.logger.debug(f'🔍 DOMWatchdog.on_BrowserStateRequestEvent: Failed to get title: {e}')
    title = 'Page'
```

**Patched code for getting page info (around line 440):**
```python
# Get comprehensive page info from CDP with timeout
# Python 3.14 fix: use polling loop instead of asyncio.wait_for
try:
    self.logger.debug('🔍 DOMWatchdog.on_BrowserStateRequestEvent: Getting page info from CDP...')
    _page_info_task = asyncio.create_task(self._get_page_info())
    _page_info_start = time.time()
    while not _page_info_task.done():
        if time.time() - _page_info_start > 1.0:
            _page_info_task.cancel()
            raise asyncio.TimeoutError()
        await asyncio.sleep(0.01)
    page_info = _page_info_task.result()
    self.logger.debug(f'🔍 DOMWatchdog.on_BrowserStateRequestEvent: Got page info from CDP: {page_info}')
except Exception as e:
    self.logger.debug(
        f'🔍 DOMWatchdog.on_BrowserStateRequestEvent: Failed to get page info from CDP: {e}, using fallback'
    )
    # Fallback to default viewport dimensions
    viewport = self.browser_session.browser_profile.viewport or {'width': 1280, 'height': 720}
    page_info = PageInfo(
        viewport_width=viewport['width'],
        viewport_height=viewport['height'],
        page_width=viewport['width'],
        page_height=viewport['height'],
        scroll_x=0,
        scroll_y=0,
        pixels_above=0,
        pixels_below=0,
        pixels_left=0,
        pixels_right=0,
    )
```

---

## 5. Double-Pass Fix in eCan.ai Application Code

### File: `agent/ec_skills/build_node.py`

**Reason:** LangGraph was entering nodes twice during resume operations, causing duplicate `BrowserStateRequestEvent` dispatches. One event would complete successfully, but the other would timeout waiting for a handler that never ran.

**Added module-level lock and set (around line 3010):**
```python
# Module-level lock and cache for preventing duplicate passive command execution
import asyncio as _asyncio_module
_passive_steps_lock = _asyncio_module.Lock()
_passive_steps_processed: set[str] = set()
```

**Added guard in `_run_browser_use()` function (around line 3311):**
```python
if passive_enabled:
    try:
        from agent.ec_skills.browser_use_extension.passive_agent import PassiveAgent

        # Guard against double-execution: check if this step_id was already processed
        # Use module-level lock and set to prevent race condition
        global _passive_steps_lock, _passive_steps_processed
        
        passive_cmd_check = None
        if isinstance(state, dict):
            attrs_check = state.get("attributes", {})
            passive_cmd_check = attrs_check.get("passive_command")
        
        # Build step_key from passive_command or fall back to node_name + run_id
        step_key = None
        if isinstance(passive_cmd_check, dict):
            step_id_check = passive_cmd_check.get("step_id", "")
            run_id_check = passive_cmd_check.get("run_id", "")
            step_key = f"{run_id_check}:{step_id_check}"
        else:
            # Fallback: use node_name + run_id from state.attributes
            if isinstance(state, dict):
                attrs = state.get("attributes", {})
                run_id_fallback = attrs.get("run_id", "")
                if run_id_fallback:
                    step_key = f"{run_id_fallback}:{node_name}"
        
        if step_key:
            async with _passive_steps_lock:
                if step_key in _passive_steps_processed:
                    logger.info(f"[BrowserAutomation] Skipping duplicate execution for step: {step_key}")
                    return {"passive": True, "skipped": True, "reason": "duplicate_execution"}
                
                # Mark this step as being processed (inside lock to prevent race condition)
                _passive_steps_processed.add(step_key)
                logger.info(f"[BrowserAutomation] Processing step: {step_key}")
                # Limit cache size to prevent memory leak
                if len(_passive_steps_processed) > 1000:
                    # Remove oldest entries (convert to list, slice, convert back)
                    _passive_steps_processed = set(list(_passive_steps_processed)[-500:])
        else:
            logger.warning(f"[BrowserAutomation] No step_key available for duplicate detection, proceeding anyway")

        # ... rest of passive mode execution
```

---

## Summary of All Patched Files

| Library | File | Lines Modified | Reason |
|---------|------|----------------|--------|
| `websockets` | `asyncio/compatibility.py` | ~5 | Use bundled async_timeout on Python 3.14+ |
| `websockets` | `asyncio/async_timeout.py` | ~3 | Handle `_task is None` in `_on_timeout()` |
| `cdp_use` | `client.py` | ~50 | Disable open_timeout, add connection test, add debug logging |
| `bubus` | `models.py` | ~25 | Replace `asyncio.wait_for()` with polling loop |
| `bubus` | `service.py` | ~30 | Replace `asyncio.wait_for()` with polling loop, add debug logging |
| `browser_use` | `browser/session_manager.py` | ~30 | Replace `asyncio.wait_for()` with polling loops (2 locations) |
| `browser_use` | `browser/watchdogs/dom_watchdog.py` | ~40 | Replace `asyncio.wait_for()` with polling loops (2 locations) |
| eCan.ai | `agent/ec_skills/build_node.py` | ~40 | Add module-level guard against double-pass execution |
