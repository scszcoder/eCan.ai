"""Periodic suppression of Feige's OWN system customer-service bot (智能客服).

Feige auto-enables its built-in 智能客服 bot after ~10 minutes of dormancy. While
OUR agents are working we want Feige's bot OFF so it doesn't answer customers in
parallel (interference / double replies). This module periodically toggles it —
turn ON then quickly OFF — which keeps it suppressed and resets Feige's ~10-min
dormant auto-enable timer, leaving the bot in the OFF state.

It runs PARALLEL to the DOM monitor: the same periodic tick driver in
``event_monitor``'s ``DOMMutationMonitor.check_now()`` fires
:func:`suppress_feige_bot_tick` on its own throttle (default every 5 min), the
same way the cold-start recovery scan is fired.

The actual CDP + DOM toggle steps are PLACEHOLDERS for now — to be filled in when
we have the concrete Feige sidebar/settings DOM for the bot on/off control.

Gated ``ECAN_FEIGE_BOT_SUPPRESS=1`` (default OFF until the placeholders are
implemented). Interval ``ECAN_FEIGE_BOT_SUPPRESS_INTERVAL_S`` (default 300s).
"""
import os

from utils.logger_helper import logger_helper as logger


async def turn_on_feige_bot(browser_session, target_id) -> bool:
    """PLACEHOLDER — enable Feige's own 智能客服 bot via CDP + DOM.

    TODO: locate the bot on/off control in the Feige sidebar/settings and click
    it ON (e.g. ``_evaluate_js`` with a selector, like the recovery scan). Toggling
    counts as activity, which resets Feige's ~10-min dormant auto-enable timer.

    Returns True on success; currently a no-op stub.
    """
    logger.info(
        "[FEIGE-BOT-CTRL] turn_on_feige_bot() — PLACEHOLDER (no-op; "
        f"fill with the DOM toggle) target_id={target_id}")
    return False


async def turn_off_feige_bot(browser_session, target_id) -> bool:
    """PLACEHOLDER — disable Feige's own 智能客服 bot via CDP + DOM.

    TODO: locate the bot on/off control and click it OFF so Feige's bot does not
    answer customers while our agents are handling them.

    Returns True on success; currently a no-op stub.
    """
    logger.info(
        "[FEIGE-BOT-CTRL] turn_off_feige_bot() — PLACEHOLDER (no-op; "
        f"fill with the DOM toggle) target_id={target_id}")
    return False


async def suppress_feige_bot_tick() -> None:
    """One suppression cycle: toggle Feige's bot ON then quickly OFF so it stays
    suppressed (and the ~10-min dormant auto-enable timer is reset).

    Resolves the focused Feige tab/session the same way the cold-start recovery
    scan does, then calls the (placeholder) on/off steps. Best-effort; never
    raises. Gated ``ECAN_FEIGE_BOT_SUPPRESS=1``.
    """
    if os.environ.get("ECAN_FEIGE_BOT_SUPPRESS", "") != "1":
        return
    try:
        from agent.ec_skills.browser_node.build_helpers import cached_browser_sessions
        from .dom_assets import (
            ensure_feige_tab_reachable,
            _SESSION_FOCUSED_FEIGE_TID_ATTR,
        )
    except Exception:
        return
    browser_session = None
    for sess in list((cached_browser_sessions or {}).values()):
        if sess is not None:
            browser_session = sess
            break
    if browser_session is None:
        return
    target_id = None
    try:
        if await ensure_feige_tab_reachable(browser_session):
            target_id = getattr(browser_session, _SESSION_FOCUSED_FEIGE_TID_ATTR, None)
    except Exception:
        target_id = None
    try:
        await turn_on_feige_bot(browser_session, target_id)
        await turn_off_feige_bot(browser_session, target_id)
        logger.info("[FEIGE-BOT-CTRL] suppression tick complete (placeholder on->off)")
    except Exception as _e:
        logger.debug(f"[FEIGE-BOT-CTRL] suppression tick failed (non-fatal): {_e}")
