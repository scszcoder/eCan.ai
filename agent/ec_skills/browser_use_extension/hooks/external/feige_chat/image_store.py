from __future__ import annotations

import os
import logging
import threading
import time
import uuid
from typing import Any

from utils.data_uri_sanitizer import (
    compact_data_uri_marker,
    data_uri_byte_len,
    data_uri_digest,
    data_uri_mime_type,
)

logger = logging.getLogger("eCan")

try:
    DEFAULT_IMAGE_REF_TTL_S = max(1.0, float(os.getenv("ECAN_FEIGE_IMAGE_REF_TTL_S", "600")))
except Exception:
    DEFAULT_IMAGE_REF_TTL_S = 600.0
try:
    MAX_IMAGE_REFS = max(1, int(os.getenv("ECAN_FEIGE_IMAGE_REF_MAX", "256")))
except Exception:
    MAX_IMAGE_REFS = 256

_LOCK = threading.RLock()
_STORE: dict[str, dict[str, Any]] = {}


def _prune_locked(now: float | None = None) -> None:
    now = time.time() if now is None else now
    expired = [ref for ref, row in _STORE.items() if float(row.get("expires_at") or 0.0) <= now]
    for ref in expired:
        _STORE.pop(ref, None)
    evicted = 0
    if len(_STORE) <= MAX_IMAGE_REFS:
        if expired:
            logger.info(
                "[data-uri-mitigation] image_ref_store_pruned "
                "expired=%d evicted=0 store_size=%d max_refs=%d",
                len(expired),
                len(_STORE),
                MAX_IMAGE_REFS,
            )
        return
    rows = sorted(_STORE.items(), key=lambda kv: float(kv[1].get("created_at") or 0.0))
    for ref, _row in rows[: max(0, len(_STORE) - MAX_IMAGE_REFS)]:
        _STORE.pop(ref, None)
        evicted += 1
    if expired or evicted:
        logger.info(
            "[data-uri-mitigation] image_ref_store_pruned "
            "expired=%d evicted=%d store_size=%d max_refs=%d",
            len(expired),
            evicted,
            len(_STORE),
            MAX_IMAGE_REFS,
        )


def put_data_uri(
    data_uri: str,
    *,
    url: str = "",
    alt: str = "",
    ttl_s: float = DEFAULT_IMAGE_REF_TTL_S,
) -> dict[str, Any]:
    if not isinstance(data_uri, str) or not data_uri.startswith("data:image/"):
        return {}
    now = time.time()
    digest = data_uri_digest(data_uri)
    image_ref = f"feige-img:{uuid.uuid4().hex}"
    row = {
        "image_ref": image_ref,
        "data_uri": data_uri,
        "url": str(url or ""),
        "alt": str(alt or ""),
        "mime_type": data_uri_mime_type(data_uri),
        "byte_len": data_uri_byte_len(data_uri),
        "sha256": digest,
        "created_at": now,
        "expires_at": now + max(1.0, float(ttl_s or DEFAULT_IMAGE_REF_TTL_S)),
    }
    with _LOCK:
        _prune_locked(now)
        _STORE[image_ref] = row
        store_size = len(_STORE)
    logger.info(
        "[data-uri-mitigation] image_ref_stored "
        "ref_suffix=%s mime=%s bytes=%s ttl_s=%.0f store_size=%d max_refs=%d",
        image_ref[-12:],
        row.get("mime_type") or "",
        row.get("byte_len") or 0,
        max(1.0, float(ttl_s or DEFAULT_IMAGE_REF_TTL_S)),
        store_size,
        MAX_IMAGE_REFS,
    )
    return dict(row)


def get_data_uri(image_ref: str) -> str | None:
    ref = str(image_ref or "")
    if not ref:
        return None
    now = time.time()
    with _LOCK:
        row = _STORE.get(ref)
        if not row:
            logger.warning(
                "[data-uri-mitigation] image_ref_resolve_miss ref_suffix=%s store_size=%d",
                ref[-12:],
                len(_STORE),
            )
            return None
        if float(row.get("expires_at") or 0.0) <= now:
            _STORE.pop(ref, None)
            logger.warning(
                "[data-uri-mitigation] image_ref_resolve_expired ref_suffix=%s store_size=%d",
                ref[-12:],
                len(_STORE),
            )
            return None
        data_uri = row.get("data_uri")
        logger.info(
            "[data-uri-mitigation] image_ref_resolved "
            "ref_suffix=%s mime=%s bytes=%s store_size=%d",
            ref[-12:],
            row.get("mime_type") or "",
            row.get("byte_len") or 0,
            len(_STORE),
        )
    return data_uri if isinstance(data_uri, str) else None


def compact_attachment(entry: dict[str, Any]) -> dict[str, Any]:
    out = dict(entry or {})
    data_uri = out.pop("data_uri", None)
    if isinstance(data_uri, str) and data_uri.startswith("data:image/"):
        row = put_data_uri(
            data_uri,
            url=str(out.get("url") or ""),
            alt=str(out.get("alt") or ""),
        )
        marker = compact_data_uri_marker(data_uri, image_ref=row.get("image_ref"))
        out.update(marker)
        out.setdefault("kind", "image")
        out["mime_type"] = row.get("mime_type") or marker.get("mime_type")
        out["byte_len"] = row.get("byte_len") or marker.get("byte_len")
        out["sha256"] = row.get("sha256") or marker.get("sha256")
    return out


def compact_attachments(attachments: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not attachments:
        return []
    out: list[dict[str, Any]] = []
    for entry in attachments:
        if isinstance(entry, dict):
            out.append(compact_attachment(entry))
    return out


def stats() -> dict[str, Any]:
    with _LOCK:
        _prune_locked()
        return {
            "count": len(_STORE),
            "total_bytes": sum(int(row.get("byte_len") or 0) for row in _STORE.values()),
        }


def clear_for_tests() -> None:
    with _LOCK:
        _STORE.clear()


__all__ = [
    "compact_attachment",
    "compact_attachments",
    "clear_for_tests",
    "get_data_uri",
    "put_data_uri",
    "stats",
]
