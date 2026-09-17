# Browser-Automation on AdsPower (CN) Post-Mortem

**Status: RUNNING** — the node drives real eBay Seller Hub pages, the model
reads them correctly, and it walks the prompt's priority queue on its own.
Client fixes in commit `488ce5ce5`, tag `v0.9.97w` (2026-09-16); the blocking
server fix is `llm_proxy 1243d05`. The CloudBase payload cap (§7) is solved by the
per-node action filter. Nothing that blocked this all day was ever the model.

A `browser_automation` node pointed at AdsPower failed six times in a row,
**exactly 30 seconds apart**, printing:

```
❌ Result failed 1/6 times:
```

Nothing after the colon. It looked like a model or credential problem. It was
neither, and the blank message was itself three separate bugs. What follows is
every layer we peeled, in the order they masked each other, plus the mistakes
made while diagnosing — those cost more time than the bugs.

Companion docs: `BROWSER_AUTOMATION_NODE_CONFIG.md` (node fields),
`CN_AUTH_SCHEME.md` (identity),
`CN_LLM_PROXY_ACCOUNT_PROVISIONING_MILESTONE_2026_08_30.md`.

---

## 1. The layers

| # | Layer | Mechanism | Proof |
|---|-------|-----------|-------|
| 1 | **Empty error message** | Three independent causes (§2) hid every real error behind a blank line. Fixing this FIRST is what made everything below findable. | 5 runs, zero usable output |
| 2 | **Screenshot, not DOM** | `_prepare_context` hardcodes `include_screenshot=True`; `ScreenshotWatchdog` wedges on an anti-detect browser and burns the whole 30s `BrowserStateRequestEvent` budget, *before* any model call. The DOM itself took 28ms. | `BSTATE-TRACE ok elapsed=30.0s` with `SNAPSHOT` at +28ms |
| 3 | **Settings file was write-only** | `browser_use_settings.json` had no runtime reader at all, so no timeout in it could ever take effect. | `get_agent_settings()` had zero callers |
| 4 | **Model catalogue emptied the model** | eCanAI ships `supported_models: []` by design; validating against it rejected every model and fell back to a default that is also empty. | node model silently became `''` |
| 5 | **403 `user_not_registered`** | **Server-side.** `verifyEcanSessionToken` returned `String(claims.sub).toLowerCase()`; the WeChat openid is mixed-case and the account lookup is case-sensitive → 0 rows. | `rows_for_lowered=0`, `rows_for_exact=1` |
| 6 | **402 `insufficient_balance`** | Account out of funds. Not a bug. | HTTP 402 |
| 7 | **413 `EXCEED_MAX_PAYLOAD_SIZE`** | CloudBase gateway caps the request body at ~100KB. The bulk is NOT the page — it is the **action schema**: 57 registered tools serialize to 66.4KB on every step. | `output_schema=66.4KB messages=40.7KB`; filtered to 10 actions → 6.8KB, 413 gone |

---

## 2. Why the error was blank — three causes, all worth knowing

1. **bubus raises `TimeoutError` with an empty `str()`**, and browser-use reports
   failures as `f'❌ Result failed {n}/{max} times: {str(error)}'`. Empty string →
   blank line. It appends a stacktrace only when its *dynamically named* logger
   (`browser_use.Agent🅰 ...`) is DEBUG-enabled, which ours never is.
2. **`ChatLambdaProxy` used `logging.getLogger(__name__)`** — outside the
   `eCan`/`eCan.cn` tree the file handler binds to. A full run produced exactly
   **one** matching log line. Every diagnostic we added was written to nothing.
   Now `from utils.logger_helper import logger_helper as logger`, like its siblings.
3. **`except httpx.TimeoutError`** — httpx has no such attribute (it is
   `TimeoutException`). Evaluating a missing attribute in an `except` clause raises
   `AttributeError` **at handling time**, which replaced the real error and skipped
   every handler below it, including the retry.

**Lesson:** when an error message is empty, that is the bug to fix first. Do not
theorise about the failure until it can describe itself.

---

## 3. The screenshot (the 30 seconds)

`browser_use/agent/service.py:1073`:

```python
browser_state_summary = await self.browser_session.get_browser_state_summary(
    include_screenshot=True,  # always capture even if use_vision=False so that
                              # cloud sync is useful (it's fast now anyway)
)
```

It is not fast on AdsPower. `BrowserStateRequestEvent.event_timeout` defaults to
**30.0s** (`browser_use/browser/events.py`), and this runs inside `Agent.step()`
*before* `_get_next_action()` — so the step fails before the model is ever
contacted, which is why no LLM call appeared in any log.

**Fix** — `runner.py::_trace_browser_state` drops the screenshot when the node has
`use_vision=False`. Measured 30.0s → 0.0s; ~7.5 min saved on a 15-step run.

Two non-obvious details:

- **Patch the CLASS, not the instance.** `BrowserSession` is a pydantic model with
  `extra='forbid'` and `validate_assignment=True`; assigning the wrapper onto the
  object raises instead of taking effect (and the `except` would only log a warning
  nobody reads). Class-patching also covers sessions browser-use builds itself.
- **Re-read the vision flag per call** (`_vision_box`). A cached session reused by a
  different node must not inherit the first node's setting.

---

## 4. Making `browser_use_settings.json` real

`agentSettings` / `browserSessionSettings` were written by the Settings page and
read by **nobody** — `get_agent_settings()` and `get_browser_session_settings()`
had zero callers outside their own module. Confirmed by repo-wide grep: the only
other references anywhere are the two IPC calls in `gui_v2/src/services/ipc/api.ts`.

`apply_browser_use_event_timeouts()` now exports `agentSettings.eventTimeouts` as
browser-use's `TIMEOUT_<EventName>` variables. This works only because
`_get_timeout` calls `os.getenv` **inside the event's `default_factory`**, i.e. per
instance — so setting the variable before a run is enough.

**Budget: 45s.** Not higher. A healthy state build is ~0.05s once the screenshot is
dropped, so 45s is pure headroom for a slow page; raising it only lengthens the
*deadlock* case (§6), which never completes at all.

> `browserSessionSettings` is still unread by the runtime. If those knobs are meant
> to reach browser-use, that is an open item.

---

## 5. Identity: four names for one user

| form | value | where it is correct |
|---|---|---|
| `mainwin.user` | `wechat_<openid>@local` | LOCAL DB owner |
| `identity.sub` / `accounts.subid` | `<openid>` (mixed case!) | the cloud |
| `user_email` | `wechat_<hash>@wechat.local` | — a different hash entirely |
| `accounts.user_name` | `wechat_<hash>` | — |

`_get_proxy_config` sent the LOCAL form as `X-User-Id`. `normalize_cloud_owner`
(which already strips both `wechat_` and `@local`) now runs there too, via
`build_node::_normalize_proxy_user` — one chokepoint covering all four
`ChatLambdaProxy` sites plus the LangChain proxy.

**This was NOT the cause of the 403.** Probing proved the header is not consulted
at all — identical 403 for the openid, the `user_name`, the legacy prefixed form,
and with the header omitted entirely; only removing the *bearer* changed the error
(to 401). Keep the normalization for metering attribution; do not credit it with
the fix.

### Audited and found CORRECT — do not "fix" these

A live round-trip (`queryAgents(input: {})`, which returns the stored `owner`)
showed all 5 agents owned by the **bare openid** even though the client writes the
local form: **the server derives owner from `identity.sub` and discards the
client's value.** So these are harmless and must be left alone:

- `agent/ec_agents/agent_utils.py` — 9 sites setting `owner = mainwin.user` on
  cloud-bound dicts (`_agent_to_dict`, `_skill_to_dict`, `_task_to_dict`,
  `_tool_to_dict`, `prep_knowledges_data_for_cloud`).
- `skill_editor_chat_handler.py:1334`, `fast_deploy_handler.py:46` — local DB.
- `server.py` `log_user` — filesystem paths.

Still genuinely suspect (filter *arguments* are applied literally, unlike owner
fields): `appsync_subscription_client.py:1347` → `{"sessionId": self._owner}` and
`{"owner": self._owner}`. Unverified.

---

## 6. Account provisioning and the browser session

- **`ensure_account` skipped WeChat.** The guard read
  `if login_type in ("password", "phone")`, on the assumption that WeChat rows came
  from the PHP-callback path. A signed-in WeChat user proved otherwise. It now runs
  for every login type — and **on session restore**, because like the HTTP
  session-token mint before it, it only ran in the login-finalize path, so a user
  signed in across restarts never retried.
- Its log printed raw account JSON (`email`, `dob`, `phone`) while truncating away
  `subs`, the one field that decides authorization. Now logs
  `success/actid/subid/subs` and nothing else.
- **A failed `browser_session.start()` used to limp on.** It timed out (20s), the
  retry failed, and the code logged `"Browser session started!"` anyway. The session
  is then half-wired: targets exist so the focus preflight looks healthy, but every
  `get_browser_state_summary` deadlocks. Observed cost: 4½ minutes and an empty
  error. `build_helpers.py` now **aborts** with the browser type and port named.

---

## 7. The payload cap — and why the obvious lever was the wrong one

```
structured=True  → payload=107.2KB → 413      structured=False → 0.6KB → OK
structured=True  → payload=107.5KB → 413      structured=False → 0.9KB → OK
```

Perfectly bimodal across every call. The 413 comes from **CloudBase's gateway,
not `llm_proxy`** — note the `docs.cloudbase.net` link and `requestId` in the
body. The cap is ~100KB.

### The wrong turn, recorded on purpose

The obvious reading is "the page is too big, trim the DOM". That is what we did:
set the node's `domLimit` from its ~25000 default to 8000. It applied correctly
(`DOM limit set to 8000 chars`, `max_clickable=8000`, plumbed through
`Agent.__init__:206 → 412 → 518`) and the payload came back **107.2KB — not one
byte different**. The clickable-element text was already under 8000; the DOM was
never the bulk.

Only then did we measure instead of reason:

```
[ChatLambdaProxy] payload split: output_schema=66.4KB messages=40.7KB
[ChatLambdaProxy] payload breakdown: [0]system=21.6KB [1]user=17.7KB
```

**62% of the body is the action schema.** Every registered tool is serialized
into `output_schema` on EVERY step — 57 actions at roughly 1.2KB each. The page
itself was 17.7KB. Even a perfect DOM could not have fitted: schema + system
prompt alone is 88KB.

### The fix: a per-node action filter

Node fields `allowedActions` / `excludedActions` (comma-separated) restrict what
the node exposes to the model. For the eBay node:

```
allowed:  navigate click input extract scroll wait go_back find_text switch done
excluded: screenshot
result:   57 -> 10 actions,  schema 66.2KB -> 6.8KB,  body ~107KB -> ~48KB
```

413 gone; the agent now runs the task.

Implementation notes that are easy to get wrong:

- **`_FilteredTools` is a delegating view, NOT a copy.** `copy.copy` on the
  Controller raises `RecursionError` — and because the helper caught it and
  returned the original, the first version filtered nothing while appearing to
  work. Check the kept COUNT, not just the absence of an error.
- **Never mutate the shared controller.** `custom_controller` is a module-level
  singleton and `Registry.exclude_action()` deletes permanently, so one node's
  filter would strip tools from every other node for the rest of the process.
  Assert the global is untouched after filtering.
- **`done` is force-kept** — the Agent builds its terminal model with
  `create_action_model(include_actions=['done'])` and cannot finish without it.
- **`None` != `[]`.** An unset field must mean "no filter", never "allow
  nothing".
- **browser-use excludes `screenshot` itself when vision is off**
  (`agent/service.py:313`) — but only when IT constructs `Tools`. We pass our own
  controller, so that never applied and our `screenshot` action was in every
  schema until this filter.
- Defaulted dataclass fields must go at the END of `RunContext`, or class
  creation raises `non-default argument ... follows default argument`.

`domLimit` was reverted to unset: it bought nothing and would only truncate a
denser page for no reason now that the schema fix freed ~59KB.

---

## 8. Traps that cost the most time

1. **There are TWO skill JSONs. The loader reads the `_bundle` one.**
   `my_skills/<skill>/diagram_dir/<skill>_skill_bundle.json` is authoritative —
   confirmed by `[SKILL_IO][BACKEND][READ_OK]` in the log. Editing
   `<skill>_skill.json` changes nothing. They also have **different shapes**: bundle
   nodes live at `sheets[0].document.nodes`, the other at `workFlow.nodes`. Always
   confirm the edit landed by looking for the setting in the next run's
   `Performance settings:` line.
2. **`dist/` holds a stale copy of the source.** `dist/eCan.cn/_internal/...` shadows
   real files in repo-wide greps and is often many commits behind. Filter it out,
   and make sure you are launching from source rather than the built app.
3. **`my_skills/generated*_skill/` contain recursive copies of the whole `gui_v2`
   tree** (`.../generated0_skill/my_skills/generated0_skill/...`). They make
   repo-wide greps time out. Scope searches to `agent/ gui/ auth/ utils/`.
4. **Handlers are loaded once via `pkgutil`.** A handler added to an
   already-imported module is not registered until the app restarts.
5. **The local IPC server is not on port 5000.** Find it with
   `netstat -ano | grep <pid>` and probe `/healthz`; it was **4668**. Handlers are
   invoked by POSTing to `/graphql` with `{"extensions":{"method":"<name>"}}`.
6. **`ECAN_APP_ID=cn` must be set** for a standalone script, or `is_cn_app()` is
   false and you silently probe the **AWS** endpoint. The tell: logger name `eCan`
   instead of `eCan.cn`.

---

## 9. What actually worked as technique

- **Read the library source instead of re-running.** The 30s constant was found by
  reading `browser_use/browser/events.py`, not by another failing run.
- **Out-of-process probes beat guessing.** Four variants of `X-User-Id` against the
  live proxy proved in one shot that the header was irrelevant — and that the bearer
  *was* being read (removing it changed the error to 401). That is what redirected
  the hunt to the server.
- **Ask the cloud what it stored.** `queryAgents` returns `owner`; one read-only call
  retired a 9-site "bug" that would have been 9 pointless edits.
- **Log the number, not a proxy for the number.** `messages=2` said nothing;
  `payload=107.2KB` next to a ~100KB cap said everything. `ChatLambdaProxy` now
  always logs body size, and splits it into `output_schema` vs `messages` (with a
  per-message and per-action breakdown) once it exceeds 64KB.
- **Measure before turning a knob, not after.** The DOM cap (§7) was a plausible
  hypothesis reasoned from a plausible premise, and it cost a full run to
  discover that the premise was wrong by 62%. One breakdown log would have
  pointed at the schema immediately. "This is obviously the big thing" is a
  hypothesis, not a measurement.
- **A caught exception can make a fix look applied when it did nothing.** Both
  the action filter (`RecursionError`) and the DOM cap failed silently-ish in
  exactly this way. Verify the OUTCOME (kept count, payload size), never the
  absence of an error.

---

## 10. Open items

- [ ] **Terminal proxy errors should stop the agent loop.** `insufficient_balance`
      (402) and `EXCEED_MAX_PAYLOAD_SIZE` (413) cannot change mid-run, yet
      browser-use retried each 5–6 times — 12 real HTTP round-trips for one
      unchanging answer. `proxy_errors.py` already documents "callers must not
      retry"; `ChatLambdaProxy` honours it, the agent loop does not.
- [ ] **`browserSessionSettings` still unread** by the runtime (§4).
- [ ] **`SkillUpdateInput` lacks `need_inputs`** — every skill sync fails with
      `Field "need_inputs" is not defined by type "SkillUpdateInput"`. Server SDL.
- [ ] **`TaskSkillRelation.owner` required** by the SDL but derived from identity
      everywhere else — `addAgentTaskSkillRels` fails on every run.
- [ ] **`agentSkill.create` unique-constraint on `id`** on repeat sync.
- [ ] `appsync_subscription_client.py` owner filter (§5) unverified.
- [x] ~~Raise or compress past the CloudBase ~100KB body cap~~ — solved by the
      per-node action filter (§7); body ~107KB → ~48KB. The cap itself still
      stands, so a node that genuinely needs many tools will hit it again.
- [ ] **Roll the action filter out to other browser nodes.** Only the eBay node
      sets `allowedActions` today; every other node still ships all 57 actions
      (~66KB per step) and pays for it in both payload and tokens.
- [ ] **Expose `allowedActions` / `excludedActions` in the node editor.** They
      are read by both normalizers but have no GUI field yet, so they can only be
      set by editing the skill bundle JSON.
- [ ] **Stale element index loops.** First real-task run: the agent clicked the
      same index (6561) three steps running while observing "did not navigate",
      and would have burned all 15 steps. Prompt-level fix (prefer `navigate` to
      a known URL over clicking nav links) plus possibly a repeat-action guard.
