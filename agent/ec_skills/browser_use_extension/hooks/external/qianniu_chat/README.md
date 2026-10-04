# qianniu_chat — 千牛 (Taobao/Tmall) native-desktop customer chat

Site bundle for the 千牛 (AliWorkbench) seller desktop client. Unlike
`feige_chat` / `pdd_chat` (browser/CDP/WebSocket), 千牛 is a **native Win32
client** with CEF DevTools locked, so it is driven the `agent/mcp/server/wechat/`
way: read-only process-memory receive + OCR select-verify + clipboard/Enter
send. Full plan: `docs/QIANNIU_PLUGIN_PLAN.md`. Feasibility evidence:
`eCan.ai/customer_logs/tools/qianniu_review/QIANNIU_CS_AGENT_FEASIBILITY.md`.

## Switching it on

Registers only when the process is told to serve 千牛:

    ECAN_LIVE_CHAT_SITE=qianniu_chat

Unset (every existing install), the bundle does nothing.

## Build status

**All phases built (0–3).** Code-complete and headless-tested; the memory
field name, OCR geometry, and the reliability gate still need calibration /
measurement on a live client (see "Needs a live client" below).

| file | role | phase |
|---|---|---|
| `mem_locator.py` | 千牛 sender-anchored scan + noise filter + seller/buyer attribution (over the platform scanner `utils/win_process_memory.py`) | 0 |
| `../../../../../mcp/server/qianniu/qianniu_ocr.py` | capture+OCR the window; `verify_header_name` guard; `read_header_name` + `transcript_contains` (learning join) | 0,2 |
| `_phase0_spike.py` | standalone READ-ONLY runner: proves memory receive+attribution and OCR header-verify | 0 |
| `observer.py` | background memory reader → pdd-shape `item` → platform dispatch door (`_dispatch_to_runners`, `session=None`); throttled display-name learning | 1,2 |
| `runner_bridge.py` | site registration + typing lock; **no** browser capabilities | 1 |
| `typing_lock.py` | single-slot desktop send lock (serializes all desktop action) | 1 |
| `../../../../../mcp/server/qianniu/qianniu_tools.py` | `qianniu_send` (auto-open + header-verified), `qianniu_open_session`, `qianniu_receive` | 1,2 |
| `name_map.py` | persistent learned `sender_id ↔ display_name` map | 2 |
| `hook.yaml` | manifest + `cs_chat/message_replied` meter | 1 |
| `__init__.py` | gated `register()` → bridge + observer | 1 |
| `_phase3_gate.py` | reliability-gate harness: observe/reply, reports wrong-recipient sends / dups / latency | 3 |

## Wiring

- `ECAN_LIVE_CHAT_SITE=qianniu_chat` — activates the bundle (bridge + observer).
- Skill graph: `pend_event` (waits for the injected `chat_message`/`browser_event`)
  → `llm`/`chat` (drafts the reply) → `mcp` calling `qianniu_send` with the
  buyer display name + draft. Modeled on `ecbot_rpa_chatter_skill.py`.
- **Hands-off send:** `qianniu_send` searches for and opens the buyer's chat when
  it isn't already open (`auto_open`, default on), then sends ONLY after an OCR
  header verify confirms the open chat is that buyer — fail-closed.
- **Learning:** the observer joins a memory sender id to a screen display name by
  content (the message text visible in the open conversation), building
  `name_map` so auto-open has a name to search for.

### Env knobs

| var | default | effect |
|---|---|---|
| `ECAN_LIVE_CHAT_SITE` | unset | must name `qianniu_chat` to activate the bundle |
| `ECAN_QIANNIU_OBSERVER` | `1` | memory observer on/off |
| `ECAN_QIANNIU_POLL_S` | `3` | observer scan interval (s) |
| `ECAN_QIANNIU_LEARN` | `1` | display-name learning on/off |
| `ECAN_QIANNIU_NO_JITTER` | unset | `1` disables humanized send pacing (tests) |
| `ECAN_QIANNIU_TYPING_LOCK_TTL_S` | `30` | dead-holder lock takeover TTL |

## Needs a live client (not covered by headless tests)

1. **Memory field name** — `mem_locator._best_text_field` takes the longest
   chat-like string; pin the real client-hashed body field from `_phase0_spike`.
2. **OCR geometry / window title** — `qianniu_ocr._HEADER_BAND_FRAC` (0.12),
   `qianniu_tools._SEARCH_ANCHORS`, and the window title string.
3. **Reliability gate** — run `_phase3_gate.py` on a controlled ≥100-message
   scenario; require zero wrong-recipient sends before any unattended use.

## Running the Phase-0 spike

On the seller's Windows machine with 千牛 open and a conversation loaded:

    python -m agent.ec_skills.browser_use_extension.hooks.external.qianniu_chat._phase0_spike --verify-header "买家昵称"

Expected: the memory leg prints sender-attributed candidates (seller id
separated from buyer id); the OCR leg prints whether the chat header matches the
given display name. Both are read-only.

## Known calibration point (plan §6)

The 千牛 message object's body field name is client-hashed (study §4.2);
`mem_locator._best_text_field` currently takes the longest chat-like string.
Pin the real field name from a live capture before Phase 1.
