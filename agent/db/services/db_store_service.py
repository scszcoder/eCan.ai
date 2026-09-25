"""Store Database Service — local store definitions (see ``store_model``)."""

import json
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy.orm import Session

from .base_service import BaseService
from ..models.store_model import Store
from utils.logger_helper import logger_helper as logger

_EDITABLE = ("name", "platform", "store_urls", "browser_profile_id", "owner", "status", "source")


def _row(s: Store) -> Dict[str, Any]:
    d = s.to_dict()
    try:
        d["store_urls"] = json.loads(s.store_urls) if s.store_urls else []
    except (TypeError, ValueError):
        d["store_urls"] = []
    return d


class DBStoreService(BaseService):
    """CRUD for the ``store`` table, keyed by ``store_id``."""

    def __init__(self, engine=None, session: Session = None):
        super().__init__(engine, session)

    @classmethod
    def initialize(cls, db_manager) -> 'DBStoreService':
        if db_manager is None:
            raise ValueError("db_manager cannot be None")
        service = cls(engine=db_manager.get_engine())
        service.db_manager = db_manager
        return service

    def list_stores(self, include_archived: bool = False) -> List[Dict[str, Any]]:
        with self.session_scope() as session:
            q = session.query(Store)
            if not include_archived:
                q = q.filter(Store.status == 'active')
            return [_row(s) for s in q.order_by(Store.created_at).all()]

    def get_store(self, store_id: str) -> Optional[Dict[str, Any]]:
        with self.session_scope() as session:
            s = session.query(Store).filter(Store.store_id == store_id).first()
            return _row(s) if s else None

    def upsert_store(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create the store, or update the given fields of an existing one."""
        sid = str(data.get("store_id") or "").strip()
        if not sid:
            raise ValueError("store_id is required")
        fields = {k: data[k] for k in _EDITABLE if k in data}
        if "store_urls" in fields and not isinstance(fields["store_urls"], str):
            fields["store_urls"] = json.dumps([str(u) for u in (fields["store_urls"] or [])],
                                              ensure_ascii=False)
        with self.session_scope() as session:
            s = session.query(Store).filter(Store.store_id == sid).first()
            if s is None:
                s = Store(store_id=sid, **fields)
                session.add(s)
            else:
                for k, v in fields.items():
                    setattr(s, k, v)
            session.flush()
            return _row(s)

    def set_status(self, store_id: str, status: str) -> bool:
        with self.session_scope() as session:
            s = session.query(Store).filter(Store.store_id == store_id).first()
            if s is None:
                return False
            s.status = status
            return True

    def mark_cloud_synced(self, store_id: str) -> None:
        with self.session_scope() as session:
            s = session.query(Store).filter(Store.store_id == store_id).first()
            if s is not None:
                s.cloud_synced_at = datetime.now(timezone.utc)

    def ensure_stores(self, rows: Iterable[Dict[str, Any]], source: str) -> int:
        """Create a record for each store id not yet known; never overwrite. Returns count created."""
        created = 0
        with self.session_scope() as session:
            known = {sid for (sid,) in session.query(Store.store_id).all()}
            for r in rows:
                sid = str(r.get("store_id") or "").strip()
                if not sid or sid in known:
                    continue
                session.add(Store(store_id=sid, name=str(r.get("name") or sid),
                                  platform=str(r.get("platform") or ""),
                                  store_urls=json.dumps(r.get("store_urls") or [], ensure_ascii=False),
                                  status=str(r.get("status") or "active"), source=source))
                known.add(sid)
                created += 1
        if created:
            logger.info(f"[StoreService] seeded {created} store record(s) from {source}")
        return created
