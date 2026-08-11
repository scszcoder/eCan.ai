"""Qianniu (千牛) WebSocket observer — Phase 1: CAPTURE-ONLY.

The platform's event monitor starts/stops this through the bridge exactly
as it does Feige's full observer:

    bridge.ws_observer.start_ws_shadow_observer(session, target_id, label,
                                                dispatch_fn=...)
    bridge.ws_observer.stop_ws_shadow_observer(client)

Phase 1 does **no decoding and no dispatch** — it attaches an isolated CDP
client to every Qianniu IM tab and appends every WebSocket frame (both
directions, verbatim payloads) to ``runlogs/tmall_capture_<ts>.jsonl``.
That corpus is the feedstock for the Phase 2 protocol reverse-engineering
(the Feige equivalent produced ``ws_reader.py``/``ws_sender.py`` from
captures decoded offline — see ``docs/TMALL_QIANNIU_CHAT_DESIGN.md`` D2).

Gate: ``ECAN_TMALL_WS_CAPTURE=1`` (default OFF → ``start`` returns None
and the DOM monitor runs alone, unaffected).

``dispatch_fn`` is accepted for signature compatibility and unused.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any

from utils.logger_helper import logger_helper as logger

from .dom import is_tmall_im_url

_CAPTURE_DIR = "runlogs"
_FP_ATTR = "_ecan_tmall_capture_fp"
_URLMAP_ATTR = "_ecan_tmall_capture_urlmap"


def capture_enabled() -> bool:
    return os.environ.get("ECAN_TMALL_WS_CAPTURE", "") == "1"


def _open_capture_file():
    os.makedirs(_CAPTURE_DIR, exist_ok=True)
    path = os.path.join(
        _CAPTURE_DIR, time.strftime("tmall_capture_%Y%m%d-%H%M%S.jsonl")
    )
    fp = open(path, "a", encoding="utf-8")
    return fp, path


async def start_ws_shadow_observer(session: Any, target_id: str, label: str = "",
                                   dispatch_fn=None) -> Any:
    """Attach a capture-only CDP observer.  Returns the CDP client (caller
    stops it on monitor teardown) or ``None`` when disabled / on failure."""
    if not capture_enabled():
        return None

    cdp_url = getattr(session, "cdp_url", None)
    if not cdp_url:
        bp = getattr(session, "browser_profile", None)
        cdp_url = getattr(bp, "cdp_url", None) if bp else None
    if not cdp_url:
        logger.warning("[TMALL-WS-CAP] no cdp_url on session — capture not started")
        return None

    try:
        from cdp_use import CDPClient

        client = CDPClient(url=cdp_url)
        await client.start()

        try:
            tinfos = (await client.send_raw("Target.getTargets", {})).get("targetInfos", [])
        except Exception:
            tinfos = []
        targets = [target_id] + [
            t.get("targetId") for t in tinfos
            if t.get("type") == "page"
            and is_tmall_im_url(t.get("url") or "")
            and t.get("targetId") and t.get("targetId") != target_id
        ]
        sids = []
        for tid in targets:
            if not tid:
                continue
            try:
                sid = (await client.send_raw(
                    "Target.attachToTarget", {"targetId": tid, "flatten": True})).get("sessionId")
                if sid:
                    await client.send_raw("Network.enable", {}, session_id=sid)
                    sids.append(sid)
            except Exception:
                pass
        if not sids:
            logger.warning("[TMALL-WS-CAP] no sessions attached — capture not started")
            await client.stop()
            return None

        fp, path = _open_capture_file()
        setattr(client, _FP_ATTR, fp)
        url_by_request: dict = {}
        setattr(client, _URLMAP_ATTR, url_by_request)
        stats = {"recv": 0, "sent": 0}

        def _write(record: dict) -> None:
            try:
                record["ts"] = time.time()
                fp.write(json.dumps(record, ensure_ascii=False) + "\n")
                fp.flush()
            except Exception:
                pass

        def _frame_record(direction: str, params: dict, session_id=None) -> None:
            resp = params.get("response", {}) or {}
            _write({
                "dir": direction,
                "opcode": resp.get("opcode"),
                "payload": resp.get("payloadData", ""),
                "request_id": params.get("requestId", ""),
                "url": url_by_request.get(params.get("requestId", ""), ""),
                "sid": session_id or "",
            })
            stats["recv" if direction == "recv" else "sent"] += 1

        def _on_frame(params, session_id=None):
            try:
                _frame_record("recv", params, session_id)
            except Exception:
                pass

        def _on_sent(params, session_id=None):
            try:
                _frame_record("sent", params, session_id)
            except Exception:
                pass

        def _on_socket_created(params, session_id=None):
            try:
                rid = params.get("requestId", "")
                url = str(params.get("url") or "")
                if rid:
                    url_by_request[rid] = url
                _write({"dir": "created", "request_id": rid, "url": url,
                        "sid": session_id or ""})
            except Exception:
                pass

        def _on_socket_closed(params, session_id=None):
            try:
                rid = params.get("requestId", "")
                _write({"dir": "closed", "request_id": rid,
                        "url": url_by_request.get(rid, ""), "sid": session_id or ""})
            except Exception:
                pass

        client._event_registry.register("Network.webSocketFrameReceived", _on_frame)
        client._event_registry.register("Network.webSocketFrameSent", _on_sent)
        client._event_registry.register("Network.webSocketCreated", _on_socket_created)
        client._event_registry.register("Network.webSocketClosed", _on_socket_closed)

        logger.info(
            f"[TMALL-WS-CAP] capture started: label={label!r} tabs={len(sids)} → {path}"
        )
        return client
    except Exception as err:
        logger.warning(f"[TMALL-WS-CAP] start failed: {err}")
        return None


async def stop_ws_shadow_observer(client: Any) -> None:
    """Best-effort teardown: close the capture file, stop the client."""
    if client is None:
        return
    fp = getattr(client, _FP_ATTR, None)
    if fp is not None:
        try:
            fp.close()
        except Exception:
            pass
    try:
        await client.stop()
    except Exception:
        pass
    logger.info("[TMALL-WS-CAP] capture stopped")
