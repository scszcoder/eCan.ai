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

# Fix 17 (2026-05-13): drift retry budget for the feige_send_message path.
# Under 20-customer flood, the Feige sidebar reshuffles roughly every 1-2s
# as neighbouring sends complete; a single pre_send_reverify cycle (1.2s
# budget) often misses the next stable window and aborts the answer
# permanently.  Adding an outer retry loop with backoff lets the sidebar
# settle.  Three cycles × ~2s ≈ 6s extra wall-time worst case (rare),
# typically resolved in 1-2 cycles.  Both pre-send drift AND the
# "drifted between typing and click" failure inside feige_send_message
# itself are treated as retryable.
# Module-level fallback values — these resolve via the env layer, and
# in-use callers should prefer ``resolve_int/float(name, default,
# state)`` from .tunables to also pick up per-node overrides.
# Defaults restored to v0.9.79 conservative values on 2026-05-18
# after the regression survey traced the 3-min worst-case customer
# latency to the v0.9.80 commit ``80d50eb36`` bumping these up for
# product-listing (a separate, slow-batch use case that should now
# set its own per-node overrides via state['metadata']
# ['browser_auto_overrides']).
from .tunables import (
    DEFAULT_HOT_PATH_DRIFT_RETRY_MAX,
    DEFAULT_HOT_PATH_TOOL_TIMEOUT_S,
    resolve_int as _tunable_int,
    resolve_float as _tunable_float,
)
try:
    HOT_PATH_DRIFT_RETRY_MAX: int = max(
        1,
        int(os.getenv(
            "ECAN_HOT_PATH_DRIFT_RETRY_MAX",
            str(DEFAULT_HOT_PATH_DRIFT_RETRY_MAX),
        )),
    )
except Exception:
    HOT_PATH_DRIFT_RETRY_MAX = DEFAULT_HOT_PATH_DRIFT_RETRY_MAX
try:
    HOT_PATH_DRIFT_RETRY_BACKOFF_S: float = max(
        0.0, float(os.getenv("ECAN_HOT_PATH_DRIFT_RETRY_BACKOFF_S", "0.6"))
    )
except Exception:
    HOT_PATH_DRIFT_RETRY_BACKOFF_S = 0.6


def _is_retryable_send_error(err_msg: str) -> bool:
    """Identify transient errors that warrant retrying the send.

    Two flavours covered:

    * **UI-shuffle drift** — sidebar/active-customer changed under our
      feet between open and type ("drift", "wrong session", "active
      customer ... mismatch").  Resolved by a fresh re-verify cycle.

    * **CDP renderer hang** — the 17 KB feige_send_message JS
      occasionally parks Runtime.evaluate on a heavily-loaded Feige tab
      and trips the per-label 15 s CDP timeout.  The fault is
      transient (the next attempt typically completes in <5 s once
      the page settles) so it's worth one more try after a backoff.
      This was the dominant Round-2 stall mode in the 21:39 flood
      (11/12 stalls all reported as ``"CDP Runtime.evaluate timed out
      after 15.0s"``).
    """
    if not err_msg:
        return False
    low = str(err_msg).lower()
    if (
        "drift" in low
        or "drifted" in low
        or "wrong session" in low
        or ("active customer" in low and "mismatch" in low)
    ):
        return True
    # CDP / Runtime.evaluate timeouts surface from the underlying
    # _evaluate_js wrapper as plain strings — match on both pieces so
    # we don't accidentally catch the outer Python-level
    # ``tool timed out after 18.0s`` wrapper (handled separately).
    if "runtime.evaluate" in low and "timed out" in low:
        return True
    if "cdp" in low and "timed out" in low:
        return True
    return False
try:
    # Fix 16 (2026-05-13): 8.0 → 18.0.  The 20:33 flood (15/20 customers
    # stalled) showed feige_send_message tool calls timing out at 8s
    # while the underlying CDP evaluate budget is 15s.  Real-world send
    # JS legitimately runs 4-6s on a loaded renderer (5483ms / 4184ms
    # observed) — any incidental queue/lock contention pushes the wall
    # clock over 8s and the tool aborts before the CDP call returns.
    # 18s gives the 15s CDP timeout full headroom plus a small margin
    # for the surrounding Python overhead while still surfacing real
    # renderer hangs.
    #
    # Fix 18 (2026-05-13): 18.0 → 25.0.  Paired with bumping the
    # CDP-eval budget for feige_send_message from 15 s → 22 s after
    # Round-2 stalls all reported the inner CDP timeout.  Outer Python
    # timeout must stay > inner CDP timeout, otherwise the wrapper
    # cancels the call before the CDP layer can return its own error
    # string (which is what Fix 17/18 retries on).
    # 2026-05-14: bumped 25 -> 50 to stay above the bumped inner CDP
    # eval timeout (45s, see extension_tools_service.py). The outer
    # Python timeout must remain strictly greater than the CDP one so
    # CDP returns its own error string instead of being cancelled.
    # Default reverted to v0.9.79's 8.0s on 2026-05-18.  The 50.0s
    # ceiling introduced May 14 was bounding the success-path latency
    # under sustained 1-on-8 load (one customer's stuck CDP call held
    # the worker pool for up to 50s × retry budget).  Skills that
    # genuinely need longer (product-listing scrape) should set
    # ``state.metadata.browser_auto_overrides.HOT_PATH_TOOL_TIMEOUT_S``
    # per-node instead of bumping the global default.
    HOT_PATH_TOOL_TIMEOUT_S: float = max(
        1.0,
        float(os.getenv(
            "ECAN_HOT_PATH_TOOL_TIMEOUT_S",
            str(DEFAULT_HOT_PATH_TOOL_TIMEOUT_S),
        )),
    )
except Exception:
    HOT_PATH_TOOL_TIMEOUT_S = DEFAULT_HOT_PATH_TOOL_TIMEOUT_S


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

    # ── Drift-during-source-verify guard (Fix 9, 2026-05-13) ──────────
    # Background (incident: 客户14, 客户08 unanswered).  This function
    # walks the currently-focused chat thread and compares the latest
    # customer bubble's msg_id against what we dispatched.  But under
    # flood load, Feige's sidebar can re-shuffle and the FOCUSED chat
    # thread can drift to a DIFFERENT customer between
    # ``_pre_send_reverify`` (line 435) and this call (line 441).
    # Once that happens, the chat thread DOM is showing customer X's
    # messages while we expected customer Y's.  Our dispatched msg_id
    # (which belongs to Y) of course isn't there — but treating that
    # as ``stale_reply_source_msg_id`` (a permanent drop, no retry)
    # silently loses Y's still-pending reply.
    #
    # Concrete observed example (2026-05-13 14:15:29 客户14):
    #   * dispatched msg_id mp4k1e3n ("丢件了怎么处理？")  ← customer 14
    #   * actual_msg_id mp4k1elt ("男装XL码适合多高？")    ← customer 18!
    # The thread DOM had drifted to 客户18's chat between the
    # pre-send-reverify (which passed, active=客户14) and this check.
    #
    # Fix: when msg_id mismatch detected, do one quick active-customer
    # re-check.  If active drifted to a different customer → return
    # ``active_customer_drifted_during_source_verify`` (a transient
    # failure code, NOT ``stale_reply_source_msg_id``).  The
    # transient-failure handler in front_desk.py clears
    # ``last_dispatched_msg_id_by_customer`` (Fix 7b) so PreDispatch's
    # next pass re-dispatches the still-pending customer question.
    # If active is still the expected customer, fall through to the
    # original stale_reply_source_msg_id drop.
    expected_customer = str(
        payload.get("customer_name")
        or payload.get("customer_id")
        or ""
    ).strip()
    if expected_customer:
        try:
            ok_active, actual_active = await _verify_active_customer(
                browser_session,
                eval_js,
                expected_customer,
                attempts=1,
                interval=0.0,
                expected_as_key=False,
            )
            if not ok_active:
                outcome.extras["drift_actual_customer"] = str(actual_active or "")
                logger.warning(
                    f"[BrowserAutomation] HOT-PATH-B: source-verify drift — "
                    f"chat thread shows customer={actual_active!r} not "
                    f"expected={expected_customer!r}; dispatched msg_id="
                    f"...{expected_msg_id[-8:] if expected_msg_id else '<none>'}, "
                    f"visible thread latest msg_id="
                    f"...{actual_msg_id[-8:] if actual_msg_id else '<none>'} "
                    f"({actual_text[:60]!r}).  Returning transient "
                    f"failure so PreDispatch can re-dispatch instead of "
                    f"silently dropping the reply, node={node_name}"
                )
                return False, "active_customer_drifted_during_source_verify"
        except Exception as drift_check_err:
            logger.debug(
                f"[BrowserAutomation] HOT-PATH-B: drift recheck failed "
                f"(non-fatal, falling through to stale-drop): "
                f"{drift_check_err}"
            )

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
    state: dict | None = None,
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
    # Per-node tunable resolution (state kwarg is threaded through from
    # execute() — callers that don't pass it fall back to module-level
    # env defaults).  Lets a product-listing skill override these via
    # ``state.metadata.browser_auto_overrides`` without changing the
    # latency-sensitive chat defaults.
    _drift_max = _tunable_int(
        "HOT_PATH_DRIFT_RETRY_MAX", HOT_PATH_DRIFT_RETRY_MAX, state,
    )
    _tool_timeout_s = _tunable_float(
        "HOT_PATH_TOOL_TIMEOUT_S", HOT_PATH_TOOL_TIMEOUT_S, state,
    )
    act_obj = actions_registry.get(tool_name)
    if not act_obj:
        logger.warning(
            f"[BrowserAutomation] HOT-PATH-B: tool {tool_name!r} not found"
        )
        outcome.reason = f"tool_not_found:{tool_name}"
        return False

    # Pre-send re-verify (2026-04-22 Fix A) + Fix 17 (2026-05-13) drift retry.
    # The original code ran reverify + source-turn-verify exactly once and
    # aborted on any failure.  Under flood load that single pass routinely
    # missed the next stable sidebar window, leaving customers unanswered.
    # We now wrap reverify + invoke in a retry cycle: each iteration does
    # a fresh reverify (which itself re-opens once internally), then
    # invokes feige_send_message; if either step reports a drift-shaped
    # error we back off briefly and try again.  Non-drift failures
    # (timeout, source-turn-verify failure, unknown error) still abort
    # immediately as before.
    timed_out = False
    result = None
    if tool_name == "feige_send_message" and customer_key:
        resolved_args.setdefault("customer_name", customer_key)
        last_drift_reason = ""
        last_drift_error = ""
        # +1 so the canonical "single attempt" case is preserved when
        # HOT_PATH_DRIFT_RETRY_MAX is set to 1 (treat the constant as
        # "max retries beyond the first attempt").
        attempts_budget = _drift_max
        attempt = 0
        params = act_obj.param_model(**resolved_args)
        while attempt < attempts_budget:
            attempt += 1
            ok, reason = await _pre_send_reverify(
                browser_session, eval_js, customer_key, actions_registry, node_name
            )
            if not ok:
                last_drift_reason = reason
                if attempt < attempts_budget:
                    logger.info(
                        f"[BrowserAutomation] HOT-PATH-B: pre_send_reverify drift "
                        f"attempt {attempt}/{attempts_budget} for cust={customer_key!r}; "
                        f"backing off {HOT_PATH_DRIFT_RETRY_BACKOFF_S}s and retrying"
                    )
                    await asyncio.sleep(HOT_PATH_DRIFT_RETRY_BACKOFF_S)
                    continue
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
                # source-turn drift means the customer sent a newer
                # bubble — answer is stale, not retryable.
                outcome.reason = reason
                return False

            # Invoke the actual send.
            try:
                result = await asyncio.wait_for(
                    _invoke_tool(act_obj, params, browser_session),
                    timeout=_tool_timeout_s,
                )
                timed_out = False
            except asyncio.TimeoutError:
                timed_out = True
                result = None
                break  # timeout: handled by the non-retry path below

            send_err = getattr(result, "error", None) if result is not None else None
            if send_err and _is_retryable_send_error(str(send_err)):
                last_drift_error = str(send_err)
                if attempt < attempts_budget:
                    logger.info(
                        f"[BrowserAutomation] HOT-PATH-B: feige_send_message drift "
                        f"attempt {attempt}/{attempts_budget} for cust={customer_key!r} "
                        f"(error={send_err!r}); backing off "
                        f"{HOT_PATH_DRIFT_RETRY_BACKOFF_S}s and retrying"
                    )
                    await asyncio.sleep(HOT_PATH_DRIFT_RETRY_BACKOFF_S)
                    continue
                # Exhausted: fall through to the standard failure path.
                logger.warning(
                    f"[BrowserAutomation] HOT-PATH-B: feige_send_message drift "
                    f"unrecoverable after {attempt} attempts for cust={customer_key!r}; "
                    f"last_error={send_err!r}"
                )
            # Success or non-retryable failure: stop iterating.
            break
        # End of drift-retry loop.  ``result`` / ``timed_out`` carry the
        # outcome of the final attempt; the unified post-call handling
        # below catches both success and failure paths.
    else:
        # Non-send actions keep the original single-shot behaviour.
        params = act_obj.param_model(**resolved_args)
        try:
            result = await asyncio.wait_for(
                _invoke_tool(act_obj, params, browser_session),
                timeout=_tool_timeout_s,
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
                f"tool timed out after {_tool_timeout_s:.1f}s"
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
    state: dict | None = None,
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
                state=state,
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
