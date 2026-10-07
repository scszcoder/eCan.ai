# 天猫 / 淘宝 客服 on 千牛 — Fast Deploy + front-desk skill (v0.9.99x, updated v0.9.99ya)

Status (2026-10-05): **code shipped in v0.9.99x, alpha.** The deploy path, the
multi-platform switch and the skill/prompt are built and tested off-line. Nothing
has yet run against a live 千牛 client or through a real LLM call. Expect the
first alpha logs to drive calibration (see "Known risks").

Related docs:
- `docs/QIANNIU_PLUGIN_PLAN.md` — the 千牛 desktop plugin plan (Phases 0-3).
- `agent/ec_skills/browser_use_extension/hooks/external/qianniu_chat/README.md`
  — the `qianniu_chat` bundle: memory observer, OCR, send tools, env knobs.
- `docs/TMALL_QIANNIU_CHAT_DESIGN.md` + `docs/OPEN_ITEMS.md` ("Tmall / Qianniu")
  — why the web route (千牛 Web, `tmall_ws` branch) is dead.

---

## 1. What changed, in one paragraph

Before this release, choosing 快速生成 → 天猫客服 ran a **stub**. It printed a plan
(1 front desk + N Q&A agents) and created nothing; the panel showed
"该场景暂未开放自动生成" / 失败.

Now it creates the same shape as 拼多多客服:
- one front-desk agent + task on the skill **淘宝客服前台01**;
- N Q&A agents + tasks on the shared **飞鸽客服问答00**.

淘宝客服前台01 was rebuilt for 千牛. It used to be an unedited copy of the Feige
browser front desk; it is now a **no-browser** graph:

`pend_event → prep code → LLM → MCP(qianniu_* / send_chat)`

It reads buyer messages from the `qianniu_chat` memory observer and replies
through the OCR-verified `qianniu_send` tool.

千牛 also runs **alongside 飞鸽 and 拼多多 in one process**:
- deploys add to `ECAN_LIVE_CHAT_SITE` instead of replacing it;
- the Settings platform switch is now a multi-select;
- the 千牛 skill declares its site, so a 千牛 reply can never be typed into
  another platform's browser.

---

## 2. Why 千牛 is different from 飞鸽 / 拼多多

| | 飞鸽 (抖店) / 拼多多 | 千牛 (天猫/淘宝) |
|---|---|---|
| Client | Web page in Chrome (CDP) | Native Win32 desktop app (AliWorkbench), CEF DevTools locked |
| Inbound messages | DOM / page WebSocket observers | `qianniu_chat` **process-memory observer** (read-only) |
| Outbound send | Browser DOM/WS send tools, direct-delivery fast path | `qianniu_send` MCP tool: OCR header (+ body) verify, then clipboard + Enter |
| Front-desk skill | `browser-automation` node + Feige/PDD prompt | **No browser node** — pend_event + code + LLM + MCP |
| Store login | Per-store browser profile | The seller signs in to the 千牛 client on that machine |
| Stores per machine | Several (one browser profile each) | **One** (one desktop window, one typing lock) |

The bundle is activated only by `ECAN_LIVE_CHAT_SITE` containing `qianniu_chat`.
It is NOT tied to the browser node, although it lives under
`browser_use_extension/hooks/external/`:
- every bundle in that folder is imported at app start (`build_node.py` hook
  discovery);
- `qianniu_chat/__init__.py` registers the runner bridge and starts the observer
  thread only when its site is named.

---

## 3. End-to-end message flow

```
千牛 client (buyer writes)
  │  process-memory scan every ECAN_QIANNIU_POLL_S (3s)
  ▼
qianniu_chat observer ── item {customer_id, customer_display_name, latest_message, msg_id, identity_key}
  │  event_monitor._dispatch_to_runners  (type=browser_event, sub_type="qianniu_chat", session=None)
  ▼
淘宝客服前台01 front desk  ── pend_event wakes (browserEventLabel "qianniu_chat")
  │  code_qn_prep → input {kind:"customer_message", ..., qa_agent_id}
  │  LLM → send_chat(recipient_agent_id = qa_agent_id, message = {customer_id, customer_name, latest_message, customer_recent_messages})
  ▼
飞鸽客服问答00 Q&A agent (shared skill; pend_event filters senderId == {{front_desk_agent_id}})
  │  classifier → rag_query / query_* → send_chat(response_text) back to the front desk (recipient auto-filled)
  ▼
淘宝客服前台01 front desk  ── pend_event wakes (chat_message / a2a_response)
  │  code_qn_prep → input {kind:"qa_reply", buyer_display_name, response_text, expect_message_text}
  │  LLM → qianniu_check_location (OCR) → [qianniu_open_session → qianniu_check_location] → qianniu_send
  ▼
千牛 client (reply typed + sent, only after the OCR checks pass)
```

Direct delivery (the runner's fast path that types a Q&A reply straight into a
cached browser) does **not** apply to 千牛:
- the skill resolves to site `qianniu_chat` (section 6);
- that bridge advertises no `open_session_tool_name` / `send_message_tool_name`;
- so `_try_direct_live_chat_delivery` returns False, and the reply is queued to
  the front desk's own graph, which sends it with `qianniu_send`.

---

## 4. Fast Deploy (`cli/deploy/commands.py`)

### 4.1 Profile

`_TMALL_PROFILE` is a `_LiveChatProfile`:

| field | value |
|---|---|
| scenario / label / platform | `tmall_cs` / 天猫客服 / `tmall` |
| front desk skill | `淘宝客服前台01` (`skill_e92218afd50a4ae6`), found by exact name (`find_skill_by_name=True`) |
| Q&A skill | `飞鸽客服问答00` (`skill_4f24592c81894ae7`), the same shared skill 飞鸽 / 拼多多 use |
| prompts verified up front | Q&A: `pr-287230` 飞鸽客服应答0, `pr-543744` 飞鸽社交应答0, `pr-56931` 飞鸽RAG路由分类0; FD: **`pr-731906` 千牛客服前台0** |
| task name prefixes | `天猫客服前台` / `天猫客服应答` |
| run.env | `ECAN_LIVE_CHAT_SITE` += `qianniu_chat` |
| `native_desktop` | **True** (new profile field; False for 飞鸽 / 拼多多) |

### 4.2 What `native_desktop=True` changes in `_deploy_live_chat`

- **No Chrome pre-check** (`run_chrome_precheck` is for browser sites).
- **Store URL optional.** A 天猫 store record may have none; `task_vars.store_url`
  is then `""`.
- **No browser login profile** (`_ensure_store_login` skipped). Instead the log
  tells the operator to open and sign in to the 千牛 client on this machine (one
  store per machine). `needs_login` is empty and tasks carry no
  `browser_identity`.
- **Q&A pool handed to the front desk.** After the Q&A agents are created, the
  front-desk task is updated so its `task_vars` include
  `qa_agent_ids=<id1,id2,…>`. Feige gets this list injected by its
  browser-node hook (`actionable_items`); a no-browser front desk has no such
  hook, so it reads the ids from task vars. A failed update aborts the deploy
  with a clear message.

Everything else is shared with 飞鸽 / 拼多多:
- replace mode clears only this store's tasks by name prefix + store id;
- skill and prompt visibility are verified before anything is created;
- agents are pinned to the store's vehicle and created under the Sales org;
- created rows are synced to the cloud.

There is **no `tmall_cs_multi`**: one 千牛 window per machine.

### 4.3 `ECAN_LIVE_CHAT_SITE` is now a merged list

`_set_run_env` treats keys in `_LIST_ENV_KEYS = {"ECAN_LIVE_CHAT_SITE"}` as
comma-separated sets:
- new entries are appended;
- existing entries stay first, because the first entry is the process default
  site for calls made outside a node run.

So deploying 拼多多 then 天猫 yields `pdd_chat,qianniu_chat`; redeploying 拼多多
leaves it unchanged. Before this, each deploy replaced the value, so deploying
one platform silently switched the other off.

---

## 5. The 淘宝客服前台01 skill (data, not code)

The skill and its prompt are **data**:
- they live in the author's local skill library (`my_skills/`) and prompt store
  (`<user>_local/my_prompts/`), both gitignored;
- they reach customers by **publishing** them from the app (skill store), never
  through git;
- the deploy refers to them only by name / id.

**Until a customer's machine has them** (subscribe, or the skill's prompts
download with it), 快速生成 → 天猫客服 stops before creating anything:
"看不到技能 淘宝客服前台01…" / "看不到提示词 千牛客服前台0 (pr-731906)…".

The pre-千牛 version (a Feige browser front-desk copy) is backed up next to the
diagram as `diagram_dir/.harness_bak/淘宝客服前台01_skill.pre_qianniu.json`
(+ `_bundle`).

### 5.1 Graph

The loop is cloned from 飞鸽客服问答00's proven inner loop (same node types,
condition style and loop-terminator pattern), minus its classifier branch, plus
one prep node:

```
loop_WdkmQ:
  block_start → pend_event_qn01 → code_qn_prep → llm_qn01 → mcp_qn01 → condition_qn01
                                                    ▲                       │ if  → code_qn_end → block_end   (round over → wait again)
                                                    └───────────────────────┘ else (tool result in history → next tool)
```

Compiled node list (verified with `load_skill_from_folder`):

`update_loop_WdkmQ_condition, check_loop_WdkmQ_condition, pend_event_qn01,
code_qn_prep, llm_qn01, mcp_qn01, condition_qn01, code_qn_end`

### 5.2 Nodes

**`pend_event_qn01`**
- Waits for `eventType=chat_message` (also accepts `a2a_response` /
  `a2a_task_result`, i.e. replies from Q&A agents; no sender filter).
- Also waits for `pendingSources=[{type: browser_event, browserEventLabel:
  "qianniu_chat"}]` — the observer sets `sub_type="qianniu_chat"`, and runner
  routing matches the label against `sub_type`.
- The labels of 飞鸽 / 拼多多 front desks differ, so their events never wake this
  skill, and 千牛 events never wake theirs.

**`code_qn_prep`** (Python code node) exists because pend_event leaves
`state["input"]` **empty** after a browser_event:
- the item lives only in `state.attributes.browser_event.body.items`, so the
  LLM's `{{input}}` would be blank;
- after a chat_message, `state["input"]` is the Q&A agent's raw JSON string.

The node turns either event into one JSON `state["input"]` and keeps per-run
memory in `state.attributes.qianniu_fd`.

| event (from `state.events[-1].event_type`) | output `kind` | fields |
|---|---|---|
| `browser_event` | `customer_message` | `customer_id`, `customer_name` (display name or id), `latest_message`, `customer_recent_messages` (last 5), `qa_agent_id` |
| same `identity_key` seen before | `skip` | `reason` |
| `chat_message` / `a2a_*` with JSON `response_text` | `qa_reply` | `customer_id`, `buyer_display_name` (may be `""`), `response_text`, `expect_message_text` (buyer's last message) |
| anything else | `unknown` | `raw` (first 500 chars) |

- **Q&A agent choice:** `task_vars.qa_agent_ids` (from the deploy).
  - **Sticky** per buyer; new buyers go round-robin.
  - Empty list → `qa_agent_id=""` and the prompt falls back to `list_chat_agents`.
- **Display name:**
  - order: the observer's `customer_display_name` → `name_map.name_for(id)`
    (names the observer learned by matching message text on screen) → the name
    remembered at dispatch;
  - the raw memory id is **never** used as a 千牛 display name, because a wrong
    name can only fail the header check anyway.
- **Dedup:** the last 200 `identity_key`s.
- **Log line per round:**
  `[QIANNIU-FD] event=<type> -> <input JSON>`.
- **`hookBundles = [{"path": "qianniu_chat"}]`** sits on this node's
  inputsValues. It has no effect on the code; it is how
  `live_chat_dispatch.site_for_skill` learns this skill's platform (section 6).

**`llm_qn01`**
- `promptSelection = pr-731906`, user turn `{{input}}`.
- Model settings copied from the Q&A skill's main LLM, temperature 0.2. All calls
  go through the llm-proxy like every other node.

**`mcp_qn01`**
- `llm-auto-select`: it reads the LLM's `{"tool_name", "tool_input"}` JSON and
  calls the tool in-process.
- For `send_chat` it auto-fills `sender_agent_id` (this agent) and `chat_id`.
- For replies, an empty recipient is filled with the event sender.

**`condition_qn01`**
- Terminal when `llm_result.tool_name in ("send_chat", "qianniu_send")` or
  `llm_result.all_done`. Terminal rounds go to `code_qn_end` → block_end →
  pend_event.
- Anything else (`qianniu_check_location`, `qianniu_open_session`,
  `list_chat_agents`) loops back to the LLM with the tool result in history.
- `qianniu_send` is terminal whether or not it sent: its success is not
  promoted into `work_result`, and it is fail-closed by itself, so nothing
  retries.
- The MCP node caps a round at 8 iterations.

### 5.3 Prompt `pr-731906` 千牛客服前台0 (contract)

The prompt's output rules:
- exactly one bare JSON tool call per turn, or `{"all_done":true,"work_done":true}`;
- no prose, no `multi_tool_calls`.

Each `kind` drives one flow.

**Flow A — `customer_message`:** one `send_chat` to `qa_agent_id`.
- `message` is the exact 4-field JSON string `{customer_id, customer_name,
  latest_message, customer_recent_messages}` that 飞鸽客服问答00 expects.
- The front desk never answers the buyer itself and never calls `qianniu_*` here.
- A DEDUP reply from `send_chat` counts as success (no rotating agents).

**Flow B — `qa_reply`:** "better not send than send to the wrong buyer". The
outcome depends on what `qianniu_check_location` reports (OCR of the window; it
may click the 正在接待 tab first):

| `qianniu_check_location` result | action |
|---|---|
| window missing / layout not recognised | `all_done` (nothing sent) |
| `thread_ok` (header names the buyer AND their message is in the chat) | `qianniu_send` with `expect_message_text` |
| header matches, body not visible (scrolled) | `qianniu_send` without `expect_message_text` (header-verified) |
| body matches, header doesn't (typical when the name is unknown) | pick the buyer nickname from `header_candidates`; `qianniu_send` with that name **and** `expect_message_text` |
| neither, name known | `qianniu_open_session` → check again → if still neither, one last `qianniu_send` with `auto_open:true` + `expect_message_text` (`qianniu_send` re-verifies and refuses on mismatch) |
| neither, name unknown | `all_done` (no guessing) |

Limits per round: `qianniu_check_location` ≤ 2, `qianniu_open_session` ≤ 1.

`chat_msg` is always the Q&A `response_text` verbatim. When the Q&A agent sends
a "请稍等" placeholder first and the answer second, both are delivered.

| tool | used in | input |
|---|---|---|
| `send_chat` | A | `sender_agent_id` (empty, auto), `recipient_agent_id`, `message` |
| `list_chat_agents` | A, only if `qa_agent_id` empty | `filter_name` ("客服小") |
| `qianniu_check_location` | B step 1 | `buyer_display_name`, `expect_message_text`, `ensure_reception_tab` |
| `qianniu_open_session` | B | `buyer_display_name` |
| `qianniu_send` | B end | `buyer_display_name`, `chat_msg`, `auto_open`, `expect_message_text` |
| `qianniu_receive` | diagnostics only | — |

---

## 6. Running 千牛 alongside 飞鸽 and 拼多多

**Site gate.**
- `ECAN_LIVE_CHAT_SITE` is comma-separated (`live_chat_dispatch.configured_sites`).
- 飞鸽 always registers (ungated). `pdd_chat` and `qianniu_chat` register only
  when named.
- `pdd_chat,qianniu_chat` therefore serves all three. Each bundle has its own
  bridge keyed by site (`_BRIDGES`).

**Settings switch** (`LiveChatSiteSetting.tsx` + `gui/ipc/w2p_handlers/live_chat_site_handler.py`):
- **Control:** now a multi-select of 拼多多 / 千牛, with placeholder "仅飞鸽" (Feige only).
- **IPC:** `live_chat_site.set` accepts `site` (comma string, the old single
  value still works) or `sites` (list).
- **Validation:** one unknown name refuses the whole save. A legacy saved
  `feige_chat` is accepted.
- **Applies** after restart.
- **`.get`** returns `site` (raw) plus `sites` (known entries).

**Cross-platform guard (important).** Work done for a task outside its node run
picks its platform via `site_for_skill(task.skill)`; this includes direct
delivery of a Q&A reply.
- That function reads the skill's `hookBundles`.
- A skill with no browser node has none, so it would fall back to the first
  configured site.
- `_find_cached_live_chat_browser_session` returns the only cached browser when
  there is exactly one. A 千牛 reply could then have been typed into a 拼多多 or
  飞鸽 page.

The `hookBundles` entry on `code_qn_prep` makes `site_for_skill` return
`qianniu_chat`. Verified with all three bridges registered:
`bridge_sites() = ['feige_chat', 'pdd_chat', 'qianniu_chat']` →
`site_for_skill(淘宝客服前台01) = 'qianniu_chat'`. Direct delivery then finds no
send tool on the 千牛 bridge and hands the reply to the front-desk graph.

Event isolation needs nothing extra:
- `_dispatch_to_runners` broadcasts the observer's browser_event to every runner,
  but each runner's pend routing matches its own label;
- Q&A replies are addressed to the specific front-desk agent;
- each Q&A task filters on its own `front_desk_agent_id`, so the shared Q&A
  skill serves all three front desks without crossing.

---

## 7. Verification done (2026-10-05)

- `tests/test_fast_deploy_replace_mode.py`, `tests/unit/test_deploy_live_chat_multi.py`,
  `tests/unit/test_live_chat_site_setting.py`, `tests/unit/test_live_chat_delivery_site.py`,
  `tests/test_pdd_bundle.py`: **44 passed**.
- New tests:
  - `test_tmall_is_a_real_native_desktop_deployment_not_a_stub`: profile, skill,
    prompt, env;
  - `test_live_chat_site_is_added_to_run_env_not_replaced`;
  - `test_the_site_switch_adds_to_an_old_value`: replaces the old "replaces" test
    from the one-platform era;
  - `test_handler_saves_several_sites_together`.
- `code_qn_prep` exercised on items built by the real `observer.item_for`:
  dispatch → duplicate skipped → reply with name + expect text → 2nd buyer
  round-robins to the next Q&A agent → unknown name stays `""` → non-JSON → `unknown`.
- The skill compiles through the real loader to a `CompiledStateGraph` with the
  edges in 5.1.
- `pr-731906` resolves through the same owner-scoped lookup as the Feige prompts
  (`_missing_system_prompts → []`) and renders with exactly one variable, `{{input}}`.
- `gui_v2` typecheck: no errors in the changed component. The project has 647
  pre-existing errors elsewhere.

**Not verified:**
- a real LLM turn on the prompt;
- a live 千牛 client (memory intake, OCR geometry, send);
- a full app-run deploy on a customer machine.

---

## 8. Known risks / what the alpha logs will tell us

**First alpha run (v0.9.99x, 2026-10-06), fixed in the next rev.** Two parts of
the run worked:
- the deploy created 7 agents / 7 tasks;
- all three bridges registered (飞鸽 + 拼多多 + 千牛), and the front desk compiled
  with `pr-731906` and started.

But the observer ran for ~8 h and dispatched nothing (zero `[QIANNIU-FD]` lines).

**Cause:** it scanned the first process named AliWorkbench.exe.
- 千牛 runs a root AliWorkbench.exe plus a child AliWorkbench.exe and many
  AliRender.exe.
- In the 2026-09-30 probe run, every chat message sat in the root (pid 12040),
  none in the child (pid 9320).
- psutil lists by pid, so the child came first.

**Fixes in v0.9.99ya:**
- **Process choice:** `observer._qianniu_pids()` returns the root process first.
  Scanning sticks to whichever process last held messages and falls back to the
  others. Test: `tests/unit/test_qianniu_observer_process.py`, using the real
  probe process table.
- **Seller id:** `mem_locator.seller_id_of` used to take "the id common to every
  message". With one buyer and no seller reply in memory (a single-customer
  test), that is the BUYER, and every one of their messages was then dropped as
  outgoing. It now takes the sender of the outgoing (`ccode` / `sendStatus`)
  messages only.
- **Cold-start baseline:** 千牛 memory holds chat HISTORY, so the first scan
  that finds messages now marks every buyer message already in memory as seen
  and answers none of them. After that, a message whose `sendTime` is before
  the run started (minus 60 s grace) is skipped as stale. This covers a
  conversation opened later, whose history loads into memory then. Both are
  logged.
- **Logging at every step:** see the log map below. Tests:
  `tests/unit/test_qianniu_observer_logging.py`.
- **Live check:** the real Windows read path (OpenProcess / ReadProcessMemory →
  `extract_candidates`) was checked on this machine. A message planted in the
  test process's own memory was found in both encodings, and the counters
  filled.

**Second alpha run (v0.9.99ya, 2026-10-07), fixed in v0.9.99yb.** The process
fix worked. Root pid 17080 was found and scanned in ~0.6 s; its first scan
parsed 5 objects, all UI cards, and no buyer message.

The buyer's test message 有花生味牙线吗 appeared in memory 12 minutes later. It
was swallowed by the cold-start baseline, which 0.9.99ya took on the first pass
that found any buyer message instead of on the first pass.

**Fix:**
- The first error-free pass is the baseline, even when empty; it logs
  `baseline: 0 buyer messages in memory at start`.
- A message whose `sendTime` is after the run started is never baselined.
- A start with 千牛 closed is not a baseline.
- The first-scan line now also shows one example of a dropped UI card's keys.

Tests: `test_an_empty_start_is_the_baseline_so_the_first_new_message_is_answered`
(that exact timeline) and two neighbours. Non-blocking errors in that log are
cloud sync (`addAgentTaskRels: Agent not found`, `queryAgentTaskRels` missing
subfields) and one 飞鸽 skill `examples` conversion warning.

**Third alpha run (v0.9.99yb, 2026-10-07), changes in v0.9.99yc.** The
baseline worked (the 04:15 message was correctly skipped as history). The
operator then sent 有樱桃味牙线吗 as buyer sctisz while 大作战panda's chat was
open. It landed in 千牛 but was never detected: no new message object entered
memory in that run.

What the probes and the standalone bot (`eCan.ai-cn/customer_logs/tools/qianniu_cs_bot`,
v0.15) say about it:
- The app already has the bot's detection (`cffaedda5`: both encodings, no
  region cap, `ccode` direction).
- The bot holds that hidden-conversation messages are in memory (often only the
  UTF-16LE copy).
- Probe v8 recorded a hidden message as `text, no structured metadata`.

The log could not tell which applies, so v0.9.99yc:
- **FIND mode** (`ECAN_QIANNIU_FIND=<text>[|<text>]` in run.env): each scan
  reports, on change, where that exact text is (`inside_message_object` /
  `inside_other_object` / `bare_text`), the enclosing object's keys, and one
  context dump. This is the bot's `--find`/`--probe` inside the app. The test
  text is chosen by the operator, so one run settles text-only vs structured vs
  classed-outgoing.
- **Every new message object** (either direction) is logged once with the
  reason for its direction (`cid.ccode` / `ccode` / `sendStatus` / `progress` /
  store id). This is the only place a buyer message classed OUTGOING becomes
  visible.

**Mis-delivery bug found while porting the bot's routing (fixed):**
- `transcript_contains` matched ANY OCR line on screen, including the 正在接待
  list previews.
- With panda open and sctisz's message showing as a list preview:
  `qianniu_check_location` said `body_ok`, the prompt picked panda's header
  name, and `qianniu_send` verified panda's header plus the "body" (really the
  preview). sctisz's answer would have gone to **panda**.
- The learning pass had the same hole: it could bind sctisz's id to panda's
  name.

`transcript_contains` now checks only the chat BODY (right of the list, below
the header), with a strict 6-character prefix: the bot's live-tuned rule.

**Routing ported from the bot:**
- **`find_conversation_row`:** finds the 正在接待 row whose preview shows the
  message. No name or search is needed, and it returns the list name above the
  preview.
- **`qianniu_send`, when `expect_message_text` is given:**
  - the body is the gate; if it does not show the text, the tool opens the row
    by preview, then falls back to a name search, then re-verifies;
  - a text shorter than 4 characters ("在吗") also needs a header-name match;
  - `buyer_display_name` may be empty.
- **`qianniu_open_session`:** accepts `message_text` for the same preview route.

Prompt `pr-731906` Flow B is now one call: `qianniu_send` with
`expect_message_text` and `auto_open: true` (data: republish). Tests:
`tests/unit/test_qianniu_send_routing.py` covers the exact panda/sctisz
screens: the reply opens sctisz's row or is refused, and is never typed into
panda's chat.

**Fourth alpha run (v0.9.99yc, 2026-10-07), fixes in v0.9.99yd.**

*Memory detection proven.* The test text 有石榴味牙线吗 (FIND mode on) was found
**inside a message object**: keys `code, content, msgType, receiverState,
selfStatus, sendTime, sender, status`, sender `{targetId: 678614304,
targetType: 3}`, UTF-8 copy. It was classed `dir=IN`, and the observer
dispatched it to all 21 runners at 07:23:09.

Two blockers stopped it there:

1. **No routing rule.** Every runner logged `No target task found for
   browser_event (sub_type=qianniu_chat)`.
   - The 天猫 front desk registered no rules at all at launch, while 飞鸽 and
     拼多多 each registered `browser_event:新消息`.
   - Cause: 淘宝客服前台01 is compiled from its DB copy on the customer (the
     skill-file download fails on the backend). Its diagram reaches the runner
     as a JSON string, double-encoded in the author's DB.
   - `_extract_event_types_from_skill` returned [] for a non-dict, and logged
     that only at DEBUG.

   Fix: `agent/ec_skills/skill_diagram.as_workflow()` reads every stored shape
   (string / double-encoded string / `{workFlow}` / editor `{sheets}` /
   `{nodes}`). The runner's rule extractor and `site_for_skill` (the
   cross-platform guard, same hole) use it. "No pend_event nodes" is now INFO.
   Test: `tests/unit/test_skill_diagram_shapes.py`.
2. **OCR missing in the installed app.** The error was `local OCR failed: No
   such file or directory: …\_internal\rapidocr_onnxruntime\config.yaml`. The
   build packaged rapidocr's code but not its data (`config.yaml` + three
   `.onnx` models, ~16 MB). Every OCR check behind a send would fail.

   Fix: `rapidocr_onnxruntime` added to `build_config.json`
   `build.pyinstaller.collect_data_only`. Verified on the 3.12 build venv that
   `collect_data_files('rapidocr_onnxruntime')` returns exactly those 4 files.
   Check the build log for `[SPEC] Collected data: rapidocr_onnxruntime`.

FIND mode also logged on every scan as raw hit counts drifted. It now logs only
when what the text is inside changes.

**Fifth alpha run (v0.9.99yd, 2026-10-07): routing works; the front desk's LLM
failed.** Both yd fixes held:
- the front desk registered `browser_event (label='qianniu_chat')` at launch;
- the test message was routed to 天猫客服前台001, and `[QIANNIU-FD]` produced
  the `customer_message` input;
- OCR ran.

Then:
1. **LLM rejected by the proxy.** `503 unsupported chat provider: dashscope`
   for `qwen3.8-max`. The node's model had been cloned from the author's local
   飞鸽客服问答00, which still said `Qwen`. The published copy on the customer
   runs `openai/gpt-5.4` + `gpt-4o-mini`. Fix (skill data): front-desk LLM =
   `DeepSeek / deepseek-v4-flash`, thinking off. It is domestic and was measured
   at 2–3 s against qwen's 8–16 s through the proxy (OPEN_ITEMS 2026-09-17,
   `3ced3f6db`). The node is a plain LLM node, so the deepseek json_schema gap
   does not apply.
2. **One failed round ended the whole task.** The failure left
   `llm_result.all_done=True`, and the OUTER loop exits on `all_done`, so the
   task completed and was relaunched without its state. Any `all_done` answer
   (skip / unknown input) would do the same. Fix (skill data): the loop
   terminator `code_qn_end` resets `all_done` / `work_done`, so every round goes
   back to pend_event.

Also seen: the customer still ran the OLD `pr-731906` (multi-step Flow B), so
the republish had not reached that machine.

**Sixth alpha run (v0.9.99yd + deepseek skill, 2026-10-07): first full
front-desk → Q&A → front-desk round trip.**
- The front desk (deepseek-v4-flash, 2.2 s) handed 有石榴味牙线吗 to Q&A agent
  客服小岚 via `send_chat`.
- The Q&A agent classified it, ran `rag_query`, and replied 这边暂未查到石榴味牙线信息，
  您可以发下商品链接，我帮您看看。
- The front desk got the `qa_reply`.

Three new blockers, fixed in v0.9.99ye / skill data:
1. **Wrong 千牛 window.** The tools focused and OCR'd `倪好数码:小柒-千牛工作台`, the
   workbench home: a promo banner, no 正在接待 list. Chats are in the separate
   接待中心 window. Fix: `qianniu_ocr.qianniu_chat_window()` ranks windows with
   `接待` in the title first, then by area (the bot's rule). Focus and capture
   both use it, and capture targets that window's exact title. It logs the
   candidate titles on change, and warns when no 接待 window is open.
2. **Front-desk ↔ Q&A echo loop.** A front-desk round that does not end in a
   successful `send_chat` (an `all_done`, or the intended `qianniu_send`) was
   sent back to the Q&A agent by `send_response_back`. The Q&A agent answered
   the same question again: 2 full cycles before the app closed. Fix (skill
   data): prep and terminator set `attributes.async_response = False`, the
   documented opt-out. The skip line is INFO now.
3. **A 千牛 system notice was dispatched as a buyer question**
   (`【即将超时】…未回复买家…消极接待…`). Fix: the observer skips notices by
   keyword (like the 飞鸽 filter), and logs `msgType` on every new message object
   so a structural rule can replace the keywords.

Still open: the customer kept running the OLD `pr-731906`, so the republish
did not reach the machine.

**Seventh alpha run (v0.9.99ye, 2026-10-07): the chat window fix works; the
Q&A worker never started.**
- `千牛 windows: ['倪好数码:小柒-接待中心', '倪好数码:小柒-千牛工作台']; using
  '倪好数码:小柒-接待中心'`.
- The message was dispatched, and the front desk (deepseek) handed it to
  客服小岚.
- Then nothing for 87 s.

1. **Only 16 of 22 tasks ever ran.** Every task's run loop holds a thread of
   `mainwin.threadPoolExecutor` for its whole life, and that pool had
   `max_workers=16`. With 飞鸽 + 拼多多 + 天猫 on one machine (3 front desks + 19
   Q&A workers = 22 tasks), the 6 launched last stayed `future=pending`
   forever: 5 of the 6 天猫 Q&A workers. The question routed to 客服小岚
   (天猫客服应答001) sat in a queue nobody read. Fix:
   - the pool defaults to 64 workers, overridable with `ECAN_TASK_POOL_WORKERS`;
   - `[AGENT_START]` WARNs when a task has to wait for a free task thread.

   This also explains "千牛 alongside 飞鸽 and 拼多多" failing once enough
   agents are deployed.
2. **A promo banner was learned as the buyer's name.** `read_header_name` took
   the longest header-band line, `智能客服全新升级，助力客服高效接待！`, and
   `name_map` saved it. Fix: `name_map.looks_like_buyer_name` rejects
   punctuated or UI-worded text. It applies when learning, in
   `read_header_name`, and when reading back a stored entry, so the
   already-saved bad name is ignored.

Side notes from that log, not blocking:
- The customer's skill file download failed (`requestSkillFileDownloadUrl`
  INTERNAL_SERVER_ERROR, backend), so 淘宝客服前台01 compiled from its DB diagram
  copy. That copy was the new graph.
- `[build_llm_node] … both set to 'in-line'` is a false positive (it fires on
  the working Feige Q&A nodes too).

1. **Memory body field + OCR geometry are uncalibrated** (bundle README "Needs a
   live client"). If the body field is wrong, no `[QIANNIU-MEM]` dispatches
   happen. If the geometry is wrong, `qianniu_check_location` returns
   header/body false and replies end `all_done`.
2. **Display names.** Until the observer learns a buyer's name (it needs that
   buyer's chat open on screen once), a reply can only go out when the buyer's
   chat is already the open one (body match + header pick). Others end `all_done`.
3. **`header_candidates` pick** (body-matched, header-unknown case) relies on the
   LLM choosing the nickname among OCR'd header texts. The body check is the real
   guard there.
4. **One store per machine**, and every desktop action is serialized by the
   typing lock.
5. **Front-desk history.** The LLM sees prior rounds in history; the prompt
   restricts it to the current input. Watch token growth on long runs.

### Log map (v0.9.99ya) — read a 千牛 run step by step

Everything below is **INFO** unless marked WARNING, so it is in a customer's
default log. Lines that would repeat every poll are logged **on change** only.
The 5-minute heartbeat carries the running numbers.

| # | step | grep | what it tells you |
|---|---|---|---|
| 1 | bundle on/off | `[qianniu_chat] 千牛 live-chat bundle registered` / `[qianniu_chat] not enabled (ECAN_LIVE_CHAT_SITE=…)` | Is 千牛 on in this process, and what the site list was. |
| 2 | observer start | `[QIANNIU-MEM] observer loop started (poll …s, learn=…)` | The memory reader thread is running. |
| 3 | 千牛 processes | `[QIANNIU-MEM] 千牛 processes: root=… others=[…]` / `not running; waiting` | Logged on change. "not running" = 千牛 closed, or a different exe name. |
| 4 | unreadable process | WARNING `[QIANNIU-MEM] cannot read pid …` | Once per pid. Access denied = eCan runs with lower privilege than 千牛. |
| 5 | first scan of a pid | `[QIANNIU-MEM] first scan of pid N: {…}` | See "Calibration fields" below; `no_text example keys=` comes with it. |
| 6 | where messages are | `[QIANNIU-MEM] chat messages found in pid N` / `no chat messages in any 千牛 process this pass` | Which process holds the chat. |
| 7 | seller id | `[QIANNIU-MEM] seller id in memory: …` | On change. `None` = no seller reply in memory yet; direction then comes from ccode. |
| 8 | cold start | `[QIANNIU-MEM] baseline: N buyer message(s) already in memory marked seen, NOT answered (latest: …)` | History not answered. A buyer who wrote just before start is in here. |
| 9 | stale skip | `[QIANNIU-MEM] skip stale buyer=… sendTime=…` | Old history that loaded later. |
| 10 | name learning | `[QIANNIU-MEM] learned buyer=… -> name=…` / `learn buyer=…: not in the open chat` / `no header name; header band=[…]` | Mapping a buyer id to the display name on screen. |
| 10a | message objects | `[QIANNIU-MEM] new message object: dir=IN\|OUT (reason) uid=… msg=… sendTime=… text=…` | Every new message object once, either direction (v0.9.99yc). |
| 10b | cards / memory changes | `[QIANNIU-MEM] card in memory (not answered): msgType=… summary=…` / `memory changed in pid N: extract={…}` | What each dropped card is; any change in what memory holds (v0.9.99yc). |
| 10c | FIND mode | `[QIANNIU-MEM] FIND '<text>' in pid N: … inside_message_object=… bare_text=… object_keys=[…]`, then `enclosing object:` / `context:` | Only with `ECAN_QIANNIU_FIND` set: exactly how 千牛 holds the operator's test text (v0.9.99yc). |
| 11 | dispatch | `[QIANNIU-MEM] dispatched buyer=… name=… msg=… to N runner(s): '…'` | A new buyer turn went to the agents. WARNING `no agent runner received it` if N=0. |
| 12 | routing | `[QUEUE] sync_task_wait_in_line: event_type=browser_event, sub_type=qianniu_chat` / `[QUEUE] Routed … to task=天猫客服前台001` | Which task took it. Generic runner log. |
| 13 | front-desk prep | `[QIANNIU-FD] event=browser_event -> {"kind": "customer_message", …}` / `event=chat_message -> {"kind": "qa_reply", …}` | Exactly what the LLM gets as input. From the skill's code node. |
| 14 | LLM + tool | `[LLM] …`, `[MCP Auto-Select] Resolved tool: '…' with input: …`, `[MCP] tool=… duration…` | The tool the front desk chose and how long it took. Generic. |
| 15 | hand-off to Q&A | `Resolved tool: 'send_chat'` (FD) → Q&A agent's `[QUEUE] … chat_message` → its `send_chat` back | Generic A2A logs. |
| 16 | OCR capture | `[qianniu] OCR window=… img=WxH lines=N in Xms` / WARNING `capture of the 千牛 window failed` | Every capture. |
| 17 | location check | `[qianniu_check_location] start …`, then `buyer=… on_tab=… matched_by=both\|body\|header\|none header_name=… header_band=[…]` | A miss is a WARNING that carries `screen N lines: text@(x,y) \| …` and keeps a screenshot. |
| 18 | 正在接待 tab | `[qianniu] not on the 正在接待 tab; clicking it at (x,y)` / `after clicking 正在接待: on_tab=…` | Tab switching. |
| 19 | open by name | `[qianniu_open_session] start …`, `[qianniu] open '…': clicking search box at …`, `opened, header …`, result line | A WARNING with the screen dump if there is no search box or the layout is not recognised. |
| 20 | header verify | `[qianniu] header verify OK: … ~ …` / WARNING `header verify MISMATCH: expected …, header band saw […]; screen …` | The header check behind every send. |
| 20a | open by preview | `[qianniu] open by preview '…': clicking row at (x,y) (list name '…')` / `opened, message is in the chat body` / WARNING `no 正在接待 row shows it` / `clicked but the message is not in the chat body` | The hidden-conversation route (v0.9.99yc). |
| 21 | send | `[qianniu_send] start buyer=… auto_open=… expect=… msg_len=…`, `ABORT: …` (with screen dump), `busy: desktop lock held by …`, `sent (already open / opened by preview / opened by name search; body=… header=…)` | The final send step. |
| 22 | heartbeat | `[QIANNIU-MEM] heartbeat pids=… msg_pid=… scan_ms avg=… max=… stats={…} last_scan={…}` | Every 5 min (the first one at start). |

**Calibration fields** (in the first-scan line, the heartbeat's `last_scan`, and
each pass's counters):
- `regions` / `bytes` / `chunk_read_failures` / `capped`: how much memory was read.
- `slices_matched`: memory slices containing a `"sender"` anchor.
- `extract.objects`: JSON objects parsed around anchors.
- `extract.kept`: message candidates. Drop reasons are `no_sender`, `ui_card`,
  `no_uid` and `no_text`.
- `incoming_in_memory` / `outgoing_in_memory`: the direction split.

How to read them:
- `objects > 0, kept = 0, no_text high`: the message body field moved. The logged
  `no_text example keys` show the real keys.
- `slices_matched = 0`: this process holds no chat (wrong process, or no
  conversation loaded).
- Cumulative `stats`: `baseline_seen`, `stale_skipped`, `new_incoming`,
  `dispatched`, `dispatched_to_nobody`, `learn_attempts`, `learned`,
  `scan_errors`.

**Screenshots:** each failed check, header mismatch, refused send or failed open
keeps the OCR'd screenshot. They go to
`<appdata>/runlogs/qianniu_ocr/<time>_<reason>.png`, newest 20, next to the log
the customer already sends. They contain the visible chat, are local only, and
`ECAN_QIANNIU_SAVE_SHOTS=0` turns them off.

### Debugging playbook

| symptom | look at | meaning |
|---|---|---|
| no reaction at all | step 1 | missing → `ECAN_LIVE_CHAT_SITE` lacks `qianniu_chat`, or no restart |
| bundle up, nothing dispatched | steps 3-5, 22 | process found? readable? `slices_matched` / `extract.kept` (calibration fields) |
| messages in memory, none dispatched | steps 7-9, 22 | everything baselined or stale (only messages after start are answered); `incoming_in_memory = 0` with candidates → direction classification |
| dispatched but FD silent | steps 12-13 | routing / pend label (`browserEventLabel` must be `qianniu_chat`) |
| FD dispatched, no Q&A answer | steps 14-15 | empty or stale `qa_agent_ids` → redeploy |
| answer never sent | steps 17-21 + `runlogs/qianniu_ocr/*.png` | which check refused, and the full screen it saw |
| reply landed in 拼多多/飞鸽 | `[DIRECT-DELIVERY] Using cached browser session` for a 天猫 task | `hookBundles` missing from the skill (re-publish) |

---

## 9. Files

Code (this release):
- `cli/deploy/commands.py`: `native_desktop` profile field, `_TMALL_PROFILE`,
  the native-desktop branches in `_deploy_live_chat`, `qa_agent_ids` task-var
  update, and the list-merging `_set_run_env` (`_LIST_ENV_KEYS`,
  `_merged_list_value`).
- `gui/ipc/w2p_handlers/live_chat_site_handler.py`: multi-site switch.
- `gui_v2/src/pages/Settings/components/LiveChatSiteSetting.tsx` +
  `gui_v2/src/i18n/locales/{en-US,zh-CN}.json`: multi-select + hint text.
- Tests listed in section 7.

Code (v0.9.99ya, the observer fixes and logging):
- `qianniu_chat/observer.py`: root-process choice, cold-start baseline, stale
  skip, one-time state logs, heartbeat.
- `qianniu_chat/mem_locator.py`: `seller_id_of` from outgoing messages only,
  extraction drop counters.
- `qianniu_chat/__init__.py`: "not enabled" line.
- `qianniu_chat/_phase0_spike.py`: root-process choice.
- `utils/win_process_memory.py`: optional `stats` on `scan_strings`.
- `agent/mcp/server/qianniu/qianniu_ocr.py`: capture timing, `ocr_dump`,
  `save_failure_shot`, header-verify logs.
- `agent/mcp/server/qianniu/qianniu_tools.py`: step / result logs for every tool.
- Tests: `tests/unit/test_qianniu_observer_process.py`,
  `tests/unit/test_qianniu_observer_logging.py`.

Data (author machine, gitignored — publish from the app):
- `my_skills/淘宝客服前台01_skill/diagram_dir/淘宝客服前台01_skill.json` + `_bundle.json`
  (identical `workFlow` / sheet document).
- `<author>_local/my_prompts/0_pr-731906.json` (千牛客服前台0, `format: md`).

Rollback:
- skill: restore the `.pre_qianniu` backups;
- code: revert the release commit. 天猫客服 then becomes the stub again, and the
  Settings switch goes back to single-select. A merged run.env value keeps
  working on old builds, because `configured_sites` already parses lists.

**Ninth alpha run (v0.9.99yi, 2026-10-07): replies go out; four new problems.**
The skill Update replaced `pr-731906`, and the body-gated send works:
`sent (already open; body=True)`. Our own reply was recognised as
`dir=OUT (our own sent reply)` and the store id was learned. Then:
1. **The first message went to 0 runners.** The observer was up before the
   front desk registered. Fix: a message no runner took is retried for 120 s.
2. **The rating badge `好评100.00%企超级` was learned as the name.** It sits
   next to the real name `sctisz`. Fix: `%` and badge words are rejected.
3. **The column split was wrong on this window.** It has a left nav strip,
   which put the fixed 34% list/body cut at x≈620 while buyer bubbles sit at
   x≈580. The body check rejected the buyer's own message (ABORT), and "open
   by preview" clicked a chat bubble. Fix: `_list_column` takes the list
   bounds from the 正在接待 tab bar and the search box.
4. **The front desk echoed its `qianniu_send` result to the Q&A agent.** The
   Q&A agent answered that JSON ("好的，有需要随时找我～", repeat answers), and
   those went to the buyer. Fix: `send_response_back` never propagates a round
   that ended in a 千牛 delivery tool.

Not code: the Q&A agent's first reply is often the holding phrase
「这边帮您核实一下，稍后回复您。」. RAG (`workspace=''`) found nothing for these
products, so this store needs its own knowledge base.

**Tenth and eleventh alpha runs (v0.9.99yj): the first clean runs.**
- Single buyer: 2/2 answered end-to-end alongside 拼多多 and 飞鸽, in about
  30–36 s per turn.
- Three buyers, minutes apart: every reply went into the right chat, because
  each send matched the buyer's own message in the chat body. Naming broke:
  - new buyer 3163207694 was learned as `sctisz`, which is another buyer's
    name;
  - buyer 54868217 was learned as the timestamp `2026-10-714:51:37`;
  - that buyer's first "message" was the msgType 129 entry notice
    `当前用户来自 商品详情页`, and it was answered.

Fixes (v0.9.99yk):
- the name is the line beside the rating badge;
- timestamps are not names;
- one name, one buyer: a name already held by another buyer is refused, and a
  name stored for two buyers is used for neither;
- `当前用户来自` is a system notice;
- the learn pass logs the header band with positions, so a wrong name can be
  diagnosed from the log.
