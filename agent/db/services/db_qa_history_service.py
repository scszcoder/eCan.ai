"""Q&A History Database Service — the raw feed for the self-learning KB.

Append-only from the serving side (``add_qa``); read + status transitions
from the mining side (``list_by_status`` / ``mark_status``).
"""

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from .base_service import BaseService
from ..models.qa_history_model import DBQaHistory
from utils.logger_helper import logger_helper as logger


# Fields a caller may set on insert (everything else is server-managed).
_WRITABLE = (
    "store_id", "agent_id", "task_id", "product_id", "platform", "owner",
    "customer_id", "customer_name", "chat_id", "source_msg_id",
    "question", "answer", "status",
)


class DBQaHistoryService(BaseService):
    """CRUD for the ``qa_history`` table."""

    def __init__(self, engine=None, session: Session = None):
        super().__init__(engine, session)

    def add_qa(self, **fields) -> Dict[str, Any]:
        """Append one resolved Q&A turn. Returns the standard service dict."""
        data = {k: fields[k] for k in _WRITABLE if k in fields}
        if not (data.get("question") or "").strip() and not (data.get("answer") or "").strip():
            return {"success": False, "id": None, "data": None,
                    "error": "both question and answer are empty"}
        return self.create_entity(DBQaHistory, **data)

    def list_by_status(self, status: str = "new", store_id: Optional[str] = None,
                       owner: Optional[str] = None, limit: int = 500) -> List[Dict[str, Any]]:
        """Rows in a mining-lifecycle state, oldest first."""
        with self.session_scope() as session:
            q = session.query(DBQaHistory).filter(DBQaHistory.status == status)
            if store_id:
                q = q.filter(DBQaHistory.store_id == store_id)
            if owner:
                q = q.filter(DBQaHistory.owner == owner)
            rows = q.order_by(DBQaHistory.created_at).limit(limit).all()
            return [r.to_dict() for r in rows]

    def mark_status(self, ids: List[str], status: str) -> int:
        """Move rows to a new lifecycle state. Returns the count updated."""
        if not ids:
            return 0
        with self.session_scope() as session:
            n = (session.query(DBQaHistory)
                 .filter(DBQaHistory.id.in_(list(ids)))
                 .update({DBQaHistory.status: status}, synchronize_session=False))
            return int(n or 0)

    def count_by_status(self, status: str = "new") -> int:
        with self.session_scope() as session:
            return int(session.query(DBQaHistory)
                       .filter(DBQaHistory.status == status).count())
