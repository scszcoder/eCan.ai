"""The editor's save reports whether the cloud took the skill.

2026-10-18: every save of 飞鸽客服问答00 was refused by the cloud (record
update "Not found", file upload "Skill archive upload is not permitted"), the
refusal went to the offline retry queue as "cached", and the editor still said
saved -- subscribers kept the old version and nobody knew."""
import threading

from gui.ipc.w2p_handlers import skill_file_sync as sfs
from gui.ipc.w2p_handlers import skill_handler as sh


def test_cloud_refusal_queued_as_cached_is_a_failure():
    ok, err = sh._cloud_sync_outcome({
        'success': True, 'synced': False, 'cached': True, 'task_id': 't1',
        'message': 'Cached for later sync', 'errors': [{'message': 'Not found'}]})
    assert not ok and 'Not found' in err


def test_item_level_rejection_is_a_failure_even_when_synced():
    ok, err = sh._cloud_sync_outcome({'synced': True, 'response': [
        {'id': 'skill_d0983891338f4f79', 'success': False, 'error': 'Not found'}]})
    assert not ok and err == 'Not found'


def test_accepted_save_is_ok():
    assert sh._cloud_sync_outcome({'synced': True, 'response': [{'id': 's', 'success': True}]}) == (True, '')


def test_offline_is_reported_as_retry_not_success():
    ok, err = sh._cloud_sync_outcome({'synced': False, 'cached': True, 'error': 'Connection refused'})
    assert not ok and 'Connection refused' in err


def test_wait_collects_both_parts_and_times_out_on_a_silent_one():
    w = sh._CloudSaveWait(('record', 'files'))
    w.callback('record')(True)
    threading.Timer(0.05, lambda: w.callback('files')(False, 'Skill archive upload is not permitted')).start()
    assert w.wait(2) == {'ok': False, 'errors': {'files': 'Skill archive upload is not permitted'}, 'pending': []}

    w2 = sh._CloudSaveWait(('record', 'files'))
    w2.callback('record')(True)
    w2.callback('record')(False, 'late duplicate report is ignored')
    assert w2.wait(0.05) == {'ok': False, 'errors': {}, 'pending': ['files']}


def test_cn_upload_refusal_reaches_the_save(monkeypatch, tmp_path):
    skill_dir = tmp_path / "飞鸽客服问答00_skill"
    skill_dir.mkdir()
    monkeypatch.setattr(sfs, "_is_intl_app", lambda: False)
    monkeypatch.setattr(sfs, "_get_cloud_context", lambda: {"owner": "o3YB"})
    monkeypatch.setattr(sfs, "_resolve_skill_dir", lambda d: skill_dir)
    monkeypatch.setattr(sfs, "_is_valid_skill_dir", lambda d, n: True)
    monkeypatch.setattr(sfs, "_zip_skill_dir", lambda d: b"zip")
    monkeypatch.setattr(sfs, "_RECORD_WAIT_S", (0, 0, 0))     # a refusal that persists
    monkeypatch.setattr(sfs, "_appsync_request", lambda *a, **k: {"errors": [
        {"message": "Skill archive upload is not permitted", "extensions": {"code": "NOT_FOUND"}}]})
    got, done = [], threading.Event()
    sfs.upload_skill_files_to_cloud({"id": "skill_d098", "name": "飞鸽客服问答00"},
                                    on_done=lambda ok, e: (got.append((ok, e)), done.set()))
    assert done.wait(5)
    assert got == [(False, "Skill archive upload is not permitted")]


def test_cn_upload_success_reports_ok(monkeypatch, tmp_path):
    monkeypatch.setattr(sfs, "_is_intl_app", lambda: False)
    monkeypatch.setattr(sfs, "_get_cloud_context", lambda: {"owner": "o3YB"})
    monkeypatch.setattr(sfs, "_resolve_skill_dir", lambda d: tmp_path)
    monkeypatch.setattr(sfs, "_is_valid_skill_dir", lambda d, n: True)
    monkeypatch.setattr(sfs, "_cn_upload_skill_package", lambda d, c, sid: True)
    got, done = [], threading.Event()
    sfs.upload_skill_files_to_cloud({"id": "skill_4f24", "name": "x"},
                                    on_done=lambda ok, e: (got.append((ok, e)), done.set()))
    assert done.wait(5) and got == [(True, "")]


def test_status_call_returns_the_latest_save_outcome():
    w = sh._CloudSaveWait(('record', 'files'))
    sh._CLOUD_SAVES['skill_d098'] = w
    w.callback('record')(False, 'Not found')
    w.callback('files')(False, 'Skill archive upload is not permitted')
    resp = sh.handle_skill_cloud_sync_status({'id': '1', 'method': 'skill_cloud_sync_status'}, {'skillId': 'skill_d098'})
    data = resp.get('result') or resp.get('data') or {}
    assert data['ok'] is False
    assert data['errors'] == {'record': 'Not found', 'files': 'Skill archive upload is not permitted'}
    unknown = sh.handle_skill_cloud_sync_status({'id': '2', 'method': 'x'}, {'skillId': 'never_saved'})
    assert (unknown.get('result') or unknown.get('data'))['ok'] is True


def test_save_as_outcome_is_reported_through_the_same_status_call():
    sh.record_cloud_save('skill_copy1', (False, 'Unique constraint failed on the fields: (`id`)'),
                         (False, 'skipped: the skill record was not created'))
    data = sh.handle_skill_cloud_sync_status({'id': '3', 'method': 'x'}, {'skillId': 'skill_copy1'})
    data = data.get('result') or data.get('data')
    assert data['ok'] is False and 'Unique constraint' in data['errors']['record']
    sh.record_cloud_save('skill_copy2', (True, ''), (True, ''))
    ok = sh.handle_skill_cloud_sync_status({'id': '4', 'method': 'x'}, {'skillId': 'skill_copy2'})
    assert (ok.get('result') or ok.get('data'))['ok'] is True
