# Debugging eCan — environment variables & techniques

A catalogue of the env vars and built-in instrumentation useful when diagnosing
problems — memory growth, thread leaks, CDP/browser stalls, the Feige
front-desk flood path, hangs, and noisy/quiet logging.

> Most of these are **diagnostic / tuning knobs that are *off* or at a safe
> default in production** — turn one on for a single repro run, then turn it
> back off.  None of them change the message-handling logic; they change
> instrumentation, timeouts, and thresholds.

## Setting an env var

```bat
:: Windows cmd.exe — set, then launch eCan in the same shell
set ECAN_TRACEMALLOC=1
"C:\Users\<you>\AppData\Local\eCan\eCan.exe"
```
```powershell
# PowerShell
$env:ECAN_TRACEMALLOC = "1"; & "C:\Users\<you>\AppData\Local\eCan\eCan.exe"
```
Or put `ECAN_TRACEMALLOC=1` in the project `.env` (dev runs) — but **don't
leave the heavy ones (`ECAN_TRACEMALLOC`) on permanently**: tracemalloc adds
~10–25 % allocation overhead plus memory for the traces.

## Log files (where to look first)

| File | What's in it |
|---|---|
| `runlogs/eCan.log` | Main app log. Look here for `[CDP-EVAL]`, `[FEIGE-LEDGER]`, `[DIRECT-DELIVERY]`, `HOT-PATH-B`, `[BrowserAutomation]`, errors. Rotates. |
| `runlogs/memory.log` | RSS / VMS / thread-count timeline, `thread-baseline` / `thread-census` / `thread-delta tick` / `thread-leak suspects`, and `tracemalloc diff` blocks (when enabled). Rotating, 20 MB × 3 backups. See `docs/MEMORY_MONITOR.md`. |
| `runlogs/browser_console.log` | Chrome's JS console (from the browser-use session). Rotating. |
| `runlogs/lightrag.log` | The LightRAG knowledge-base server (`rag_query` backend) — query keyword extraction, retrieval counts, rerank warnings, `uvicorn.access` for `POST /query`. |

`[FEIGE-LEDGER]` lines are structured JSON — grep `"stage": "..."` to follow a
customer's message through `dom_observed → runner_chat_message_routed →
send_chat_called → direct_reply_received → feige_send_tool_start →
feige_send_tool_success / direct_sent_and_cleaned` (or `…_failed` /
`stale_reply_source_msg_id` / `direct_stale_dropped`).

---

## Memory & threads

| Var | Default | Effect |
|---|---|---|
| `ECAN_TRACEMALLOC` | `0` | `=1` starts `tracemalloc` (8 frames) and writes a top-15 "growing allocations by file:line" diff to `memory.log` every 120 s — the way to find *what* is holding RSS. Heavy; one repro run only. |
| `ECAN_TRACEMALLOC_BASELINE_EVERY` | `5` | When tracemalloc is on, also emit a `tracemalloc diff (vs baseline)` (total growth since process start, not just incremental) every Nth snapshot. |
| `ECAN_THREAD_CENSUS_EVERY_CHECKS` | `20` | Re-log the **full** thread breakdown (`thread-census (N total): …`) every Nth memory check (≈ every 10 min at the 30 s check interval) — so `memory.log` always has a recent complete thread map, not only deltas. The per-change `thread-delta tick` and the ≥5-since-start `[MemoryMonitor] thread-leak suspects` warning are always on regardless. |
| `ECAN_RSS_LIVE_CHAT_PROTECT_MB` | `6000` | When RSS crosses this, the monitor cools the live-chat CDP path + releases browser-cache pressure + GCs (once). Legacy `ECAN_RSS_FEIGE_PROTECT_MB` still honored. |
| `ECAN_RSS_PROTECT_MB` | `7500` | When RSS crosses this, run self-protection cleanup (release browser caches, GC). |
| `ECAN_RSS_CRITICAL_MB` | `9000` | Same, more aggressive. |

Reading `memory.log` thread lines: `thread-baseline (N total): cat=N, …` at
startup is "normal"; `thread-delta tick` shows what changed; `thread-census`
is the periodic full picture; `[MemoryMonitor] thread-leak suspects` (also
echoed to `eCan.log`) fires when a category has ≥5 more live threads than at
startup — the leak alarm. Note: ~290 threads under a 10-agent deployment is the
*expected* baseline (each agent ≈ an asyncio-loop thread + a `MemoryMgr-agent_*`
thread + an `wan_a2a` channel thread, plus shared pools `asyncio:~22`,
`SkillExec:~9`, `ThreadPoolExecutor-2:~9`); it's only a problem if a category
*keeps growing*.

The Feige image cache (raw bytes for `feige-img:` refs sent into LLM prompts)
is bounded — see `ECAN_FEIGE_IMAGE_REF_MAX` / `ECAN_FEIGE_IMAGE_REF_TTL_S`
below — so it isn't an unbounded leak source.

---

## CDP / browser-use tracing

| Var | Default | Effect |
|---|---|---|
| `ECAN_CDP_EVALUATE_TRACE_ALL` | `0` | `=1` logs a `[CDP-EVAL]` line for **every** `Runtime.evaluate` call (not just slow / timed-out / `feige_*` ones). Very verbose; use briefly. |
| `ECAN_CDP_EVALUATE_TRACE_SLOW_MS` | `500` | A `[CDP-EVAL]` line is emitted when an eval takes longer than this many ms (besides always logging timeouts, errors, cross-loop, and `feige_*`). Lower it to catch borderline-slow evals. |
| `ECAN_CDP_RUNTIME_ENABLE_BEFORE_EVALUATE` | `0` | `=1` sends `Runtime.enable` before each `Runtime.evaluate` (diagnostic for "context not found" cases). |
| `ECAN_DOM_DEBUG` | `0` | `=1` in the event monitor: slows the DOM poll to 5 s and dumps the compact page-text it sees each tick — for diagnosing "the monitor isn't seeing the customer's message". |
| `ECAN_QTWEBENGINE_REMOTE_DEBUGGING` | unset | Port for Chrome DevTools remote debugging of the embedded WebEngine view (also reads the standard `QTWEBENGINE_REMOTE_DEBUGGING`). Then open `http://localhost:<port>` in another Chrome to inspect. |
| `ECAN_ICON_DEBUG` | unset | Verbose logging for window/taskbar icon resolution. |

`[CDP-EVAL]` fields worth knowing: `phase` (`get_or_create_cdp_session` /
`Runtime.enable` / `Runtime.evaluate` / `cdp_operation_lock_wait` / `complete`),
`session_ms` (CDP-session resolution time — ~3 s here usually means the
`ensure_valid_focus` round-trip), `runtime_evaluate_ms` (the JS execution time
in the renderer), `lock_wait_ms` / `blocked_by` / `lock_held_ms` (per-session
operation-lock contention), `cross_loop` (the CDP handler task is on a different
event loop than the caller). Distinct WARN tags: `[CDP-EVAL][LOCK-CONTENTION]`
(timed out waiting for the operation lock — renderer is fine, a holder is slow),
`[CDP-EVAL][READ-ONLY-TIMEOUT]` (a read-only scrape timed out — caller falls
back, session not invalidated), `[CDP-EVAL][RENDERER-SLOW]` (an eval timed out
in the `Runtime.evaluate` phase — renderer too slow; cooldown applied but the
session is *not* invalidated).

---

## CDP / Feige timeouts & recovery thresholds

These shape how the Feige front-desk behaves under a flood of chat messages —
how long an eval can run before it's a timeout, how many timeouts before a
cooldown/circuit/session-recovery kicks in. Defaults below are the
flood-hardened values (2026-05-11).

| Var | Default | Effect |
|---|---|---|
| `ECAN_CDP_EVALUATE_TIMEOUT_S` | `6.0` | Per-eval hard timeout for non-`feige_*` evals (DOM scrapes, generic browser-use `evaluate`). |
| `ECAN_FEIGE_CDP_EVALUATE_TIMEOUT_S` | `12.0` | Per-eval timeout for `feige_*`-labelled evals that don't set their own (`feige_open_session`, `feige_list_sessions`, `feige_get_chat_thread`, `feige_scrape_bubble`, …) — more generous because they can eat a contended CDP-session setup. |
| `ECAN_FEIGE_SEND_CDP_EVALUATE_TIMEOUT_S` | `15.0` | Per-eval timeout for `feige_send_message` (its JS is ~17 KB and types + clicks + polls the DOM). |
| `ECAN_MONITOR_CDP_EVALUATE_TIMEOUT_S` | `3.0` | Per-eval timeout for the event monitor's polling evals. |
| `ECAN_HOT_PATH_TOOL_TIMEOUT_S` | `8.0` | Per-tool timeout inside the HOT-PATH-B direct-delivery executor. |
| `ECAN_FEIGE_TARGET_RESOLVE_TIMEOUT_S` | `2.0` | Bounded timeout for resolving "which Chrome tab is the Feige tab". |
| `ECAN_CDP_EVALUATE_RECOVERY_THRESHOLD` | `3` | Non-`feige_*` `Runtime.evaluate` *setup-phase* timeouts before the shared `BrowserSession` is invalidated for recovery. (Renderer-slow `Runtime.evaluate` timeouts no longer count — see `[CDP-EVAL][RENDERER-SLOW]`.) |
| `ECAN_FEIGE_CDP_EVALUATE_RECOVERY_THRESHOLD` | `3` | Same, for `feige_*` evals. (Bumped from 1 — one slow send must not nuke the shared session and strand every queued delivery.) |
| `ECAN_FEIGE_CDP_HEALTH_COOLDOWN_S` | `4.0` | After a `feige_*` eval times out, reject subsequent feige sends for this many seconds (back-off for a slow renderer). |
| `ECAN_FEIGE_SEND_CDP_TIMEOUT_COOLDOWN_S` | `3.0` | Like above but specific to `feige_send_message` CDP timeouts. |
| `ECAN_LIVE_CHAT_SHUTDOWN_DRAIN_TIMEOUT_S` | `15.0` | On app exit, how long to wait for in-flight Feige deliveries to drain. |
| `ECAN_LIVE_CHAT_SHUTDOWN_FALLBACK_WAIT_S` | `3.0` | Extra wait for fallback-path deliveries during shutdown. |
| `ECAN_FEIGE_IMAGE_REF_MAX` | `256` | Max number of `feige-img:` image-byte entries kept in the in-memory store (LRU). |
| `ECAN_FEIGE_IMAGE_REF_TTL_S` | `600` | TTL for `feige-img:` entries (10 min). Images sent into a customer's chat are stripped to a `feige-img:` ref + URL + sha256 in the A2A message / history; the raw bytes live only in this bounded store and are re-resolved into the LLM prompt at call time. |

### HOT-PATH-B direct-delivery (the front-desk → customer reply path)

> 2026-08-01: the runner-side knobs were renamed to platform-neutral
> `DIRECT_LIVE_CHAT_*` / `ECAN_LIVE_CHAT_*` names as part of moving all
> Feige-specific code out of `ec_tasks/runner.py`.  The historical
> `DIRECT_FEIGE_*` / `ECAN_FEIGE_*` spellings still work — the runner's
> `_live_chat_env()` falls back to any legacy site-branded alias.

| Var | Default | Effect |
|---|---|---|
| `DIRECT_LIVE_CHAT_JOB_TIMEOUT_S` | `35.0` | Hard timeout for a single direct-delivery job (must exceed the send eval timeout + typing-lock wait). |
| `DIRECT_LIVE_CHAT_MAX_ASYNC_QUEUE_DEPTH` | `1` | How many direct-delivery jobs the worker accepts before back-pressuring (retaining the reply in the worker). |
| `DIRECT_LIVE_CHAT_BROWSER_SESSION_WAIT_S` | `5.0` | How long a direct-delivery job waits for the browser session to be ready. |
| `DIRECT_LIVE_CHAT_REQUEUE_LIMIT` | `1` | Max re-queues of a failed direct delivery before falling back to the front-desk agent. |
| `DIRECT_LIVE_CHAT_REQUEUE_DELAY_S` | `0.75` | Delay before a direct-delivery re-queue. |
| `DIRECT_LIVE_CHAT_CDP_COOLDOWN_REQUEUE_LIMIT` | `0` | Re-queues allowed while a Feige-CDP cooldown is active (0 = none → fall back instead). |
| `DIRECT_LIVE_CHAT_CDP_COOLDOWN_RETRY_BUFFER_S` | `0.25` | Extra wait after a cooldown expires before retrying. |
| `DIRECT_LIVE_CHAT_CDP_TIMEOUT_DELAY_CAP_S` | `20.0` | Cap on the back-off delay for CDP-timeout re-queues. |
| `DIRECT_LIVE_CHAT_CDP_TIMEOUT_CIRCUIT_THRESHOLD` | `2` | Consecutive `feige_send_message` CDP timeouts before opening the direct-delivery circuit (bypass HOT-PATH-B fleet-wide for the cooldown). Bumped from 1. |
| `DIRECT_LIVE_CHAT_CDP_TIMEOUT_CIRCUIT_COOLDOWN_S` | `6.0` | How long the direct-delivery circuit stays open. Reduced from 20. |
| `DIRECT_LIVE_CHAT_CDP_TIMEOUT_CIRCUIT_QUEUE_BYPASS` | `0` | `=1` lets queued deliveries bypass even while the circuit is open. |
| `DIRECT_LIVE_CHAT_FOCUS_RETRIES` / `DIRECT_LIVE_CHAT_FOCUS_RETRY_DELAY_S` | `2` / `0.5` | Retries (and delay) for the focus step in direct delivery. |
| `DIRECT_LIVE_CHAT_MAX_RETRIES` / `DIRECT_LIVE_CHAT_RETRY_DELAY_S` / `DIRECT_LIVE_CHAT_TASK_IDLE_WAIT_S` | — | Other direct-delivery retry knobs. |
| `RUNNING_TASK_BLOCKED_CLEAR_SEC` | `300` | If a task stays `working` with a running future for this long, the queue pump force-clears it (zombie/blocked-task recovery). |

---

## LLM / skill execution

| Var | Default | Effect |
|---|---|---|
| `ECAN_ASYNC_LLM` | `true` | Use the async LLM invocation path in LLM nodes. Set `0` to force the sync path (diagnostic). |
| `ECAN_ASYNC_EXECUTION` | — | Toggle async skill execution. |
| `ECAN_NATIVE_TOOL_CALLS` | `0` | `=1` uses provider-native tool-call format instead of the JSON-in-text bridge (also per-skill via `mapping_rules`). |
| `ECAN_LLM_TIMEOUT_SEC` | — | Per-LLM-call timeout (the `llm-async-timeout-*` watchdog threads). |
| `ECAN_SKILL_WORKERS` / `ECAN_SKILL_MAX_QUEUED` | — | Skill-execution thread-pool size / queue cap. |
| `ECAN_MCP_MAX_CONCURRENT_SESSIONS` / `ECAN_MCP_SESSION_TIMEOUT_SEC` | — | MCP server session pool size / idle timeout. |
| `ECAN_SKILL_EDITOR_LOG_MAX_CHARS` | — | Truncation length for skill-editor state-summary log lines. |

## Hooks / discovery

| Var | Default | Effect |
|---|---|---|
| `ECAN_DISABLE_EXTERNAL_HOOK_DISCOVERY` | `0` | `=1` turns off auto-discovery of external hook bundles (e.g. if a bad bundle is breaking startup). |
| `ECAN_EXTRA_HOOK_DIRS` | — | Extra directories to scan for hook bundles (`;`-separated). |
| `ECAN_BROWSER_IDLE_SHUTDOWN_DELAY` | `60` | Seconds a browser slot can sit idle before the manager shuts it down. Raise it if browsers are being recycled too eagerly during a test. |

## Logging verbosity & mode

| Var | Default | Effect |
|---|---|---|
| `ECAN_LOG_LEVEL` | `INFO` (prod) | Set `DEBUG` for verbose logging, `WARNING` to quiet it. |
| `ECAN_MODE` | `desktop` | `web` runs the FastAPI/WebSocket server (`web_server.py`); `cli` the CLI. |
| `ECAN_CRASH_HEARTBEAT_INTERVAL_S` | — | How often the crash-boundary heartbeat thread ticks (it records the last "phase" so a crash log shows where it died). |
| `ECAN_RUN_ID` | auto | Tag for correlating logs across a run. |

> Not listed: deployment/wiring vars (`ECAN_SQS_QUEUE_URL`, `ECAN_SKILLS_BUCKET`,
> `ECAN_WS_URL`, `ECAN_LOCAL_SERVER_HOST/PORT`, `ECAN_USER*`, `ECAN_WORKER_*`,
> `ECAN_CLOUD_MODE`, `ECAN_SALES_DB_PATH`, …) and build vars (`DEV_WIN_CERT_*`,
> `TARGET_ARCH`, …) — those configure where things run, not how to debug them.
> `grep -rn 'os.getenv("ECAN_' --include="*.py"` for the full set.

---

## Debugging a hang / deadlock (no env var — the app is wedged and not logging)

When `eCan.log` / `memory.log` stop being written to but the process is still
alive (a log-rotation `WinError 32 "being used by another process"` is a tell —
the process holds the file open), it's a deadlock or a cross-loop wait. Capture
a stack dump **before** killing it:

- **`py-spy` (best, no app cooperation needed):** `pip install py-spy`, then
  `py-spy dump --pid <eCan_pid>` — prints a Python traceback of every thread,
  including which lock/await each is parked on.
- **Ctrl+Break in the eCan console window** (Windows dev builds with a console):
  Python turns `SIGBREAK` into a traceback dump of all threads to stderr.
- **`faulthandler`** is installed at startup, so `kill -SIGABRT <pid>` style
  signals (or a crash) also dump tracebacks — check the crash log.

Then look for two threads each holding a lock the other needs (common
candidates here: the per-session CDP operation lock, the Feige typing lock, the
browser startup lock, `run_coroutine_threadsafe` waits between the runner loop
and the `LiveChatDirectDelivery` loop).

## A typical "the flood test stalled" investigation

1. `runlogs/eCan.log`: grep `[FEIGE-LEDGER]` for the customer — did `dom_observed` → `runner_chat_message_routed` → `send_chat_called` → `direct_sent_and_cleaned` complete, or did it stop at `feige_send_tool_failed` / `stale_reply_source_msg_id` / `direct_stale_dropped`?
2. Check for `Invalidated cached BrowserSession`, `missing_browser_session`, `browser-use run failed: CancelledError`, `CDP health cooldown active`, `direct_cdp_timeout_circuit_opened`, `HOT-PATH-B: ABORT`, `Input cleared but outgoing bubble not observed` — these are the cascade markers.
3. `[CDP-EVAL]` lines: is `session_ms` ~3000 (focus-tax) or `runtime_evaluate_ms` high (renderer slow)? Any `[CDP-EVAL][RENDERER-SLOW]`?
4. `runlogs/memory.log`: did RSS spike / threads climb / a `thread-leak suspects` warning fire?
5. `runlogs/lightrag.log`: did `POST /query` requests keep returning 200, or did the RAG server stop logging?
6. If the *process itself* is wedged: get a `py-spy dump` before restarting — that's the one piece of evidence a restart destroys.

> Operational hygiene for flood tests: restart eCan **and** kill `chrome.exe`
> first (a fresh renderer; `browser_session.start()` can take 30 s × 2 if the
> reused Chrome has dozens of leftover tabs), and reset the customer-service
> site's chat histories (accumulated message threads make every DOM scrape /
> send slower run-over-run).
