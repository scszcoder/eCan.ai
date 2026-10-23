"""Checkpointer selection for compiled skill graphs.

The seam.  Only one saver exists: LangGraph's in-memory saver.  It is
required, not optional — LangGraph refuses to run ``Command(resume=...)``
without a checkpointer at all::

    RuntimeError: Cannot use Command(resume=...) without checkpointer

so the interrupt/auto-resume path in ``agent/ec_tasks/runner.py`` depends on it.
It is cheap: an empty ``InMemorySaver`` is a 72-byte dict, and
``agent/ec_tasks/executor.py`` prunes the finished task's thread from it.

Durable savers (sqlite/postgres) were removed on purpose.  They cost ~19 MB
of psycopg v3 wheels on every image, and no deployment ever enabled them.

What "restart and keep working" actually needs does NOT come from a
checkpointer:

* task progress is persisted in the task's stored ``metadata["state"]``
  (``agent/ec_tasks/serializer.py``), and re-read as the seed state on the
  next run (``agent/ec_tasks/runner.py``);
* chat history is re-read from the database
  (``agent/ec_tasks/chat_transcript.py``).

So a restarted task continues from its persisted state and re-runs its graph,
rather than resuming the exact frame it was parked on.  A task blocked on a
human answer starts its run over instead of resuming mid-interrupt.

This module is the ONLY place a saver class is named.  Call sites ask for
``build_checkpointer()``.
"""
from __future__ import annotations

import os
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver

# Env var name, kept here so nothing else has to spell it.
ENV_KIND = "ECAN_CHECKPOINTER"

_MEMORY_ALIASES = ("", "memory", "inmemory", "in_memory", "none")


class CheckpointerUnavailable(RuntimeError):
    """A checkpointer backend was requested but is not supported."""


def selected_kind() -> str:
    """The configured backend name, normalised. 'memory' when unset."""
    kind = (os.environ.get(ENV_KIND) or "").strip().lower()
    return "memory" if kind in _MEMORY_ALIASES else kind


def is_durable() -> bool:
    """True when the configured backend survives process restart.

    Always False: the in-memory saver does not survive a restart.  Kept
    because ``agent/cloud_worker/cn_serve.py`` reads it to decide whether a
    pod may serve.
    """
    return False


def build_checkpointer() -> Any:
    """Build the checkpointer for a compiled skill graph.

    Returns an ``InMemorySaver``.  A durable backend named in
    ``ECAN_CHECKPOINTER`` raises — it is never silently ignored, so a
    deployment still asking for postgres fails loudly instead of quietly
    getting a saver that loses state on restart.
    """
    kind = selected_kind()

    if kind == "memory":
        return InMemorySaver()

    raise CheckpointerUnavailable(
        f"{ENV_KIND}={kind!r} is not a supported checkpointer backend "
        f"(memory is the only one). Durable savers (sqlite/postgres) were "
        f"removed; task progress is persisted in the task's stored state and "
        f"re-read on restart, so a run continues from that state.")


# ---------------------------------------------------------------------------
# State serializability
#
# ``NodeState.history`` and ``NodeState.messages`` are both ``List[Any]``, so
# the type system will not catch someone appending a live object — a driver
# handle, a socket, a Qt widget.  Every call site is clean today, but the
# state IS persisted to the database for restart-resume, so what it is given
# has to be persistable.  This keeps the invariant checkable.
# ---------------------------------------------------------------------------

ENV_STRICT = "ECAN_STRICT_CHECKPOINT_STATE"

_SAFE_SCALARS = (str, int, float, bool, bytes, type(None))
_MAX_DEPTH = 8
_TRUTHY = ("1", "true", "yes", "on")


def is_checkpoint_safe(obj: Any, _depth: int = 0) -> bool:
    """True when ``obj`` can survive a persist/restore round-trip.

    Accepts LangChain messages (``BaseMessage`` subclasses, which includes
    ``ActionMessage``) and plain data — scalars and JSON-shaped containers of
    them. Anything else is rejected: better a loud failure here than a task
    whose state cannot be re-read after a restart.
    """
    if isinstance(obj, _SAFE_SCALARS):
        return True

    try:
        from langchain_core.messages import BaseMessage
        if isinstance(obj, BaseMessage):
            return True
    except ImportError:  # pragma: no cover - langchain always present here
        pass

    if _depth >= _MAX_DEPTH:
        # Too deep to verify — treat as unsafe rather than assume.
        return False

    if isinstance(obj, dict):
        return all(isinstance(k, (str, int)) and is_checkpoint_safe(v, _depth + 1)
                   for k, v in obj.items())

    if isinstance(obj, (list, tuple, set, frozenset)):
        return all(is_checkpoint_safe(v, _depth + 1) for v in obj)

    return False


def strict_state_checks_enabled() -> bool:
    return (os.environ.get(ENV_STRICT) or "").strip().lower() in _TRUTHY


def assert_checkpoint_safe(items: Any, where: str = "") -> None:
    """Reject state that could not be persisted.

    OFF by default — Phase 0 changes no behaviour. Enable with
    ``ECAN_STRICT_CHECKPOINT_STATE=1`` (tests, CI) to turn a
    silently-unpersistable append into an immediate, located failure.
    """
    if not strict_state_checks_enabled():
        return

    candidates = items if isinstance(items, (list, tuple)) else [items]
    for item in candidates:
        if not is_checkpoint_safe(item):
            raise TypeError(
                f"Non-checkpointable object appended to state"
                f"{' at ' + where if where else ''}: {type(item).__name__}. "
                f"History/messages must hold LangChain BaseMessage subclasses "
                f"or plain data — persisted state cannot hold this.")
