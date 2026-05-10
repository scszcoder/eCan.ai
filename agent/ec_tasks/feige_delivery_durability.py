import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from utils.logger_helper import logger_helper as logger

_LOCK = threading.RLock()
_FILE_NAME = "feige_pending_deliveries.json"


def _state_path() -> Path:
    try:
        from config.app_info import app_info
        root = Path(app_info.appdata_path) / "runlogs"
    except Exception:
        root = Path.cwd() / "runlogs"
    root.mkdir(parents=True, exist_ok=True)
    return root / _FILE_NAME


def _atomic_write(path: Path, data: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def _load() -> dict[str, Any]:
    path = _state_path()
    if not path.exists():
        return {"version": 1, "items": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"version": 1, "items": {}}
        items = data.get("items")
        if not isinstance(items, dict):
            data["items"] = {}
        return data
    except Exception:
        return {"version": 1, "items": {}}


def _save(data: dict[str, Any]) -> None:
    _atomic_write(_state_path(), data)


def _is_feige_payload(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    has_customer = bool(
        payload.get("customer_id")
        or payload.get("customerId")
        or payload.get("customer_name")
        or payload.get("customerName")
        or payload.get("name")
    )
    has_turn = bool(
        payload.get("latest_message")
        or payload.get("last_message")
        or payload.get("response_text")
        or payload.get("latest_message_msg_id")
        or payload.get("source_customer_msg_id")
    )
    return has_customer and has_turn


def _delivery_key(payload: dict[str, Any], source: str = "") -> str:
    raw = "|".join([
        str(payload.get("customer_name") or payload.get("customer_id") or payload.get("customerId") or ""),
        str(payload.get("source_customer_msg_id") or payload.get("latest_message_msg_id") or ""),
        str(payload.get("response_text") or payload.get("latest_message") or payload.get("last_message") or ""),
    ])
    return uuid.uuid5(uuid.NAMESPACE_URL, raw).hex


def record_pending_delivery(payload: dict[str, Any], *, source: str, **fields: Any) -> str:
    if not _is_feige_payload(payload):
        return ""
    key = _delivery_key(payload, source)
    now = time.time()
    row = {
        "id": key,
        "source": str(source or ""),
        "payload": dict(payload),
        "created_at": now,
        "updated_at": now,
        "pid": os.getpid(),
        "fields": dict(fields or {}),
    }
    with _LOCK:
        data = _load()
        existing = data["items"].get(key)
        if isinstance(existing, dict):
            row["created_at"] = existing.get("created_at") or now
        data["items"][key] = row
        _save(data)
    return key


def clear_pending_delivery(payload_or_id: Any, *, source: str = "") -> None:
    if isinstance(payload_or_id, str):
        key = payload_or_id
    elif isinstance(payload_or_id, dict):
        key = _delivery_key(payload_or_id, source)
    else:
        return
    with _LOCK:
        data = _load()
        if data["items"].pop(key, None) is not None:
            _save(data)


def snapshot_pending_deliveries() -> list[dict[str, Any]]:
    with _LOCK:
        items = _load().get("items", {})
        if not isinstance(items, dict):
            return []
        return [dict(row) for row in items.values() if isinstance(row, dict)]


def abort_pending_from_previous_process(reason: str = "previous_process_died_mid_delivery") -> int:
    rows = snapshot_pending_deliveries()
    if not rows:
        return 0
    aborted = 0
    for row in rows:
        payload = row.get("payload") if isinstance(row, dict) else None
        if not isinstance(payload, dict):
            continue
        try:
            from agent.ec_skills.browser_use_extension.hooks.external.feige_chat.trace_ledger import log_payload
            log_payload(
                "delivery_aborted_shutdown",
                payload,
                reason=reason,
                durability_source=row.get("source") or "",
                durability_pid=row.get("pid"),
                durability_created_at=row.get("created_at"),
                durability_id=row.get("id") or "",
            )
        except Exception:
            pass
        aborted += 1
    with _LOCK:
        _save({"version": 1, "items": {}})
    if aborted:
        logger.warning(f"[FEIGE-DURABILITY] terminal-aborted pending delivery record(s) from previous process: {aborted}")
    return aborted
