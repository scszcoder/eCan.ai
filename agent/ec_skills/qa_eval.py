"""Try a Q&A agent on a fake buyer turn and read its reply -- nothing is sent.

``qa.eval`` (gui/ipc/w2p_handlers/qa_eval_handler.py) hands a Q&A agent a turn
shaped exactly like the front desk's (frontdesk_dispatch._build_assignment_payload:
latest_message + latest_message_attachments with the picture as a data URI),
marked with ``_ecan_eval``. The agent runs as it would for a real buyer --
its prompt, model, vision input, knowledge lookups, tools. When it would hand
its answer back to the front desk, send_response_back asks ``capture()``: a
marked turn is recorded here and NOT sent, so no front desk, store or buyer
ever sees it.

Why not a fake WS frame: for 抖店 an image message's frame carries no picture
-- the front desk scrapes the bubble from the page -- so the hand-off is the
first point where the picture exists.
"""
from __future__ import annotations

import json
import threading
import time
from typing import Any, Dict, Optional

MARK = "_ecan_eval"
_lock = threading.Lock()
_pending: Dict[str, Dict[str, Any]] = {}


def register(eval_id: str) -> threading.Event:
    ev = threading.Event()
    with _lock:
        _pending[eval_id] = {"event": ev, "started": time.time(), "result": None}
    return ev


def take(eval_id: str) -> Optional[Dict[str, Any]]:
    with _lock:
        slot = _pending.pop(eval_id, None)
    return (slot or {}).get("result")


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        return str(value)


def eval_id_of(state: Any) -> str:
    """The eval id carried by this run's turn, or ""."""
    if not isinstance(state, dict):
        return ""
    for part in (state.get("input"), state.get("attributes")):
        t = _text(part) if part else ""
        i = t.find(MARK)
        if i >= 0:
            tail = t[i + len(MARK):i + len(MARK) + 80]
            for q in ('": "', '\\": \\"', '":"', '\\":\\"'):
                j = tail.find(q)
                if j == 0:
                    return tail[len(q):].split('"')[0].split("\\")[0]
            return "?"
    return ""


def _reply_of(state: dict) -> Dict[str, Any]:
    result = state.get("result") or {}
    llm = result.get("llm_result") if isinstance(result, dict) else None
    last = ""
    for m in reversed(state.get("messages") or []):
        content = getattr(m, "content", None)
        if content and type(m).__name__ in ("AIMessage", "AIMessageChunk"):
            last = content if isinstance(content, str) else _text(content)
            break
    tools = []
    for m in state.get("messages") or []:
        for call in getattr(m, "tool_calls", None) or []:
            tools.append({"name": call.get("name"), "args": call.get("args")})
        if type(m).__name__ == "ToolMessage":
            tools.append({"result_of": getattr(m, "name", ""), "content": _text(getattr(m, "content", ""))[:1500]})
    return {"llm_result": llm, "last_ai_message": last, "tools": tools[-12:]}


def capture(state: Any) -> bool:
    """True when this run is an eval turn: its reply is recorded and must not be sent."""
    eid = eval_id_of(state)
    if not eid:
        return False
    with _lock:
        slot = _pending.get(eid)
        if slot is not None and slot["result"] is None:
            slot["result"] = {**_reply_of(state), "elapsed_s": round(time.time() - slot["started"], 1)}
            slot["event"].set()
    try:
        from utils.logger_helper import logger_helper as logger
        logger.info(f"[qa-eval] reply captured for {eid} (not sent)")
    except Exception:
        pass
    return True


def capture_send(message_text: Any) -> Optional[Dict[str, Any]]:
    """send_chat's guard: a reply addressed to an eval buyer (customer_id
    "eval-<id>") is recorded and must not be sent -- returns send_chat's
    result for it, or None for every other message. The eval hand-off itself
    carries MARK and is let through."""
    if not isinstance(message_text, str) or "eval-ev" not in message_text or MARK in message_text:
        return None
    try:
        msg = json.loads(message_text, strict=False)
    except Exception:
        msg = None
    cid = str((msg or {}).get("customer_id") or "") if isinstance(msg, dict) else ""
    if not cid.startswith("eval-ev"):
        if '"customer_id": "eval-ev' not in message_text and '"customer_id":"eval-ev' not in message_text:
            return None
        cid = "eval-" + message_text.split("eval-", 1)[1].split('"')[0]
    eid = cid[len("eval-"):]
    with _lock:
        slot = _pending.get(eid)
        if slot is not None and slot["result"] is None:
            slot["result"] = {"response_text": (msg or {}).get("response_text") if isinstance(msg, dict) else None,
                              "message": msg if isinstance(msg, dict) else message_text[:2000],
                              "elapsed_s": round(time.time() - slot["started"], 1)}
            slot["event"].set()
    try:
        from utils.logger_helper import logger_helper as logger
        logger.info(f"[qa-eval] send_chat reply captured for {eid} (not sent)")
    except Exception:
        pass
    return {"success": True, "eval_captured": True, "chat_id": f"eval-{eid}", "timestamp": int(time.time() * 1000)}
