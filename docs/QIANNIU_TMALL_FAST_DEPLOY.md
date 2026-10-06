# 天猫 / 淘宝 客服 on 千牛 — Fast Deploy + front-desk skill (v0.9.99x)

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

### Debugging playbook

| symptom | grep | meaning |
|---|---|---|
| no reaction at all | `[qianniu_chat] 千牛 live-chat bundle registered` | missing → `ECAN_LIVE_CHAT_SITE` lacks `qianniu_chat` or no restart |
| bundle up, nothing dispatched | `[QIANNIU-MEM]` | observer not attributing messages (calibration) |
| dispatched but FD silent | `[QIANNIU-FD] event=` | prep never ran → pend label / routing |
| FD dispatched, no Q&A answer | `send_chat` / `Recipient agent not found` | empty or stale `qa_agent_ids` → redeploy |
| answer never sent | `[qianniu_send]` (`ABORT: header` / `body verify failed`) | OCR checks refused — correct, fail-closed; calibrate or name not learned |
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

Data (author machine, gitignored — publish from the app):
- `my_skills/淘宝客服前台01_skill/diagram_dir/淘宝客服前台01_skill.json` + `_bundle.json`
  (identical `workFlow` / sheet document).
- `<author>_local/my_prompts/0_pr-731906.json` (千牛客服前台0, `format: md`).

Rollback:
- skill: restore the `.pre_qianniu` backups;
- code: revert the release commit. 天猫客服 then becomes the stub again, and the
  Settings switch goes back to single-select. A merged run.env value keeps
  working on old builds, because `configured_sites` already parses lists.
