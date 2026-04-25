"""Step 4 — AppSync binding for :class:`HybridTransport`.

Wraps :class:`AppSyncPassiveClient` so step-3 protocol messages
(``PrimitiveCommand``, ``ScrapeRequest``, ``EventEnvelope``,
``HookOutcome``) flow over the existing AppSync subscription/mutation
channel that ``passive_command_service`` already opens.

Design choices
--------------

* **Multiplex by ``type`` field** — the existing wire carries any
  Pydantic model with a discriminator ``type``.  This adapter:

  - On the cloud side: serializes outbound commands via
    ``model_dump()`` and submits them through whatever ``send_command``
    callable the caller injects (in production: an AppSync mutation;
    in tests: a queue).
  - On the local side: receives raw AppSync envelope dicts via the
    ``inject_inbound`` method (production wires this from the
    AppSync subscription's ``on_command_received``; tests call it
    directly), parses the discriminator, and dispatches to the right
    Pydantic model.

* **Reuse the existing client when possible** — :class:`AppSyncPassiveClient`
  already does WS subscription + reconnect + auth.  We don't replace
  it; we add a sibling channel for the new message types.  The
  GraphQL schema needs one new mutation
  (``publishHybridMessage``) and one new subscription
  (``onHybridMessage``) — those are server-side changes outside this
  module's scope.

* **Step ID correlation** — same as :class:`LoopbackTransport`: cloud
  awaits a future keyed by ``step_id``; local replies resolve it.
  Reply-arriving-before-await race is handled by buffering.

* **No top-level imports of httpx/websocket** — kept import-light so
  unit tests don't pull in the full HTTP stack.

Production wiring (sketch — done in caller, not here)
-----------------------------------------------------

    # cloud side
    transport = AppSyncHybridTransport(
        send_command=lambda msg: appsync_client.publish_hybrid_message(msg),
        run_id=run_id,
    )

    # local side
    transport = AppSyncHybridTransport(send_command=None, run_id=run_id)
    appsync_client.on_hybrid_message = transport.inject_inbound

Tests
-----

The :class:`AppSyncHybridTransport` is fully driveable without a real
AppSync — the unit tests mock ``send_command`` and call
:meth:`inject_inbound` directly.  See :mod:`test_appsync_hybrid_transport`.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Awaitable, Callable, Optional

from pydantic import BaseModel

from agent.ec_skills.browser_use_extension.hybrid_protocol import (
    BundleDeliveryRequest,
    BundleDeliveryResponse,
    EventEnvelope,
    HookOutcome,
    HybridTransport,
    PrimitiveCommand,
    PrimitiveResult,
    ScrapeRequest,
    ScrapeResponse,
)

logger = logging.getLogger("ecan.appsync_hybrid_transport")

__all__ = [
    "AppSyncHybridTransport",
    "MESSAGE_TYPE_REGISTRY",
]


# ============================================================================
# Type registry — discriminator value → Pydantic class
# ============================================================================


MESSAGE_TYPE_REGISTRY: dict[str, type[BaseModel]] = {
    "primitive_command": PrimitiveCommand,
    "primitive_result": PrimitiveResult,
    "scrape_request": ScrapeRequest,
    "scrape_response": ScrapeResponse,
    "event_envelope": EventEnvelope,
    "hook_outcome": HookOutcome,
    "bundle_delivery_request": BundleDeliveryRequest,
    "bundle_delivery_response": BundleDeliveryResponse,
}


def _parse_inbound(raw: Any) -> BaseModel:
    """Parse a raw AppSync payload (dict or JSON string) into the right
    Pydantic model based on its ``type`` discriminator.

    Raises ``ValueError`` for unknown / missing types.
    """
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception as exc:
            raise ValueError(f"inbound payload is not valid JSON: {exc}")
    if not isinstance(raw, dict):
        raise ValueError(
            f"inbound payload must be dict, got {type(raw).__name__}"
        )
    type_tag = raw.get("type")
    if not type_tag:
        raise ValueError(f"inbound payload missing 'type' field: {raw!r}")
    cls = MESSAGE_TYPE_REGISTRY.get(type_tag)
    if cls is None:
        raise ValueError(
            f"unknown hybrid message type: {type_tag!r} "
            f"(registered: {sorted(MESSAGE_TYPE_REGISTRY.keys())})"
        )
    return cls.model_validate(raw)


# ============================================================================
# AppSyncHybridTransport
# ============================================================================


# Caller-injected outbound function.  Production wires this to either
# an AppSync mutation (cloud→local direction) or a different mutation
# (local→cloud direction).  Tests use a Mock or a queue.
_SendCommand = Callable[[BaseModel], Awaitable[None]]


class AppSyncHybridTransport:
    """:class:`HybridTransport` implementation backed by AppSync.

    Bidirectional: the same instance is used by both sides — the cloud
    side calls :meth:`send_to_local`, the local side calls
    :meth:`receive_command` / :meth:`reply_to_cloud` / :meth:`send_to_cloud`.
    Production deploys two separate instances (one per side); tests can
    use a single instance that loopbacks.

    Outbound messages go through the caller-supplied ``send_command``
    coroutine.  Inbound messages are pushed into the transport via
    :meth:`inject_inbound` (called by the AppSync subscription's message
    handler in production, or by tests directly).
    """

    def __init__(
        self,
        *,
        send_command: Optional[_SendCommand],
        run_id: str = "",
    ):
        self._send_command = send_command
        self._run_id = run_id

        # Inbound queue (for local side: commands from cloud)
        self._inbound: asyncio.Queue[BaseModel] = asyncio.Queue()
        # Outbound non-reply queue (for tests to inspect cloud-side pushes)
        self._sent_to_cloud: list[BaseModel] = []
        # Step→future map (cloud waits here for replies)
        self._pending: dict[str, asyncio.Future[BaseModel]] = {}
        # Race buffer: replies that arrived before send_to_local awaited
        self._reply_buffer: dict[str, BaseModel] = {}
        # Best-effort loop ref for thread-safe future resolution
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    # ── caller-side API: inject inbound messages ──
    def inject_inbound(self, raw: Any) -> None:
        """Called by the AppSync subscription handler when a message
        arrives for this side.

        ``raw`` may be a dict (already-decoded), a JSON string, or a
        Pydantic model instance (when caller has already parsed).
        Errors during parsing are logged and the message dropped —
        this is a robustness boundary.
        """
        try:
            if isinstance(raw, BaseModel):
                msg = raw
            else:
                msg = _parse_inbound(raw)
        except Exception as exc:
            logger.warning(
                f"[AppSyncHybridTransport] dropping unparseable inbound: "
                f"{exc!r}; raw={str(raw)[:200]!r}"
            )
            return
        self._route_inbound(msg)

    def _route_inbound(self, msg: BaseModel) -> None:
        """Route a parsed inbound message to either:

        * the pending-reply futures (if it's a reply correlated by step_id), or
        * the local-side inbound queue (commands awaiting a worker).
        """
        if isinstance(msg, (PrimitiveResult, ScrapeResponse)):
            step_id = getattr(msg, "step_id", "")
            if step_id and step_id in self._pending:
                fut = self._pending[step_id]
                self._set_future_safely(fut, msg)
            elif step_id:
                # Reply landed before the cloud-side send_to_local
                # awaited; buffer for race tolerance.
                self._reply_buffer[step_id] = msg
            else:
                logger.warning(
                    f"[AppSyncHybridTransport] reply missing step_id; "
                    f"dropping: {type(msg).__name__}"
                )
            return
        # Commands / events / outcomes — enqueue for the local-side
        # consumer (or for inspection by cloud-side tests).
        try:
            self._inbound.put_nowait(msg)
        except Exception as exc:
            logger.warning(
                f"[AppSyncHybridTransport] inbound queue put failed: {exc!r}"
            )

    @staticmethod
    def _set_future_safely(fut: asyncio.Future, value: Any) -> None:
        if fut.done():
            return
        loop = fut.get_loop()
        # If we're on the same running loop, set directly; otherwise
        # marshal across via call_soon_threadsafe.
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is loop:
            fut.set_result(value)
        else:
            try:
                loop.call_soon_threadsafe(fut.set_result, value)
            except RuntimeError:
                # Loop closed mid-flight — best-effort drop.
                pass

    # ── HybridTransport — cloud side ──
    async def send_to_local(self, command: BaseModel) -> BaseModel:
        if self._send_command is None:
            raise RuntimeError(
                "AppSyncHybridTransport has no send_command wired; "
                "this side cannot originate commands"
            )
        step_id = getattr(command, "step_id", None)
        if not step_id:
            raise ValueError("command must have step_id for correlation")

        # Check the buffer FIRST (race-tolerant, mirrors LoopbackTransport)
        if step_id in self._reply_buffer:
            return self._reply_buffer.pop(step_id)

        loop = asyncio.get_running_loop()
        self._loop = loop  # cache for inject_inbound thread-safety
        fut: asyncio.Future[BaseModel] = loop.create_future()
        self._pending[step_id] = fut
        try:
            await self._send_command(command)
        except Exception:
            self._pending.pop(step_id, None)
            raise
        try:
            return await fut
        finally:
            self._pending.pop(step_id, None)

    # ── HybridTransport — local side ──
    async def receive_command(self) -> BaseModel:
        return await self._inbound.get()

    async def send_to_cloud(self, message: BaseModel) -> None:
        """Local→cloud non-reply push (events, outcomes).

        In production this should publish via an AppSync mutation; the
        ``send_command`` callable is used.  Tests can also pop the
        :attr:`sent_to_cloud_log` for inspection.
        """
        self._sent_to_cloud.append(message)
        if self._send_command is not None:
            await self._send_command(message)

    async def reply_to_cloud(self, reply: BaseModel) -> None:
        """Local→cloud reply (PrimitiveResult, ScrapeResponse).

        In a single-process configuration (cloud and local share the
        same transport instance), a reply resolves the local pending
        future directly.  In a real deployment the reply is published
        via the same outbound channel as :meth:`send_to_cloud`, and
        the cloud-side instance routes it via :meth:`inject_inbound`.
        """
        # Fast path: same instance is acting as both sides (tests + co-located).
        step_id = getattr(reply, "step_id", "")
        if step_id and step_id in self._pending:
            self._set_future_safely(self._pending[step_id], reply)
            return
        if step_id:
            self._reply_buffer[step_id] = reply
        # Production: also publish so the cloud-side counterpart (a
        # different transport instance) can route it via inject_inbound.
        if self._send_command is not None:
            await self._send_command(reply)

    # ── inspection helpers (mostly for tests) ──
    @property
    def sent_to_cloud_log(self) -> list[BaseModel]:
        return list(self._sent_to_cloud)

    def pending_step_ids(self) -> list[str]:
        return list(self._pending.keys())
