# Handoff 2026-10-27/28: intl edition, cloud sync, eCanAI proxy, Amazon and Shopify after-sales skills

Branch: `us_ec_skills` (pushed). Edition: intl (`.env` has `ECAN_APP_ID=intl`, skip-worktree).
Run the app with the venv: `.\.venv\Scripts\python.exe main.py` (system Python 3.13 lacks deps and
causes a login-page refresh loop). `npm run dev` in `gui_v2` serves the UI on port 3000; the local
server is on 4668; the embedded browser exposes CDP on 9223.

Account-specific findings (store red flags, ASINs, reports) are deliberately NOT in this repo.
Reports live in `C:\reports\amazon\<store>\<date>\` on the machine that ran them.

## What is done (commits on us_ec_skills)

| Area | Change |
|---|---|
| intl fleet | store/fleet/transfer/turn/pod/usage calls go to AppSync on intl (`agent/cloud_api/intl_fleet.py`); CN unchanged |
| WebSocket | saved `ws_api_endpoint` on the AppSync HTTP host is moved to `appsync-realtime-api` (was a 400 reconnect loop) |
| Orgs | a new department shows in the agent editor's list at once (shared org store refreshed) |
| Agents page | avatar videos 640px and play on hover; reduced-motion CSS uses `0s` (the 0.01ms transition pushed antd popups ~8000px off-screen); double-click a card to open it |
| eCanAI proxy | proxy base per edition from `apps/<edition>/config/auth_config.yml` `LLM_PROXY.BASE_URL` (`agent/cloud_api/endpoints.py:llm_proxy_base`); intl = US Lambda `.../v1` |
| Model list | live from the US proxy (122 models incl. `gpt-6-luna`); a failed fetch warns once |
| Login-token fallback | intl eCanAI with no account key uses the Cognito token (`endpoints.llm_proxy_session_token`), resolved in `extract_provider_config`; Settings shows eCanAI as configured when signed in |
| Key leak | `create_browser_use_llm_by_provider_type` no longer fills `OPENAI_API_KEY` in for non-OpenAI providers (it was sent to the eCanAI proxy) |
| run_agent_task | refuses to hand a task to a different agent when the task's agent is not loaded (used to fall back to `agents[0]`) |
| Cloud sync | `cloud_hydrate` rebuilds a UI skill folder from its cloud record's diagram/config when no files archive exists (all intl skill uploads failed server-side) |
| Reports | `agent/ec_skills/reports/report_store.py` (local dated folder + presigned S3 upload, "pending" until the server mutation exists) and `amazon_report.py` (renders report.md/report.json; a failed run says "CHECK DID NOT COMPLETE", never an all-clear) |
| Store reports | `store_report.py` renders any platform's run (amazon, shopify); report.md opens with the day title `N orders, N processed, N todos, N redflags` (`report_store.day_title`); a report naming a different store than the folder is filed as CHECK DID NOT COMPLETE; `amazon_report.py` is a thin wrapper |
| Skill guessing | a task with no bound skill no longer gets one by shared generic words when several skills tie (`ebay_after_sales_daily` was handed `shopify_after_sales` and ran it on the Shopify stores) |

## Local-only state (not in git)

- `my_skills/amazon_after_sales_skill/` was rewired: Start -> `Amazon_Triage` (browser-automation,
  eCanAI `gpt-6-luna`, the store's fingerprint browser profile, maxSteps 40, prompt `pr-23537`) -> `Save_Report`
  (code step calling `save_amazon_run_report(state, store_name="sc_amazon_0")`) -> End.
  The pend_event/loop that waited on an unrelated agent was removed.
- Prompt `pr-23537` ("amazon_after_sales") holds the read-only Amazon instructions (it was a copy of
  the Feige front-desk prompt, as are etsy/shopify/tiktok/manage_after_sales).
- User settings: `default_llm=ecanai`, `default_llm_model=gpt-6-luna` (startup cleared the model to "";
  the skill's node names its own model).
- Neither the skill folder nor the prompt reaches the cloud until server item 1 below is fixed; save
  the skill in the editor after that to upload it.
- Store browser profiles (2026-10-28): each store has its own fingerprint browser profile
  (Settings -> Browser Profiles; registry `browser_profiles.json`, gitignored; data under
  `C:\ecan_browser_data\`), signed in once by the seller. Each store's browser step sets
  `browser: fingerprint`, `browserProfileId: <profile id>`, `cdpPortAuto: true`; the step launches the
  profile or attaches to it if already running, on a free port. Never recreate, reset or delete a
  signed-in profile or clear its data: it is the store's login. If a session expires, the seller signs
  in again in that profile. To open one by hand: local-server method `browser_profile.launch
  {id, start_url}`. Profiles have en-US, preset `win_chrome_02`, no proxy (add one per store in the
  profile settings if wanted).
- Older shared automation Chrome (fallback, no longer used by these skills): `C:\chrome_data` profile on port 9228, launched with
  `agent.mcp.server.chrome_launcher.launch_chrome_debug(9228, extra_flags=[<url>])`; the seller signs
  in once there.

- `my_skills/shopify_after_sales_skill/` (skill_566d45b267e94806) checks two stores in turn:
  Start -> `code_set_<store>` -> `shopify_triage_<store>` (browser-automation, eCanAI `gpt-6-luna`,
  the store's own browser profile, maxSteps 40, prompt `pr-218691`) -> `code_save_<store>` (`save_store_run_report(state,
  "shopify", store_name=<store>, node="shopify_triage_<store>")`), for two stores, then End.
  The set step must write `state["attributes"]["current_invocation_input"]` ("Designated store: ...");
  a top-level state key is dropped between steps and the browser step then never learns the store.
  A set step can also name legacy orders to ignore.
- Prompt `pr-218691` ("shopify_after_sales"): read-only Shopify checks, stop if no store is given,
  list every open order from the list page, ~30-action budget, skip pages still loading after one wait.
  Prompts are read at app start: restart after editing one.

## How to run the Amazon skill

1. App running and signed in; the store's browser profile signed in to Seller Central (the step opens it).
2. Start the task (same request the UI's Run button sends) by POSTing to the local server from the
   app page, method `run_agent_task`, params `{username, task_id: "task_37b055101b834999",
   skill_id: "skill_9015d67186384b7a", skill: "amazon_after_sales", agent_id: "agent_4c1832d018a34ada"}`.
   The task has no `agent_id` of its own, so pass it.
3. A chat message to the agent (`send_chat` with `receiverId` = the agent id) also starts the task and
   its text is appended to the browser task ("Current Invocation Input"); use this for focused passes.
4. Watch `runlogs/eCan.log` for `skill=amazon_after_sales`; the report lands in
   `C:\reports\amazon\sc_amazon_0\<date>\`. Note: test runs also write to eCan.log, so match the
   real reports path when waiting.

Observed cost: daily check 13 steps / 25 calls / ~162k tokens; a broad deep dive hit the 40-step cap
(81 calls / ~530k tokens). Split deep dives into small chat-message passes.

## How to run the Shopify skill

Agent "Shopify Operator" (agent_cd634be668ca48d3), task `shopify_after_sales_daily`
(task_5606d1b634444711, schedule trigger). It starts by itself at app start when due; otherwise use
`run_agent_task` as above with that task, skill_id `skill_566d45b267e94806`, skill
`shopify_after_sales`. Reports: `C:
eports\shopify\<store>\<date>\`. A run takes ~6 min for both
stores. The app starts a new `runlogs/eCan.log` on restart, so a `tail -f` started before a restart
sees nothing.

## Open items

Server (paste on the AWS machine):

1. `requestSkillFileUploadUrl` returns `null` with no error on intl (AppSync API
   `3oqwpjy5jzal7ezkxrxxmnt6tq`, us-east-1). Both resolver implementations in the repo
   (`lambda_functions/skill_editor_lambda/handler.py:_handle_request_skill_file_upload_url`,
   `lambda_functions/agentScheduler/index.js` case `requestSkillFileUploadUrl`) return a URL or throw,
   so the deployed field is attached to something else (NONE data source / wrong Lambda / response
   template). Expected `{uploadUrl, s3Key, expiresIn}` or an error.
2. `requestSkillFileDownloadUrl` with no archive fails with "Cannot return null for non-nullable type
   ... SkillFileDownloadResult"; return NOT_FOUND or make the fields nullable.
3. New `requestReportUploadUrl(input: ReportUploadInput!): ReportUploadResult` with input
   `{category, storeName, date (YYYY-MM-DD), fileName}` and result `{uploadUrl, s3Key, expiresIn}`;
   bucket `ecan-reports` (S3 names cannot contain `_`); key
   `<user_id>/<category>/<storeName>/<date>/<fileName>` with user_id from the token; sanitise names;
   presigned PUT ~15 min; content types text/markdown, application/json, text/html, text/csv,
   application/pdf. The client (`report_store.py`) already calls this shape.
4. `queryApiKeys` on intl lacks `items` (`QueryApiKeysResponse`); align with CN
   `items: [{id, key, name, createdAt, revokedAt}]` and confirm `reqApiKey` on intl. Until then intl
   desktops use the ~1 h Cognito token for the proxy.
5. Subscriptions `onA2AMessage` and `onAgentEndpoint` are undefined on the intl schema (many startup
   errors).

Client:

- Shopify prompt: payments/payouts, domains and billing pages often still show loading placeholders
  after the one allowed wait, so those checks are skipped (noted in the report); a longer wait on
  those pages or another way to read them is the main gap. The payouts URL in the prompt answered
  "There's no page at this address" once.
- gpt-6-luna sometimes answers with its own notes instead of the action JSON; six in a row end the
  browser step ("consecutive failures"). A rerun got through; a fallback model would make it robust.
- The eBay Operator task `ebay_after_sales_daily` has no skill bound and now runs nothing until one is.
- The browser-step / agent eCanAI client is created with the login token once; a run longer than
  the token's ~1 h life will 401. Fix properly via an account key (server item 4) or a token-refresh
  hook like the CN `ChatLambdaProxy` path.
- `lightrag_template.env` and the gui_v2 knowledge-parser defaults (`SettingsTab.tsx`,
  `providerConfig.ts`) still default to the CN proxy.
- `test_ecanai_provider_support.py::test_lightrag_effective_env_follows_system_ecanai_defaults_and_keys`
  fails with `KeyError: 'RERANK_BINDING_HOST'` (pre-existing).
- The ChipDocsCoordinator agent auto-starts `chip_docs_crawl_manager_00` on startup with an OpenAI
  `gpt-5.6-sol` node; with a working OpenAI key it spends on every start.
- The reconnect loop in `agent/cloud_api/cloud_api.py:_appsync_ws_reconnect_loop` / passive client
  tracks a new thread per attempt (thread growth during long outages).
- `mcp_tools_schema.json` is regenerated by test runs; it is left uncommitted on purpose.
