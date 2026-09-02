# Open Items / Tech-Debt Tracker

Running list of known-but-unfixed issues, deferred work, and follow-ups.
Add new items at the top of their section. Mark done with ✅ + date, or
delete once merged and verified.

_Last updated: 2026-09-02_

---

## 🔴 Bugs (unfixed)

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

## 🟡 Environment / deps

- **`zeroconf` module missing** — LAN discovery disabled on the CN dev machine
  (`discovery imports failed: No module named 'zeroconf'`). `pip install zeroconf`.
- ✅ 2026-08-19 **`gui_v2/pnpm-lock.yaml` uncommitted** — committed with the
  CN skill-editor chat fallback fixes.

## 🟠 Design smells / v1 limitations

- **WeChat desktop login: no refresh token (v1)** — the PHP bridge returns a bare
  token, so CN desktop sessions won't auto-refresh (re-login on expiry). Enhance
  by having the provision service also return a refresh token.
- **`cloudbase_wechat_qr_login` blocks the IPC request thread** for the whole scan,
  starving init-progress polls during the scan. The 300s poller window covers it,
  but a non-blocking (event-driven) design would be cleaner.

## 🔵 Tmall / Qianniu (Phase 2+) — see docs/TMALL_QIANNIU_CHAT_DESIGN.md

- **All Qianniu selectors are SPECULATIVE** — calibrate against the live 千牛 Web
  workbench (bundle README playbook) before real use.
- **Qianniu WS wire protocol uncaptured** — reverse-engineer from
  `ECAN_TMALL_WS_CAPTURE=1` logs to build the `ws_reader`/`ws_sender` equivalents.
- **`im.jinritemai.com` hostname literals** still hard-coded in `event_monitor.py` /
  `browser_node/runner.py` — move behind `bridge.url_detector` before the Tmall WS
  detection lane goes live.

## 🟢 In progress

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
