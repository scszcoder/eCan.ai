from __future__ import annotations

import copy
import hashlib
import json
import re
from typing import Any

DATA_URI_IMAGE_RE = re.compile(r"data:image/[A-Za-z0-9.+-]+;base64,[A-Za-z0-9+/=]+")
DATA_URI_FIELD_RE = re.compile(
    r'"data_uri"\s*:\s*"data:image/[^"\\]*(?:\\.[^"\\]*)*"\s*,?\s*'
)
DEFAULT_STRING_PREVIEW_CHARS = 240
DEFAULT_MAX_STRING_CHARS = 4000


def data_uri_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()


def data_uri_byte_len(value: str) -> int:
    if not isinstance(value, str):
        return 0
    payload = value.split(",", 1)[1] if "," in value else value
    return max(0, (len(payload) * 3) // 4)


def data_uri_mime_type(value: str) -> str:
    if not isinstance(value, str) or not value.startswith("data:"):
        return ""
    head = value.split(",", 1)[0]
    return head[5:].split(";", 1)[0]


def compact_data_uri_marker(value: str, *, image_ref: str | None = None) -> dict[str, Any]:
    digest = data_uri_digest(value)
    marker: dict[str, Any] = {
        "data_uri_stripped": True,
        "mime_type": data_uri_mime_type(value),
        "byte_len": data_uri_byte_len(value),
        "sha256": digest,
    }
    if image_ref:
        marker["image_ref"] = image_ref
    return marker


def sanitize_text_data_uris(text: str, *, preview_chars: int = DEFAULT_STRING_PREVIEW_CHARS) -> str:
    if not isinstance(text, str) or "data:image/" not in text:
        return text

    def _replace(match: re.Match[str]) -> str:
        uri = match.group(0)
        digest = data_uri_digest(uri)
        return (
            f"[image data_uri stripped: mime={data_uri_mime_type(uri) or 'image/*'} "
            f"bytes~={data_uri_byte_len(uri)} sha256={digest[:16]}]"
        )

    stripped = DATA_URI_FIELD_RE.sub("", text)
    stripped = DATA_URI_IMAGE_RE.sub(_replace, stripped)
    if len(stripped) > preview_chars and len(text) > preview_chars * 4:
        return stripped[:preview_chars] + f"... [text truncated, original_len={len(text)}]"
    return stripped


def sanitize_data_uris(value: Any, *, max_string_chars: int = DEFAULT_MAX_STRING_CHARS, _depth: int = 0) -> Any:
    if _depth > 12:
        return f"<{type(value).__name__}: max_depth>"
    if value is None or isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, str):
        if "data:image/" not in value:
            return value
        text = sanitize_text_data_uris(value)
        if len(text) > max_string_chars:
            digest = hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()
            return (
                text[:DEFAULT_STRING_PREVIEW_CHARS]
                + f"... [string truncated: original_len={len(text)} sha256={digest[:16]}]"
            )
        return text
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            key_s = str(key)
            if key_s == "data_uri" and isinstance(item, str) and item.startswith("data:image/"):
                out.update(compact_data_uri_marker(item))
                continue
            out[key_s] = sanitize_data_uris(item, max_string_chars=max_string_chars, _depth=_depth + 1)
        return out
    if isinstance(value, (list, tuple, set)):
        return [sanitize_data_uris(v, max_string_chars=max_string_chars, _depth=_depth + 1) for v in value]
    if hasattr(value, "content"):
        try:
            cloned = copy.copy(value)
            cloned.content = sanitize_data_uris(getattr(value, "content"), max_string_chars=max_string_chars, _depth=_depth + 1)
            return cloned
        except Exception:
            pass
    if hasattr(value, "model_dump") and callable(getattr(value, "model_dump")):
        try:
            return sanitize_data_uris(value.model_dump(mode="python"), max_string_chars=max_string_chars, _depth=_depth + 1)
        except Exception:
            pass
    if hasattr(value, "__dict__"):
        try:
            return sanitize_data_uris(vars(value), max_string_chars=max_string_chars, _depth=_depth + 1)
        except Exception:
            pass
    return sanitize_data_uris(str(value), max_string_chars=max_string_chars, _depth=_depth + 1)


def sanitize_json_text(text: str) -> str:
    if not isinstance(text, str) or "data:image/" not in text:
        return text
    try:
        parsed = json.loads(text)
    except Exception:
        return sanitize_text_data_uris(text, preview_chars=DEFAULT_MAX_STRING_CHARS)
    sanitized = sanitize_data_uris(parsed)
    try:
        return json.dumps(sanitized, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        return sanitize_text_data_uris(text, preview_chars=DEFAULT_MAX_STRING_CHARS)


def data_uri_stats(value: Any, *, _seen: set[int] | None = None) -> dict[str, int]:
    if _seen is None:
        _seen = set()
    oid = id(value)
    if oid in _seen:
        return {"count": 0, "chars": 0, "bytes": 0, "max_string_len": 0}
    _seen.add(oid)
    stats = {"count": 0, "chars": 0, "bytes": 0, "max_string_len": 0}

    def _merge(other: dict[str, int]) -> None:
        stats["count"] += other.get("count", 0)
        stats["chars"] += other.get("chars", 0)
        stats["bytes"] += other.get("bytes", 0)
        stats["max_string_len"] = max(stats["max_string_len"], other.get("max_string_len", 0))

    if isinstance(value, str):
        stats["max_string_len"] = len(value)
        if "data:image/" in value:
            uris = DATA_URI_IMAGE_RE.findall(value)
            stats["count"] += len(uris)
            stats["chars"] += sum(len(u) for u in uris)
            stats["bytes"] += sum(data_uri_byte_len(u) for u in uris)
        return stats
    if isinstance(value, dict):
        for item in value.values():
            _merge(data_uri_stats(item, _seen=_seen))
        return stats
    if isinstance(value, (list, tuple, set)):
        for item in value:
            _merge(data_uri_stats(item, _seen=_seen))
        return stats
    if hasattr(value, "content"):
        return data_uri_stats(getattr(value, "content", None), _seen=_seen)
    if hasattr(value, "__dict__"):
        try:
            return data_uri_stats(vars(value), _seen=_seen)
        except Exception:
            return stats
    return stats
