"""Phase 2 tests: per-task variables for shared skills.

Covers docs/SHARED_SKILL_MULTI_TASK_PLAN.md Phase 2:
- ``apply_task_vars`` seeds task-carried variables into the run state
  (prompt_refs first-stop of the resolution cascade + attributes copy).
- ``_convert_dict_to_task`` carries task_vars from DB settings into runtime
  task metadata.
- CLI: ``ecan tasks add --skill --var`` and ``ecan tasks update --var``.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

# Enter the ec_tasks ↔ prep_skills_run import cycle from the package side
# (production import order); importing prep_skills_run first would hit the
# partially-initialized module via ec_tasks.resume → ec_tasks.__init__ →
# runner → prep_skills_run.
import agent.ec_tasks  # noqa: F401
from agent.ec_skills.prep_skills_run import apply_task_vars


def _task(task_vars=None, metadata=...):
    if metadata is ...:
        metadata = {"task_vars": task_vars} if task_vars is not None else {}
    return SimpleNamespace(metadata=metadata)


class TestApplyTaskVars:
    def test_seeds_prompt_refs_and_attributes(self):
        state = {}
        apply_task_vars(_task({"shop_name": "Shop A", "tone": "friendly"}), state)
        assert state["prompt_refs"] == {"shop_name": "Shop A", "tone": "friendly"}
        assert state["attributes"]["task_vars"] == {"shop_name": "Shop A", "tone": "friendly"}

    def test_overwrites_stale_prompt_refs_but_preserves_others(self):
        state = {"prompt_refs": {"shop_name": "stale", "upstream": "keep"}}
        apply_task_vars(_task({"shop_name": "Shop A"}), state)
        assert state["prompt_refs"] == {"shop_name": "Shop A", "upstream": "keep"}

    def test_noop_without_task_vars(self):
        state = {"prompt_refs": {"a": 1}}
        apply_task_vars(_task(metadata={}), state)
        apply_task_vars(_task(metadata=None), state)
        apply_task_vars(_task({}), state)
        assert state == {"prompt_refs": {"a": 1}}

    def test_tolerates_bad_inputs(self):
        apply_task_vars(_task({"a": 1}), None)  # non-dict state: no raise
        apply_task_vars(SimpleNamespace(), {})  # no metadata attr: no raise

    def test_resolution_cascade_picks_up_seeded_vars(self):
        """Seeded vars are found by the FIRST stop of the resolution chain."""
        from agent.ec_skills.prompt_variable_providers import resolve_prompt_variables

        state = {}
        apply_task_vars(_task({"shop_name": "Shop A"}), state)
        resolved = resolve_prompt_variables(["shop_name"], state, mainwin=None)
        assert resolved["shop_name"] == "Shop A"


class TestConvertDictToTaskCarriesVars:
    def test_task_vars_propagate_from_db_metadata(self):
        from agent.agent_converter import _convert_dict_to_task

        task_obj = _convert_dict_to_task({
            "id": "task_1",
            "name": "T",
            "metadata": {"task_vars": {"shop_name": "Shop A"}, "other": "ignored"},
        })
        assert task_obj.metadata == {"task_vars": {"shop_name": "Shop A"}}

    def test_no_metadata_gives_empty_runtime_metadata(self):
        from agent.agent_converter import _convert_dict_to_task

        task_obj = _convert_dict_to_task({"id": "task_1", "name": "T"})
        assert task_obj.metadata == {}


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
    fake.db.task_service.add_skill_to_task.return_value = {'success': True}
    with patch('cli.tasks.commands.get_context', return_value=fake), \
         patch('cli.base.context.get_context', return_value=fake), \
         patch('cli.tasks.commands.get_output', return_value=MagicMock()), \
         patch('cli.base.sync.cloud_sync'), \
         patch('cli.base.resolve.resolve_entity_id',
               side_effect=lambda svc, ident, kind: f"{kind}_{ident}"):
        yield fake


class TestCliTaskVars:
    def test_add_with_skill_and_vars(self, runner, cli_env):
        from cli.tasks.commands import add

        result = runner.invoke(add, [
            '-n', 'Shop A QA', '--skill', 'rt_chat_bot',
            '--var', 'shop_name=Shop A', '--var', 'tone=friendly',
        ])
        assert result.exit_code == 0
        task_data = cli_env.db.task_service.add_task.call_args[0][0]
        assert task_data['settings'] == {'task_vars': {'shop_name': 'Shop A', 'tone': 'friendly'}}
        cli_env.db.task_service.add_skill_to_task.assert_called_once_with(
            'task_1', 'skill_rt_chat_bot')

    def test_add_invalid_var_fails(self, runner, cli_env):
        from cli.tasks.commands import add

        result = runner.invoke(add, ['-n', 'T', '--var', 'no-equals-sign'])
        assert result.exit_code == 1
        cli_env.db.task_service.add_task.assert_not_called()

    def test_add_without_vars_stores_no_settings(self, runner, cli_env):
        from cli.tasks.commands import add

        result = runner.invoke(add, ['-n', 'T'])
        assert result.exit_code == 0
        assert 'settings' not in cli_env.db.task_service.add_task.call_args[0][0]

    def test_update_merges_vars_into_existing_settings(self, runner, cli_env):
        from cli.tasks.commands import update

        cli_env.db.task_service.get_task_by_id.return_value = {
            'success': True,
            'data': {'metadata': {'task_vars': {'shop_name': 'Old', 'keep': 'me'},
                                  'unrelated': 'setting'}},
        }
        result = runner.invoke(update, ['task_1', '--var', 'shop_name=Shop B'])
        assert result.exit_code == 0
        settings = cli_env.db.task_service.update_task.call_args[0][1]['settings']
        assert settings['task_vars'] == {'shop_name': 'Shop B', 'keep': 'me'}
        assert settings['unrelated'] == 'setting'

    def test_update_var_on_task_without_settings(self, runner, cli_env):
        from cli.tasks.commands import update

        result = runner.invoke(update, ['task_1', '--var', 'a=1'])
        assert result.exit_code == 0
        settings = cli_env.db.task_service.update_task.call_args[0][1]['settings']
        assert settings == {'task_vars': {'a': '1'}}
