"""The checkpointer contract: memory only, and the in-memory saver is required.

Durable savers (sqlite/postgres) were removed.  Two things must stay true:

1. ``ECAN_CHECKPOINTER`` naming a durable backend raises — it must never
   quietly hand back an in-memory saver, because a deployment pointing at
   postgres would then lose state on restart without saying so.

2. The in-memory saver stays.  LangGraph refuses to run ``Command(resume=...)``
   without a checkpointer at all::

       RuntimeError: Cannot use Command(resume=...) without checkpointer

   so the interrupt/auto-resume path (``agent/ec_tasks/runner.py``) depends on
   one existing.  This test pins that dependency: if it is ever dropped, the
   auto-resume path breaks in a way that only shows up at runtime.
"""

import pytest

from agent import checkpointing as ck


def test_durable_backends_are_not_declared_as_dependencies():
    """The removed packages must not creep back into the requirements."""
    from pathlib import Path

    req = Path("requirements-base.txt").read_text(encoding="utf-8")
    assert "langgraph-checkpoint-sqlite" not in req
    assert "langgraph-checkpoint-postgres" not in req
    assert "psycopg[binary]" not in req


def test_asking_for_sqlite_raises_rather_than_degrading(monkeypatch):
    monkeypatch.setenv(ck.ENV_KIND, "sqlite")
    with pytest.raises(ck.CheckpointerUnavailable) as exc:
        ck.build_checkpointer()
    assert "sqlite" in str(exc.value)


def test_asking_for_postgres_raises_rather_than_degrading(monkeypatch):
    monkeypatch.setenv(ck.ENV_KIND, "postgres")
    with pytest.raises(ck.CheckpointerUnavailable) as exc:
        ck.build_checkpointer()
    assert "postgres" in str(exc.value)


def test_the_in_memory_saver_is_still_built(monkeypatch):
    monkeypatch.delenv(ck.ENV_KIND, raising=False)
    from langgraph.checkpoint.memory import InMemorySaver

    assert isinstance(ck.build_checkpointer(), InMemorySaver)
    assert ck.is_durable() is False


def test_the_in_memory_saver_is_required_for_resume():
    """The reason the in-memory saver was kept.

    Without a checkpointer LangGraph refuses ``Command(resume=...)``, which is
    exactly how the runner resumes a graph after a pend_event interrupt.
    """
    from typing import TypedDict

    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.graph import END, START, StateGraph
    from langgraph.types import Command, interrupt

    class _S(TypedDict):
        v: str

    def _work(state):
        return {"v": interrupt({"ask": "continue?"})}

    def _build(checkpointer):
        g = StateGraph(_S)
        g.add_node("work", _work)
        g.add_edge(START, "work")
        g.add_edge("work", END)
        return g.compile(checkpointer=checkpointer)

    cfg = {"configurable": {"thread_id": "t1"}}

    # With the in-memory saver: interrupt, then resume.
    graph = _build(InMemorySaver())
    assert "__interrupt__" in graph.invoke({"v": ""}, cfg)
    assert graph.invoke(Command(resume="yes"), cfg) == {"v": "yes"}

    # Without any checkpointer: the resume itself fails.
    bare = _build(None)
    with pytest.raises(RuntimeError, match="without checkpointer"):
        bare.invoke(Command(resume="yes"), cfg)
