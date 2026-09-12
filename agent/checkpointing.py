"""Checkpointer selection for compiled skill graphs (Path 1.5, Phase 0.2).

The seam. Desktop keeps LangGraph's in-memory saver — today's behaviour,
unchanged — while a cloud pod selects a durable saver so a conversation
survives the pod that happens to be serving it: the graph stays resident for
warmth, but every turn is checkpointed, so any pod can resume and pod loss
costs warmth rather than the conversation.

This module is the ONLY place a saver class is named. Call sites ask for
``build_checkpointer()``.

Selection is by environment:

    ECAN_CHECKPOINTER       memory (default) | postgres | sqlite
    ECAN_CHECKPOINTER_DSN   connection string, required by the durable backends

A backend that is asked for but cannot be built raises. It deliberately does
NOT fall back to the in-memory saver: a cloud pod that silently checkpoints to
memory looks like a working run right up until a pod restart eats a
conversation. Same reason ``AppContextMeta.__getattr__`` returning ``None`` has
to become loud before headless gaps can be found — a silent downgrade is the
expensive failure, not a noisy one.
"""
from __future__ import annotations

import os
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver

from utils.logger_helper import logger_helper as logger

# Env var names, kept here so nothing else has to spell them.
ENV_KIND = "ECAN_CHECKPOINTER"
ENV_DSN = "ECAN_CHECKPOINTER_DSN"

_MEMORY_ALIASES = ("", "memory", "inmemory", "in_memory", "none")


class CheckpointerUnavailable(RuntimeError):
    """A durable checkpointer was requested but could not be constructed."""


def selected_kind() -> str:
    """The configured backend name, normalised. 'memory' when unset."""
    kind = (os.environ.get(ENV_KIND) or "").strip().lower()
    return "memory" if kind in _MEMORY_ALIASES else kind


def is_durable() -> bool:
    """True when the configured backend survives process restart."""
    return selected_kind() != "memory"


def build_checkpointer() -> Any:
    """Build the checkpointer for a compiled skill graph.

    Returns an ``InMemorySaver`` unless ``ECAN_CHECKPOINTER`` selects a durable
    backend. Raises ``CheckpointerUnavailable`` if a durable backend is asked
    for and cannot be built — never degrades silently.
    """
    kind = selected_kind()

    if kind == "memory":
        return InMemorySaver()

    if kind in ("postgres", "postgresql", "pg"):
        return _build_postgres()

    if kind == "sqlite":
        return _build_sqlite()

    raise CheckpointerUnavailable(
        f"{ENV_KIND}={kind!r} is not a known checkpointer backend "
        f"(memory | postgres | sqlite)")


def _require_dsn(kind: str) -> str:
    dsn = (os.environ.get(ENV_DSN) or "").strip()
    if not dsn:
        raise CheckpointerUnavailable(
            f"{ENV_KIND}={kind} needs a connection string in {ENV_DSN}")
    return dsn


def _build_postgres() -> Any:
    dsn = _require_dsn("postgres")
    try:
        from langgraph.checkpoint.postgres import PostgresSaver
    except ImportError as exc:  # dependency not installed on this image
        raise CheckpointerUnavailable(
            "langgraph-checkpoint-postgres is not installed; a cloud image "
            "selecting ECAN_CHECKPOINTER=postgres must ship it") from exc

    saver = PostgresSaver.from_conn_string(dsn)
    # from_conn_string hands back a context manager in current langgraph; enter
    # it for the process lifetime, since the saver outlives any one graph run.
    if hasattr(saver, "__enter__"):
        saver = saver.__enter__()
    saver.setup()
    logger.info("[checkpointing] Using durable Postgres checkpointer")
    return saver


def _build_sqlite() -> Any:
    dsn = _require_dsn("sqlite")
    try:
        from langgraph.checkpoint.sqlite import SqliteSaver
    except ImportError as exc:
        raise CheckpointerUnavailable(
            "langgraph-checkpoint-sqlite is not installed") from exc

    saver = SqliteSaver.from_conn_string(dsn)
    if hasattr(saver, "__enter__"):
        saver = saver.__enter__()
    saver.setup()
    logger.info("[checkpointing] Using durable SQLite checkpointer")
    return saver


# ---------------------------------------------------------------------------
# State serializability (Phase 0.1)
#
# ``NodeState.history`` and ``NodeState.messages`` are both ``List[Any]``, so
# the type system will not catch someone appending a live object — a driver
# handle, a socket, a Qt widget. Every call site is clean today; an in-memory
# saver would not care either way, but a durable one has to pickle/serialize
# what it is given. This keeps the invariant checkable before that matters.
# ---------------------------------------------------------------------------

ENV_STRICT = "ECAN_STRICT_CHECKPOINT_STATE"

_SAFE_SCALARS = (str, int, float, bool, bytes, type(None))
_MAX_DEPTH = 8
_TRUTHY = ("1", "true", "yes", "on")


def is_checkpoint_safe(obj: Any, _depth: int = 0) -> bool:
    """True when ``obj`` can survive a durable checkpoint round-trip.

    Accepts LangChain messages (``BaseMessage`` subclasses, which includes
    ``ActionMessage``) and plain data — scalars and JSON-shaped containers of
    them. Anything else is rejected: better a loud failure here than a pod that
    cannot rehydrate a conversation.
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
    """Reject state a durable checkpointer could not persist.

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
                f"or plain data — a durable checkpointer cannot persist this."
            )
