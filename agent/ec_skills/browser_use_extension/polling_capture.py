"""
PollingCapture — pure user-land CDP Network interception for HTTP polling.

Captures HTTP polling responses via Chrome DevTools Protocol Network domain
events, without any modifications to the browser-use library source code.

Adapted from browser-use examples/features/chat_polling_capture.py.
"""
from __future__ import annotations

import asyncio
import base64
import re
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from browser_use import BrowserSession
from utils.logger_helper import logger_helper as logger


@dataclass
class PollingCaptureConfig:
    """Configuration for which HTTP responses to capture."""

    url_patterns: list = field(default_factory=list)
    methods: list = field(default_factory=lambda: ["GET", "POST"])
    content_filters: list = field(default_factory=list)
    min_body_length: int = 0

    def matches_url(self, url: str, method: str) -> bool:
        if self.methods and method.upper() not in [m.upper() for m in self.methods]:
            return False
        for pattern in self.url_patterns:
            if re.search(pattern, url):
                return True
        return False


@dataclass
class _TrackedRequest:
    request_id: str
    url: str
    method: str
    status: int = 0
    session_id: str = None


class PollingCapture:
    """Captures HTTP polling responses via CDP Network domain.

    Works entirely through browser-use's public API + direct CDP event
    registration.  No source modifications to browser-use are needed.

    Usage::

        session = BrowserSession(browser_profile=BrowserProfile(...))
        await session.start()
        await asyncio.sleep(3)  # let CDP reconnection settle

        capture = PollingCapture(
            session=session,
            config=PollingCaptureConfig(url_patterns=[r'/api/poll']),
            on_response=my_callback,
            on_message=my_match_callback,
        )
        await capture.start()
    """

    def __init__(
        self,
        session: BrowserSession,
        config: PollingCaptureConfig,
        on_response: Callable = None,
        on_message: Callable = None,
    ):
        self.session = session
        self.config = config
        self.on_response = on_response
        self.on_message = on_message
        self._tracked: Dict[str, _TrackedRequest] = {}
        self.captured_count = 0
        self.matched_count = 0
        self._enabled = False
        # Store captured responses for assertions / inspection
        self.captured_responses: List[dict] = []
        self.matched_messages: List[dict] = []

    async def start(self) -> None:
        """Enable CDP Network interception and register handlers."""
        if self._enabled:
            return

        cdp_session = await self.session.get_or_create_cdp_session()
        await cdp_session.cdp_client.send.Network.enable(
            session_id=cdp_session.session_id
        )

        cdp = self.session.cdp_client.register
        cdp.Network.requestWillBeSent(self._on_request)
        cdp.Network.responseReceived(self._on_response)
        cdp.Network.loadingFinished(self._on_loading_finished)

        self._enabled = True
        logger.info(
            f"[PollingCapture] Started: url_patterns={self.config.url_patterns}, "
            f"methods={self.config.methods}, filters={len(self.config.content_filters)}, "
            f"min_body={self.config.min_body_length}"
        )

    async def stop(self) -> None:
        """Mark capture as disabled (CDP handlers remain registered but are no-ops)."""
        self._enabled = False
        logger.info(f"[PollingCapture] Stopped: captured={self.captured_count}, matched={self.matched_count}")

    def _on_request(self, params, session_id):
        if not self._enabled:
            return
        try:
            req = (
                params.get("request", {})
                if isinstance(params, dict)
                else getattr(params, "request", {})
            )
            url = req.get("url") if isinstance(req, dict) else getattr(req, "url", None)
            method = (
                req.get("method") if isinstance(req, dict) else getattr(req, "method", None)
            )
            request_id = (
                params.get("requestId")
                if isinstance(params, dict)
                else getattr(params, "requestId", None)
            )

            if not url or not method or not request_id:
                return
            if not self.config.matches_url(url, method):
                return

            self._tracked[request_id] = _TrackedRequest(
                request_id=request_id,
                url=url,
                method=method,
                session_id=session_id,
            )
            logger.debug(f"[PollingCapture] Tracking request: {method} {url[:120]} (id={request_id})")
        except Exception as e:
            logger.debug(f"[PollingCapture] _on_request error: {e}")

    def _on_response(self, params, session_id):
        if not self._enabled:
            return
        try:
            request_id = (
                params.get("requestId")
                if isinstance(params, dict)
                else getattr(params, "requestId", None)
            )
            if not request_id or request_id not in self._tracked:
                return

            response = (
                params.get("response", {})
                if isinstance(params, dict)
                else getattr(params, "response", {})
            )
            tracked = self._tracked[request_id]
            tracked.status = (
                response.get("status")
                if isinstance(response, dict)
                else getattr(response, "status", 0)
            )
            if session_id:
                tracked.session_id = session_id
            logger.debug(f"[PollingCapture] Response received: status={tracked.status} {tracked.url[:120]}")
        except Exception as e:
            logger.debug(f"[PollingCapture] _on_response error: {e}")

    def _on_loading_finished(self, params, session_id):
        if not self._enabled:
            return
        try:
            request_id = (
                params.get("requestId")
                if isinstance(params, dict)
                else getattr(params, "requestId", None)
            )
            if not request_id or request_id not in self._tracked:
                return

            tracked = self._tracked.pop(request_id)
            logger.debug(f"[PollingCapture] Loading finished, fetching body: {tracked.method} {tracked.url[:120]}")
            asyncio.create_task(self._fetch_and_callback(tracked))
        except Exception as e:
            logger.debug(f"[PollingCapture] _on_loading_finished error: {e}")

    async def _fetch_and_callback(self, tracked: _TrackedRequest) -> None:
        body = ""
        try:
            resp = await self.session.cdp_client.send.Network.getResponseBody(
                params={"requestId": tracked.request_id},
                session_id=tracked.session_id,
            )
            raw = resp.get("body", "")
            is_b64 = resp.get("base64Encoded", False)
            if is_b64:
                try:
                    body = base64.b64decode(raw).decode("utf-8", errors="replace")
                except Exception:
                    body = raw
            else:
                body = raw if isinstance(raw, str) else str(raw)
        except Exception as e:
            logger.debug(f"[PollingCapture] Body fetch failed for {tracked.url[:120]}: {e}")

        if len(body) < self.config.min_body_length:
            logger.debug(f"[PollingCapture] Body too short ({len(body)}<{self.config.min_body_length}): {tracked.url[:120]}")
            return

        self.captured_count += 1
        logger.info(f"[PollingCapture] Captured #{self.captured_count}: {tracked.method} {tracked.url[:120]} (body={len(body)} chars)")

        capture_record = {
            "url": tracked.url,
            "method": tracked.method,
            "status": tracked.status,
            "body": body,
            "timestamp": time.time(),
        }
        self.captured_responses.append(capture_record)

        # Call on_response callback
        if self.on_response:
            try:
                result = self.on_response(tracked.url, tracked.method, tracked.status, body)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.debug(f"[PollingCapture] on_response callback error: {e}")

        # Run content filters (always, for tracking) and call on_message if set
        if self.config.content_filters and body:
            for filt in self.config.content_filters:
                try:
                    rule = filt(body)
                    if rule:
                        self.matched_count += 1
                        logger.info(
                            f"[PollingCapture] Content filter MATCHED #{self.matched_count}: "
                            f"rule='{rule}', url={tracked.url[:120]}, body_len={len(body)}"
                        )
                        match_record = {
                            "url": tracked.url,
                            "method": tracked.method,
                            "status": tracked.status,
                            "body": body,
                            "rule": rule,
                            "timestamp": time.time(),
                        }
                        self.matched_messages.append(match_record)
                        if self.on_message:
                            result = self.on_message(
                                tracked.url, tracked.method, tracked.status, body, rule
                            )
                            if asyncio.iscoroutine(result):
                                await result
                        break
                except Exception as e:
                    logger.debug(f"[PollingCapture] Content filter error: {e}")
