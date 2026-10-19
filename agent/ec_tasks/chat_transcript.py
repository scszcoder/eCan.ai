"""Give a chat skill its conversation back after the app restarts.

A skill's run state lives in an in-memory LangGraph checkpointer on desktop,
so a restart starts every chat skill over with an empty history -- although
the chat window still shows the whole conversation from the database. A skill
that opts in gets the last N messages of its chat loaded into ``history`` when
a run starts fresh, so it carries on instead of starting over.

Opt-in (first found wins): the task's settings ``restore_chat_history``, the
skill's ``config["restore_chat_history"]``, or a top-level
``"restore_chat_history"`` in the skill file. The value is how many messages
to load (``true`` = 40). Skills that wipe history on purpose (the 客服 Q&A
skills reset it per buyer) simply don't opt in.
"""
from __future__ import annotations

from typing import Any, List, Optional

from utils.logger_helper import logger_helper as logger

DEFAULT_LIMIT = 40
MAX_LIMIT = 200
KEY = "restore_chat_history"


def _as_limit(value: Any) -> int:
    if value is True:
        return DEFAULT_LIMIT
    if value in (None, False, ""):
        return 0
    try:
        n = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(n, MAX_LIMIT))


def restore_limit(task: Any) -> int:
    """How many chat messages this task's skill wants restored (0 = off)."""
    meta = getattr(task, "metadata", None)
    if isinstance(meta, dict) and KEY in meta:
        return _as_limit(meta.get(KEY))
    skill = getattr(task, "skill", None)
    cfg = getattr(skill, "config", None)
    if isinstance(cfg, dict) and KEY in cfg:
        return _as_limit(cfg.get(KEY))
    diagram = getattr(skill, "diagram", None)
    if isinstance(diagram, dict) and KEY in diagram:
        return _as_limit(diagram.get(KEY))
    return 0


def _text_of(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, dict):
        if content.get("type") in (None, "text", "markdown"):
            return str(content.get("text") or "").strip()
    return ""


def transcript_messages(rows: List[dict], current_input: str = "", current_msg_id: str = "") -> list:
    """Chat rows (oldest first) -> LangChain messages, without the message
    that started this run (it reaches the skill as its input)."""
    from langchain_core.messages import AIMessage, HumanMessage

    rows = [r for r in rows if isinstance(r, dict)]
    if current_msg_id:
        rows = [r for r in rows if str(r.get("id") or "") != current_msg_id]
    cur = (current_input or "").strip()
    if cur:
        for i in range(len(rows) - 1, -1, -1):
            r = rows[i]
            if str(r.get("role") or "") == "user" and _text_of(r.get("content")) == cur:
                del rows[i]
                break
    out = []
    for r in rows:
        text = _text_of(r.get("content"))
        if not text:
            continue
        role = str(r.get("role") or "")
        if role == "user":
            out.append(HumanMessage(content=text))
        elif role == "agent":
            out.append(AIMessage(content=text))
    return out


def restore_history(task: Any, state: Optional[dict], db_chat_service: Any) -> int:
    """Fill an empty ``state["history"]`` from the run's chat. Returns how many
    messages were restored (0 when off, not a chat run, or nothing to load)."""
    try:
        limit = restore_limit(task)
        if not limit or not isinstance(state, dict) or state.get("history"):
            return 0
        attrs = state.get("attributes") or {}
        chat_id = str(attrs.get("chat_id") or "").strip()
        if not chat_id or db_chat_service is None:
            return 0
        res = db_chat_service.query_messages_by_chat(chatId=chat_id, limit=limit + 1, offset=0, reverse=True)
        if not isinstance(res, dict) or not res.get("success"):
            return 0
        rows = list(reversed(res.get("data") or []))          # oldest first
        msgs = transcript_messages(rows, str(state.get("input") or ""), str(attrs.get("msg_id") or ""))
        msgs = msgs[-limit:]
        if not msgs:
            return 0
        state["history"] = msgs
        logger.info(f"[chat_transcript] restored {len(msgs)} message(s) of chat {chat_id} "
                    f"into '{getattr(task, 'name', '?')}' (fresh run)")
        return len(msgs)
    except Exception as e:
        logger.warning(f"[chat_transcript] could not restore chat history for "
                       f"'{getattr(task, 'name', '?')}': {e}")
        return 0
