# -*- coding: utf-8 -*-
"""A reused browser session with a dead bubus event bus must be flagged for
rebuild, not reused forever.

Customer run 2026-10-17 (build yao, 抖店 + 拼多多 in one process): the PDD front
desk failed 41× in ~2 min with ``bubus.service.QueueShutDown``. Its browser
launched once; every retry reused the SAME cached session whose event bus had
been shut down by a cancelled prior run, so ``browser_session.start()`` kept
re-dispatching ``BrowserStartEvent`` onto a dead queue. The recovery: on a
QueueShutDown failure, set ``_ecan_force_recreate`` on the cached session so
``get_or_create_browser_session`` rebuilds a fresh one next invocation (the
existing eviction path at build_helpers.py already honours that flag).
"""
import agent.ec_tasks.runner  # noqa: F401  (import runner first: prep<->ec_tasks cycle)
from agent.ec_skills.browser_node import build_helpers as bh
from agent.ec_skills.browser_node import runner as r
from bubus.service import QueueShutDown


def test_detects_queue_shutdown_direct_and_wrapped():
    assert r._exc_chain_has_queue_shutdown(QueueShutDown()) is True

    # Wrapped the way browser-use/our runner re-raise it (implicit __context__).
    try:
        try:
            raise QueueShutDown()
        except Exception as inner:
            raise RuntimeError("wrapped") from inner
    except Exception as e:
        assert r._exc_chain_has_queue_shutdown(e) is True

    # Chain deliberately broken (`from None`) — message fallback still catches it.
    assert r._exc_chain_has_queue_shutdown(
        RuntimeError("Browser automation failed: QueueShutDown()")
    ) is True

    assert r._exc_chain_has_queue_shutdown(ValueError("unrelated")) is False


def test_force_recreate_flags_cached_session():
    class _FakeSession:
        pass

    scope = "chat:test-scope@pdd"
    sess = _FakeSession()
    bh.cached_browser_sessions[scope] = sess
    try:
        r._force_recreate_cached_session(scope)
        assert getattr(sess, "_ecan_force_recreate", False) is True
    finally:
        bh.cached_browser_sessions.pop(scope, None)


def test_force_recreate_falls_back_to_agent_session_when_not_cached():
    class _FakeSession:
        pass

    class _FakeAgent:
        def __init__(self, s):
            self.browser_session = s

    sess = _FakeSession()
    # Not in the cache — must still flag the agent's live session.
    r._force_recreate_cached_session("chat:absent", agent=_FakeAgent(sess))
    assert getattr(sess, "_ecan_force_recreate", False) is True


def test_force_recreate_never_raises_on_garbage():
    # Best-effort contract: bad inputs are swallowed, never propagated.
    r._force_recreate_cached_session(None)
    r._force_recreate_cached_session("", agent=None)
