from unittest.mock import Mock, patch

from auth.auth_manager import AuthManager


def _manager(login_type="phone"):
    manager = AuthManager.__new__(AuthManager)
    manager._is_cn = True
    manager.current_user = "+86 13700000000"
    manager.user_profile = {"login_type": login_type}
    manager.tokens = {"AccessToken": "provider.jwt.token"}
    manager._save_wechat_session_token = Mock(return_value=True)
    return manager


def test_non_wechat_login_mints_and_persists_http_session_token():
    manager = _manager()
    response = Mock()
    response.text = "json"
    response.json.return_value = {
        "data": {
            "mintHttpSessionToken": {
                "sessionToken": "durable.http.session",
                "expiresIn": 2592000,
            }
        }
    }

    with patch("requests.post", return_value=response) as post, patch(
        "agent.cloud_api.cloud_api.get_appsync_endpoint",
        return_value="https://example.test/graphql",
    ):
        assert manager._finalize_http_session_token() is True

    manager._save_wechat_session_token.assert_called_once_with("durable.http.session")
    request = post.call_args.kwargs
    assert request["headers"]["Authorization"] == "Bearer provider.jwt.token"
    assert request["json"]["variables"]["input"]["loginType"] == "phone"


def test_wechat_login_keeps_provider_specific_exchange():
    manager = _manager("wechat")
    manager.current_user = "wechat_openid"
    manager._finalize_wechat_session_token = Mock(return_value=True)

    assert manager._finalize_http_session_token() is True
    manager._finalize_wechat_session_token.assert_called_once_with()
