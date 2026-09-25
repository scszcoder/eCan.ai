"""Computers page: a machine's old ``<host>:win`` entry folds into its live entry."""

from gui.ipc.w2p_handlers.vehicle_handler import _fold_legacy_names


def test_platoon_sees_the_live_commander_not_the_residue():
    residue = {'id': 'old-row', 'name': 'SCHOME:win', 'role': 'Commander', 'status': 'offline', 'type': 'desktop'}
    live = {'id': 'fp-123', 'name': 'schome', 'hostname': 'SCHOME', 'role': '', 'status': 'active', 'type': 'desktop'}
    me = {'id': 'fp-999', 'name': 'platoon1', 'status': 'active', 'type': 'desktop'}
    out = _fold_legacy_names([residue, live, me], 'platoon1')
    assert [e['id'] for e in out] == ['fp-123', 'fp-999']
    assert live['role'] == 'Commander', "the live entry takes over the role the residue carried"


def test_commander_own_legacy_entry_goes_even_before_self_is_listed():
    legacy_self = {'vid': 0, 'name': 'SCHOME:win', 'status': 'running_idle', 'type': 'Computer'}
    assert _fold_legacy_names([legacy_self], 'SCHOME') == []


def test_a_legacy_name_with_no_live_twin_stays():
    only = {'id': 'x', 'name': 'OFFICE2:win', 'status': 'offline'}
    assert _fold_legacy_names([only], 'schome') == [only]


def test_a_live_role_is_not_overwritten():
    residue = {'name': 'HOST:win', 'role': 'Commander'}
    live = {'name': 'host', 'role': 'Platoon'}
    _fold_legacy_names([residue, live], '')
    assert live['role'] == 'Platoon'
