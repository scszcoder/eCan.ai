"""Feige-specific HOT-PATH-B action executor.

Phase 4 relocation (2026-04-23).  The ~440 lines of Feige DOM
orchestration that used to sit inline inside ``build_node._auto``'s
HOT-PATH-B block are relocated here so the generic ``browser_automation``
node no longer carries site-specific selector knowledge.

What this module owns
---------------------

* **Pre-action tab focus** — switch the session to a Feige tab and
  click the ``当前会话`` inner sub-tab if needed.  Delegates to
  :func:`dom_assets.ensure_feige_tab_focused`.

* **Typing lock** — claim the Feige active-session for this customer
  (3 s wait) so parallel PreDispatch scrapes can't steal the session
  between our ``feige_open_session`` and ``feige_send_message``.
  Delegates to :mod:`.typing_lock`.

* **Action sequence execution with per-tool verification** —

  - ``feige_open_session`` → post-open active-customer verification
    polled for up to 8 × 75 ms.  ABORT the whole sequence on confirmed
    mismatch (the crosstalk guard that prevents 客户A's answer from
    landing in 客户C's chat).

  - ``feige_send_message`` → pre-send re-verify + inline re-open
    recovery.  If the active customer drifted between open and send
    (CDP/render race), re-open and poll again.  If recovery fails,
    ABORT the send.

* **Post-success tab restore** — click ``当前会话`` again so future DOM
  reads stay on the live customer queue, not recent-contact history.

* **Typing-lock release on all exit paths** — including the defensive
  outer ``except`` so a mid-sequence exception can't leave the lock
  stuck until TTL expiry.

What this module does **not** own
---------------------------------

* Payload extraction from LangGraph state — generic plumbing, stays
  in ``build_node``.
* Rule matching against ``hotPathActions`` config — generic, stays in
  ``build_node``.
* Dedup cache / cooldown bookkeeping / ``assigned_sessions`` eviction
  / ``qa_response_pending`` release — these interact with module-level
  state in ``build_node`` and the ``agent.mcp`` chat tools; the
  executor reports success/failure and the caller does the
  bookkeeping.

Why this split
--------------

Half A of HOT-PATH-B (payload extraction, dedup, bookkeeping,
cross-customer bleed detection) is *generic LangGraph-state* plumbing
that will apply to any future deterministic hot-path — including for
sites other than Feige.  Keeping it in ``build_node`` prevents
coupling generic state logic to a single site bundle.  Half B (this
module) is 100% Feige-specific: selectors, sub-tab names, DOM
verification.  Extracting only Half B removes 440 lines of site code
from the core node without mis-locating generic logic.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Callable

from . import typing_lock
from .dom_assets import (
    FEIGE_ACTIVE_CUSTOMER_JS,
    FEIGE_LATEST_CUSTOMER_BUBBLE_JS,
    ensure_feige_tab_focused,
    _normalize_dispatch_identity_key,
    _normalize_reply_text,
    verify_customer_match,
)

logger = logging.getLogger("eCan")

__all__ = ["HotPathOutcome", "execute"]


# Timeouts / retry counts are module-level constants so the caller or a
# future test can monkey-patch them without touching the executor body.
TYPING_LOCK_WAIT_ATTEMPTS: int = 120     # 120 × 100 ms = 12 s
TYPING_LOCK_WAIT_INTERVAL_S: float = 0.1
POST_OPEN_VERIFY_ATTEMPTS: int = 16       # 16 × 75 ms = 1.2 s
POST_OPEN_VERIFY_INTERVAL_S: float = 0.075
PRE_SEND_REVERIFY_ATTEMPTS: int = 16
PRE_SEND_REVERIFY_INTERVAL_S: float = 0.075
POST_SEND_TAB_RESTORE_SLEEP_S: float = 0.3
try:
    HOT_PATH_TOOL_TIMEOUT_S: float = max(
        1.0,
        float(os.getenv("ECAN_HOT_PATH_TOOL_TIMEOUT_S", "8.0")),
    )
except Exception:
    HOT_PATH_TOOL_TIMEOUT_S = 8.0


@dataclass
class HotPathOutcome:
    """Result of ``execute(...)``.

    Attributes
    ----------
    ok:
        ``True`` iff every action in the sequence ran successfully
        **and** all Feige verifications (post-open, pre-send) passed.
        The caller should perform its success-path bookkeeping
        (dedup-mark, clear inflight, evict assigned session, etc.)
        iff ``ok`` is ``True``.
    reason:
        Short tag describing the exit path.  Values:
          ``"all_ok"`` / ``"tool_failed:<tool>"`` /
          ``"post_open_verify_failed"`` / ``"pre_send_reverify_failed"`` /
          ``"typing_lock_unavailable"`` / ``"tool_not_found:<tool>"`` /
          ``"exception:<msg>"``.
    typing_acquired:
        Whether we acquired the typing lock for this customer.  Used
        by the caller only if it needs to call ``typing_lock.release``
        manually — the executor already releases on every exit path.
    last_tool_error:
        The ``error`` attribute of the last failed action result (if
        any), for caller logging.
    """

    ok: bool = False
    reason: str = ""
    typing_acquired: bool = False
    last_tool_error: str = ""
    actions_attempted: int = 0
    extras: dict = field(default_factory=dict)


async def _acquire_typing_lock(customer_key: str, node_name: str) -> bool:
    """Claim Feige's per-customer typing lock with a bounded wait.

    Waits up to ``TYPING_LOCK_WAIT_ATTEMPTS x INTERVAL_S`` for a prior
    holder to release. Returns ``True`` on success, ``False`` if the
    timeout elapsed. Callers must fail closed rather than type without
    the guard.
    """
    if not customer_key:
        return False
    for _ in range(TYPING_LOCK_WAIT_ATTEMPTS):
        if typing_lock.try_acquire(customer_key):
            logger.info(
                f"[BrowserAutomation] HOT-PATH-B: acquired Feige typing "
                f"lock for cust={customer_key!r}, node={node_name}"
            )
            return True
        await asyncio.sleep(TYPING_LOCK_WAIT_INTERVAL_S)
    logger.warning(
        f"[BrowserAutomation] HOT-PATH-B: could not acquire Feige typing "
        f"lock for cust={customer_key!r} within "
        f"{TYPING_LOCK_WAIT_ATTEMPTS * TYPING_LOCK_WAIT_INTERVAL_S:.1f}s "
        f"(current holder={typing_lock.holder()!r}); aborting guarded send, "
        f"node={node_name}"
    )
    return False


async def _invoke_tool(act_obj, params, browser_session):
    """Dispatch a browser_use registry action, forwarding browser_session
    only if the underlying function accepts it.
    """
    sig = inspect.signature(act_obj.function)
    if "browser_session" in sig.parameters:
        return await act_obj.function(params=params, browser_session=browser_session)
    return await act_obj.function(params=params)


async def _reopen_feige_session(actions_registry: dict, browser_session, customer_key: str) -> None:
    """Best-effort re-call of ``feige_open_session`` for *customer_key*.

    Used by the pre-send re-verify path to recover from late-committing
    click events that swapped the active session between our earlier
    open-session verification and the imminent send.
    """
    reopen_obj = actions_registry.get("feige_open_session")
    if not reopen_obj:
        return
    try:
        reopen_params = reopen_obj.param_model(customer_name=customer_key)
        await _invoke_tool(reopen_obj, reopen_params, browser_session)
    except Exception as exc:
        logger.debug(
            f"[BrowserAutomation] HOT-PATH-B: re-open feige_open_session "
            f"errored: {exc}"
        )


async def _pre_send_reverify(
    browser_session,
    eval_js: Callable,
    customer_key: str,
    actions_registry: dict,
    node_name: str,
) -> tuple[bool, str]:
    """Immediately before ``feige_send_message``, re-check the active
    customer.  On drift: re-open inline and poll.  On failed recovery:
    return ``(False, "pre_send_reverify_failed")`` so the caller aborts.
    """
    ok, active = await _verify_active_customer(
        browser_session, eval_js, customer_key, attempts=1
    )
    if ok:
        return True, ""
    logger.warning(
        f"[BrowserAutomation] HOT-PATH-B: pre-send active-customer DRIFT "
        f"detected — expected={customer_key!r} active={active!r}; "
        f"re-opening session before typing, node={node_name}"
    )
    await _reopen_feige_session(actions_registry, browser_session, customer_key)
    recovered_ok, recovered_active = await _verify_active_customer(
        browser_session,
        eval_js,
        customer_key,
        attempts=PRE_SEND_REVERIFY_ATTEMPTS,
        interval=PRE_SEND_REVERIFY_INTERVAL_S,
    )
    if not recovered_ok:
        logger.error(
            f"[BrowserAutomation] HOT-PATH-B: ABORT send — pre-send "
            f"re-verify failed after re-open: expected={customer_key!r} "
            f"active={recovered_active!r}. Refusing to type into the "
            f"wrong session, node={node_name}"
        )
        return False, "pre_send_reverify_failed"
    logger.info(
        f"[BrowserAutomation] HOT-PATH-B: pre-send re-verify recovered — "
        f"active now {recovered_active!r}, node={node_name}"
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


async def _verify_reply_source_turn(
    browser_session,
    eval_js: Callable,
    payload: dict,
    *,
    node_name: str,
    outcome: "HotPathOutcome",
) -> tuple[bool, str]:
    """Fail closed when a reply was generated for an older customer bubble.

    Sender/recipient IDs route the Q&A response back to the front-desk
    agent, but Feige typing still has to prove the visible customer thread is
    on the same customer-bubble msg_id that was dispatched to Q&A.
    """
    expected_msg_id = _source_customer_msg_id(payload)
    expected_text = str(
        payload.get("source_latest_message")
        or payload.get("latest_message")
        or payload.get("latest_message_text")
        or ""
    ).strip()

    try:
        raw = await eval_js(browser_session, FEIGE_LATEST_CUSTOMER_BUBBLE_JS)
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
            f"[BrowserAutomation] HOT-PATH-B: source-turn verification "
            f"eval failed: {type(exc).__name__}: {exc}; refusing to type "
            f"reply for source_msg_id=...{expected_msg_id[-8:] if expected_msg_id else '<none>'}, "
            f"node={node_name}"
        )

    if actual_msg_id and actual_msg_id == expected_msg_id:
        logger.info(
            f"[BrowserAutomation] HOT-PATH-B: source-turn verified "
            f"msg_id=...{expected_msg_id[-8:]}, node={node_name}"
        )
        return True, ""

    if expected_text and _normalize_reply_text(actual_text) == _normalize_reply_text(expected_text):
        if not expected_msg_id:
            logger.info(
                f"[BrowserAutomation] HOT-PATH-B: source-turn verified "
                f"by text (no msg_id), text={expected_text[:80]!r}, "
                f"node={node_name}"
            )
            return True, ""
        if not actual_msg_id:
            logger.info(
                f"[BrowserAutomation] HOT-PATH-B: source-turn verified "
                f"by text fallback because active msg_id is empty; "
                f"expected_msg_id=...{expected_msg_id[-8:]}, node={node_name}"
            )
            return True, ""

    if not expected_msg_id and not expected_text:
        return True, ""

    outcome.extras["expected_source_customer_msg_id"] = expected_msg_id
    outcome.extras["active_customer_msg_id"] = actual_msg_id
    outcome.extras["active_customer_text_preview"] = actual_text[:80]
    logger.warning(
        f"[BrowserAutomation] HOT-PATH-B: DROP stale reply — source "
        f"customer msg_id=...{expected_msg_id[-8:]} no longer matches "
        f"latest visible customer bubble msg_id="
        f"...{actual_msg_id[-8:] if actual_msg_id else '<none>'}; "
        f"latest_text={actual_text[:80]!r}, node={node_name}"
    )
    return False, "stale_reply_source_msg_id"


async def _post_open_verify(
    browser_session,
    eval_js: Callable,
    resolved_args: dict,
    node_name: str,
) -> tuple[bool, str]:
    """After ``feige_open_session`` returns OK, poll the active-customer
    DOM state for up to 600 ms.  On confirmed mismatch return
    ``(False, "post_open_verify_failed")`` so the caller aborts the
    rest of the sequence (the crosstalk guard).
    """
    expected = (
        resolved_args.get("customer_name")
        or resolved_args.get("customer_id")
        or ""
    )
    if not expected:
        return True, ""
    ok, active = await _verify_active_customer(
        browser_session,
        eval_js,
        expected,
        attempts=POST_OPEN_VERIFY_ATTEMPTS,
        interval=POST_OPEN_VERIFY_INTERVAL_S,
        expected_as_key=False,
    )
    if not ok:
        logger.error(
            f"[BrowserAutomation] HOT-PATH-B: ABORT send — active-customer "
            f"verification failed after feige_open_session: "
            f"expected={expected!r} active={active!r}. Refusing to type "
            f"reply into the wrong session (crosstalk guard), "
            f"node={node_name}"
        )
        return False, "post_open_verify_failed"
    logger.info(
        f"[BrowserAutomation] HOT-PATH-B: active-customer verified = "
        f"{active!r} after feige_open_session"
    )
    return True, ""


async def _restore_feige_tab(browser_session, node_name: str) -> None:
    """Click Feige's current-conversation sub-tab after a successful send."""
    try:
        page = await browser_session.get_current_page()
        if not page:
            return
        tab = await page.query_selector('[data-qa-id="qa-active-chat-tab"]')
        if not tab:
            return
        await tab.click()
        await asyncio.sleep(POST_SEND_TAB_RESTORE_SLEEP_S)
        logger.info(
            f"[BrowserAutomation] HOT-PATH-B: switched back to "
            f"current-conversation tab, node={node_name}"
        )
    except Exception as exc:
        logger.debug(
            f"[BrowserAutomation] HOT-PATH-B: tab switch failed: {exc}"
        )


async def _run_one_action(
    act: dict,
    *,
    actions_registry: dict,
    payload: dict,
    resolve_template: Callable,
    browser_session,
    eval_js: Callable,
    customer_key: str,
    node_name: str,
    outcome: "HotPathOutcome",
) -> bool:
    """Execute one action from ``action_seq``.

    Returns ``True`` if the outer loop should continue, ``False`` if it
    should abort.  Mutates *outcome* in place (``actions_attempted``,
    ``reason``, ``last_tool_error``).
    """
    outcome.actions_attempted += 1
    tool_name = act.get("tool", "")
    resolved_args = {
        k: resolve_template(v, payload) for k, v in act.get("args", {}).items()
    }
    act_obj = actions_registry.get(tool_name)
    if not act_obj:
        logger.warning(
            f"[BrowserAutomation] HOT-PATH-B: tool {tool_name!r} not found"
        )
        outcome.reason = f"tool_not_found:{tool_name}"
        return False

    # Pre-send re-verify (2026-04-22 Fix A).
    if tool_name == "feige_send_message" and customer_key:
        resolved_args.setdefault("customer_name", customer_key)
        ok, reason = await _pre_send_reverify(
            browser_session, eval_js, customer_key, actions_registry, node_name
        )
        if not ok:
            outcome.reason = reason
            return False
        ok, reason = await _verify_reply_source_turn(
            browser_session,
            eval_js,
            payload,
            node_name=node_name,
            outcome=outcome,
        )
        if not ok:
            outcome.reason = reason
            return False

    # Call the tool.  Bound each browser action so a contended CDP
    # Runtime.evaluate cannot park HOT-PATH-B until the whole task
    # times out while the customer waits.
    params = act_obj.param_model(**resolved_args)
    timed_out = False
    try:
        result = await asyncio.wait_for(
            _invoke_tool(act_obj, params, browser_session),
            timeout=HOT_PATH_TOOL_TIMEOUT_S,
        )
    except asyncio.TimeoutError:
        timed_out = True
        result = None
    action_ok = result and not getattr(result, "error", None)
    if not action_ok:
        err_msg = (
            getattr(result, "error", None)
            if result is not None
            else (
                f"tool timed out after {HOT_PATH_TOOL_TIMEOUT_S:.1f}s"
                if timed_out
                else "action returned None"
            )
        )
        if tool_name == "feige_open_session" and timed_out:
            outcome.last_tool_error = str(err_msg or "")
            outcome.extras["open_session_timeout"] = str(err_msg or "")
            logger.warning(
                f"[BrowserAutomation] HOT-PATH-B: {tool_name} timed out "
                f"args={resolved_args}; continuing to "
                f"feige_send_message self-open fallback"
            )
            return True
        logger.warning(
            f"[BrowserAutomation] HOT-PATH-B: {tool_name} → FAIL "
            f"args={resolved_args} error={err_msg!r}"
        )
        outcome.last_tool_error = str(err_msg or "")
        outcome.reason = f"tool_failed:{tool_name}"
        return False

    logger.info(
        f"[BrowserAutomation] HOT-PATH-B: {tool_name} → OK "
        f"args={resolved_args} "
        f"extracted={getattr(result, 'extracted_content', '')!r}"
    )

    # Post-open crosstalk guard.
    if tool_name == "feige_open_session":
        ok, reason = await _post_open_verify(
            browser_session, eval_js, resolved_args, node_name
        )
        if not ok:
            outcome.reason = reason
            return False

    # Per-action settle delay.
    delay_ms = act.get("delay_after_ms", 300)
    await asyncio.sleep(float(delay_ms) / 1000.0)
    return True


async def execute(
    *,
    browser_session,
    customer_key: str,
    action_seq: list[dict],
    payload: dict,
    actions_registry: dict,
    resolve_template: Callable[[Any, dict], Any],
    node_name: str = "",
) -> HotPathOutcome:
    """Run a Feige HOT-PATH-B action sequence against *browser_session*.

    Thin orchestrator — all per-stage logic lives in ``_acquire_typing_lock``,
    ``_run_one_action``, ``_restore_feige_tab`` and the verification
    helpers above.  Each exit path (success, abort, exception) releases
    the typing lock exactly once via the ``finally`` block.

    See module-level docstring for the detailed contract.
    """
    outcome = HotPathOutcome()
    if not browser_session:
        outcome.reason = "no_browser_session"
        return outcome

    # Import lazily so this module has no top-level dependency on
    # extension_tools_service (which itself imports browser_use bits).
    try:
        from agent.ec_skills.browser_use_extension.extension_tools_service import (
            _evaluate_js as eval_js,
        )
    except Exception as imp_err:
        logger.warning(
            f"[BrowserAutomation] HOT-PATH-B: _evaluate_js import failed; "
            f"tool actions may run, but DOM verification will fail closed: "
            f"{imp_err}"
        )

        async def eval_js(_browser_session, _script):
            raise RuntimeError(f"_evaluate_js import failed: {imp_err}")

    # Pre-action: ensure on the Feige tab + current-conversation sub-tab.
    try:
        await ensure_feige_tab_focused(browser_session)
    except Exception as pretab_err:
        logger.warning(
            f"[BrowserAutomation] HOT-PATH-B: pre-action tab focus failed "
            f"(non-fatal): {pretab_err}",
            exc_info=True,
        )

    outcome.typing_acquired = await _acquire_typing_lock(customer_key, node_name)
    if customer_key and not outcome.typing_acquired:
        outcome.ok = False
        outcome.reason = "typing_lock_busy"
        return outcome

    try:
        for act in action_seq:
            if not await _run_one_action(
                act,
                actions_registry=actions_registry,
                payload=payload,
                resolve_template=resolve_template,
                browser_session=browser_session,
                eval_js=eval_js,
                customer_key=customer_key,
                node_name=node_name,
                outcome=outcome,
            ):
                break
        else:
            # Loop completed every action without break → success.
            # (Python's for-else runs only when no break occurred,
            # and also runs when action_seq is empty — preserving
            # the original "empty sequence = success" behaviour.)
            outcome.ok = True
            outcome.reason = "all_ok"
            await _restore_feige_tab(browser_session, node_name)
    except asyncio.CancelledError:
        # ── Diagnostic surface (2026-04-28) ──
        # ``CancelledError`` is ``BaseException`` (not ``Exception``)
        # in Python 3.8+, so the bare ``except Exception`` below would
        # silently let cancellations through with no log.  When the
        # parent persistent-worker cycle is pre-empted mid-await
        # (observed 2026-04-28 05:17:27 — cejs HOT-PATH-B's CDP focus
        # hung 3 s under contention, then the entire run was
        # cancelled), the executor was torn down without any visible
        # signal.  Mark the outcome and re-raise so the cancel still
        # propagates correctly; the ``finally`` below releases the
        # typing lock.
        logger.warning(
            f"[BrowserAutomation] HOT-PATH-B: executor cancelled "
            f"mid-sequence (cust={customer_key!r}, "
            f"actions_attempted={outcome.actions_attempted}, node={node_name})"
        )
        outcome.ok = False
        if not outcome.reason:
            outcome.reason = "cancelled"
        raise
    except Exception as exc:
        logger.warning(
            f"[BrowserAutomation] HOT-PATH-B: executor exception: {exc}",
            exc_info=True,
        )
        outcome.ok = False
        if not outcome.reason:
            outcome.reason = f"exception:{exc}"
    finally:
        # Release the typing lock on EVERY exit path — success, early
        # abort, or mid-sequence exception.  Safe no-op when not held.
        if outcome.typing_acquired and customer_key:
            try:
                typing_lock.release(customer_key)
            except Exception:
                pass

    return outcome


async def _verify_active_customer(
    browser_session,
    eval_js: Callable,
    expected: str,
    *,
    attempts: int = 1,
    interval: float = 0.075,
    expected_as_key: bool = True,
) -> tuple[bool, str]:
    """Poll ``FEIGE_ACTIVE_CUSTOMER_JS`` up to *attempts* times.

    Returns ``(ok, active_name_last_seen)``.

    When *expected_as_key* is True, the expected string is treated as
    a pre-normalised customer key and compared against the normalised
    ``active`` field.  When False (post-open-verify path), the raw
    stringified ``active`` is compared against the raw expected.
    """
    active_last = ""
    for _ in range(attempts):
        try:
            raw = await eval_js(browser_session, FEIGE_ACTIVE_CUSTOMER_JS)
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
