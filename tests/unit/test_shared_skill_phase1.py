"""Phase 1 regression tests for shared-skill concurrent execution.

Covers docs/SHARED_SKILL_MULTI_TASK_PLAN.md Phase 1:
- B1: executor checkpoint cleanup is scoped to the finishing task's thread_id
  (a sibling task's checkpoints on the SAME skill survive).
- B3: the mt068 agent-id recovery cache is task-scoped and declines
  ambiguous recovery when multiple agents share one skill.
- Concurrency: one compiled graph + one InMemorySaver serves parallel runs
  with distinct thread_ids without state crosstalk.
"""

import threading
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from langgraph.checkpoint.base import empty_checkpoint
from langgraph.checkpoint.memory import InMemorySaver

from agent.ec_tasks.executor import TaskExecutor


def _put_checkpoint(saver: InMemorySaver, thread_id: str) -> None:
    config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
    saver.put(config, empty_checkpoint(), {"source": "test", "step": 0, "parents": {}}, {})


def _saver_thread_ids(saver: InMemorySaver) -> set:
    return set(saver.storage.keys())


def _make_task(saver: InMemorySaver, thread_id: str, *, interrupted: bool = False):
    from a2a.types import TaskState

    state = TaskState.input_required if interrupted else TaskState.completed
    return SimpleNamespace(
        metadata={"config": {"configurable": {"thread_id": thread_id, "store": None}}},
        skill=SimpleNamespace(runnable=SimpleNamespace(checkpointer=saver)),
        status=SimpleNamespace(state=state),
    )


@pytest.fixture(autouse=True)
def _no_build_node_cache_clear():
    """Keep the executor cleanup test independent of build_node's module caches."""
    with patch("agent.ec_skills.build_node._clear_module_caches"):
        yield


class TestPerThreadCheckpointCleanup:
    def test_cleanup_deletes_only_own_thread(self):
        saver = InMemorySaver()
        _put_checkpoint(saver, "thread-a")
        _put_checkpoint(saver, "thread-b")

        TaskExecutor(_make_task(saver, "thread-a"))._clear_skill_module_caches()

        assert _saver_thread_ids(saver) == {"thread-b"}

    def test_cleanup_skips_own_thread_when_interrupted(self):
        saver = InMemorySaver()
        _put_checkpoint(saver, "thread-a")

        TaskExecutor(_make_task(saver, "thread-a", interrupted=True))._clear_skill_module_caches()

        assert _saver_thread_ids(saver) == {"thread-a"}

    def test_sibling_parked_interrupt_survives_completion(self):
        """Task A completes while task B (same skill/saver) is parked on an
        interrupt — B's checkpoints must survive A's cleanup."""
        saver = InMemorySaver()
        _put_checkpoint(saver, "thread-a")
        _put_checkpoint(saver, "thread-b")

        # B parks first (no deletion), then A completes.
        TaskExecutor(_make_task(saver, "thread-b", interrupted=True))._clear_skill_module_caches()
        TaskExecutor(_make_task(saver, "thread-a"))._clear_skill_module_caches()

        assert _saver_thread_ids(saver) == {"thread-b"}

    def test_cleanup_without_thread_id_leaves_saver_untouched(self):
        saver = InMemorySaver()
        _put_checkpoint(saver, "thread-b")

        task = _make_task(saver, "ignored")
        task.metadata = {}  # no cached config → no thread_id
        TaskExecutor(task)._clear_skill_module_caches()

        assert _saver_thread_ids(saver) == {"thread-b"}


class TestAgentIdRecoveryCache:
    @pytest.fixture(autouse=True)
    def _clean_cache(self):
        from agent.ec_skills import build_node

        build_node._last_known_agent_id_by_node.clear()
        build_node._known_agent_ids_by_node.clear()
        yield
        build_node._last_known_agent_id_by_node.clear()
        build_node._known_agent_ids_by_node.clear()

    @staticmethod
    def _recover(node, state, agent_id):
        from agent.ec_skills.build_node import _record_or_recover_agent_id

        return _record_or_recover_agent_id(node, state, agent_id)

    def test_record_then_recover_same_scope(self):
        state = {"attributes": {"thread_id": "t1"}}
        assert self._recover("fd_node", state, "agent-A") == "agent-A"
        assert self._recover("fd_node", {"attributes": {"thread_id": "t1"}}, None) == "agent-A"

    def test_two_agents_same_node_do_not_cross_contaminate(self):
        self._recover("fd_node", {"attributes": {"thread_id": "t1"}}, "agent-A")
        self._recover("fd_node", {"attributes": {"thread_id": "t2"}}, "agent-B")

        assert self._recover("fd_node", {"attributes": {"thread_id": "t1"}}, None) == "agent-A"
        assert self._recover("fd_node", {"attributes": {"thread_id": "t2"}}, None) == "agent-B"

    def test_degraded_state_single_agent_recovers(self):
        """Old single-agent behaviour is preserved even when the degraded
        state lost the scope identifiers entirely."""
        self._recover("fd_node", {"attributes": {"thread_id": "t1"}}, "agent-A")
        assert self._recover("fd_node", {}, None) == "agent-A"

    def test_degraded_state_multiple_agents_declines(self):
        self._recover("fd_node", {"attributes": {"thread_id": "t1"}}, "agent-A")
        self._recover("fd_node", {"attributes": {"thread_id": "t2"}}, "agent-B")
        assert self._recover("fd_node", {}, None) is None

    def test_unknown_node_returns_none(self):
        assert self._recover("never_seen", {"attributes": {"thread_id": "t1"}}, None) is None


class TestSharedGraphConcurrency:
    def test_parallel_runs_have_independent_state(self):
        """One compiled graph + one InMemorySaver, invoked concurrently with
        distinct thread_ids: no crosstalk, and per-thread deletes only
        remove their own thread."""
        from typing_extensions import TypedDict

        from langgraph.graph import StateGraph

        class S(TypedDict):
            val: str

        def node(state: S) -> S:
            return {"val": state["val"] + "-done"}

        g = StateGraph(S)
        g.add_node("work", node)
        g.set_entry_point("work")
        g.set_finish_point("work")
        saver = InMemorySaver()
        compiled = g.compile(checkpointer=saver)

        results: dict[str, str] = {}
        errors: list[BaseException] = []

        def run(tid: str):
            try:
                out = compiled.invoke(
                    {"val": tid}, config={"configurable": {"thread_id": tid}}
                )
                results[tid] = out["val"]
            except BaseException as e:  # pragma: no cover - surfaced via assert
                errors.append(e)

        tids = [f"t{i}" for i in range(4)]
        threads = [threading.Thread(target=run, args=(tid,)) for tid in tids]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert not errors
        assert results == {tid: f"{tid}-done" for tid in tids}
        assert _saver_thread_ids(saver) == set(tids)

        saver.delete_thread("t0")
        assert _saver_thread_ids(saver) == {"t1", "t2", "t3"}
