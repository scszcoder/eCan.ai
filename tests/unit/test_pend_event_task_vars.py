"""pend_event {{var}} placeholder resolution from task_vars (runner.py).

Shared skills stay agent-agnostic: a pend_event node's agentIds /
matchFields may carry ``{{front_desk_agent_id}}`` instead of a concrete
agent id (which would be a per-deployment value baked into a shared,
published artifact — the 飞鸽客服问答00 blocker: the published diagram
hard-coded the author's own long-gone front-desk agent id, so on every
other machine the Q&A skill filtered out all real dispatches).

``_extract_event_types_from_skill(skill, task)`` resolves the tokens at
task-launch time from ``task.metadata["task_vars"]``; an unresolvable
token DROPS the filter (catch-all + WARNING) instead of installing a
literal ``{{...}}`` that can never match.
"""

from types import SimpleNamespace

import agent.ec_tasks  # noqa: F401  (import order: avoids prep_skills_run circular import)
from agent.ec_tasks.runner import TaskRunner


def _skill(agent_ids="", match_literal=None, pending=None):
    mf = []
    if match_literal is not None:
        mf.append({"event_path": "context.senderId", "literal": match_literal})
    node = {
        "id": "pend_event_1",
        "type": "pend_event_node",
        "data": {
            "title": "PendEvent_1",
            "inputsValues": {
                "eventType": {"type": "constant", "content": "chat_message"},
                "agentIds": {"type": "constant", "content": agent_ids},
                "matchFields": {"type": "constant", "content": mf},
                "pendingSources": {"type": "constant", "content": pending or []},
            },
        },
    }
    return SimpleNamespace(diagram={"workFlow": {"nodes": [node], "edges": []}}, name="qa_skill")


def _task(task_vars=None):
    return SimpleNamespace(metadata={"task_vars": task_vars or {}}, name="飞鸽客服应答001", id="task_1")


def _extract(skill, task=None):
    # The method touches no instance state — unbound call keeps the test light.
    return TaskRunner._extract_event_types_from_skill(None, skill, task)


def _sender_literals(entry):
    return [mf.get("literal") for mf in entry.get("match_fields", [])
            if mf.get("event_path") == "context.senderId"]


class TestAgentIdsPlaceholder:
    def test_placeholder_resolves_from_task_vars(self):
        entries = _extract(_skill(agent_ids="{{front_desk_agent_id}}"),
                           _task({"front_desk_agent_id": "agent_fd1"}))
        assert len(entries) == 1
        assert _sender_literals(entries[0]) == ["agent_fd1"]

    def test_unresolved_placeholder_drops_filter_not_entry(self):
        entries = _extract(_skill(agent_ids="{{front_desk_agent_id}}"),
                           _task({"store_url": "https://x"}))
        assert len(entries) == 1  # the routing entry survives (catch-all)…
        assert _sender_literals(entries[0]) == []  # …with no impossible filter

    def test_no_task_given_drops_placeholder_filter(self):
        entries = _extract(_skill(agent_ids="{{front_desk_agent_id}}"))
        assert _sender_literals(entries[0]) == []

    def test_concrete_id_passes_through_unchanged(self):
        entries = _extract(_skill(agent_ids="agent_abc"), _task({"front_desk_agent_id": "agent_fd1"}))
        assert _sender_literals(entries[0]) == ["agent_abc"]

    def test_comma_separated_var_becomes_membership_list(self):
        entries = _extract(_skill(agent_ids="{{front_desk_agent_id}}"),
                           _task({"front_desk_agent_id": "agent_a,agent_b"}))
        assert _sender_literals(entries[0]) == [["agent_a", "agent_b"]]


class TestMatchFieldsLiteralPlaceholder:
    """The skill editor materializes agentIds into a context.senderId
    matchFields literal — that copy must resolve too."""

    def test_literal_placeholder_resolves(self):
        entries = _extract(_skill(match_literal="{{front_desk_agent_id}}"),
                           _task({"front_desk_agent_id": "agent_fd1"}))
        assert _sender_literals(entries[0]) == ["agent_fd1"]

    def test_unresolved_literal_drops_only_that_entry(self):
        entries = _extract(_skill(match_literal="{{front_desk_agent_id}}"), _task({}))
        assert _sender_literals(entries[0]) == []

    def test_both_agent_ids_and_literal_resolve_consistently(self):
        # The real 问答00 diagram carries BOTH — under match_mode "all" they
        # must resolve to the same value or the rule can never match.
        entries = _extract(_skill(agent_ids="{{front_desk_agent_id}}",
                                  match_literal="{{front_desk_agent_id}}"),
                           _task({"front_desk_agent_id": "agent_fd1"}))
        assert _sender_literals(entries[0]) == ["agent_fd1", "agent_fd1"]

    def test_concrete_literal_untouched(self):
        entries = _extract(_skill(match_literal="agent_abc"), _task({}))
        assert _sender_literals(entries[0]) == ["agent_abc"]

    def test_multi_id_var_in_literal_becomes_list(self):
        entries = _extract(_skill(match_literal="{{front_desk_agent_id}}"),
                           _task({"front_desk_agent_id": "agent_a,agent_b"}))
        assert _sender_literals(entries[0]) == [["agent_a", "agent_b"]]


class TestPendingSourcesPlaceholder:
    def test_source_agent_ids_placeholder_resolves(self):
        pending = [{"type": "task_request", "agentIds": "{{front_desk_agent_id}}"}]
        entries = _extract(_skill(pending=pending), _task({"front_desk_agent_id": "agent_fd1"}))
        tr = [e for e in entries if e["event_type"] == "task_request"]
        assert len(tr) == 1
        assert _sender_literals(tr[0]) == ["agent_fd1"]
