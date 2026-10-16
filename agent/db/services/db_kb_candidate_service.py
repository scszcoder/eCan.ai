"""KB Candidate Database Service — mined Q&A awaiting merchant approval."""

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from .base_service import BaseService
from ..models.kb_candidate_model import DBKbCandidate
from utils.logger_helper import logger_helper as logger


_WRITABLE = (
    "owner", "store_id", "product_id", "platform",
    "question", "answer", "rationale", "examples", "confidence", "status",
)


class DBKbCandidateService(BaseService):
    """CRUD for the ``kb_candidate`` table."""

    def __init__(self, engine=None, session: Session = None):
        super().__init__(engine, session)

    def add_candidate(self, **fields) -> Dict[str, Any]:
        data = {k: fields[k] for k in _WRITABLE if k in fields}
        if not (data.get("question") or "").strip() or not (data.get("answer") or "").strip():
            return {"success": False, "id": None, "data": None,
                    "error": "question and answer are both required"}
        data.setdefault("status", "pending")
        return self.create_entity(DBKbCandidate, **data)

    def list_candidates(self, status: str = "pending", owner: Optional[str] = None,
                        limit: int = 500) -> List[Dict[str, Any]]:
        with self.session_scope() as session:
            q = session.query(DBKbCandidate).filter(DBKbCandidate.status == status)
            if owner:
                q = q.filter(DBKbCandidate.owner == owner)
            rows = q.order_by(DBKbCandidate.created_at).limit(limit).all()
            return [r.to_dict() for r in rows]

    def get_candidate(self, candidate_id: str) -> Optional[Dict[str, Any]]:
        with self.session_scope() as session:
            r = session.get(DBKbCandidate, candidate_id)
            return r.to_dict() if r else None

    def set_status(self, candidate_id: str, status: str,
                   promoted_ref: Optional[str] = None,
                   answer: Optional[str] = None) -> Dict[str, Any]:
        """Transition a candidate; optionally store the KB ref / an edited answer."""
        with self.session_scope() as session:
            r = session.get(DBKbCandidate, candidate_id)
            if not r:
                return {"success": False, "error": f"candidate {candidate_id} not found"}
            r.status = status
            if promoted_ref is not None:
                r.promoted_ref = promoted_ref
            if answer is not None:
                r.answer = answer
            session.flush()
            return {"success": True, "id": candidate_id, "data": r.to_dict()}
