# Tmall / Qianniu (千牛) Customer-Service Chat — Design & Phase Plan

Branch: `tmall_ws` · Started 2026-08-11 · Status: **Phase 1 scaffold**

Goal: replicate the Feige real-time customer-service chat capability for
Tmall stores, operated through the **Qianniu Web workbench** (千牛网页版,
`work.taobao.com` / `myseller.taobao.com`), following the exact
platform/business split established by the 2026-08 Feige decoupling
(`docs/PLATFORM_FEIGE_DECOUPLING_2026_08.md`).

Non-negotiable rule inherited from that work: **the platform tree gains
ZERO case-insensitive "tmall"/"qianniu"/"taobao" business references.**
Everything Tmall-specific lives in
`agent/ec_skills/browser_use_extension/hooks/external/tmall_chat/` (plus,
later, `gui/ipc/w2p_handlers/tmall_*.py` if GUI handlers are needed).
Enforcement grep (mirror of the Feige one):

```bash
rg -c -i "tmall|qianniu" agent gui utils web_server.py main.py --no-ignore -g '*.py' -g '!__pycache__' \
  | rg -v 'hooks.external|w2p_handlers.tmall|platform_profiles|platform_detector|platform_config_mcp_tools|human_behavior|agent_config|prompts.py|cloud_agent'
# must print NOTHING new.  Site bundles under hooks/external/ are exempt
# (they are the business tree — feige_chat/__init__ may cite this doc);
# the other whitelisted files carry pre-existing incidental mentions (the
# speculative declarative profile + anti-detection timing comments) that
# predate this work and are not part of the live-chat path.
# Verified clean 2026-08-11 (agent/gui/utils/main.py/web_server.py).
```

---

## 1. Architecture decisions

### D1 — Site selection: env-gated single-active-site (bundle-side)

`live_chat_dispatch.register_runner_bridge()` and
`register_placeholder_handler()` are **last-write-wins, one per process**.
Auto-discovery imports every bundle under `hooks/external/`, so with two
site bundles present, whichever imports second would silently win.

Decision: a bundle registers **only when it is the active site**, decided
by the env var:

```
ECAN_LIVE_CHAT_SITE=feige_chat   # default when unset → existing behavior
ECAN_LIVE_CHAT_SITE=tmall_chat   # activates the Tmall bundle instead
```

- Read **inside each bundle's `__init__`** — the platform is untouched and
  never learns site names (the value happens to equal the bundle dir name).
- Default = `feige_chat`, so every existing run/test is bit-identical.
- An inactive bundle imports but registers nothing: no bridge, no
  controller tools, no hooks. Tool namespaces therefore never collide.
- Running BOTH sites in one process is explicitly out of scope for now; it
  requires generalizing the registry to key by site (and per-site
  `live_chat_env` resolution — see D4 caveat). Revisit only if a real
  deployment needs one process driving both workbenches.

### D2 — Phase 1 is DOM-first; the WS lane starts as capture-only

Feige's <300 ms path rests on a reverse-engineered WebSocket protocol
(`ws_reader.py` / `ws_sender.py`). Qianniu's wire protocol (accs/mtop —
Taobao's own stack, likely protobuf-in-binary frames like Frontier but a
completely different schema) is unknown until we capture real traffic.

So the Tmall bundle ships in the same order Feige itself evolved:

1. **Phase 1 (this scaffold):** DOM tools (`tmall_list_sessions` /
   `tmall_open_session` / `tmall_get_chat_thread` / `tmall_send_message`),
   generic DOM-mutation detection through the existing platform
   event-monitor, **plus a capture-only `ws_observer`** that logs every
   Qianniu WS frame to `runlogs/tmall_capture_*.jsonl` for offline
   protocol reverse-engineering (gated `ECAN_TMALL_WS_CAPTURE=1`).
2. **Phase 2:** decode inbound frames (`ws_reader` equivalent) → WS-path
   detection feeding the same normalized-item contract the DOM monitor
   emits (`event_monitor._ws_dispatch_fn` wiring is already site-neutral).
3. **Phase 3:** off-DOM send (`ws_session.frame_for` template-clone +
   eval-inject), typing-lock skip, hot-path ports — only what live latency
   numbers justify.

### D3 — Partial bridge is valid by design

The decoupling's guard-semantics invariant: every platform call site wraps
bridge use in `try/except` and falls back to its site-agnostic default
when the attribute is missing — exactly like a failed lazy import. The
`TmallRunnerBridge` therefore implements **only what Phase 1 supports**
(identity strings, DOM tab resolver, site adapter preset, tunables,
system-message filter, ws_observer capture stub, cdp-health passthroughs)
and deliberately omits the rest (`dispatch_state`, `placeholder_timer`,
`hot_path`, `ws_session`, `pre_dispatch_enrich`, ...). Missing attributes
raise `AttributeError` inside the platform's existing guards → same
fallback as "no bundle loaded". Features are added to the bridge one at a
time as their modules are ported.

### D4 — Env namespace: `ECAN_TMALL_*` / `DIRECT_TMALL_*`

Platform-side knobs keep their neutral `ECAN_LIVE_CHAT_*` /
`DIRECT_LIVE_CHAT_*` names — operators use those directly for platform
behavior. Bundle-side (site-branded) knobs use `ECAN_TMALL_*` spellings
resolved through the bundle's own `tunables.py` (per-node override →
`ECAN_<NAME>` env → default, same precedence as Feige).

Caveat carried from the decoupling doc: `live_chat_env()`'s legacy-alias
scan matches **any** `ECAN_<SITE>_X` spelling. Don't set `ECAN_FEIGE_X`
and `ECAN_TMALL_X` variants of the same platform knob simultaneously —
prefer the neutral `ECAN_LIVE_CHAT_X` name for platform knobs, always.

### D5 — Prompts

Generated 2026-08-10 in `customer_logs/` (same schema as the Feige ones):

- `prompt_pr-tmall-fd.json` — 天猫客服前台 (front-desk; mirrors `pr-198938`,
  tools renamed to `tmall_*`, 千牛 login-expiry wording, Qianniu system-row
  filter keywords, Taobao-register greetings)
- `prompt_pr-tmall-qa.json` — 天猫应答 (Q&A worker; mirrors `pr-278012`,
  identical output contract, `[商品卡片]` marker kept, Tmall service tags
  七天无理由/运费险, bargaining rule, 亲/您 tone)

Both keep the exact 3-field `bu_send_chat` / `send_chat` payload contracts
so the platform dispatch pipeline is unchanged.

---

## 2. Phase 1 bundle inventory

```
hooks/external/tmall_chat/
  __init__.py            # active-site gate + registrations (bridge, site tools)
  runner_bridge.py       # TmallRunnerBridge — partial surface (D3)
  dom.py                 # Qianniu tab resolver (URL markers, TTL cache)
  site_adapter_preset.py # sidebar/header selector preset (SPECULATIVE — calibrate)
  site_tools.py          # 4 controller actions (DOM path, placeholder selectors)
  typing_lock.py         # lean process-wide async send serialization
  tunables.py            # per-node → ECAN_<NAME> env → default resolution
  system_message_filter.py # Qianniu platform-row denylist (calibrate live)
  ws_observer.py         # CAPTURE-ONLY WS frame logger (Phase 2 feedstock)
  README.md              # bundle status + calibration playbook
```

`feige_chat/__init__.py` gains the same active-site gate (default active),
which is the only edit outside the new bundle.

## 3. Everything marked SPECULATIVE must be calibrated on the first live run

Qianniu selectors in `site_adapter_preset.py` / `site_tools.py` are
educated placeholders (partially informed by the old
`agent/ec_tasks/platform_profiles.json` "tmall" entry, itself unvalidated).
Calibration playbook on first login to the Qianniu Web workbench:

1. Open the seller IM page; run `tmall_list_sessions` — if `sessions=[]`
   with `total_visible=0`, use extract_dom on the left panel, pin the real
   row/name/preview/badge selectors into `site_tools.py` + preset.
2. Same for the thread pane (`tmall_get_chat_thread`) and compose area
   (`tmall_send_message`), mirroring how the Feige constants document their
   captured DOM (site_tools.py header comment).
3. Set `ECAN_TMALL_WS_CAPTURE=1`, chat from a buyer account, and collect
   `runlogs/tmall_capture_*.jsonl` for the Phase 2 protocol work.
4. Pin the real system-row texts into `system_message_filter.py` and the
   two prompt keyword lists (front-desk 预筛选 + tab wording).

## 4. Known Feige↔platform couplings that will bite Phase 2

- `event_monitor.py` / `browser_node/runner.py` still hard-code
  `im.jinritemai.com` (decoupling doc §6 leftover). Harmless while those
  code paths only run under the Feige site, but they must move behind
  `bridge.url_detector`/`bridge.dom` before the Tmall WS-detection lane
  goes live, so URL-keyed behavior follows the active bundle.
- Anti-bot posture: Qianniu's risk-control is stricter than Feige's.
  Phase 1 sends type through the DOM (native input events); the raw-WS
  send lane stays OFF until validated (same stance as
  `ECAN_FEIGE_WS_SEND_RAW`, default off).
