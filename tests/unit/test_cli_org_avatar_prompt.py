"""CRUD wiring for the new/updated CLI groups: `ecan org`, `ecan avatar`,
and `ecan prompts update`."""

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from cli.organizations.commands import add as org_add, update as org_update, remove as org_remove, list_orgs
from cli.avatars.commands import add as avatar_add, remove as avatar_remove, list_avatars


@pytest.fixture
def runner():
    return CliRunner()


# ── org ──────────────────────────────────────────────────────────────────────

@pytest.fixture
def org_ctx():
    fake = MagicMock()
    fake.username = 'tester'
    fake.db.org_service.add_org.return_value = {'success': True, 'id': 'org_1', 'data': None}
    fake.db.org_service.update_org.return_value = {'success': True, 'data': None}
    fake.db.org_service.delete_org.return_value = {'success': True}
    # id-aware: only a real id resolves; a name falls through to search_orgs.
    fake.db.org_service.get_org_by_id.side_effect = lambda oid: (
        {'success': True, 'data': {'id': 'org_1', 'name': 'Sales'}}
        if oid == 'org_1' else {'success': False, 'data': None}
    )
    fake.db.org_service.search_orgs.return_value = {'success': True, 'data': [{'id': 'org_1', 'name': 'Sales'}]}
    fake.db.org_service.get_all_orgs.return_value = {'success': True, 'data': [{'id': 'org_1', 'name': 'Sales'}]}
    return fake


@pytest.fixture
def org_env(org_ctx):
    org_ctx.require_auth.return_value = None
    with patch('cli.organizations.commands.get_context', return_value=org_ctx), \
         patch('cli.base.context.get_context', return_value=org_ctx), \
         patch('cli.organizations.commands.get_output', return_value=MagicMock()), \
         patch('cli.base.sync.cloud_sync') as sync:
        yield org_ctx, sync


def test_org_add_creates_and_syncs(runner, org_env):
    ctx, sync = org_env
    res = runner.invoke(org_add, ['-n', 'Marketing', '-d', 'MK team'])
    assert res.exit_code == 0, res.output
    data = ctx.db.org_service.add_org.call_args[0][0]
    assert data['name'] == 'Marketing' and data['owner'] == 'tester'
    assert sync.called and sync.call_args[0][2].value == 'add'


def test_org_add_resolves_parent(runner, org_env):
    ctx, _ = org_env
    res = runner.invoke(org_add, ['-n', 'Sub', '-p', 'Sales'])
    assert res.exit_code == 0, res.output
    assert ctx.db.org_service.add_org.call_args[0][0]['parent_id'] == 'org_1'


def test_org_update_sends_only_changed_fields(runner, org_env):
    ctx, sync = org_env
    res = runner.invoke(org_update, ['org_1', '--status', 'inactive'])
    assert res.exit_code == 0, res.output
    oid, fields = ctx.db.org_service.update_org.call_args[0]
    assert oid == 'org_1' and fields == {'status': 'inactive'}
    assert sync.call_args[0][2].value == 'update'


def test_org_remove_deletes_and_syncs(runner, org_env):
    ctx, sync = org_env
    res = runner.invoke(org_remove, ['org_1', '-f'])
    assert res.exit_code == 0, res.output
    assert ctx.db.org_service.delete_org.call_args[0][0] == 'org_1'
    assert sync.call_args[0][2].value == 'delete'


def test_org_list_json(runner, org_env):
    res = runner.invoke(list_orgs, ['--format', 'json'])
    assert res.exit_code == 0, res.output


# ── avatar ───────────────────────────────────────────────────────────────────

@pytest.fixture
def avatar_env():
    mgr = MagicMock()

    async def _upload(data, name):
        return {'success': True, 'id': 'avatar_abc'}

    async def _delete(aid):
        return {'success': True}

    mgr.upload_avatar.side_effect = _upload
    mgr.upload_avatar_video.side_effect = _upload
    mgr.delete_uploaded_avatar.side_effect = _delete
    mgr.get_system_avatars.return_value = [{'id': 'A001', 'name': 'sys'}]
    mgr.get_uploaded_avatars.return_value = [{'id': 'avatar_abc', 'name': 'mine'}]

    fake = MagicMock()
    fake.username = 'tester'
    fake.require_auth.return_value = None
    with patch('cli.avatars.commands.get_context', return_value=fake), \
         patch('cli.base.context.get_context', return_value=fake), \
         patch('cli.avatars.commands.get_output', return_value=MagicMock()), \
         patch('cli.avatars.commands._manager', return_value=mgr):
        yield mgr


def test_avatar_add_uploads_image(runner, avatar_env, tmp_path):
    img = tmp_path / 'face.png'
    img.write_bytes(b'\x89PNG\r\n')
    res = runner.invoke(avatar_add, [str(img)])
    assert res.exit_code == 0, res.output
    assert avatar_env.upload_avatar.called
    assert not avatar_env.upload_avatar_video.called


def test_avatar_add_routes_video(runner, avatar_env, tmp_path):
    vid = tmp_path / 'clip.mp4'
    vid.write_bytes(b'\x00\x00')
    res = runner.invoke(avatar_add, [str(vid)])
    assert res.exit_code == 0, res.output
    assert avatar_env.upload_avatar_video.called


def test_avatar_remove_rejects_system_id(runner, avatar_env):
    res = runner.invoke(avatar_remove, ['A001', '-f'])
    assert res.exit_code != 0
    assert not avatar_env.delete_uploaded_avatar.called


def test_avatar_remove_deletes_uploaded(runner, avatar_env):
    res = runner.invoke(avatar_remove, ['avatar_abc', '-f'])
    assert res.exit_code == 0, res.output
    assert avatar_env.delete_uploaded_avatar.called


def test_avatar_list_runs(runner, avatar_env):
    res = runner.invoke(list_avatars, ['--format', 'json'])
    assert res.exit_code == 0, res.output


# ── prompts update ───────────────────────────────────────────────────────────

def test_prompts_update_keeps_id_and_syncs(runner):
    from cli.prompts.commands import update as prompt_update
    doc = {'id': 'pr-abc', 'title': 'greeting', 'topic': 'greeting',
           'mdContent': 'old', '__path': '/tmp/pr-abc.json'}
    _auth = MagicMock(); _auth.require_auth.return_value = None
    with patch('cli.base.context.get_context', return_value=_auth), \
         patch('cli.prompts.commands.get_output', return_value=MagicMock()), \
         patch('cli.prompts.commands._find_by_title', return_value=dict(doc)), \
         patch('cli.prompts.commands._load_prompt_docs', return_value=[dict(doc)]), \
         patch('cli.prompts.commands._write_doc') as write_doc, \
         patch('cli.prompts.commands._prompt_cloud_sync') as sync:
        res = runner.invoke(prompt_update, ['greeting', '-c', 'new text'])
    assert res.exit_code == 0, res.output
    written = write_doc.call_args[0][0]
    assert written['id'] == 'pr-abc' and written['mdContent'] == 'new text'
    assert sync.call_args[0][1] == 'UPDATE'


def test_prompts_update_nothing_to_do(runner):
    from cli.prompts.commands import update as prompt_update
    doc = {'id': 'pr-abc', 'title': 'greeting', '__path': '/tmp/x.json'}
    _auth = MagicMock(); _auth.require_auth.return_value = None
    with patch('cli.base.context.get_context', return_value=_auth), \
         patch('cli.prompts.commands.get_output', return_value=MagicMock()), \
         patch('cli.prompts.commands._find_by_title', return_value=dict(doc)), \
         patch('cli.prompts.commands._write_doc') as write_doc:
        res = runner.invoke(prompt_update, ['greeting'])
    assert res.exit_code == 0
    assert not write_doc.called
