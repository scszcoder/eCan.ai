"""Phase 0 of Path 1.5 (durable residency) — the three independent seams.

None of this changes desktop behaviour. It puts the pieces in place that let a
conversation later outlive the pod serving it:

  0.1  state appended to history/messages stays checkpointer-safe
  0.2  the checkpointer is chosen in one place, and a durable backend that
       cannot be built FAILS instead of silently degrading to memory
  0.3  skills and tasks can declare where they may run and how long they live

The 0.2 failure mode is the important one. A cloud pod that asks for Postgres
and silently gets an in-memory saver looks healthy right up until a restart
eats a conversation — the same silent-no-op class as
``AppContextMeta.__getattr__`` returning None for a missing service.
"""

import pytest

from agent import checkpointing as ck


# ---------------------------------------------------------------------------
# 0.1 — serializability
# ---------------------------------------------------------------------------

class _LiveHandle:
    """Stand-in for a driver/socket/widget — exactly what must never land in state."""

    def __init__(self):
        self.conn = object()


def test_langchain_messages_are_checkpoint_safe():
    from langchain_core.messages import AIMessage, HumanMessage
    assert ck.is_checkpoint_safe(HumanMessage(content="有运费险吗"))
    assert ck.is_checkpoint_safe(AIMessage(content="有的"))


def test_action_message_is_checkpoint_safe():
    """ActionMessage subclasses BaseMessage — the real history payload."""
    from agent.ec_skills.build_node import ActionMessage
    assert ck.is_checkpoint_safe(ActionMessage(content="did a thing"))


def test_plain_data_is_checkpoint_safe():
    assert ck.is_checkpoint_safe({"role": "user", "n": 3, "tags": ["a", "b"]})
    assert ck.is_checkpoint_safe([1, "two", None, True, {"k": [1, 2]}])


def test_live_objects_are_not_checkpoint_safe():
    assert not ck.is_checkpoint_safe(_LiveHandle())
    assert not ck.is_checkpoint_safe(lambda x: x)
    # nested one level down is still caught
    assert not ck.is_checkpoint_safe({"ok": 1, "bad": _LiveHandle()})
    assert not ck.is_checkpoint_safe([{"deep": [_LiveHandle()]}])


def test_strict_check_is_off_by_default(monkeypatch):
    """Phase 0 must not change behaviour: unflagged, nothing raises."""
    monkeypatch.delenv(ck.ENV_STRICT, raising=False)
    ck.assert_checkpoint_safe([_LiveHandle()], where="test")  # no raise


def test_strict_check_fails_loudly_when_enabled(monkeypatch):
    monkeypatch.setenv(ck.ENV_STRICT, "1")
    with pytest.raises(TypeError) as exc:
        ck.assert_checkpoint_safe([_LiveHandle()], where="add_to_history")
    assert "_LiveHandle" in str(exc.value)
    assert "add_to_history" in str(exc.value)


def test_add_to_history_rejects_unpersistable_state_when_strict(monkeypatch):
    """The regression net, on the real call path."""
    from agent.ec_skills.build_node import add_to_history
    monkeypatch.setenv(ck.ENV_STRICT, "1")

    state = {"history": []}
    with pytest.raises(TypeError):
        add_to_history(state, [_LiveHandle()])


def test_add_to_history_still_works_for_real_messages(monkeypatch):
    from langchain_core.messages import HumanMessage
    from agent.ec_skills.build_node import add_to_history
    monkeypatch.setenv(ck.ENV_STRICT, "1")

    state = {"history": []}
    add_to_history(state, [HumanMessage(content="hi")])
    assert len(state["history"]) == 1


def test_add_to_history_still_prunes(monkeypatch):
    """Guard the pre-existing behaviour the new check sits in front of."""
    from agent.ec_skills.build_node import add_to_history
    monkeypatch.delenv(ck.ENV_STRICT, raising=False)

    state = {"history": []}
    add_to_history(state, [f"m{i}" for i in range(250)], max_entries=200)
    assert len(state["history"]) == 200
    assert state["history"][0] == "m50"


# ---------------------------------------------------------------------------
# 0.2 — checkpointer factory
# ---------------------------------------------------------------------------

def test_default_is_in_memory_saver(monkeypatch):
    """Desktop behaviour, unchanged."""
    monkeypatch.delenv(ck.ENV_KIND, raising=False)
    from langgraph.checkpoint.memory import InMemorySaver

    assert ck.selected_kind() == "memory"
    assert ck.is_durable() is False
    assert isinstance(ck.build_checkpointer(), InMemorySaver)


def test_blank_or_none_still_means_memory(monkeypatch):
    for value in ("", "  ", "none", "MEMORY", "InMemory"):
        monkeypatch.setenv(ck.ENV_KIND, value)
        assert ck.selected_kind() == "memory", value
        assert ck.is_durable() is False


def test_unknown_backend_raises_rather_than_defaulting(monkeypatch):
    monkeypatch.setenv(ck.ENV_KIND, "redis")
    with pytest.raises(ck.CheckpointerUnavailable):
        ck.build_checkpointer()


def test_durable_backend_without_dsn_raises(monkeypatch):
    monkeypatch.setenv(ck.ENV_KIND, "postgres")
    monkeypatch.delenv(ck.ENV_DSN, raising=False)
    with pytest.raises(ck.CheckpointerUnavailable) as exc:
        ck.build_checkpointer()
    assert ck.ENV_DSN in str(exc.value)


def test_missing_durable_dependency_raises_not_silently_memory(monkeypatch):
    """The whole point of 0.2: never quietly hand back an in-memory saver."""
    monkeypatch.setenv(ck.ENV_KIND, "postgres")
    monkeypatch.setenv(ck.ENV_DSN, "postgresql://user:pw@host/db")
    try:
        import langgraph.checkpoint.postgres  # noqa: F401
        pytest.skip("postgres saver installed; unavailability path not exercised here")
    except ImportError:
        pass

    with pytest.raises(ck.CheckpointerUnavailable) as exc:
        ck.build_checkpointer()
    assert "not installed" in str(exc.value)
    assert ck.is_durable() is True  # and it still reports itself as durable


def test_saver_class_named_in_exactly_one_place():
    """No call site outside the factory names a saver class."""
    from pathlib import Path
    skill_src = Path("agent/ec_skill.py").read_text(encoding="utf-8")
    assert "InMemorySaver()" not in skill_src
    assert "build_checkpointer()" in skill_src


def test_executor_cleanup_does_not_poke_durable_saver_internals():
    """The InMemorySaver-internals fallback must be shape-guarded, not a bare else.

    executor.py deletes a finished task's thread from the saver. Its legacy
    fallback reaches into ``saver.storage`` / ``.writes`` / ``.blobs`` — valid
    for the in-memory saver, meaningless for a durable one.
    """
    from pathlib import Path
    src = Path("agent/ec_tasks/executor.py").read_text(encoding="utf-8")
    assert 'elif isinstance(getattr(saver, "storage", None), dict):' in src
    # and an unknown saver says so instead of failing silently
    assert "NOT deleted" in src


# ---------------------------------------------------------------------------
# 0.3 — placement declarations
# ---------------------------------------------------------------------------

def test_skill_defaults_are_permissive():
    from agent.ec_skill import EC_Skill
    sk = EC_Skill(name="t", description="d")
    assert sk.residency == "any"
    assert sk.lifetime == "conversation"
    assert sk.requires == []


def test_task_defaults_are_permissive():
    from agent.ec_tasks.models import ManagedTask
    # ManagedTask extends the a2a Task, which requires contextId.
    t = ManagedTask(name="t", contextId="c1")
    assert t.residency == "any"
    assert t.lifetime == "conversation"
    assert t.requires == []


def test_skill_placement_round_trips_through_to_dict():
    """to_dict is an allowlist — a field missing from it is silently dropped."""
    from agent.ec_skill import EC_Skill
    sk = EC_Skill(name="t", description="d", residency="cloud",
                  lifetime="long_running", requires=["browser_local"])
    d = sk.to_dict()
    assert d["residency"] == "cloud"
    assert d["lifetime"] == "long_running"
    assert d["requires"] == ["browser_local"]


def test_invalid_placement_values_are_rejected():
    from agent.ec_skill import EC_Skill
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        EC_Skill(name="t", description="d", residency="somewhere")
    with pytest.raises(ValidationError):
        EC_Skill(name="t", description="d", lifetime="forever")


def test_long_running_is_declarable():
    """How a skill says 'never checkpoint me mid-run' (e.g. a crawling agent)."""
    from agent.ec_skill import EC_Skill
    sk = EC_Skill(name="crawler", description="d", lifetime="long_running")
    assert sk.lifetime == "long_running"


def test_placement_fields_do_not_derive_from_legacy_flags():
    """Deliberate: two sources of truth reconciled by guesswork is how contracts drift.

    run_in_cloud stays independent of residency until someone decides the
    mapping on purpose.
    """
    from agent.ec_skill import EC_Skill
    sk = EC_Skill(name="t", description="d", run_in_cloud=True)
    assert sk.residency == "any"
