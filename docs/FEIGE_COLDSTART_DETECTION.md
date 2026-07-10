# Feige Cold-Start Detection Algorithm

**Status:** implemented ws166/ws167 (2026-07-10). Files: `hooks/external/feige_chat/ws_session.py`, `front_desk.py`, `event_monitor.py`.

## The problem

Feige (飞鸽/Douyin IM) has two message-detection channels, and each is blind in a
different way:

1. **WS (Frontier socket, passive observation)** — realtime, but the server does
   **not push frames for a conversation that wasn't active when the socket
   connected**, and **stops pushing after the conversation is closed**
   (`关闭会话`). Text and 转人工 sent into a dormant conversation produce **zero
   frames** (verified repeatedly; product cards are the exception — they do
   traverse WS even for dormant conversations). This is external server
   behavior and cannot be fixed on our side.
2. **DOM (renderer evals)** — sees everything the page renders, but heavy
   sidebar/bubble scrapes saturate the renderer under load (~96 scrapes/min →
   104–188s detection blackouts; the historical 1-vs-N stall root). The heavy
   scrape is therefore **deliberately paused** while WS is delivering
   (`is_dispatch_live()`), keeping only a **light ~3ms sidebar scan** (ws108)
   always-on.

The failure mode: `is_dispatch_live()` is **per-socket** (sticky True after the
first frame from *any* conversation) while WS blindness is
**per-conversation**. A dormant customer's first message hits: WS silent for
that conversation + heavy DOM paused + (pre-ws166) the light scan silently dead
until the first browser_event registered the dispatch slot → total blindness.
This single condition explained most of the "random" cold-start failures across
30+ revisions: multi-customer tests half-worked because *someone's* card frame
woke the pipeline; single-customer text/转人工 tests failed totally.

## The algorithm (per-conversation dormant/live state machine)

```
State per conversation X:
  DORMANT  — no WS frame observed for X since process start,
             OR since X's last 关闭会话 close marker.
  LIVE     — at least one WS frame observed for X since then.

Transitions:
  process start                          → every conversation DORMANT
  any WS frame arrives for X's talk_id   → X becomes LIVE
  sidebar shows 关闭会话 for X            → X becomes DORMANT again

Detection ownership:
  X DORMANT → the DOM side owns X's next message (it IS a cold start;
              WS will not deliver it). The ws108 light sidebar scan routes
              X's row change on the FAST gate (~4s) — no "give WS first
              crack" wait, because WS gets no crack.
  X LIVE    → WS owns X's realtime detection. The light scan remains X's
              late safety net only (15s stale gate), with the ws126
              inflight dedup preventing double-dispatch.
```

Key properties:

- **Dormancy is per-customer/conversation**, matching the actual granularity of
  WS blindness. The global `is_dispatch_live()` pause of the *heavy* DOM scrape
  is unchanged (renderer protection) — the light scan is the dormant watcher.
- **Never-seen customers are dormant by definition** (no frame yet), covering
  first-contact-ever and process-restart without special cases.
- **关闭会话 is the dormant re-entry signal** (both variants:
  `客服【店铺】手动关闭会话` and `用户超时未回复，系统关闭会话`; regex
  `session_close_notice` in `system_message_filter.py`). Verified live: a
  conversation that was WS-live at 19:44 was manually closed; its 21:38 转人工
  arrived with zero frames.
- **Cards may arrive on both channels** for a dormant conversation (WS delivers
  cards even cold). That's fine: dormancy never *suppresses* WS; the existing
  ws126 backstop↔WS inflight dedup + msg-id dedup collapse duplicates.

## Implementation map

| Piece | Where | Marker to grep |
|---|---|---|
| Per-conv live stamp on every frame | `ws_session.note_recv_frame` → `_stamp_conv_live(talk)` | — |
| `is_conv_live(name_or_talk)` / `mark_conv_dormant(...)` | `ws_session.py` (handles `card:<talk>` synth names) | — |
| Dormant re-entry on close marker | ws108 scan in `front_desk.coldstart_overdue_recovery_scan` | `ws167 close marker -> conversation DORMANT` |
| Dormant fast-route (4s gate instead of 15s) | same scan, stale-gate selection | `ws167 dormant fast-route` |
| Scan alive from t=0 without a prior event (slot bootstrap via legacy browser_event) | `event_monitor.check_now` → `coldstart_overdue_recovery_scan(legacy_dispatcher=_ws_dispatch_fn)` | `ws166 backstop scanning WITHOUT dispatch slot`, `ws166 backstop -> legacy event dispatch` |
| Connect-banner rows route fast (pre-existing) | same scan (`ws144`) | `ws108 missed-msg backstop: routing CONNECT-BANNER` |

Env gates (all default **on**): `ECAN_FEIGE_DORMANT_FASTROUTE`,
`ECAN_FEIGE_COLDSTART_RECOVERY_SCRAPE` (=1 required for the scan),
`ECAN_FEIGE_BACKSTOP_INTERVAL_S` (5), `ECAN_FEIGE_BACKSTOP_CONNECT_STALE_S` (4,
also the dormant gate), `ECAN_FEIGE_BACKSTOP_STALE_S` (15, live-row safety
net).

## Expected cold-start timeline (SLA: answer < 40s)

```
t=0     dormant customer sends text/card/转人工
t≤5s    ws108 scan tick sees the row change (banner or badge)
t≤9s    fast gate passes → routed (legacy event if slot cold, direct if warm)
t≤12s   enrich thread-scrape pulls the real message; 过渡句/[微笑] fires
t≤30s   QA answer delivered; conversation now LIVE (reply echo/frames follow)
```

## History / why it looked random for 30+ revisions

Before ws166, the scan required the front-desk dispatch slot, which registered
only on the **first browser_event** of the process — so at every startup the
safety net was silently dead until some WS-visible message (usually a card)
woke it, after which it immediately drained any stuck cold-starts (e.g. ws150
log Jul 7: dead 22:31:58→22:45:38, then three CONNECT-BANNER rows routed within
90s of the first event). Run-to-run variance in *when* that lucky wake-up
happened produced the apparently-random cold-start behavior. Related fixes in
the same arc: ws162 (mt030 must not mask backstop reopens), ws163 (转人工
[微笑] ack reliability), ws164 (new-turn answers must not be dup-killed on
identical text), ws165 (cold-start card must not resolve to the wrong
customer's sidebar row).
