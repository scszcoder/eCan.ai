"""KB Candidate IPC handlers (``kb.*``) — the merchant's approval gate.

The self-learning miner writes mined Q&A to ``kb_candidate`` (status 'pending')
and emails the merchant. These handlers back the in-app review: list the
pending candidates, and approve (promote into the knowledge base) or reject
them. Approval is the ONLY path a mined answer enters the KB.

Promotion writes the approved Q&A into the retrievable product-knowledge store
as a tenant-default FAQ policy (``knowledge.ks.service.save_policy``), so the
customer-service agent's ``rag_query`` serves it immediately.
"""
from typing import Any, Callable, Dict, Optional

from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response
from utils.logger_helper import logger_helper as logger


def _svc():
    """The kb_candidate DB service on the running app."""
    from app_context import AppContext
    mw = AppContext.get_main_window()
    if mw is None or getattr(mw, "ec_db_mgr", None) is None:
        raise RuntimeError("app not ready")
    return mw.ec_db_mgr.kb_candidate_service


def _call(request: IPCRequest, code: str, fn: Callable[[], Any]) -> IPCResponse:
    try:
        return create_success_response(request, fn())
    except ValueError as e:
        return create_error_response(request, 'INVALID_PARAMS', str(e))
    except Exception as e:
        logger.error(f"[KB] {code} failed: {e}", exc_info=True)
        return create_error_response(request, code, str(e))


@IPCHandlerRegistry.handler('kb.listCandidates')
def handle_list_candidates(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    p = params or {}
    return _call(request, 'KB_LIST_CANDIDATES_ERROR',
                 lambda: {'candidates': _svc().list_candidates(
                     status=(p.get('status') or 'pending'),
                     owner=(p.get('owner') or None),
                     limit=int(p.get('limit') or 500))})


@IPCHandlerRegistry.handler('kb.reviewCandidate')
def handle_review_candidate(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    def run():
        p = params or {}
        cid = p.get('id') or p.get('candidate_id')
        decision = (p.get('decision') or '').strip().lower()
        if not cid:
            raise ValueError("missing parameter: id")
        if decision not in ('approve', 'reject'):
            raise ValueError("decision must be 'approve' or 'reject'")

        svc = _svc()
        cand = svc.get_candidate(cid)
        if not cand:
            raise ValueError(f"candidate {cid} not found")

        if decision == 'reject':
            svc.set_status(cid, 'rejected')
            return {'id': cid, 'status': 'rejected'}

        # approve -> promote into the KB as a tenant-default FAQ policy
        answer = (p.get('answer') or cand.get('answer') or '').strip()
        question = (cand.get('question') or '').strip()
        if not question or not answer:
            raise ValueError("candidate has empty question/answer")

        from knowledge.ks.service import get_service
        topic = f"FAQ: {question[:100]}"
        text = f"问：{question}\n答：{answer}"
        pol = get_service().save_policy(topic=topic, text=text, store_id=None, title="FAQ")
        ref = (pol or {}).get('id') if isinstance(pol, dict) else None

        svc.set_status(cid, 'promoted', promoted_ref=ref,
                       answer=(answer if p.get('answer') else None))
        logger.info(f"[KB] candidate {cid} approved -> promoted to KB policy {ref}")
        return {'id': cid, 'status': 'promoted', 'kb_ref': ref}

    return _call(request, 'KB_REVIEW_CANDIDATE_ERROR', run)
