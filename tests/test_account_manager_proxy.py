"""The desktop calls ecbAccountManager server-side, because the browser can't.

Reported: the web app lists pods fine, the desktop shows "Could not load your
pods / Failed to fetch". The console said why:

    Access to fetch at '.../ecbAccountManager' from origin
    'http://localhost:3000' has been blocked by CORS policy
    [AccountManager] pod_list failed {}

Pods are not GraphQL — they are ecbAccountManager actions writing `fleet_pools`.
The web build is served from the cloud origin so its fetch is allowed; the
desktop UI runs on localhost (dev) or file:// (packaged) and is refused. A
server-side allowlist cannot fix the packaged case either, since file:// sends
`Origin: null`. So the desktop makes the call from Python.
"""

import json
from unittest.mock import patch

import pytest

from gui.ipc.types import create_request


@pytest.fixture
def handler():
    from gui.ipc.w2p_handlers.vehicle_handler import handle_account_manager_call
    return handle_account_manager_call


def _call(handler, action, payload=None, status=200, data=None, boom=None):
    """Run the handler with the cloud call stubbed."""
    def _fake(_action, _payload):
        if boom:
            raise boom
        return status, (data if data is not None else {'success': True, 'pods': []})

    with patch('gui.ipc.w2p_handlers.vehicle_handler._call_account_manager', _fake):
        return handler(create_request('account_manager_call'),
                       {'action': action, 'input': payload or {}})


def test_an_allowlisted_action_returns_the_servers_payload(handler):
    resp = _call(handler, 'pod_list',
                 data={'success': True, 'pods': [{'id': 'pod_1'}], 'limits': {'max_pods': 5}})

    assert resp['status'] == 'success', resp
    assert resp['result']['pods'] == [{'id': 'pod_1'}]
    assert resp['result']['limits'] == {'max_pods': 5}
    # `success` is the envelope, not payload — the web path strips it too, so
    # both platforms hand the caller the same shape.
    assert 'success' not in resp['result']


def test_an_unknown_action_is_refused_without_calling_out(handler):
    """A local endpoint holding the user's bearer is not an open proxy."""
    called = []

    def _fake(action, payload):
        called.append(action)
        return 200, {'success': True}

    with patch('gui.ipc.w2p_handlers.vehicle_handler._call_account_manager', _fake):
        resp = handler(create_request('account_manager_call'),
                       {'action': 'delete_account', 'input': {}})

    assert resp['status'] == 'error'
    assert resp['error']['code'] == 'ACTION_NOT_ALLOWED'
    assert called == [], 'a refused action must not reach the network'


@pytest.mark.parametrize('action', ['pod_list', 'pod_save', 'pod_delete', 'fleet_status'])
def test_the_pod_actions_the_ui_needs_are_allowed(handler, action):
    resp = _call(handler, action)
    assert resp['status'] == 'success', resp


def test_the_servers_own_message_survives(handler):
    """The pod cap answers with the real number; a generic 'failed' loses it."""
    resp = _call(handler, 'pod_save', status=409,
                 data={'success': False, 'error': 'POD_LIMIT',
                       'message': 'that would put this account at 6 pods; the limit is 5'})

    assert resp['status'] == 'error'
    assert resp['error']['code'] == 'POD_LIMIT'
    assert '6 pods' in resp['error']['message']


def test_a_rejected_session_says_so_rather_than_failing_generically(handler):
    resp = _call(handler, 'pod_list', status=401, data={'success': False})

    assert resp['status'] == 'error'
    assert resp['error']['code'] == 'UNAUTHORIZED'
    assert 'sign in' in resp['error']['message'].lower()


def test_a_transport_failure_is_reported_as_one(handler):
    resp = _call(handler, 'pod_list', boom=OSError('connection refused'))

    assert resp['status'] == 'error'
    assert resp['error']['code'] == 'NETWORK_ERROR'
    assert 'connection refused' in resp['error']['message']


def test_not_signed_in_is_told_apart_from_a_network_failure(handler):
    resp = _call(handler, 'pod_list', boom=PermissionError('Not signed in — no session token'))

    assert resp['status'] == 'error'
    assert resp['error']['code'] == 'TOKEN_REQUIRED'


def test_a_non_dict_input_does_not_reach_the_server_as_one(handler):
    seen = {}

    def _fake(action, payload):
        seen['payload'] = payload
        return 200, {'success': True}

    with patch('gui.ipc.w2p_handlers.vehicle_handler._call_account_manager', _fake):
        handler(create_request('account_manager_call'),
                {'action': 'pod_list', 'input': 'not-a-dict'})

    assert seen['payload'] == {}


def test_the_client_routes_desktop_through_this_handler():
    """The TS side must not fetch the cloud directly when on desktop.

    That is the whole bug: a direct fetch from localhost/file:// is refused by
    CORS, and no amount of retrying changes that.
    """
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1]
           / 'gui_v2/src/services/api/accountManagerClient.ts').read_text(encoding='utf-8')

    assert "detectPlatform() === 'desktop'" in src
    assert "'account_manager_call'" in src
    # The desktop branch has to come before the fetch, or it never runs.
    assert src.index("detectPlatform() === 'desktop'") < src.index('await fetch(')
