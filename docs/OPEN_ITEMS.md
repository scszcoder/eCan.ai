# Open Items / Tech-Debt Tracker

Running list of known-but-unfixed issues, deferred work, and follow-ups.
Add new items at the top of their section. Mark done with ✅ + date, or
delete once merged and verified.

_Last updated: 2026-10-18_

---

## 🔴 Bugs (unfixed)

### Chat skills lose an in-progress step on app restart — durable checkpoints (2026-10-18)

Desktop compiles every skill with LangGraph's `InMemorySaver` (`agent/checkpointing.py`;
durable sqlite/postgres exist only via `ECAN_CHECKPOINTER`, meant for cloud pods). The run's
`thread_id` is a runtime uuid in `task.metadata["config"]` (`ec_tasks/executor.py:prepare_config`),
never stored, and "parked on an interrupt" is in-memory task status. So a restart loses all run
state.
- **Partly fixed (aa76ab9ac, yar):** opt-in `restore_chat_history: N`
  (`agent/ec_tasks/chat_transcript.py`) reloads the chat's last N messages into `history` on a
  fresh run, so a chat skill (做图经理小李) carries on the conversation after a restart.
- **Still open:** a step in progress at restart is lost — e.g. 小李 parked on `pend_waitWang`
  waiting for 做图专家小王's images: the handoff is gone and the user has to ask again; skill
  attributes (`delivered_images`, `accepted_images`, `job_status`) also reset.
- **Fix = durable checkpoints, as a separate, carefully tested change:** an opt-in per skill
  SQLite checkpointer on desktop; a stored per-(task, chat) `thread_id`; and the runner resuming
  the parked step on the first message after a restart (treat a thread with a pending interrupt
  as `input_required`). Risks to cover: every step writes to disk (keep high-rate skills like the
  Feige front desk off it), all state must be serialisable (`checkpointing.assert_checkpoint_safe`),
  the executor's checkpoint cleanup (`_clear_skill_module_caches`) must not delete a parked
  durable thread, and the other agent's half (小王's job) is lost on restart too.

### Catalog export only exists for Douyin; tmall/pdd 客服 answer with no product KB (2026-10-12)

Response-quality complaints on 客服 (stalls like "稍后回复您 / 看商品详情页" on product-attribute
questions) trace to an **empty 商品知识 base**. The base is filled only by the one-time catalog
export (`cfg.fetch_catalog`, `cli/deploy/commands.py`).
- **Fixed 2026-10-12:** the export was idle-deadlocked on busy stores — it runs on the front
  desk's own browser with `start_after_idle_min:5`, and a live Feige desk never idles 5 min, so
  `_unprompted_run_held` deferred it forever. Added `start_after_idle_max_min:60` (runner caps the
  wait and runs the once-only job anyway). See `runner.py:_unprompted_run_held`,
  `_CATALOG_TASK_SETTINGS`, tests in `test_task_scheduling_rules.py` / `test_deploy_douyin_cs.py`.
- **Still open:** only `douyin_cs` has a `catalog_skill_name` (`抖店商品导出`, which drives
  `fxg.jinritemai.com` — Douyin-only). `tmall_cs` (CS_SCHEMA) and `pdd_cs` (PDD_CS_SCHEMA) have no
  `fetchCatalog` and no exporter skill, so 天猫/拼多多 stores never get a catalog. Needs
  platform-specific exporters (`千牛商品导出`, `拼多多商品导出`) before wiring `catalog_skill_name`
  + `fetchCatalog` on those profiles. Do NOT point them at `抖店商品导出` (wrong backend).

### Real-time promotions: code shipped, two data pieces pending (2026-10-12)

Promotions start/stop through the day, so a daily catalog snapshot can't answer "本月有活动吗"
(it stalled in the yw log). **Code landed 2026-10-12** (all on master):
- Storage: `knowledge/ks/promo_snapshots.py` (per-store JSON, auto-applied, TTL-trusted 90 min) +
  `KnowledgeService.set_promos/get_promos/promo_line`; the skill calls `apply_snapshot(...)`.
- Deploy: `_DDCS_PROFILE.promo_skill_name="抖店营销导出"` + a recurring (every-30-min) background
  task (`活动刷新`), opt-in via `fetch_promos` (on by default in `DOUYIN_CS_SCHEMA`). Reuses the
  idle cap (`start_after_idle_min:2`, `start_after_idle_max_min:10`).
- Q&A injection: the front desk hands Q&A a dated `[当前活动] 截至HH:MM：…` line next to
  `[商品卡片]` — **Feige** path (`feige_chat/actionable_items.py:_promo_line_for`, the live 抖店
  front desk) and the 千牛 path (`qianniu_chat/direct_qa.py`, for when tmall gets a promo skill).
- **Still pending (data, user builds in the editor):** (1) the `抖店营销导出` skill — read 抖店
  营销中心, call `apply_snapshot(store_id, promotions=…, summary=…, source="抖店营销中心")`; publish
  as public+rentable so the deploy finds it by name. (2) the Q&A prompt (`飞鸽客服问答00`) must read
  `[当前活动]` and prefer it (or a just-seen card) over a stale 3 h product card for 活动/价格.
- Only `douyin_cs` has a promo skill; tmall/pdd need their own 营销 readers (closed-env for 千牛).

### Left open after multi-task agents, agent pools and lazy agents (2026-10-11)

Shipped 2026-10-10/11 (all on master): resource gate + scheduling rules + "after task" trigger +
task-editor run rules (Phases 1-4); in-process A2A delivery in core, one shared A2A server,
agents with no tasks built on first use (5a-5c); least-busy Q&A pick, pool sizing/metrics,
demand-sized active set + 问答客服池 panel, `pick_for_customer` for 千牛 (6a-6d); staged catalog
imports + run_once / start_after_idle_min + 快速生成 product-export option (7b). Design notes:
the agent scheduler/pool memory and the commit messages.

- **Not exercised by live chat yet** (no LLM balance on the dev machine): in-process A2A delivery
  (`[a2a_local] in-process ->`), the shared A2A server under real traffic, pool picks and the
  controller (`[agent-pool]`). Before a customer build: one Feige/千牛 session with 3+ customers.
  Kill switches: `ECAN_A2A_LOCAL_FASTPATH=0`, `ECAN_A2A_SHARED_SERVER=0`, `ECAN_LAZY_AGENTS=0`,
  `ECAN_POOL_PICK=0`, `ECAN_POOL_SCALING=0`, `ECAN_TASK_RESOURCE_GATE=0`.
- **TODO (agreed 2026-10-11): pool scale-down to a real stop.** Pools park, they don't stop: a
  parked member keeps its task-loop thread, memory worker, LLM clients and A2A registration.
  Now that a stopped agent can be replaced by a fresh one built from the DB (`_swap_agent`,
  re-enable), add a third tier: active -> parked (warm) -> stopped (cold).
  1. **Measure first** (logging is in: `[agent-cost]` lines in runlogs/memory.log — build, start,
     start after 10 s, stop after 3 s + gc, with the thread families added/removed). Read the
     median per Q&A agent from a normal startup, plus one isolated restart (`ecan agents update
     <qa agent> -d <same text>` stops and rebuilds it).
     **Measured 2026-10-11 (idle agents, no chat yet):** build 2-4 MB each (sequential, clean);
     isolated restart of 客服小敏: start +0.1 MB, +2 threads (`MemoryMgr-<agent>`, task-loop pool
     thread), a `SkillExec` thread appears on its first run; stop freed those threads, RSS moved
     within GC noise (+-20 MB). **Decision: parking is enough for idle members.** Re-measure
     after a live chat session (an agent that has answered turns may hold LLM clients / caches):
     restart one Q&A agent the same way and read its `[agent-cost] stop` line.
  2. **Then decide:** worth it if a Q&A agent costs ~30-50 MB+ and a few threads. Proposed rules:
     stop a member parked >= 30 min when the hourly forecast says it won't be needed in the next
     30-60 min; always keep min active + 1 warm spare; never stop one with a turn running/queued or
     active in another front desk's pool; rebuild cold members ~10 min before a forecast peak.
- **Shared Q&A pool across stores (done 2026-10-11, not live-tested; docs/SHARED_QA_POOL.md).** 快速生成 → 客服 for a store
  of 抖店/拼多多 when another store of the platform already has Q&A agents: "与本平台其他店铺共享问答客服"
  is on by default (pool picker when several, "新增问答客服" count); the new store gets its own
  front desk, the existing Q&A tasks accept it (`front_desk_agent_id` list) and drop their own
  store, the front desks' pool size covers all members (`_share_pool`, `cs_pools`,
  IPC `fast_deploy.cs_pools`). Pool controller sizes front desks sharing members as one group.
  Each shared turn answers for the store that dispatched it (`resolve_store_id` reads the
  dispatch JSON's `store_id`; KS policies/products follow; the LLM's tool args can't name the
  store inside a run). 千牛 excluded (one store per machine). Open:
  - **Live test with two stores** (two 抖店 logins, one shared pool): answers use each store's
    policies/products; `[agent-pool]` shows one group.
  - Usage/metering of a shared turn carries the asking store (runner `_scope_turn_store`,
    per turn, in the turn's own context copy) -- unit-tested, not live.
  - Takes effect after an app restart (running Q&A tasks keep their old front desk list).
  - `douyin_cs_multi`/`pdd_cs_multi` (CLI only) still create the old shape (shared Q&A tasks
    with no store, several stores in one deploy); same result, different entry point.
- ~~"after task" finishes survive a restart~~ done 2026-10-11: a prerequisite saves `last_finish`,
  a dependent saves `after_consumed_at` (task settings); the runner's tracker is seeded from them.
  A dependent that should have started when its prerequisite finished, but the app died in that
  instant, is not started at the next launch (it runs at the prerequisite's next finish).
- **Lazy agents: any new loop over ALL agents must read only `LazyAgent._CHEAP` attributes**, or it
  builds every deferred agent (three such scans were found live; the audit list is in the 5c
  commits). Symptom: `[lazy-agent] building '<name>' on first use (... from <file:line>)` for many
  agents at once.
- **`抖店商品导出` skill (data, my_skills) is unverified on a real 抖店 backend** — permission of the
  store login for 商品管理, the real button labels, where the download lands. Its owner is split:
  the file says `wechat_b603…`, the DB/cloud record is `wechat_o3YB…` (created while logged in as
  o3YB). Fix: log in as b603, give the file a new `skillId`, save in the Skill Editor, delete the
  o3YB copy (Fast Deploy finds the skill by exact name).
- **CLI → running app (docs/LOCAL_API.md)**: verified live on 2026-10-11 with a throwaway agent
  测试 (CLI run as the app's user via `ECAN_CLI_USER`): read commands, tasks add/update/remove and
  agents update/remove through the app, `agents run` (chat delivered), `agents stop`, pin error path.
  `tasks execute` re-tested after the fix: one loop started, a second execute reused it (2 runs,
  1 loop); deleting the agent stopped it. **Not yet live:** `agents pool --pin` on a real front
  desk (needs a front desk that has dispatched). `ecan agents add` still writes the database
  directly.
- **Saving a running agent now restarts it** (`_swap_agent`): a turn in progress at that moment is
  cut off. Before, the rebuilt copy never started and the old one kept running out of sight.
- **抖店 export column mapping untuned** (7a): needs one real export file.
- **Staged import copies are kept after import** (`knowledge_service/staged_imports/`): the import
  job reads the file after the review list drops it. Prune old copies later.
- A `queue_one` scheduled run due while its task is parked on input is dropped by the existing
  parked-task guard.
- **A Q&A agent with no chat skill can't answer a direct chat** (客服小晴: `No chat skill found …
  cannot auto-create chatter task`) — setup question, not lazy-agent related.
- **Full suite, 2026-10-11** (every file under tests/, tests/unit, tests/ks, one pytest per file,
  skipping the known aborter test_ota_path_safety and the hanging inflight-race test): 428 files,
  155 failing tests in 69 files. 9 are environment (async tests: pytest-asyncio not active on the
  Python 3.14 dev env, "async def functions are not natively supported"); the other 146 fail the
  same on the commit before this work (9ad66e8a1, compared test by test; untracked test files
  copied in) — mostly release/CI workflow, Feige source-structure and setup-prereq tests.
  None was introduced by the work above. Notable ones:
  `test_submit_task_execution_race::test_submit_allows_feige_response_when_input_required_future_running`;
  `test_frontdesk_dispatch_inflight_race.py` hangs > 300 s; `test_direct_feige_delivery_worker`
  (5); `test_mt038_attachment_marker_rescue` (5); `test_dom_echo_text_baseline` (1);
  `test_feige_turn_metadata` (1); `test_phase_c_store_dimension` (migration chain 3.1.8 vs 3.1.7);
  `SearchFilter.test.tsx` (1); collection errors in `tests/integration/test_a2a_skill_execution.py`
  and `tests/test_product_listing_orchestrator_skill.py`.

### Left open after the rag-enterprise merge + Fast Deploy rework (2026-10-10)

- **`tests/ks` breaks later suites in the same run.** `pytest tests/unit/test_deploy_douyin_cs.py tests/ks`
  collects only 11 tests and 5 deploy tests fail on message-language regexes (also on master
  before the Fast Deploy change). Likely a `tests/ks` fixture leaking app region/language state.
  Run `tests/ks` in its own pytest invocation until fixed.
- **Fast Deploy no longer offers the "several stores" tiles** (`douyin_cs_multi`, `pdd_cs_multi`).
  Each store is deployed on its own from its platform button, so a second store gets its own
  Q&A agents instead of sharing one pool. The CLI scenarios still exist; add a "share Q&A agents
  with this platform's other stores" option under 客服 if merchants need it.
- **Fast Deploy areas 售前/售后/营销/调研/经理 are placeholders** (grayed). 京东 has no 客服 recipe yet; for 京东
  and 其他平台 (custom platform name) Generate only creates the store.
- **Desktop memory footprint ~1.7-1.9 GB, ~300 threads** (memory.log, 2026-10-10). Not a leak: it
  plateaus (14:08 run flat at 1.63-1.70 GB for 40 min). Startup ramps 0.57 -> 1.25 GB in 30 s; opening
  the Knowledge page adds ~200 MB and ~150 threads (likely the KS embedder and its thread pools).
  Worth slimming: lazy-load the embedder, cap onnx/torch threads.
- KS server security fixes: brief handed to the server side (authz headers, audit tenant, verified
  email, cross-tenant store checks, deploy/ks move to eCan_lambda).

### Left open after the chip-docs crawler / platoon / cloud work (2026-10-09)

- **An offline pinned host's agents are adopted elsewhere.** `agent_launch_allowed`
  adopts a pin that no *known* host owns; a host is "known" by a local vehicle row
  or (since 2026-10-09) a live LAN advert. If the Commander is off when a Platoon
  starts, the Platoon adopts and runs the Commander's agents (seen: the coordinator
  started on the Platoon). Start order avoids it today. Fix idea: also treat any id
  in the cloud vehicles list as a known host (`vehicle_affinity._pin_belongs_to_other_host`).
- **Merged agents are not saved locally on a fresh machine:** `DBAgent(**agent_dict)`
  in `gui/MainGUI.py` (merge step) fails with "'card' is an invalid keyword argument".
- **Task→skill fallback matching is fragile:** when the id does not match,
  `agent_converter` falls back to name prefix / shared words and can pick the wrong
  skill (`chip_docs_crawl_1` → `chip_docs_crawl_manager_00`). Ids now match for file
  skills; the heuristics remain.
- **llm-proxy does not enforce the action schema** for `gpt-5.6-sol`: the model
  invents argument names (`search_page.query`, `evaluate.expression`) and wastes steps.
  Server-side (llm-proxy repo).
- **Fresh intl installs:** no llm-proxy default endpoint and empty `wan/ws_api_endpoint`
  until an interactive login writes them; the app now falls back to the session-token
  llm-proxy for LLMs once an endpoint exists. Decide whether intl ships a default
  like CN does.
- **Cloud worker (AWS):** proof works with one hand-launched Fargate task
  (`ecan-cloud-worker-proof:1`). Missing for production: a service credential for the
  llm-proxy (proof used the user's IdToken), cloud-to-cloud messaging for a cloud
  coordinator, launching N workers, the runCloudTasks resolver forwarding task_vars.
  Live worker image `:latest` is from 2026-02; its task env holds direct provider keys.
- **Dev venv drift:** a venv with PySide6 6.9.1 hid the bu_run_code crash that the
  pinned 6.10.1 triggers — keep dev venvs on requirements-base.txt.

### An orphaned Chromium from a killed app blocks every browser launch on its profile (2026-10-09)

When the app is force-killed (or crashes), the Chromium it launched for a
"new chromium" browser node can survive and keep `browser_profiles/<name>` in
use. On the next start every launch on that profile fails after 30 s
(`LocalBrowserWatchdog.on_BrowserLaunchEvent` TimeoutError) and a looping node
retries forever. `ProfileLockCleaner` reported the profile "not locked" — it
checks the lock file, not a live process using the directory. Fix idea: at
startup (or on a launch timeout), find chrome.exe processes whose
`--user-data-dir` is one of OUR profile dirs and whose parent is gone, and
kill them. Repro 2026-10-09: chip-docs coordinator, orphan PID from 14:46.

### ✅ FIXED — two stores' browsers started on 9228 and closed each other (2026-10-04)

Customer run 99r ("Chrome 闪退"): the 抖店 and 拼多多 front desks started together;
`BrowserManager.acquire_browser` turned their "auto" CDP port into the
plain-Chrome slot pool's 9228 for both, both launched there, each found the
other's browser answering, refused it and terminated its own. Fixed: a profile
browser on auto keeps port 0 (free OS port), and `launch_profile` is serialized
in-process. Reuse/relaunch rules and the one-browser-per-store layout are written
up in [OWN_FINGERPRINT_BROWSER.md](OWN_FINGERPRINT_BROWSER.md) ("Reuse or
relaunch", "Several stores on one machine").

### ✅ FIXED — a migration that adds a table froze startup on its own lock (2026-09-25)

A 98w customer (DB at 3.1.6) could not get past the startup spinner: each
migration step's "create missing tables" ran on a SECOND connection while the
migration session already held SQLite's write lock (its migration-log row was
flushed), so every step waited out the 60s busy timeout. 3.1.6 -> 3.1.8 = two
steps = ~2 minutes frozen; the app was closed before the version was recorded,
so every start repeated it. Reproduced at 130.9s; fixed (0.0s) by creating the
missing tables on the migration session's own connection and committing
(agent/db/migrations/migration_manager.py, tests/test_migration_no_self_lock.py).

### A saved task edit does not reach the agent holding the task until restart (2026-09-23)

`save_agent_task` writes the DB, syncs the cloud, and replaces the task in
`mainwin.agent_tasks` (`_update_agent_task_in_memory` in
`gui/ipc/w2p_handlers/task_handler.py`) — but each agent's `agent.tasks` keeps
its own object. The runner reads `task2run.metadata` from there, so an edited
`task_vars` value (e.g. `store_id`) is not used by the next run, and the store
reporter (`agent/ec_agents/store_reporter.py`) does not see it, until the app
restarts. Seen live tagging `task_570fda777488452e` with a test `store_id`: six
heartbeats, no report; after restart it appeared. Fix: replace the object in
the owning agent's `tasks` too (or have agents hold ids, not copies).

### ⚡ NEXT UP — Feige Q&A input-token cost (2026-09-15)

**~11,000 input tokens per customer query, of which the customer's own message is
under 1.5%.** Full measurement and method in
[FEIGE_QA_TOKEN_COST.md](FEIGE_QA_TOKEN_COST.md) (52 queries across two customer
logs). Input:output runs ~95:1, so all the money is prompt. Do these in order:

1. **Fold the RAG decision into the classifier.** It already emits
   `{"needs_rag":…,"category":…}`; the separate `rag_query` call pays the full
   3.1k-token Q&A prompt to emit a 46-token tool call. **−3.0k/query (−27%).**
2. **Stop carrying the classifier's system prompt into the rag and answer calls.**
   It stays in `recent_context` and instructs a classifier that already ran.
   **−1 to −2k/query.** Context-assembly leak, not prompt authoring.
3. **Move `{{input}}` / `{{events}}` out of the Q&A system prompt.** `{{input}}` sits
   at char 2,223 of 11,426 (19% in), so the stable prefix is ~600 tokens — under the
   1,024-token floor for automatic prompt caching. **Cache hit rate is 0% today.**
   The same text is already the user message, so the turn is also sent twice.
   After the move the ~3.1k-token prompt is a stable prefix and measured call
   spacing predicts a **~75-80%** hit rate.
4. **Skip the classifier for greetings** (also the biggest latency win — see the
   cloud-serving item below).
5. **Trim the template**: the five largest sections are 7.4k of its 11.4k chars.

Steps 1+2 take ~11k → ~6.5k; step 3 makes most of the remainder cacheable.

**Unverified**: that the CN llm-proxy passes caching through at all. Every usage
record logs `'prompt_tokens_details': None`. Test by sending an identical prompt
twice inside a minute and checking for a non-null `cached_tokens`.

### deepseek needs a json_object shim to drive browser-use (2026-09-17)

deepseek supports json_object but NOT json_schema, and the proxy maps our
`output_schema` onto json_schema -- the unavailable one. Measured against the
live proxy:

| request shape | deepseek-v4-flash | deepseek-v4-pro |
|---|---|---|
| `output_schema` (what ChatLambdaProxy sends) | 400 unavailable | 400 unavailable |
| `response_format: json_schema` | 400 unavailable | 400 unavailable |
| `response_format: json_object` | 400 "prompt must contain the word 'json'" | same |
| `json_object` **+ the word "json" in the prompt** | **200 `{"ok": true}`** | **200 `{"ok": true}`** |
| no structure | 200 | 200 |

qwen3.7-plus and qwen3.8-flash both return 200 for `output_schema`, so this is
a deepseek/provider gap, not a proxy bug.

Today every step call 400s and browser-use retries, so a run crawls even
though deepseek answers in 2-3s against qwen's 8-16s -- it is 4-5x faster per
call and unusable overall. (Plain LLM nodes needing no schema are unaffected.)

A client-side shim would make it work, for providers that cannot do
json_schema: send `response_format: {"type": "json_object"}`, render the
schema into the prompt as instructions, make sure the literal word "json"
appears (deepseek rejects the mode otherwise), then validate the reply against
the pydantic model on our side and retry on mismatch. json_object guarantees
VALID json, not json matching the action model, so the client-side validation
is the whole point -- without it browser-use gets well-formed garbage.

Needs a per-model capability map (which shape each model accepts) rather than
a global switch. ~60-100 lines in `ChatLambdaProxy`. Worth it for the latency;
not worth blocking the eBay skill on.

Probe, if this needs re-checking: POST /api/llm-proxy/v1/chat/completions with
each shape and compare status codes across models. `/v1/models` needs the
ACCOUNT API KEY, not the session token.

### ✅ FIXED — a failing MCP tool was propagated as a success (2026-09-17)

A tool missing from `tool_function_mapping` logs an ERROR and is then reported
as a SUCCESS to everything upstream:

    [unified_tool_handler] Tool 'bu_send_email' not found in tool_function_mapping!
    [MCP Result Propagation] tool=bu_send_email success=True
                             work_result={'last_action_succeeded': True}
    [MCP Multi-Tool] Completed 1 tool(s) (1 succeeded)

The node, the multi-tool executor and the run summary all say the email was
sent. Nothing arrived. A missing tool must fail the call, not pass it —
"1 succeeded" that means "1 silently did nothing" is worse than no tool at all,
because it stops anyone looking.

Related and worth fixing together: **no `bu_*` tool is in
`tool_function_mapping`** — zero of them. Every browser-use extension action
(`bu_send_email`, `bu_send_sms`, `bu_send_chat`, `bu_rag_query`, …) is callable
from a browser node and invisible to an MCP node. `MCP_TOOL_AUTO_SELECT.md`
step 6 already warns that skipping this registry makes a tool "fail at runtime
even though everything else looks wired correctly"; the whole `bu_*` family
skipped it.

Workaround in place: the skill's prompt and the synthesised report email both
call `send_email` (MCP-registered, canonical `{"input": {...}}` wrapper,
cc accepts a comma string) instead of `bu_send_email`.

**Fixed** in the result-propagation and multi-tool paths: a result whose text
starts with `❌` or `Error:` is now treated as a failure. `isError` alone was
not enough — it is set only when a handler RAISES, and these tools catch their
own failures and return the error as text. A second real case proved the point
minutes later: `❌ Email send failed: ... FailedOperation.InvalidTemplateID`
was still reported as "Completed 1 tool(s) (1 succeeded)".

STILL OPEN, and the underlying cause: **no `bu_*` tool is in
`tool_function_mapping`** — zero of them, so the whole browser-use extension
family is invisible to MCP nodes.

### ✅ DONE — deepseek runs on native tool-calling (2026-09-17)

The shim in `ChatLambdaProxy` (279d8f00c) works, but it is not the most direct
route. Measured against the live proxy:

| request shape | deepseek-v4-flash / -pro |
|---|---|
| `output_schema` / `response_format: json_schema` | 400 "This response_format type is unavailable now" — **even with thinking disabled** |
| `response_format: json_object` | 400 unless the prompt contains the word "json" |
| `tools` + forced `tool_choice` | 400 **"Thinking mode does not support this tool_choice"** |
| `tools` + forced `tool_choice` + `thinking: {"type":"disabled"}` | **200, real `tool_calls` returned** |
| same + `reasoning_effort: "none"` | **200, real `tool_calls` returned** |

So deepseek never supports json_schema, but it DOES support native function
calling with a forced tool_choice — the blocker was thinking mode, not tool
support. Two switches turn it off: `thinking: {"type": "disabled"}` or
`reasoning_effort: "none"`.

Why that is better than the shim:
- The PROVIDER enforces the argument schema, instead of us rendering the schema
  into the prompt and validating after the fact.
- The schema stops riding in the prompt on every step (~10KB now, ~66KB on a
  node with no action filter — see the payload-cap item).
- It is the standard OpenAI-compatible mechanism, so it generalises to other
  providers that reject json_schema but do support tools.

**Implemented in 3ced3f6db**; the json_object shim is removed. Verified
against the live proxy with a real multi-field action model — deepseek-v4-flash,
deepseek-v4-pro, qwen3.7-plus and qwen3.8-flash all return a validated object.

Still open: thinking is off on the tool path, so there is no reasoning trace.
Effect on multi-step browser reasoning is UNMEASURED — deepseek's decisiveness
on the proxy-failure test may partly come from thinking. Worth a head-to-head
on a real task once the proxy is up.

### Structured-output coverage gaps (2026-09-17)

Applies to ANY skill, not just eBay — it is in `ChatLambdaProxy.ainvoke`, gated
on model name only, and all four construction sites are in
`browser_node/runner.py`. It does NOT cover:

- **LLM nodes**, which use `lambda_proxy_langchain.py` (a different class, no
  shim) and mention `with_structured_output` consumers.
- **Cloud/serving workers**, which never import `ChatLambdaProxy`.
- Direct provider calls that bypass the proxy.

Both former scenario limits are GONE with native tool-calling: the schema no
longer rides in the prompt (so the hidden dependency on the action filter is
resolved) and the provider enforces it (so the guarantee is no longer weaker).
The coverage gaps above remain — a deepseek LLM node or cloud worker still has
no structured-output path.

### Platform-purity regression: a live-chat hook ran during an eBay run (2026-09-17)

`agent/chats/wan_a2a_chat.py` registered the live-chat page-refresh handler
unconditionally, on a WAN-connectivity callback. The bundle's bridge exists
whenever a live-chat bundle is IMPORTABLE -- which it is as soon as any
live-chat skill sits in the workspace, running or not -- so the handler
registered on every app start and fired on every WAN flap, for every customer.

Seen during an eBay AdsPower run with nothing live-chat about it:

    [wan_a2a:TCB] WebSocket closed normally   x5
    [feige_page_refresh] no Feige tab in browser; operator may have closed it
    [feige_page_refresh] ... (again, 67s later)

It reached into `cached_browser_sessions` -- its own comment says "any session
that's open will do" -- and walked the shared cache, including the eBay
AdsPower session, before deciding there was no live-chat tab and skipping.
Site-specific code touching a SHARED structure mid-run is exactly what the
2026-08-02 bundle split exists to prevent, and the enforcement grep in
`feedback_keep_core_general_feige_in_hooks` does not catch it because the
module is correctly quarantined -- it is the REGISTRATION that leaked onto a
platform path.

Fixed: registration is now opt-in via `ECAN_LIVE_CHAT_PAGE_REFRESH`, resolved
through `live_chat_dispatch.live_chat_env()` which already aliases a bundle's
legacy `ECAN_<SITE>_PAGE_REFRESH` spelling.

**BEHAVIOUR CHANGE for live-chat deployments:** unset now means OFF where it
previously meant ON. A deployment that already sets `ECAN_FEIGE_PAGE_REFRESH=1`
is unaffected; one relying on the default-on must now set it explicitly.

NOT established: whether this contributed to the worker-thread handoff stall
observed in the same run. It logged "skipping" and runs on its own thread, but
it does enumerate the same shared session cache the stalled handoff uses, so
it was worth removing from the picture before investigating that.

### qwen3.7-plus follows the output contract but not the handoff block (2026-09-17)

Five runs of the SAME prompt against the SAME broken proxy, changing nothing
between them:

| run | emitted handoff block |
|---|---|
| 1 | no  |
| 2 | yes |
| 3 | no  |
| 4 | no  |
| 5 | yes |

Roughly a coin flip. Everything ELSE in the contract was produced correctly
every single time: `task_completed`, `system_errors` with an accurate
`ERR_PROXY_CONNECTION_FAILED` diagnosis, `work_summery`, `work_done`,
`all_done`. It is specifically the SECOND json object -- the tool-call block
appended after the contract -- that gets dropped.

Moving the requirement next to the `all_done` line (where the model is already
deciding the turn is over) rather than in its own section at the end of a
9.3k-char prompt improved it but did not fix it.

Reading of it: a single trailing "and also emit this other object" instruction
is weak against a model that has just produced what looks like a complete
answer. Worth comparing other models before spending more on prompt wording --
if a model emits it reliably, that is a cheaper answer than either prose or
code.

Mitigated in code by the synthesised report email (`a73c9ed1a`), so a dropped
block no longer means a silent run. That is a floor, not a fix: the labels
still only get reformatted and printed when the model emits the block itself.

### Prompts exist in two places that never reconcile (2026-09-17)

A prompt lives BOTH in the cloud (`queryPrompts`/`updatePrompts`) and on disk at
`<user>_local/my_prompts/<name>_<id>.json`. Nothing reconciles them, and the
desktop reads only the file.

`_load_prompt_data` (`agent/ec_skills/build_node.py`) tries the CN GraphQL path
first, but that path is gated on `ECAN_CN_GRAPHQL_ENDPOINT` +
`ECAN_TCB_ACCESS_TOKEN` — env vars only a serving pod sets. On the desktop it
returns None every time and falls through to the local GUI loader. So the cloud
branch is effectively dead code on desktop, and a cloud-side prompt edit has no
effect there at all.

Cost, 2026-09-17: updated `pr-665505` in the cloud (5173 -> 8682 chars,
confirmed `success: true` and re-read back), then watched the next run log
`Resolved prompts - system: 5172 chars` and spent a while assuming a cache. The
app had simply read the file, which still held the old text.

Fix options, roughly in order of value:
- Have the desktop resolve prompts through the same cloud path it uses for
  everything else (it already holds a valid session token), or
- make the local file authoritative and push edits cloud-ward on save, or
- at minimum log WHICH source a prompt was resolved from and its length, so a
  divergence is visible in one line instead of inferred.

See `EBAY_AFTER_SALES_PROMPT_CONTRACT.md` for where the copies live and how to
edit each.

### Skill-editor canvas keeps showing a node as "running" after a run ends (2026-09-17)

A node's running indicator never clears when the run ends without a completion
event for that node -- a failed node, an aborted graph, or a node the graph
never reached. The badge then sits on the canvas indefinitely and reads exactly
like a live run.

Observed 2026-09-17: the canvas showed the running man on the trailing MCP node
(`mcp_sN5l7`) while the backend had executed NOTHING in that session -- zero
`Executing node`, zero `astream_run`, zero `[BA._auto] dispatch` in the whole
log. The only canvas activity was `SmartLinesPlugin` patching edges, i.e.
drawing the diagram. The stale badge was left over from the previous run, whose
browser node returned `success: False`.

Cost: it is indistinguishable from a real run, so you reason about a run that
never happened. Fix by clearing per-node run state when a run terminates for any
reason (not just success), and on canvas load.

### Terminal llm-proxy errors do not stop the agent loop (2026-09-16)

`insufficient_balance` (402) and `EXCEED_MAX_PAYLOAD_SIZE` (413) cannot change
mid-run, yet browser-use retried each 5-6 times -- 12 real HTTP round-trips for
one unchanging answer, and 6 identical error lines instead of one actionable
message. `agent/ec_skills/llm_utils/proxy_errors.py` already documents the rule
("the balance only moves via top-up, so callers must not retry") and
`ChatLambdaProxy` honours it (retries 5xx only); the browser-use failure loop
above it does not. Needs a terminal-error signal the agent loop respects.

### Action schema dominates the llm-proxy request body (2026-09-16)

Measured split of a 107KB body: `output_schema=66.4KB messages=40.7KB`, i.e.
**62% is the tool schema** -- 57 registered actions at ~1.2KB each, serialized on
EVERY step. The page was only 17.7KB of it. CloudBase's gateway caps the body at
~100KB, so this 413'd.

Fixed for the eBay node by the new per-node action filter (`allowedActions` /
`excludedActions`): 57 -> 10 actions, schema 66.2KB -> 6.8KB, body -> ~48KB.
See `BROWSER_AUTOMATION_ADSPOWER_POSTMORTEM.md` §7.

Still open:
- Every OTHER browser node still ships all 57 actions and pays ~66KB per step in
  both payload and input tokens. Roll the filter out.
- `allowedActions` / `excludedActions` have no node-editor field yet; they can
  only be set by editing the skill bundle JSON.
- The ~100KB cap itself still stands for any node that genuinely needs many
  tools.

### browser_use_settings.json `browserSessionSettings` is still unread (2026-09-16)

`agentSettings.eventTimeouts` now reaches the runtime via
`apply_browser_use_event_timeouts()`, but `browserSessionSettings` (headless,
wait_* timings, highlight_elements, keep_alive...) still has no consumer -- the
Settings page writes knobs that change nothing.

### Cloud SDL gaps surfacing on every skill/task sync (2026-09-16)

- `SkillUpdateInput` has no `need_inputs`, so every skill sync fails with
  `Field "need_inputs" is not defined by type "SkillUpdateInput"` -- this is the
  client-side prompt-variable feature having nowhere to land.
- `TaskSkillRelation.owner` is a required `String!` even though every other
  resolver derives owner from `identity.sub`; `addAgentTaskSkillRels` fails on
  every run and drops to the failed queue.
- `agentSkill.create` hits `Unique constraint failed on the fields: (id)` on
  repeat sync.

### Payment page receives the bearer as a URL query parameter (2026-09-16)

`handle_payment_topup` appends the user's token to the payment URL as
`?token=<jwt>` (`gui/ipc/w2p_handlers/payment_handler.py`). A token in a query
string is written down in places we do not control: the webview's history, the
`Referer` header on anything the page loads afterwards, and every access log on
the path. Rotating it is the only remedy once it has leaked.

Why it is there: the desktop's embedded webview is an OTR profile with no site
session cookie, so the page cannot identify the payer unless the client hands it
the bearer; without it the page charges anonymously and nothing is credited (the
¥0.01 order-'' incident).

Fix — needs the payment PHP changed in lockstep, so it is not a one-liner:
either POST the token as form data into the page, or have the client exchange it
for a short-lived single-use code and put only that in the URL.

Adjacent, and fixed 2026-09-16: the token was also sent *expired*, because
`get_tokens()` returns what is stored without checking `exp`. `ensure_valid_tokens()`
now runs first. That is a staleness fix, not a confidentiality one — this item
stands on its own.

### Cloud skill serving / customer-chat demo (2026-09-14)

Working end to end — see `docs/CLOUD_SKILL_SERVING_POSTMORTEM.md`. These are
what is left, roughly in the order they are worth doing.

- **The skill runs a classifier LLM before answering** — `{"needs_rag": false,
  "category": "greeting"}`, 1568 input tokens, ~1.5-2.5s, on **every** turn
  including 你好. That is ~75% of a warm 6-7s turn. **Prompt change, owner's
  side**: skip the classifier for short greetings or fold the routing into the
  answer call. Biggest single latency win available.
- **The reply envelope carries literal `<customer_id>` / `<customer_name>`
  placeholders** — nothing substitutes them on the serving path, so the skill
  still believes it is talking to Feige. Harmless to the visible reply (the
  serving lane reads `response_text`), but wrong. Either drop them for web or
  have the runtime fill them from the turn, which knows `owner` and
  `conversationId`.
- **`send_chat` still fails on the A2A lane for skills that name a recipient
  that does not exist on this path.** The serving lane only triggers when there
  is NO recipient. A skill that hardcodes one still errors.
- **Orphaned Python pod handlers still point at the wrong table.**
  `get_pods`/`save_pod`/`delete_pod` in `gui/ipc/w2p_handlers/vehicle_handler.py`
  plus the `agent/cloud_api` vehicle generators use `queryVehicles`/`addVehicles`
  — the OBSERVED-state `vehicles` table that `c4079271a` moved the client off.
  Nothing calls them today (`IPCAPI.getPods` routes to `callAccountManager`), so
  they are inert, but anything that calls them again writes a pod no Deployment
  is built from. ~200 lines plus the now-pointless `isWeb()` branch in
  `podService.ts`. **Removal agreed in principle, not done.**
- **`langgraph-checkpoint-postgres` is in no `requirements-*.txt`**, so
  `ECAN_CHECKPOINTER=postgres` raises `CheckpointerUnavailable` at import and the
  pods run `ECAN_SERVE_ALLOW_EPHEMERAL=1` — in-flight conversations die with the
  pod. One line, client-side. Does not block today because a serving turn
  resumes inside a single call and never needs the checkpoint to outlive the pod.
- **Each pod has its own skill cache and its own cold start**, so N pods means N
  first-turn misses (measured: turn 2 of 4 was a miss because it landed on the
  other pod). Argues for sticky routing by conversation — `vehicleHint` already
  exists on the turn.
- **A serving pod imports the whole desktop agent stack** — browser-use with 53
  registered actions, the Feige hook bundle, the IPC registry — to answer a text
  message. ~14s of the cold start. Irrelevant for long-lived pods; becomes
  per-wake cost if `on_demand` pods that scale to zero are ever used.
- **The pod cannot push node-status updates**: `[IPCAPI] No WebSocket manager
  available, dropping push: update_skill_run_stat`. A live chat UI will not
  stream progress even though the answer works.
- **`[HYBRID] Async execution failed, falling back to sync`** fires on every
  turn. Working, but the fallback is not free and the message suggests it is not
  intended.
- **No `turn_get` read action** on ecbAccountManager (only enqueue/claim/
  heartbeat/done/route/send), so a turn's stored `result` cannot be verified
  server-side — only inferred from pod logs. Backend-side.
- **`tests/test_skill_e2e_resume.py` fails collection outright** — it hardcodes
  `\Users\liuqiang\WorkSpace\ecan\eCan.ai` at line 29. Pre-existing, breaks
  any pytest run that includes it.
- **10 pre-existing Feige test failures**, verified unrelated to this work by
  re-running with the changes reverted: 5 in `test_direct_feige_delivery_worker`
  (the local `resolve_target()` stub does not accept the `customer_key` argument
  production passes) and 5 across `test_feige_send_lock` /
  `test_feige_turn_metadata` / `test_feige_flood_hardening`.
- **CVM disk at 90%** (7.7 GB free). Each worker image is ~6 GB. The two real
  consumers are `~/html/workbench` (11 GB) and `.vscode-server` (5.8 GB).
- **GitHub is unreliable from the CVM** — `expected flush after ref listing`,
  and connect timeouts after 135s. Dangerous because `git merge --ff-only` then
  reports "Already up to date" against a stale ref and the build tags a SHA it
  does not contain. No Gitee mirror is configured on that checkout.

- **Pod desired state has no cloud columns — backend SDL gap (2026-09-13)**.
  Pods are now cloud-backed (`save_pod`/`get_pods`/`delete_pod` read and write
  `addVehicles`/`queryVehicles`/`removeVehicles`), but `lifecycle`,
  `idle_shutdown_minutes` and `desired_replicas` exist on no cloud type —
  not CN `Vehicle`/`VehicleInput`/`VehicleUpdateInput`
  (`eCan_lambda/cn/tencent/cloudbase-graphql/scf/index.js:493,1198,1229`), and
  AWS has no `VehicleInput` at all. Until they land, the client round-trips
  them inside `settings.pod` and `_pod_view` reads column-first/blob-second, so
  nothing is lost — but **the fleet scheduler cannot filter or index on
  `desired_replicas`** while it is buried in a JSON blob.
  **Backend ask**: add the three fields to `Vehicle`, `VehicleInput` and
  `VehicleUpdateInput` plus the Prisma columns. The client needs no change —
  `_query_pod_rows` probes for them once per process and switches over on its
  own (`_is_missing_pod_columns`). Two adjacent gaps found while wiring it,
  both backend-side: (a) there is no `VEHICLE_SNAKE_TO_CAMEL` fold in
  `resolvers/entities.js` the way `AGENT`/`TASK` have one, so a snake_case
  vehicle payload passes SDL validation and is then dropped by `addVehicles`
  (reads `item.cpuCores`) or throws in `updateVehicles` (spreads into Prisma) —
  the client now sends camelCase to work around this; (b) `VehicleQueryInput`
  has no filter for `vehicleType`, so listing pods means fetching all of the
  owner's vehicles (`take: 50`) and filtering client-side.

- **Feige sidebar preview selector drift — cold-start row invisible to the
  backstop scan (2026-09-04, build 96s, customer 肽斯特)**. The rebuilt Feige
  frame no longer matches `[class*="msgContent"], .lF_M7QiFB0ukHWpMfQde span`,
  so `ws108 backstop scan` skipped EVERY row `empty_preview` (150 ticks) while
  the new conversation's rows rendered (rows 12→14 at 13:16:04); WS carried only
  the msg_type 1000/2004 system frames (customer text never reaches WS), DOM
  monitor paused under WS-live → zero dispatches, customer waited 12 min.
  ws189 (uncommitted at time of writing) adds a structural leaf-text fallback
  shared by front_desk / pre_dispatch_enrich / site_tools
  (`sidebar_preview_js.py`) + an `EMPTY-PREVIEW DUMP` (row outerHTML 1500) so the
  real preview class can be pinned. **Still open**: (a) live validation of the
  fallback on the customer frame; (b) `event_monitor.py` `last_message` field
  still uses only the dead hashed selector, with NO fallback chain (unlike its
  `name` field, which has two). Mitigated today only because the DOM-monitor
  path is paused under WS-live — i.e. the backstop path is broken precisely
  when it is needed, after WS drops. **`_FEIGE_LIST_SESSIONS_JS` was the other
  half of (b) and is now FIXED (2026-09-20)**: it backs the agent-callable
  `feige_list_sessions` tool, is not covered by the WS-live pause, and had read
  the preview with the dead selector alone since ws189 reached the other three
  readers. It now composes and calls `__ecanRowPreviewFallback`, with a test
  asserting every snippet that touches the dead selector carries the fallback;
  (c) `hasUnread()` in the scan JS matches the rebuilt frame's `auxo-badge`
  avatar wrapper on every row (unread=true everywhere) — harmless today because
  unread is no longer a routing gate (ws104), but wrong; (d) the deeper
  OPEN-CLAIM-CAP gap (claiming an unrendered cold conversation) is unchanged.
- **CN "请求日志分析" (Request Log Analysis, Help menu) upload fails —
  backend SDL gap (2026-09-03)**. Client sends `requestDebug(input:
  RequestDebugInput!)` + `requestDebugDone(zipKey, owner)` (matches AWS
  `schema.graphql:412-413,1739-1753`); the CN TCB GraphQL schema never
  defined them → `Unknown type "RequestDebugInput". Did you mean
  "ReqSceneInput"?`. **Client is correct — backend-only fix** (CLAUDE.md
  §5). Backend copilot: add the 3 types + 2 mutations to the CN SDL, and
  a resolver mirroring `lambda_functions/debug_log_uploader/lambda_function.py`
  but with a Tencent **COS** presigned PUT (key `debug-logs/{owner_safe}/
  log_{ts}_{uid}.zip`, TTL 900s) instead of S3. Client PUTs with
  `Content-Type: application/zip` (`debug_log_handler.py:320`) — sign
  `content-type;host` or host-only per the writeSkillFile COS convention
  to avoid the prior SignatureDoesNotMatch mismatch. No client rebuild
  needed once deployed.
- **Offline-sync delete retries spam "Not found" (2026-09-03)**. Batch-deleted
  agents/tasks that never synced to cloud queue `agent.delete`/`task.delete`
  ops that 404 ("Not found"), retry 3×, and log ERROR each time (99 lines in
  one customer session). Fix: treat item-level "Not found" on DELETE ops as
  success in CloudAPIService/OfflineSyncQueue — the goal state already holds.
- **CN `sendWanMessage` resolver returns "Unexpected error" (2026-09-03)**.
  Every WAN A2A send from the customer machine fails server-side (5×/session).
  Backend-side investigation needed (eCan_lambda repo).
- **`get_llm_provider_api_key` logs ERROR for unset provider (ryoais)**.
  Expected-behavior class — downgrade to WARNING/info per CLAUDE.md §6.

- **CI frontend builds have NO lockfile (2026-09-02)**. `setup-node-env`
  installs gui_v2 deps with `npm install --legacy-peer-deps`;
  package-lock.json is gitignored and pnpm-lock.yaml is unused by CI, so
  every release resolves fresh dependency versions. This turned the
  312a59707 manualChunks split into a landmine: local pnpm bundles booted
  while every CI installer 96l–96n died at load (`Cannot access 'ti'
  before initialization`, stuck 加载中) — reverted in 0e3daf792 (96o).
  Fix: make CI install from a committed lockfile (commit package-lock.json
  or switch CI to pnpm + pnpm-lock.yaml), and only then consider
  re-splitting vendor chunks — with a QtWebEngine smoke test of the built
  bundle as a release gate.

- **CN COS signed-upload URLs fail `SignatureDoesNotMatch` (server signing bug,
  2026-08-21 evening)**. writeSkillFile now returns proper signed PUT URLs
  (list-contract + metadata both fixed), but every PUT is rejected by COS.
  Probe evidence: `q-header-list=content-type;host`, and COS's error echoes
  the expected FormatString `put\n<path>\n\ncontent-type=&host=<bucket-host>` —
  the server's signature was computed over something else (tried empty +
  5 common content-types client-side; all 403). Recommended server fix:
  sign with `host` only (drop content-type from the signed header list) or
  use the COS SDK's presigned-URL helper; alternatively return the exact
  signed content-type so clients can echo it. Client side is complete and
  will start landing files in ecan-skills-1251680599 the moment signatures
  verify. Meanwhile: updateAgentSkills for skill_511221cb45ba41af returns
  success:true — metadata sync is fully working.

- **TCB skills schema drift blocks BOTH skill sync directions** (completed
  diagnosis 2026-08-21). The AWS canonical schema has `public: Boolean` on
  AgentSkill/AgentSkillInput; the TCB SDL renamed it `is_public`/`isPublic`
  on `AgentSkill` AND `SkillInput`. Result: `queryAgentSkills` fails
  validation every startup ("Cloud returned no skills"), and editor-created
  skills — which DO go through the full intended pipeline (skill editor →
  local DB → OfflineSyncManager → addAgentSkills) — die on
  `Field "public" is not defined by type "SkillInput"`, with the offline
  queue retrying into the same wall. Server fix: add the `public` alias to
  both types (TCB already dual-aliases camel/snake). Verified by live probe
  that the resolver itself works (insert OK/visible/removable; re-add same
  id → graceful success:false, still not upsert). Separately: the 4
  built-in panel skills (resource/my_skills) have NO sync path at all —
  they're disk-loaded, ownerless until request-time stamping; syncing them
  is a feature decision, not a bug.
  (found 2026-08-21). Proven with a live probe: first add of a new id → OK,
  second add of the same id → `INTERNAL_SERVER_ERROR "Unexpected error."`
  (unique-constraint violation). The AWS original (DynamoDB put_item) is an
  upsert, and the client contract assumes upsert — the TCB resolver must do
  `INSERT … ON CONFLICT (id) DO UPDATE` scoped to owner. Consequences: cloud
  prompt rows freeze at first-insert content; the startup bulk sync now
  reports "0 ok, 9 errors" every run (all rows already exist — it was "8 ok"
  only when the table was empty). Server-side fix (CLAUDE.md §5).
- **TCB `removePrompts` schema drifted from the client/AWS contract**
  (found 2026-08-21): client sends `removePrompts(input: [ID!]!)` expecting a
  scalar list; the TCB SDL is `removePrompts(ids: [ID!]!): [PromptMutationResult!]!`.
  Every cloud prompt deletion fails with GRAPHQL_VALIDATION_FAILED (silently —
  local delete still works). Also `addPrompts` result type lost its `owner`/
  `version` fields (`PromptMutationResult` only has `id`; the client's bulk-
  sync selection asking for `id` works, but selecting `owner` errors). Align
  the TCB SDL with the AWS schema server-side; do not fork the client.
- **TCB `getSkillEditorChatSessions` returns `INTERNAL_SERVER_ERROR`** on every
  call (server-side; `createSkillEditorChatSession` and `sendSkillEditorChatMessage`
  work after the 2026-08-19 llm_proxy fix). Client now falls back to local
  sessions gracefully, but cloud chat history is invisible until the resolver
  is fixed. See docs/CN_SKILL_EDITOR_CHAT_DEBUG_2026_08_19.md.
- **UPDATE 2026-08-20: client no longer amplifies this into a logout.** Only
  `SESSION_EXPIRED` now signs the user out; `WX_TOKEN_EXPIRED` / transient
  refresh failures keep the session alive — HTTP GraphQL continues on the
  30-day session-token bearer, only WS features degrade. Also fixed 4 handlers
  (prompt_cloud_sync, prompt_completion, skill_file_sync, chat_handler A2A
  HTTP) that sent the raw combined token instead of `_http_auth_header()` —
  their CN cloud calls failed auth even with a live session. Server fix still
  needed so WS tokens can be re-minted past the first JWT TTL.
  **VERDICT 2026-08-20 23:00 (live run): code = `WX_TOKEN_EXPIRED`; rotation
  RULED OUT.** The refresh payload has no `sessionToken` field (client fell
  back to legacy selection), and the login-time session token still
  authenticated HTTP 29 min after mint — so nothing rotates; the server just
  cannot re-mint WS JWTs once the underlying wx credential expires.
  Client resilience CONFIRMED working: app stayed signed in ~18 min past the
  historical death point, prompt sync completed (8 prompts verified in the
  cloud table), HTTP live-probed OK. Remaining impact: WS-only (wan_chat /
  subscriptions have no fresh JWT). Server fix: `refreshWeChatToken` must
  mint the access JWT from the durable `wechat_sessions` row instead of the
  login-time wx credential. Optional client cleanup: throttle the 30s
  "WS-token refresh unavailable" retry warnings.
- **Server kills the WeChat 30-day session token within ~10 min (TCB)** —
  root cause of "no WeChat session token available": `refreshWeChatToken`
  returns SESSION_EXPIRED/WX_TOKEN_EXPIRED ~5–10 min after
  `registerWeChatSession` mints the token (expiresIn=2592000), so the client
  (correctly) deletes it and signs out. Reproduced 3/3 runs 2026-08-19.
  Server-side fix needed — likely the session row depends on the short-lived
  CloudBase/WeChat access token instead of a durable secret. Client-side
  diagnosis was blocked for weeks by the SessionSupervisor logging to an
  unconfigured logger (`eCan.session_supervisor`) — ✅ fixed 2026-08-19
  (now logs via logger_helper; refresh failures now log the server's code).
  See docs/CN_SKILL_EDITOR_CHAT_DEBUG_2026_08_19.md "Follow-up session".
- **AppSync account-info GraphQL parse error** — fetching account info fails with
  `Syntax Error: Expected Name, found String "action"` (`GRAPHQL_PARSE_FAILED`).
  Non-fatal (MainWindow init continues, "Failed to fetch account info"), but the
  account page likely renders incomplete. Almost certainly `lq_dev_util` merge
  damage in a GraphQL query string. Seen 2026-08-11 CN first-login run.
- **5 merge-broken files (syntax errors, committed)** — not on startup path, but
  break their features when invoked. From the `lq_dev_util` merge:
  - `agent/ec_skills/knowledge_builder/prep_knowledge_builder_skill.py:12` — IndentationError
  - `agent/ec_skills/search_parts/prep_search_parts_chatter_skill.py:19` — IndentationError
  - `agent/ec_skills/self_test/prep_self_test_chatter_skill.py:11` — IndentationError
  - `agent/mcp/server/api/captcha2/captcha2_api.py` — positional arg after keyword arg
  - `agent/mcp/server/fingerprint_playwright/har_capture.py` — `await` outside function

### ⚡ Runtime self-healing against changing sites (2026-09-19)

Plan of record: **`docs/SELF_HEALING_ROADMAP.md`**. Read it before touching
element resolution in any hook bundle.

The gap in one line: we built the design-time authoring loop (skill editor,
flowgram, validate-and-fix) and none of the runtime healing loop. When a site
changes, the repair path is customer-notices -> logs -> human patches selectors
-> build. That ran on ws189, ws193, mt062/063 and the June Feige redesign.

Four phases, in order of prevent-before-repair: semantic targeting (L1),
resolver fallback that picks from a live element table (L2), write back what
was resolved (L3), site knowledge (L4). Phase 1 is logging-only and is the
urgent one -- it produces the evidence for whether Phase 2 is worth building.

Two industry sources converged on the same answer from opposite directions:
`jev-ultrafast` (model returns an index into an observed table, never a
selector) and `workflow-use` (schema deprecates cssSelector/xpath/elementHash
in favour of target_text + container_hint + position_hint). The durable
identifier is what a human would say, not what the DOM says.

Separate track: a shadow experiment with TypeSafe's Jev on element resolution,
Etsy/eBay only until the CN data-residency question is answered.

### Left open after the fingerprint-browser session (2026-09-18)

The etsy_after_sales0 run now works end to end -- profile recovers itself,
steps around the user's own Chrome, proxies correctly, lands signed in, sends
the email. These are what was found on the way and NOT fixed.

**Cloud sync is failing on two backend SDL gaps.** Every skill/task save is
going to the offline queue instead of the cloud:

    GraphQL Error: Field "need_inputs" is not defined by type "SkillUpdateInput"
    GraphQL Error: Field "TaskSkillRelation.owner" of required type "String!" was not provided

Both are backend fixes in `eCan_lambda` per Section 5 -- update the SDL and
redeploy, do NOT rename the client field (that breaks the AWS side and the
local shape together). Client sends `need_inputs` because it is folded into
the skill config and lifted back out by `DBAgentSkill.to_dict`.

**Duplicate skill rows on save.** `etsy_after_sales0`, `飞鸽客服前台00` and
`飞鸽客服问答00` each have two rows -- a `skill_*` id and a UUID id, same name,
one carrying `need_inputs` and the twin carrying none. TaskDetail resolves a
skill by `id===sid || name===sid`, so the wrong twin can win and the 任务变量
panel renders empty. STRONG LEAD, unproven: a failing `update` (above) retried
as an `add` would create exactly this. Fix the SDL first and see if it stops.
Same family as [CN skill sync ownerless repair].

**Skill-editor saves not reaching disk.** Node edits in the editor did not
change `my_skills/etsy_after_sales0_skill/diagram_dir/*.json` for hours --
mtime stayed at the morning's save while the user was editing. Possibly the
same root cause as the duplicate rows; not investigated.

**`work_done: false` on a successful run.** The etsy run returns
`{"all_done": true, "work_done": false, "work_result": {"last_action_succeeded": true}}`
and DOES send the email. Whatever `work_done` is gated on is not being
satisfied, so the flag is currently not trustworthy as a success signal.

**Memory-wins merges need an audit.** THREE separate bugs today were one
pattern -- a merge where an in-memory copy shadows a DB field it does not own:
`org_id` in `get_all_org_agents`, the browser identity precedence, and
`need_inputs` in `get_agent_skills`. Each was found only when a user noticed
something missing from the GUI. Worth walking the remaining handlers that
merge memory with DB before a fourth one surfaces.

**The Ziniao importer has never been run.** Written blind for a customer demo
(`vendor_import.import_ziniao`). The vendor list carries `validated: false` and
the dialog warns. Two things most likely wrong on first contact: the shape of
the `getBrowserList` response, and whether the proxy is exposed at all -- if it
is not, the profile registers WITHOUT one and will egress from the local
address, which is logged loudly but still worth checking before a demo.

**Inbound skill sanitisation.** `skill_share_sanitize` strips
`browserProfileId` on the way OUT. Anything already published still carries
whatever was in it, and an import does not clean it. Outbound is the leak that
matters; inbound is defence in depth.

**The SOCKS relay dies when system DNS cannot resolve the proxy host.**
Cost an afternoon: a phone hotspot became a second default route and its
carrier DNS returned NXDOMAIN for `us11.kookeey.info` (8.8.8.8 resolved it
fine). The relay has no fallback, so the profile simply cannot reach anything.
Anti-detect users sit behind filtered or captive DNS often. Options: fall back
to a public resolver for the proxy host only, or cache the last known good IP
on the profile record. Both hardcode a policy, so decide deliberately.

## 🟡 Environment / deps

- **`zeroconf` module missing** — LAN discovery disabled on the CN dev machine
  (`discovery imports failed: No module named 'zeroconf'`). `pip install zeroconf`.
- ✅ 2026-08-19 **`gui_v2/pnpm-lock.yaml` uncommitted** — committed with the
  CN skill-editor chat fallback fixes.

## 🔵 Planned work

### 10-day unattended 客服 run — plan (2026-10-18)

Goal (customer ask): the 客服 desktop runs ≥10 days with no one at the PC. Order: **soak test
first** (measure what actually fails), then **watchdog + alerts** (every failure either heals
itself or reaches the owner within minutes), then the rest. Inventory of what exists today:

| # | Piece | Today | To do |
|---|---|---|---|
| 1 | **Soak test** | none | Real PC, 2 抖店 stores, 10 days; daily RSS/threads/Chrome-process/handle counts, disk, reply latency, every restart and its cause. `utils/memory_monitor.py` (memory.log, 30 s) and `runlogs/process_heartbeat.json` already record RSS/threads. |
| 2 | **Start at boot** | none (Inno `[Tasks]` = desktop icon only, `build_system/ecan_build.py:692-1009`) | Run key or logon scheduled task + settings toggle. |
| 3 | **Restart on crash/hang** | heartbeat file written every 5 s (`utils/crash_boundary.py:204-268`), read only by the NEXT launch; no supervisor | Small external watchdog (scheduled task / service): pid alive + fresh `updated_at`, else kill + relaunch; report the restart. |
| 4 | **Sign back in after restart** | CN restore needs a keyring password (`auth_manager.py:2503`) → WeChat QR users land on the QR screen; 30-day session token never re-minted | Restore from the saved 30-day WeChat session token at startup; re-mint before day 30 (server: re-mint from the website session token). |
| 5 | **Agents + store browsers after restart** | yes (`MainGUI` phase 3; `browser_manager.py:1202-1228` reattaches/starts per-profile Chrome, cookies persist) | Covered once 2–4 work. |
| 6 | **Store browser dies** | `browser_watchdog.py` exists but OFF (`ECAN_BROWSER_WATCHDOG=1`, :88-91) — customer 2026-10-18: store B's Chrome died 14:57 and stayed dead 8 h | Turn it on for front desks (after testing); stop the coldstart/bot-toggle retry storm when there is no SessionManager (~24k failed evals in 16 h). |
| 7 | **Store site logged out** | only generic `monitor_hb=page_mismatch` (`event_monitor.py:3128-3157`); PDD "账户在别处登录" detected | Explicit `login=logged_out` in AGENT-STATUS per platform (login/QR page URL patterns) → alert. A human re-scan stays necessary; the goal is knowing within minutes. |
| 8 | **Owner alerts off the machine** | fleet feed (`agent/fleet/activity_feed.py`) is pull-only; balance low/zero = in-app banner only (`proxy_errors.py:100-111`) | Push (e.g. WeChat message) for: app restarted/died, eCan signed out, store logged out, agent silent N min, balance low/zero. Needs a server-side sender (user's server terminal). Server-side "machine went silent" alarm off the fleet feed. |
| 9 | **Sleep / wake** | sleep inhibitor has an 8 h cap (`utils/sleep_inhibitor.py:63`); `utils/power_monitor.py:178` subclasses `QObject` without importing it → NameError, wake recovery never installed; `wake_recovery.py` step 2 re-subscribes WAN per agent on every wake with no dedupe (thread/connection leak if enabled as is) | Fix the import + make WAN re-subscribe idempotent, then enable and test; no inhibitor cap while front desks run; fast deploy sets/warns power settings. |
| 10 | **Windows Update reboot** | nothing (no `RegisterApplicationRestart`, no end-session handling) | Covered by 2 + 4; optionally `RegisterApplicationRestart`. |
| 11 | **Growth** | logs rotate (eCan.log 10 MB×5, wscap 20 MB×5); no pruning of chat messages / notifications / qa_history, `generated_medias`, version snapshots; chatter-task `InMemorySaver` threads never deleted | Retention by age/count; cap per-thread checkpoints for long-lived chatter tasks. |
| 12 | **OTA** | auto-check shows a modal dialog (`gui/WebGUI.py:1969-2002`) → needs a click; relaunch then hits #4 | Unattended policy: defer or install-and-relaunch at a quiet hour; depends on #4. |
| 13 | **Site layout changes** | not preventable | Covered by 7/8 (agent silent → alert). |

Already fixed on the way (2026-10-18, unbuilt): QR login silently signed out after 45 min
(6bf22cb6f); refresh-loop sign-out now tells the window (84e0dd037); GUI WebSocket force-closed
every 5 min (469475ec3).

### RAG work — starts after the chip-docs crawler runs on the cloud side (2026-10-09)

The user has a batch of RAG work queued behind the chip-docs crawler; it will be
done on the CN side. First item:

- **Doc parser URL is hard-coded to the CN backend.** `ECANAI_PARSER_BASE_URL`
  in `knowledge/lightrag_parser_config.py:55` is the CN tcloudbase llm-proxy
  URL, and it is the default Docling/MinerU endpoint (`DEFAULT_DOCLING_ENDPOINT`,
  the settings default/placeholder) in BOTH apps — the intl app sends document
  parsing to the CN backend. It should come from the app's own endpoint config.

### ⚡ Fleet transfer: fetch logs + move a store with its login (2026-09-24)

Client built (`agent/fleet/`, `fleet_handler.py`, Vehicles → Fetch logs, Stores →
Move with login…); design in `docs/FLEET_TRANSFER_DESIGN.md`. **Blocked on the
server half** — `docs/FLEET_TRANSFER_SERVER_CONTRACT.md` (`transfer_*` actions on
ecbAccountManager + a private `fleet-transfers/` prefix with presigned links).
Until it is deployed, every heartbeat's `transfer_list` fails quietly (DEBUG).

Open after v1:
- **A dead source cannot hand over its login.** Failover from a machine that will
  not boot needs periodic encrypted snapshots in the cloud, encrypted to a key the
  account's machines share and the server does not hold. Decide key custody
  (who creates it, how a new machine gets it) before building.
- The server could substitute the receiver's public key (it is trusted for the
  control plane, not the data). Per-machine signing keys would close it.
- Not verified on real machines yet: cookie restore through `Storage.setCookies`
  keeps a Douyin/飞鸽 session alive on the target; Windows firewall prompt on the
  receiver's first listener.

### ⚡ Per-store browser profile: CONFIG-first cloud vault + commander/platoon provisioning (2026-10-15)

**Agreed design (user approved 2026-10-15).** A store's browser profile (its
login identity: fingerprint + proxy + binding) should be an account-level asset
that survives any machine dying and can be (re)deployed to any machine —
pristine platoon included. This is the CONFIG-first layer of the Fleet-transfer
work above (the STATE/cookie-snapshot half is the "Open after v1" notes there,
and stays phase-2 behind a flag). Prompted by a user run (build `9cd805e10`) of
2 抖店 stores still showing "1 Chrome, 2 tabs": only 店B's front desk launched a
fingerprint browser; the 2nd store's didn't — see
`project_multistore_browser_autoprovision` memory.

**Decisions locked:**
1. **Source of truth = a per-account cloud vault** (reuse the COS skill-sync
   pattern/credentials, new prefix — e.g. `profiles/<account>/`), NOT a
   commander-hosted store. Commander is the *orchestrator*, not the sole holder,
   so an abandoned commander is not fatal. (Alternative rejected: commander disk
   as master — same single-point-of-failure one level up.)
2. **CONFIG-first; STATE (cookies/`user_data_dir`) is opt-in / phase-2.** Live
   session migration fights the anti-detection invariant (a session reappearing
   on a new machine/IP looks like account-takeover → likely forces re-login
   anyway) and is heavy/racy (hundreds of MB, file-locked while Chrome runs). So
   do NOT sync it per task. CONFIG-sync alone already gives "redeploy a store to
   any machine, comes up configured, needs only a one-time sign-in" (~80% of the
   value, none of the risk).
3. **Front-desk reconciliation = a guided CLI/GUI action the operator triggers**
   (reports duplicates, confirm before rewriting agent/task rows), NOT a silent
   auto-migration on launch (it's surgery on live rows).

**Vault CONFIG fields (small, safe):** `fingerprint_profile` (template id),
proxy (password stays in secure-store, not the vault), `locale`, `domain_name`,
`store_id`, `login_state`, `machine_id`. Explicitly NOT in v1: `user_data_dir`,
`install_salt`, cookies.

**Single-writer is free:** `store_placement` already enforces one assignee per
store, so only the current assignee writes CONFIG back — no multi-writer
conflict.

**TODO (implementation — client landed 2026-10-15; vault cloud side BLOCKED ON SERVER):**
- [x] **Fix `runner.py:5542` (+ `:5625`)** (`d6b0a67b5`): the browser node now
      resolves the per-run `browser_profile_id` (new
      `build_helpers.user_data_dir_for_profile_id`) into BOTH the effective
      `user_data_dir` and the fingerprint, instead of falling back to the shared
      `browser_profiles\default` dir / the node's build-time id. Tests in
      `test_browser_identity_phase3.py`.
- [x] **Seed a standard fingerprint template when a store has no profile**
      (`4e3478ebd`): `_provision_store_profile` seeds a standard Windows-Chrome
      template (deterministic per store) instead of an empty fingerprint. NB only
      2 win templates; 店A/店B both hash to `win_chrome_01` (distinct
      `user_data_dir`, so still separate browsers).
- [x] **Vault I/O + pristine-platoon provisioning — CLIENT done** (`profile_vault.py`):
      `pull_descriptor(store_id)` / `push_descriptor(profile)` over the
      presigned-URL AppSync pattern (mirrors `skill_file_sync`); ships ONLY
      `profile_registry.descriptor()` (no `user_data_dir`/proxy/cookies — the
      stays-local guard still passes). Wired into `_provision_store_profile`:
      pull → adopt the vault's fingerprint/locale when present, else seed the
      standard template; push after create. **Gated OFF behind `ECAN_PROFILE_VAULT`**
      (instant no-op, no network/log-spam) until the backend ops exist. Tests in
      `test_profile_vault.py`.
- [ ] **BLOCKED ON SERVER — vault cloud ops** (eCan_lambda, user's other terminal):
      add `requestStoreProfileUploadUrl` / `requestStoreProfileDownloadUrl`
      presigned-URL ops, key `profile-vault/<owner>/<store_id>.json`, owner-auth
      check. Full contract: `docs/PROFILE_VAULT_SERVER_CONTRACT.md`. Then flip
      `ECAN_PROFILE_VAULT=1` and validate the two-machine redeploy.
- [x] **Front-desk reconciliation — REPORT done** (`b9e0dcd0d`): pure planner
      `store_overview.plan_front_desk_reconcile` + `is_front_desk_name`, surfaced
      as `ecan stores reconcile` (read-only; flags stores with >1 front desk,
      recommends keeping the store-scoped one). Tests in
      `test_front_desk_reconcile.py`.
- [x] **reconciliation ENACTMENT — CLI done (yak):** `ecan stores reconcile`
      now also reports STALE Q&A wiring (`store_overview.plan_qa_rewire`: a Q&A
      pool pointed at a dead `front_desk_agent_id`) and gained `--apply`
      (`--force` to skip the prompt): it retires duplicate front desks and
      re-points stale Q&A, through the running app's handlers
      (`delete_agent`/`delete_agent_task`/`save_agent_task`, so the CLOUD copy is
      cleaned and running tasks update) when `edits_via_app`, else direct DB +
      `cloud_sync`. Ambiguous stores (no single store-scoped front desk) are
      skipped for a human. Productionizes the one-off
      `fix_frontdesk_wiring.py`. Tests: `test_front_desk_reconcile.py`.
      NOTE: the three CLI primitives were there all along — `ecan agents remove`,
      `ecan tasks remove`, `ecan tasks update --var front_desk_agent_id=…` — the
      gap was the one-shot planner+enactment, which this fills.
- [ ] **FOLLOW-UP — reconciliation ENACTMENT (GUI):** a guided "retire duplicate
      front desk / fix wiring" action on the Stores page (the CLI `--apply`
      engine behind a visible confirm), part of the Repair panel (see "Remote
      quick-patch / self-repair" below).

**Phase-2 (STATE, deferred, behind a flag):** periodic encrypted cookie/storage
snapshots to the vault (lifecycle events — graceful stop / login refresh /
assignment release — NOT per task), restore-on-deploy, key custody per the
Fleet-transfer "Open after v1" notes. Do not start until CONFIG-first is live
and we see whether platforms honor a migrated session.

Full design writeup: fold into `docs/FLEET_TRANSFER_DESIGN.md` (CONFIG-first
section) when implementation starts.

### Fresh-install browserless: missing Chromium on unsigned builds (2026-10-16)

Field bug (customer zbb, pristine machine, yai): single douyin store, NO Chrome;
`%LOCALAPPDATA%\eCan\ms-playwright\chromium-1181\chrome-win\` had the folder tree
but no `chrome.exe`. NOT the multistore wiring issue. The installer DOES bundle
Chromium (build log: `[SPEC] Added 110 Playwright files`, incl chrome.exe/.dll).
On first run eCan copies the bundle to `%LOCALAPPDATA%\eCan\ms-playwright`
(`agent/playwright/core/setup.py::ensure_playwright_browsers_ready`). On a
pristine + UNSIGNED install, Windows Defender real-time protection quarantines the
unsigned `chrome.exe` during/after that copy — tree lands, exe gone — and the
setup error was swallowed (`agent/playwright/utils.py`), so the app came up
"green" with no browser. Non-pristine machines (e.g. Admin) worked off a cached
copy from a prior install. Confirm on a box via Windows Security → Protection
history (a `chrome.exe` quarantine entry).

**UPDATE 2026-10-16 — the REAL root cause (not client-side Defender):** zbb's
Windows Defender Protection history is CLEAN (no chrome.exe entry), and the
INSTALL's own `_internal\third_party\ms-playwright\chromium-1181\chrome-win\` has
all the DATA files (.pak/.dat/.bin, correct sizes) but NONE of the PE binaries
(chrome.exe, chrome.dll, the DLLs). So the **installer is shipped WITHOUT the
chromium executables** — deterministic, hits every fresh machine. A complete
chromium is 106 files incl 22 PE binaries; the build logged "Added 110 Playwright
files", so the PEs were collected but dropped between PyInstaller and the
installer: the spec removes the Playwright binaries from `a.binaries` to re-ship
as data (`minibuild_core.py:1038`), and PyInstaller's datas/binaries dedupe (or
the build runner's own Defender eating the unsigned PEs from the dist before Inno)
drops the executables while the data survives.

ALSO CORRECTED: the CN (and intl) installer is **per-user, non-elevated**
(`privileges_required: "lowest"`, `default_dir: {localappdata}\eCan.cn`), so an
installer-time `Add-MpPreference` can NOT run — the earlier "installer
self-excludes" idea was reverted as dead code for these installs.

Fixes landed:
- **yak `946dc2ee0`** — `ensure_playwright_browsers_ready` re-validates the target
  AFTER the first-run copy; if `chrome.exe` is missing it logs an ERROR + the
  repair-script pointer and raises. Diagnosable instead of silent.
- **build completeness guard (`ecan_build._ensure_chromium_in_dist`)** — before
  Inno packages, re-lay the complete chromium from `third_party` into the dist
  (fixes the PyInstaller dedupe drop) and FAIL the build if it still isn't whole
  (catches the runner-Defender-ate-the-source case, with a message to exclude the
  runner work dir). So a browserless installer can never ship again. Validated:
  py-compiles; `_chromium_complete` returns (True,True) on a good tree,
  (True,False) on the broken dist, (False,False) when there's no chromium.
- **RUNNER (one-time, user):** on the win-runner, elevated,
  `Add-MpPreference -ExclusionPath "C:\actions-runner\_work"` so the runner's
  Defender stops eating the unsigned chromium during the build.
- **Immediate unblock for already-installed boxes:** `fix_missing_chromium.ps1`
  (eCan_lambda/docs/support) — run ELEVATED with `-SourceDir` pointing at a
  COMPLETE `ms-playwright` (Admin box or dev repo); it copies the whole
  `chrome-win` (all PE files) into the per-user appdata + verifies.

Durable belt-and-suspenders: **sign the installer** (BLOCKED short-term — no
code-signing cert). Signing would also stop any per-client Defender from eating
the exe post-install, which this build fix does not address (not observed on zbb,
but possible elsewhere — the yak verify + repair script cover it).

### Decision point: several same-platform stores in ONE store process (Phase E) (2026-09-24)

Today each store on a machine with 2+ stores of one platform gets its own store
process (worker; ONE_APP_MANY_STORES.md). Sharing one process between stores of
the same platform (e.g. two 抖店 stores) is mechanically trivial -- give both
the same isolation key -- but NOT safe yet: the live-chat runner bridge is
registered per platform (live_chat_dispatch._BRIDGES), the typing lock and tab
pool are single, and per-customer state is keyed by display name (two stores
can both have a customer "小王"). The failure mode is a wrong-store reply, not a
crash. Already store-aware: placeholder timers (store_key), the 飞鸽 WS observer
(chat_browser_cdp_url(store_key)).

**Trigger:** W4's measurement of RSS per store process on a real multi-store
machine. Only if a typical machine cannot host the store count customers run,
do the Phase E store-scoping (bridge, typing lock, tab pool, per-customer keys).
Middle option worth weighing then: per-store front desks (each bound to its
store's browser) sharing ONE Q&A pool -- most of the memory, same
store-scoping prerequisites on the Q&A side.

**Live confirmation on yai (2026-10-16, customer `C:\Users\Admin`, owner
`o3YBk2WG34…`, stores `douyin-抖音二号`/`douyin-抖音三号`).** yai's per-task
`browser_profile_id` fix worked (TWO Chrome, each store its own
`user_data_dir`), but one store stayed silent. Three in-process
cross-contamination vectors, all from running 2 同平台 stores in one process
(`ECAN_STORE_ISOLATION` off) where both front desks share ONE skill → ONE node
id `browser_automation_0t5L6`:
  1. **Agent-id recovery crossed stores** — `_record_or_recover_agent_id`
     (`build_node.py`) keyed its caches by the shared node id alone; a degraded
     WS re-entry (empty `state.attributes.agent_id`) recovered the OTHER store's
     id via the `len(known)==1` / last-known fallback → PreDispatch sent as the
     wrong store's front desk (`frontdesk_dispatch.py:2879` `sender_agent_id =
     ctx.calling_agent_id`). **FIXED in yai→yaj:** the recovery caches + scope
     are now partitioned by the run's `browser_profile_id` (store) — see
     `_agent_recovery_node_key` / `_run_browser_profile_id`; the single-store
     fast-path can only return an id recorded for THIS store. Tests:
     `test_browser_identity_phase3.py::TestTwoStoresShareOneSkill`.
  2. **`新消息` browser_event not store-qualified** — `_augment_match_fields`
     (`runner.py:2957`) adds `senderId` filtering only for chat/a2a events, NOT
     `browser_event`, so a detection on either store's session matches EVERY
     front desk's `browser_event:新消息` rule → 抖音三号's detection can resume
     抖音二号's desk (which then finds nothing on its own session → the message
     is swallowed → silence). **NOT fixed (needs live Feige validation):** the
     normalized event (`event_monitor._build_normalized_browser_event`) carries
     only `session_id=id(session)`, no store; the fix is to thread the session's
     `browser_profile_id`/`store_id` into the event AND add a browser_event
     match-field keyed on the task's store. Tractable but touches battle-tested
     detection+routing — do it on a live two-store 抖店 run, not blind.
  3. **Deterministic total silence = stale deploy wiring** (NOT code): 抖音二号's
     Q&A pool pend-waits on `front_desk_agent_id=agent_a57354ffe68d4286` but the
     live front desk registered as `agent_7ca0a254b8d3435d` (re-created after the
     Q&A pool was wired), and the legacy `前台小张`/`飞鸽客服前台001` is still
     deployed on 抖音三号's profile `167bb80f`. **Customer fix = the reconcile
     runbook:** retire `前台小张`, then clean-redeploy 抖音二号 (its profile
     `6a4b2c53` is store-keyed so login persists). `ecan stores reconcile` flags
     it.
The definitive guarantee remains process isolation (re-enable
`ECAN_STORE_ISOLATION`, blocked on worker skill-compilation). Vectors 1 & 3 get
抖音二号 answering; vector 2 is the residual intermittent cross-routing until
isolation or the store-qualified browser_event lands.

**Vector-2 client landed, gated OFF (`8fcb94db0`, yaj+1):** store-scoped
browser_event dispatch behind `ECAN_STORE_SCOPED_BROWSER_EVENTS` (default off).
The detecting session's `browser_profile_id` is stamped onto the event
(`event_monitor`: http-polling bridge + ws_frontier `_evt`, threaded via
`ActiveMonitorSet`→`start_monitors`→`ensure_started`, profile pulled from the
`browser_scope_key`'s `@browser_profile_id=` tail in `browser_node/runner`); and
`_augment_match_fields` (`ec_tasks/runner.py`) adds a browser_event match-field
`browser_profile_id == login_profile_id(store_id)` so a front desk only resumes
for its own store. Both ends use the same canonical value (verified). **Must be
validated on a live two-store 抖店 Feige run before default-on** (adds a filter
to battle-tested detection routing). Tests: `test_store_scoped_browser_events.py`.

### Worker skill-compilation → re-enable ECAN_STORE_ISOLATION (plan, 2026-10-16)

The real finish for multi-store (TODO #1). Today an isolated store worker
(`agent/ec_tasks/worker_entry.py` → `start_domain_agents` → `load_agents_from_db`)
builds EC_Agents from DB rows via `convert_agent_dict_to_ec_agent`, which resolves
each task's executable skill out of `mainwin.agent_skills` (the COMPILED pool). On
the worker that pool is `WorkerContext.agent_skills = []`
(`agent/ec_tasks/worker_context.py:72-79`), so every skill stays a DB stub with
`runnable=None` → a front-desk agent with no runnable chat skill comes up inert and
never opens a browser (the yah/yai "agents green, no Chrome" when isolation was
tried).

**Minimal change (reuse MAIN's exact pipeline, so app and worker compile
identically):** in `start_domain_agents` (`worker_entry.py`, before
`load_agents_from_db`), populate `ctx.agent_skills` by calling
`agent/ec_skills/build_agent_skills.build_agent_skills(ctx)` (headless-safe — no
PySide6/pyautogui at import; the cloud ECS worker already compiles via
`load_skill_from_folder(..., mainwin=None)` + `flowgram2langgraph_v2`). The worker
has no running loop there, so `asyncio.run(...)` is fine. Update the
`worker_context.py:72-79` comment that asserts the pool "stays empty".
  - **Lighter alt (preferred if boot latency / offline robustness matters):** build
    the pool DB-only — `_load_skills_from_database_async` + `_convert_db_skill_to_object`
    per row — skipping `_load_skills_from_cloud_async` (the parent already owns cloud
    sync; avoids a second DB writer racing the parent on the shared sqlite).
  - Do NOT register a Qt progress callback in the worker (`set_status_callback` is
    opt-in/None by design).
**Then** flip `ECAN_STORE_ISOLATION` default on
(`agent/ec_agents/store_isolation.py:39`) ONLY after live validation.

**Headless-safety risks (low):** `build_node` must keep its lazy PySide6/pyautogui
guards (the worker runs on Windows with a display, so run-time use is fine; only
import/compile must stay guarded — it already is). Compile-path reads of
`AppContext.get_main_window()` (e.g. `_inject_toolset_skillset_variables`,
`_get_cached_browser_use_llm`) resolve to the `WorkerContext`; they use
`getattr(..., None)` defaults, but any NEW attribute the compile path reaches
without a default surfaces as a worker-context gap (caught by
`tests/test_worker_entry.py`).

**Must validate live (can't be proven in checkout):** (1) the spawned
`worker_entry` process logs `✅ Converted DB skill … (runnable: <CompiledStateGraph>)`
and the front-desk chat task resolves to a non-None `runnable` (no
`[SKILL_WARNING] Skill has runnable=None`, no `⚠️ No skill matched`); (2) the
isolated front desk opens its fingerprint browser and services a live chat end to
end; (3) worker boot latency with the full compile is acceptable (else DB-only
build); (4) no double-writer corruption on the shared sqlite from a worker cloud→DB
write racing the parent; (5) the worker's checkpointer matches the desktop's
(`EC_Skill.set_work_flow` → `build_checkpointer()`). No change needed to the
compiler itself. Spawn entrypoint is `agent.ec_tasks.worker_entry` (NOT the ECS
`cloud_worker/worker_main.py`); the isolated worker is a separate OS process
(`worker_placement.default_spawner`).

### Remote quick-patch / self-repair of a customer install (idea, 2026-10-16)

Need: apply a DEPLOYMENT/data fix to a customer's installed app (e.g. the
front-desk reconcile runbook — retire a duplicate desk, re-point a stale Q&A
`front_desk_agent_id`, re-run Fast Deploy) WITHOUT a full rebuild/reinstall.
Split cleanly:
  - **Data/deployment fixes** (90% of cases): mutate DB rows + config via the
    app's existing IPC handlers (`delete_agent`, `fast_deploy.generate`,
    `stores reconcile`). Low-risk, reversible.
  - **Code hot-patches:** keep on the OTA path (already ed25519-signed). The app
    is PyInstaller-frozen; a real code change is a build. Do NOT build an
    arbitrary-code overlay — it voids every signing/whitelist guarantee.

**Security line (non-negotiable):** any "run this to fix it" mechanism is remote
code/command execution. A hidden page that runs arbitrary scripts (the first
`ctrl-alt-t` sketch) is the worst shape (powerful + invisible + no audit) and an
FTP-a-script flow is the phishing shape. So: never execute raw code/scripts —
only a WHITELIST of ops the app already knows, SIGNED (reuse the OTA ed25519
key), owner- and time-SCOPED, report-first + explicit CONSENT + UNDO + AUDIT log.

**Two tracks:**
1. **Near-term, lightweight (preferred first step):** the user already has a
   copilot agent — give it prompts + the runbook ops (and a diagnosis template)
   so it can walk/apply the deployment fix on the customer machine. Quick and
   dirty; no new signed-runner infra. Risk: it's still acting through whatever
   access the copilot has — keep it to the known IPC/CLI ops, report-first.
2. **Robust (future):** a signed, declarative **maintenance-recipe runner** — a
   JSON recipe of whitelisted ops (`stores.reconcile`, `agent.delete`,
   `store.redeploy`, …) + `owner`/`expires`/`sig`, executed through existing IPC
   handlers behind a visible **Stores → Repair** panel (this subsumes the
   reconcile ENACTMENT TODO). Delivery, best→worst: (a) cloud-pushed over
   `PassiveCommandService`/AppSync (zero customer action; note its ws_endpoint
   bug is still open), (b) a short maintenance CODE the customer pastes → app
   fetches that signed recipe by code (presigned-URL pattern, like
   `skill_file_sync`), (c) signed `.ecanfix` file loaded offline (FTP idea, made
   safe by the signature — verify before any op). Signing + cloud-push channel =
   an eCan_lambda (server) piece. `ctrl-alt-t` stays diagnostics-only.

### ⚡ Store placement: the assignment decides where a store runs (2026-09-24)

Design: `docs/STORE_PLACEMENT_DESIGN.md` (D1 auto-claim, D2 run when the cloud
is unknown, D3 60s heartbeat). Server half shipped 2026-09-24 (eCan_lambda
`ff89a55`, `504435f`). Client half shipped: `store_placement` gate in
`EC_Agent.start()`, claim, on-disk assignment cache, `store_reconciler` per
heartbeat, `EC_Agent.stop()`, release in the store report. **Not yet verified
on two real machines.** Deliberate limits, fix when they bite:

- **A stopped agent does not restart in the same process.** `EC_Agent.stop()`
  goes through `TaskRunner.stop()`, which cancels the ManagedTask objects and
  queues `__shutdown__`; the agent keeps those objects. Moving a store back to a
  machine that stopped it logs a WARNING asking for an app restart. Making it
  restartable = clear each task's `cancellation_event`, drain the shutdown
  sentinels, fresh TaskRunner.
- **The in-flight turn is cut, not drained**, when a store moves away
  (`ManagedTask.exit()` is a force stop). The customer's current message can
  go unanswered; the next one is answered on the new machine.
- **A stopped store's browser event monitors keep running** until app exit:
  `TaskRunner.stop()`'s monitor cleanup is process-wide, so the per-agent stop
  passes `cleanup_monitors=False` rather than blind the other stores. Needs a
  per-agent monitor cleanup.
- **Agents with an isolation key are not reconciled** — the worker supervisor
  owns them; wiring its `reconcile()` to store placement is still open.
- **Dead-machine takeover is slow**: 180s stale + up to one 5-min server timer.
  Planned moves use release and are not affected.

### Store registry has no intl backend (2026-09-24)

`store_report` / `store_list` / `store_assign` / `store_archive` exist only on
the CN `ecbAccountManager`. On intl, `store_api._call` targets
`<graphql host>/ecbAccountManager`, which has no intl counterpart (inferred
from the code, not tried live), so the heartbeat's store report and
Settings → Stores should come back as a typed WARNING, not a crash. Store placement depends on these actions, so intl
multi-machine needs the AWS side first. Deliberately deferred.

### Ideas from researching two other e-commerce automation OSS projects (2026-09-21)

Bounced ideas while researching `cs-lazy-tools/ChatGPT-On-CS`
(github.com/cs-lazy-tools/ChatGPT-On-CS) and `zpoint/vibe-seller`
(github.com/zpoint/vibe-seller) for comparison against eCan.ai. Full
write-up: `~/jsPrj/research-chatgpt-on-cs-vs-vibe-seller.md` (not in this
repo). Not a decided plan — two ideas worth a look, not yet scoped:

1. **Declare-scope-before-acting, grade-against-declaration governance
   pattern**, from vibe-seller's `app/ai/ad_declaration.py`. Before
   touching a browser, an ad task must declare its kind + scope; the
   declaration is append-only with a narrow "ratchet" (can only shrink
   scope, or safely upgrade within the same turn) so an agent cannot
   re-declare its way around a completeness gate. Built after a real
   incident: a 2-campaign audit satisfied a 5-marketplace completeness
   check by transcribing an old report. eCan runs unattended
   one-time/recurring scheduled tasks with nobody watching in real
   time — the same failure shape (a task quietly under-delivering while
   its own report reads as complete) is available to us today with no
   analogous guardrail. Worth scoping for skills/tasks whose output is a
   report or a set of decisions, not for every task.
2. **Per-store markdown knowledge base as a memory type distinct from
   RAG**, from vibe-seller's `~/.vibe-seller/stores/<slug>/` — the agent
   writes its own notes as it explores an unsupported platform (which
   button, which path, which trap) and reuses them next run; only
   Amazon/Noon ship hand-authored Skills, everything else is
   self-learned this way. This is *procedural* / learned-by-doing memory
   ("how does THIS store's checkout flow actually behave"), not the
   product/policy document retrieval our RAG feature covers. Worth
   checking whether `agent/memory` already has an equivalent, or whether
   that kind of learned-by-doing knowledge currently has nowhere
   durable, diffable, and human-readable to live.

### Open commercial decisions for business-metric billing (2026-09-21)

Design + backend brief: `cn/tencent/BILLING_METERING_SERVER_TODO.md` in the
**eCan_lambda** repo (it carries cost basis and pricing internals). The plan
explanation page is shipped (`/account/payment-plan/details`, reached from the ?
on each plan card); these are the terms it deliberately does NOT state, because
inventing them would put a made-up number in front of a paying customer.

**Settled already** (so nobody re-litigates): ¥68 is a monthly **minimum
charge** (保底), not a bundled quantity — 月度应付 = max(¥68, Σ usage), unused
part does not roll over. `cs_chat.message_replied` is ¥0.05. Both plans charge
identical unit prices; they differ only by `minimum_charge_minor`.

Open, none of them blocking Phase A (metering in shadow mode):

1. **Per-meter list prices beyond ¥0.05/reply.** Needed before a second
   scenario (`ebay_aftersales`: label printed / return handled / dispute
   handled) can leave shadow mode. Blocks Phase B seeding of `price_book_item`.
2. **Subscription auto-renew, and mid-period cancellation vs the minimum.**
   Pro-rate the floor, or charge it in full? This one has to be decided before
   the first renewal cycle runs, not after — the period-close true-up job
   (§6.1a) needs the rule, and getting it wrong overcharges a real customer.
3. **Refund wording for reversals.** The ledger supports reversal rows; what a
   customer is told when an event is reversed is unwritten.
4. **Whether unused PAYG balance expires.** Currently omitted from the plan page
   entirely rather than shown as an open question. If it does expire, that is a
   term that must appear before purchase, not after.

Unit economics, cost-per-event dashboards and anything else touching margin are
tracked in the backend brief, not here.

### Own fingerprint browser: profile + proxy + session management (2026-09-17)

Plan of record now lives in the **eCan_lambda** repo at
`docs/OWN_FINGERPRINT_BROWSER_PLAN.md` (backend/infra design + cloud
headless design). Pointer and client-side findings:
`OWN_FINGERPRINT_BROWSER.md`.

**Phases 0-2 are BUILT** (`fingerprint/profile_registry.py`,
`fingerprint/fingerprint_browser.py`) and verified against the live Etsy
profile: launch -> attach from a second process -> egress confirmed at the
proxy exit -> close -> cold relaunch, still signed in with no login prompt.
Session persistence itself was always free (Chromium writes to
`--user-data-dir`); what was missing was the binding of identity ->
user-data-dir -> proxy -> fingerprint, and the lifecycle to launch them as a
unit. That now exists.

**Phase 3 is BUILT** too: `browser="fingerprint"` on a browser-automation node
plus a `browserProfileId` is the whole configuration — `BrowserType.FINGERPRINT`
launches the profile, hands back the CDP endpoint, and the node injects the
fingerprint the registry record names. Several nodes share one running browser;
it closes when the LAST AutoBrowser record holding it is shut down, not the
first (found in testing: the first shutdown was killing the browser under a
node still using it).

**Phase 4 is BUILT**: `ecan browser import --from adspower --profile <serial>
--as <id>` (plus `list` / `show` / `remove`). Verified against the live Etsy
profile — 23MB in 8s, and the imported copy launched signed in.

**A management GUI is BUILT** (2026-09-18): Settings → Browser Profiles does
CRUD, proxy, fingerprint, launch/stop and import, over a `browser_profile.*`
IPC facade whose DTO is deliberately not the registry's storage shape (so the
model behind profiles can change without the page changing). The node's
**Browser Profile** field is now a dropdown of registered profiles instead of
free text, and `fingerprint_browser.profile_status()` answers "is it running,
on what port" across processes by reading `.ecan_cdp.json` — which `ecan
browser list/show` now report too. NOT yet clicked through in the running app:
handlers were exercised directly, the page was type-checked and built.

**Profiles are LOCAL BY DEFAULT and that is a requirement, not a gap.** A
profile is a live logged-in seller session plus proxy credentials, so nothing
about it syncs to the cloud, travels with a shared skill, or crosses the IPC
boundary as a password. Guarded by
`tests/unit/test_browser_profile_stays_local.py`, which also asserts every
local artefact is gitignored — the registry, its `.tmp`, the
`browser_profiles.broken-*.json` salvage copy, `fingerprint_profiles/`,
`browser_use_settings.json` (AdsPower api_key + Ziniao credentials) and
`ecan_browser_data/`. That last part matters because **in dev
`app_info.appdata_path` is the repo root**, so these land beside the source;
`browser_use_settings.json` and `fingerprint_profiles/` were both unignored
until 2026-09-18. Nothing was ever committed (history checked). Any future cloud-headless
path must be (1) user-commanded in an action whose purpose is that, (2) scoped
to one profile and one use case — no account-wide switch — and (3) warned
before anything leaves the machine. Do not treat these as defaults a later
convenience can flip.

Still open:
- **Prove it over time.** The plan's own gate: reboot AND a week of idleness.
  **Reboot leg PASSED 2026-09-18** — after a real Windows restart the Etsy
  profile landed on the Shop Manager dashboard signed in, through the proxy,
  ~3s after launch. The idleness leg is open: re-run the same check around
  2026-09-25 without touching the profile in between.
- **`shutdown_browser` cannot close a browser-use session.** Every shutdown
  logs `'BrowserSession' object has no attribute 'close'` — browser-use 0.12
  renamed it, and the call has been failing silently for every browser type,
  not just this one. The CDP connection is left to be reaped.
- **Relay ownership.** The SOCKS relay lives in the launching process, so a
  second process can attach but inherits a relay it cannot restart.
  `launch_profile` refuses to attach when the recorded relay port is dead —
  egressing from the real IP is worse than failing — but a long-lived relay
  service would remove the restriction.

Two findings worth keeping even if the plan is never built:

- **Chromium cannot authenticate to a SOCKS5 proxy.** No command-line form, and
  the extension `onAuthRequired` hook never fires for SOCKS (confirmed by
  grepping AdsPower's own extensions — it is absent). They solve it by patching
  the browser. We solve it with `fingerprint/socks_relay.py`, a local no-auth
  front for an authenticated upstream.
- **An anti-detect profile's real config is only on the RUNNING process's
  command line.** AdsPower's app data holds the Electron app and browser
  binaries, not the profiles; the browser is `SunBrowser.exe`, not
  `chrome.exe`.

A third finding shapes the cloud side: **cookies do not cross platforms.**
Verified — `Local State`'s `os_crypt.encrypted_key` begins with `b'DPAPI'`, so
the key is bound to a Windows account. A Linux pod cannot read it and Chromium
treats the cookies as EMPTY rather than erroring, so it looks fine until the
site shows a login page.

Biggest risk, and the reason to test before building: fingerprint parity is
not achievable (the vendor's opaque launch blob is understood only by their
patched browser) and our stealth-JS substitute is UNTESTED over time. Whether a
store treats it as the same device over weeks is the thing that would
invalidate the approach.

## 🟠 Design smells / v1 limitations

- **WeChat desktop login: no refresh token (v1)** — the PHP bridge returns a bare
  token, so CN desktop sessions won't auto-refresh (re-login on expiry). Enhance
  by having the provision service also return a refresh token.
- **`cloudbase_wechat_qr_login` blocks the IPC request thread** for the whole scan,
  starving init-progress polls during the scan. The 300s poller window covers it,
  but a non-blocking (event-driven) design would be cleaner.

## 🔵 Tmall / Qianniu (Phase 2+) — see docs/TMALL_QIANNIU_CHAT_DESIGN.md

- **2026-10-05 (v0.9.99x): the route taken is the 千牛 DESKTOP client**
  (`qianniu_chat` bundle: memory intake + OCR-verified send). 快速生成 → 天猫客服
  now deploys for real on a rebuilt no-browser 淘宝客服前台01, and 千牛 runs
  alongside 飞鸽 + 拼多多 — see **docs/QIANNIU_TMALL_FAST_DEPLOY.md**. The web
  items below apply only to the abandoned 千牛 Web route. Still open:
  - live calibration (memory body field, OCR header geometry);
  - first alpha run (real LLM turn on `pr-731906`, end-to-end send);
  - publishing 淘宝客服前台01 + `pr-731906` (data).

- **BLOCKER (2026-09-27): there is no 千牛 Web chat to calibrate against.**
  qianniu_probe runs: the web workbench (qn.taobao.com) only has 接待 *settings*
  (接待工具 cards); the 接待中心 itself says "需下载千牛客户端使用". The desktop
  client (AliWorkbench.exe, CEF 9.95/9.97) never opens DevTools (option-3 diag
  verdict DEAD: flag / inner-exe / WebView2-env all failed). So all Qianniu
  selectors are SPECULATIVE with no DOM to calibrate them on.
- **Official routes (researched, none fit eCan as-is):**
  (a) 客服机器人 ISV solution — buyer messages arrive via 奇门
  `qimen.taobao.message.chatrobot.sync`, but the service must run in Alibaba's
  **AIPaaS 封闭环境** (VPC with no public internet, own-Aliyun resources banned)
  → cannot call eCan agents or external LLMs; needs the 【AIPaaS封闭环境】 perm package.
  (b) 客服面板插件 (PC mini-program in the client's 接待中心 sidebar; category
  电商管理→客服工具→客服面板插件, needs 客户服务平台插件权限) — assist mode only:
  JS SDK can `insertText2Inputbox` (human still presses send); no documented
  message-read or direct-send API.
- **Qianniu WS wire protocol uncaptured** — neither route above exposes it;
  `ECAN_TMALL_WS_CAPTURE=1` has nothing to attach to.
- **`im.jinritemai.com` hostname literals** still hard-coded in `event_monitor.py` /
  `browser_node/runner.py` — move behind `bridge.url_detector` before the Tmall WS
  detection lane goes live.

## 🟢 In progress

- **Vendor desktop-workbench (Electron) CDP attach spike (2026-09-05)**.
  `ECAN_CDP_HOST_EXE` (default OFF) makes `_start_chrome_with_cdp` launch
  that exe with only `--remote-debugging-port` and log `[CDP-HOST]`
  target URLs / a VERDICT line. Build tag `v0.9.96y-spike-doudian-app-cdp-1`.
  **Open**: (a) live verdict on a machine with 抖店工作台 installed;
  (b) if attach works, compare target URLs vs the skill's
  `page_url_patterns`; (c) same-window coexistence with the human
  (row-click / typing collisions) is unsolved by design — the safer
  product answer remains a dedicated 客服子账号 in eCan's own Chrome.
  See docs/CDP_HOST_APP_SPIKE.md.
- **CN presigned-flow convergence (2026-08-27, LIVE-VERIFIED)**. 95n
  retest "no diff" root cause: the client's CN file APIs didn't match
  the DEPLOYED SDL — listSkillFiles/readSkillFile return TYPED results
  needing selection sets (client sent scalar shape → validation error
  silently swallowed as "no files listed"), and readSkillFile returns
  content INLINE (no downloadUrl). Meanwhile the CN backend implements
  the FULL intl presigned flow (requestSkillFileUploadUrl/DownloadUrl →
  users/<owner>/skills/<name>_skill.zip) AND the COS signing bug is
  FIXED (live PUT+GET roundtrip 200 from author machine). CLIENT now
  uses presigned zip as primary on CN (upload via real skillId; download
  primary + typed per-file fallback with inline content). GENUINE
  packages for 问答00/前台00/问答0 uploaded to COS and roundtrip-verified.
  REMAINING SERVER ITEM (user): requestSkillFileDownloadUrl must allow
  CROSS-OWNER calls (customer token, owner=author) when the skill is
  isPublic — untestable from the author account; if the resolver
  already skips the owner check, customer downloads work with the next
  build. processSkillZipUpload (explode) still absent on CN SDL —
  needed only for web-editor per-file views.

- **LLM proxy missing-key fallback (2026-08-27)**. Confirmed the
  suspected behavior did NOT exist: proxy routing was purely
  config-driven (ECAN_FORCE_LAMBDA_PROXY / node useProxy / global
  use_lambda_proxy); a missing local API key raised "<provider> requires
  an API key". NOW: all three LLM-construction paths fall back to the
  cloud LLM proxy when the local key/config is missing AND
  lambda_proxy_endpoint is configured — build_node._build_runtime_llm
  (skill LLM nodes; _make_proxy_llm("no local API key") before the
  raise), browser_node build_local_llm and _build_cloud_llm_impl
  (browser-use agents; _proxy_fallback on node-LLM ValueError/
  RuntimeError, global-default None/failure, and the explicit no-key
  raise). Without an endpoint the original errors still raise. Tests:
  tests/unit/test_llm_proxy_fallback.py (13). ✅ 2026-08-27 follow-up
  (3e2f69949): RAG side reroutes key-less LLM/EMBEDDING bindings to the
  proxy in lightrag _compute_system_api_keys (ollama + env-key rows
  untouched); launcher header patch recognizes the CN TCB host; CN
  builds default lambda_proxy_endpoint to
  https://sccb0-d0gc5398xf028be6a.service.tcloudbase.com/api/llm-proxy
  (OpenAI-compatible /v1/chat/completions; user-set value wins, intl no
  default).

- **CN zip-only save + zip-first download (2026-08-26/27)**. CN save now
  uploads ONLY one artifact per skill:
  `{safe_owner}/my_skills/<folder>/_package.zip` (writeSkillFile register
  with content:"" + raw-bytes PUT to the signed URL; ≤20MB cap). The
  per-file upload leg was REMOVED (zip-only convergence — same shape as
  the intl S3 flow). Subscriber download is ZIP-FIRST: readSkillFile on
  `<folder>/_package.zip` (then the owner-prefixed form), signed GET,
  unzip with zip-slip guard; per-file listing remains as DOWNLOAD-only
  fallback for legacy publishes (normalizes owner-prefixed filePaths,
  skips the zip artifact). Verified consumers: cn_worker loads diagrams
  from GraphQL (no COS file reads); per-file COS objects matter only to
  the WEB-mode skill editor → hence server explode requirement below.
  Tests: tests/unit/test_cn_skill_package.py (10).
  **SERVER SPEC (user applies, cn-skill-editor.js)**:
  (1) writeSkillFile must accept `_package.zip` (binary; don't gate on
  text extensions) and return a signed PUT whose signature works for
  arbitrary bytes with no Content-Type (COS signing fix prerequisite).
  (2) **EXPLODE on receipt**: after the package object lands (or on the
  writeSkillFile call), unzip it server-side into per-file objects under
  the same `<owner>/my_skills/<folder>/` prefix (replace-all semantics:
  delete files no longer in the zip) so listSkillFiles/readSkillFile and
  the web skill editor keep working with zero client per-file uploads.
  Guard extraction against zip-slip + absolute paths; cap entry count
  and total uncompressed size.
  (3) readSkillFile cross-owner gate can be NARROW: when userId ≠
  identity.sub, allow ONLY filePath == `<folder>/_package.zip` (either
  path shape) where <folder> maps to an isPublic=true skill owned by
  userId.
  (4) readSkillFile should resolve BOTH path shapes
  (`<folder>/_package.zip` and `<owner>/my_skills/<folder>/_package.zip`)
  to the same object.

- **Skill save-timestamp versioning + read-only (2026-08-26, uncommitted→
  committing)**. `version` = UTC save timestamp yymmddHHMMSSmmm (15
  digits, utils/skill_version.py; legacy "1.0.0" sorts older than any
  timestamp → first re-save upgrades everyone). Stamped on
  save_agent_skill/new_agent_skill (row + diagram JSON, monotonic guard),
  rides the existing cloud push. get_public_skills annotates store rows
  with local_version/update_available (cloud newer → store shows 更新
  button = re-subscribe refresh); own-skill merge repair sets
  update_available + cloud_version when the cloud copy is newer (My
  Skills red badge 云端有新版本; display-only, NO auto-pull). READ-ONLY:
  save_agent_skill rejects SKILL_READ_ONLY when row owner ≠ current user
  (frontend already gates via canEdit/isThirdPartySkill). Tests:
  tests/unit/test_skill_versioning.py (18).
  v0.9.95j CUSTOMER LOG findings (user 1050588178@qq.com): popup "sync
  to cloud failed" = TCB lacks subscribeToSkill mutation; forgotten
  已订阅 = subscription state is device-local until the cloud rel exists;
  file download logged "no files listed" = userId gate not deployed AND
  COS bucket likely empty (SignatureDoesNotMatch upload bug). SERVER
  список (user applies, exact wire shapes in this repo's cloud_api.py
  send_subscribe_to_skill_request / _fetch_cloud_subscribed_skill_ids):
  subscribeToSkill/unsubscribeFromSkill mutations + getSubscribedSkillIds
  query; verify updateAgentSkills persists `version`; userId file gate;
  COS signing fix.

- **pend_event {{front_desk_agent_id}} placeholder (2026-08-25)**. The
  published 飞鸽客服问答00 diagram hard-codes agent_48bdd65f982a4cdb (a
  long-gone author-machine front-desk agent) in its pend_event node's
  agentIds AND matchFields senderId literal — on every other machine the
  Q&A skill filters out all real front-desk dispatches. FIX: runner
  `_extract_event_types_from_skill(skill, task)` now resolves `{{var}}`
  tokens in agentIds / matchFields literals / pendingSources.agentIds
  from `task.metadata["task_vars"]` at task-launch time (unresolvable →
  drop filter, catch-all + WARNING `[EventRouting][task_vars]`; comma
  values become membership lists). douyin_cs fast-deploy now creates
  前台小张 FIRST and stamps `front_desk_agent_id` into every Q&A task's
  task_vars; also verifies 2 more prompts: 飞鸽社交应答0 (pr-543744) +
  飞鸽RAG路由分类0 (pr-56931). Tests:
  tests/unit/test_pend_event_task_vars.py (11) + test_deploy_douyin_cs.
  **USER ACTION**: in the skill editor set 问答00's pend_event agent
  field to `{{front_desk_agent_id}}` (replacing the stale concrete id)
  and REPUBLISH — until then subscribed copies still carry the dead id.

- **Subscribed-skill FILES + paid subscribe flow (2026-08-25, uncommitted)**.
  CONFIRMED user suspicion: subscribe never downloaded the skill's FILE
  package — triply broken: (a) subscribe_to_skill never called the
  downloader, (b) download_skill_files_from_cloud was a NO-OP on CN
  (intl S3-presigned only), (c) CN readSkillFile/listSkillFiles are
  hard-scoped to identity.sub's own COS namespace. Subscribed skills ran
  only from the DB diagram (code-file refs / data_mapping broken).
  CLIENT FIXES: CN per-file download implementation
  (skill_file_sync._download_skill_files_cn via listSkillFiles/
  readSkillFile with userId=author + downloadUrl GET), wired into both
  subscribe branches and the list-time auto-download (subscribed rows now
  download under the author namespace); paid-subscribe flow — frontend
  Modal.confirm for price>0 (monthly charge notice, free = instant
  已订阅) + backend INSUFFICIENT_FUNDS gate (rejects only when
  mainwin._account_info fund is KNOWN and < price; unknown fund does not
  block — real charging is a server-side billing item, still OPEN).
  **SERVER FIX NEEDED (user applies)**: CN cn-skill-editor.js
  listSkillFiles/readSkillFile currently `void userId` and force
  owner=identity.sub — accept the existing `userId` arg for CROSS-OWNER
  reads gated like queryPrompts: allow when the path's skill folder
  (first segment, '<name>_skill') matches an isPublic=true skill owned by
  userId; otherwise keep own-namespace. Until deployed, cross-owner
  downloads list nothing (logged, non-fatal).

- **CUSTOMER-side skill store + prompts (2026-08-24, from customer_logs/
  eCan.log, user wechat_94ef25fd457d171c19a8158a)**. Two distinct roots:
  1. **Empty skill store (CLIENT, fixed)**: `get_public_skills` filtered the
     caller's OWN queryAgentSkills list (owner-scoped server-side) — another
     author's public skills could never appear, and `subscribe_to_skill`'s
     target lookup had the same blindness ("Skill not found in cloud").
     FIX: fetch the real public catalog — CN `queryAgentSkills(input:
     {isPublic:true})` (TCB resolver already supported it, client never
     called it) with `getPublicSkills` (AWS Lambda) and legacy-filter
     fallbacks; subscribe lookup searches own list then catalog
     (`_find_cloud_skill_for_subscribe`). Tests:
     tests/unit/test_public_skill_store.py.
  2. **Prompts unreachable for subscribers (BACKEND, changed in eCan_lambda,
     NEEDS DEPLOY)**: TCB `authenticatedOwner` throws FORBIDDEN on any
     cross-owner read, so a customer could never queryPrompts(id,
     owner=author) — the free-skill runtime prompt fetch was dead on CN.
     FIX in eCan_lambda cloudbase-graphql queryPrompts: narrow exception —
     authenticated caller + specific prompt id + id referenced by an
     isPublic=true skill of the requested owner; everything else stays
     strictly same-owner. UNCOMMITTED in eCan_lambda; deploy via its
     workflow, then verify with the customer flow: store shows skills →
     subscribe → run → prompts resolve under author.
  Still open (backend, non-fatal): TCB lacks `getSubscribedSkillIds` and the
  agent_skill_rels subscription-sync mutation the client calls — local
  subscription persistence works, cloud-side rel tracking silently fails.
  **ROUND 4 (2026-08-24, v0.9.95f test, user 2263962934@qq.com — CN EMAIL/
  CIAM login)**: sync dead for ALL cloud HTTP because the SCF gate rejects
  the CIAM RS256 access token ("Bearer token required" on every call — the
  gate only accepts TCB-context identity or the eCan HS256 session token).
  The v0.9.95f client already calls `mintHttpSessionToken` at login to
  exchange the CIAM token for a session token, but the mutation DOES NOT
  EXIST server-side (`Unknown type "MintHttpSessionTokenInput"` in the
  customer log). SERVER FIX (user applies directly): implement
  mintHttpSessionToken in cloudbase-graphql — SDL input/payload + resolver
  (validate CloudBase token via decode+exp like registerWeChatSession;
  CRITICAL: mint HS256 sub = userIdentifier (the login email) ONLY after
  verifying the accessToken belongs to that user, since identity.sub must
  equal the owner string clients query with) + add 'mintHttpSessionToken'
  to the isWeChatSessionOperation no-session bypass allowlist (auth.js:109).
  Customer must RE-LOGIN after deploy (mint runs at login finalize).
  Store/catalog client fixes verified working in the same log (clean
  fallback, no crash).
  **ROUND 5 (2026-08-25 log)**: server deployed mintHttpSessionToken →
  after RE-LOGIN the mint SUCCEEDS (login_type=password, 30d) and the
  catalog query works end-to-end ("public catalog returned 4 skill(s)").
  Remaining client gaps fixed (uncommitted): (a) restore path never
  minted — `try_restore_cloudbase_session` now calls
  `_finalize_http_session_token`, plus a throttled lazy mint in
  `cloud_api._get_wechat_http_session_token` so LIVE sessions self-heal
  without re-login; (b) deployed SDL populates `isPublic` while `public`
  resolves null → the strict store filter dropped ALL 4 catalog rows →
  empty store tab; filter + fetch conversion now normalize
  public/isPublic/is_public; (c) prompt bulk-push uploaded
  sample_prompts (author-owned ids) from customer accounts → 7×
  "Prompt belongs to a different owner" noise; now skipped by source.
  NOTE: server AI's claims that the client "has no mint call" and "does
  not issue the catalog query" were STALE — both proven working in the
  02:2x log lines. Ship a new client build (v0.9.95g) for the customer.

- **Cloud↔local skill sync: ownerless-row repair** (2026-08-23, uncommitted).
  Diagnosed the "skill_71209937ed7449bf / pr-330448 in cloud PG but not in
  GUI" report: cloud sync-down WORKS (queryAgentSkills returns them — the
  2026-08-21 `public`-field validation bug appears fixed server-side), but
  the LOCAL DB rows were ownerless (owner='', public/rentable=0) and the
  get_agent_skills merge skipped already-local ids without repairing them.
  Ownerless rows are invisible in gui_v2 My Skills (`owner === username`
  filter) and skipped by owner-scoped startup loading. FIX:
  `_repair_local_skill_from_cloud` in skill_handler backfills empty
  identity/store fields (owner/public/rentable/price) from the user's own
  cloud row on every get_agent_skills merge — heals on next Skills-page
  load. SECOND incident same day: 前台00's my_skills FILE twin carried a
  STALE owner (songc@yahoo.com from the previous intl login) — non-empty
  ≠ username, so it stayed hidden and fill-empty-only repair skipped it.
  Repair v2 also corrects owner MISMATCH (the cloud row is pre-verified
  as the current user's, so it is authoritative for identity); the stale
  file owner was fixed in place (my_skills = git-ignored user data).
  6 tests (`tests/unit/test_skill_cloud_repair.py`).
  Prompts side: pr-330448/pr-287230 files ARE in my_prompts and the
  Prompts page has no owner filter — should display; if still missing,
  suspect the store's one-shot `fetched` cache (fetch before sync-down
  completed) — re-check after restart.
  BACKEND ITEM: TCB Query type lacks `getSubscribedSkillIds`
  (GRAPHQL_VALIDATION_FAILED every Skills-page load, non-fatal — cloud
  subscription-rel checks silently fail). Fix in eCan_lambda SDL per
  Section 5.

- **快速生成 → 抖店客服 (douyin_cs Fast Deploy) — REAL, shared-skill model**
  (2026-08-23). `cli/deploy/commands.py::_deploy_douyin_cs` rewritten: verifies
  visibility of skills skill_4f24592c81894ae7 (飞鸽客服问答00) +
  skill_71209937ed7449bf (飞鸽客服前台00) and prompts pr-287230/pr-330448
  (local store, then cloud under the skills' author); creates N tasks
  飞鸽客服应答00N + 飞鸽客服前台001 (trigger auto) REFERENCING the shared
  skills; agents 客服小X (name pool) + 前台小张 under Sales org, pinned to
  the local vehicle. store_url/store_urls propagate as task_vars →
  {{store_url}} in prompts. Panel pops the CLI result. 9 tests
  (`tests/unit/test_deploy_douyin_cs.py`).
  **TO VERIFY / REMAINING:**
  1. Prompts pr-287230/pr-330448 must actually reference `{{store_url}}`
     where the store link matters (prompt content edit, no code).
  2. Front-desk skill's auto-dispatch `filter_by_tasks` must match the new
     task names (contains "客服应答", NOT the old "客户应答" example) —
     check skill_71209937ed7449bf's dispatch config.
  3. GAP: browser-monitor `page_url_patterns` (cdpFilterExpr) is build-time
     skill config — NOT per-task overridable, so a shared front-desk skill
     can't carry per-deployment store hosts. Mitigation: the Feige IM host
     im.jinritemai.com is shop-independent — ship it in the shared template.
     If per-store page monitoring is ever needed: extend the Phase-3
     state-override channel to event-monitor URL patterns.
  4. Old QA trigger was "message"; per spec these use "auto" — queue
     polling auto-enables on pending items, but validate in a live run.
  5. Live end-to-end (subscribe → deploy → agents answer) untested.

- **Shared skill / multi-task plan** (2026-08-23) — multiple tasks/agents
  (and hosts) reference ONE skill with per-task variables; concurrent runs
  from day one (no per-skill lock). Full phase list + blocker table in
  `docs/SHARED_SKILL_MULTI_TASK_PLAN.md`.
  **Phase 1 DONE 2026-08-23**: per-thread checkpoint cleanup in
  `executor._clear_skill_module_caches` (was wiping the whole shared
  InMemorySaver) + task-scoped re-key of the mt068 agent-id recovery cache
  + 10 regression tests (`tests/unit/test_shared_skill_phase1.py`).
  **Phase 1.5 DONE 2026-08-23**: vehicle/host affinity gate at
  `EC_Agent.start()` (`agent/ec_agents/vehicle_affinity.py`, fail-open,
  kill switch `ECAN_DISABLE_VEHICLE_AFFINITY=1`) + local-vehicle
  registration + `ecan agents update --vehicle this|none|<id>` + 13 tests.
  gui_v2 vehicle-assignment UI deferred.
  **Phase 2 DONE 2026-08-23**: per-task `task_vars` seeded into
  `prompt_refs` for ALL trigger types (`apply_task_vars` in
  prep_skills_run.py, wired in runner `_execute_skill`); persisted in DB
  task settings; `ecan tasks add --skill --var k=v` / `update --var`;
  12 tests (`tests/unit/test_task_vars_phase2.py`). gui_v2 task-create
  `need_inputs` form deferred; hybrid-cloud path doesn't apply vars yet.
  **Phase 3 DONE 2026-08-23**: per-task browser identity
  (`resolve_state_browser_identity` + task `browser_identity` seeded via
  `apply_task_vars`; profile/user_data_dir/headless/cdp_port resolvable
  per run, state wins over node config incl. an `acquire_browser`
  precedence fix) + agent-suffixed pinned browser scopes
  (`node:<node>:<agent_id>`, mt068-sticky); CLI `--browser k=v`;
  16 tests (`tests/unit/test_browser_identity_phase3.py`) + updated
  front-desk scope contract tests.
  **Phase 4 DONE 2026-08-23**: `ecan skills dedupe [--apply] [--delete]`
  (identical-diagram duplicate detection + reference re-pointing via new
  `DBSkillService.find_duplicate_skills`/`merge_skill_references`); FIXED
  author-prompt wiring gap — `_compile_skill_workflow_from_flow` now
  injects `skill_obj.skill_owner` as the flow owner so store/rented skill
  prompts resolve under the AUTHOR (was resolving under the runner);
  9 tests (`tests/unit/test_skill_dedupe_phase4.py`).
  **Follow-ups batch DONE 2026-08-23** (uncommitted): hybrid-cloud/
  cloud-worker task_vars (companion inheritance + WorkerMessage fields +
  CN worker extraction); skill_owner now persists via config JSON fold
  (was silently dropped by add_skill's column filter); gui_v2 task-create
  Task Variables form from skill need_inputs; vehicle dropdown merges DB
  rows + gate accepts legacy same-host rows ("local-legacy-row");
  **Phase 5a** done (typing_lock {session: holder} + session-scoped
  dispatch-inflight keys, single-shop behavior identical). REMAINING:
  Phase 5b per-session runner-bridge/WS/CDP plumbing (deferred — one
  process per shop); live two-account store e2e; AWS-side envelope
  senders passing task_vars (backend repo).

- **Account top-up / payments** (2026-08-12) — region-detected top-up wired:
  - CN → in-app payment dialog (`gui/payments/payment_dialog.py`, embedded
    QWebEngineView) loads the proven web entry (`apps/cn/config/payment_config.json`
    `entry_url` → `…/cn/payment-test/index.php`), which offers Alipay + WeChat Pay;
    the dialog watches the page's server-verified `#state` and returns SUCCESS/FAILED.
    Handler: `payment_topup` (`gui/ipc/w2p_handlers/payment_handler.py`, auth-required).
  - Intl → existing Stripe flow (`Account.tsx` navigates to `/account/payment-plan`).
  - Top-up button (`Account.tsx handleTopUp`) branches on `useIsCN()`.
  - **FOLLOW-UPS (not done):**
    1. **Balance is not credited yet.** The test endpoints verify payment but don't
       credit `Account.fund` for the paying user. Server-side: associate the order
       with the logged-in user (pass user id to the payment start) and credit
       `Account.fund` (AppSync `updateAccts`/`makeOrder`) in the payment-notify
       handler. Until then, top-up executes payment but the balance won't move.
    2. **Fixed amount.** Test server charges ¥0.01 regardless of the entered amount;
       needs a variable-amount server endpoint (the app already forwards `?amount=`).
    3. **Confirm the deployed CN payment URL** — `entry_url` defaults to
       `www.fastprecisiontech.com/cn/payment-test/index.php`; verify it's live there.
    4. Intl "Stripe link" for variable-amount top-up (vs the existing fixed
       subscription buy-buttons in `PaymentPlan.tsx`) — confirm intended UX.
    5. `payment_topup` blocks the IPC thread while the modal is open (acceptable —
       the dialog is ApplicationModal — but a non-blocking design would be cleaner).

---

## ✅ Recently done
- 2026-10-06 — 千牛 alpha v0.9.99x dispatched nothing for 8 h. Fixed in
  v0.9.99ya:
  - the observer scanned the CHILD AliWorkbench.exe; chat is in the root;
  - `seller_id_of` named a lone buyer as the seller;
  - added a cold-start baseline + stale skip (memory holds history);
  - added INFO logs for every step of the chain, failure screenshots in
    `runlogs/qianniu_ocr/`, and a 5-min heartbeat.

  Log map: docs/QIANNIU_TMALL_FAST_DEPLOY.md §8.
- 2026-10-05 — 天猫客服 Fast Deploy is real (was a stub that showed 失败):
  - `_TMALL_PROFILE` (native desktop: no Chrome pre-check / browser login /
    store URL; Q&A pool passed as `task_vars.qa_agent_ids`);
  - 淘宝客服前台01 rebuilt as pend_event → prep code → LLM → qianniu_* tools;
  - `ECAN_LIVE_CHAT_SITE` merged, not replaced; Settings switch multi-select;
  - `hookBundles` on the skill stops a 千牛 reply reaching another platform's
    browser.

  Details + debugging playbook: docs/QIANNIU_TMALL_FAST_DEPLOY.md.
- 2026-08-16 — CN HTTP cloud auth, round 2: the 08-12 fix was insufficient — the
  SCF HTTP gate (`cloudbase-graphql/scf/auth.js resolveIdentity`) cannot validate
  the WeChat access JWT (`uid` claim, no `sub`) over plain HTTPS; only the
  eCan-minted 30-day session token passes `verifySessionToken`. Server side:
  `registerWeChatSession` exempted from the gate (deployed). Client side:
  `_http_auth_header()` now prefers the stored WeChat session token as the CN
  HTTP bearer (fallback: extracted access JWT); `endpoints.build_http_headers`
  routed through the same helper (covers wan_chat / wan_a2a_chat HTTP);
  `_register_wechat_session` / `_refresh_wechat_token` no longer crash on
  `data: null` responses. WS paths untouched. **Verify:** reqAccountInfo +
  offline-queue agent replay after next login; 李四's queued add is in the
  *failed* list and may need manual re-queue.
- 2026-08-12 — CN HTTP cloud auth: `Bearer token required` fixed. The WeChat
  session token is the combined `<id>/@@/<jwt>` form (works verbatim over WS,
  rejected by the HTTP GraphQL endpoint). Added `_http_auth_header()` in
  `agent/cloud_api/cloud_api.py` that extracts the JWT and sends `Bearer <jwt>`
  for CN HTTP (intl unchanged; WS paths untouched). Applied to
  `appsync_http_request` / `request2` / `request8` / `runCloudTasks`.
  **Follow-up (nice-to-have):** have the WeChat provision endpoint return a
  plain CloudBase JWT (like email login) so the combined form isn't needed at all.
- 2026-08-12 — Account top-up payment: fixed dialog-parent crash (MainWindow is
  not a QWidget → guard with isinstance) + CN currency symbol (¥ not $).
- 2026-08-11 — CN desktop WeChat QR login (tag `wechat_login_succeed`)
- 2026-08-11 — Fixed `MainGUI.py` IndentationError (login-blocker) + poller 60s→300s
