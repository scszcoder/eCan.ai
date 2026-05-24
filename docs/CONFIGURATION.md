# eCan.ai Configuration Reference

This document covers the runtime knobs that aren't part of the GUI's
**Settings** page. Most are tuning parameters added during incident
post-mortems — defaults are calibrated for typical workloads and only
need touching when you're chasing a specific symptom.

There are three places configuration lives:

| Location | Use for |
|---|---|
| GUI **Settings → General/LLM/...** | User-facing prefs (API keys, default model, paths) |
| `resource/data/settings.json` (per-user) | Same as above, persisted |
| Environment variables (`ECAN_*`) | Tuning knobs, test flags, build/deploy switches |

The GUI settings are documented in-line in the UI. The rest of this file
documents the environment variables.

---

## LLM & history

### `ECAN_MCP_RESULT_HISTORY_CAP`

- **Default:** `24000` (chars)
- **Purpose:** Truncate large MCP tool results (notably `rag_query`
  knowledge-graph dumps) before they're appended to the chat history that
  gets re-sent to the LLM on every turn.
- **Trade-off:** Larger values retain more product/RAG context for
  follow-up questions, but inflate prompt tokens turn-over-turn. The
  default 24KB retains the top 6-10 entries of a typical RAG result.
- **When to change:** If response quality regresses on long
  conversations because the bot has "forgotten" specific product
  details, raise to 48000 or 64000. If RSS / token cost is the
  bottleneck, lower to 12000 or 8000.
- **History:** Introduced 2026-05-13 at 8000 (RSS-spike mitigation),
  raised to 24000 on 2026-05-15 after the customer reported quality
  regression.
- **Source:** `agent/ec_skills/build_node.py:_compact_mcp_result_for_history`

### `ECAN_TASK_TEXT_HISTORY_CAP`

- **Default:** `400` (chars)
- **Purpose:** Truncate browser-use `task_instructions` before they're
  recorded in action history. The verbatim copy serves no downstream
  purpose — the browser-use agent already consumed it.
- **When to change:** Leave alone unless you're debugging a specific
  flowgram where the historical task text matters.
- **Source:** `agent/ec_skills/build_node.py:_compact_task_text_for_history`

### `ECAN_LLM_TIMEOUT_SEC`

- **Default:** `45.0` (seconds)
- **Purpose:** Hard ceiling for a single LLM `ainvoke` HTTP call.
  Two timeouts use this value:
  1. The inner `asyncio.wait_for(llm.ainvoke, timeout=ECAN_LLM_TIMEOUT_SEC)`
     fires when the **HTTP request itself** hangs. Logged as
     `⏱️ LLM async request timed out after ...s`.
  2. The outer worker wall-clock = `ECAN_LLM_TIMEOUT_SEC + 5.0` fires
     when the worker thread fails to signal completion in time. Logged
     as `⏱️ LLM async worker timed out after ...s`.
- **Retry behaviour:** Either timeout triggers ONE retry on a fresh
  worker thread + fresh event loop. If the second attempt also times
  out, the failure surfaces (and the dispatch is re-queued for the
  next cycle).
- **When to change:**
  - **Lower** (e.g. `30`) only if you're willing to fail-fast on slow
    cloud responses. Most of the time the call succeeds within a few
    seconds; pulling the limit down doesn't help typical traffic.
  - **Raise** (e.g. `90`) if your provider/model genuinely needs more
    than 45s for some calls (very long contexts, slow regions). The
    customer's production runs show p90=5.3s, max=18.5s for healthy
    OpenAI HTTP calls, so 45s gives ample headroom.
- **mt035 (2026-05-24):** Earlier behaviour was: even when ainvoke
  *succeeded* within budget, the worker thread's event-loop teardown
  could hang on a saturated httpx pool, causing the outer wall-clock
  to fire and **discard the already-good response**. The customer's
  2026-05-24 09:25:50 packet 130cm turn cost 56 s of wall-clock for
  this reason (real LLM call: 18.5 s; cleanup hang: 32 s; retry: 4.6 s).
  mt035 moved `done.set()` to fire immediately after result capture so
  the caller is no longer at the mercy of teardown latency. Grep the
  log for `LLM async worker timed out` to confirm the issue is absent
  in your environment (post-mt035 should be near-zero in normal traffic).
- **Diagnostics:** every 15 s of waiting prints
  `[LLM-HEARTBEAT] ... still waiting for ainvoke after Xs`. If you
  see these AND a subsequent `LLM async worker timed out`, you're
  hitting the cleanup hang; consider whether mt035 is deployed.
- **Source:** `agent/ec_skills/build_node.py`
  (`_invoke_async_with_thread_timeout`, search for `mt035`)

---

## Feige CDP & send-message tuning

### `ECAN_FEIGE_SEND_CDP_EVALUATE_TIMEOUT_S`

- **Default:** `45.0` (seconds)
- **Purpose:** Hard ceiling on `Runtime.evaluate` for `feige_send_message`.
- **History:** 15 → 22 → 45 over 2026-05-12..14 as the renderer was
  observed to spend 7-10s under flood load; 45 gives headroom over a
  typical successful call.
- **Source:** `agent/ec_skills/browser_use_extension/extension_tools_service.py`

### `ECAN_HOT_PATH_TOOL_TIMEOUT_S`

- **Default:** `50.0` (seconds)
- **Purpose:** Outer Python timeout wrapping `feige_send_message`. Must
  stay strictly greater than the CDP evaluate timeout above so CDP
  returns its own error string before the wrapper cancels.
- **Source:** `agent/ec_skills/browser_use_extension/hooks/external/feige_chat/hot_path.py`

### `ECAN_FEIGE_SLOW_CDP_THRESHOLD_MS` / `_COUNT` / `_RECOVERY_COOLDOWN_S`

- **Defaults:** `6000` / `6` / `5.0`
- **Purpose:** If `N` consecutive CDP evals each take >`THRESHOLD_MS`,
  apply a `RECOVERY_COOLDOWN_S` pause to let the renderer breathe.
- **History:** Originally 3000/5/15 calibrated for the pre-optimization
  era when feige_send_message averaged 7-10s. Retuned 2026-05-14 after
  the source_guard short-circuit dropped the average to 2.7s — the old
  threshold was tripping inappropriately on normal 3-5s evals and
  causing 4+ minute round-2 stalls.
- **Source:** `agent/ec_skills/browser_use_extension/extension_tools_service.py:_record_feige_cdp_eval_timing`

### `ECAN_FEIGE_CDP_HEALTH_COOLDOWN_S`

- **Default:** `4.0`
- **Purpose:** Cooldown after the renderer is marked unhealthy via
  `mark_feige_cdp_unhealthy()`. Separate from the slow-CDP-consecutive
  recovery cooldown above.

### `ECAN_FEIGE_STALE_GAP_S`

- **Default:** `300.0` (seconds, i.e. 5 minutes)
- **Purpose:** Threshold for the **mt034 stale-guard time-gap
  relaxation**. When `feige_send_message`'s source guard would reject
  the bot's reply because the customer typed a new question after the
  one being answered (`stale_reason=older_bubble_match`), the gap
  between the target customer bubble and the latest customer bubble is
  computed from `placeholder_timer.get_message_first_seen`. If the gap
  is **less than or equal to** `ECAN_FEIGE_STALE_GAP_S`, the send is
  retried with `bypass_older_bubble_match=true` so the answer to the
  earlier question still gets typed.
- **Rationale:** Without the relaxation, a customer who fires two
  back-to-back questions causes the first answer to be silently
  discarded. The intent of the strict guard is to skip stale replies
  to abandoned questions — short gaps mean the customer is still
  engaged and the answer is still relevant.
- **When to change:**
  - **Lower** (e.g. `60`) for high-traffic shops where customers
    routinely ask many rapid follow-ups and a `bypassed` reply more
    than a minute late looks awkward. Trade-off: more answers
    discarded.
  - **Raise** (e.g. `600`) for low-traffic shops where back-to-back
    questions are rare and a late reply is still useful. Trade-off:
    increased risk of replying to a customer who's already moved on.
  - **Set to `0`** to disable the relaxation entirely and restore the
    pre-mt034 strict latest-only behaviour.
- **What it does NOT affect:** Replies are still discarded when the
  target bubble has genuinely vanished from the chat thread
  (`stale_reason=no_match`); when the active customer has drifted
  between the source-guard pass and the click
  (`active_customer_drifted_during_source_guard`); or when mt030
  detects an agent bubble already exists more recent than the target
  customer bubble (caught at PreDispatch, never reaches the guard).
- **Telemetry:** Every relaxation emits a `feige_send_mt034_stale_relaxed`
  FEIGE-LEDGER event with `customer`, `source_msg_id`, `latest_msg_id`,
  `gap_s`, and `stale_gap_s` so you can confirm the threshold is being
  hit appropriately.
- **History:** Introduced 2026-05-23 (mt034) after the customer's
  trace showed 6 `stale_reply_source_msg_id` rejections in a single
  ~3 hour run, all on customer `肽斯特`, all caused by 30-90 s gaps
  between rapid back-to-back questions.
- **Source:** `agent/ec_skills/browser_use_extension/extension_tools_service.py`
  (`feige_send_message` — search for `mt034`)

### `ECAN_STALE_QUEUE_EVENT_TTL_S`

- **Default:** `1800` (seconds, i.e. 30 min)
- **Purpose:** Drop chat_message / a2a / channel_message events that
  have been sitting in a task queue longer than this. Prevents
  zombie deliveries to long-closed chats after the front-desk wakes
  from a multi-hour idle.
- **Source:** `agent/ec_tasks/runner.py`

---

## Mode switches

### `ECAN_MODE`

- **Values:** `desktop` (default) / `web`
- **Purpose:** Selects between the Qt desktop GUI and the headless
  FastAPI server entry point.

### `ECAN_QTWEBENGINE_REMOTE_DEBUGGING`

- **Default:** unset
- **Purpose:** When set, opens a Chrome DevTools port for the embedded
  QtWebEngine so the React frontend can be inspected externally.

---

## Test-only flags

### `ECAN_EMULATION_TEST_FLAGS`

- **Default:** unset (= disabled)
- **Values:** `1`, `true`
- **Purpose:** When set, the LLM-node reads
  `customer_logs/emulation/emulation_config.json` at every invocation
  and injects the configured fault (HTTP 429 or connection error)
  according to the `llmFault.inject429Probability` knob. Used by the
  emulation site's **真实站点模拟** panel to reproduce the customer's
  quota-exhausted live failure mode locally without depleting an OpenAI
  key.
- **Source:** `agent/ec_skills/build_node.py:_maybe_inject_llm_test_fault`
- **Production safety:** When this env var is unset (the default), the
  test-fault code path is short-circuited at the first line.

The same JSON file also controls the **多轮对话** (multi-round chat)
emulation button which queues follow-up product-detail questions per
customer at the configured interval — purely a front-end feature
(server-side fields recorded for telemetry consistency).

### `ECAN_TEST_*` (other)

Various skill / module-specific test flags surface alongside their
features. Grep `os.getenv("ECAN_TEST_` for the full list.

---

## How to discover new knobs

The codebase has accumulated >40 `ECAN_*` env vars; this doc covers the
ones you'll most often want to touch. To find the rest:

```bash
grep -r "os.getenv(\"ECAN_" --include="*.py" agent/ config/ ota/ | \
  sed -E 's/.*os\.getenv\("(ECAN_[A-Z_0-9]+)".*/\1/' | sort -u
```

If you add a new one, please add it here with default, purpose, and
source file.
