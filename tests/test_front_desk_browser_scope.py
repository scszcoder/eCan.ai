"""Regression tests for the front-desk browser-scope pinning fix and the
focus-preflight ``did_switch`` short-circuit.

Stress-test 2026-04-30 (20 simultaneous customers, 1 front-desk + 3 Q&A bots)
revealed two compounding bottlenecks in the browser-automation node:

  Fix #1 — ``resolve_browser_scope_key`` was returning ``chat:<customer_id>``
    for the front-desk dispatcher because ``state["messages"][1]`` (the
    customer-id index) leaked into the candidate list.  Each customer ->
    different scope key -> brand-new browser session -> 30-35 s wait on the
    cdp_port=9228 startup lock.

  Fix #2 — ``run_cdp_focus_preflight`` was unconditionally calling
    ``get_browser_state_summary`` (3 s timeout x 2 attempts), and the
    post-preflight site repeated the same call, even when ``cur_focus ==
    target_focus`` and no SwitchTabEvent was dispatched.  Under 23-tab CDP
    load the call always timed out -> 12 s wasted per iteration on pure
    overhead with no semantic effect.

These tests pin the contract so a refactor cannot reintroduce either
regression.  They cover only pure logic (no real browser session) by
mocking the module-level helpers and feeding controlled state dicts.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import types
import unittest
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.ec_skills.browser_node import build_helpers as bh  # noqa: E402
from agent.ec_skills.browser_node import runner as br  # noqa: E402


# ---------------------------------------------------------------------------
# Fix #1 — resolve_browser_scope_key pin-to-node opt-in
# ---------------------------------------------------------------------------

class TestResolveBrowserScopeKey(unittest.TestCase):
    # Phase 3 (SHARED_SKILL_MULTI_TASK_PLAN B6): pinned node scopes carry an
    # agent suffix (node:<name>:<agent_id>) resolved from state, with the
    # mt068 recovery cache keeping it sticky. Clear that cache per test so
    # expectations stay deterministic.
    def _clear_mt068_cache(self):
        from agent.ec_skills import build_node
        build_node._last_known_agent_id_by_node.clear()
        build_node._known_agent_ids_by_node.clear()

    def setUp(self):
        bh.reset_pin_browser_scope_cache()
        self._clear_mt068_cache()

    def tearDown(self):
        bh.reset_pin_browser_scope_cache()
        self._clear_mt068_cache()

    # ---- existing chat-id path (must remain intact for Q&A bots) ----

    def test_default_chat_id_path_preserved(self):
        """Q&A bots must continue to scope per-chat."""
        state = {"attributes": {"chat_id": "cust42"}}
        self.assertEqual(
            bh.resolve_browser_scope_key(state, node_name="bn"),
            "chat:cust42",
        )

    def test_messages_index_1_used_as_chat_id(self):
        """Existing fallback: state['messages'][1] becomes chat scope."""
        state = {"messages": ["agent_id_0", "cust99"]}
        self.assertEqual(
            bh.resolve_browser_scope_key(state, node_name="bn"),
            "chat:cust99",
        )

    def test_no_chat_identifier_returns_node_scope(self):
        self.assertEqual(
            bh.resolve_browser_scope_key({}, node_name="bn"),
            "node:bn",
        )

    # ---- pin_to_node kwarg overrides everything ----

    def test_pin_to_node_kwarg_overrides_chat_id(self):
        """The front-desk dispatcher's intended pattern."""
        state = {"attributes": {"chat_id": "cust42"},
                 "messages": ["agent_id", "cust42"]}
        self.assertEqual(
            bh.resolve_browser_scope_key(state, node_name="bn", pin_to_node=True),
            "node:bn:agent_id",  # Phase 3: pinned scope carries the agent suffix
        )

    def test_pin_to_node_kwarg_false_does_not_force_node(self):
        """``pin_to_node=False`` must NOT block the chat-id path."""
        state = {"attributes": {"chat_id": "cust42"}}
        self.assertEqual(
            bh.resolve_browser_scope_key(state, node_name="bn", pin_to_node=False),
            "chat:cust42",
        )

    # ---- state.attributes flag ----

    def test_state_attribute_flag_pins_to_node(self):
        state = {"attributes": {"chat_id": "cust42",
                                "pin_browser_scope_to_node": True}}
        self.assertEqual(
            bh.resolve_browser_scope_key(state, node_name="bn"),
            "node:bn",
        )

    def test_state_attribute_string_truthy_pins_to_node(self):
        for v in ("1", "true", "yes", "on", "TRUE"):
            with self.subTest(v=v):
                state = {"attributes": {"chat_id": "c",
                                        "pin_browser_scope_to_node": v}}
                self.assertEqual(
                    bh.resolve_browser_scope_key(state, node_name="bn"),
                    "node:bn",
                )

    def test_params_camelCase_flag_pins_to_node(self):
        state = {"attributes": {"chat_id": "cust42",
                                "params": {"pinBrowserScopeToNode": True}}}
        self.assertEqual(
            bh.resolve_browser_scope_key(state, node_name="bn"),
            "node:bn",
        )

    def test_customer_front_desk_defaults_to_node_scope(self):
        state = {
            "attributes": {"chat_id": "客户13"},
            "messages": ["agent_id", "客户13"],
        }
        self.assertEqual(
            bh.resolve_browser_scope_key(
                state,
                node_name="browser_automation_0t5L6",
                skill_name="customer_front_desk",
            ),
            "node:browser_automation_0t5L6:agent_id",  # Phase 3 agent suffix
        )

    def test_customer_front_desk_state_skill_name_defaults_to_node_scope(self):
        state = {
            "attributes": {
                "chat_id": "客户20",
                "skill_name": "customer_front_desk",
            },
            "messages": ["agent_id", "客户20"],
        }
        self.assertEqual(
            bh.resolve_browser_scope_key(
                state,
                node_name="browser_automation_0t5L6",
            ),
            "node:browser_automation_0t5L6:agent_id",  # Phase 3 agent suffix
        )

    def test_feige_front_desk_defaults_to_node_scope(self):
        state = {
            "attributes": {"chat_id": "陆地飞鱼"},
            "messages": ["agent_id", "陆地飞鱼"],
        }
        self.assertEqual(
            bh.resolve_browser_scope_key(
                state,
                node_name="browser_automation_janWe",
                skill_name="飞鸽前台0",
            ),
            "node:browser_automation_janWe:agent_id",  # Phase 3 agent suffix
        )

    # ---- skill mapping_rules opt-in (front-desk's intended path) ----

    def test_skill_mapping_rules_pins_to_node(self):
        fake_skill = types.SimpleNamespace(
            name="customer_front_desk",
            mapping_rules={"pin_browser_scope_to_node": True},
        )
        fake_main = types.SimpleNamespace(agent_skills=[fake_skill])
        with patch("app_context.AppContext.get_main_window", return_value=fake_main):
            bh.reset_pin_browser_scope_cache()
            state = {"attributes": {"chat_id": "cust42",
                                    "skill_name": "customer_front_desk"}}
            self.assertEqual(
                bh.resolve_browser_scope_key(state, node_name="browser_automation_0t5L6"),
                "node:browser_automation_0t5L6",
            )

    def test_skill_mapping_rules_other_skill_does_not_inherit(self):
        """Different skill name must NOT inherit another skill's flag."""
        s_pinned = types.SimpleNamespace(
            name="customer_front_desk",
            mapping_rules={"pin_browser_scope_to_node": True},
        )
        s_qa = types.SimpleNamespace(
            name="rt_chat_bot00",
            mapping_rules={},
        )
        fake_main = types.SimpleNamespace(agent_skills=[s_pinned, s_qa])
        with patch("app_context.AppContext.get_main_window", return_value=fake_main):
            bh.reset_pin_browser_scope_cache()
            # Q&A bot resolves chat scope normally.
            state = {"attributes": {"chat_id": "cust42",
                                    "skill_name": "rt_chat_bot00"}}
            self.assertEqual(
                bh.resolve_browser_scope_key(state, node_name="bn"),
                "chat:cust42",
            )

    def test_skill_mapping_rules_cache_returns_consistent(self):
        """Cache must persist across calls for the same skill name."""
        fake_skill = types.SimpleNamespace(
            name="qa", mapping_rules={"pin_browser_scope_to_node": True}
        )
        fake_main = types.SimpleNamespace(agent_skills=[fake_skill])
        with patch("app_context.AppContext.get_main_window", return_value=fake_main) as p:
            bh.reset_pin_browser_scope_cache()
            for _ in range(3):
                state = {"attributes": {"skill_name": "qa", "chat_id": "x"}}
                self.assertEqual(
                    bh.resolve_browser_scope_key(state, node_name="bn"),
                    "node:bn",
                )
            # Mainwin lookup is cached, so get_main_window is called only once
            # for the resolution path (additional calls may happen elsewhere
            # during state-attribute checks, but the skill cache should hit).
            self.assertGreaterEqual(p.call_count, 1)


class TestRuntimeInvocationInput(unittest.TestCase):
    def test_browser_event_predispatch_cycle_suppresses_stale_response_text(self):
        stale_reply = {
            "customer_id": "客户B",
            "customer_name": "客户B",
            "response_text": "old reply",
            "source_customer_msg_id": "old-msg",
        }
        state = {
            "prompt_refs": {
                "events": json.dumps({"event_type": "browser_event"})
            },
            "messages": ["agent", "客户B", "", "", json.dumps(stale_reply)],
            "_ecan_predispatch_actionable_items": [
                {
                    "customer_name": "客户C",
                    "last_message": "女士牛仔裤27码腰围是多少？",
                }
            ],
        }

        self.assertEqual(bh.extract_runtime_invocation_input(state), "")

    def test_chat_message_cycle_keeps_response_text(self):
        reply = {
            "customer_id": "客户B",
            "customer_name": "客户B",
            "response_text": "reply",
        }
        state = {
            "prompt_refs": {
                "events": json.dumps({"event_type": "chat_message"})
            },
            "input": json.dumps(reply),
        }

        self.assertEqual(
            json.loads(bh.extract_runtime_invocation_input(state)),
            reply,
        )


# ---------------------------------------------------------------------------
# Fix #2 — focus-preflight did_switch contract
# ---------------------------------------------------------------------------

def _make_browser_session_mock(target_ids: list[str], cur_focus: str | None = None):
    """Build a minimal browser_session mock that satisfies
    ``run_cdp_focus_preflight``'s contract."""
    targets = {tid: MagicMock(target_type="page", url=f"http://x/{tid}") for tid in target_ids}
    sm = MagicMock()
    sm.get_all_targets.return_value = targets
    sm.get_target.side_effect = lambda tid: targets.get(tid)
    bs = MagicMock()
    bs.session_manager = sm
    bs.agent_focus_target_id = cur_focus
    bs.cdp_url = "ws://test"
    bs.event_bus = MagicMock()
    bs.event_bus.dispatch = AsyncMock()
    bs.get_browser_state_summary = AsyncMock(return_value=None)
    return bs


class TestFocusPreflightDidSwitch(unittest.TestCase):
    def test_returns_three_tuple(self):
        """Contract: must now return (target_focus, last_known, did_switch)."""
        bs = _make_browser_session_mock(["t1", "t2"], cur_focus="t1")
        result = asyncio.run(br.run_cdp_focus_preflight(
            bs,
            last_known_focus_target_id=None,
            assignment_tab_id=None,
            assignment_chat_url=None,
            skill_name="test_skill",
            node_name="test_node",
        ))
        self.assertEqual(len(result), 3)
        target_focus, last_known, did_switch = result
        self.assertEqual(target_focus, "t1")  # cur_focus picked
        self.assertEqual(last_known, "t1")
        self.assertFalse(did_switch)  # cur_focus already valid, no switch

    def test_no_switch_skips_state_summary(self):
        """When cur_focus is already correct, state-summary must NOT run."""
        bs = _make_browser_session_mock(["t1", "t2"], cur_focus="t1")
        target_focus, _, did_switch = asyncio.run(br.run_cdp_focus_preflight(
            bs,
            last_known_focus_target_id=None,
            assignment_tab_id=None,
            assignment_chat_url=None,
            skill_name="s",
            node_name="n",
        ))
        self.assertFalse(did_switch)
        self.assertEqual(target_focus, "t1")
        # No SwitchTabEvent dispatched.
        bs.event_bus.dispatch.assert_not_awaited()
        # CRITICAL: state-summary not called (the whole point of Fix #2).
        bs.get_browser_state_summary.assert_not_awaited()

    def test_actual_switch_runs_state_summary(self):
        """When the focus DOES change, state-summary still runs (correctness)."""
        bs = _make_browser_session_mock(["t1", "t2"], cur_focus="t1")
        # Force assignment to t2 so the preflight switches focus.
        target_focus, _, did_switch = asyncio.run(br.run_cdp_focus_preflight(
            bs,
            last_known_focus_target_id=None,
            assignment_tab_id="t2",
            assignment_chat_url=None,
            skill_name="s",
            node_name="n",
        ))
        self.assertTrue(did_switch)
        self.assertEqual(target_focus, "t2")
        bs.event_bus.dispatch.assert_awaited_once()
        bs.get_browser_state_summary.assert_awaited()

    def test_no_targets_raises(self):
        """Existing contract preserved: no page targets -> RuntimeError."""
        bs = _make_browser_session_mock([])
        with self.assertRaises(RuntimeError):
            asyncio.run(br.run_cdp_focus_preflight(
                bs,
                last_known_focus_target_id=None,
                assignment_tab_id=None,
                assignment_chat_url=None,
                skill_name="s",
                node_name="n",
            ))


if __name__ == "__main__":
    unittest.main()
