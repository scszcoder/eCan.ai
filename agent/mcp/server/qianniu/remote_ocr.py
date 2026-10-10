"""千牛 screen OCR on the server's GPU (CN GraphQL ``ocrImage``), local CPU as fallback.

Local RapidOCR took 6-7 s per read on the alpha customer's old PC -- the 千牛
throughput bottleneck. The CN backend runs OCR on a GPU behind the same
authenticated GraphQL (billed to the signed-in account), so every 千牛 read goes
there first. Local OCR is used only when the remote call keeps failing:

* each read tries the server ``_TRIES_PER_READ`` times;
* after ``_FAILED_READS_TO_BACK_OFF`` reads in a row fail remotely, reads go
  local for ``_BACKOFF_S``, then the server is tried again;
* "OCR is not enabled on this server" backs off for ``_DISABLED_BACKOFF_S``.

CN only for now: ``ocrImage`` is on the CN schema (the AWS AppSync schema does
not have it), so intl builds use local OCR. ``ECAN_QIANNIU_REMOTE_OCR=0`` turns
the remote path off.

Results come back as RapidOCR-shaped lines ``(quad, text, confidence)`` in the
pixels of the image sent, so the caller's normalize/scale/offset chain is the
same for both engines.
"""
from __future__ import annotations

import base64
import os
import threading
import time
from typing import List, Optional, Tuple

from utils.logger_helper import logger_helper as logger

_TRIES_PER_READ = 2
_FAILED_READS_TO_BACK_OFF = 3
_BACKOFF_S = 300.0
_DISABLED_BACKOFF_S = 1800.0
_TIMEOUT_S = 15.0
# The CN HTTP gateway rejects bodies over ~1 MB with HTTP 413 (measured
# 2026-10-10: a 792 KB image = 1.05 MB base64 was refused), far below the
# ~6 MB callFunction ceiling. Screens go as JPEG at their own pixel size (bbox
# coordinates stay valid) and must stay under this many raw bytes.
_MAX_SEND_BYTES = 700 * 1024
_JPEG_QUALITIES = (85, 70, 55)

_MUTATION = """
mutation OcrImage($input: OcrInput!) {
  ocrImage(input: $input) {
    text
    blocks { text confidence bbox }
    width height provider model
  }
}
"""

_state_lock = threading.Lock()
_failed_reads = [0]
_local_until = [0.0]


class RemoteOcrError(RuntimeError):
    pass


def _server_lacks_ocr(msg: str) -> bool:
    """The server cannot do OCR at all (key unset, or a backend whose schema has
    no ocrImage yet) -- retrying every read only adds latency."""
    m = (msg or "").lower()
    return "not enabled" in m or 'cannot query field "ocrimage"' in m or 'unknown type "ocrinput"' in m


def remote_ocr_enabled() -> bool:
    """True when this read should try the server: CN build, not switched off,
    not in a back-off window."""
    if os.environ.get("ECAN_QIANNIU_REMOTE_OCR", "1") == "0":
        return False
    try:
        from utils.app_env import is_cn
        if not is_cn():
            return False
    except Exception:
        return False
    with _state_lock:
        return time.monotonic() >= _local_until[0]


def _auth():
    from app_context import AppContext
    from agent.cloud_api.cloud_api import get_appsync_endpoint
    mainwin = AppContext.get_main_window()
    token = mainwin.get_auth_token() if mainwin and hasattr(mainwin, "get_auth_token") else None
    endpoint = (mainwin.getWanApiEndpoint() if mainwin and hasattr(mainwin, "getWanApiEndpoint") else None) \
        or get_appsync_endpoint()
    if not token or not endpoint:
        raise RemoteOcrError("not signed in (no token / endpoint)")
    return token, endpoint


def _call(image_bytes: bytes) -> dict:
    import requests
    from agent.cloud_api.cloud_api import _http_auth_header
    token, endpoint = _auth()
    payload = {"query": _MUTATION,
               "variables": {"input": {"image": base64.b64encode(image_bytes).decode("ascii"),
                                       "type": "general"}}}
    resp = requests.post(endpoint, json=payload, timeout=_TIMEOUT_S, headers={
        "Content-Type": "application/json", "Authorization": _http_auth_header(token),
        "cache-control": "no-cache"})
    try:
        data = resp.json()
    except Exception:
        raise RemoteOcrError(f"HTTP {resp.status_code}: non-JSON response")
    errors = data.get("errors") if isinstance(data, dict) else None
    if errors:
        raise RemoteOcrError("; ".join(str(e.get("message") or e) for e in errors)[:300])
    result = ((data or {}).get("data") or {}).get("ocrImage")
    if not isinstance(result, dict):
        raise RemoteOcrError(f"HTTP {resp.status_code}: no ocrImage in response")
    return result


def to_rapidocr_lines(result: dict) -> List[Tuple[list, str, Optional[float]]]:
    """Server blocks (bbox [x1,y1,x2,y2]) as RapidOCR lines (quad, text, confidence)."""
    lines = []
    for b in result.get("blocks") or []:
        text, box = str(b.get("text") or "").strip(), b.get("bbox") or []
        if not text or len(box) != 4:
            continue
        x1, y1, x2, y2 = (float(v) for v in box)
        lines.append(([[x1, y1], [x2, y1], [x2, y2], [x1, y2]], text, b.get("confidence")))
    return lines


def _jpeg_bytes(path: str) -> bytes:
    """The image at *path* as JPEG (same pixel size) under _MAX_SEND_BYTES."""
    import io
    from PIL import Image
    with Image.open(path) as im:
        rgb = im.convert("RGB")
    for q in _JPEG_QUALITIES:
        buf = io.BytesIO()
        rgb.save(buf, format="JPEG", quality=q)
        if buf.tell() <= _MAX_SEND_BYTES:
            return buf.getvalue()
    raise RemoteOcrError(f"image is {buf.tell() // 1024} KB as JPEG q{_JPEG_QUALITIES[-1]}, "
                         f"over the {_MAX_SEND_BYTES // 1024} KB inline limit")


def ocr_png(path: str) -> Tuple[List[Tuple[list, str, Optional[float]]], str]:
    """OCR the image at *path* on the server. Returns (lines, engine label).
    Raises RemoteOcrError when every try failed; the caller then reads locally."""
    try:
        image = _jpeg_bytes(path)
    except RemoteOcrError as exc:
        _note_failed_read(exc)
        raise
    last: Optional[Exception] = None
    for attempt in range(1, _TRIES_PER_READ + 1):
        try:
            result = _call(image)
            with _state_lock:
                _failed_reads[0] = 0
            return to_rapidocr_lines(result), f"remote:{result.get('provider') or '?'}/{result.get('model') or '?'}"
        except Exception as exc:
            last = exc
            if _server_lacks_ocr(str(exc)):
                break
    _note_failed_read(last)
    raise RemoteOcrError(str(last))


def _note_failed_read(exc: Optional[Exception]) -> None:
    msg = str(exc or "")
    with _state_lock:
        _failed_reads[0] += 1
        if _server_lacks_ocr(msg):
            _local_until[0] = time.monotonic() + _DISABLED_BACKOFF_S
            logger.warning(f"[qianniu] server OCR unavailable on this backend; local OCR for "
                           f"{_DISABLED_BACKOFF_S / 60:.0f} min ({msg})")
            _failed_reads[0] = 0
        elif _failed_reads[0] >= _FAILED_READS_TO_BACK_OFF:
            _local_until[0] = time.monotonic() + _BACKOFF_S
            logger.warning(f"[qianniu] server OCR failed {_failed_reads[0]} reads in a row; local OCR for "
                           f"{_BACKOFF_S / 60:.0f} min (last: {msg})")
            _failed_reads[0] = 0
        else:
            logger.warning(f"[qianniu] server OCR failed ({msg}); this read uses local OCR")
