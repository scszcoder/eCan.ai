"""Run rules and pool size on `ecan tasks add/update`, and `ecan knowledge pending`."""

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from cli.tasks.commands import add, update


@pytest.fixture
def runner():
    return CliRunner()


def _ctx(stored=None, others=None):
    fake = MagicMock()
    fake.username = 'tester'
    fake.require_auth.return_value = None
    svc = fake.db.task_service
    svc.add_task.return_value = {'success': True, 'id': 'task_1', 'data': None}
    svc.update_task.return_value = {'success': True, 'data': None}
    svc.get_task_by_id.return_value = {'success': True, 'data': stored or {}}
    others = others or {}
    svc.query_tasks.side_effect = lambda id: {'success': True, 'data': [others.get(id, {})]}
    return fake


@pytest.fixture
def env():
    holder = {}

    def make(stored=None, others=None):
        ctx = _ctx(stored, others)
        ctx.out = MagicMock()
        holder['patches'] = [
            patch('cli.tasks.commands.get_context', return_value=ctx),
            patch('cli.base.context.get_context', return_value=ctx),
            patch('cli.tasks.commands.get_output', return_value=ctx.out),
            patch('cli.base.sync.cloud_sync'),
            patch('cli.base.resolve.resolve_entity_id', side_effect=lambda svc, ident, kind: ident),
        ]
        for p in holder['patches']:
            p.start()
        return ctx
    yield make
    for p in holder.get('patches', []):
        p.stop()


def _saved(ctx):
    return ctx.db.task_service.update_task.call_args[0][1]['settings']


def test_add_one_time_background_export(runner, env):
    ctx = env()
    r = runner.invoke(add, ['-n', 'export', '--run-once', '--run-class', 'background', '--start-after-idle', '5'])
    assert r.exit_code == 0, r.output
    data = ctx.db.task_service.add_task.call_args[0][0]
    assert data['settings'] == {'run_once': True, 'run_class': 'background', 'start_after_idle_min': 5}


def test_add_after_defaults_trigger_to_after(runner, env):
    ctx = env()
    r = runner.invoke(add, ['-n', 'report', '--after', 'scrape', '--after-require-success'])
    assert r.exit_code == 0, r.output
    data = ctx.db.task_service.add_task.call_args[0][0]
    assert data['trigger'] == 'after'
    assert data['settings']['after'] == {'tasks': ['scrape'], 'require_success': True}


def test_update_fixed_pool_keeps_other_settings(runner, env):
    ctx = env(stored={'name': 'fd', 'metadata': {'task_vars': {'a': '1'}, 'pool': {'min': 2, 'max': 8, 'idle_minutes': 10}}})
    r = runner.invoke(update, ['fd', '--pool-min', '4', '--pool-max', '4'])
    assert r.exit_code == 0, r.output
    assert _saved(ctx) == {'task_vars': {'a': '1'}, 'pool': {'min': 4, 'max': 4, 'idle_minutes': 10}}


def test_update_pool_min_above_max_fails(runner, env):
    ctx = env(stored={'metadata': {'pool': {'max': 3}}})
    r = runner.invoke(update, ['fd', '--pool-min', '5'])
    assert r.exit_code == 1
    ctx.db.task_service.update_task.assert_not_called()


def test_update_no_pool_and_defaults_are_not_stored(runner, env):
    ctx = env(stored={'metadata': {'pool': {'min': 1}, 'run_class': 'background', 'overlap_policy': 'queue_one',
                                   'max_lateness_min': 10}})
    r = runner.invoke(update, ['t', '--no-pool', '--run-class', 'normal', '--overlap', 'skip', '--max-lateness', 'off'])
    assert r.exit_code == 0, r.output
    assert _saved(ctx) == {}


def test_update_reset_run_once(runner, env):
    ctx = env(stored={'metadata': {'run_once': True, 'completed_once_at': '2026-10-11T10:00:00'}})
    r = runner.invoke(update, ['t', '--reset-run-once'])
    assert r.exit_code == 0, r.output
    assert _saved(ctx) == {'run_once': True}


def test_update_after_cycle_is_rejected(runner, env):
    ctx = env(stored={'name': 'A', 'trigger': 'after', 'metadata': {}},
              others={'B': {'name': 'B', 'metadata': {'after': {'tasks': ['A']}}}})
    r = runner.invoke(update, ['A', '--after', 'B'])
    assert r.exit_code == 1
    assert ctx.out.error.call_args[0][0] == 'Task dependencies form a cycle: A -> B -> A'
    ctx.db.task_service.update_task.assert_not_called()


def test_update_after_without_cycle_is_saved(runner, env):
    ctx = env(stored={'name': 'A', 'trigger': 'after', 'metadata': {}},
              others={'B': {'name': 'B', 'metadata': {'after': {'tasks': ['C']}}}})
    assert runner.invoke(update, ['A', '--after', 'B']).exit_code == 0
    assert _saved(ctx) == {'after': {'tasks': ['B'], 'require_success': False}}
    ctx.out.warning.assert_not_called()


def test_update_after_warns_when_trigger_lacks_after(runner, env):
    ctx = env(stored={'name': 'A', 'trigger': 'message', 'metadata': {}})
    assert runner.invoke(update, ['A', '--after', 'B']).exit_code == 0
    assert 'no effect' in ctx.out.warning.call_args[0][0]


def test_update_after_self_is_rejected(runner, env):
    ctx = env(stored={'name': 'A', 'metadata': {}})
    r = runner.invoke(update, ['A', '--after', 'A'])
    assert r.exit_code == 1
    assert 'itself' in ctx.out.error.call_args[0][0]
    ctx.db.task_service.update_task.assert_not_called()


def test_update_exclusive_add_and_clear(runner, env):
    ctx = env(stored={'metadata': {'exclusive_resources': ['printer']}})
    assert runner.invoke(update, ['t', '--exclusive', 'scanner', '--exclusive', 'printer']).exit_code == 0
    assert _saved(ctx) == {'exclusive_resources': ['printer', 'scanner']}
    ctx2 = env(stored={'metadata': {'exclusive_resources': ['printer']}})
    assert runner.invoke(update, ['t', '--no-exclusive']).exit_code == 0
    assert _saved(ctx2) == {}


def test_update_bad_lateness_fails(runner, env):
    ctx = env(stored={'metadata': {}})
    assert runner.invoke(update, ['t', '--max-lateness', 'soon']).exit_code == 1
    ctx.db.task_service.update_task.assert_not_called()


def test_knowledge_pending_list_and_dismiss(runner, tmp_path):
    from cli.knowledge.commands import pending
    from knowledge.ks.pending_imports import PendingImports
    folder = tmp_path / 'knowledge_service'
    src = tmp_path / 'goods.csv'
    src.write_text('商品名称,价格\n杯子,9.9\n', encoding='utf-8')
    entry = PendingImports(str(folder)).stage(str(src), source='抖店商品导出')
    ctx = MagicMock(username='tester')
    ctx.require_auth.return_value = None
    out = MagicMock()
    with patch('cli.knowledge.commands.get_context', return_value=ctx), \
         patch('cli.base.context.get_context', return_value=ctx), \
         patch('cli.knowledge.commands.get_output', return_value=out), \
         patch('utils.user_path_helper.get_user_data_dir', return_value=str(tmp_path)):
        assert runner.invoke(pending, ['list', '-f', 'json']).exit_code == 0
        listed = out.json.call_args[0][0]
        assert listed['count'] == 1 and listed['items'][0]['id'] == entry['id']
        assert runner.invoke(pending, ['dismiss', entry['id']]).exit_code == 0
        assert runner.invoke(pending, ['dismiss', entry['id']]).exit_code == 1
    assert PendingImports(str(folder)).list() == []
