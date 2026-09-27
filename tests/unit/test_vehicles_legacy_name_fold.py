"""Computers page: one entry per machine, however many ways it reaches the list."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from gui.ipc.w2p_handlers import vehicle_handler as vh


def _fresh():
    return (datetime.now(timezone.utc) - timedelta(seconds=20)).isoformat()


PLATOON_CLOUD = {'id': '87d7c0de', 'name': 'DESKTOP-LNOV1-S:win', 'status': 'active', 'role': 'Platoon',
                 'type': 'desktop', 'source': 'cloud', 'last_heartbeat': _fresh()}
PLATOON_LAN = {'id': 'lan-87d7', 'name': 'DESKTOP-LNOV1-S', 'status': 'offline', 'type': 'desktop',
               'source': 'lan', 'ip': '192.168.1.23'}


def test_a_live_cloud_row_is_never_dropped_for_a_stale_twin():
    out = vh._merge_same_machine([PLATOON_LAN, dict(PLATOON_CLOUD)])
    assert len(out) == 1
    only = out[0]
    assert only['id'] == '87d7c0de' and only['status'] == 'active'
    assert only['name'] == 'DESKTOP-LNOV1-S', "the :win suffix is dropped for display only"
    assert only['ip'] == '192.168.1.23' and only['role'] == 'Platoon'


def test_this_machine_always_appears_once_and_as_itself():
    me = 'ab7e1120'
    mainwin = SimpleNamespace(host_role='Commander', machine_name='SCHOME', ip='10.0.0.2',
                              platform='Windows', processor='x86_64')
    entries = [
        {'vid': 0, 'name': 'SCHOME:win', 'status': 'running_idle', 'type': 'Computer'},   # legacy in-memory
        {'id': me, 'name': 'SCHOME:win', 'status': 'active', 'type': 'desktop', 'source': 'cloud',
         'last_heartbeat': _fresh(), 'role': 'Commander'},
        dict(PLATOON_CLOUD),
    ]
    with patch.object(vh.AppContext, 'get_main_window', return_value=mainwin), \
         patch('agent.ec_agents.vehicle_affinity.resolve_local_vehicle_id', return_value=me):
        out = vh._mark_self_and_scope(entries)
    mine = [e for e in out if e.get('is_self')]
    assert len(mine) == 1 and mine[0]['id'] == me and mine[0]['name'] == 'SCHOME'
    assert [e['name'] for e in out].count('SCHOME') == 1
    assert any(e['name'] == 'DESKTOP-LNOV1-S' and e['status'] == 'active' for e in out)


def test_a_platoon_sees_itself_and_its_live_commander():
    me = '87d7c0de'
    mainwin = SimpleNamespace(host_role='Platoon', machine_name='DESKTOP-LNOV1-S', ip='', platform='', processor='')
    commander = {'id': 'ab7e1120', 'name': 'SCHOME:win', 'status': 'active', 'type': 'desktop',
                 'source': 'cloud', 'last_heartbeat': _fresh(), 'role': 'Commander'}
    with patch.object(vh.AppContext, 'get_main_window', return_value=mainwin), \
         patch('agent.ec_agents.vehicle_affinity.resolve_local_vehicle_id', return_value=me):
        out = vh._mark_self_and_scope([dict(PLATOON_CLOUD), PLATOON_LAN, commander])
    names = sorted((e['name'], e['status']) for e in out)
    assert names == [('DESKTOP-LNOV1-S', 'active'), ('SCHOME', 'active')]


def test_cloud_pods_are_listed_as_they_are():
    pods = [{'id': 'p1', 'name': 'pod-a', 'type': 'cloud', 'status': 'active'},
            {'id': 'p2', 'name': 'pod-a', 'type': 'cloud', 'status': 'active'}]
    assert len(vh._merge_same_machine(pods)) == 2
