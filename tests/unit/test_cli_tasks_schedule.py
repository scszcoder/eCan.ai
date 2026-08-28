"""Tests for schedule/trigger options on `ecan tasks add` and `ecan tasks update`."""

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from cli.tasks.commands import add, update


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def ctx():
    """Fake CLI context with a mocked task service."""
    fake = MagicMock()
    fake.username = 'tester'
    fake.require_auth.return_value = None
    fake.db.task_service.add_task.return_value = {'success': True, 'id': 'task_1', 'data': None}
    fake.db.task_service.update_task.return_value = {'success': True, 'data': None}
    fake.db.task_service.get_task_by_id.return_value = {'success': True, 'data': {}}
    return fake


@pytest.fixture
def cli_env(ctx):
    with patch('cli.tasks.commands.get_context', return_value=ctx), \
         patch('cli.base.context.get_context', return_value=ctx), \
         patch('cli.tasks.commands.get_output', return_value=MagicMock()), \
         patch('cli.base.sync.cloud_sync'), \
         patch('cli.base.resolve.resolve_entity_id', side_effect=lambda svc, ident, kind: ident):
        yield ctx


class TestAdd:
    def test_add_with_schedule_and_trigger(self, runner, cli_env):
        result = runner.invoke(add, [
            '-n', 'Daily Report', '--trigger', 'schedule',
            '--repeat-type', 'days', '--repeat-number', '2',
            '--start', '2026-08-24 09:00:00', '--timeout', '300',
        ])
        assert result.exit_code == 0
        task_data = cli_env.db.task_service.add_task.call_args[0][0]
        assert task_data['trigger'] == 'schedule'
        assert task_data['schedule'] == {
            'repeat_type': 'days',
            'repeat_unit': 'days',
            'repeat_number': 2,
            'time_out': 300,
            'start_date_time': '2026-08-24 09:00:00',
        }

    def test_add_schedule_defaults(self, runner, cli_env):
        result = runner.invoke(add, ['-n', 'T', '--repeat-type', 'weeks'])
        assert result.exit_code == 0
        schedule = cli_env.db.task_service.add_task.call_args[0][0]['schedule']
        assert schedule['repeat_number'] == 1
        assert schedule['time_out'] == 120

    def test_add_without_schedule_options_stores_no_schedule(self, runner, cli_env):
        result = runner.invoke(add, ['-n', 'T'])
        assert result.exit_code == 0
        task_data = cli_env.db.task_service.add_task.call_args[0][0]
        assert 'schedule' not in task_data
        assert 'trigger' not in task_data

    def test_add_schedule_option_without_repeat_type_fails(self, runner, cli_env):
        result = runner.invoke(add, ['-n', 'T', '--start', '2026-08-24 09:00:00'])
        assert result.exit_code == 1
        cli_env.db.task_service.add_task.assert_not_called()

    def test_add_invalid_trigger_fails(self, runner, cli_env):
        result = runner.invoke(add, ['-n', 'T', '--trigger', 'bogus'])
        assert result.exit_code == 1
        cli_env.db.task_service.add_task.assert_not_called()

    def test_add_invalid_datetime_fails(self, runner, cli_env):
        result = runner.invoke(add, ['-n', 'T', '--repeat-type', 'days', '--start', 'tomorrow'])
        assert result.exit_code == 1
        cli_env.db.task_service.add_task.assert_not_called()


class TestUpdate:
    def test_update_trigger(self, runner, cli_env):
        result = runner.invoke(update, ['task_1', '--trigger', 'schedule,message'])
        assert result.exit_code == 0
        fields = cli_env.db.task_service.update_task.call_args[0][1]
        assert fields['trigger'] == 'schedule,message'

    def test_update_merges_into_existing_schedule(self, runner, cli_env):
        cli_env.db.task_service.get_task_by_id.return_value = {
            'success': True,
            'data': {'schedule': {
                'repeat_type': 'days', 'repeat_unit': 'days',
                'repeat_number': 5, 'time_out': 300,
                'start_date_time': '2026-01-01 00:00:00',
            }},
        }
        result = runner.invoke(update, ['task_1', '--repeat-number', '2'])
        assert result.exit_code == 0
        schedule = cli_env.db.task_service.update_task.call_args[0][1]['schedule']
        assert schedule['repeat_number'] == 2
        # untouched fields survive the partial update
        assert schedule['time_out'] == 300
        assert schedule['start_date_time'] == '2026-01-01 00:00:00'
        assert schedule['repeat_type'] == 'days'

    def test_update_schedule_without_existing_requires_repeat_type(self, runner, cli_env):
        result = runner.invoke(update, ['task_1', '--repeat-number', '2'])
        assert result.exit_code == 1
        cli_env.db.task_service.update_task.assert_not_called()

    def test_update_full_schedule_on_task_without_one(self, runner, cli_env):
        result = runner.invoke(update, ['task_1', '--repeat-type', 'hours', '--repeat-number', '6'])
        assert result.exit_code == 0
        schedule = cli_env.db.task_service.update_task.call_args[0][1]['schedule']
        assert schedule == {
            'repeat_type': 'hours', 'repeat_unit': 'hours', 'repeat_number': 6,
        }

    def test_update_invalid_trigger_fails(self, runner, cli_env):
        result = runner.invoke(update, ['task_1', '--trigger', 'cron'])
        assert result.exit_code == 1
        cli_env.db.task_service.update_task.assert_not_called()
