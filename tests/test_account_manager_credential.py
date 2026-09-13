"""ecbAccountManager takes the same bearer GraphQL does.

Reported: the desktop pods panel reached the server (the CORS fix worked) and
was then refused:

    account_manager_call -> UNAUTHORIZED:
    The session was rejected by pod_list; sign in again.

while the *same* session was making GraphQL calls successfully with a 177-char
HS256 token. Two credentials exist for a CN WeChat login and only one works
over HTTP:

  * eCan session token — HS256, sub=<openid>, 30 days. What the SCF HTTP gate
    verifies. `_http_auth_header` picks this for every GraphQL call.
  * CloudBase access JWT — sub=<uid>, ~10 minutes, unrefreshable for WeChat.
    Valid on the WS lane only.

`_session_bearer_token` read the access token first, so every ecbAccountManager
call — pod_list, fleet_status, turn_enqueue — sent the credential the gate
cannot verify.
"""

import pytest


class _FakeAuthManager:
    def __init__(self, tokens):
        self._tokens = tokens

    def get_tokens(self):
        return self._tokens


class _FakeMainWindow:
    def __init__(self, http_bearer, tokens=None):
        self._http_bearer = http_bearer
        self.auth_manager = _FakeAuthManager(tokens or {})

    def get_auth_token(self):
        return 'combined-token'


@pytest.fixture
def use_mainwin(monkeypatch):
    """Install a fake MainWindow and a controllable _http_auth_header."""
    def _install(http_bearer, tokens=None):
        import agent.cloud_api.cloud_api as cloud_api
        import app_context

        win = _FakeMainWindow(http_bearer, tokens)
        monkeypatch.setattr(app_context.AppContext, 'get_main_window',
                            staticmethod(lambda: win), raising=False)
        monkeypatch.setattr(cloud_api, '_http_auth_header', lambda _t: http_bearer)
        return win
    return _install


def test_the_session_token_wins_over_the_access_token(use_mainwin):
    """The exact shape of the bug: both exist, and the wrong one was chosen."""
    from agent.cloud_api.turn_queue import _session_bearer_token

    use_mainwin(
        http_bearer='Bearer ecan-session-token',
        tokens={'AccessToken': 'cloudbase-access-jwt'},
    )

    assert _session_bearer_token() == 'ecan-session-token'


def test_the_bearer_prefix_is_stripped(use_mainwin):
    """The caller adds its own `Authorization: Bearer <token>`."""
    from agent.cloud_api.turn_queue import _session_bearer_token

    use_mainwin(http_bearer='Bearer abc123')

    token = _session_bearer_token()
    assert token == 'abc123'
    assert not token.lower().startswith('bearer')


def test_an_unprefixed_token_passes_through(use_mainwin):
    """Intl sends the Cognito token raw, with no Bearer prefix."""
    from agent.cloud_api.turn_queue import _session_bearer_token

    use_mainwin(http_bearer='cognito-id-token')

    assert _session_bearer_token() == 'cognito-id-token'


def test_the_access_token_is_still_the_fallback(use_mainwin):
    """An email/CIAM login before its session token is minted has only this."""
    from agent.cloud_api.turn_queue import _session_bearer_token

    use_mainwin(http_bearer='', tokens={'AccessToken': 'ciam-access-token'})

    assert _session_bearer_token() == 'ciam-access-token'


def test_no_window_and_no_tokens_yield_empty_rather_than_raising(monkeypatch):
    """Callers treat "" as not-signed-in and say so; an exception would not."""
    import app_context
    from agent.cloud_api.turn_queue import _session_bearer_token

    monkeypatch.setattr(app_context.AppContext, 'get_main_window',
                        staticmethod(lambda: None), raising=False)

    assert _session_bearer_token() == ''


def test_every_account_manager_caller_uses_this_one_selection():
    """pod_*, fleet_status and turn_enqueue are one gateway and one credential.

    They drifted once already; a second copy of the selection is how it would
    happen again.
    """
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    handler = (root / 'gui/ipc/w2p_handlers/vehicle_handler.py').read_text(encoding='utf-8')
    queue = (root / 'agent/cloud_api/turn_queue.py').read_text(encoding='utf-8')

    # The handler must not pick a credential of its own.
    assert 'AccessToken' not in handler, 'vehicle_handler picks its own credential'
    assert handler.count('_session_bearer_token') >= 2, 'handler should use the shared helper'

    # And the helper must derive it from the HTTP header selection.
    body = re.search(r'def _session_bearer_token.*?\n\ndef ', queue, re.S)
    assert body and '_http_auth_header' in body.group(0), (
        '_session_bearer_token must delegate to the GraphQL credential choice')
