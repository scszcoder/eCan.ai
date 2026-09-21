"""Business-outcome metering — the platform half.

``token_tracker`` answers "what did that call cost us?". This answers "what did
the customer actually get?": one delivered reply, one label printed, one return
handled. Billing on outcomes is what lets an invoice read like the customer's
own business rather than like an LLM bill.

**Shadow mode (2026-09-21).** Events are written locally and nothing is charged.
The cloud ledger and the rating job are separate work; until they exist this is
a local record whose whole job is telling us what a reply really costs before a
price is committed to.

Two rules this module exists to enforce
---------------------------------------
1. **Nothing business-specific lives here.** ``scenario_code`` / ``meter_code``
   arrive from the caller — for live chat, from the site bundle through the
   runner bridge — so the platform never learns what any one site's reply
   means. Adding
   a site name to this file breaks the standing platform-purity rule.
2. **Emission is not reachable from customer-authored code.** A skill selects a
   certified bundle; it never writes the emit call. If a customer-editable code
   node could call this, it could fabricate or suppress billable events, and
   the meter would be worth nothing. Keep this import out of any code-node
   execution surface.

Idempotency
-----------
``idempotency_key`` is the business identity of the outcome, never a timestamp
or a row id. A turn is delivered once but can be observed many times — retries,
drift recovery, duplicate dispatch — and all of those must collapse to one
billable event. A duplicate key is a SUCCESS (the outcome is already recorded),
never an error.

Failure policy
--------------
Metering must never be able to break the thing it measures. Every entry point
swallows its own exceptions and logs; a lost event costs us a fraction of a
cent, while an exception escaping into the delivery path costs a customer their
reply.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Mapping, Optional

from utils.logger_helper import logger_helper as logger

# Emitted on every recorded outcome. Deliberately greppable, and deliberately
# generic — a site bundle keeps its own branded tags.
LOG_TAG = "[METER]"


def _json_or_none(value: Any) -> Optional[str]:
    if value is None:
        return None
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        return None


def _scope() -> dict:
    try:
        from utils.log_scope import get_scope
        return get_scope() or {}
    except Exception:
        return {}


def _service():
    """Usage-event DB service, or None when there is no DB (cloud worker, tests)."""
    try:
        from agent.db.db_manager import ec_db_mgr
    except Exception as exc:
        logger.debug(f"{LOG_TAG} db manager unavailable: {exc}")
        return None
    try:
        from agent.db.services.db_usage_event_service import DBUsageEventService
        return DBUsageEventService.initialize(ec_db_mgr)
    except Exception as exc:
        logger.debug(f"{LOG_TAG} usage-event service unavailable: {exc}")
        return None


def emit(
    scenario_code: str,
    meter_code: str,
    *,
    idempotency_key: str,
    quantity: int = 1,
    evidence: Optional[Mapping[str, Any]] = None,
    cost_basis: Optional[Mapping[str, Any]] = None,
    occurred_at: Optional[datetime] = None,
    owner: Optional[str] = None,
) -> bool:
    """Record one billable business outcome. Returns True if a NEW row landed.

    False means "not newly recorded" and covers both a duplicate key (the
    outcome was already counted — the common, correct case under retry) and a
    failure to record. Callers treat it as informational; nothing downstream
    should branch on it.

    Attribution (store / agent / task / skill / vehicle) is read from the run
    scope, so callers pass only what identifies the OUTCOME.
    """
    if not scenario_code or not meter_code or not idempotency_key:
        logger.warning(
            f"{LOG_TAG} refusing to emit without scenario/meter/idempotency_key "
            f"({scenario_code!r}, {meter_code!r}, {idempotency_key!r})"
        )
        return False

    try:
        sc = _scope()
        store_id = str(sc.get("store_id") or "")
        row = {
            "id": f"ue_{uuid.uuid4().hex[:16]}",
            "idempotency_key": str(idempotency_key),
            "scenario_code": str(scenario_code),
            "meter_code": str(meter_code),
            "quantity": int(quantity) if quantity else 1,
            "owner": owner or str(sc.get("owner") or "") or None,
            "store_id": store_id,
            "agent_id": str(sc.get("agent_id") or "") or None,
            "task_id": str(sc.get("task_id") or "") or None,
            "skill_id": str(sc.get("skill_id") or "") or None,
            "vehicle_id": str(sc.get("vehicle_id") or "") or None,
            "occurred_at": occurred_at or datetime.utcnow(),
            "status": "pending",
            "evidence": _json_or_none(evidence),
            "cost_basis": _json_or_none(cost_basis),
            "source": "client",
        }

        svc = _service()
        if svc is None:
            # No DB: still leave a trace, so a shadow-mode run on a machine
            # without one is not silently unmeasured.
            logger.info(
                f"{LOG_TAG} {scenario_code}.{meter_code} x{row['quantity']} "
                f"store={store_id!r} key={idempotency_key!r} (not persisted: no DB)"
            )
            return False

        created = svc.record_event(row)
        logger.info(
            f"{LOG_TAG} {scenario_code}.{meter_code} x{row['quantity']} "
            f"store={store_id!r} key={idempotency_key!r} "
            f"{'recorded' if created else 'duplicate (already counted)'}"
        )
        return bool(created)
    except Exception as exc:
        # Never let metering break the path it measures.
        logger.warning(f"{LOG_TAG} emit failed (non-fatal): {exc}")
        return False
