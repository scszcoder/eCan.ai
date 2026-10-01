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

**Phase 1 (current) — co-pilot: agent reads + drafts, human-supervised send.**

| file | role | phase |
|---|---|---|
| `mem_locator.py` | 千牛 sender-anchored scan + noise filter + seller/buyer attribution (over the platform scanner `utils/win_process_memory.py`) | 0 |
| `_phase0_spike.py` | standalone READ-ONLY runner: proves memory receive+attribution and OCR header-verify on a live client | 0 |
| `../../../../../mcp/server/qianniu/qianniu_ocr.py` | capture+OCR the 千牛 window; `verify_header_name` select-verify guard | 0 |
| `observer.py` | background memory reader → pdd-shape `item` dict → platform dispatch door (`_dispatch_to_runners`, `session=None`) | 1 |
| `runner_bridge.py` | site registration + typing lock; **no** browser capabilities (missing attrs → generic fallback) | 1 |
| `typing_lock.py` | single-slot desktop send lock | 1 |
| `../../../../../mcp/server/qianniu/qianniu_tools.py` | `qianniu_send` (header-verified) + `qianniu_receive` MCP tools; registered in `server.py` + `tool_schemas.py` | 1 |
| `hook.yaml` | manifest + `cs_chat/message_replied` meter | 1 |
| `__init__.py` | gated `register()` → bridge + observer | 1 |
| OCR conversation auto-select (click sidebar / search-by-name) | hands-off recipient switching | 2 (TODO) |
| reliability gate (≥100 msgs, humanized pacing, recovery) | before unattended use | 3 (TODO) |

## Wiring (co-pilot)

- `ECAN_LIVE_CHAT_SITE=qianniu_chat` — activates the bundle (bridge + observer).
- Observer gate `ECAN_QIANNIU_OBSERVER` (default on), poll `ECAN_QIANNIU_POLL_S`
  (default 3s).
- Skill graph: `pend_event` (waits for the injected `chat_message`/`browser_event`)
  → `llm`/`chat` (drafts the reply) → `mcp` calling `qianniu_send` with the
  buyer display name + draft. Modeled on `ecbot_rpa_chatter_skill.py`.
- `qianniu_send` refuses unless the open conversation's OCR'd header matches the
  named buyer — in co-pilot, a human keeps the right chat open; Phase 2 adds the
  automatic open+verify.

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
