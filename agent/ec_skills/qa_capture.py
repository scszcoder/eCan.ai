"""Capture a resolved customer Q&A turn into the ``qa_history`` table.

Called once per *confirmed* customer reply (today from the Feige HOT-PATH-B
``outcome.ok`` branch). It derives the full scope from the live graph ``state``
— store_id / product_id via the same ``scope_from_state`` the RAG lookup uses,
agent_id / task_id / chat_id from ``state['attributes']`` — and appends the
question + answer. It must NEVER raise into the send path, so everything is
guarded; a capture failure is logged and swallowed.

This is the raw feed for the self-learning KB miner; dedup/clustering happens
there, so capture is a straight append.
"""

from typing import Any, Dict, Optional

from utils.logger_helper import logger_helper as logger


def _attr(state: dict, key: str) -> str:
    try:
        v = (state.get("attributes") or {}).get(key)
        return str(v).strip() if v else ""
    except Exception:
        return ""


def _platform_of(store_id: str) -> str:
    # store_id is "<platform>-<name>" (e.g. "douyin-店B") — take the prefix.
    if store_id and "-" in store_id:
        return store_id.split("-", 1)[0]
    return ""


def _resolve_db_mgr(ctx: Any):
    """Reach the running DB manager from the hook context (desktop or worker)."""
    for owner in (getattr(ctx, "mainwin", None), ctx):
        mgr = getattr(owner, "ec_db_mgr", None)
        if mgr is not None:
            return mgr
    return None


def record_qa(state: dict, payload: Dict[str, Any], ctx: Any,
              *, question: Optional[str] = None, answer: Optional[str] = None) -> None:
    """Append one resolved Q&A turn. Safe: logs and returns on any error."""
    try:
        payload = payload or {}
        q = (question if question is not None
             else (payload.get("source_latest_message")
                   or payload.get("latest_message")
                   or payload.get("latest_message_text") or "")).strip()
        a = (answer if answer is not None
             else (payload.get("response_text") or "")).strip()
        if not q and not a:
            return

        # store_id + product_id from the same scope the RAG lookup uses.
        store_id = product_id = ""
        try:
            from knowledge.ks.agent_bridge import scope_from_state
            scope = scope_from_state(state) or {}
            store_id = str(scope.get("store_id") or "").strip()
            product_id = str(scope.get("platform_item_id") or "").strip()
        except Exception as e:
            logger.debug(f"[qa_capture] scope_from_state failed: {e}")

        agent_id = _attr(state, "agent_id") or str(getattr(ctx, "calling_agent_id", "") or "").strip()
        task_id = _attr(state, "task_id")
        chat_id = _attr(state, "chat_id")

        mgr = _resolve_db_mgr(ctx)
        svc = getattr(mgr, "qa_history_service", None) if mgr else None
        if svc is None:
            logger.debug("[qa_capture] no qa_history_service available; skipping")
            return

        res = svc.add_qa(
            store_id=store_id or None,
            agent_id=agent_id or None,
            task_id=task_id or None,
            product_id=product_id or None,
            platform=_platform_of(store_id) or None,
            customer_id=str(payload.get("customer_id") or "").strip() or None,
            customer_name=str(payload.get("customer_name") or "").strip() or None,
            chat_id=chat_id or str(payload.get("talk_id") or "").strip() or None,
            source_msg_id=str(payload.get("source_customer_msg_id")
                              or payload.get("latest_message_msg_id") or "").strip() or None,
            question=q,
            answer=a,
            status="new",
        )
        if res.get("success"):
            logger.info(f"[qa_capture] recorded Q&A id={res.get('id')} store={store_id!r} "
                        f"product={product_id or '-'} agent={agent_id or '-'}")
        else:
            logger.warning(f"[qa_capture] add_qa failed: {res.get('error')}")
    except Exception as e:
        logger.warning(f"[qa_capture] record_qa error (swallowed): {e}")
