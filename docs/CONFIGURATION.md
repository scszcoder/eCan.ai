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
