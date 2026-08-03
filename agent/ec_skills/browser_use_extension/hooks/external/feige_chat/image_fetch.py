"""Bounded async fetch of customer-attached images → data URI.

The front-desk hot path scrapes raw image URLs from the chat thread (see
``dom_assets.FEIGE_LATEST_CUSTOMER_BUBBLE_JS`` and
``site_tools._FEIGE_GET_THREAD_JS``).  Those URLs are signed
and time-limited (``x-expires=...``) — by the time the Q&A worker is
actually invoked the URL may be expired.  So the **front-desk** pre-fetches
them and embeds them as ``data:image/...;base64,...`` URIs in the dispatch
payload.

The fetch is intentionally bounded (default 0.3 s, 8 MB) so a slow CDN
can't stall the front-desk hot path.  On any failure the function returns
``(None, "<reason>")`` and the caller is expected to fall back to passing
the raw URL through; the Q&A worker can attempt a longer-timeout retry on
its side.

Public API:
    fetch_image_to_data_uri(url, *, timeout_s, max_bytes, cookies) -> (data_uri, error)
    fetch_attachments(attachments, *, timeout_s, max_bytes, cookies) -> list[dict]

The second helper takes the list-of-dicts shape produced by the scraper
(``[{"kind": "image", "url": "...", "alt": "..."}, ...]``) and returns the
same list with each entry augmented in-place with ``data_uri`` (on success)
or ``fetch_error`` (on failure).  Always returns a new list — caller's
input is not mutated.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any

logger = logging.getLogger("eCan")


# Default budget tuned for the front-desk hot path.  At 0.3 s per image
# (in parallel) with an 8 MB cap, a typical 100 KB chat image arrives in
# <100 ms over a healthy connection.  Bumping these up makes the hot path
# more sluggish; bumping them down increases fallback rate.
DEFAULT_TIMEOUT_S: float = 0.3
DEFAULT_MAX_BYTES: int = 8 * 1024 * 1024  # 8 MB

# Mime sniffing — restricted to formats LLM vision APIs reliably accept.
# ``application/octet-stream`` falls through to "image/jpeg" as a safe
# default; almost all chat-platform CDNs serve JPEGs.
_MIME_BY_MAGIC: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"RIFF", "image/webp"),  # WEBP starts with RIFF....WEBP
)


def _sniff_mime(data: bytes, content_type: str | None) -> str:
    """Best-effort image mime detection.

    Prefers the HTTP ``Content-Type`` header when it looks like a
    plausible image type; otherwise sniffs the magic bytes; otherwise
    falls back to ``image/jpeg``.
    """
    if content_type:
        ct = content_type.split(";", 1)[0].strip().lower()
        if ct.startswith("image/") and ct not in ("image/svg+xml",):
            # WEBP via RIFF — only honour if magic bytes back it up.
            return ct
    for magic, mime in _MIME_BY_MAGIC:
        if data.startswith(magic):
            # Special case: RIFF + check for WEBP signature within.
            if mime == "image/webp" and not (len(data) > 12 and data[8:12] == b"WEBP"):
                continue
            return mime
    return "image/jpeg"


async def fetch_image_to_data_uri(
    url: str,
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    max_bytes: int = DEFAULT_MAX_BYTES,
    cookies: dict[str, str] | None = None,
) -> tuple[str | None, str | None]:
    """Fetch *url* and return ``(data_uri, None)`` on success.

    On any failure (timeout, HTTP non-2xx, oversized payload, network
    error, missing aiohttp dependency) returns ``(None, reason)`` where
    ``reason`` is a short machine-readable token suitable for embedding
    in logs and as the ``fetch_error`` field of an attachment dict.

    The function never raises — failure modes are folded into the
    returned tuple so the front-desk hot path can stay synchronous-ish
    in its error handling.
    """
    if not url or not isinstance(url, str):
        return None, "empty_url"

    # Lazy import — keeps test environments that don't install aiohttp
    # from blowing up at module-import time.  ``aiohttp`` is in the main
    # requirements but defensive imports never hurt for a soft path.
    try:
        import aiohttp  # type: ignore
    except Exception as exc:
        return None, f"aiohttp_missing:{type(exc).__name__}"

    try:
        timeout = aiohttp.ClientTimeout(total=timeout_s)
        async with aiohttp.ClientSession(
            timeout=timeout, cookies=cookies or {}
        ) as session:
            async with session.get(url) as resp:
                if resp.status >= 400:
                    return None, f"http_{resp.status}"
                # Read bounded — abort if exceeds max_bytes.
                buf = bytearray()
                async for chunk in resp.content.iter_chunked(64 * 1024):
                    buf.extend(chunk)
                    if len(buf) > max_bytes:
                        return None, f"too_large:>{max_bytes}"
                if not buf:
                    return None, "empty_response"
                ctype = resp.headers.get("Content-Type")
                mime = _sniff_mime(bytes(buf), ctype)
                b64 = base64.b64encode(bytes(buf)).decode("ascii")
                return f"data:{mime};base64,{b64}", None
    except asyncio.TimeoutError:
        return None, "timeout"
    except asyncio.CancelledError:
        # Don't swallow cancel — propagate so the caller's task tree
        # collapses cleanly.
        raise
    except Exception as exc:
        return None, f"error:{type(exc).__name__}:{str(exc)[:80]}"


async def fetch_attachments(
    attachments: list[dict[str, Any]] | None,
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    max_bytes: int = DEFAULT_MAX_BYTES,
    cookies: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Concurrently fetch every image entry; return augmented list.

    Each input entry is a dict ``{"kind": "image", "url": "...", "alt": "..."}``
    as produced by the scraper.  The returned list has the same length
    and order, with each dict carrying either:

      * ``data_uri``: on successful fetch (``url`` is preserved so the
        worker can still log the source).
      * ``fetch_error``: short reason string on failure (``url`` is
        preserved for worker-side retry).

    Non-image entries (``kind != "image"``) are passed through untouched.
    Returns an empty list when *attachments* is falsy.
    """
    if not attachments:
        return []

    pending: list[tuple[int, dict[str, Any], asyncio.Task]] = []
    out: list[dict[str, Any]] = []
    for idx, entry in enumerate(attachments):
        # Always start with a defensive shallow copy so we don't mutate
        # the caller's dicts in place.
        if not isinstance(entry, dict):
            out.append({"kind": "unknown", "fetch_error": "non_dict"})
            continue
        copy = dict(entry)
        out.append(copy)
        if copy.get("kind") != "image":
            continue
        url = str(copy.get("url") or "").strip()
        if not url:
            copy["fetch_error"] = "empty_url"
            continue
        task = asyncio.create_task(
            fetch_image_to_data_uri(
                url, timeout_s=timeout_s, max_bytes=max_bytes, cookies=cookies
            )
        )
        pending.append((idx, copy, task))

    if not pending:
        return out

    # Wait for all in parallel — a single hung URL bounded by timeout_s
    # cannot stall faster ones since each fetch has its own timeout.
    results = await asyncio.gather(
        *(t for _, _, t in pending), return_exceptions=True
    )
    for (idx, copy, _task), res in zip(pending, results):
        if isinstance(res, BaseException):
            copy["fetch_error"] = f"task_exc:{type(res).__name__}"
            continue
        data_uri, err = res
        if data_uri:
            from .image_store import compact_attachment
            copy["data_uri"] = data_uri
            copy["data_uri_chars"] = len(data_uri)
            copy = compact_attachment(copy)
            out[idx] = copy
        else:
            copy["fetch_error"] = err or "unknown"

    # Concise summary log for ops visibility.
    ok = sum(1 for e in out if e.get("image_ref"))
    failed = sum(1 for e in out if e.get("fetch_error"))
    total_bytes = sum(int(e.get("byte_len") or 0) for e in out)
    total_data_uri_chars = sum(int(e.get("data_uri_chars") or 0) for e in out)
    max_bytes_seen = max((int(e.get("byte_len") or 0) for e in out), default=0)
    if ok or failed:
        logger.info(
            f"[data-uri-mitigation] image_fetch_compacted "
            f"stored_refs={ok} failed={failed} total={ok + failed} "
            f"total_bytes={total_bytes} data_uri_chars_removed={total_data_uri_chars}"
        )
    if max_bytes_seen > 1024 * 1024:
        logger.warning(
            f"[data-uri-mitigation] large_image_attachment_fetched "
            f"max_bytes={max_bytes_seen} attachment_count={len(out)}"
        )
    return out


__all__ = [
    "DEFAULT_TIMEOUT_S",
    "DEFAULT_MAX_BYTES",
    "fetch_image_to_data_uri",
    "fetch_attachments",
]
