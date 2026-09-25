# pdd_chat — Pinduoduo (拼多多) merchant customer chat

**Phase 0: probing.** Nothing here answers customers yet. This bundle supplies
the site preset (`site.py`) for the generic probe
(`agent/ec_skills/browser_use_extension/site_probe.py`), which records what the
chat page says over the wire so the protocol can be decoded offline — the path
Feige took from capture to `ws_reader.py` / `ws_sender.py`.

## Record a session

1. Open the store's login (Settings → Browser Profiles → Launch — or any
   Chrome started with `--remote-debugging-port=9222`) and log in to
   商家后台 → 客服 (the chat workbench).
2. Start the probe. In the app (what a customer uses): Settings → Browser
   Profiles → on the open login, **Record traffic → pdd_chat**; stop with the
   **Recording** button, which shows what was captured. From a dev checkout:

   ```
   ecan probe run --site pdd_chat --profile <login id>
   ecan probe run --site pdd_chat --cdp-url http://127.0.0.1:9222
   ```

3. Use the chat for 10–20 minutes, covering as much as possible:
   * receive a message in the OPEN conversation, and one in a conversation
     that is NOT open (sidebar only);
   * send a text reply, an emoji, an image, a product card / order link;
   * a new customer arriving; switching conversations; marking read;
   * a conversation transferred / closed / timing out (系统消息);
   * the page reconnecting (toggle Wi-Fi briefly).
4. Ctrl+C. The probe prints a summary; the capture is
   `runlogs/probe/pdd_chat_<time>.jsonl` plus `..._dom1.html` snapshots.
   `ecan probe summarize <file>` re-prints the summary.

On a customer's machine: run the probe there, then **Vehicles → Fetch logs**
from the commander — `runlogs/probe/` travels with the logs.

## What is captured, what is not

* every WebSocket opened by the chat pages **and their workers**: URL (token-
  like query values redacted), handshake headers (cookie/auth values
  redacted), every frame both directions — text verbatim, binary as base64;
* API calls (XHR/fetch) on pinduoduo/yangkeduo hosts: method, URL, request
  body, status, response body (≤ 256 KB);
* one DOM snapshot per chat tab when first attached.

Frames and API bodies are NOT redacted — they are what we are decoding — so a
capture contains real customer conversations. It stays in `runlogs/probe/`.

Narrow or widen what is watched without a release:
`ECAN_PDD_PAGE_MARKERS` (page URL substrings, default `mms.pinduoduo.com`),
`ECAN_PDD_API_MARKERS` (default `pinduoduo.com,yangkeduo.com`).

## Next (after the first capture)

1. Decode: which socket carries chat, framing (JSON / protobuf / custom),
   message kinds (new message, read, typing, system), the ids that identify a
   conversation and a customer, and whether sends go over the socket or an API.
2. Then build it the Feige way, in this bundle: a read-only WS reader wired as
   a shadow observer, DOM tools for the conversation list / thread / send, the
   runner bridge, prompts and skills — platform code stays untouched
   (keep-core-general rule).
