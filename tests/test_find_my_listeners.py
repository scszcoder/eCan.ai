"""find_my_listeners() — deriving a front desk's group from the routing table.

The group is NOT a roster. It is read back from the ``context.senderId``
match_fields that a Q&A task's pend_event node installs at launch — the same
filter that decides whether the dispatch is accepted. These tests pin the
properties that make that safe, above all: **a rule with no sender filter is
not a member**. That case is a deliberate catch-all for delivery (an
unresolvable ``{{front_desk_agent_id}}`` is dropped rather than blackholing
events), and reading it as "listens to everyone" would put a misconfigured
agent into every front desk's group — the exact multi-store failure this
mechanism exists to prevent.
"""

import unittest
from unittest.mock import patch

from agent.ec_tasks.runner import (
    TaskRunnerRegistry,
    find_my_listeners,
    _declared_senders,
    _routing_rules_of,
    _listener_agent_for_rule,
)

FD = "agent_frontdesk_0001"
QA1 = "agent_qa_0001"
QA2 = "agent_qa_0002"
OTHER_FD = "agent_frontdesk_0002"


class _Task:
    def __init__(self, task_id, agent_id=""):
        self.id = task_id
        self.agent_id = agent_id


class _Card:
    def __init__(self, cid):
        self.id = cid


class _Agent:
    def __init__(self, cid):
        self.card = _Card(cid)


class _Runner:
    """Minimal stand-in for TaskRunner: the routing table + task lookup."""

    def __init__(self, routing, tasks, agent_id=""):
        self._global_event_routing = routing
        self._tasks = {t.id: t for t in tasks}
        self.agent = _Agent(agent_id) if agent_id else None

    def _find_task_by_id(self, task_id):
        return self._tasks.get(task_id)


def _rule(task_id, senders=None, **extra):
    """A routing rule shaped as _amend_event_routing_for_task builds it."""
    mf = list(extra.pop("match_fields", []))
    if senders is not None:
        mf.append({"event_path": "context.senderId", "literal": senders})
    r = {
        "task_selector": f"id:{task_id}",
        "_auto_added_by_task": task_id,
        "match_fields": mf,
    }
    r.update(extra)
    return r


class _RegistryPatch:
    """Swap TaskRunnerRegistry._runners for the duration of a test."""

    def __init__(self, runners):
        self.runners = runners

    def __enter__(self):
        self.saved = TaskRunnerRegistry._runners
        TaskRunnerRegistry._runners = list(self.runners)

    def __exit__(self, *exc):
        TaskRunnerRegistry._runners = self.saved
        return False


class DeclaredSendersTests(unittest.TestCase):
    def test_reads_a_single_string_literal(self):
        self.assertEqual(_declared_senders(_rule("t1", FD)), [FD])

    def test_reads_a_list_literal(self):
        self.assertEqual(_declared_senders(_rule("t1", [FD, OTHER_FD])), [FD, OTHER_FD])

    def test_no_sender_filter_yields_nothing(self):
        # The catch-all case. Must be empty, NOT a wildcard.
        self.assertEqual(_declared_senders(_rule("t1")), [])

    def test_unresolved_placeholder_is_not_a_sender(self):
        # task_vars carried no front_desk_agent_id; the literal survived verbatim.
        self.assertEqual(_declared_senders(_rule("t1", "{{front_desk_agent_id}}")), [])

    def test_partially_resolved_list_keeps_only_real_ids(self):
        self.assertEqual(
            _declared_senders(_rule("t1", [FD, "{{front_desk_agent_id}}"])), [FD]
        )

    def test_ignores_other_match_field_paths(self):
        r = _rule("t1", match_fields=[{"event_path": "context.chatId", "literal": FD}])
        self.assertEqual(_declared_senders(r), [])

    def test_tolerates_malformed_match_fields(self):
        r = {"match_fields": ["not-a-dict", None, {"event_path": "context.senderId"}]}
        self.assertEqual(_declared_senders(r), [])

    def test_missing_match_fields_key(self):
        self.assertEqual(_declared_senders({}), [])


class RuleUnwrapTests(unittest.TestCase):
    def test_bare_rule(self):
        r = _rule("t1", FD)
        self.assertEqual(_routing_rules_of(r), [r])

    def test_rule_chain(self):
        a, b = _rule("t1", FD), _rule("t2", FD)
        self.assertEqual(_routing_rules_of({"_rule_chain": [a, b]}), [a, b])

    def test_chain_drops_non_dict_entries(self):
        a = _rule("t1", FD)
        self.assertEqual(_routing_rules_of({"_rule_chain": [a, "junk", None]}), [a])

    def test_non_dict_entry(self):
        self.assertEqual(_routing_rules_of("junk"), [])


class ListenerAgentResolutionTests(unittest.TestCase):
    def test_prefers_the_task_row_agent_id(self):
        r = _Runner({}, [_Task("t1", QA1)], agent_id="runner_agent")
        self.assertEqual(_listener_agent_for_rule(r, _rule("t1", FD)), QA1)

    def test_falls_back_to_the_runner_agent_when_task_has_no_agent_id(self):
        # Fast-deploy links agent -> task, so task.agent_id is often blank.
        r = _Runner({}, [_Task("t1", "")], agent_id=QA1)
        self.assertEqual(_listener_agent_for_rule(r, _rule("t1", FD)), QA1)

    def test_unknown_task_resolves_to_nothing(self):
        # A stale rule loaded from event_routing.json for a task this runner
        # is not running. Attributing it to the runner's agent would invent a
        # listener that will never receive anything.
        r = _Runner({}, [], agent_id=QA1)
        self.assertEqual(_listener_agent_for_rule(r, _rule("t_gone", FD)), "")

    def test_recovers_task_id_from_selector_when_marker_absent(self):
        r = _Runner({}, [_Task("t1", QA1)])
        rule = {
            "task_selector": "id:t1",
            "match_fields": [{"event_path": "context.senderId", "literal": FD}],
        }
        self.assertEqual(_listener_agent_for_rule(r, rule), QA1)

    def test_no_task_reference_at_all(self):
        r = _Runner({}, [_Task("t1", QA1)])
        self.assertEqual(_listener_agent_for_rule(r, {"match_fields": []}), "")


class FindMyListenersTests(unittest.TestCase):
    def test_finds_the_agents_that_declared_me(self):
        runner = _Runner(
            {"chat_message": {"_rule_chain": [_rule("t1", FD), _rule("t2", FD)]}},
            [_Task("t1", QA1), _Task("t2", QA2)],
        )
        with _RegistryPatch([runner]):
            self.assertEqual(find_my_listeners(FD), [QA1, QA2])

    def test_excludes_agents_listening_to_a_different_front_desk(self):
        # THE multi-store case: store B's Q&A agent must not appear in store
        # A's group even though both run the same skill on one machine.
        runner = _Runner(
            {"chat_message": {"_rule_chain": [_rule("t1", FD), _rule("t2", OTHER_FD)]}},
            [_Task("t1", QA1), _Task("t2", QA2)],
        )
        with _RegistryPatch([runner]):
            self.assertEqual(find_my_listeners(FD), [QA1])

    def test_agent_with_no_sender_filter_is_not_a_member(self):
        # The trap: _extract_event_types_from_skill DROPS an unresolvable
        # placeholder so events are not blackholed. That agent accepts
        # anything, but it belongs to no group.
        runner = _Runner(
            {"chat_message": {"_rule_chain": [_rule("t1", FD), _rule("t2")]}},
            [_Task("t1", QA1), _Task("t2", QA2)],
        )
        with _RegistryPatch([runner]):
            self.assertEqual(find_my_listeners(FD), [QA1])

    def test_scans_every_registered_runner(self):
        # TaskRunner is per-agent (ec_agent.py:165), so each Q&A agent's rules
        # live on its own runner's table.
        r1 = _Runner({"chat_message": _rule("t1", FD)}, [_Task("t1", QA1)])
        r2 = _Runner({"chat_message": _rule("t2", FD)}, [_Task("t2", QA2)])
        with _RegistryPatch([r1, r2]):
            self.assertEqual(find_my_listeners(FD), [QA1, QA2])

    def test_deduplicates_an_agent_declared_under_several_event_types(self):
        runner = _Runner(
            {"chat_message": _rule("t1", FD), "a2a_response": _rule("t1", FD)},
            [_Task("t1", QA1)],
        )
        with _RegistryPatch([runner]):
            self.assertEqual(find_my_listeners(FD), [QA1])

    def test_never_returns_the_caller(self):
        # A front desk whose own pend_event listens for its own id must not
        # dispatch to itself.
        runner = _Runner({"chat_message": _rule("t1", FD)}, [_Task("t1", FD)])
        with _RegistryPatch([runner]):
            self.assertEqual(find_my_listeners(FD), [])

    def test_matches_a_list_literal_containing_me(self):
        runner = _Runner({"chat_message": _rule("t1", [OTHER_FD, FD])}, [_Task("t1", QA1)])
        with _RegistryPatch([runner]):
            self.assertEqual(find_my_listeners(FD), [QA1])

    def test_blank_sender_returns_nothing(self):
        runner = _Runner({"chat_message": _rule("t1", FD)}, [_Task("t1", QA1)])
        with _RegistryPatch([runner]):
            self.assertEqual(find_my_listeners(""), [])
            self.assertEqual(find_my_listeners(None), [])

    def test_empty_registry(self):
        with _RegistryPatch([]):
            self.assertEqual(find_my_listeners(FD), [])

    def test_runner_without_a_routing_table_is_skipped(self):
        broken = _Runner(None, [])
        good = _Runner({"chat_message": _rule("t1", FD)}, [_Task("t1", QA1)])
        with _RegistryPatch([broken, good]):
            self.assertEqual(find_my_listeners(FD), [QA1])


class NarrowToListenersTests(unittest.TestCase):
    """The dispatcher side: listeners narrow the pool, never widen it."""

    def setUp(self):
        from agent.ec_skills.node_runtime import frontdesk_dispatch as fd

        self.fd = fd
        self.cfg = fd.DispatchConfig(log_tag="Test")
        self.live = [{"id": QA1}, {"id": QA2}]

    def _run(self, listeners, env=None):
        with patch(
            "agent.ec_tasks.runner.find_my_listeners", return_value=listeners
        ), patch.dict("os.environ", env or {}, clear=False):
            return self.fd._narrow_to_listeners(self.cfg, FD, self.live)

    def test_narrows_to_the_declared_listeners(self):
        self.assertEqual(self._run([QA1]), [{"id": QA1}])

    def test_no_listeners_falls_back_to_the_full_pool_by_default(self):
        # Permissive default: a hand-built skill with no agentIds keeps
        # today's keyword-only behaviour instead of going dark.
        self.assertEqual(self._run([]), self.live)

    def test_no_listeners_aborts_under_strict_mode(self):
        self.assertIsNone(self._run([], {"ECAN_DISPATCH_LISTENERS_STRICT": "1"}))

    def test_listeners_outside_the_live_pool_fall_back_by_default(self):
        self.assertEqual(self._run(["agent_elsewhere"]), self.live)

    def test_listeners_outside_the_live_pool_abort_under_strict_mode(self):
        self.assertIsNone(
            self._run(["agent_elsewhere"], {"ECAN_DISPATCH_LISTENERS_STRICT": "1"})
        )

    def test_kill_switch_skips_the_lookup_entirely(self):
        def _boom(*a, **k):
            raise AssertionError("lookup must not run when disabled")

        with patch("agent.ec_tasks.runner.find_my_listeners", _boom), patch.dict(
            "os.environ", {"ECAN_DISPATCH_USE_LISTENERS": "0"}, clear=False
        ):
            self.assertEqual(
                self.fd._narrow_to_listeners(self.cfg, FD, self.live), self.live
            )

    def test_lookup_failure_falls_back_rather_than_crashing_dispatch(self):
        def _boom(*a, **k):
            raise RuntimeError("registry exploded")

        with patch("agent.ec_tasks.runner.find_my_listeners", _boom):
            self.assertEqual(
                self.fd._narrow_to_listeners(self.cfg, FD, self.live), self.live
            )


if __name__ == "__main__":
    unittest.main()
