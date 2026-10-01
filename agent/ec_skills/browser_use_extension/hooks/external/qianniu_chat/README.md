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

**Phase 0 (current) — de-risk primitives only.**

| file | role | phase |
|---|---|---|
| `mem_locator.py` | 千牛 sender-anchored scan + noise filter + seller/buyer attribution (over the platform scanner `utils/win_process_memory.py`) | 0 |
| `_phase0_spike.py` | standalone READ-ONLY runner: proves memory receive+attribution and OCR header-verify on a live client | 0 |
| `../../../../../mcp/server/qianniu/qianniu_ocr.py` | capture+OCR the 千牛 window; `verify_header_name` select-verify guard | 0 |
| `__init__.py` | gated `register()` — a no-op until Phase 1 | 0 |
| `runner_bridge.py` | advertises `qianniu_*` tool names; no browser capabilities | 1 (TODO) |
| `observer.py` | memory reader → pdd-shape `item` dict → platform dispatch door | 1 (TODO) |
| `qianniu_tools.py` (in `mcp/server/qianniu/`) | `qianniu_list/open/get/send` MCP tools | 1 (TODO) |
| `hook.yaml` | manifest + `cs_chat/message_replied` meter | 1 (TODO) |

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
