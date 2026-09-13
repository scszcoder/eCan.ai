"""Activating a vehicle from the details panel.

Reported 2026-09-13: clicking 激活 showed the raw i18n key
`pages.vehicles.statusUpdateFailed`. The handler had received
`{'vehicle_id': None, 'status': 'active'}` — the client sent no id at all,
because `vehicleApi.update` did `updatedVehicle.vid || parseInt(id)` and the
row it was acting on is a DB-backed one whose id is a non-numeric string.
`parseInt` returned NaN, which JSON-encodes as null.

Fixing that alone only moved the error: the handler looked the id up in the
in-memory machine registry, where a DB-backed row has never been, so it would
then have answered VEHICLE_NOT_FOUND.
"""

import pytest

from gui.ipc.types import create_request


class _FakeVehicle:
    def __init__(self, vid, status='offline'):
        self.id = vid
        self.status = status

    def setStatus(self, s):
        self.status = s

    def to_dict(self):
        return {'vid': self.id, 'status': self.status}


class _FakeService:
    def __init__(self, rows):
        self.rows = rows
        self.updates = []

    def query_vehicles(self, id=None, **kw):
        hit = [r for r in self.rows if str(r.get('id')) == str(id)]
        return {'success': True, 'data': hit}

    def update_vehicle(self, vid, fields):
        self.updates.append((vid, fields))
        return {'success': True}


class _FakeCtx:
    def __init__(self, vehicles, service):
        self._vehicles = vehicles
        self._service = service
        self.main_window = self
        self.saved = []

    def get_vehicles(self):
        return self._vehicles

    def get_ec_db_mgr(self):
        return type('M', (), {'vehicle_service': self._service})()

    def saveVehicle(self, v):
        self.saved.append(v)


@pytest.fixture
def ctx(monkeypatch):
    from gui.ipc.w2p_handlers import vehicle_handler as vh

    service = _FakeService([
        {'id': 'mach-abc', 'name': 'builder', 'vehicle_type': 'desktop', 'status': 'offline'},
        {'id': 'pod_deadbeef', 'name': 'cs-pod', 'vehicle_type': 'cloud', 'status': 'offline'},
    ])
    c = _FakeCtx([_FakeVehicle(3)], service)
    monkeypatch.setattr(vh, 'get_handler_context', lambda r, p: c)
    return c


def test_an_in_memory_machine_still_updates(ctx):
    """The legacy path must keep working."""
    from gui.ipc.w2p_handlers.vehicle_handler import handle_update_vehicle_status

    resp = handle_update_vehicle_status(
        create_request('update_vehicle_status'), {'vehicle_id': 3, 'status': 'active'})

    assert resp['status'] == 'success', resp
    assert ctx._vehicles[0].status == 'online'   # active -> online
    assert ctx.saved == [ctx._vehicles[0]]


def test_a_db_backed_row_updates_instead_of_not_found(ctx):
    """A string-id row merged in by get_vehicles is not in the registry."""
    from gui.ipc.w2p_handlers.vehicle_handler import handle_update_vehicle_status

    resp = handle_update_vehicle_status(
        create_request('update_vehicle_status'),
        {'vehicle_id': 'mach-abc', 'status': 'active'})

    assert resp['status'] == 'success', resp
    assert ctx._service.updates == [('mach-abc', {'status': 'online'})]


def test_a_pod_refuses_because_its_status_is_reported(ctx):
    """Writing 'online' into a pod row starts nothing; it only makes the UI lie."""
    from gui.ipc.w2p_handlers.vehicle_handler import handle_update_vehicle_status

    resp = handle_update_vehicle_status(
        create_request('update_vehicle_status'),
        {'vehicle_id': 'pod_deadbeef', 'status': 'active'})

    assert resp['status'] == 'error'
    assert resp['error']['code'] == 'POD_STATUS_IS_REPORTED'
    assert ctx._service.updates == []


def test_an_unknown_id_is_still_not_found(ctx):
    from gui.ipc.w2p_handlers.vehicle_handler import handle_update_vehicle_status

    resp = handle_update_vehicle_status(
        create_request('update_vehicle_status'), {'vehicle_id': 'nope', 'status': 'active'})

    assert resp['status'] == 'error'
    assert resp['error']['code'] == 'VEHICLE_NOT_FOUND'


def test_a_missing_id_is_still_rejected(ctx):
    """The original symptom: the client sent null. Still a clear refusal."""
    from gui.ipc.w2p_handlers.vehicle_handler import handle_update_vehicle_status

    resp = handle_update_vehicle_status(
        create_request('update_vehicle_status'), {'vehicle_id': None, 'status': 'active'})

    assert resp['status'] == 'error'
    assert resp['error']['code'] == 'INVALID_PARAMS'


def test_every_vehicles_message_key_exists_in_both_locales():
    """The popup showed `pages.vehicles.statusUpdateFailed` verbatim.

    It was one of 15 keys the page referenced and neither locale defined, so
    the untranslated key was rendered as the message.
    """
    import json
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / 'gui_v2/src'
    used = set()
    for f in (root / 'pages/Vehicles').rglob('*.tsx'):
        used |= set(re.findall(r'pages\.vehicles\.([A-Za-z0-9_]+)',
                               f.read_text(encoding='utf-8')))
    assert used, 'no keys found — did the page move?'

    for loc in ('en-US', 'zh-CN'):
        data = json.loads((root / f'i18n/locales/{loc}.json').read_text(encoding='utf-8'))
        have = set(data['pages']['vehicles'].keys())
        assert not (used - have), f'{loc} is missing {sorted(used - have)}'
