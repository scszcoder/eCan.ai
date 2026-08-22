# Open Items / Tech-Debt Tracker

Running list of known-but-unfixed issues, deferred work, and follow-ups.
Add new items at the top of their section. Mark done with ✅ + date, or
delete once merged and verified.

_Last updated: 2026-08-19_

---

## 🔴 Bugs (unfixed)

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
