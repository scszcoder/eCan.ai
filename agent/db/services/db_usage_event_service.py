"""
Usage Event Database Service

Persistence for billable business outcomes (see ``usage_event_model``).

The only interesting behaviour here is that ``record_event`` is idempotent on
``idempotency_key``: a turn delivered once but observed several times — retries,
drift recovery, duplicate dispatch — must produce exactly one billable row. A
duplicate is a normal, expected outcome, not an error, so it is reported as
"nothing new" rather than raised.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .base_service import BaseService
from ..models.usage_event_model import UsageEvent
from utils.logger_helper import logger_helper as logger


class DBUsageEventService(BaseService):
    """Database service for billable business outcomes."""

    def __init__(self, engine=None, session: Session = None):
        super().__init__(engine, session)

    @classmethod
    def initialize(cls, db_manager) -> 'DBUsageEventService':
        """Initialize the service with a database manager."""
        if db_manager is None:
            raise ValueError("db_manager cannot be None")
        engine = db_manager.get_engine()
        service = cls(engine=engine)
        service.db_manager = db_manager
        return service

    def record_event(self, row: Dict[str, Any]) -> bool:
        """Insert one outcome. True if a NEW row landed, False if already known.

        Idempotency is enforced by the unique index AND checked first. The
        pre-check keeps the common duplicate path cheap and log-quiet; the
        IntegrityError catch is what actually makes it correct when two threads
        deliver the same turn at once.
        """
        key = row.get('idempotency_key')
        if not key:
            raise ValueError("idempotency_key is required")

        try:
            with self.session_scope() as session:
                existing = session.query(UsageEvent.id).filter(
                    UsageEvent.idempotency_key == key
                ).first()
                if existing is not None:
                    return False

                session.add(UsageEvent(**row))
                try:
                    session.flush()
                except IntegrityError:
                    # Lost a race with a concurrent delivery of the same turn.
                    # The other writer recorded it, so the outcome IS counted.
                    session.rollback()
                    logger.debug(
                        f"[UsageEvent] concurrent insert for {key!r}; already counted"
                    )
                    return False
                return True
        except Exception as e:
            logger.error(f"[UsageEvent] record_event failed for {key!r}: {e}")
            return False

    def get_events(
        self,
        *,
        status: Optional[str] = None,
        scenario_code: Optional[str] = None,
        meter_code: Optional[str] = None,
        store_id: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        """Recent events, newest first. Used by shadow-mode analysis and, later,
        by the reporter that ships pending events to the cloud ledger."""
        try:
            with self.session_scope() as session:
                q = session.query(UsageEvent)
                if status:
                    q = q.filter(UsageEvent.status == status)
                if scenario_code:
                    q = q.filter(UsageEvent.scenario_code == scenario_code)
                if meter_code:
                    q = q.filter(UsageEvent.meter_code == meter_code)
                if store_id is not None:
                    q = q.filter(UsageEvent.store_id == store_id)
                if since:
                    q = q.filter(UsageEvent.occurred_at >= since)
                rows = q.order_by(UsageEvent.occurred_at.desc()).limit(limit).all()
                return [self._to_dict(r) for r in rows]
        except Exception as e:
            logger.error(f"[UsageEvent] get_events failed: {e}")
            return []

    def count_by_meter(
        self,
        *,
        since: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Totals per (scenario, meter, store) — the shadow-mode question:
        'how many of these would we have billed?'"""
        from sqlalchemy import func
        try:
            with self.session_scope() as session:
                q = session.query(
                    UsageEvent.scenario_code,
                    UsageEvent.meter_code,
                    UsageEvent.store_id,
                    func.sum(UsageEvent.quantity).label('quantity'),
                    func.count(UsageEvent.id).label('events'),
                )
                if since:
                    q = q.filter(UsageEvent.occurred_at >= since)
                rows = q.group_by(
                    UsageEvent.scenario_code, UsageEvent.meter_code, UsageEvent.store_id
                ).all()
                return [
                    {
                        'scenario_code': r[0],
                        'meter_code': r[1],
                        'store_id': r[2],
                        'quantity': int(r[3] or 0),
                        'events': int(r[4] or 0),
                    }
                    for r in rows
                ]
        except Exception as e:
            logger.error(f"[UsageEvent] count_by_meter failed: {e}")
            return []

    @staticmethod
    def _to_dict(row: UsageEvent) -> Dict[str, Any]:
        return {
            'id': row.id,
            'idempotency_key': row.idempotency_key,
            'scenario_code': row.scenario_code,
            'meter_code': row.meter_code,
            'quantity': row.quantity,
            'owner': row.owner,
            'store_id': row.store_id,
            'agent_id': row.agent_id,
            'task_id': row.task_id,
            'skill_id': row.skill_id,
            'vehicle_id': row.vehicle_id,
            'occurred_at': row.occurred_at.isoformat() if row.occurred_at else None,
            'reported_at': row.reported_at.isoformat() if row.reported_at else None,
            'status': row.status,
            'evidence': row.evidence,
            'cost_basis': row.cost_basis,
            'source': row.source,
        }
