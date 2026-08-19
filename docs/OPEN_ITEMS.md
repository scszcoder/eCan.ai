# Open Items / Tech-Debt Tracker

Running list of known-but-unfixed issues, deferred work, and follow-ups.
Add new items at the top of their section. Mark done with ✅ + date, or
delete once merged and verified.

_Last updated: 2026-08-11_

---

## 🔴 Bugs (unfixed)

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
- **`gui_v2/pnpm-lock.yaml` uncommitted** — updated when `@cloudbase/js-sdk@3.7.1`
  was installed (the merge added it to package.json but not the lockfile). Commit
  so teammates don't hit the same Vite "failed to resolve import" wall.

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
