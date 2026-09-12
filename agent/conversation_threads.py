"""Conversation-scoped LangGraph threads (Path 1.5, Phase 2).

Today the LangGraph state is per *chatter-task*, and a chatter task is
per-*agent*, not per-customer. Every customer talking to one agent therefore
shares one ``state["history"]`` — which is what caused the 2026-04-27 incident
(customer A's answer typed into customer B's tab) and why
``_reset_qa_history_on_customer_change`` wipes history on every inbound turn.

The fix is to make the conversation the unit of isolation: key the checkpointer
thread on the conversation instead of the task, so two customers on one agent
resume independent state and neither can see the other's turns.

The plumbing for this already exists on both execution paths — the desktop
executor caches a ``configurable.thread_id`` per task
(``ec_tasks/executor.py``), and the AWS worker passes one keyed on ``run_id``
(``cloud_worker/worker_main.py``). What changes is *what the key is derived
from*, which is what this module owns.

**Off by default.** ``ECAN_CONVERSATION_THREADS=1`` opts in. Until a live
multi-customer run proves isolation holds, the per-turn history clear stays the
thing keeping customers apart — see the warning on Phase 3. Flipping this on
does not by itself retire that clear.

Thread lifetime is the part that bites: a task-scoped thread is deleted when
the task finishes (``executor.py`` calls ``saver.delete_thread``), but a
conversation-scoped thread must outlive any one task, or a finishing task will
wipe a conversation another turn still needs. ``is_conversation_thread`` is how
the executor tells the two apart.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

ENV_ENABLED = "ECAN_CONVERSATION_THREADS"

# Marks a thread id as conversation-scoped rather than task-scoped. Kept as a
# prefix (not a side table) so any component holding only the id — including
# the checkpoint-cleanup path — can tell what it is looking at.
CONVERSATION_THREAD_PREFIX = "conv"

_TRUTHY = ("1", "true", "yes", "on")


def conversation_threads_enabled() -> bool:
    """True when conversation-keyed threads are switched on."""
    return (os.environ.get(ENV_ENABLED) or "").strip().lower() in _TRUTHY


def conversation_id_from_payload(payload: Any) -> Optional[str]:
    """The conversation key carried by an inbound Q&A dispatch, if any.

    Deliberately reads the same fields as ``_is_qa_inbound_payload`` /
    ``_reset_qa_history_on_customer_change`` in ``build_node``: the customer is
    the conversation. Returns None for anything that is not an inbound customer
    turn (Q&A replies carrying ``response_text``, browser events, front-desk
    traffic), because those must not open a conversation thread.
    """
    if not isinstance(payload, dict):
        return None

    cust = str(payload.get("customer_id") or payload.get("customerId") or "").strip()
    latest = str(payload.get("latest_message") or "").strip()
    response = str(payload.get("response_text") or "").strip()

    if cust and latest and not response:
        return cust
    return None


def thread_id_for(agent_id: Any, conversation_id: Any) -> str:
    """Canonical conversation thread key.

    Namespaced by agent: the same customer talking to two different agents is
    two conversations, and sharing a thread between them would recreate the
    cross-talk bug one level up.
    """
    agent = str(agent_id or "").strip() or "unknown-agent"
    conv = str(conversation_id or "").strip()
    if not conv:
        raise ValueError("conversation_id is required for a conversation thread")
    return f"{CONVERSATION_THREAD_PREFIX}:{agent}:{conv}"


def is_conversation_thread(thread_id: Any) -> bool:
    """True when ``thread_id`` is conversation-scoped.

    The checkpoint-cleanup path uses this to avoid deleting a conversation's
    state just because one task that touched it finished.
    """
    return str(thread_id or "").startswith(CONVERSATION_THREAD_PREFIX + ":")


def config_for_conversation(base_config: Optional[Dict[str, Any]],
                            agent_id: Any,
                            conversation_id: Any) -> Dict[str, Any]:
    """Return ``base_config`` re-keyed onto this conversation's thread.

    A shallow copy — the caller's cached per-task config keeps its own
    ``thread_id``, so turning the flag off restores task-scoped behaviour with
    no residue.
    """
    config = dict(base_config or {})
    configurable = dict(config.get("configurable") or {})
    configurable["thread_id"] = thread_id_for(agent_id, conversation_id)
    config["configurable"] = configurable
    return config


def resolve_thread_config(base_config: Optional[Dict[str, Any]],
                          agent_id: Any,
                          payload: Any) -> Dict[str, Any]:
    """Config for this turn: conversation-keyed when enabled and applicable.

    Falls through to ``base_config`` unchanged when the flag is off or the
    payload is not an inbound customer turn — so a front-desk dispatch or a
    reply keeps running on the task thread exactly as before.
    """
    if not conversation_threads_enabled():
        return dict(base_config or {})

    conversation_id = conversation_id_from_payload(payload)
    if not conversation_id:
        return dict(base_config or {})

    return config_for_conversation(base_config, agent_id, conversation_id)
