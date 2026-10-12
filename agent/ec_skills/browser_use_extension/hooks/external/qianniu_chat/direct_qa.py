"""A buyer message straight to a Q&A agent, as the 千牛 front desk.

The front desk's graph turned each buyer message into the same send_chat with
an LLM round (~2.5 s per message, alpha yt 2026-10-12) -- nothing in it needs
a model: the Q&A agent comes from the front desk's ``task_vars.qa_agent_ids``
(the pool picks one per customer), the message is fixed JSON. The Q&A agent's
reply comes back to the front desk agent and goes out through the runner's
reply direct-delivery (``runner_bridge.deliver_reply``).

Returns False whenever it can't (no front desk / Q&A agent yet, send failed,
``ECAN_QIANNIU_DIRECT_QA=0``): the observer then emits the browser event and
the front desk's graph handles the message as before.
"""
from __future__ import annotations

import json
import os
import threading
from collections import OrderedDict

from utils.logger_helper import logger_helper as logger

SITE = "qianniu_chat"
_recent: "OrderedDict[str, list]" = OrderedDict()   # customer id -> last 5 messages (front-desk prep's "recent")
_lock = threading.Lock()


def enabled() -> bool:
    return os.environ.get("ECAN_QIANNIU_DIRECT_QA", "1") != "0"


def _task_vars(task) -> dict:
    md = getattr(task, "metadata", None)
    tv = md.get("task_vars") if isinstance(md, dict) else None
    return tv if isinstance(tv, dict) else {}


def front_desk(mainwin):
    """(agent, task) of the running 千牛 front desk: a task whose skill is a
    qianniu_chat skill and that names its Q&A agents. Reads only cheap agent
    attributes (lazy agents are not built)."""
    from agent.ec_skills import live_chat_dispatch
    for ag in list(getattr(mainwin, "agents", None) or []):
        for task in list(getattr(ag, "tasks", None) or []):
            if not _task_vars(task).get("qa_agent_ids"):
                continue
            if live_chat_dispatch.site_for_skill(getattr(task, "skill", None)) == SITE:
                return ag, task
    return None, None


def forward(item: dict) -> bool:
    """Send the observer's *item* (customer_id, customer_display_name,
    latest_message, product_card) to a Q&A agent. True = sent."""
    if not enabled():
        return False
    try:
        from app_context import AppContext
        mainwin = AppContext.get_main_window()
        fd_agent, fd_task = front_desk(mainwin)
        if fd_agent is None:
            return False
        fd_id = str(getattr(getattr(fd_agent, "card", None), "id", "") or "")
        uid = str(item.get("customer_id") or item.get("customer_name") or "").strip()
        msg = str(item.get("latest_message") or item.get("last_message") or "").strip()
        if not fd_id or not uid or not msg:
            return False
        from agent.ec_agents.agent_pool import pick_for_customer
        qa_id = pick_for_customer(fd_id, uid, _task_vars(fd_task).get("qa_agent_ids"))
        if not qa_id:
            return False
        name = str(item.get("customer_display_name") or "").strip()
        product = str(item.get("product_card") or "").strip()
        with _lock:
            recent = (_recent.pop(uid, None) or []) + [msg]
            _recent[uid] = recent[-5:]
            while len(_recent) > 500:
                _recent.popitem(last=False)
            recent = list(_recent[uid])
        message = json.dumps({
            "customer_id": uid,
            "customer_name": name or uid,
            "latest_message": msg,
            # the product the buyer asks about first (the Q&A prompt reads "[商品卡片] …")
            "customer_recent_messages": ([product] if product else []) + recent,
        }, ensure_ascii=False)
        from agent.mcp.server.chat_utils.chat_tools import send_chat
        res = send_chat(mainwin, {"sender_agent_id": fd_id, "recipient_agent_id": qa_id, "message": message})
        ok = bool((res or {}).get("success"))
        logger.info(f"[QIANNIU-FD] direct to Q&A {qa_id} ({'sent' if ok else 'FAILED: ' + str((res or {}).get('error'))}) "
                    f"buyer={uid!r} name={name!r}: {msg[:40]!r}")
        return ok
    except Exception as exc:
        logger.warning(f"[QIANNIU-FD] direct to Q&A failed, the front desk takes it: {exc}")
        return False
