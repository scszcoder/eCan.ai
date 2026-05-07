"""Structured Feige customer-message trace logging.

The flood path spans DOM monitors, front-desk pre-dispatch, Q&A workers,
MCP ``send_chat``, and direct browser delivery. Plain prose logs make it
hard to reconstruct one customer's lifecycle, so this module emits compact
JSON lines with a stable prefix:

    [FEIGE-LEDGER] {"stage":"...", "customer":"...", ...}

It is intentionally dependency-light and best-effort. A ledger logging
failure must never affect chat handling.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any

PREFIX = "[FEIGE-LEDGER]"

_LOGGER = logging.getLogger("ecan.feige.ledger")
_APP_LOGGER = logging.getLogger("eCan")
_MAX_TEXT = 180


def parse_jsonish_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def short_text(value: Any, limit: int = _MAX_TEXT) -> str:
    text = "" if value is None else str(value)
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)] + "..."


def normalize_customer(value: Any) -> str:
    text = "" if value is None else str(value).strip()
    if "|" in text:
        prefix = text.split("|", 1)[0].strip()
        if prefix:
            text = prefix
    return text


def customer_from_payload(payload: dict[str, Any]) -> str:
    return normalize_customer(
        payload.get("customer_id")
        or payload.get("customerId")
        or payload.get("customer_name")
        or payload.get("customerName")
        or payload.get("name")
        or ""
    )


def source_msg_id_from_payload(payload: dict[str, Any]) -> str:
    return str(
        payload.get("source_customer_msg_id")
        or payload.get("latest_message_msg_id")
        or payload.get("reply_to_msg_id")
        or payload.get("msg_id")
        or payload.get("message_id")
        or ""
    ).strip()


def latest_text_from_payload(payload: dict[str, Any]) -> str:
    return str(
        payload.get("source_latest_message")
        or payload.get("latest_message")
        or payload.get("latest_message_text")
        or payload.get("last_message")
        or payload.get("last_message_text")
        or payload.get("message")
        or payload.get("text")
        or ""
    ).strip()


def make_trace_id(
    *,
    customer: str = "",
    source_msg_id: str = "",
    latest_message: str = "",
    session_id: str = "",
) -> str:
    basis = "|".join(
        [
            normalize_customer(customer),
            str(source_msg_id or "").strip(),
            short_text(latest_message, 120),
            str(session_id or "").strip(),
        ]
    )
    return hashlib.sha1(basis.encode("utf-8", errors="replace")).hexdigest()[:16]


def payload_trace_fields(payload: dict[str, Any]) -> dict[str, str]:
    customer = customer_from_payload(payload)
    source_msg_id = source_msg_id_from_payload(payload)
    latest_message = latest_text_from_payload(payload)
    session_id = str(payload.get("session_id") or payload.get("sessionId") or "").strip()
    response_text = str(payload.get("response_text") or "").strip()
    return {
        "customer": customer,
        "customer_id": str(
            payload.get("customer_id") or payload.get("customerId") or ""
        ).strip(),
        "customer_name": str(
            payload.get("customer_name") or payload.get("customerName") or ""
        ).strip(),
        "session_id": session_id,
        "source_msg_id": source_msg_id,
        "latest_preview": short_text(latest_message),
        "response_preview": short_text(response_text),
        "trace_id": make_trace_id(
            customer=customer,
            source_msg_id=source_msg_id,
            latest_message=latest_message or response_text,
            session_id=session_id,
        ),
        "turn_key": make_trace_id(
            customer=customer,
            source_msg_id="",
            latest_message=latest_message or response_text,
            session_id=session_id,
        ),
    }


def log_event(stage: str, *, level: int = logging.INFO, **fields: Any) -> None:
    """Emit one structured ledger line.

    Large text fields are summarized. Empty fields are omitted except for
    ``stage``, ``trace_id``, and ``ts_ms``.
    """
    try:
        payload = dict(fields)
        customer = normalize_customer(payload.get("customer") or "")
        if not customer:
            customer = normalize_customer(
                payload.get("customer_id") or payload.get("customer_name") or ""
            )
        source_msg_id = str(payload.get("source_msg_id") or "").strip()
        latest_preview = str(payload.get("latest_preview") or "").strip()
        response_preview = str(payload.get("response_preview") or "").strip()
        session_id = str(payload.get("session_id") or "").strip()
        trace_id = str(payload.get("trace_id") or "").strip() or make_trace_id(
            customer=customer,
            source_msg_id=source_msg_id,
            latest_message=latest_preview or response_preview,
            session_id=session_id,
        )
        turn_key = str(payload.get("turn_key") or "").strip() or make_trace_id(
            customer=customer,
            source_msg_id="",
            latest_message=latest_preview or response_preview,
            session_id=session_id,
        )

        record: dict[str, Any] = {
            "stage": str(stage),
            "trace_id": trace_id,
            "turn_key": turn_key,
            "ts_ms": int(time.time() * 1000),
        }
        if customer:
            record["customer"] = customer
        if source_msg_id:
            record["source_msg_id"] = source_msg_id

        for key, value in payload.items():
            if key in {"trace_id", "turn_key", "customer", "source_msg_id"}:
                continue
            if value is None or value == "":
                continue
            if isinstance(value, str):
                if key.endswith("_text") or key.endswith("_message") or "preview" in key:
                    record[key] = short_text(value)
                else:
                    record[key] = value
            elif isinstance(value, (int, float, bool)):
                record[key] = value
            else:
                record[key] = short_text(value)

        message = json.dumps(record, ensure_ascii=False, sort_keys=True)
        _LOGGER.log(level, "%s %s", PREFIX, message)
        if _APP_LOGGER is not _LOGGER:
            _APP_LOGGER.log(level, "%s %s", PREFIX, message)
    except Exception:
        return


def log_payload(
    stage: str,
    payload: dict[str, Any],
    *,
    level: int = logging.INFO,
    **fields: Any,
) -> None:
    base = payload_trace_fields(payload)
    base.update(fields)
    log_event(stage, level=level, **base)
