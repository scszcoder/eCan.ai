# Handoff 2026-10-27 to 11-08: intl edition, cloud sync, eCanAI proxy, store after-sales skills, product research skills

Branch: `us_ec_skills` (pushed). Edition: intl (`.env` has `ECAN_APP_ID=intl`, skip-worktree).
Run the app with the venv: `.\.venv\Scripts\python.exe main.py` (system Python 3.13 lacks deps and
causes a login-page refresh loop). `npm run dev` in `gui_v2` serves the UI on port 3000; the local
server is on 4668; the embedded browser exposes CDP on 9223.

Account-specific findings (store red flags, ASINs, reports) are deliberately NOT in this repo.
Reports live in `C:\reports\<platform>\<store>\<date>\` on the machine that ran them.

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
| Stealth script | `fingerprint/stealth_injection.js` parses once filled in (list values were pasted inside `JSON.parse("...")`, a SyntaxError, so no fingerprint was ever applied); `test_stealth_js_syntax.py` runs `node --check` on every preset |
| WebRTC on proxy | Chrome ignores `--force-webrtc-ip-handling-policy`; before a proxied launch `fingerprint_browser._keep_webrtc_on_proxy` merges `webrtc.ip_handling_policy=disable_non_proxied_udp` into the profile's `Default/Preferences` (only those keys change, sign-ins are kept). Without it a STUN request returned the PC's real IP around the proxy |
| Etsy reports | `store_report.PLATFORMS` has `etsy` (orders, `buyer_messages`, listings) |
| eBay reports | `store_report.PLATFORMS` has `ebay` (Seller Hub names) |
| Signed-in profiles | a registered fingerprint profile runs as launched, with no page-level JS fingerprint (`runner.apply_stealth_fingerprint`). The skill-only fake GPU/CPU/canvas differed from the device the seller signed in on, and eBay answered with a CAPTCHA and a password reset |
| Sign-in across restarts | an app restart kills the proxy relay (it lives in the app); a running profile now gets its relay back on the same port and is reused instead of closed (`fingerprint_browser._revive_relay`). Profiles launch with `--restore-last-session` and close via CDP `Browser.close` (`close_profile`), the only combination that keeps session-only cookies (eBay `s`/`ebay`) across a full close. Closing a window with its X still loses them; close store windows from the app |
| Run now on scheduled tasks | a schedule-only task's loop lost its task after its first idle pass, so `run_agent_task` only queued a message that waited for an app restart; the loop now keeps its own task (`runner._launch_unified_run_impl`) |
| Research reports | `reports/review_report.py` (review mining: complaints with quotes, praise, improvement ideas, competitors, `reviews_read` count, a note when Amazon asked for the password again; a run with no listings is "MINING DID NOT COMPLETE") and `reports/idea_verdict.py` (blunt verdict on a product idea) |
| Chat greeting | the chat page's own greeting (role `agent`) is saved, not routed: routing looked for the user as an agent and posted "This agent is not on this machine" into every new chat (`chat_handler.handle_send_chat`) |
| Account page (intl) | shows the signed-in account (`userStore.username`) when the cloud account row has no email |

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
- Proxied profiles (2026-10-29): `ebay_0` (preset `win_chrome_02`) and `etsy_0` (`win_chrome_01`) share one
  SOCKS5 proxy (host/port/type/user/password in `C:\software\proxy.txt`; never print them). Created with
  local-server `browser_profile.save` plus `proxy_password` (stored in the OS keyring; the registry keeps
  `password_ref`); SOCKS5 with auth goes through a local `socks_relay`. The provider only accepts
  whitelisted source IPs, so a new PC or IP must be whitelisted first. Before anyone signs in to a new
  proxied profile, check its exit IP (ipinfo.io) and that a STUN `RTCPeerConnection` gives no candidate
  with the real IP. `etsy_0` is signed in; `ebay_0` is not yet.
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
  list every open order from the list page, ~30-action budget. Settings pages render in 6-12 s, so the
  prompt waits 12 s (+10 s once), opens `/settings` once and clicks Payments/Billing/Domains in the
  Settings left menu: settings pages typed by URL stall mid-render inside the app's agent session (not
  reproducible outside the app; root cause unknown). `/payments/disputes` and `/inbox` are not admin URLs.
- `my_skills/etsy_after_sales_skill/` (skill_73e13d44573346b9): Start -> `code_set_etsy` ->
  `etsy_triage_<shop>` (browser-automation, `gpt-6-luna`, profile `etsy_0`, prompt `pr-557496`) ->
  `code_save_etsy` (`save_store_run_report(state, "etsy", store_name=<shop>, node=...)`) -> End.
  Prompt `pr-557496` ("etsy_after_sales", was a Feige front-desk copy) is read-only and allows only these
  Shop Manager URLs: `/your/shops/me/dashboard`, `/your/orders/sold`, `/messages`,
  `/your/shops/me/policy-violations`, `/your/account/payments`, `/your/shops/me/search-visibility`,
  `/your/shops/me/customer-service-stats`.
  Prompts are read at app start: restart after editing one.
- Product research (2026-11-06/08): `my_skills/review_miner_skill/` (skill_f656f23ee8ee4a07) and
  `my_skills/idea_reality_check_skill/` (skill_09758ce57fcd447e). Each runs one browser-automation step
  (eCanAI, profile `amazon_research_0`, maxSteps 70, prompt `pr-500372` "amazon_review_mining") and a
  code step that saves the report. `amazon_research_0` (`win_chrome_01`, no proxy) is signed in with a
  separate Amazon shopper account, not the seller account; same no-touch rule as the store profiles.
  The prompt is read-only (no cart, buy, review, Helpful, follow; no account or order pages; never
  types into sign-in fields), answers by action 62, reads the critical reviews page
  (`/product-reviews/<ASIN>/?filterByStar=critical&sortBy=recent`) and sets `signin_required` when
  Amazon asks for the password. A prompt saved through the local server needs `"format": "md"` and
  `mdContent`, or the step runs with the guardrails only (browser task length ~1.1k instead of ~10k).
  Skills compile when registered: restart the app after changing a diagram on disk.

## How to run the research skills

Agent "Review Miner" (agent_cbc6d22197f9419f, task_84e29a6711334839) and agent "Idea Reality Check"
(agent_f837fa0778984d96, task_bce0330953f54e2d). Send a chat message to the agent (`send_chat` with
`receiverId` = the agent id): a niche for Review Miner (e.g. "bamboo cutting board"), a product idea
for Idea Reality Check. Reports: `C:\reports\review_mining\<niche>\<date>\` (report.md, report.json).
Not yet run end to end: the eCanAI gateway gives empty answers (server item 6).

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
`shopify_after_sales`. Reports: `C:\reports\shopify\<store>\<date>\`. A run takes ~6 min for both
stores. The app starts a new `runlogs/eCan.log` on restart, so a `tail -f` started before a restart
sees nothing.

## How to run the Etsy skill

Agent "Etsy Operator" (agent_7b156097178b4ba4), task `etsy_after_sales_daily` (task_b893fd8c3c2f4488,
already linked to skill_73e13d44573346b9). Use `run_agent_task` as above with skill `etsy_after_sales`.
For about a minute after a restart it answers AGENT_NOT_FOUND while agents build; retry. Reports:
`C:\reports\etsy\<shop>\<date>\`. The first run (2026-10-29) took ~5 min.

## How to run the eBay skill

Agent "eBay Operator" (agent_1d2e6fb62b7e4af1), task `ebay_after_sales_daily` (task_f458094a8f51423f,
schedule trigger, linked to skill_31a78604324940e9 `ebay_after_sales`, local-only). It runs at app start
when due; `run_agent_task` as above now starts it at once, no restart needed. Browser: fingerprint
profile `ebay_0` on the shared SOCKS5 proxy (password in the OS keyring). The prompt stops on any
CAPTCHA/verify page with `login_required`. Reports: `C:\reports\ebay\<seller>\<date>\`. A full run
takes ~4-5 min. Never edit `ebay_0`'s cookies/Preferences or navigate it by hand for probing (the
seller's rule).

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
6. eCanAI LLM proxy (US Lambda `/v1`): since 2026-11-06 every chat completion returns HTTP 200 with
   an empty `choices` list (still on 11-08; last good answer 10-30). Every skill on eCanAI fails,
   including the daily eBay/Etsy runs.
7. `reqApiKey` on intl: the deployed field is `reqApiKey(input: CustomerInput): genKeyResponse!` and
   the resolver returns null ("Cannot return null for non-nullable type: 'genKeyResponse'"), so
   Account -> Generate API key fails. The repo schema (`agent/cloud_api/appsync_schema.graphql`) has
   `reqApiKey(ops: [KeyOp]!): AWSJSON!`; align the two.
8. The intl account query (`get_account_info`) returns `{"statusCode":200,"body":{}}`, so the Account
   page shows Free Tier, $0 and 0 quota. CN returns the account rows.

Client:

- Shopify: payments are now read in both stores. One store's Domains/Billing still stayed on
  placeholders, and its alert feed, plus the other store's Inbox/app list and sales-channel panel, went
  unread. The root cause of the in-app settings render stall is open.
- gpt-6-luna sometimes answers with its own notes instead of the action JSON; six in a row end the
  browser step ("consecutive failures"). A rerun got through; a fallback model would make it robust.
- eBay: first full run 2026-10-31. An earlier run that day hit an eBay security challenge after one
  page change; the proxy egress is a datacenter range (Cogent). A residential proxy, or slower page
  changes, would cut challenges. The app logs the proxy host in `[socks-relay] listening on ...`;
  mask it when sharing logs.
- A store window closed with its X loses session-only cookies. Covering that needs an AdsPower-style
  cookie save/restore, which writes into the profile: the seller has to approve it first.
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
