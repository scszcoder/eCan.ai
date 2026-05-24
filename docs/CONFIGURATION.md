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

## Feige human-intervention (mt017 / mt036)

### `HUMAN_HANDLED_TTL_S`

- **Default:** `120.0` (seconds, hard-coded; not env-overridable)
- **Purpose:** How long a `mark_handled` entry survives. After this
  the customer's automation resumes. A second human reply re-stamps
  the entry.
- **Source:** `agent/ec_skills/browser_use_extension/hooks/external/feige_chat/human_intervention.py`

### mt036A — scoped human-intervention skip

Before mt036 the human-intervention mark suppressed ALL bot replies
to a customer for the full 120 s TTL. In the customer's 2026-05-24
11:34 trace, a mis-fire on an unrecognised agent bubble (msg_id
`673c40e5`, actually our own 11:33:59 reply) caused 4 legitimate
follow-up replies to be dropped, each costing 5+ min of re-dispatch
wait.

Post-mt036A: `mark_handled` records the CUSTOMER question's msg_id
the human appears to be answering. The direct-delivery hot path uses
`is_question_handled(customer, target_question_msg_id)` to scope the
suppression — only the bot's reply targeting the SAME question gets
dropped; replies to newer questions proceed normally.

- **Telemetry:** grep `[HUMAN-INTERVENTION]` log lines — they now
  include `question_msg_id=...XXXXXXXX` so you can see which question
  is suppressed.
- **Operator override:** call `human_intervention.clear(customer_key)`
  to wipe both blanket AND per-question entries — automation resumes
  immediately.

### mt036B — whitespace-stripped typed-text recognition

`record_typed_text` and `is_known_typed_text` normalise via
`re.sub(r"\s+", "", text)` so the Feige scraper's DOM extraction
(which collapses `\n` between paragraphs without inserting a space)
matches against the bot's recorded text. Before mt036B, multi-line
bot replies failed exact-match against the scraper's text, causing
mt017 to mis-fire `mark_handled` on the bot's own bubbles.

- **Source:** `agent/ec_skills/browser_use_extension/hooks/external/feige_chat/human_intervention.py`
  (search for `mt036`)

---

## Feige EventMonitor & verified_msg_id (mt037)

### EventMonitor DOM check timeout

- **Default:** `max(check_interval_ms/50, 5.0)` seconds (≈ 5 s with the
  default 250 ms check interval). Not env-overridable today; change the
  literal in `event_monitor.py:_run_loop` if you need to tune it.
- **Purpose:** Hard ceiling on a single DOM check via CDP `Runtime.evaluate`.
  When this fires, **mt037A** force-recycles the monitor's CDP client so
  the next poll opens a fresh WebSocket — instead of reusing a stuck
  client through more timeouts.
- **History:** Pre-mt037 the timeout floor was 8 s AND the stuck client
  was reused, producing 5×8 s = 40 s clusters of "customer message not
  detected" (live trace 2026-05-24 13:31:36 → 13:32:28, packet's 能包邮
  question sat unobserved for 59 s). Post-mt037 a single 5 s timeout
  triggers a recycle and the next poll (~250 ms later) sees the message.
- **Diagnostics:** grep `[EventMonitor]` log lines. Old behaviour logged
  `... timed out after 8.0s ...; continuing loop`. Post-mt037 logs
  `... timed out after 5.0s ...; recycling CDP client` followed soon by
  `Independent CDP connection established` on the next poll.
- **Source:** `agent/ec_skills/browser_use_extension/event_monitor.py`
  (search for `mt037`)

### mt037C — `verified_msg_id` capture

`feige_send_message`'s JS function `latestAgentBubbleMsgId` is called
post-verify to capture the typed bubble's `data-id`. Python uses this
to call `record_typed_msg_id`, which is mt017's primary recognition
channel for "is this agent bubble ours?".

Pre-mt037C: the function used a single-criterion selector check
(`.iD7SHBvMhm4OhfCsBGr1` + `messageIsMe` class) and didn't tolerate
the brief window between bubble render and `data-id` assignment.
Result: **0 of 57 successful sends captured a msg_id** in the
customer's 2026-05-24 13:05-13:34 trace. mt017 then mis-fired on the
bot's own bubbles via fragile text-only matching.

Post-mt037C: the function (a) accepts EITHER `messageIsMe` class OR
row `flexDirection: row-reverse` (matching the working chat-thread
scraper), (b) prefers the bubble whose textContent matches the text
we just typed, (c) polls up to 5×100 ms for the async `data-id`
assignment.

- **Telemetry:** grep `verified_msg_id` in FEIGE-LEDGER entries.
  Pre-mt037C: never appears. Post-mt037C: should appear on most
  successful sends.
- **Source:** `agent/ec_skills/browser_use_extension/extension_tools_service.py`
  (search for `mt037C`)

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
- **Purpose:** When set, the eCan app reads
  `customer_logs/emulation/emulation_config.json` before every LLM call
  AND before every `rag_query` call, and injects the configured fault
  according to the JSON stanzas:
  - `llmFault.inject429Probability` — synthesizes OpenAI 429 / connection
    error. Mode picked from `llmFault.errorMode` (`429` or `connection`).
  - `ragFault.injectProbability` — added 2026-05-24 (mt038). Synthesizes
    a RAG fault. Mode picked from `ragFault.mode`:
    - `hang` — `await asyncio.sleep(ragFault.hangSeconds)` before the
      real RAG call. Set `hangSeconds > 10` to exercise mt019's 10s
      timeout cap.
    - `error` — raise `ValueError` immediately. Exercises QA-side
      RAG-error fallbacks.
  Used by the emulation site's **真实站点模拟** panel (LLM 429) and the
  **RAG 故障注入** panel to reproduce live failure modes locally without
  depleting an OpenAI key or bringing down a real LightRAG server.
- **Sources:**
  - `agent/ec_skills/build_node.py:_maybe_inject_llm_test_fault`
  - `agent/ec_skills/rag/local_rag_mcp.py:_maybe_inject_rag_test_fault`
- **Production safety:** When this env var is unset (the default), the
  test-fault code path is short-circuited at the first line.

The same JSON file also controls the **多轮对话** (multi-round chat)
emulation button which queues follow-up product-detail questions per
customer at the configured interval — purely a front-end feature
(server-side fields recorded for telemetry consistency).

---

## mt0XX local-repro map

Each `mtNNN` marker tagged in the code corresponds to a specific
production bug fix. The local emulator
(`customer_logs/emulation/server.py`) exposes the trigger pattern
needed to reproduce each bug under test conditions. The table below
maps each marker to: (a) the bug it fixes, (b) the emulator control
that reproduces the trigger, (c) the code anchor for the fix.

Updated 2026-05-24 alongside mt038.

| Marker | Bug fixed | Emulator trigger | Code anchor |
|---|---|---|---|
| **mt015** | placeholder ↔ real-reply race + orphan timers | `CDP / Renderer Chaos` → `Block click ms` + `Delay append ms` | `agent/ec_skills/browser_use_extension/extension_tools_service.py` |
| **mt016** | runaway placeholder loop | `并发消息` + env `FEIGE_MAX_PLACEHOLDERS_PER_INFLIGHT` (default 2) | `agent/ec_skills/runner.py` |
| **mt017/18/21** | human-intervention detection (abort if before LLM, no-op if after) | per-customer button `*·人工直接回复 (mt017)` | `agent/ec_skills/browser_use_extension/hooks/external/feige_chat/human_intervention.py` |
| **mt019** | rag_query MCP hang | `RAG 故障注入` panel → `mode=hang`, `hangSeconds=30` | `agent/ec_skills/rag/local_rag_mcp.py` |
| **mt020** | RAG default-mode tunable | env `ECAN_RAG_QUERY_DEFAULT_MODE=naive` + `RAG 故障注入` to see effect | same |
| **mt022** | LLM 150s → 45s timeout + retry-on-hang + heartbeat | `真实站点模拟` → `LLM 429 注入概率 100%`, mode `Connection error` | `agent/ec_skills/build_node.py` |
| **mt023** | three unanswered-customer bugs (typing-lock leak, scrape race) | `并发消息` (default 20 → flood) | `agent/ec_skills/node_runtime/frontdesk_dispatch.py` |
| **mt024/25** | front-desk parallel dispatch + revert | `并发消息` | same |
| **mt026-31** | scrape lock + dom-echo baselines + stale-bubble | `并发消息` + `CDP / Renderer Chaos` → `Rerender during send` | `agent/ec_skills/browser_use_extension/hooks/external/feige_chat/*` |
| **mt030** | skip dispatch when agent_idx > customer_idx | per-customer button `*·注入历史会话 (mt030)` | `agent/ec_skills/browser_use_extension/hooks/external/feige_chat/pre_dispatch_enrich.py` |
| **mt033** | placeholder ledger registration BEFORE await | `CDP / Renderer Chaos` → `Delay append ms` ≥ 1000 + `并发消息` | `agent/ec_skills/runner.py`, `event_monitor.py` |
| **mt034** | whitespace-strip normalize + 300s stale-gap relaxation | `并发消息` (multi-line bot replies + close-spaced customer Qs) | `agent/ec_skills/browser_use_extension/extension_tools_service.py` |
| **mt035** | LLM worker `done.set()` ordering | `真实站点模拟` → `LLM 429` near completion | `agent/ec_skills/build_node.py` |
| **mt036A/B** | scoped human-intervention + whitespace-stripped typed-text | `并发消息` + `*·人工直接回复` mid-flood | `agent/ec_skills/browser_use_extension/hooks/external/feige_chat/human_intervention.py` |
| **mt037A** | EventMonitor CDP recycle on TimeoutError | `CDP / Renderer Chaos` → `Renderer stall` ON, `Block ms` 450, `Every ms` 1800 | `agent/ec_skills/browser_use_extension/event_monitor.py` |
| **mt037B** | DOM-check timeout floor 5.0s (was 8.0s) | same — covered passively | same |
| **mt037C** | `verified_msg_id` JS rewrite (dual-test agent bubble, polling) | any send — runs passively | `agent/ec_skills/browser_use_extension/extension_tools_service.py` |
| **mt038A** | re-scrape rescue on `stale_reply_source_msg_id` | `并发消息` with `图文 % > 0` or `卡片 % > 0` (defaults 20/20) | `agent/ec_skills/browser_use_extension/extension_tools_service.py` |
| **mt038B** | defer dispatch when scrape fails AND sidebar is attachment marker | `并发消息` (defaults guarantee `[商品]`/`[图片]` previews) OR per-customer button `B客户·裸图` | `agent/ec_skills/browser_use_extension/hooks/external/feige_chat/pre_dispatch_enrich.py` |
| **mt038C** | source-guard recognizes product-card bubbles (no_match drop when latest bubble is a card) | `并发消息` with `卡片 % > 0` (default 20) — any 客户 receiving a card-mode hand-off | `agent/ec_skills/browser_use_extension/extension_tools_service.py` (`allCustomerBubbles()` JS) |
| **mt038D** | placeholder sweeper survives CDP recovery (was a sticky boolean flag → sweeper never restarted after `Invalidated cached BrowserSession`, customers stranded with no placeholder) | `并发消息` heavy enough to trigger 3 consecutive `get_or_create_cdp_session` timeouts → `[CDP-EVAL] recovery invalidated browser session` log line | `agent/ec_skills/browser_use_extension/hooks/external/feige_chat/dom_assets.py` (`_start_placeholder_sweeper` + `ensure_feige_tab_focused` call site) |
| **mt038E** | placeholder key-mismatch suppress — when `arm()` / `cancel()` see different `source_msg_id` values under flood (PreDispatch scrape failed on one side OR LLM reply payload lost `source_customer_msg_id` on the other), the placeholder mis-fired AFTER the real reply had already landed | `并发消息` with `图文 % > 0` and/or `卡片 % > 0` — any flood where PreDispatch's per-customer tab focus times out (look for `armed cust='客户XX' source_msg_id='' fires_in=1.0s` followed by `fired placeholder` AFTER `feige_send_tool_success`) | `agent/ec_skills/browser_use_extension/hooks/external/feige_chat/placeholder_timer.py` (`cancel`, `mark_real_reply_delivered`, `claim_expired`, `is_real_reply_recent` — all stamp / consult the `(customer, '')` slot, gated by `entry.armed_at`) |
| **mt038F (emulator)** | deep reset button — `重置所有聊天记录（mt030 基线）` wipes each customer's `dialogs[]` so multiple `并发消息` runs in the same emulator session don't accumulate stale Q+A pairs that trip mt030 | (test-tool: click before each flood run for a clean baseline) | `customer_logs/emulation/static/app.js` (`resetAllChatThreads`) + `index.html` button |
| **mt038F (F.2)** | mt030 honors mt017's "pre-existing baseline" tag — was wrongly skipping dispatch when the "agent" bubble was actually a smart_cs greeting / prior-session leftover that mt017 had already classified as not-our-reply | `并发消息` after `mt038F (emulator)` reset — under scrape-lock contention (~2s+) the emulator's auto-greeter races the customer Q in the chat thread; pre-F.2 trace shows `mt030 skip dispatch ... text='亲亲，在哒~...'`; post-F.2 logs `mt038F-F2 mt030 would fire but agent bubble is pre-existing baseline` instead | `agent/ec_skills/browser_use_extension/hooks/external/feige_chat/pre_dispatch_enrich.py` (`_agent_bubble_is_pre_existing_baseline` flag set in mt017 branches, consulted by mt030 check) |

**How to use this table during a regression sweep:**

1. Start the emulator: `python customer_logs/emulation/server.py`
2. Launch eCan with `ECAN_EMULATION_TEST_FLAGS=1` so the LLM/RAG fault
   injectors are armed.
3. For each marker you want to re-verify, set the listed emulator
   trigger, run `并发消息` (or the per-customer button), and grep
   `customer_logs/eCan.log` for the marker's expected log line (e.g.
   `mt038A re-scrape rescue`, `mt038B defer dispatch`, `mt030 skip
   dispatch`, etc.).
4. The `并发消息` default mix (20% image / 20% card / 60% text)
   reliably exercises mt038A/B + the multimodal scraper paths on
   every flood. Drop image%/card% to 0 for legacy text-only behavior.

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
