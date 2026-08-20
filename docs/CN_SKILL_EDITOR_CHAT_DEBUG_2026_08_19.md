# CN Skill Editor Chat — Debug Session 2026-08-19

End-to-end debugging of "hello → fake workflow template" in the CN desktop
chat panel, from first repro to working cloud chat. Companion to commit
`9271b6a5d` (SSE display streaming via llm_proxy).

## Symptom

Typing `hello` in the chat panel returned:

> Here is the workflow I'm planning to build:
> (Auto-generation failed — proceeding with original request.)
> hello
> — Would you like me to **proceed** with this design…

On repeat turns the reply nested the previous reply recursively.

## Root-cause chain (three stacked failures)

1. **TCB cloud errors.** `sendSkillEditorChatMessage` and
   `getSkillEditorChatSessions` on the Tencent GraphQL service
   (`sccb0-…service.tcloudbase.com/api/graphql`) returned
   `INTERNAL_SERVER_ERROR` (~250 ms, deterministic).
   `createSkillEditorChatSession` worked, so auth/routing were fine.
   Fixed server-side (VPC/NAT + llm_proxy work, 2026-08-19 evening).
2. **Local fallback had no usable LLM.** On cloud failure the handler falls
   back to the in-process `SkillEditorAgent`, whose LLM was OpenAI with the
   `sk-placeholder-key-for-first-time-setup` key → every call 401'd → the
   agent emitted its template ("Auto-generation failed…") instead of failing
   cleanly.
3. **Stale pipeline state made it recursive.** The local session persisted
   `pipeline_state=reviewing_workflow_description`, so each new bare `hello`
   was treated as *feedback on the previous workflow description*, embedding
   the prior reply into the next one (`skill_editor_agent.py` workflow-review
   path).

A fourth, separate failure surfaced mid-debugging: after the WeChat access
JWT expired (~36 min), `AuthManager` reported "Token expired, no WeChat
session token available" even though the 30-day session token had been
registered at login — so `se_cloud_relay` had no auth token and the request
never left the machine. Server logs (correctly) showed no llm_proxy call,
which misled the server-side analysis into concluding the desktop was still
routed to legacy AWS AppSync. It wasn't: the desktop relay has always
targeted the TCB endpoint; the "AWS agent" text was generated locally.

## Client fixes (this repo)

- `gui/ipc/w2p_handlers/skill_editor_cloud_relay.py` —
  `relay_get_sessions()` now returns `None` on failure instead of `[]`, so
  the handler distinguishes "cloud failed" (falls back to local sessions)
  from "no sessions". Previously it logged `Cloud get_sessions OK: 0
  sessions` right after a GraphQL error.
- `gui/ipc/w2p_handlers/skill_editor_chat_handler.py` — added
  `_local_llm_usable()` gate (reuses `needs_onboarding()` from `pick_llm`):
  when the cloud fails AND the local LLM has a placeholder/missing key, the
  chat returns a clean "⚠️ Chat service unavailable…" message instead of
  running the agent into a chain of 401s and the fake template.
  Limitation: a *wrong but non-placeholder* key still runs the agent.
- `gui/ipc/w2p_handlers/llm_display_stream.py` (new) + handler hookup —
  CN-only SSE display streaming moved server-side (desktop Python opens the
  `/v1/chat/completions` SSE stream on the `ecan-graphql-ws` 云托管 service,
  pushes deltas over the app WebSocket; the canonical GraphQL response
  supersedes them). Frontend `llmStream.ts` and the Chat-page SSE code were
  removed accordingly.

## Server fixes (TCB, separate repo)

- llm_proxy VPC/NAT timeout path fixed; `sendSkillEditorChatMessage` now
  returns structured responses (verified 22:13 run: HTTP 200, real reply
  after the final llm_proxy fix).
- `getSkillEditorChatSessions` was still 500ing as of 22:13 — tracked in
  OPEN_ITEMS.

## Verification ladder (useful for future triage)

| Run | Result | Meaning |
|---|---|---|
| 18:38 | GraphQL `INTERNAL_SERVER_ERROR` → fake template | cloud resolver broken + fallback broken |
| 21:42 | `No auth token` → fake template (recursive) | token expiry bug; request never left machine |
| 22:13 | 200 + `state=error` "llm_proxy returned no Skill Editor response", SSE connected but 0 deltas | handler fixed, llm_proxy empty upstream |
| later | working chat | llm_proxy fixed |

## Follow-up session (same evening): session-token death + invisible supervisor

**Symptom:** every run, ~10 min after WeChat login, the app logs out
("Session expired event received; triggering logout") and subsequent chat
attempts show `[se_cloud_relay] No auth token`.

**Root cause chain:**

1. `auth/session_supervisor.py` logged to `logging.getLogger("eCan.session_supervisor")`,
   but the app only attaches handlers to `eCan.cn`/`eCan.intl` (with
   `propagate=False`) — **every supervisor log line was silently discarded**,
   so its refresh attempts and failures were invisible. Fixed: it now uses
   `utils.logger_helper.logger_helper` like the rest of the app.
2. With visibility restored (by code reading + local-token forensics): the
   supervisor's proactive refresh (JWT remaining ≤ 300s) calls
   `refreshWeChatToken` with the 30-day session token, and the **server
   rejects it with SESSION_EXPIRED or WX_TOKEN_EXPIRED within ~10 minutes of
   `registerWeChatSession` minting it** (verified: local token deleted from
   both keyring `ecan_wechat_session` and `.wx_st_*` file — deletion only
   happens on those two codes; reproduced 3/3 runs: 22:45→~22:55,
   22:54→23:05, 23:25→23:35 local). The client then correctly signs out.
3. Also fixed: the deleting branch in `_attempt_wechat_session_token_refresh`
   never logged the server's error code/message. Now it does — the next
   occurrence will show exactly which code the server returns.

**Server-side handoff (TCB auth functions):**

- `registerWeChatSession` returns `expiresIn: 2592000` (30 days), but
  `refreshWeChatToken(input:{sessionToken})` (sent with
  `Authorization: Bearer <sessionToken>`) starts failing ~5–10 min later
  with SESSION_EXPIRED or WX_TOKEN_EXPIRED. Hypothesis: the server session
  row stores/depends on the short-lived CloudBase/WeChat access token
  instead of a durable secret, so the "30-day" session dies with the
  ~600s JWT. Check what registerWeChatSession persists and what
  refreshWeChatToken validates.
- `getSkillEditorChatSessions(userId: ID!)` still returns
  `INTERNAL_SERVER_ERROR "Unexpected error."` on every call (while
  createSkillEditorChatSession and sendSkillEditorChatMessage now work).
  Note the create input is only `{name, flowgramId}` — **no userId** — so
  session rows may lack user attribution; if the list resolver filters on a
  user column that is absent/null-typed in the Prisma model, that would
  500 exactly like this. Selected fields:
  `id name flowgramId createdAt updatedAt`.

## Triage lessons

- The fake workflow template is **always locally generated** — its presence
  means the cloud path failed *and* the local LLM is unconfigured. Grep for
  `se_cloud_relay` first to see whether the request even left the machine.
- "No llm_proxy invocation in server logs" does not imply wrong routing —
  check for `[se_cloud_relay] No auth token` (client never sent).
- The SSE display stream is an independent probe of llm_proxy health:
  connected-but-zero-deltas = llm_proxy upstream returning nothing.
