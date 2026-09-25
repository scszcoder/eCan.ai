# pdd_chat — Pinduoduo (拼多多) merchant customer chat

Site bundle for mms.pinduoduo.com/chat-merchant/, built the Feige way:
customer messages are read off the page's WebSocket, replies go through the
page. Wire notes: git-ignored `WS_PDD_PROTOCOL_SPEC.md` at the repo root.

## Switching it on

Registers only when the process is told to serve Pinduoduo:

    ECAN_LIVE_CHAT_SITE=pdd_chat

Unset (every existing install), the bundle does nothing and Feige behaves
exactly as before. Why a switch: with two live-chat bridges registered, calls
made outside a node run (direct reply delivery, chat tools) cannot tell which
platform they belong to; `ECAN_LIVE_CHAT_SITE` names the one this process
serves (`live_chat_dispatch.configured_sites()`). One live-chat platform per
process for now; per-store processes are the path to both on one machine.

## Pieces

| file | role |
|---|---|
| `ws_protocol.py` | decode a titan frame (gzip JSON) into normalized chat events |
| `ws_observer.py` | attach to the chat tab, dispatch each buyer message to the front desk; cold-start pass over conversations already waiting |
| `dom.py` | list conversations, open one, read the thread, type + click Send; chat-tab resolver |
| `site_tools.py` | `pdd_list_sessions`, `pdd_open_session`, `pdd_get_chat_thread`, `pdd_send_message` controller actions |
| `runner_bridge.py` | what the platform reads (`live_chat_dispatch.runner_bridge()`) |
| `typing_lock.py`, `hot_path_v2.py`, `ws_session.py`, `system_message_filter.py`, `site_adapter_preset.py` | the bridge's supporting parts |
| `site.py` | preset for the traffic probe (Settings → 指纹浏览器配置 → Record traffic, or `pdd_probe.exe`) |

## Identity: the buyer uid

Nicknames are masked (`S*******n`, `X*K`) and collide, so every item and tool
keys a conversation by the buyer **uid** (`customer_name` = uid). The masked
name rides along as `customer_display_name`. Rows carry the uid in
`data-random="<uid>-0-<group>"`; the socket carries it as `from.uid`.

## Sending

The HTTP send needs `anti_content`, which only the page's own script can mint,
so `pdd_send_message` opens the conversation, verifies the thread's
`currentuid` is that buyer (it refuses to type otherwise), types into
`#replyTextarea`, clicks `.send-btn`, and waits for the bubble. A send that
clicked but was not seen is reported as `pdd_send_unverified:*` and never
retried (it may have landed).

## Skill wiring (front desk)

- `hookBundles: [{"path": "pdd_chat", ...}]` — sets the active site for the node.
- Event monitor: DOM mutation on `page_url_patterns: ["mms.pinduoduo.com/chat-merchant"]`
  (the platform starts `ws_observer` from it).
- `preDispatch.site_plugin: "pdd_chat"`, `actionableField: "unread_badge"`,
  `assignment_extra_fields: ["latest_message_msg_id", "last_message_attachments",
  "customer_display_name", "product_context", "message_kind"]` — without the
  list, pictures and product context never reach the Q&A agent.
- Tools: `pdd_*`.

## Not done yet

Front-desk / Q&A skills + prompts for Pinduoduo, a Fast Deploy recipe, a GUI
switch instead of the env var, PDD's own robot hosting (托管) detection,
transfer / close notices, a live end-to-end run on a real store.
