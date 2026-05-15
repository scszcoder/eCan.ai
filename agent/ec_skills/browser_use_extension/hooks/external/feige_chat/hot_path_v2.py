"""Step 2g — port of ``hot_path.execute`` DOM orchestration to v2 surface.

The legacy :mod:`hot_path` module orchestrates Feige's HOT-PATH-B
action sequence directly against a browser-use session, an
``actions_registry`` dict keyed by tool name, and a private
``_evaluate_js`` helper.  This v2 port takes the same control flow
(typing-lock acquire, per-action verification, post-success tab
restore, finally-release) but replaces the three legacy dependencies
with two typed Protocol surfaces:

* :class:`BrowserPrimitives` — for ``eval_js`` + ``click`` + ``wait_for``
  used by the verification helpers and the post-success tab restore.

* :class:`ToolInvoker` — for the bundle-specific tool calls
  (``feige_open_session``, ``feige_send_message``).  In-process
  callers wrap a real ``actions_registry`` via :class:`RegistryToolInvoker`;
  hybrid_cloud callers can plug an RPC variant once step-5 lands.

* :class:`TypingLock` — already a Protocol; same surface, no change.

What's identical to v1
----------------------

Every decision branch (typing-lock wait loop, per-tool verification
attempts, intervals, abort reasons, post-success tab restore + sleep)
preserves the v1 timing constants and behaviour.  See
:func:`execute_v2` docstring for a side-by-side mapping.

What's intentionally different
------------------------------

* No ``inspect.signature(...)`` introspection — :class:`ToolInvoker`
  has a single typed surface (``invoke(name, args)``).
* No top-level dependency on ``extension_tools_service._evaluate_js``.
  Verification helpers receive primitives via the executor instance.
* No ``browser_session.get_current_page()`` for the tab restore —
  :meth:`BrowserPrimitives.click` is sufficient on Feige's SPA.

Tests
-----

See :mod:`tests.test_hot_path_v2`.  The test surface uses
:class:`StubPrimitives` and :class:`StubToolInvoker` so the executor
runs end-to-end without a real browser.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, runtime_checkable

from agent.ec_skills.browser_node.contexts import (
    BrowserPrimitives,
    TypingLock,
)

logger = logging.getLogger("eCan")

__all__ = [
    "ToolInvoker",
    "ToolResult",
    "RegistryToolInvoker",
    "HotPathOutcomeV2",
    "HotPathExecutorV2",
    "execute_v2",
    # Re-exposed for tests / monkey-patching
    "TYPING_LOCK_WAIT_ATTEMPTS",
    "TYPING_LOCK_WAIT_INTERVAL_S",
    "POST_OPEN_VERIFY_ATTEMPTS",
    "POST_OPEN_VERIFY_INTERVAL_S",
    "PRE_SEND_REVERIFY_ATTEMPTS",
    "PRE_SEND_REVERIFY_INTERVAL_S",
    "POST_SEND_TAB_RESTORE_SLEEP_S",
    "HOT_PATH_TOOL_TIMEOUT_S",
]


# ── Timing constants (identical to v1 hot_path module) ────────────────────
TYPING_LOCK_WAIT_ATTEMPTS: int = 120     # 120 × 100 ms = 12 s
TYPING_LOCK_WAIT_INTERVAL_S: float = 0.1
POST_OPEN_VERIFY_ATTEMPTS: int = 16       # 16 × 75 ms = 1.2 s
POST_OPEN_VERIFY_INTERVAL_S: float = 0.075
PRE_SEND_REVERIFY_ATTEMPTS: int = 16
PRE_SEND_REVERIFY_INTERVAL_S: float = 0.075
POST_SEND_TAB_RESTORE_SLEEP_S: float = 0.3
try:
    # Fix 16/18 (2026-05-13): 8.0 → 18.0 → 25.0;
    # 2026-05-14: 25.0 → 50.0 (paired with CDP eval bump to 45.0).
    # See hot_path.py for the full rationale.  Both modules share
    # ECAN_HOT_PATH_TOOL_TIMEOUT_S so a single env override changes both.
    HOT_PATH_TOOL_TIMEOUT_S: float = max(
        1.0,
        float(os.getenv("ECAN_HOT_PATH_TOOL_TIMEOUT_S", "50.0")),
    )
except Exception:
    HOT_PATH_TOOL_TIMEOUT_S = 50.0
ACTIVE_CUSTOMER_EVAL_TIMEOUT_S: float = 0.75
SOURCE_TURN_EVAL_TIMEOUT_S: float = 1.0

# ── Selectors / DOM contracts ─────────────────────────────────────────────
# Feige's current-conversation sub-tab. Keep the SPA on the live queue; the
# recent-contacts tab contains history/system rows with the same selectors.
CURRENT_CONVERSATION_TAB_SELECTOR: str = '[data-qa-id="qa-active-chat-tab"]'

# JS snippet that returns ``{ok, active}`` — the active customer's
# normalised name on the current Feige page.  Imported from the
# bundle's dom_assets so v2 stays in lock-step with v1's contract.
try:
    from .dom_assets import (
        FEIGE_ACTIVE_CUSTOMER_JS,
        FEIGE_LATEST_CUSTOMER_BUBBLE_JS,
        _normalize_dispatch_identity_key,
        _normalize_reply_text,
        verify_customer_match,
    )
except Exception:  # pragma: no cover — bundle import side-effects
    FEIGE_ACTIVE_CUSTOMER_JS = "({ok: false, active: ''})"
    FEIGE_LATEST_CUSTOMER_BUBBLE_JS = "({msg_id: '', text: ''})"
    def _normalize_dispatch_identity_key(s: str) -> str:  # type: ignore
        return (s or "").strip().lower()
    def _normalize_reply_text(s: str) -> str:  # type: ignore
        return (s or "").strip()[:120]
    def verify_customer_match(data: dict, expected: str) -> tuple[bool, str]:  # type: ignore
        active = str(data.get("active") or "").strip()
        return (active == str(expected or "").strip(), f"legacy-active={active!r}")


def _feige_cdp_health_cooldown_remaining() -> float:
    try:
        from agent.ec_skills.browser_use_extension import extension_tools_service as _ets
        remaining_fn = getattr(_ets, "feige_cdp_health_cooldown_remaining", None)
        if callable(remaining_fn):
            return max(0.0, float(remaining_fn()))
    except Exception:
        pass
    return 0.0


# ============================================================================
# ToolInvoker Protocol — replaces legacy ``actions_registry`` + ``inspect``
# ============================================================================


@dataclass
class ToolResult:
    """Result returned by :class:`ToolInvoker.invoke`.

    Mirrors the surface the legacy executor consumed via
    ``getattr(result, 'error', None)`` and
    ``getattr(result, 'extracted_content', '')``.  Using an explicit
    dataclass lets v2 callers / tests build results without touching
    browser-use internals.
    """

    ok: bool = True
    error: str = ""
    extracted_content: Any = None


@runtime_checkable
class ToolInvoker(Protocol):
    """Bundle-specific tool invocation surface.

    The HOT-PATH-B executor calls ``invoke('feige_open_session', {...})``
    and ``invoke('feige_send_message', {...})``.  Production binding
    wraps the live ``actions_registry`` (see :class:`RegistryToolInvoker`);
    tests use a stub.  A future hybrid_cloud binding can implement this
    Protocol over the transport.
    """

    async def invoke(self, name: str, args: dict[str, Any]) -> ToolResult:
        """Invoke a registered tool by *name* with *args*."""
        ...


class RegistryToolInvoker:
    """In-process :class:`ToolInvoker` that wraps a browser-use
    ``actions_registry`` + ``browser_session``.

    This is the production binding for ``full_local`` mode.  It
    preserves the v1 introspection: forwards ``browser_session`` only
    when the underlying tool function accepts that parameter.  Errors
    surface via :class:`ToolResult` (no exceptions out the top).
    """

    def __init__(self, actions_registry: dict, browser_session: Any):
        self._reg = actions_registry
        self._sess = browser_session

    async def invoke(self, name: str, args: dict[str, Any]) -> ToolResult:
        act_obj = self._reg.get(name)
        if act_obj is None:
            return ToolResult(ok=False, error=f"tool_not_found:{name}")
        try:
            params = act_obj.param_model(**args)
        except Exception as exc:
            return ToolResult(
                ok=False, error=f"param_validation_failed:{exc}"
            )
        try:
            import inspect as _inspect
            sig = _inspect.signature(act_obj.function)
            if "browser_session" in sig.parameters:
                raw = await asyncio.wait_for(
                    act_obj.function(params=params, browser_session=self._sess),
                    timeout=HOT_PATH_TOOL_TIMEOUT_S,
                )
            else:
                raw = await asyncio.wait_for(
                    act_obj.function(params=params),
                    timeout=HOT_PATH_TOOL_TIMEOUT_S,
                )
        except asyncio.TimeoutError:
            return ToolResult(
                ok=False,
                error=f"tool timed out after {HOT_PATH_TOOL_TIMEOUT_S:.1f}s",
            )
        except Exception as exc:
            return ToolResult(ok=False, error=f"tool_raised:{exc}")
        if raw is None:
            return ToolResult(ok=False, error="action returned None")
        err = getattr(raw, "error", None)
        if err:
            return ToolResult(ok=False, error=str(err))
        return ToolResult(
            ok=True,
            extracted_content=getattr(raw, "extracted_content", None),
        )


# ============================================================================
# Outcome dataclass (compatible with v1 HotPathOutcome shape)
# ============================================================================


@dataclass
class HotPathOutcomeV2:
    """Result of :func:`execute_v2`.

    Field-compatible superset of the v1 :class:`HotPathOutcome` so
    code that consumes the old shape works unchanged after a swap.
    """

    ok: bool = False
    reason: str = ""
    typing_acquired: bool = False
    last_tool_error: str = ""
    actions_attempted: int = 0
    extras: dict = field(default_factory=dict)


# ============================================================================
# Verification helpers — pure functions over BrowserPrimitives
# ============================================================================


async def _verify_active_customer(
    primitives: BrowserPrimitives,
    expected: str,
    *,
    attempts: int = 1,
    interval: float = 0.075,
    expected_as_key: bool = True,
) -> tuple[bool, str]:
    """Poll ``FEIGE_ACTIVE_CUSTOMER_JS`` up to *attempts* times.

    Identical semantics to v1 ``_verify_active_customer`` — same JSON
    decoding, same key-normalisation, same return shape.
    """
    active_last = ""
    for _ in range(attempts):
        try:
            raw = await asyncio.wait_for(
                primitives.eval_js(FEIGE_ACTIVE_CUSTOMER_JS),
                timeout=ACTIVE_CUSTOMER_EVAL_TIMEOUT_S,
            )
            data = raw
            if isinstance(raw, str):
                try:
                    data = json.loads(raw)
                except Exception:
                    data = {}
            if isinstance(data, dict) and data.get("ok"):
                active_last = str(
                    data.get("active")
                    or data.get("header_name")
                    or data.get("sidebar_name")
                    or ""
                ).strip()
                has_split_signals = (
                    "sidebar_name" in data or "header_name" in data
                )
                if has_split_signals:
                    ok, reason = verify_customer_match(data, expected)
                    if ok:
                        return True, active_last
                    active_last = f"{active_last or '<none>'}; {reason}"
                elif expected_as_key:
                    if _normalize_dispatch_identity_key(active_last) == expected:
                        return True, active_last
                else:
                    if active_last == str(expected).strip():
                        return True, active_last
        except Exception:
            pass
        if attempts > 1:
            await asyncio.sleep(interval)
    return False, active_last


async def _post_open_verify(
    primitives: BrowserPrimitives,
    resolved_args: dict,
    node_name: str,
) -> tuple[bool, str]:
    """Crosstalk guard after ``feige_open_session`` returns OK."""
    expected = (
        resolved_args.get("customer_name")
        or resolved_args.get("customer_id")
        or ""
    )
    if not expected:
        return True, ""
    ok, active = await _verify_active_customer(
        primitives, expected,
        attempts=POST_OPEN_VERIFY_ATTEMPTS,
        interval=POST_OPEN_VERIFY_INTERVAL_S,
        expected_as_key=False,
    )
    if not ok:
        logger.error(
            f"[hot_path_v2] ABORT send — active-customer verification "
            f"failed after feige_open_session: expected={expected!r} "
            f"active={active!r}. Crosstalk guard tripped, node={node_name}"
        )
        return False, "post_open_verify_failed"
    logger.info(
        f"[hot_path_v2] active-customer verified = {active!r} after "
        f"feige_open_session"
    )
    return True, ""


async def _pre_send_reverify(
    primitives: BrowserPrimitives,
    invoker: ToolInvoker,
    customer_key: str,
    node_name: str,
) -> tuple[bool, str]:
    """Re-verify and (on drift) re-open inline before ``feige_send_message``."""
    ok, active = await _verify_active_customer(
        primitives, customer_key, attempts=1
    )
    if ok:
        return True, ""
    logger.warning(
        f"[hot_path_v2] pre-send DRIFT — expected={customer_key!r} "
        f"active={active!r}; re-opening session before typing, node={node_name}"
    )
    # Best-effort re-open.  Errors are swallowed so the recovery poll
    # has a chance to succeed even if the re-open call itself raised.
    try:
        await invoker.invoke("feige_open_session", {"customer_name": customer_key})
    except Exception as exc:  # pragma: no cover — defensive
        logger.debug(f"[hot_path_v2] re-open feige_open_session errored: {exc}")
    recovered_ok, recovered_active = await _verify_active_customer(
        primitives, customer_key,
        attempts=PRE_SEND_REVERIFY_ATTEMPTS,
        interval=PRE_SEND_REVERIFY_INTERVAL_S,
    )
    if not recovered_ok:
        logger.error(
            f"[hot_path_v2] ABORT send — pre-send re-verify failed after "
            f"re-open: expected={customer_key!r} active={recovered_active!r}, "
            f"node={node_name}"
        )
        return False, "pre_send_reverify_failed"
    logger.info(
        f"[hot_path_v2] pre-send re-verify recovered — active now "
        f"{recovered_active!r}, node={node_name}"
    )
    return True, ""


def _source_customer_msg_id(payload: dict) -> str:
    if not isinstance(payload, dict):
        return ""
    return str(
        payload.get("source_customer_msg_id")
        or payload.get("latest_message_msg_id")
        or payload.get("reply_to_msg_id")
        or ""
    ).strip()


def _source_customer_text(payload: dict) -> str:
    if not isinstance(payload, dict):
        return ""
    return str(
        payload.get("source_latest_message")
        or payload.get("latest_message")
        or payload.get("latest_message_text")
        or ""
    ).strip()


async def _verify_reply_source_turn_v2(
    primitives: BrowserPrimitives,
    payload: dict,
    *,
    node_name: str,
    outcome: HotPathOutcomeV2,
) -> tuple[bool, str]:
    expected_msg_id = _source_customer_msg_id(payload)
    expected_text = _source_customer_text(payload)

    try:
        raw = await asyncio.wait_for(
            primitives.eval_js(FEIGE_LATEST_CUSTOMER_BUBBLE_JS),
            timeout=SOURCE_TURN_EVAL_TIMEOUT_S,
        )
        if isinstance(raw, str):
            try:
                data = json.loads(raw)
            except Exception:
                data = {}
        else:
            data = raw if isinstance(raw, dict) else {}
        actual_msg_id = str(data.get("msg_id") or "").strip()
        actual_text = str(data.get("text") or "").strip()
    except Exception as exc:
        actual_msg_id = ""
        actual_text = ""
        logger.warning(
            f"[hot_path_v2] source-turn verification eval failed: "
            f"{type(exc).__name__}: {exc}; refusing to type reply for "
            f"source_msg_id=...{expected_msg_id[-8:] if expected_msg_id else '<none>'}, node={node_name}"
        )

    if actual_msg_id and actual_msg_id == expected_msg_id:
        logger.info(
            f"[hot_path_v2] source-turn verified "
            f"msg_id=...{expected_msg_id[-8:]}, node={node_name}"
        )
        return True, ""

    if expected_text and _normalize_reply_text(actual_text) == _normalize_reply_text(expected_text):
        if not expected_msg_id:
            logger.info(
                f"[hot_path_v2] source-turn verified by text (no msg_id), "
                f"text={expected_text[:80]!r}, node={node_name}"
            )
            return True, ""
        if not actual_msg_id:
            logger.info(
                f"[hot_path_v2] source-turn verified by text fallback "
                f"because active msg_id is empty; expected_msg_id="
                f"...{expected_msg_id[-8:]}, node={node_name}"
            )
            return True, ""

    if not expected_msg_id and not expected_text:
        return True, ""

    outcome.extras["expected_source_customer_msg_id"] = expected_msg_id
    outcome.extras["active_customer_msg_id"] = actual_msg_id
    outcome.extras["active_customer_text_preview"] = actual_text[:80]
    logger.warning(
        f"[hot_path_v2] DROP stale reply — source customer msg_id="
        f"...{expected_msg_id[-8:]} no longer matches latest visible "
        f"customer bubble msg_id=..."
        f"{actual_msg_id[-8:] if actual_msg_id else '<none>'}; "
        f"latest_text={actual_text[:80]!r}, node={node_name}"
    )
    return False, "stale_reply_source_msg_id"


async def _restore_current_conversation_tab(
    primitives: BrowserPrimitives,
    node_name: str,
) -> None:
    """Click Feige's current-conversation sub-tab; non-fatal on failure."""
    try:
        clicked = await asyncio.wait_for(
            primitives.click(CURRENT_CONVERSATION_TAB_SELECTOR),
            timeout=ACTIVE_CUSTOMER_EVAL_TIMEOUT_S,
        )
        if clicked:
            await asyncio.sleep(POST_SEND_TAB_RESTORE_SLEEP_S)
            logger.info(
                f"[hot_path_v2] switched back to current-conversation tab, node={node_name}"
            )
    except Exception as exc:
        logger.debug(f"[hot_path_v2] tab switch failed: {exc}")


# ============================================================================
# Executor — orchestrates one HOT-PATH-B action sequence
# ============================================================================


class HotPathExecutorV2:
    """v2 HOT-PATH-B executor satisfying
    :class:`front_desk_hot_path_v2.HotPathExecutor` Protocol.

    Constructor wires the two backends; :meth:`execute` runs a single
    sequence and returns a :class:`HotPathOutcomeV2`.  The same
    instance can be reused across many calls.
    """

    def __init__(
        self,
        primitives: BrowserPrimitives,
        invoker: ToolInvoker,
        typing_lock: TypingLock,
    ):
        self._prim = primitives
        self._invoker = invoker
        self._lock = typing_lock

    # ── public ──
    async def execute(
        self,
        *,
        customer_key: str,
        action_seq: list[dict],
        payload: dict,
        resolve_template: Callable[[Any, dict], Any],
        node_name: str = "",
    ) -> HotPathOutcomeV2:
        return await execute_v2(
            primitives=self._prim,
            invoker=self._invoker,
            typing_lock=self._lock,
            customer_key=customer_key,
            action_seq=action_seq,
            payload=payload,
            resolve_template=resolve_template,
            node_name=node_name,
        )


# ============================================================================
# Functional entry point — preserved for callers that prefer free functions
# ============================================================================


async def _acquire_typing_lock(
    typing_lock: TypingLock, customer_key: str, node_name: str,
) -> bool:
    """Bounded-wait typing-lock acquire (identical to v1 timing)."""
    if not customer_key:
        return False
    for _ in range(TYPING_LOCK_WAIT_ATTEMPTS):
        if typing_lock.try_acquire(customer_key):
            logger.info(
                f"[hot_path_v2] acquired Feige typing lock "
                f"cust={customer_key!r}, node={node_name}"
            )
            return True
        await asyncio.sleep(TYPING_LOCK_WAIT_INTERVAL_S)
    logger.warning(
        f"[hot_path_v2] could not acquire typing lock cust={customer_key!r} "
        f"within {TYPING_LOCK_WAIT_ATTEMPTS * TYPING_LOCK_WAIT_INTERVAL_S:.1f}s "
        f"(holder={typing_lock.holder()!r}); aborting guarded send, node={node_name}"
    )
    return False


async def _run_one_action(
    act: dict,
    *,
    primitives: BrowserPrimitives,
    invoker: ToolInvoker,
    payload: dict,
    resolve_template: Callable[[Any, dict], Any],
    customer_key: str,
    node_name: str,
    outcome: HotPathOutcomeV2,
) -> bool:
    """Execute one action.  Returns True to continue, False to abort."""
    outcome.actions_attempted += 1
    tool_name = act.get("tool", "")
    resolved_args = {
        k: resolve_template(v, payload) for k, v in act.get("args", {}).items()
    }

    # Pre-send re-verify (Fix A in v1, line-for-line preserved).
    if tool_name == "feige_send_message" and customer_key:
        resolved_args.setdefault("customer_name", customer_key)
        source_msg_id = _source_customer_msg_id(payload)
        source_text = _source_customer_text(payload)
        if source_msg_id:
            resolved_args.setdefault("source_customer_msg_id", source_msg_id)
        if source_text:
            resolved_args.setdefault("source_latest_message", source_text)
        ok, reason = await _pre_send_reverify(
            primitives, invoker, customer_key, node_name,
        )
        if not ok:
            outcome.reason = reason
            return False
        ok, reason = await _verify_reply_source_turn_v2(
            primitives,
            payload,
            node_name=node_name,
            outcome=outcome,
        )
        if not ok:
            outcome.reason = reason
            return False

    # Invoke the tool.
    result = await invoker.invoke(tool_name, resolved_args)
    if not result.ok:
        if (
            tool_name == "feige_open_session"
            and "timed out after" in (result.error or "")
        ):
            outcome.last_tool_error = result.error
            outcome.extras["open_session_timeout"] = result.error
            logger.warning(
                f"[hot_path_v2] {tool_name} timed out args={resolved_args}; "
                f"continuing to feige_send_message self-open fallback"
            )
            return True
        # Distinguish missing tool vs failure.
        if result.error.startswith("tool_not_found:"):
            outcome.reason = result.error
        else:
            outcome.last_tool_error = result.error
            outcome.reason = f"tool_failed:{tool_name}"
        logger.warning(
            f"[hot_path_v2] {tool_name} → FAIL args={resolved_args} "
            f"error={result.error!r}"
        )
        return False

    logger.info(
        f"[hot_path_v2] {tool_name} → OK args={resolved_args} "
        f"extracted={result.extracted_content!r}"
    )

    # Post-open crosstalk guard.
    if tool_name == "feige_open_session":
        ok, reason = await _post_open_verify(
            primitives, resolved_args, node_name,
        )
        if not ok:
            outcome.reason = reason
            return False

    delay_ms = act.get("delay_after_ms", 300)
    await asyncio.sleep(float(delay_ms) / 1000.0)
    return True


async def execute_v2(
    *,
    primitives: BrowserPrimitives,
    invoker: ToolInvoker,
    typing_lock: TypingLock,
    customer_key: str,
    action_seq: list[dict],
    payload: dict,
    resolve_template: Callable[[Any, dict], Any],
    node_name: str = "",
) -> HotPathOutcomeV2:
    """Run a Feige HOT-PATH-B action sequence using v2 surfaces.

    Behaviour matches v1 ``hot_path.execute`` line-for-line:

    1. Acquire typing lock (bounded wait).
    2. Loop ``action_seq``, invoking each tool via :class:`ToolInvoker`.
       * Pre-send re-verify on ``feige_send_message`` with re-open recovery.
       * Post-open crosstalk-guard verification on ``feige_open_session``.
       * Per-action settle delay (``delay_after_ms``, default 300).
    3. On full success: click ``当前会话`` to restore tab state.
    4. ``finally``: release typing lock on every exit path.

    Differences from v1 are documented in module docstring; none of
    them affect the decision tree.
    """
    outcome = HotPathOutcomeV2()
    cooldown_remaining = _feige_cdp_health_cooldown_remaining()
    if cooldown_remaining > 0.0:
        outcome.ok = False
        outcome.reason = "cdp_health_cooldown_active"
        outcome.last_tool_error = f"cdp_health_cooldown_active {cooldown_remaining:.1f}s"
        outcome.extras["cooldown_remaining_s"] = round(cooldown_remaining, 3)
        logger.warning(
            f"[hot_path_v2] Feige CDP health cooldown active for "
            f"{cooldown_remaining:.1f}s; deferring guarded send, node={node_name}"
        )
        return outcome
    outcome.typing_acquired = await _acquire_typing_lock(
        typing_lock, customer_key, node_name,
    )
    if customer_key and not outcome.typing_acquired:
        outcome.ok = False
        outcome.reason = "typing_lock_busy"
        return outcome

    try:
        for act in action_seq:
            if not await _run_one_action(
                act,
                primitives=primitives,
                invoker=invoker,
                payload=payload,
                resolve_template=resolve_template,
                customer_key=customer_key,
                node_name=node_name,
                outcome=outcome,
            ):
                break
        else:
            # Loop completed every action without break → success.  The
            # for-else also runs when action_seq is empty, preserving
            # v1's "empty sequence = success" behaviour.
            outcome.ok = True
            outcome.reason = "all_ok"
            await _restore_current_conversation_tab(primitives, node_name)
    except Exception as exc:
        logger.warning(
            f"[hot_path_v2] executor exception: {exc}", exc_info=True,
        )
        outcome.ok = False
        if not outcome.reason:
            outcome.reason = f"exception:{exc}"
    finally:
        if outcome.typing_acquired and customer_key:
            try:
                typing_lock.release(customer_key)
            except Exception:
                pass

    return outcome
