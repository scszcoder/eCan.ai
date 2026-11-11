"""Fleet, store, transfer, turn, pod and usage calls on the intl edition.

On CN these are ``ecbAccountManager`` actions: ``POST <graphql host>/ecbAccountManager``
with ``{"action": ..., "input": {...}}``. AppSync has no such route, so on intl
every one of them came back HTTP 404 ``UnknownOperationException``. The intl
backend serves the same actions as AppSync GraphQL fields (Cognito user-pool
auth, ``AWSJSON`` in and out), and this module is the one place that maps
between the two.

``call`` answers exactly what the CN route would have: ``(http_like_status,
cn_shaped_body)``. That lets every caller keep its existing status and
``success`` checks, and the CN path below each call site stays untouched.

Three rules the server relies on:

* **Never send an owner.** The server takes it from the verified token's
  ``email`` claim and strips ``input.owner`` anyway. A client-supplied owner is
  a claim, not a fact.
* **Never send the internal fleet token.** On intl that is a worker credential
  for a different door; a desktop always uses the signed-in session (the
  Cognito IdToken, raw, which is what ``_http_auth_header`` produces on intl).
* **Never log the payload.** A store report carries a descriptor that can hold
  seller details. Log the action, field, status and error code only.
"""

from __future__ import annotations

import copy
import json
import os
import re
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from utils.logger_helper import logger_helper as logger

LOG_TAG = "[IntlFleet]"

NOT_AVAILABLE_ERROR = "not_available_on_edition"
NOT_AVAILABLE_MSG = "Store placement is not available on this edition yet"

# Worker/pod actions. On AWS they live on the internal REST door of the billing
# jobs Lambda, not on AppSync, and must never get an AppSync twin.
WORKER_ONLY = frozenset({
    "vehicle_register", "vehicle_offline", "turn_claim", "turn_heartbeat",
    "turn_done", "fleet_scale_signal", "turn_route", "fleet_gc", "turn_send",
})
WORKER_ONLY_MSG = "This operation is only available to cloud workers"

# cn_action -> (kind, field, input_required)
AWS_OPS: Dict[str, Tuple[str, str, bool]] = {
    "store_report": ("mutation", "reportStores", True),
    "store_list": ("query", "getStores", False),
    "store_assign": ("mutation", "assignStore", True),
    "store_define": ("mutation", "defineStore", True),
    "store_claim": ("mutation", "claimStore", True),
    "store_archive": ("mutation", "archiveStore", True),
    "store_delete": ("mutation", "deleteStore", True),
    "turn_enqueue": ("mutation", "enqueueTurn", True),
    "transfer_create": ("mutation", "createTransfer", True),
    "transfer_list": ("query", "listTransfers", False),
    "transfer_get": ("query", "getTransfer", True),
    "transfer_update": ("mutation", "updateTransfer", True),
    "transfer_upload_url": ("mutation", "transferUploadUrl", True),
    "transfer_download_url": ("mutation", "transferDownloadUrl", True),
    "transfer_finish": ("mutation", "finishTransfer", True),
    "pod_list": ("query", "getPods", False),
    "pod_save": ("mutation", "savePod", True),
    "pod_delete": ("mutation", "deletePod", True),
    "fleet_status": ("query", "getFleetStatus", False),
}

USAGE_FIELD = "reportUsageEvents"
USAGE_DOCUMENT = (
    "mutation ReportUsageEvents($input: ReportUsageEventsInput!) { "
    "reportUsageEvents(input: $input) { accepted duplicates rejected { idempotency_key reason } } }"
)

# What the CN route answers for the same refusal codes. Compared lower-case:
# AWS spells TOO_MANY_TRANSFERS and INVALID_TRANSITION in upper case.
_CODE_STATUS = {
    "not_found": 404,
    "pod_limit": 409,
    "turn_id_taken": 409,
    "too_many_transfers": 409,
    "invalid_transition": 409,
    "unauthenticated": 401,
    "account_insufficient": 403,
}
_CODE_PREFIX = re.compile(r"^([A-Za-z_]+): (.*)$", re.DOTALL)

# The AWS turnMaxQueuedSeconds default, so the backlog warning still works.
_DEFAULT_MAX_QUEUED_SECONDS = 900
_ZERO_LLM30D = {"calls": 0, "tokens": 0, "costFen": 0}

_session_lock = threading.Lock()
_session_obj = None
_internal_token_warned = False


def use_appsync() -> bool:
    """True on the intl edition. The single switch; tests patch this."""
    from utils.app_env import is_intl
    return is_intl()


def appsync_http_request(*args, **kwargs):
    """``cloud_api.appsync_http_request``, imported late (it is a heavy module).

    A module-level name so tests can patch it here.
    """
    from agent.cloud_api.cloud_api import appsync_http_request as _request
    return _request(*args, **kwargs)


def _session():
    global _session_obj
    with _session_lock:
        if _session_obj is None:
            import requests
            _session_obj = requests.Session()
        return _session_obj


def _token() -> str:
    global _internal_token_warned
    from agent.cloud_api.turn_queue import ENV_TOKEN, _session_bearer_token

    if (os.environ.get(ENV_TOKEN) or "").strip() and not _internal_token_warned:
        _internal_token_warned = True
        logger.warning(
            f"{LOG_TAG} {ENV_TOKEN} is set on an intl desktop; ignoring it. It is a "
            f"worker credential for a different door; this client uses the session."
        )
    return _session_bearer_token()


def _document(kind: str, field: str, required: bool) -> str:
    t = "AWSJSON!" if required else "AWSJSON"
    name = field[0].upper() + field[1:]
    return f"{kind} {name}($input: {t}) {{ {field}(input: $input) }}"


def _refusal(status: int, error: str, message: str) -> Tuple[int, Dict[str, Any]]:
    return status, {"success": False, "error": error, "message": message}


def _classify_errors(errors: List[Any]) -> Tuple[int, Dict[str, Any]]:
    """GraphQL ``errors`` -> what the CN route would have answered."""
    first = errors[0] if errors and isinstance(errors[0], dict) else {}
    error_type = str(first.get("errorType") or "")
    message = str(first.get("message") or "")

    if error_type == "UnauthorizedException":
        return _refusal(401, "unauthorized", message or "The session was rejected; sign in again.")
    if error_type == "UnknownOperationException" or "FieldUndefined" in message:
        return _refusal(503, NOT_AVAILABLE_ERROR, NOT_AVAILABLE_MSG)
    if error_type == "RequestError":
        return _refusal(502, "transport_error", message or "request failed")
    return _refusal(400, error_type or "graphql_error", message or "request refused")


def _classify_value(value: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    """A field value -> CN shape. A successful result never has ``success``."""
    if value.get("success") is not False:
        return 200, {"success": True, **value}

    raw = str(value.get("error") or "")
    if raw.strip().upper() == "ACCOUNT INSUFFICIENT":
        return _refusal(403, "account_insufficient", raw)
    match = _CODE_PREFIX.match(raw)
    if match:
        code, message = match.group(1), match.group(2)
    else:
        code, message = "", raw
    status = _CODE_STATUS.get(code.lower(), 400) if code else 400
    return _refusal(status, code or "refused", message or "request refused")


def _classify(jresp: Any, field: str) -> Tuple[int, Dict[str, Any]]:
    if not isinstance(jresp, dict):
        return _refusal(502, "bad_response", f"{field} returned an unexpected response")

    data = jresp.get("data")
    value = data.get(field) if isinstance(data, dict) else None
    errors = jresp.get("errors")
    if value is None:
        if isinstance(errors, list) and errors:
            return _classify_errors(errors)
        return _refusal(502, "empty_response", f"{field} returned no data")

    # AWSJSON can arrive encoded twice (a JSON string holding a JSON string).
    for _ in range(2):
        if not isinstance(value, str):
            break
        try:
            value = json.loads(value)
        except Exception:
            return _refusal(502, "bad_response", f"{field} returned non-JSON")
    if not isinstance(value, dict):
        return _refusal(502, "bad_response",
                        f"{field} returned an unexpected shape ({type(value).__name__})")
    return _classify_value(value)


def _prepare_input(action: str, payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    body = copy.deepcopy(payload) if isinstance(payload, dict) else {}
    body.pop("owner", None)
    if action == "pod_save" and "taskId" in body and "task_id" not in body:
        body["task_id"] = body.pop("taskId")
    return body


def _post_process(action: str, data: Dict[str, Any]) -> Dict[str, Any]:
    if action == "store_list":
        # AWS has no 30-day LLM cost yet; StoreDetail reads llm30d?.costFen.
        for row in data.get("stores") or []:
            if isinstance(row, dict) and not row.get("llm30d"):
                row["llm30d"] = dict(_ZERO_LLM30D)
    elif action == "fleet_status":
        queue = data.get("queue")
        if isinstance(queue, dict) and "maxQueuedSeconds" not in queue:
            queue["maxQueuedSeconds"] = _DEFAULT_MAX_QUEUED_SECONDS
    return data


def _log_result(action: str, field: str, status: int, data: Dict[str, Any]) -> None:
    if status < 400:
        logger.info(f"{LOG_TAG} {action} -> {field} status={status}")
    else:
        logger.warning(f"{LOG_TAG} {action} -> {field} status={status} error={data.get('error')}")


def call(action: str, payload: Optional[Dict[str, Any]],
         timeout: float = 20.0) -> Tuple[int, Dict[str, Any]]:
    """Run one CN ecbAccountManager action against AppSync.

    Returns ``(http_like_status, cn_shaped_body)``, exactly what the CN route
    would have answered:

      success  -> (200, {"success": True, **result})
      refusal  -> (4xx, {"success": False, "error": code, "message": msg})
      no op    -> (503, {"success": False, "error": "not_available_on_edition", "message": NOT_AVAILABLE_MSG})
      no token -> (401, {"success": False, "error": "unauthorized", "message": "Not signed in"})

    Never raises for server/transport problems. Raises ValueError for an action
    it does not know.
    """
    if action in WORKER_ONLY:
        logger.warning(f"{LOG_TAG} refused worker-only action {action} on a desktop")
        return _refusal(403, "worker_only", WORKER_ONLY_MSG)
    if action not in AWS_OPS:
        raise ValueError(f"no AppSync operation for action {action!r}")

    kind, field, required = AWS_OPS[action]
    token = _token()
    if not token:
        return _refusal(401, "unauthorized", "Not signed in")

    body = _prepare_input(action, payload)
    jresp = appsync_http_request(
        _document(kind, field, required), _session(), token, None, timeout,
        variables={"input": json.dumps(body)},
    )
    status, data = _classify(jresp, field)
    if status < 400:
        data = _post_process(action, data)
    _log_result(action, field, status, data)
    return status, data


def _aws_datetime(value: Any) -> Any:
    """``AWSDateTime`` needs an offset; local rows are naive UTC.

    An offset-less timestamp makes AppSync reject the whole request, so send
    ``YYYY-MM-DDTHH:MM:SS.sssZ``. A value that does not parse is passed through.
    """
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str) and value.strip():
        try:
            dt = datetime.fromisoformat(value.strip())
        except ValueError:
            return value
    else:
        return value
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)
    return f"{dt:%Y-%m-%dT%H:%M:%S}.{dt.microsecond // 1000:03d}Z"


def _usage_event(event: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(event)
    # The server resolves the account from the token; a mismatch is refused.
    out.pop("account_id", None)
    out["occurred_at"] = _aws_datetime(out.get("occurred_at"))
    for key in ("evidence", "cost_basis"):
        value = out.get(key)
        if value is not None and not isinstance(value, str):
            out[key] = json.dumps(value)
    try:
        out["quantity"] = int(out.get("quantity") or 1)
    except (TypeError, ValueError):
        out["quantity"] = 1
    return out


def report_usage_events(events: List[Dict[str, Any]],
                        timeout: float = 20.0) -> Tuple[int, Dict[str, Any]]:
    """``report_usage_event`` via the typed ``reportUsageEvents`` mutation.

    Same return contract as ``call``. The input is a real input object, not
    AWSJSON, so ``variables["input"]`` is a dict.
    """
    token = _token()
    if not token:
        return _refusal(401, "unauthorized", "Not signed in")

    variables = {"input": {"events": [_usage_event(e) for e in events or []]}}
    jresp = appsync_http_request(USAGE_DOCUMENT, _session(), token, None, timeout,
                                 variables=variables)
    status, data = _classify(jresp, USAGE_FIELD)
    _log_result("report_usage_event", USAGE_FIELD, status, data)
    return status, data
