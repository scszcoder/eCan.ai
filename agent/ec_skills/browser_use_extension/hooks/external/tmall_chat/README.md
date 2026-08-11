# tmall_chat — Tmall / Qianniu (千牛) live-chat bundle

Phase 1 scaffold (2026-08-11). Design doc: `docs/TMALL_QIANNIU_CHAT_DESIGN.md`.
Template: the sibling `feige_chat` bundle (read its README + the
platform/feige decoupling doc first).

## Activation

```
ECAN_LIVE_CHAT_SITE=tmall_chat    # required — default active site is feige_chat
ECAN_TMALL_WS_CAPTURE=1           # optional — record Qianniu WS frames for Phase 2
ECAN_TMALL_IM_URL_MARKERS=...     # optional — override Qianniu IM tab URL substrings
```

When `ECAN_LIVE_CHAT_SITE` is unset or `feige_chat`, this bundle imports
but registers **nothing** (no bridge, no tools) — Feige behavior is
bit-identical to before this bundle existed.

## What works in Phase 1

- `TmallRunnerBridge` (partial surface — missing attributes intentionally
  fall back to platform defaults via the guard-semantics invariant)
- Four DOM controller tools: `tmall_list_sessions`, `tmall_open_session`,
  `tmall_get_chat_thread`, `tmall_send_message` (typing-lock serialized)
- Qianniu tab resolution by URL marker (`dom.py`)
- Capture-only WS observer → `runlogs/tmall_capture_*.jsonl`
- Prompts: `customer_logs/prompt_pr-tmall-fd.json` (前台) /
  `prompt_pr-tmall-qa.json` (应答)

## What is NOT here yet (Phase 2/3 — see design doc)

WS frame decoding + WS-path detection, off-DOM WS send, hot paths,
pre-dispatch enrichment, placeholder pipeline, human-mode/bot arbitration,
multi-tab pool, product-card capture, cold-start state machine.

## ⚠️ Calibration playbook (FIRST live run against the real workbench)

Every `_TMALL_*` selector in `site_tools.py` / `site_adapter_preset.py`
and the literals in `system_message_filter.py` are SPECULATIVE.

1. Log into Qianniu Web, open the seller IM page. Note the actual host —
   if it isn't in `dom.im_url_markers()`, set `ECAN_TMALL_IM_URL_MARKERS`.
2. Run `tmall_list_sessions`. If `total_visible=0`, extract_dom the left
   session panel, pin real row/name/preview/badge selectors into
   `site_tools.py` and `site_adapter_preset.py`, and document them in the
   header comment the way `feige_chat/site_tools.py` does.
3. Repeat for `tmall_get_chat_thread` (thread pane) and
   `tmall_send_message` (compose input + send button + header nick).
4. Set `ECAN_TMALL_WS_CAPTURE=1`, send messages from a buyer account, and
   collect `runlogs/tmall_capture_*.jsonl` — the Phase 2 protocol corpus.
5. Pin real system-row texts into `system_message_filter.py` and sync the
   front-desk prompt's 预筛选 keyword list.
6. Anti-bot: keep sends on the DOM path; do not enable any raw-socket
   sending until risk-control behavior is understood.
