"""Synchronous client for the eCan llm-proxy media endpoints.

Every media call (upload, transcription, image / speech / video generation)
goes through the llm-proxy -- never to a vendor directly -- so it is billed
per skill from the ``X-Ecan-*`` attribution headers, which are read from the
run scope at REQUEST time (``utils.log_scope.attribution_headers``).

Paid POSTs carry an ``Idempotency-Key``; retries of the same call reuse it so
the proxy never charges twice.
"""

from __future__ import annotations

import mimetypes
import os
import re
import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import unquote, urlparse

import httpx

from utils.logger_helper import logger_helper as logger

# Multipart transcription limit (the live proxy's effective body limit is
# ~4 MB); larger files are uploaded via /files and sent by URL.
TRANSCRIBE_MULTIPART_MAX_BYTES = 4 * 1024 * 1024
MODEL_CAPS_TTL_S = 600.0
VIDEO_TERMINAL_STATUSES = ("succeeded", "failed", "cancelled", "expired")

_DEFAULT_ERROR_CODES = {
    400: "invalid_request",
    401: "unauthenticated",
    402: "insufficient_balance",
    403: "forbidden",
    404: "not_found",
    413: "payload_too_large",
    429: "rate_limited",
    502: "upstream_error",
    503: "upstream_error",
    504: "upstream_timeout",
}
_RETRY_STATUSES = (429, 502, 503, 504)
# Never retried even on a retryable status: retrying can't change the answer.
_NO_RETRY_CODES = ("model_not_priced", "content_policy")
CONTENT_POLICY_HINT = "the provider's content moderation rejected this request; change the prompt or inputs"

# GET /models capabilities per base_url: {base_url: (fetched_at, {model_id: capabilities})}
_CAPS_CACHE: Dict[str, Tuple[float, Dict[str, Dict[str, Any]]]] = {}
_CAPS_LOCK = threading.Lock()


class MediaProxyError(Exception):
    """An error answer from the llm-proxy (OpenAI error shape)."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(f"[{status}] {code}: {message}")
        self.status = status
        self.code = code
        self.message = message


def is_url(value: str) -> bool:
    return str(value or "").strip().lower().startswith(("http://", "https://"))


def guess_mime(name: str, default: str = "application/octet-stream") -> str:
    return mimetypes.guess_type(name)[0] or default


class ProxyMediaClient:
    def __init__(self, base_url: str, api_key: str, extra_headers: Optional[Dict[str, str]] = None,
                 timeout: float = 180.0):
        if not base_url or not api_key:
            raise ValueError("llm-proxy base_url and api_key are required")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.extra_headers = dict(extra_headers or {})
        self.timeout = timeout
        self.max_retries = 2
        self.retry_backoff_s = 2.0
        self.poll_initial_s = 5.0
        self.poll_max_s = 30.0
        self.idempotency_wait_s = 5.0      # 409 idempotency_in_progress: same key, later
        self.idempotency_max_waits = 12
        self._sleep: Callable[[float], None] = time.sleep
        self._http = httpx.Client(timeout=httpx.Timeout(timeout, connect=15.0), follow_redirects=True)

    @classmethod
    def from_ecanai(cls) -> "ProxyMediaClient":
        """Client on the configured ``ecanai`` provider (the eCan llm-proxy).

        Same resolution as ``create_ecanai_chat_llm``. Raises when ecanai isn't
        configured -- never falls back to a vendor host.
        """
        from app_context import AppContext
        from agent.ec_skills.llm_utils.llm_utils import extract_provider_config
        mainwin = AppContext.get_main_window()
        cm = getattr(mainwin, "config_manager", None)
        provider = cm.llm_manager.get_provider("ecanai") if cm else None
        if not provider:
            raise RuntimeError("ecanai provider not configured")
        cfg = extract_provider_config(provider, config_manager=cm)
        if not cfg.get("api_key") or not cfg.get("base_url"):
            raise RuntimeError("ecanai API key / llm-proxy URL not configured")
        headers = {"X-Provider": "ecanai"}
        user = getattr(mainwin, "user", "") or ""
        if user:
            try:
                from agent.cloud_api.cloud_api import normalize_cloud_owner
                user = normalize_cloud_owner(user)
            except Exception:
                pass
            headers["X-User-Id"] = user
        return cls(cfg["base_url"], cfg["api_key"], extra_headers=headers)

    def close(self) -> None:
        try:
            self._http.close()
        except Exception:
            pass

    # ------------------------------------------------------------------ core
    def _headers(self, idempotency_key: Optional[str]) -> Dict[str, str]:
        from utils.log_scope import attribution_headers
        headers = {"Authorization": f"Bearer {self.api_key}", **self.extra_headers}
        headers.update(attribution_headers())
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        return headers

    def _request(self, method: str, path: str, *, json_body: Any = None, files: Any = None,
                 data: Any = None, paid: bool = False, timeout: Optional[float] = None) -> httpx.Response:
        url = f"{self.base_url}/{path.lstrip('/')}"
        idem = str(uuid.uuid4()) if paid else None   # one key for every retry of this call
        attempt = 0
        waits = 0
        while True:
            try:
                resp = self._http.request(
                    method, url, headers=self._headers(idem), json=json_body, files=files, data=data,
                    timeout=httpx.Timeout(timeout, connect=15.0) if timeout else httpx.USE_CLIENT_DEFAULT)
            except httpx.TransportError as e:
                if attempt >= self.max_retries:
                    raise MediaProxyError(0, "network_error", f"{type(e).__name__}: {e}") from e
                attempt += 1
                self._sleep(self.retry_backoff_s * attempt)
                continue
            if resp.status_code >= 400:
                code, _ = self._error_of(resp)
                retry_after = resp.headers.get("Retry-After", "")
                if code == "idempotency_in_progress" and waits < self.idempotency_max_waits:
                    # The same key is still running on the proxy: ask again later WITH that key.
                    waits += 1
                    self._sleep(float(retry_after) if retry_after.isdigit() else self.idempotency_wait_s)
                    continue
                if (resp.status_code in _RETRY_STATUSES and code not in _NO_RETRY_CODES
                        and attempt < self.max_retries):
                    attempt += 1
                    self._sleep(float(retry_after) if retry_after.isdigit() else self.retry_backoff_s * attempt)
                    continue
                self._raise_for(resp, method, path)
            billed = resp.headers.get("X-Ecan-Billed-Units")
            if billed:
                logger.info(f"[MediaProxy] {method} {path} billed {billed} "
                            f"(request_id={resp.headers.get('X-Request-Id', '')})")
            return resp

    @staticmethod
    def _error_of(resp: httpx.Response) -> Tuple[str, str]:
        """``(code, message)`` of an error answer (OpenAI shape, else by status)."""
        code = message = None
        try:
            err = (resp.json() or {}).get("error")
            if isinstance(err, dict):
                code = err.get("code") or err.get("type")
                message = err.get("message")
            elif isinstance(err, str):
                message = err
        except Exception:
            pass
        code = code or _DEFAULT_ERROR_CODES.get(resp.status_code, "http_error")
        return str(code), str(message or (resp.text or "")[:300])

    @classmethod
    def _raise_for(cls, resp: httpx.Response, method: str, path: str) -> None:
        code, message = cls._error_of(resp)
        if code == "content_policy":
            message = f"{CONTENT_POLICY_HINT} ({message})"
        if resp.status_code == 401:
            # Expected: token expired / missing; the session supervisor re-auths.
            logger.warning(f"[MediaProxy] {method} {path} unauthenticated (401): {message}")
        raise MediaProxyError(resp.status_code, code, message)

    # ------------------------------------------------------------- endpoints
    def list_models(self) -> List[Dict[str, Any]]:
        """``GET /models``: entries with their ``capabilities`` (may be absent = text-only)."""
        return (self._request("GET", "/models", timeout=15.0).json() or {}).get("data") or []

    def get_model_capabilities(self) -> Dict[str, Dict[str, Any]]:
        """``{model_id: capabilities}`` from ``GET /models``, cached per process
        for ``MODEL_CAPS_TTL_S``. A model without capabilities maps to ``{}``
        (text-only chat). Raises when the proxy can't be reached and nothing is cached."""
        now = time.monotonic()
        with _CAPS_LOCK:
            hit = _CAPS_CACHE.get(self.base_url)
            if hit and now - hit[0] < MODEL_CAPS_TTL_S:
                return hit[1]
        caps = {str(m.get("id")): dict(m.get("capabilities") or {})
                for m in self.list_models() if isinstance(m, dict) and m.get("id")}
        with _CAPS_LOCK:
            _CAPS_CACHE[self.base_url] = (now, caps)
        return caps

    def upload_file(self, path: str, purpose: str = "model_input") -> str:
        """``POST /files`` then PUT the bytes to the presigned URL; returns the fetchable URL."""
        name = os.path.basename(path)
        mime = guess_mime(name)
        size = os.path.getsize(path)
        info = self._request("POST", "/files", json_body={
            "filename": name, "mime_type": mime, "size": size, "purpose": purpose}).json()
        headers = dict(info.get("upload_headers") or {"Content-Type": mime})
        with open(path, "rb") as fh:
            # Presigned storage URL: never send our bearer / attribution there.
            put = self._http.put(info["upload_url"], content=fh.read(), headers=headers,
                                 timeout=httpx.Timeout(max(self.timeout, 600.0), connect=15.0))
        if put.status_code >= 400:
            raise MediaProxyError(put.status_code, "upload_failed", (put.text or "")[:300])
        return info["url"]

    def transcribe(self, path_or_url: str, model: str, language: Optional[str] = None) -> Dict[str, Any]:
        """``POST /audio/transcriptions`` (verbose_json). Local files ≤4 MB go
        multipart; larger ones are uploaded first and sent by URL."""
        if not is_url(path_or_url) and os.path.getsize(path_or_url) <= TRANSCRIBE_MULTIPART_MAX_BYTES:
            name = os.path.basename(path_or_url)
            with open(path_or_url, "rb") as fh:
                content = fh.read()
            form = {"model": model, "response_format": "verbose_json"}
            if language:
                form["language"] = language
            return self._request("POST", "/audio/transcriptions", paid=True, data=form,
                                 files={"file": (name, content, guess_mime(name))}).json()
        url = path_or_url if is_url(path_or_url) else self.upload_file(path_or_url)
        body = {"url": url, "model": model, "response_format": "verbose_json"}
        if language:
            body["language"] = language
        return self._request("POST", "/audio/transcriptions", paid=True, json_body=body).json()

    def generate_images(self, model: str, prompt: str, timeout_s: Optional[float] = None,
                        **params: Any) -> List[Dict[str, Any]]:
        """``POST /images/generations`` (synchronous); returns the ``data`` list."""
        body = {"model": model, "prompt": prompt, "response_format": "url"}
        body.update({k: v for k, v in params.items() if v not in (None, "", [])})
        resp = self._request("POST", "/images/generations", paid=True, json_body=body, timeout=timeout_s)
        return (resp.json() or {}).get("data") or []

    def speech(self, model: str, text: str, voice: Optional[str] = None, fmt: Optional[str] = None,
               speed: Optional[float] = None, timeout_s: Optional[float] = None) -> Tuple[bytes, str]:
        """``POST /audio/speech``; returns ``(audio bytes, mime type)``.

        ``fmt`` empty -> no ``response_format`` (the proxy uses the model's first
        format). Large audio comes back as JSON ``{url, mime_type, ...}`` instead
        of raw bytes; it is downloaded here so callers always get bytes."""
        body: Dict[str, Any] = {"model": model, "input": text}
        if fmt:
            body["response_format"] = fmt
        if voice:
            body["voice"] = voice
        if speed is not None:
            body["speed"] = speed
        resp = self._request("POST", "/audio/speech", paid=True, json_body=body, timeout=timeout_s)
        ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ctype != "application/json":
            return resp.content, ctype
        info = resp.json() or {}
        if not info.get("url"):
            raise MediaProxyError(502, "empty_output", "speech returned JSON without an audio url")
        # Presigned output URL: never send our bearer / attribution there.
        got = self._http.get(info["url"], timeout=httpx.Timeout(max(self.timeout, 600.0), connect=15.0))
        if got.status_code >= 400:
            raise MediaProxyError(got.status_code, "download_failed", (got.text or "")[:300])
        mime = info.get("mime_type") or (got.headers.get("Content-Type") or "").split(";")[0].strip()
        return got.content, mime

    def submit_video(self, model: str, prompt: str, **params: Any) -> Dict[str, Any]:
        """``POST /videos``: queue a generation job (202)."""
        body = {"model": model, "prompt": prompt}
        body.update({k: v for k, v in params.items() if v not in (None, "", [])})
        return self._request("POST", "/videos", paid=True, json_body=body).json()

    def get_video(self, video_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/videos/{video_id}").json()

    def cancel_video(self, video_id: str) -> Dict[str, Any]:
        return self._request("DELETE", f"/videos/{video_id}").json()

    def wait_video(self, video_id: str, timeout_s: float = 900.0,
                   on_progress: Optional[Callable[[Dict[str, Any]], None]] = None) -> Dict[str, Any]:
        """Poll ``GET /videos/{id}`` (5 s, backing off to 30 s) until a terminal
        status; returns that job. Raises ``MediaProxyError(code="client_timeout")``
        when ``timeout_s`` runs out first (the job is left as is)."""
        deadline = time.monotonic() + float(timeout_s)
        interval = self.poll_initial_s
        while True:
            job = self.get_video(video_id)
            if on_progress:
                try:
                    on_progress(job)
                except Exception:
                    pass
            if job.get("status") in VIDEO_TERMINAL_STATUSES:
                return job
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise MediaProxyError(408, "client_timeout",
                                      f"video {video_id} still {job.get('status')} after {timeout_s}s")
            self._sleep(min(interval, remaining))
            interval = min(interval * 2, self.poll_max_s)

    def download(self, url: str, dest_dir: str, filename: Optional[str] = None) -> str:
        """Download ``url`` (a presigned output URL) into ``dest_dir``; returns the path."""
        os.makedirs(dest_dir, exist_ok=True)
        resp = self._http.get(url, timeout=httpx.Timeout(max(self.timeout, 600.0), connect=15.0))
        if resp.status_code >= 400:
            raise MediaProxyError(resp.status_code, "download_failed", (resp.text or "")[:300])
        name = filename or os.path.basename(unquote(urlparse(url).path)) or "media"
        name = re.sub(r'[\\/:*?"<>|]+', "_", name)
        if not os.path.splitext(name)[1]:
            ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip()
            name += mimetypes.guess_extension(ctype) or ""
        path = unique_path(dest_dir, name)
        with open(path, "wb") as fh:
            fh.write(resp.content)
        return path


def unique_path(dest_dir: str, name: str) -> str:
    """``dest_dir/name``, suffixed ``_1``, ``_2`` ... if that file exists."""
    stem, ext = os.path.splitext(name)
    path = os.path.join(dest_dir, name)
    n = 1
    while os.path.exists(path):
        path = os.path.join(dest_dir, f"{stem}_{n}{ext}")
        n += 1
    return path


def ecanai_media_input_caps(model: str) -> Optional[Dict[str, bool]]:
    """``{"video", "audio"}`` input support of ``model`` from the ecanai proxy's
    ``GET /models`` capabilities (cached), or None when the proxy can't be asked
    or doesn't list the model -- the caller then falls back to its own flags."""
    try:
        client = ProxyMediaClient.from_ecanai()
        try:
            caps = client.get_model_capabilities()
        finally:
            client.close()
    except Exception as e:
        logger.warning(f"[MediaProxy] GET /models unavailable, using local media flags: {e}")
        return None
    if model not in caps:
        return None
    inputs = caps[model].get("input") or []
    return {"video": "video" in inputs, "audio": "audio" in inputs}
