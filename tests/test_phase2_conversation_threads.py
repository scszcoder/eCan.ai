"""Phase 2 + 3.1 of Path 1.5 — conversation as the unit of isolation.

The 2026-04-27 incident: a Q&A worker handling several customers by round-robin
typed customer A's answer into customer B's tab, because the LangGraph state is
per chatter-task and a chatter task is per-*agent*, not per-customer — so every
customer shared one ``state["history"]``.

Phase 2 makes the conversation the thread key so that state is naturally
separate. Phase 3.1 puts the existing per-turn history clear behind a flag that
is **on by default** — it is not removed, because until a live multi-customer
run proves threads isolate, that clear is the only thing keeping customers
apart.
"""

import pytest

from agent import conversation_threads as ct


@pytest.fixture(autouse=True)
def _flag_off(monkeypatch):
    monkeypatch.delenv(ct.ENV_ENABLED, raising=False)
    yield


# ---------------------------------------------------------------------------
# Conversation identity
# ---------------------------------------------------------------------------

def test_inbound_customer_turn_is_a_conversation():
    payload = {"customer_id": "cust-A", "latest_message": "有运费险吗"}
    assert ct.conversation_id_from_payload(payload) == "cust-A"


def test_camelcase_customer_id_also_recognised():
    payload = {"customerId": "cust-B", "latest_message": "hello"}
    assert ct.conversation_id_from_payload(payload) == "cust-B"


def test_qa_reply_is_not_a_conversation_turn():
    """A reply flowing back to front-desk must not open a conversation thread."""
    payload = {"customer_id": "cust-A", "latest_message": "x",
               "response_text": "您好"}
    assert ct.conversation_id_from_payload(payload) is None


def test_non_dispatch_payloads_are_ignored():
    for payload in (None, "", {}, {"latest_message": "no customer"},
                    {"customer_id": "c"}, ["not", "a", "dict"]):
        assert ct.conversation_id_from_payload(payload) is None


def test_detection_matches_build_nodes_own_rule():
    """Must agree with _is_qa_inbound_payload or the two will drift apart."""
    from agent.ec_skills.build_node import _is_qa_inbound_payload
    cases = [
        {"customer_id": "c", "latest_message": "m"},
        {"customer_id": "c", "latest_message": "m", "response_text": "r"},
        {"customerId": "c", "latest_message": "m"},
        {"latest_message": "m"},
        {"customer_id": "c"},
        {},
    ]
    for payload in cases:
        assert bool(ct.conversation_id_from_payload(payload)) == \
            _is_qa_inbound_payload(payload), payload


# ---------------------------------------------------------------------------
# Thread keys
# ---------------------------------------------------------------------------

def test_two_customers_on_one_agent_get_different_threads():
    """The incident, expressed as a key assertion."""
    a = ct.thread_id_for("agent-1", "cust-A")
    b = ct.thread_id_for("agent-1", "cust-B")
    assert a != b


def test_same_customer_on_two_agents_gets_different_threads():
    """Otherwise the cross-talk bug reappears one level up."""
    assert ct.thread_id_for("agent-1", "cust-A") != ct.thread_id_for("agent-2", "cust-A")


def test_thread_key_is_stable_across_turns():
    assert ct.thread_id_for("agent-1", "cust-A") == ct.thread_id_for("agent-1", "cust-A")


def test_conversation_id_is_required():
    with pytest.raises(ValueError):
        ct.thread_id_for("agent-1", "")


def test_conversation_threads_are_identifiable_from_the_id_alone():
    """The cleanup path only has the id — it must be able to tell."""
    assert ct.is_conversation_thread(ct.thread_id_for("a", "c")) is True
    assert ct.is_conversation_thread("d7a1f2b0-uuid-task-thread") is False
    assert ct.is_conversation_thread(None) is False


# ---------------------------------------------------------------------------
# Config resolution — off by default
# ---------------------------------------------------------------------------

_BASE = {"configurable": {"thread_id": "task-uuid", "store": None},
         "recursion_limit": 200}


def test_disabled_by_default_config_untouched():
    payload = {"customer_id": "cust-A", "latest_message": "m"}
    out = ct.resolve_thread_config(_BASE, "agent-1", payload)
    assert out["configurable"]["thread_id"] == "task-uuid"


def test_enabled_rekeys_onto_the_conversation(monkeypatch):
    monkeypatch.setenv(ct.ENV_ENABLED, "1")
    payload = {"customer_id": "cust-A", "latest_message": "m"}
    out = ct.resolve_thread_config(_BASE, "agent-1", payload)
    assert out["configurable"]["thread_id"] == ct.thread_id_for("agent-1", "cust-A")
    assert out["recursion_limit"] == 200          # rest of the config preserved


def test_enabled_but_non_conversation_payload_keeps_task_thread(monkeypatch):
    monkeypatch.setenv(ct.ENV_ENABLED, "1")
    out = ct.resolve_thread_config(_BASE, "agent-1", {"response_text": "reply"})
    assert out["configurable"]["thread_id"] == "task-uuid"


def test_resolution_does_not_mutate_the_cached_task_config(monkeypatch):
    """The executor caches this dict per task; turning the flag off must leave no residue."""
    monkeypatch.setenv(ct.ENV_ENABLED, "1")
    base = {"configurable": {"thread_id": "task-uuid"}}
    ct.resolve_thread_config(base, "agent-1", {"customer_id": "c", "latest_message": "m"})
    assert base["configurable"]["thread_id"] == "task-uuid"


# ---------------------------------------------------------------------------
# 2.3 — conversation threads survive a finishing task
# ---------------------------------------------------------------------------

def test_executor_retains_conversation_threads_on_task_end():
    """A finishing task must not delete a conversation others are still using."""
    from pathlib import Path
    src = Path("agent/ec_tasks/executor.py").read_text(encoding="utf-8")
    assert "is_conversation_thread(thread_id)" in src
    assert "conversation-scoped; retained" in src
    # the guard runs BEFORE the delete
    assert src.index("is_conversation_thread(thread_id)") < src.index("saver.delete_thread(thread_id)")


# ---------------------------------------------------------------------------
# 3.1 — the isolation hack is flagged, NOT removed
# ---------------------------------------------------------------------------

def test_history_clear_still_exists_and_defaults_on(monkeypatch):
    from agent.ec_skills.build_node import _reset_qa_history_on_customer_change
    monkeypatch.delenv("ECAN_QA_HISTORY_ISOLATION", raising=False)

    state = {"history": ["A asked 有红色的吗", "A was answered"], "prompts": ["p"]}
    payload = {"customer_id": "cust-B", "latest_message": "转人工"}

    assert _reset_qa_history_on_customer_change(state, payload, node_name="t") is True
    assert state["history"] == [], "customer A's turn must not survive into B's"
    assert state["prompts"] == []


def test_history_clear_can_be_disabled_for_ab_testing(monkeypatch):
    """Phase 2 needs to A/B against it — but only deliberately."""
    from agent.ec_skills.build_node import _reset_qa_history_on_customer_change
    monkeypatch.setenv("ECAN_QA_HISTORY_ISOLATION", "0")

    state = {"history": ["A's turn"], "prompts": []}
    payload = {"customer_id": "cust-B", "latest_message": "转人工"}

    assert _reset_qa_history_on_customer_change(state, payload, node_name="t") is False
    assert state["history"] == ["A's turn"], "flag off means genuinely off"


def test_disabling_the_clear_is_logged_loudly(monkeypatch):
    from agent.ec_skills.build_node import _reset_qa_history_on_customer_change
    monkeypatch.setenv("ECAN_QA_HISTORY_ISOLATION", "0")

    class _Log:
        def __init__(self): self.warnings = []
        def warning(self, m, *a, **k): self.warnings.append(m)
        def debug(self, m, *a, **k): pass
        def info(self, m, *a, **k): pass

    log = _Log()
    _reset_qa_history_on_customer_change(
        {"history": [], "prompts": []},
        {"customer_id": "c", "latest_message": "m"},
        node_name="t", logger_=log)

    assert any("DISABLED" in w for w in log.warnings)
    assert any("bleed" in w for w in log.warnings)


def test_phase3_did_not_delete_the_incident_record():
    """The 2026-04-27 rationale must stay attached to the code."""
    from pathlib import Path
    src = Path("agent/ec_skills/build_node.py").read_text(encoding="utf-8")
    assert "2026-04-27" in src
    assert "do not turn this off in" in src.lower()
