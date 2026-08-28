"""Browser-use sub-agent helpers: cross-round reset, history clamp.

The browser-use ``Agent`` is heavyweight (owns ``MessageManager``,
history, LLM client refs, ~860 MB allocations).  We cache one per
scope and reuse across pend_event-loop iterations so the cost is
paid only once per chat session.

This module owns the helpers that keep the cached agent reusable:

* :func:`reset_bu_agent_for_next_round` — wipe / trim history, reset
  state fields that would otherwise cause ``run()`` to exit early,
  restore the full ``AgentOutput`` schema (browser-use clobbers it
  to ``DoneAgentOutput`` when ``max_steps`` or ``max_failures`` is
  reached, which would lose all custom actions on the next round).

Future scope: the per-round agent construction logic and the
``agent.step`` monkey-patch installer (cancellation polling, tab
refocus, abort guard, DOM-focus hide/restore) currently live inline
in ``build_node.py::_run_browser_use``.  They will land here in a
follow-up commit.
"""

from __future__ import annotations

import asyncio
from typing import Any

from utils.logger_helper import logger_helper as logger


# ─────────────────────────────────────────────────────────────────────
# Agent reset (cross-round)
# ─────────────────────────────────────────────────────────────────────

def reset_bu_agent_for_next_round(agent: Any, mode: str, task: str) -> None:
    """Reset a cached browser-use sub-agent for re-use in the next round.

    Args:
        agent: The browser-use Agent instance to reset.
        mode:  ``loop_history_mode`` — one of ``"clear"``, ``"trim:N"``,
               or ``"accumulate"``.
        task:  The new task string for this round.  Updates **both**
               ``agent.task`` and ``agent.message_manager.task`` —
               browser-use reads the latter on every step via
               ``AgentMessagePrompt(task=self.task)``, so a stale
               ``message_manager.task`` would feed the LLM the very
               first round's task forever.

    Behavior summary (mirrors the original closure version):

    * Always: update ``task`` on agent + message_manager.
    * Always: restore full ``AgentOutput`` if a previous run clobbered
      it to ``DoneAgentOutput`` (custom actions would otherwise be
      missing).
    * Always: reset ``LoopDetector`` action-hash + page-fingerprint
      caches to prevent false repetition nudges across rounds.
    * Always: reset ``state.n_steps`` / ``consecutive_failures`` /
      ``stopped`` so ``run()`` doesn't exit before its first step.
    * ``mode == "accumulate"``: keep all message history.
    * ``mode == "clear"``:    wipe ``context_messages``, ``agent_history_items``,
      ``compacted_memory``, and ``history.history``.
    * ``mode == "trim:N"``:    keep only the last N items in both
      ``agent_history_items`` and ``history.history``.

    Errors are logged at warning level and swallowed; the goal is
    "best-effort cleanup" — a partially-reset agent is still better
    than aborting the round.
    """
    try:
        _reset_task_text(agent, task)
        _restore_full_agent_output(agent)
        _reset_loop_detector(agent)
        _reset_state_fields(agent)
        _diagnose_agent_output(agent)

        if mode == "accumulate":
            logger.debug("[browser_node.agent] mode=accumulate: preserving full history")
            return

        _reset_message_manager(agent, mode)
        _trim_history_list(agent, mode)
    except Exception as exc:
        logger.warning(f"[browser_node.agent] reset_bu_agent_for_next_round error (non-fatal): {exc}")


# ─────────────────────────────────────────────────────────────────────
# Internals — each handles one specific concern
# ─────────────────────────────────────────────────────────────────────

def _reset_task_text(agent: Any, task: str) -> None:
    if hasattr(agent, "task"):
        agent.task = task
    mm = getattr(agent, "message_manager", None)
    if mm is not None and hasattr(mm, "task"):
        mm.task = task


def _restore_full_agent_output(agent: Any) -> None:
    """Re-attach the full ``AgentOutput`` schema if browser-use clobbered it.

    Browser-use replaces ``AgentOutput`` with ``DoneAgentOutput`` (a
    done-only subclass) when ``max_steps`` / ``max_failures`` is hit.
    Since we cache and reuse the agent, the next round would only see
    the ``done`` action and lose all custom actions (site-registered
    send/open tools, etc.).
    """
    full_output = getattr(agent, "_ecan_full_AgentOutput", None)
    if full_output is None or not hasattr(agent, "AgentOutput"):
        return
    was_clobbered = agent.AgentOutput is not full_output
    agent.AgentOutput = full_output
    if was_clobbered:
        logger.info(
            "[browser_node.agent] AgentOutput was clobbered (DoneAgentOutput) — restored full"
        )


def _reset_loop_detector(agent: Any) -> None:
    """Clear LoopDetector caches so the ``done`` hash from the previous
    round doesn't trigger false repetition nudges in the next round.
    """
    ld = getattr(getattr(agent, "state", None), "loop_detector", None)
    if ld is None:
        return
    prev_rep = getattr(ld, "max_repetition_count", 0)
    if hasattr(ld, "recent_action_hashes"):
        ld.recent_action_hashes.clear()
    if hasattr(ld, "recent_page_fingerprints"):
        ld.recent_page_fingerprints.clear()
    if hasattr(ld, "max_repetition_count"):
        ld.max_repetition_count = 0
    if hasattr(ld, "most_repeated_hash"):
        ld.most_repeated_hash = None
    if hasattr(ld, "consecutive_stagnant_pages"):
        ld.consecutive_stagnant_pages = 0
    if prev_rep >= 3:
        logger.info(
            f"[browser_node.agent] Reset LoopDetector (was repetition={prev_rep})"
        )


def _reset_state_fields(agent: Any) -> None:
    """Reset agent.state fields that would cause run() to exit early."""
    st = getattr(agent, "state", None)
    if st is None:
        return
    for attr, val in (("n_steps", 1), ("consecutive_failures", 0), ("stopped", False)):
        try:
            setattr(st, attr, val)
        except Exception:
            pass

    # CRITICAL: Re-create _external_pause_event for reuse across rounds
    # The original Event from a previous run() call is bound to that event loop
    # and cannot be used in a new run() call in a different loop context.
    # Creating a fresh Event avoids "is bound to a different event loop" errors.
    try:
        if hasattr(agent, "_external_pause_event"):
            new_event = asyncio.Event()
            new_event.set()  # Ensure it's in "resumed" (not paused) state
            agent._external_pause_event = new_event
            logger.debug("[browser_node.agent] Re-created _external_pause_event for new run")
    except Exception as exc:
        logger.debug(f"[browser_node.agent] Failed to re-create _external_pause_event: {exc}")


def _diagnose_agent_output(agent: Any) -> None:
    """Log a warning if the restored ``AgentOutput`` is missing custom actions."""
    try:
        ao = getattr(agent, "AgentOutput", None)
        if ao is None:
            return
        action_field = ao.model_fields.get("action")
        if not action_field or not hasattr(action_field.annotation, "model_fields"):
            return
        names = list(action_field.annotation.model_fields.keys())
        if len(names) <= 1:
            full_set = getattr(agent, "_ecan_full_AgentOutput", None)
            logger.warning(
                f"[browser_node.agent] AgentOutput has only {len(names)} actions ({names}) — "
                f"custom tools may be missing! _ecan_full_AgentOutput="
                f"{'set' if full_set is not None else 'NOT set'}"
            )
        else:
            logger.debug(f"[browser_node.agent] AgentOutput OK: {len(names)} actions")
    except Exception as exc:
        logger.debug(f"[browser_node.agent] AgentOutput check failed: {exc}")


def _reset_message_manager(agent: Any, mode: str) -> None:
    """Wipe (or trim) ``context_messages``, ``agent_history_items`` per mode."""
    mm = getattr(agent, "message_manager", None)
    mm_state = getattr(mm, "state", None) if mm else None
    if mm_state is None:
        return

    if hasattr(mm_state, "context_messages"):
        mm_state.context_messages.clear()

    if mode == "clear":
        had_history = False
        had_memory = False
        if hasattr(mm_state, "agent_history_items"):
            had_history = len(mm_state.agent_history_items) > 0
            mm_state.agent_history_items.clear()
        if hasattr(mm_state, "compacted_memory"):
            had_memory = mm_state.compacted_memory is not None
            mm_state.compacted_memory = None
        logger.info(
            f"[browser_node.agent] mode=clear: wiped message_manager "
            f"(had_history={had_history}, had_compacted_memory={had_memory})"
        )
    elif mode.startswith("trim:"):
        keep_n = _parse_trim_n(mode)
        if hasattr(mm_state, "agent_history_items"):
            items = mm_state.agent_history_items
            if len(items) > keep_n:
                del items[:-keep_n]
        logger.debug(f"[browser_node.agent] mode={mode}: trimmed mm to last {keep_n}")


def _trim_history_list(agent: Any, mode: str) -> None:
    """Reset/trim ``agent.history`` (used by ``final_result`` / ``is_done``).

    Without this, ``history.is_done()`` returns True from the previous
    round and ``run()`` may exit before executing a single step.
    """
    hist = getattr(agent, "history", None)
    if hist is None or not hasattr(hist, "history"):
        return
    if mode == "clear":
        hist.history.clear()
    elif mode.startswith("trim:"):
        keep_n = _parse_trim_n(mode)
        if len(hist.history) > keep_n:
            del hist.history[:-keep_n]


def _parse_trim_n(mode: str) -> int:
    try:
        return int(mode.split(":", 1)[1])
    except (ValueError, IndexError):
        return 10
