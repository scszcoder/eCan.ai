"""Phase 3 tests: per-task browser identity for shared skills.

Covers docs/SHARED_SKILL_MULTI_TASK_PLAN.md Phase 3:
- ``resolve_state_browser_identity`` reads per-run overrides from state
  (root → attributes → params) incl. headless coercion.
- ``apply_task_vars`` seeds a task's ``browser_identity`` into the state
  keys the browser-node runtime honors.
- Pinned ``node:*`` browser scopes carry an agent suffix so agents sharing
  one skill get separate cached sessions (B6); chat scopes are unchanged.
- CLI ``--browser k=v`` parsing, canonicalization, and update-merge.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

import agent.ec_tasks  # noqa: F401  — enter the ec_tasks cycle from the package side
from agent.ec_skills.prep_skills_run import apply_task_vars
from agent.ec_skills.browser_node.build_helpers import (
    resolve_browser_scope_key,
    resolve_state_browser_identity,
)


@pytest.fixture(autouse=True)
def _clean_mt068_cache():
    from agent.ec_skills import build_node

    build_node._last_known_agent_id_by_node.clear()
    build_node._known_agent_ids_by_node.clear()
    yield
    build_node._last_known_agent_id_by_node.clear()
    build_node._known_agent_ids_by_node.clear()


class TestResolveStateBrowserIdentity:
    def test_reads_root_then_attributes_then_params(self):
        state = {
            "cdp_port": "9333",
            "attributes": {
                "browser_profile": "shop-a",
                "params": {"user_data_dir": "C:/profiles/a", "headless": "true"},
            },
        }
        ident = resolve_state_browser_identity(state)
        assert ident == {
            "cdp_port": "9333",
            "browser_profile": "shop-a",
            "user_data_dir": "C:/profiles/a",
            "headless": True,
        }

    def test_root_wins_over_attributes(self):
        state = {"browser_profile": "root", "attributes": {"browser_profile": "attrs"}}
        assert resolve_state_browser_identity(state)["browser_profile"] == "root"

    def test_headless_coercion_and_invalid_values(self):
        assert resolve_state_browser_identity({"headless": "0"})["headless"] is False
        assert resolve_state_browser_identity({"headless": True})["headless"] is True
        assert "headless" not in resolve_state_browser_identity({"headless": "maybe"})

    def test_empty_state_gives_empty_dict(self):
        assert resolve_state_browser_identity({}) == {}
        assert resolve_state_browser_identity(None) == {}


class TestApplyTaskVarsBrowserIdentity:
    def test_seeds_identity_into_attributes(self):
        task = SimpleNamespace(metadata={"browser_identity": {
            "profile": "shop-a", "cdp_port": "9333", "headless": "1",
        }})
        state = {}
        apply_task_vars(task, state)
        attrs = state["attributes"]
        assert attrs["browser_profile"] == "shop-a"
        assert attrs["cdp_port"] == "9333"
        assert attrs["headless"] == "1"
        # End-to-end: the runtime resolver sees the seeded identity
        assert resolve_state_browser_identity(state)["browser_profile"] == "shop-a"

    def test_identity_and_vars_coexist(self):
        task = SimpleNamespace(metadata={
            "task_vars": {"shop_name": "Shop A"},
            "browser_identity": {"user_data_dir": "C:/profiles/a"},
        })
        state = {}
        apply_task_vars(task, state)
        assert state["prompt_refs"]["shop_name"] == "Shop A"
        assert state["attributes"]["user_data_dir"] == "C:/profiles/a"

    def test_empty_values_not_seeded(self):
        task = SimpleNamespace(metadata={"browser_identity": {"profile": "", "cdp_port": None}})
        state = {}
        apply_task_vars(task, state)
        assert "browser_profile" not in state.get("attributes", {})
        assert "cdp_port" not in state.get("attributes", {})


class TestPinnedScopeAgentSuffix:
    def test_pinned_scope_includes_agent(self):
        state = {"attributes": {"agent_id": "agent-A", "thread_id": "t1"}}
        key = resolve_browser_scope_key(state, node_name="fd_node", pin_to_node=True)
        assert key == "node:fd_node:agent-A"

    def test_two_agents_get_distinct_pinned_scopes(self):
        key_a = resolve_browser_scope_key(
            {"attributes": {"agent_id": "agent-A", "thread_id": "t1"}},
            node_name="fd_node", pin_to_node=True)
        key_b = resolve_browser_scope_key(
            {"attributes": {"agent_id": "agent-B", "thread_id": "t2"}},
            node_name="fd_node", pin_to_node=True)
        assert key_a != key_b

    def test_degraded_state_keeps_suffix_stable_single_agent(self):
        """mt068 recovery keeps the pin suffix stable when a re-entry state
        lost agent_id (single-agent world)."""
        healthy = {"attributes": {"agent_id": "agent-A", "thread_id": "t1"}}
        key1 = resolve_browser_scope_key(healthy, node_name="fd_node", pin_to_node=True)
        degraded = {"attributes": {}}
        key2 = resolve_browser_scope_key(degraded, node_name="fd_node", pin_to_node=True)
        assert key1 == key2 == "node:fd_node:agent-A"

    def test_no_agent_falls_back_to_bare_scope(self):
        key = resolve_browser_scope_key({}, node_name="fd_node", pin_to_node=True)
        assert key == "node:fd_node"

    def test_chat_scope_unchanged(self):
        state = {"attributes": {"chat_id": "cust-1", "agent_id": "agent-A"}}
        key = resolve_browser_scope_key(state, node_name="fd_node", skill_name="qa_skill")
        assert key == "chat:cust-1:qa_skill"


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def cli_env():
    fake = MagicMock()
    fake.username = 'tester'
    fake.require_auth.return_value = None
    fake.db.task_service.add_task.return_value = {'success': True, 'id': 'task_1', 'data': None}
    fake.db.task_service.update_task.return_value = {'success': True, 'data': None}
    fake.db.task_service.get_task_by_id.return_value = {'success': True, 'data': {}}
    with patch('cli.tasks.commands.get_context', return_value=fake), \
         patch('cli.base.context.get_context', return_value=fake), \
         patch('cli.tasks.commands.get_output', return_value=MagicMock()), \
         patch('cli.base.sync.cloud_sync'), \
         patch('cli.base.resolve.resolve_entity_id', side_effect=lambda svc, ident, kind: ident):
        yield fake


class TestCliBrowserIdentity:
    def test_add_with_browser_identity_canonicalizes_keys(self, runner, cli_env):
        from cli.tasks.commands import add

        result = runner.invoke(add, [
            '-n', 'Shop A QA',
            '--browser', 'profile=shop-a', '--browser', 'cdp_port=9333',
            '--browser', 'slot=s1',
        ])
        assert result.exit_code == 0
        settings = cli_env.db.task_service.add_task.call_args[0][0]['settings']
        assert settings['browser_identity'] == {
            'browser_profile': 'shop-a', 'cdp_port': '9333', 'browser_slot_id': 's1',
        }

    def test_add_invalid_browser_key_fails(self, runner, cli_env):
        from cli.tasks.commands import add

        result = runner.invoke(add, ['-n', 'T', '--browser', 'proxy=1.2.3.4'])
        assert result.exit_code == 1
        cli_env.db.task_service.add_task.assert_not_called()

    def test_update_merges_identity_preserving_existing(self, runner, cli_env):
        from cli.tasks.commands import update

        cli_env.db.task_service.get_task_by_id.return_value = {
            'success': True,
            'data': {'metadata': {
                'browser_identity': {'browser_profile': 'old', 'user_data_dir': 'keep'},
                'task_vars': {'shop_name': 'A'},
            }},
        }
        result = runner.invoke(update, ['task_1', '--browser', 'profile=new'])
        assert result.exit_code == 0
        settings = cli_env.db.task_service.update_task.call_args[0][1]['settings']
        assert settings['browser_identity'] == {'browser_profile': 'new', 'user_data_dir': 'keep'}
        assert settings['task_vars'] == {'shop_name': 'A'}


class TestConvertDictToTaskCarriesIdentity:
    def test_browser_identity_propagates(self):
        from agent.agent_converter import _convert_dict_to_task

        task_obj = _convert_dict_to_task({
            "id": "task_1",
            "name": "T",
            "metadata": {"browser_identity": {"browser_profile": "shop-a"},
                         "task_vars": {"x": "1"}},
        })
        assert task_obj.metadata == {
            "browser_identity": {"browser_profile": "shop-a"},
            "task_vars": {"x": "1"},
        }
