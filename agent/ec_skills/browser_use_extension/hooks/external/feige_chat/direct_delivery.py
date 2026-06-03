"""Feige direct-delivery placeholder send.

The async coroutine that types a single placeholder bubble ("人工服务
正在回复中...") into a Feige customer chat thread.  Moved here from
``runner.py``'s ``_enqueue_direct_placeholder`` inline closure in
mt051C (2026-05-28); runner.py now fires
``Stage.ON_LIVE_CHAT_PLACEHOLDER_NEEDED`` via ``live_chat_dispatch``
and stays agnostic about Feige tools, tab pools, and DOM selectors.

Future-site abstraction: when a 2nd live-chat bundle (Shopify, WeChat,
etc.) is added, it ships its own ``direct_delivery.py`` with an
equivalent ``register()`` and is loaded instead of this one.  The
``LiveChatPlaceholderRequest`` envelope (``hook_api.py``) is the
shared contract.
"""
import asyncio
from typing import Any

from utils.logger_helper import logger_helper as logger

from agent.ec_skills.browser_use_extension.hook_api import (
    LiveChatPlaceholderRequest,
)


async def _placeholder_send_coroutine(
    customer_key: str,
    source_msg_id: str,
    text: str,
    browser_session: Any,
    armed_at: float,
) -> None:
    """Run on the direct-delivery worker loop.  Allocates pool tab,
    types, releases.  Registers itself with placeholder_timer so a
    late-arriving cancel can abort mid-send via asyncio task
    cancellation.

    Body verbatim from the pre-mt051C inline closure in
    ``runner._enqueue_direct_placeholder``.  Logic touched in mt050N/O/P
    is preserved exactly so the existing test suite keeps validating
    the same code paths.
    """
    try:
        from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
            tab_pool as _ph_pool,
            placeholder_timer as _ph_timer,
        )
        from agent.ec_skills.browser_use_extension.extension_tools_service import (
            custom_controller as _ph_ctrl,
        )
    except Exception as _imp_e:
        logger.warning(
            f"[placeholder_timer] import failed in send coroutine: {_imp_e}"
        )
        return
    import asyncio as _ph_asyncio_inner
    try:
        _ph_current_task = _ph_asyncio_inner.current_task()
    except Exception:
        _ph_current_task = None
    if _ph_current_task is not None:
        _ph_timer.register_inflight_placeholder(
            customer_key, source_msg_id, _ph_current_task
        )
    # 2026-05-20 race-fix (v2 per-turn): between claim_expired (which
    # atomically claimed this placeholder slot) and now (the actual
    # type), the real reply may have arrived for THIS specific turn.
    # If so, cancel() would have stamped _REAL_REPLY_AT[(cust, src)]
    # — skip typing.  Other turns' placeholders are unaffected.
    # mt050P (2026-05-28): pass armed_at to honour newer-turn
    # semantics; without it, the previous turn's blank-key stamp
    # was suppressing every burst-typing customer's placeholders.
    if _ph_timer.is_real_reply_recent(
        customer_key, source_msg_id, armed_at=armed_at,
    ):
        logger.info(
            f"[placeholder_timer] suppressed placeholder for "
            f"cust={customer_key!r} src_msg={source_msg_id!r} "
            f"text={text!r} — real reply for this turn was "
            f"delivered while this placeholder was queued"
        )
        _ph_timer.unregister_inflight_placeholder(customer_key, source_msg_id)
        return
    pool = _ph_pool.get_pool()
    tab = pool.allocate_for_typing(customer_key)
    # 2026-05-21: pool-exhaustion retry.  Under burst load (17+
    # placeholders firing simultaneously for 6 pool tabs) the
    # original code silently dropped placeholders — meaning 客户02/03
    # got NO acknowledgement within Feige's 30s window.  Now we
    # retry briefly (typing usually completes in 0.5-3s so a free
    # tab appears within a couple of seconds) before giving up.
    # If still nothing after the retry budget, fall back to the
    # monitor tab so the placeholder ALWAYS reaches the customer.
    if tab is None:
        POOL_RETRY_INTERVAL_S = 0.5
        POOL_RETRY_BUDGET_S = 3.0
        _waited = 0.0
        while tab is None and _waited < POOL_RETRY_BUDGET_S:
            # Re-check suppression each iteration — if the real
            # reply landed during the wait, abort cleanly.
            # mt050P: pass armed_at for newer-turn semantics.
            if _ph_timer.is_real_reply_recent(
                customer_key, source_msg_id, armed_at=armed_at,
            ):
                logger.info(
                    f"[placeholder_timer] suppressed during pool-wait "
                    f"cust={customer_key!r} src_msg={source_msg_id!r} "
                    f"text={text!r}"
                )
                _ph_timer.unregister_inflight_placeholder(customer_key, source_msg_id)
                return
            await _ph_asyncio_inner.sleep(POOL_RETRY_INTERVAL_S)
            _waited += POOL_RETRY_INTERVAL_S
            tab = pool.allocate_for_typing(customer_key)
    if tab is None:
        # Pool truly saturated.  Fall back to the monitor tab —
        # it's always present and (under flood) often less busy
        # than typing tabs since EventMonitor polls are short.
        # Borrow it briefly; chat_scope guard in the JS prevents
        # mis-delivery if monitor's active chat doesn't match.
        try:
            monitor_tab_id = pool.get_monitor()
        except Exception:
            monitor_tab_id = None
        if monitor_tab_id:
            logger.info(
                f"[placeholder_timer] pool saturated for "
                f"cust={customer_key!r}; falling back to monitor tab "
                f"...{monitor_tab_id[-6:]} for placeholder typing"
            )
            # Synthesize a minimal TypingTabState pointing at the
            # monitor tab.  We DON'T call pool.allocate (would mark
            # monitor as in_use, blocking PreDispatch scrapes).
            # Instead use it transparently — feige_send_message will
            # resolve target_id via tab pool, falling back to
            # monitor if no pool tab is sticky.
            class _MonitorFallbackTab:
                target_id = monitor_tab_id
            tab = _MonitorFallbackTab()
        else:
            logger.warning(
                f"[placeholder_timer] pool saturated AND no monitor "
                f"tab fallback for cust={customer_key!r} — placeholder "
                f"dropped (customer will see no acknowledgement)"
            )
            _ph_timer.unregister_inflight_placeholder(customer_key, source_msg_id)
            return
        _used_monitor_fallback = True
    else:
        _used_monitor_fallback = False
    _ok = False
    try:
        _actions = _ph_ctrl.registry.registry.actions
        _open_fn = _actions.get("feige_open_session")
        _send_fn = _actions.get("feige_send_message")
        if not _open_fn or not _send_fn:
            logger.warning(
                "[placeholder_timer] feige tools not in registry; "
                "cannot type placeholder"
            )
            return
        # Open the customer's chat on the assigned pool tab.
        # customer_key routes to the right tab via the resolver
        # (Phase 1 plumbing).  RegisteredAction wraps the function —
        # invoke via .function(params=..., browser_session=...)
        # NOT direct call (that errors 'RegisteredAction' is not
        # callable — bug found live 2026-05-20 17:36).
        try:
            import inspect as _ph_inspect
        except Exception:
            _ph_inspect = None

        async def _ph_invoke(action, params):
            """Mirror the call pattern at runner.py:4683-4694."""
            if _ph_inspect is not None:
                _sig = _ph_inspect.signature(action.function)
                if "browser_session" in _sig.parameters:
                    _raw_call = action.function(
                        params=params, browser_session=browser_session
                    )
                else:
                    _raw_call = action.function(params=params)
            else:
                _raw_call = action.function(
                    params=params, browser_session=browser_session
                )
            if hasattr(_raw_call, "__await__"):
                return await _raw_call
            return _raw_call

        _open_params = _open_fn.param_model(customer_name=customer_key)
        await _ph_invoke(_open_fn, _open_params)

        # 2026-05-20 v3: re-check suppression AFTER feige_open_session
        # returns.  Pool allocation + tab focus switch can take
        # 5-10s under load; in that window the real reply may have
        # arrived and stamped _REAL_REPLY_AT.  Without this second
        # check, placeholders typed AFTER the real answer (客户09/10
        # 23:19-23:20 trace: real answer landed 0.7s after fire,
        # placeholder typed 5s after fire).
        # mt050P: pass armed_at for newer-turn semantics.
        if _ph_timer.is_real_reply_recent(
            customer_key, source_msg_id, armed_at=armed_at,
        ):
            logger.info(
                f"[placeholder_timer] suppressed placeholder for "
                f"cust={customer_key!r} src_msg={source_msg_id!r} "
                f"text={text!r} — real reply for this turn arrived "
                f"during pool/open window; aborting before typing"
            )
            return

        # Empty source_msg_id + source_latest_message bypasses
        # source-turn-verify (placeholder isn't a reply to any
        # specific bubble — it's a stand-by message).
        _send_params = _send_fn.param_model(
            text=text,
            customer_name=customer_key,
            source_customer_msg_id="",
            source_latest_message="",
        )
        # 2026-05-23 mt029: pre-register the placeholder TEXT in
        # the mt028 no-TTL typed-text set BEFORE the await on
        # feige_send_message.  Reason: feige_send_message's JS
        # eval often types the bubble into the DOM but the Python
        # wrapper coroutine can still be cancelled mid-flight by
        # supersede / real-reply-arrived.  When that happens, the
        # CancelledError below skips the post-send record_typed_*
        # registration, but the bubble IS in the DOM — and mt017's
        # next scrape sees an unknown agent bubble msg_id and
        # mis-fires mark_handled.  Live trace 2026-05-22 15:38:23
        # → 15:38:33 客户13: placeholder typed (JS completed),
        # Python cancelled before record, mt017 fired, customer
        # stuck.  Pre-registering means even a cancelled-after-
        # JS path leaves the text in the set so mt017 recognises
        # it.  False positive risk (text was actually never typed
        # and a real customer happens to send the same text) is
        # essentially nil for placeholder strings like "您好,稍等".
        try:
            from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
                human_intervention as _ph_hi,
            )
            _ph_hi.record_typed_text(customer_key, text)
        except Exception:
            pass
        # 2026-05-23 mt033: pre-register the placeholder text in the
        # recent-agent-reply ledger BEFORE awaiting the CDP typing
        # eval.  The eval takes ~1.5-2s; during that window the
        # placeholder bubble appears in the DOM and the mutation
        # observer fires.  If we record AFTER the await (as the
        # original placement did), EventMonitor's dom_echo filter
        # consults an empty/stale ledger and treats the bubble as
        # a new customer message → phantom dispatch → front-desk
        # queue explosion.  Live trace 2026-05-23 13:02:22 肽斯特:
        # CDP success at .541, dom_observed bogus placeholder at
        # .779, ledger updated at .883 — 240ms race window.  Pre-
        # registering closes the window.  Safe under cancellation:
        # remember_agent_reply is idempotent + the ledger has a 90s
        # TTL, so a typing failure leaves at most a short-lived
        # stale entry that can only suppress an unlikely real
        # customer message that exactly matches a placeholder
        # string.
        try:
            from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
                dispatch_state as _ph_ds,
            )
            _ph_ds.remember_agent_reply(customer_key, text)
            # 2026-05-27 mt050K-(b) — also tag as placeholder so
            # PreDispatch's dom-echo guard can distinguish "this
            # sidebar text is just our placeholder echo (don't
            # suppress)" from "this sidebar text is our real reply
            # (do suppress)".  Without this tag, the placeholder
            # echo strands the customer for the full RECENT_REPLY_
            # TTL_S (~90 s) whenever they had a pending question
            # that hasn't been answered yet.
            _ph_ds.mark_placeholder_text(text)
        except Exception as _record_err:
            logger.debug(
                f"[placeholder_timer] remember_agent_reply pre-register "
                f"failed (non-fatal): {_record_err}"
            )
        await _ph_invoke(_send_fn, _send_params)
        _ok = True
        # 2026-05-21 Fix B: stamp the per-customer typed-placeholder
        # ledger so claim_expired's hard cap (no more than
        # max_placeholders per customer per window) takes effect
        # against orphan-timer cases.
        try:
            # mt068: pass source_msg_id so the standing-placeholder suppression
            # is turn-aware (only a same-turn double-fire is a 弹出多次 dup).
            _ph_timer.mark_placeholder_typed(customer_key, source_msg_id)
        except Exception:
            pass
        logger.info(
            f"[placeholder_timer] typed placeholder cust={customer_key!r} "
            f"text={text!r} pool_tab=...{tab.target_id[-6:]}"
        )
        # Grep-friendly per-customer state marker
        logger.info(
            f"[FEIGE-CUSTOMER-STATE] cust={customer_key!r} "
            f"phase=placeholder_typed text={text[:30]!r}"
        )
    except _ph_asyncio_inner.CancelledError:
        # Real reply landed mid-send and cancel() aborted the task
        logger.info(
            f"[placeholder_timer] in-flight send aborted by cancel "
            f"for cust={customer_key!r} src_msg={source_msg_id!r} "
            f"text={text!r} — real reply arrived during send"
        )
        raise
    except Exception as _send_err:
        logger.warning(
            f"[placeholder_timer] send failed for cust={customer_key!r}: "
            f"{type(_send_err).__name__}: {_send_err}"
        )
    finally:
        # Only release REAL pool tabs.  Monitor-tab fallback was
        # never allocated through pool.allocate so releasing it
        # would corrupt the pool's customer→tab sticky map.
        if not _used_monitor_fallback:
            try:
                pool.release(tab.target_id, succeeded=_ok, customer_key=customer_key)
            except Exception:
                pass
        try:
            _ph_timer.unregister_inflight_placeholder(customer_key, source_msg_id)
        except Exception:
            pass


def _placeholder_handler(
    req: LiveChatPlaceholderRequest,
    *,
    worker_loop: Any = None,
    **_unused: Any,
) -> bool:
    """live_chat_dispatch handler — schedules the placeholder send
    coroutine on the runner-supplied worker loop.

    Returns True if the coroutine was successfully scheduled.  The
    coroutine itself runs to completion asynchronously; the schedule
    result does NOT reflect whether the send eventually succeeded
    (that's logged from inside the coroutine).
    """
    browser_session = req.site_context.get("browser_session")
    if browser_session is None:
        logger.debug(
            "[direct_delivery] placeholder handler: no browser_session in "
            "site_context; skipping"
        )
        return False
    if worker_loop is None or getattr(worker_loop, "is_closed", lambda: True)():
        logger.debug(
            "[direct_delivery] placeholder handler: worker_loop missing or "
            "closed; skipping"
        )
        return False
    try:
        asyncio.run_coroutine_threadsafe(
            _placeholder_send_coroutine(
                req.session_id,
                req.turn_id,
                req.text,
                browser_session,
                req.armed_at,
            ),
            worker_loop,
        )
        return True
    except Exception as _sched_err:
        logger.warning(
            f"[direct_delivery] failed to schedule placeholder send for "
            f"session={req.session_id!r}: {_sched_err}"
        )
        return False


def register() -> None:
    """Register this bundle's placeholder handler with the shared
    ``live_chat_dispatch`` registry.  Called automatically when the
    feige_chat package is imported (see ``__init__.py``).  Idempotent:
    re-registering replaces the prior handler (no-op when it's the
    same callable as this module's).
    """
    from agent.ec_skills import live_chat_dispatch
    live_chat_dispatch.register_placeholder_handler(_placeholder_handler)
