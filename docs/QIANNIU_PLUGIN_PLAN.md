# 千牛 (Taobao/Tmall) Customer-Service Agent — Plugin Plan

Branch: `qianniu` (off `origin/master`). Companion to
`eCan.ai/customer_logs/tools/qianniu_review/QIANNIU_CS_AGENT_FEASIBILITY.md`
(the proven receive/attribute/send loop) and
`docs/PLATFORM_FEIGE_DECOUPLING_2026_08.md` (the platform/business seam this
plan obeys).

**Status: design settled, not yet built.** Receive path decided (see §4).

---

## 1. Why 千牛 is not "another pdd_chat"

The feige/pdd bundles assume a **browser substrate** — CDP tabs, page DOM, a
page WebSocket, an injected `BrowserSession`. 千牛 (`AliWorkbench.exe`) is a
**native Win32 client** with CEF DevTools locked: no CDP, no DOM, no page WS to
hook. Its proven primitives (feasibility doc) are:

- **receive** = read `AliWorkbench.exe` process memory (sender-anchored scan)
- **select** = OCR + window-foreground + mouse/keyboard
- **send**   = clipboard + `Ctrl+V` + `Enter` (foreground fix first)

The repo already ships the native-desktop pattern 千牛 needs:
`agent/mcp/server/wechat/` drives WeChat (a native Win32 client) via
window-focus + screenshot + local OCR + pyautogui + clipboard — **no browser**.
The RPA-skill precedent is `agent/ec_skills/ecbot_rpa/ecbot_rpa_chatter_skill.py`
(generic `pend_event → llm → chat → mcp` graph, no browser node).

So 千牛 fuses two existing patterns along a clean seam: **wechat-style native
driver** for transport, **feige/pdd-style front-desk machinery** for the agent
loop.

---

## 2. Platform vs. business split (the governing rule)

Same rule as the feige decoupling: **generic mechanism stays platform-side; all
site-specifics live in the bundle.** A future WeChat-CS / DingTalk desktop site
must plug in without touching platform code.

### PLATFORM — business-agnostic, reuse as-is

| Capability | Location | Note |
|---|---|---|
| Window focus / enumerate | `agent/mcp/server/wechat/platform_utils.py` → `find_windows_by_title`, `bring_window_to_front` | cross-platform; untouched |
| Clipboard (text/file) + paste | same file → `clipboard_set_text`, `clipboard_set_file`, `paste_hotkey` | untouched |
| Screenshot per window/region | `agent/ec_skills/ocr/image_prep.py` → `captureScreen`, `_apply_window_offset` | untouched |
| Local OCR | `agent/mcp/server/local_ocr/paddle_ocr.py` → `run_ocr_on_image` | RapidOCR/onnx, offline; untouched |
| Capture→OCR→abs-coords recipe | `agent/mcp/server/wechat/wechat_tools.py::_do_ocr_local` | copy verbatim |
| Dispatch door (inbound) | `event_monitor._dispatch_to_runners` → `runner.sync_task_wait_in_line("chat_message", item)` (`runner.py:4161`) | **confirmed browser-agnostic**; `session` is opaque metadata |
| Site registry | `agent/ec_skills/live_chat_dispatch.py` → `register_runner_bridge`, `ECAN_LIVE_CHAT_SITE`, `live_chat_env` | already anticipates non-browser sites |
| Skill graph builders | `agent/ec_skills/build_node.py` (`build_pend_event_node`/`build_llm_node`/`build_chat_node`/`build_mcp_tool_calling_node`) | no `BrowserSession` created |

**Two small generic additions (not 千牛-branded):**

1. **Window-alias entry** in `image_prep.get_top_visible_window` `_WIN_ALIASES`:
   add `"千牛"/"AliWorkbench"/"阿里旺旺"` (table already holds dingtalk/feishu).
2. **Desktop observer trigger.** The browser path starts its observer from
   `event_monitor` DOM-mutation on URL patterns — a desktop site has no URL. Add
   a neutral "start the registered native observer when the node runs and the
   target window is present," started from the bundle's `register()` under
   `ECAN_LIVE_CHAT_SITE`. Keep the trigger generic; the observer itself is
   bundle code.
3. **Read-only process-memory scanner** (new platform primitive — see §4). The
   *mechanism* (`OpenProcess`/`VirtualQueryEx`/`ReadProcessMemory` region walk,
   read-only, identity-verified) is business-agnostic → platform. The
   *locator/schema* is 千牛-specific → bundle. None exists today; the house
   style is screenshot+OCR, so this is net-new and Windows-only.

### BUSINESS — the 千牛 bundle, platform never imports it

| File | Role |
|---|---|
| `agent/mcp/server/qianniu/qianniu_tools.py` | Desktop driver (cloned from `wechat_tools.py`): `qianniu_list_sessions` / `qianniu_open_session` / `qianniu_get_chat_thread` / `qianniu_send_message`. Registered in `server.py` (~4115) + `tool_schemas.py`. |
| `hooks/external/qianniu_chat/runner_bridge.py` | What the platform reads. Advertises `qianniu_*` tool names; declares **no** browser capabilities (missing attrs degrade to generic behaviour). |
| `hooks/external/qianniu_chat/observer.py` | Continuous memory reader → builds the pdd-shape `item` dict → injects via the platform dispatch door. |
| `hooks/external/qianniu_chat/mem_locator.py` | 千牛 sender-anchored scan + message-object schema + noise filter (doc §4.1–4.3). |
| `hooks/external/qianniu_chat/select_verify.py` | OCR the chat-header name region, require == target display name, else ABORT (doc §5, fail-closed). `sender_id ↔ display_name` learning. |
| `hooks/external/qianniu_chat/{system_message_filter,typing_lock,site_adapter_preset}.py` | Supporting parts (mirror pdd). |
| `hooks/external/qianniu_chat/hook.yaml` | Manifest + meters `cs_chat / message_replied` (same as pdd). |
| `hooks/external/qianniu_chat/__init__.py` | `register()` gated on `live_chat_dispatch.site_enabled("qianniu_chat")` (mirror pdd). |
| Skill graph | Modeled on `ecbot_rpa_chatter_skill.py`: `pend_event → llm/chat → mcp(qianniu_send)`. No browser node. |

---

## 3. The reused contracts (exact seams)

**Inbound `item` dict** (from `pdd_chat/ws_observer.py::_State.item_for`) — the
memory observer builds the identical shape:
`customer_name`(=buyer sender-id), `name`, `session_id`, `customer_id`,
`talk_id`, `customer_display_name`, `last_message`, `latest_message`, `msg_id`,
`latest_message_msg_id`, `identity_key`(=`f"{uid}|{msgid}"`), `unread_badge`,
`source`(=`"qianniu_mem"`), `message_kind`, optional `last_message_attachments`.

**Outbound tools** — the agent calls `qianniu_*` by the names the runner bridge
advertises (`send_message_tool_name` etc.), exactly as pdd advertises `pdd_*`.
Unlike pdd these take **no** `browser_session`; they drive the desktop via
platform_utils + captureScreen + run_ocr_on_image + pyautogui.

---

## 4. Receive path — DECIDED: hybrid (feasibility doc §5)

- **Receive + attribution:** read-only process-memory scan, sender-anchored
  (doc §4.1–4.3). Chosen because OCR misses very short replies (proven v3) and
  sender-id attribution (no cross-talk, catches hidden conversations) is not
  recoverable from pixels.
- **Select-verify before every send:** OCR the chat-header name, require it ==
  the target buyer's known display name, else abort. Closes the gap memory
  could not (v15: active conversation not in memory).
- **Send:** foreground-fix → clipboard → `Ctrl+V` → `Enter` (doc §4.4).

Cost accepted: a new read-only process-memory primitive (platform) + 千牛
locator/schema (bundle). **No injection, no 风控 bypass** (doc §6 stays off the
table).

---

## 5. Phased build — ALL BUILT (0–3)

Code-complete and headless-tested. The three live-client calibration/measurement
items are listed under §6; everything else is implemented and committed.

**Phase 0 — primitives (DONE).** Window alias; cloned `_do_ocr_local`; read-only
memory scanner (`utils/win_process_memory.py`) + sender-anchored locator
(`mem_locator.py`); `verify_header_name`; `_phase0_spike.py`. Tested: carving,
two-buyer attribution, noise filter.

**Phase 1 — co-pilot (DONE).** `qianniu_send`/`qianniu_receive` MCP tools;
`observer.py` injecting the pdd-shape item via `_dispatch_to_runners`
(`session=None`); `runner_bridge.py`; `hook.yaml`; gated `register()`. Tested:
fail-closed send guard, item shape, dedup, bridge registration, gated-off
inertness.

**Phase 2 — hands-off selection (DONE).** `qianniu_open_session` + `qianniu_send`
auto-open (search-by-name → OCR header verify, fail-closed); `name_map.py`
persistent learned map; observer content-join learning. Tested: auto-open send,
open-fail fail-closed, learning pass, name-map roundtrip, search-box OCR anchor.

**Phase 3 — hardening + gate (DONE).** Humanized pacing (`_humanize`), layout-drift
guard (`_looks_like_qianniu`), typing-lock serialization across open+send,
re-verify before each send; `_phase3_gate.py` reliability harness. Tested: gate
recorder (wrong-recipient + duplicate detection). *Running the gate on ≥100 live
messages is the operator's step.*

---

## 6. Live-client calibration / measurement (the only remaining work)

- **Memory field name** — content field is client-hashed (§4.2). `mem_locator.
  _best_text_field` takes the longest chat-like string; pin the real field from
  a `_phase0_spike.py` capture.
- **OCR geometry / window title** — `qianniu_ocr._HEADER_BAND_FRAC` (0.12),
  `qianniu_tools._SEARCH_ANCHORS`, and the window-title string (`千牛` vs
  `千牛工作台`/`AliWorkbench`).
- **Reliability gate** — run `_phase3_gate.py` over ≥100 controlled messages;
  require zero wrong-recipient sends before any unattended use.
- **Observer lifecycle** — currently started from `register()` on a background
  thread; revisit if/when a second desktop site ships (the generic desktop
  observer trigger in §2).
