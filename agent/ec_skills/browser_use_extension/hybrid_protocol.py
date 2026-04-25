"""Step 3 — hybrid-cloud wire protocol + transport-agnostic adapters.

Extends the existing ``passive_protocol`` with the message types needed
for the four cross-tier flows that emerged from step 2's hook ports:

* **PrimitiveCommand / PrimitiveResult** — cloud asks local to execute
  one ``BrowserPrimitives`` operation (eval_js / read_dom / click /
  type / wait_for) and awaits the result.  Backs cloud-side
  :class:`RpcBrowserPrimitives` so cloud_only hooks can drive a remote
  browser.

* **ScrapeRequest / ScrapeResponse** — cloud asks local to run a
  named ``local_extract`` scraper (e.g. Feige's ``customer_bubble``)
  and awaits a typed payload.  Backs cloud-side
  :class:`RpcScrapeFunction`.

* **EventEnvelope** — local pushes DOM events up to cloud.  Carries
  the event type, sub_type, timestamp, and any actionable_items the
  client-side EventMonitor extracted.  Replaces the ad-hoc dict
  shape currently flowing through ``AppSyncPassiveClient``.

* **HookOutcome** — local-side hook fires (e.g. HOT-PATH-B,
  FeigeQuickReplyHook) and reports its decision to cloud for state
  reconciliation.

Design notes
------------

The protocol is **transport-agnostic**.  Each message is a Pydantic
``BaseModel`` with a discriminated ``type`` field; transport layers
(AppSync, websocket, in-memory loopback for tests) only need to
serialize/deserialize and route by type.

The adapters in this module take a :class:`HybridTransport` Protocol
that any transport can satisfy.  Production binding (Step 4) wires
this to ``AppSyncPassiveClient``; the in-memory ``LoopbackTransport``
in this module is what tests use to validate the round-trip without
touching a network.

The three pieces — protocol, adapters, transport — together let a
``CloudHookContext.primitives`` proxy work transparently:

    cloud hook code:        await ctx.primitives.eval_js(snippet)
                                          │
                                          ▼ (RpcBrowserPrimitives)
    PrimitiveCommand       ─ sent_to_local ─►
    (over transport)
                                          ▼ (LocalPrimitiveExecutor)
    real BrowserPrimitives  ◀── dispatched ──
    on local browser
                                          │
                                          ▼
    PrimitiveResult         ─ send_to_cloud ─►
                                          │
                                          ▼
    cloud hook code:        receives the value
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, Awaitable, Callable, Literal, Optional, Protocol, Union, runtime_checkable

from pydantic import BaseModel, Field

from agent.ec_skills.browser_node.contexts import (
    BrowserPrimitives,
    LocalExtractContext,
)

logger = logging.getLogger("ecan.hybrid_protocol")

__all__ = [
    # Protocol message types
    "PrimitiveCommand",
    "PrimitiveResult",
    "ScrapeRequest",
    "ScrapeResponse",
    "EventEnvelope",
    "HookOutcome",
    # Bundle delivery (Step 5)
    "BundleDeliveryRequest",
    "BundleDeliveryResponse",
    # Transport
    "HybridTransport",
    "LoopbackTransport",
    # Adapters
    "RpcBrowserPrimitives",
    "RpcScrapeFunction",
    "LocalPrimitiveExecutor",
    "LocalScrapeExecutor",
]


# ============================================================================
# Protocol message types (Pydantic BaseModel — wire-format-friendly)
# ============================================================================


_PrimitiveOp = Literal["eval_js", "read_dom", "click", "type", "wait_for"]


class PrimitiveCommand(BaseModel):
    """Cloud → Local: execute one BrowserPrimitives operation.

    The ``op`` discriminator selects which primitive to invoke; ``params``
    carries op-specific keyword args mirroring the
    :class:`BrowserPrimitives` Protocol method signatures.
    """

    schema_version: int = Field(default=1)
    type: Literal["primitive_command"] = "primitive_command"

    # Correlation
    run_id: str
    step_id: str

    op: _PrimitiveOp
    params: dict[str, Any] = Field(default_factory=dict)


class PrimitiveResult(BaseModel):
    """Local → Cloud: result of a PrimitiveCommand.

    ``value`` carries the primitive's return value (DOM tree dict,
    JS-eval result, bool, etc.).  ``ok=False`` with ``error`` set when
    the primitive raised; the cloud-side adapter re-raises so hook code
    sees a normal exception.
    """

    schema_version: int = Field(default=1)
    type: Literal["primitive_result"] = "primitive_result"

    run_id: str
    step_id: str

    ok: bool = True
    value: Any = None
    error: str = ""
    error_type: str = ""
    elapsed_ms: int = 0


class ScrapeRequest(BaseModel):
    """Cloud → Local: invoke a named local_extract scraper.

    Specialization of the primitive flow for the cross-tier scrape RPC
    pattern in step 2f.  Distinct message type because scrapers are
    bundle-owned (multiple bundles may register different scrapers)
    rather than the fixed BrowserPrimitives surface.
    """

    schema_version: int = Field(default=1)
    type: Literal["scrape_request"] = "scrape_request"

    run_id: str
    step_id: str

    bundle: str           # which bundle owns the scraper, e.g. 'feige_chat'
    scraper: str          # scraper name, e.g. 'customer_bubble'
    params: dict[str, Any] = Field(default_factory=dict)


class ScrapeResponse(BaseModel):
    """Local → Cloud: scrape result, serialized payload.

    ``payload`` is whatever ``to_dict`` shape the scraper produces
    (e.g. :class:`pre_dispatch_scrape_v2.ScrapeResult.to_dict`).  Cloud
    side reconstructs via the matching ``from_dict``.
    """

    schema_version: int = Field(default=1)
    type: Literal["scrape_response"] = "scrape_response"

    run_id: str
    step_id: str

    ok: bool = True
    payload: dict[str, Any] = Field(default_factory=dict)
    error: str = ""


class EventEnvelope(BaseModel):
    """Local → Cloud: a DOM event observed by the local EventMonitor.

    Carries the extracted-dict payload (``actionable_items``) so the
    cloud-side actionable_items hook can consume them without round-
    tripping for each item.  Privacy filter is applied locally before
    the envelope leaves.
    """

    schema_version: int = Field(default=1)
    type: Literal["event_envelope"] = "event_envelope"

    run_id: str
    event_id: str

    event_type: str        # 'browser_event' | 'chat_message' | ...
    sub_type: str = ""     # site-specific label, e.g. '新消息'
    timestamp_ms: int

    # Already-extracted DOM rows (sidebar items etc.) — local saves cloud
    # a per-row scrape round-trip.
    actionable_items: list[dict[str, Any]] = Field(default_factory=list)

    # Free-form event data (chat text, sender ID, etc.)
    data: dict[str, Any] = Field(default_factory=dict)


class HookOutcome(BaseModel):
    """Local → Cloud: a local hook fired and reports its decision.

    Used for cloud-side state reconciliation: when a local_reactive
    hook (e.g. HOT-PATH-B) types a reply, cloud needs to know so its
    own dispatch state stays consistent.  Side effects are explicit
    so cloud can replay state mutations idempotently.
    """

    schema_version: int = Field(default=1)
    type: Literal["hook_outcome"] = "hook_outcome"

    run_id: str
    hook_id: str

    decision: str          # 'cont' | 'replace' | 'bypass' | 'drop' | 'handoff' | 'escalate'
    reason: str = ""

    # Free-form record of what the hook did (KV writes, primitives invoked).
    side_effects: list[dict[str, Any]] = Field(default_factory=list)

    duration_ms: int = 0
    trace_id: str = ""


class BundleDeliveryRequest(BaseModel):
    """Cloud → Local: deliver an external hook bundle for installation.

    Carries the bundle's manifest + every file (text or base64-encoded
    binary) needed to materialise it on local disk.  The cloud signs
    the manifest with the operator's private key (via
    :mod:`hook_signing`); the local side verifies before extraction.

    Workflow (production)
    ---------------------

    1. Cloud reads bundle dir from disk, packages files into ``files``,
       computes :func:`hook_signing.compute_hmac_sha256` of the manifest
       bytes, packs the result as ``signature``.
    2. Local extracts the bundle to a sandbox dir (typically
       ``<appdata>/hooks/external/<bundle>/``), writes the files,
       writes ``hook.sig`` from the signature blob, then calls
       :func:`hook_signing.enforce_trust` against the resulting dir
       BEFORE importing any code.
    3. On signature failure: extracted dir is deleted and the local
       responds with ``ok=False`` + an error tag.
    """

    schema_version: int = Field(default=1)
    type: Literal["bundle_delivery_request"] = "bundle_delivery_request"

    run_id: str
    step_id: str

    bundle_name: str           # 'feige_chat'
    bundle_version: str = "0.0.0"

    # File map: relative path → either utf-8 text (str) or base64 bytes
    # (dict ``{"b64": "..."}`` for binaries).  Always includes hook.yaml.
    files: dict[str, Any] = Field(default_factory=dict)

    # Signature envelope as produced by hook_signing.compute_hmac_sha256.
    # Same shape as on-disk hook.sig: ``{"key_id", "alg", "sig"}``.
    signature: dict[str, str] = Field(default_factory=dict)

    # Optional install hints for the local sandbox loader.
    install_hint: dict[str, Any] = Field(default_factory=dict)


class BundleDeliveryResponse(BaseModel):
    """Local → Cloud: result of installing a delivered bundle.

    ``ok=True`` means the signature verified, files were written, and
    the bundle is loadable via the existing :func:`hook_loader.load_bundle`.
    ``ok=False`` carries an ``error`` tag drawn from a small fixed
    vocabulary so cloud can categorise failures without parsing prose.
    """

    schema_version: int = Field(default=1)
    type: Literal["bundle_delivery_response"] = "bundle_delivery_response"

    run_id: str
    step_id: str

    ok: bool = True
    bundle_name: str = ""
    installed_path: str = ""    # absolute path on local disk, when ok=True
    hooks_loaded: list[str] = Field(default_factory=list)

    # Error vocabulary (when ok=False):
    #   'signature_invalid' | 'manifest_missing' | 'unsupported_alg'
    #   'extract_failed' | 'load_failed:<inner>' | 'unknown'
    error: str = ""
    error_detail: str = ""


# Union over all cloud→local and local→cloud message types — useful for
# transport implementations that need a single deserializer.
HybridMessage = Union[
    PrimitiveCommand, PrimitiveResult,
    ScrapeRequest, ScrapeResponse,
    EventEnvelope, HookOutcome,
    BundleDeliveryRequest, BundleDeliveryResponse,
]


# ============================================================================
# Transport Protocol
# ============================================================================


@runtime_checkable
class HybridTransport(Protocol):
    """Bidirectional cross-tier transport.

    Production binding (Step 4): AppSync subscription (cloud→local)
    + mutation (local→cloud).
    Tests: :class:`LoopbackTransport`.

    All methods are async.  Implementations must serialize/deserialize
    Pydantic models — ``model_dump`` and ``model_validate`` are the
    canonical helpers.
    """

    # ── cloud-side methods ──
    async def send_to_local(self, command: BaseModel) -> BaseModel:
        """Cloud: send ``command`` to local; return the matching reply.

        Correlation is by ``step_id`` for command/result pairs.
        Implementations are expected to time out after a transport-
        appropriate window and raise on timeout.
        """
        ...

    # ── local-side methods ──
    async def receive_command(self) -> BaseModel:
        """Local: await the next inbound command.

        Returns one of :class:`PrimitiveCommand` / :class:`ScrapeRequest`
        depending on what the cloud sent.
        """
        ...

    async def send_to_cloud(self, message: BaseModel) -> None:
        """Local: push a non-reply message to cloud.

        Used for :class:`EventEnvelope` and :class:`HookOutcome` —
        fire-and-forget.  Replies to commands go through
        :meth:`reply_to_cloud` instead so the cloud-side waiter can
        match by step_id.
        """
        ...

    async def reply_to_cloud(self, reply: BaseModel) -> None:
        """Local: send a reply correlated with an inbound command.

        ``reply.step_id`` must match the inbound command's step_id.
        """
        ...


class LoopbackTransport:
    """In-memory bidirectional transport for tests.

    Two queues + a step→future map for command/result correlation.
    Satisfies :class:`HybridTransport` by structural typing.

    Cloud writes → ``_to_local`` queue → local reads.
    Local writes (replies) → resolves the ``_pending[step_id]`` future.
    Local writes (non-replies) → ``_to_cloud`` queue (callers pull via
    :meth:`pop_cloud_messages` for assertions).
    """

    def __init__(self):
        self._to_local: asyncio.Queue[BaseModel] = asyncio.Queue()
        self._to_cloud: list[BaseModel] = []
        self._pending: dict[str, asyncio.Future[BaseModel]] = {}
        # If a reply arrives BEFORE send_to_local is awaited (rare race),
        # buffer it here keyed by step_id.
        self._reply_buffer: dict[str, BaseModel] = {}

    # ── cloud-side ──
    async def send_to_local(self, command: BaseModel) -> BaseModel:
        step_id = getattr(command, "step_id", None)
        if not step_id:
            raise ValueError("command must have step_id for correlation")
        loop = asyncio.get_running_loop()
        # Honour a buffered reply if it landed first.
        if step_id in self._reply_buffer:
            return self._reply_buffer.pop(step_id)
        fut: asyncio.Future[BaseModel] = loop.create_future()
        self._pending[step_id] = fut
        await self._to_local.put(command)
        try:
            return await fut
        finally:
            self._pending.pop(step_id, None)

    # ── local-side ──
    async def receive_command(self) -> BaseModel:
        return await self._to_local.get()

    async def send_to_cloud(self, message: BaseModel) -> None:
        self._to_cloud.append(message)

    async def reply_to_cloud(self, reply: BaseModel) -> None:
        step_id = getattr(reply, "step_id", "")
        if step_id and step_id in self._pending:
            self._pending[step_id].set_result(reply)
        else:
            # Buffer for late awaiters (race-tolerant).
            if step_id:
                self._reply_buffer[step_id] = reply

    # ── test inspection helpers ──
    def pop_cloud_messages(self) -> list[BaseModel]:
        msgs = list(self._to_cloud)
        self._to_cloud.clear()
        return msgs


# ============================================================================
# Cloud-side adapters — proxy local capabilities over the transport
# ============================================================================


def _next_step_id() -> str:
    """Generate a unique step_id for command correlation."""
    return uuid.uuid4().hex[:16]


class RpcBrowserPrimitives:
    """Cloud-side :class:`BrowserPrimitives` backed by a transport.

    Each method packages its args as a :class:`PrimitiveCommand` and
    awaits the matching :class:`PrimitiveResult`.  In hybrid_cloud mode
    this is what backs ``CloudHookContext.primitives`` (when a
    cloud_only hook needs DOM access — rare, but possible) and
    ``LocalReactiveContext.primitives`` (when running a local_reactive
    hook from the cloud side under sandboxed delegation — even rarer,
    not the primary path).

    For local-side hooks running on local: use the real in-process
    primitives, not this proxy.
    """

    def __init__(self, transport: HybridTransport, *, run_id: str):
        self._t = transport
        self._run_id = run_id

    async def _dispatch(self, op: _PrimitiveOp, params: dict[str, Any]) -> Any:
        cmd = PrimitiveCommand(
            run_id=self._run_id,
            step_id=_next_step_id(),
            op=op,
            params=params,
        )
        result = await self._t.send_to_local(cmd)
        if not isinstance(result, PrimitiveResult):
            raise RuntimeError(
                f"unexpected reply type for primitive op={op}: "
                f"{type(result).__name__}"
            )
        if not result.ok:
            # Re-raise so hook code sees a normal Python exception.
            # Best-effort to preserve original exception type so hook
            # code that catches specific types (ValueError, TimeoutError,
            # etc.) keeps working across the wire.
            err_msg = result.error or "primitive failed"
            err_type = result.error_type or "RuntimeError"
            import builtins
            exc_cls = getattr(builtins, err_type, None)
            if (not isinstance(exc_cls, type)
                    or not issubclass(exc_cls, BaseException)):
                exc_cls = RuntimeError
            raise exc_cls(err_msg)
        return result.value

    # ── BrowserPrimitives Protocol methods ──
    async def eval_js(self, snippet: str, *, timeout_ms: int = 3000) -> Any:
        return await self._dispatch(
            "eval_js", {"snippet": snippet, "timeout_ms": timeout_ms}
        )

    async def read_dom(self, selector: str, *, depth: int = 2) -> dict:
        return await self._dispatch(
            "read_dom", {"selector": selector, "depth": depth}
        )

    async def click(self, selector: str, *, timeout_ms: int = 3000) -> bool:
        return await self._dispatch(
            "click", {"selector": selector, "timeout_ms": timeout_ms}
        )

    async def type(
        self,
        selector: str,
        text: str,
        *,
        clear_first: bool = True,
        submit: bool = False,
    ) -> bool:
        return await self._dispatch(
            "type",
            {
                "selector": selector,
                "text": text,
                "clear_first": clear_first,
                "submit": submit,
            },
        )

    async def wait_for(
        self,
        selector: str,
        *,
        condition: str = "present",
        timeout_ms: int = 5000,
    ) -> bool:
        return await self._dispatch(
            "wait_for",
            {"selector": selector, "condition": condition, "timeout_ms": timeout_ms},
        )


class RpcScrapeFunction:
    """Cloud-side :class:`ScrapeFunction` proxy for a named local scraper.

    Wraps the cross-tier scrape RPC pattern from step 2f.  Production
    binding for ``cloud_only`` PreDispatch passes one of these as
    ``scrape_fn`` to :func:`pre_dispatch_v2.before_run_hook_v2`.

    The matching ``ScrapeResult.from_dict`` is supplied by the caller
    (``result_factory``) so this class stays generic — different
    bundles ship different result shapes.
    """

    def __init__(
        self,
        transport: HybridTransport,
        *,
        run_id: str,
        bundle: str,
        scraper: str,
        result_factory: Callable[[dict[str, Any]], Any],
    ):
        self._t = transport
        self._run_id = run_id
        self._bundle = bundle
        self._scraper = scraper
        self._result_factory = result_factory

    async def __call__(self, **params: Any) -> Any:
        req = ScrapeRequest(
            run_id=self._run_id,
            step_id=_next_step_id(),
            bundle=self._bundle,
            scraper=self._scraper,
            params=params,
        )
        result = await self._t.send_to_local(req)
        if not isinstance(result, ScrapeResponse):
            raise RuntimeError(
                f"unexpected reply for scrape req={self._scraper}: "
                f"{type(result).__name__}"
            )
        if not result.ok:
            raise RuntimeError(result.error or "scrape failed")
        return self._result_factory(result.payload)


# ============================================================================
# Local-side executors — receive commands and dispatch to real impls
# ============================================================================


class LocalPrimitiveExecutor:
    """Local-side service that consumes :class:`PrimitiveCommand`
    messages and dispatches them to a real :class:`BrowserPrimitives`
    implementation.

    Run via :meth:`run_one` (single command) or :meth:`run_loop`
    (forever, for the production service).  Each command's result is
    pushed back via ``transport.reply_to_cloud``.
    """

    def __init__(
        self,
        primitives: BrowserPrimitives,
        transport: HybridTransport,
    ):
        self._primitives = primitives
        self._t = transport

    async def run_one(self, cmd: PrimitiveCommand) -> PrimitiveResult:
        """Dispatch one command, return the result (also push it via
        transport).  Returned for testing convenience."""
        t0 = time.monotonic()
        try:
            value = await self._dispatch(cmd)
            result = PrimitiveResult(
                run_id=cmd.run_id,
                step_id=cmd.step_id,
                ok=True,
                value=value,
                elapsed_ms=int((time.monotonic() - t0) * 1000),
            )
        except Exception as exc:
            result = PrimitiveResult(
                run_id=cmd.run_id,
                step_id=cmd.step_id,
                ok=False,
                value=None,
                error=str(exc),
                error_type=type(exc).__name__,
                elapsed_ms=int((time.monotonic() - t0) * 1000),
            )
        await self._t.reply_to_cloud(result)
        return result

    async def _dispatch(self, cmd: PrimitiveCommand) -> Any:
        op = cmd.op
        p = cmd.params
        if op == "eval_js":
            return await self._primitives.eval_js(
                p["snippet"], timeout_ms=int(p.get("timeout_ms", 3000))
            )
        if op == "read_dom":
            return await self._primitives.read_dom(
                p["selector"], depth=int(p.get("depth", 2))
            )
        if op == "click":
            return await self._primitives.click(
                p["selector"], timeout_ms=int(p.get("timeout_ms", 3000))
            )
        if op == "type":
            return await self._primitives.type(
                p["selector"],
                p["text"],
                clear_first=bool(p.get("clear_first", True)),
                submit=bool(p.get("submit", False)),
            )
        if op == "wait_for":
            return await self._primitives.wait_for(
                p["selector"],
                condition=str(p.get("condition", "present")),
                timeout_ms=int(p.get("timeout_ms", 5000)),
            )
        raise ValueError(f"unknown primitive op: {op!r}")

    async def run_loop(self) -> None:
        """Run forever — for production binding.  Cancel the task to stop."""
        while True:
            cmd = await self._t.receive_command()
            if isinstance(cmd, PrimitiveCommand):
                await self.run_one(cmd)
            # Other inbound types (ScrapeRequest) are handled by
            # LocalScrapeExecutor running in parallel.


class LocalScrapeExecutor:
    """Local-side service that consumes :class:`ScrapeRequest` messages
    and dispatches them to registered scraper functions.

    Each scraper is registered as an async callable mapping ``(ctx,
    **params) -> result_with_to_dict``.  The executor wraps the call,
    serializes via ``result.to_dict()``, and replies.
    """

    def __init__(
        self,
        ctx: LocalExtractContext,
        transport: HybridTransport,
        *,
        scrapers: dict[tuple[str, str], Callable[..., Awaitable[Any]]] | None = None,
    ):
        self._ctx = ctx
        self._t = transport
        self._scrapers: dict[tuple[str, str], Callable[..., Awaitable[Any]]] = (
            scrapers or {}
        )

    def register(
        self,
        bundle: str,
        scraper: str,
        fn: Callable[..., Awaitable[Any]],
    ) -> None:
        """Register a scraper ``fn`` under ``(bundle, scraper)``.

        ``fn`` is an async callable.  Step 3 calls it as
        ``await fn(ctx, **req.params)``; the returned object must have
        a ``to_dict`` method.
        """
        self._scrapers[(bundle, scraper)] = fn

    async def run_one(self, req: ScrapeRequest) -> ScrapeResponse:
        key = (req.bundle, req.scraper)
        fn = self._scrapers.get(key)
        if fn is None:
            resp = ScrapeResponse(
                run_id=req.run_id,
                step_id=req.step_id,
                ok=False,
                error=f"unregistered scraper: {req.bundle}/{req.scraper}",
            )
            await self._t.reply_to_cloud(resp)
            return resp
        try:
            result = await fn(self._ctx, **req.params)
        except Exception as exc:
            resp = ScrapeResponse(
                run_id=req.run_id,
                step_id=req.step_id,
                ok=False,
                error=f"{type(exc).__name__}: {exc}",
            )
            await self._t.reply_to_cloud(resp)
            return resp
        # Result must have a ``to_dict`` method for wire serialization.
        try:
            payload = result.to_dict() if hasattr(result, "to_dict") else dict(result)
        except Exception as exc:
            resp = ScrapeResponse(
                run_id=req.run_id,
                step_id=req.step_id,
                ok=False,
                error=f"to_dict failed: {type(exc).__name__}: {exc}",
            )
            await self._t.reply_to_cloud(resp)
            return resp
        resp = ScrapeResponse(
            run_id=req.run_id,
            step_id=req.step_id,
            ok=True,
            payload=payload,
        )
        await self._t.reply_to_cloud(resp)
        return resp

    async def run_loop(self) -> None:
        """Run forever, dispatching ScrapeRequest messages."""
        while True:
            msg = await self._t.receive_command()
            if isinstance(msg, ScrapeRequest):
                await self.run_one(msg)
