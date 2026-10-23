"""The durable sqlite checkpointer must actually work on the desktop build.

Two separate blockers used to make ``ECAN_CHECKPOINTER=sqlite`` unusable:

1. **The dependency was missing.**  ``langgraph-checkpoint-sqlite`` was
   never declared in any requirements file, so the import failed and
   ``build_checkpointer()`` raised ``CheckpointerUnavailable``.

2. **The context manager was dropped.**  ``SqliteSaver.from_conn_string``
   returns a ``@contextmanager`` generator; the *context manager* owns the
   sqlite connection and closes it in its ``finally``.  Writing
   ``saver = cm.__enter__()`` drops the last reference to ``cm`` at the end
   of the statement, the generator is collected, the connection closes, and
   the very next ``setup()`` fails with "Cannot operate on a closed
   database".

The second one is the interesting bug: it is not a missing package, it is
a lifetime bug that would have bitten every deployment the moment the
dependency was added.
"""

import gc
import os

import pytest

from agent import checkpointing as ck


sqlite_saver = pytest.importorskip(
    "langgraph.checkpoint.sqlite",
    reason="langgraph-checkpoint-sqlite is not installed in this environment",
)


def test_sqlite_checkpointer_is_declared_as_a_dependency():
    """The package must be in the requirements, not just installed here."""
    from pathlib import Path

    req = Path("requirements-base.txt").read_text(encoding="utf-8")
    assert "langgraph-checkpoint-sqlite" in req, (
        "the sqlite checkpointer must be declared, otherwise a fresh install "
        "cannot build it"
    )


def test_build_checkpointer_builds_a_sqlite_saver(monkeypatch, tmp_path):
    monkeypatch.setenv(ck.ENV_KIND, "sqlite")
    monkeypatch.setenv(ck.ENV_DSN, str(tmp_path / "ck.sqlite"))

    saver = ck.build_checkpointer()
    assert isinstance(saver, sqlite_saver.SqliteSaver)
    assert ck.is_durable() is True


def test_the_sqlite_connection_survives_garbage_collection(monkeypatch, tmp_path):
    """The regression: the context manager owns the connection, so it must
    outlive the ``__enter__`` call.  Without that, the connection is closed
    the moment the builder returns and every later use fails.
    """
    monkeypatch.setenv(ck.ENV_KIND, "sqlite")
    monkeypatch.setenv(ck.ENV_DSN, str(tmp_path / "ck.sqlite"))

    saver = ck.build_checkpointer()
    gc.collect()

    # The connection must still be usable.
    saver.conn.execute("select 1").fetchone()
    assert saver.is_setup is True


def test_the_sqlite_tables_are_really_created(monkeypatch, tmp_path):
    """``setup()`` must have run against a live connection."""
    monkeypatch.setenv(ck.ENV_KIND, "sqlite")
    monkeypatch.setenv(ck.ENV_DSN, str(tmp_path / "ck.sqlite"))

    saver = ck.build_checkpointer()
    names = {
        row[0]
        for row in saver.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "checkpoints" in names
    assert "writes" in names


def test_enter_and_keep_preserves_the_context_manager(monkeypatch, tmp_path):
    """The helper must keep the context manager alive next to the saver."""
    import contextlib

    class _Saver:
        pass

    @contextlib.contextmanager
    def cm():
        try:
            yield _Saver()
        finally:
            pass

    manager = cm()
    entered = ck._enter_and_keep(manager)
    assert isinstance(entered, _Saver)

    # The context manager must be reachable from the saver, so it cannot
    # be collected while the saver is alive.
    assert getattr(entered, "_eCan_context_manager", None) is manager


def test_enter_and_keep_falls_back_when_the_saver_refuses_attributes(monkeypatch):
    """A saver that forbids attribute assignment must still keep the
    connection open — via the module-level fallback list.
    """
    import contextlib

    closed = []

    @contextlib.contextmanager
    def cm():
        try:
            yield _NoAttrs()
        finally:
            closed.append(True)

    ck._KEEP_ALIVE.clear()
    manager = cm()
    entered = ck._enter_and_keep(manager)
    gc.collect()

    assert isinstance(entered, _NoAttrs)
    assert manager in ck._KEEP_ALIVE


class _NoAttrs:
    """A saver-like object that refuses attribute assignment."""

    __slots__ = ()

    def __setattr__(self, name, value):
        raise AttributeError("no attributes here")
