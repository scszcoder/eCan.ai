"""Ships locally-recorded business outcomes (``metering.emit``) to the cloud
ledger — the piece ``db_usage_event_service.get_events`` already anticipated
("used by shadow-mode analysis and, later, by the reporter that ships pending
events to the cloud ledger").

Local recording (metering.py) and cloud reporting are deliberately two steps,
not one: recording happens synchronously on the delivery path and must never
block or fail it; reporting is a network call, batched and retried on its own
schedule, with no opinion on when a reply actually landed.

Failure policy mirrors metering.py: a reporting failure must never raise past
this module. The worst case is a batch stays local and unsent until the next
tick — recoverable by definition, since the server dedupes on
idempotency_key. There is no "give up and mark it dead": under-counting
revenue is a bug to fix, not a state to model.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any, Dict, List, Optional

from utils.logger_helper import logger_helper as logger

LOG_TAG = "[METER-REPORT]"

DEFAULT_BATCH = 100  # server refuses batches over 200; stay well under it
DEFAULT_INTERVAL_SECONDS = 300


def _service():
    try:
        from app_context import AppContext
        db = AppContext.get_ec_db_mgr()
    except Exception as exc:
        logger.debug(f"{LOG_TAG} app context unavailable: {exc}")
        return None
    if db is None:
        return None
    return getattr(db, "usage_event_service", None)


def _account_manager_url() -> str:
    from gui.ipc.w2p_handlers.account_verify_handler import _account_manager_url as _url
    return _url()


def _bearer_token() -> str:
    # Same helper the coupon/verify calls use: it calls ensure_valid_tokens()
    # before reading, unlike the older payment_handler path that shipped with
    # a stale-token bug for exactly this reason.
    from gui.ipc.w2p_handlers.payment_handler import _coupon_bearer_token
    return _coupon_bearer_token()


def _parse_json_field(value: Any) -> Optional[Any]:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return None


def _to_wire_event(row: Dict[str, Any]) -> Dict[str, Any]:
    """Local row -> the server's report_usage_event shape. account_id is
    deliberately omitted: the server resolves the account from the bearer
    token, not from anything the client asserts."""
    return {
        "idempotency_key": row.get("idempotency_key"),
        "scenario_code": row.get("scenario_code"),
        "meter_code": row.get("meter_code"),
        "quantity": row.get("quantity") or 1,
        "occurred_at": row.get("occurred_at"),
        "store_id": row.get("store_id") or None,
        "agent_id": row.get("agent_id") or None,
        "task_id": row.get("task_id") or None,
        "skill_id": row.get("skill_id") or None,
        "vehicle_id": row.get("vehicle_id") or None,
        "evidence": _parse_json_field(row.get("evidence")),
        "cost_basis": _parse_json_field(row.get("cost_basis")),
        "source": row.get("source") or "client",
    }


def _post(url: str, token: str, body: Dict[str, Any]) -> Dict[str, Any]:
    import urllib.error
    import urllib.request

    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read(262144).decode("utf-8", "replace")
            status = resp.status
    except urllib.error.HTTPError as he:
        raw = he.read(4096).decode("utf-8", "replace")
        status = he.code
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        payload = {"raw": raw[:500]}
    if not isinstance(payload, dict):
        payload = {}
    payload["_http_status"] = status
    return payload


def report_pending(limit: int = DEFAULT_BATCH) -> Dict[str, int]:
    """Send up to `limit` unreported local events to the cloud ledger.

    Returns counts for logging/tests; callers should not branch on the
    result. Every failure mode (no DB, no auth, network error, server error)
    leaves the batch local and unsent — never raises.
    """
    result = {"sent": 0, "accepted": 0, "duplicates": 0, "rejected": 0, "left_pending": 0}
    svc = _service()
    if svc is None:
        return result

    try:
        rows = svc.get_unreported_events(limit=limit)
    except Exception as exc:
        logger.warning(f"{LOG_TAG} could not read pending events: {exc}")
        return result
    if not rows:
        return result
    result["sent"] = len(rows)

    url = _account_manager_url()
    if not url:
        logger.debug(f"{LOG_TAG} no ecbAccountManager endpoint configured; leaving {len(rows)} event(s) pending")
        result["left_pending"] = len(rows)
        return result
    token = _bearer_token()
    if not token:
        logger.debug(f"{LOG_TAG} not signed in; leaving {len(rows)} event(s) pending")
        result["left_pending"] = len(rows)
        return result

    by_key = {r["idempotency_key"]: r for r in rows}
    body = {"action": "report_usage_event", "events": [_to_wire_event(r) for r in rows]}
    try:
        payload = _post(url, token, body)
    except Exception as exc:
        logger.warning(f"{LOG_TAG} transport error, leaving {len(rows)} event(s) pending: {exc}")
        result["left_pending"] = len(rows)
        return result

    status = payload.get("_http_status", 0)
    if status >= 400 or not payload.get("success", True):
        logger.warning(f"{LOG_TAG} server rejected the batch (status={status}): {payload.get('message') or payload.get('error')}")
        result["left_pending"] = len(rows)
        return result

    rejected_keys = {str(r.get("idempotency_key")) for r in (payload.get("rejected") or [])}
    accepted = int(payload.get("accepted") or 0)
    duplicates = int(payload.get("duplicates") or 0)
    result["accepted"], result["duplicates"], result["rejected"] = accepted, duplicates, len(rejected_keys)

    # Accepted or duplicate both mean "the cloud has it" — reported_at is a
    # sync marker, not a rating outcome, so either case clears it locally.
    reported_ids = [row["id"] for key, row in by_key.items() if key not in rejected_keys]
    cleared = svc.mark_reported(reported_ids) if reported_ids else 0
    result["left_pending"] = len(rows) - cleared

    logger.info(
        f"{LOG_TAG} sent={len(rows)} accepted={accepted} duplicates={duplicates} "
        f"rejected={len(rejected_keys)} cleared_locally={cleared}"
    )
    if rejected_keys:
        # Surfaced at debug, not warning: 'unknown_meter' on a fresh deploy is
        # expected until the meter catalog is seeded, and self-heals on the
        # next tick — it is not an operator-actionable failure by itself.
        logger.debug(f"{LOG_TAG} rejected keys: {sorted(rejected_keys)}")
    return result


_stop_event: Optional[threading.Event] = None


def _run_loop(interval_seconds: int, stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        try:
            report_pending()
        except Exception as exc:
            # Belt-and-suspenders: report_pending already swallows its own
            # errors, but this loop must survive ANYTHING to keep ticking.
            logger.warning(f"{LOG_TAG} tick failed (non-fatal): {exc}")
        stop_event.wait(interval_seconds)


def start(interval_seconds: int = DEFAULT_INTERVAL_SECONDS) -> threading.Thread:
    """Start the background reporter. Idempotent: calling twice is a no-op on
    the second call, so it is safe to wire into an init path that could
    theoretically run more than once."""
    global _stop_event
    if _stop_event is not None:
        return None  # already running
    _stop_event = threading.Event()
    thread = threading.Thread(
        target=_run_loop,
        args=(interval_seconds, _stop_event),
        name="MeteringReporter",
        daemon=True,
    )
    thread.start()
    logger.info(f"{LOG_TAG} started, interval={interval_seconds}s")
    return thread


def stop() -> None:
    global _stop_event
    if _stop_event is not None:
        _stop_event.set()
        _stop_event = None
