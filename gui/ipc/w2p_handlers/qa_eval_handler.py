"""qa.eval: give a Q&A agent a fake buyer turn (text and/or pictures) and return
its reply -- nothing is sent to the front desk, a store or a buyer
(agent/ec_skills/qa_eval.py).

params:
  agent        Q&A agent name or id (required)
  text         the buyer's message ("" with pictures = a picture-only turn)
  images       local picture paths or https links, read/downloaded here
  store_id     the eCan store the turn belongs to (scopes product knowledge)
  sender       front desk agent name or id (default: an agent named 前台…)
  timeout_s    how long to wait for the reply (default 180)
"""
from __future__ import annotations

import base64
import json
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response
from utils.logger_helper import logger_helper as logger


def _agents():
    from app_context import AppContext
    mw = AppContext.get_main_window()
    return list(getattr(mw, "agents", None) or []), mw


def _find(agents, ref: str):
    for ag in agents:
        card = getattr(ag, "card", None)
        if ref in (getattr(card, "id", None), getattr(card, "name", None)):
            return ag
    return None


def _picture(src: str) -> Dict[str, Any]:
    from knowledge.ks import product_images
    data, err = product_images._fetch(src)
    if data is None:
        raise ValueError(f"picture {src!r}: {err}")
    ext = product_images._ext_of(data, src.rsplit(".", 1)[-1])
    if not ext:
        raise ValueError(f"picture {src!r}: not an image")
    mime = "image/jpeg" if ext == "jpg" else f"image/{ext}"
    return {"kind": "image", "mime": mime, "byte_len": len(data),
            "data_uri": f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"}


def _run(params: Dict[str, Any]) -> Dict[str, Any]:
    from agent.ec_skills import qa_eval
    from agent.mcp.server.chat_utils.chat_tools import send_chat
    agents, mainwin = _agents()
    qa = _find(agents, str(params.get("agent") or ""))
    if qa is None:
        raise ValueError(f"no agent {params.get('agent')!r} in this app")
    sender = _find(agents, str(params.get("sender") or "")) or next(
        (a for a in agents if str(getattr(a.card, "name", "")).startswith("前台")), qa)
    text = str(params.get("text") or "").strip()
    pictures = [_picture(str(s)) for s in params.get("images") or []]
    if not text and not pictures:
        raise ValueError("text or images is required")
    eval_id = "ev" + uuid.uuid4().hex[:12]
    payload = {
        "customer_id": f"eval-{eval_id}", "session_id": f"eval-{eval_id}", "chat_url": "",
        "customer_name": "测试买家", "latest_message": text or "[图片]",
        "latest_message_msg_id": eval_id,
        qa_eval.MARK: eval_id,
    }
    if params.get("store_id"):
        payload["store_id"] = str(params["store_id"])
    if pictures:
        payload["latest_message_attachments"] = pictures
    done = qa_eval.register(eval_id)
    send = {"sender_agent_id": sender.card.id, "recipient_agent_id": qa.card.id, "chat_id": f"eval-{eval_id}",
            "message": json.dumps(payload, ensure_ascii=False), "message_type": "text", "async_send": False}
    logger.info(f"[qa-eval] {eval_id} -> {qa.card.name}: text={text[:40]!r} pictures={len(pictures)}")
    t0 = time.time()
    sent: Dict[str, Any] = {}
    threading.Thread(target=lambda: sent.update(send_chat(mainwin, send) or {}),
                     name=f"qa-eval-{eval_id}", daemon=True).start()
    finished = done.wait(float(params.get("timeout_s") or 180))
    result = qa_eval.take(eval_id)
    sent_text = json.dumps(sent, ensure_ascii=False, default=str)
    return {"eval_id": eval_id, "agent": qa.card.name, "finished": finished,
            "seconds": round(time.time() - t0, 1), "reply": result,
            # A skill that answers through the synchronous waiter instead of
            # send_response_back: its answer is send_chat's return value.
            "send_chat": json.loads(sent_text) if len(sent_text) <= 4000 else {"truncated": sent_text[:4000]}}


@IPCHandlerRegistry.background_handler('qa.eval')
def handle_qa_eval(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    try:
        return create_success_response(request, _run(params or {}))
    except ValueError as e:
        return create_error_response(request, 'INVALID_PARAMS', str(e))
    except Exception as e:
        logger.error(f"[qa-eval] failed: {type(e).__name__}: {e}")
        return create_error_response(request, 'QA_EVAL_ERROR', f"{type(e).__name__}: {e}")
