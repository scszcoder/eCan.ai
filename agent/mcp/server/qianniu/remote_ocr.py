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

Screens go by URL: a presigned COS upload through the llm-proxy
(``POST /v1/files``), then ``ocrImage(input: {url})``; the server fetches it
(cap ``_MAX_URL_BYTES``). CloudBase's HTTP gateway caps a JSON (text-type)
body at 100 KB (EXCEED_MAX_PAYLOAD_SIZE, a fixed platform cap), ~70 KB of raw
image after base64, so only small crops go inline (base64 in the GraphQL
body). After one 413 the session stops trying inline.

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
# Inline only below this many raw JPEG bytes: the gateway's 100 KB text-body
# cap minus base64 (x1.33) and the GraphQL/JSON overhead (server team,
# 2026-10-12; an 85 KB screen was refused). Images keep their pixel size, so
# bbox coordinates stay valid; inline uses the first quality only (lower ones
# blur the text), the rest only shrink an image too big for the URL cap.
_MAX_SEND_BYTES = 60 * 1024
_JPEG_QUALITIES = (85, 70, 55)
# Server-side cap on an image fetched by URL (llm_proxy OCR_MAX_IMAGE_BYTES).
_MAX_URL_BYTES = 4 * 1024 * 1024

# Direct route (2026-10-20): the web-function OCR endpoint of the llm-proxy takes
# the image INLINE up to 4 MB (its gateway allows ~6 MB bodies), where GraphQL's
# event-function gateway refuses bodies over ~100 KB -- so every 千牛 screenshot
# paid a guaranteed 413, a COS upload and ocrImage(url): ~3.4 s a read. Same
# server handler, account check and billing; same result shape (plain JSON).
# The original file is sent as-is (lossless). Any failure other than "too big"
# falls back to the GraphQL route for _DIRECT_BACKOFF_S; ECAN_QIANNIU_OCR_DIRECT=0
# turns the route off, ECAN_QIANNIU_OCR_URL overrides its address.
_DIRECT_MAX_BYTES = 4 * 1024 * 1024
_DIRECT_BACKOFF_S = 600.0
_direct_off_until = [0.0]

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
_inline_refused = [False]   # a 413 this session: every read goes by URL


class RemoteOcrError(RuntimeError):
    pass


class _BodyTooLarge(RemoteOcrError):
    """The GraphQL gateway refused the inline image (HTTP 413)."""


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


def _call(image_bytes: Optional[bytes] = None, url: Optional[str] = None) -> dict:
    """One ocrImage call with the image inline (*image_bytes*) or by *url*."""
    import requests
    from agent.cloud_api.cloud_api import _http_auth_header
    token, endpoint = _auth()
    ocr_input = {"url": url} if url else {"image": base64.b64encode(image_bytes).decode("ascii")}
    ocr_input["type"] = "general"
    payload = {"query": _MUTATION, "variables": {"input": ocr_input}}
    resp = requests.post(endpoint, json=payload, timeout=_TIMEOUT_S, headers={
        "Content-Type": "application/json", "Authorization": _http_auth_header(token),
        "cache-control": "no-cache"})
    if resp.status_code == 413:
        raise _BodyTooLarge(f"HTTP 413: {len(image_bytes or b'') // 1024} KB image over the gateway body limit")
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


def _jpeg_bytes(path: str) -> Tuple[Optional[bytes], bytes]:
    """The image at *path* as JPEG (same pixel size, so bbox coordinates stay
    valid): (full-quality JPEG to send inline, or None when it's over
    _MAX_SEND_BYTES or the gateway refused inline this session; a JPEG under
    _MAX_URL_BYTES if one could be made, for an original too big to upload)."""
    import io
    from PIL import Image
    with Image.open(path) as im:
        rgb = im.convert("RGB")
    first, data = None, b""
    for q in _JPEG_QUALITIES:
        buf = io.BytesIO()
        rgb.save(buf, format="JPEG", quality=q)
        data = buf.getvalue()
        if first is None:
            first = data
        if len(data) <= _MAX_URL_BYTES:
            break
    inline = first if len(first) <= _MAX_SEND_BYTES and not _inline_refused[0] else None
    return inline, data


def _upload_for_url(path: str, smallest_jpeg: bytes) -> str:
    """Upload the image to COS (presigned PUT via the llm-proxy) and return the
    URL the server fetches. The original file when it fits the server's URL cap
    (no JPEG loss), else the smallest JPEG."""
    import tempfile
    from agent.ec_skills.media.proxy_media_client import ProxyMediaClient
    tmp = None
    try:
        if os.path.getsize(path) <= _MAX_URL_BYTES:
            src = path
        elif len(smallest_jpeg) <= _MAX_URL_BYTES:
            fd, tmp = tempfile.mkstemp(suffix=".jpg")
            with os.fdopen(fd, "wb") as fh:
                fh.write(smallest_jpeg)
            src = tmp
        else:
            raise RemoteOcrError(f"image is {len(smallest_jpeg) // 1024} KB even as JPEG, "
                                 f"over the {_MAX_URL_BYTES // 1024} KB server limit")
        client = ProxyMediaClient.from_ecanai()
        try:
            return client.upload_file(src)
        finally:
            client.close()
    except RemoteOcrError:
        raise
    except Exception as exc:
        raise RemoteOcrError(f"COS upload failed: {exc}") from exc
    finally:
        if tmp:
            try:
                os.remove(tmp)
            except OSError:
                pass


def _direct_url(endpoint: str) -> str:
    override = (os.environ.get("ECAN_QIANNIU_OCR_URL") or "").strip()
    if override:
        return override
    if "/api/graphql" in (endpoint or ""):
        return endpoint.split("/api/graphql")[0] + "/api/llm-proxy-b/v1/images/ocr"
    return ""


def _call_direct(image_bytes: bytes) -> dict:
    """One OCR call on the direct route with the image inline. Raises on any non-200."""
    import requests
    from agent.cloud_api.cloud_api import _http_auth_header
    token, endpoint = _auth()
    url = _direct_url(endpoint)
    if not url:
        raise RemoteOcrError(f"no direct OCR address for endpoint {endpoint!r}")
    resp = requests.post(url, timeout=_TIMEOUT_S,
                         json={"image": base64.b64encode(image_bytes).decode("ascii"), "type": "general"},
                         headers={"Content-Type": "application/json", "Authorization": _http_auth_header(token),
                                  "X-Ecan-Source": "qianniu_ocr"})
    if resp.status_code != 200:
        try:
            err = (resp.json() or {}).get("error") or {}
            msg = f"{err.get('code') or err.get('type') or ''} {err.get('message') or ''}".strip()
        except Exception:
            msg = resp.text[:200]
        raise RemoteOcrError(f"HTTP {resp.status_code}: {msg}")
    return resp.json()


def _try_direct(path: str):
    """(lines, engine) from the direct route, or None to use the GraphQL route."""
    if os.environ.get("ECAN_QIANNIU_OCR_DIRECT", "1") == "0" or time.monotonic() < _direct_off_until[0]:
        return None
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return None
    if len(data) > _DIRECT_MAX_BYTES:
        return None
    try:
        result = _call_direct(data)
    except Exception as exc:
        _direct_off_until[0] = time.monotonic() + _DIRECT_BACKOFF_S
        logger.warning(f"[qianniu] direct OCR route failed ({exc}); GraphQL route for "
                       f"{_DIRECT_BACKOFF_S / 60:.0f} min")
        return None
    with _state_lock:
        _failed_reads[0] = 0
    return (to_rapidocr_lines(result),
            f"remote/direct:{result.get('provider') or '?'}/{result.get('model') or '?'}")


def ocr_png(path: str) -> Tuple[List[Tuple[list, str, Optional[float]]], str]:
    """OCR the image at *path* on the server. Returns (lines, engine label).
    Raises RemoteOcrError when every try failed; the caller then reads locally."""
    direct = _try_direct(path)
    if direct is not None:
        return direct
    try:
        image, smallest = _jpeg_bytes(path)
    except Exception as exc:
        _note_failed_read(exc)
        raise RemoteOcrError(f"could not read image: {exc}") from exc
    url: Optional[str] = None
    last: Optional[Exception] = None
    for attempt in range(1, _TRIES_PER_READ + 1):
        try:
            if image is None and url is None:
                url = _upload_for_url(path, smallest)
            result = _call(image, url=url)
            with _state_lock:
                _failed_reads[0] = 0
            via = "/url" if url else ""
            return (to_rapidocr_lines(result),
                    f"remote{via}:{result.get('provider') or '?'}/{result.get('model') or '?'}")
        except _BodyTooLarge as exc:
            # The gateway refused even a small image: URL for the rest of the session.
            last, image = exc, None
            _inline_refused[0] = True
            logger.info(f"[qianniu] server OCR: {exc}; sending by COS URL from now on")
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
