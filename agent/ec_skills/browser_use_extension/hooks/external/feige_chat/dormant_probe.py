# -*- coding: utf-8 -*-
"""ws182: dormant-conversation read-probe — phase 1 EXPERIMENT, default OFF.

The 2026-07-18 run quantified the cold-start latency floor: a dormant
conversation's new message is WITHHELD server-side for ~66s (11:14:12 send →
11:15:18 first sidebar paint; the decoded wscap window shows 203 frames and
ZERO customer messages, and even the page's ~1/s get_user_message polling
surfaced nothing). The question this probe answers with ONE run:

  Do the backstage JSON read endpoints bypass the assignment gate — i.e.
  return a withheld message / the dormant conversation's fresh state EARLY —
  and do their captured auth params (cookies + x-secsdk-csrf-token + query
  msToken/a_bogus) replay successfully from an in-page ``fetch()``?

Phase 1 only REPLAYS + LOGS (marker ``[FEIGE-DORMANT-PROBE]``); it dispatches
nothing. Phase 2 wires whichever endpoint proves EARLY into detection.

Wiring:
  - ``feige_bot_control``'s network sniffer stashes live URL+header templates
    via :func:`note_request` (so the probe replays REAL, fresh-signed URLs the
    page just used — no signing code on our side). The sniffer must be armed
    (``ECAN_FEIGE_BOT_TOGGLE_CAPTURE=1`` or ``ECAN_FEIGE_OPEN_CLAIM_CAPTURE=1``,
    both standard in Feige runs).
  - ``front_desk``'s ws108 tick calls :func:`maybe_probe` — internally
    throttled + capped, a no-op on most ticks.

Gates: ``ECAN_FEIGE_DORMANT_POLL=1`` (default OFF),
``ECAN_FEIGE_DORMANT_POLL_S`` (default 15s between probes),
``ECAN_FEIGE_DORMANT_POLL_MAX`` (default 200 probes per run).
"""

import json
import logging
import os
import time

logger = logging.getLogger("eCan")

# Candidate READ endpoints (JSON, cookie+csrf auth — replayable without the
# protobuf pigeon_sign machinery). The signed fxg pigeon_im endpoints
# (get_by_conversation etc.) are deliberately OUT of phase 1.
_EP_KEYS = (
    "getConversationSummary",
    "getCSReceptionInServiceAssist",
    "can_start_conversation",
)

# ep_key -> {"ep", "url", "method", "headers", "body"}; latest capture wins so
# the replayed query params (msToken/a_bogus/verifyFp) stay as fresh as the
# page's own traffic.
_TEMPLATES: dict = {}
_probe_state = {"last_ts": 0.0, "count": 0, "logged_off": False}


def note_request(method: str, url: str, headers: dict, post: str) -> None:
    """Stash a live request template for candidate endpoints (sniffer hook)."""
    try:
        u = str(url or "")
        ep = next((k for k in _EP_KEYS if k in u), "")
        if not ep:
            return
        h = {}
        src = headers or {}
        for k, v in src.items():
            if str(k).lower() in ("x-secsdk-csrf-token", "content-type"):
                h[str(k)] = str(v)
        body = str(post or "")
        if body and not body.lstrip().startswith("{"):
            body = ""   # non-JSON (protobuf) bodies don't replay — drop
        _TEMPLATES[ep] = {
            "ep": ep, "url": u, "method": str(method or "GET"),
            "headers": h, "body": body,
        }
    except Exception:
        pass


async def maybe_probe(browser_session) -> None:
    """Replay the stashed templates in-page and log status+body head. Throttled;
    total no-op unless ECAN_FEIGE_DORMANT_POLL=1."""
    if os.environ.get("ECAN_FEIGE_DORMANT_POLL", "") != "1":
        return
    try:
        gap = float(os.environ.get("ECAN_FEIGE_DORMANT_POLL_S", "15") or 15)
    except (TypeError, ValueError):
        gap = 15.0
    try:
        cap = int(os.environ.get("ECAN_FEIGE_DORMANT_POLL_MAX", "200") or 200)
    except (TypeError, ValueError):
        cap = 200
    now = time.time()
    if now - _probe_state["last_ts"] < gap or _probe_state["count"] >= cap:
        return
    if not _TEMPLATES:
        if not _probe_state["logged_off"]:
            _probe_state["logged_off"] = True
            logger.info(
                "[FEIGE-DORMANT-PROBE] armed but no templates captured yet — "
                "needs the bot-toggle/open-claim sniffer running and the page "
                "to have fired one of: " + ", ".join(_EP_KEYS))
        return
    _probe_state["last_ts"] = now
    _probe_state["count"] += 1
    try:
        from agent.ec_skills.browser_use_extension.extension_tools_service import (
            _evaluate_js,
        )
        templates = list(_TEMPLATES.values())[:3]
        js = (
            "(async function(){var T=" + json.dumps(templates, ensure_ascii=False) + ";"
            "var out=[];for(var i=0;i<T.length;i++){var t=T[i];try{"
            "var o={method:t.method,headers:t.headers,credentials:'include'};"
            "if(t.body)o.body=t.body;"
            "var r=await fetch(t.url,o);var x=await r.text();"
            "out.push({ep:t.ep,status:r.status,len:x.length,head:x.slice(0,600)});"
            "}catch(e){out.push({ep:t.ep,err:String(e)});}}"
            "return JSON.stringify(out);})()"
        )
        res = await _evaluate_js(
            browser_session, js,
            focus=False, read_only=True, lock_free=True,
            timeout_s=10.0,
            trace_label="feige_dormant_probe",
        )
        rows = []
        if isinstance(res, str):
            try:
                rows = json.loads(res)
            except Exception:
                rows = []
        if not isinstance(rows, list):
            rows = []
        for r in rows:
            logger.info(
                f"[FEIGE-DORMANT-PROBE] #{_probe_state['count']} ep={r.get('ep')} "
                f"status={r.get('status')} len={r.get('len')} err={r.get('err', '')!r} "
                f"head={str(r.get('head', ''))[:600]!r}")
        if not rows:
            logger.info(
                f"[FEIGE-DORMANT-PROBE] #{_probe_state['count']} eval returned no rows "
                f"(res_type={type(res).__name__})")
    except Exception as exc:
        logger.info(f"[FEIGE-DORMANT-PROBE] probe failed (non-fatal): {exc}")
