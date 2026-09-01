"""CN account API-key helper (agent/cloud_api/api_keys.py).

Contract pinned (2026-08-30, live-verified): invoke the myAPIKeygen CloudBase
function via the gateway route — the HTTP equivalent of the web SDK's
callFunction, so all surfaces manage the same ecan_apikeys key:

    POST https://{env_id}.api.tcloudbasegateway.com/v1/functions/myAPIKeygen
    Authorization: Bearer <CloudBase access token>

401/403 falls through the candidate-token chain (given -> app -> minted from
the keyring refresh token, persisting the ROTATED refresh token — CloudBase
refresh tokens are single-use). ensure_api_key is idempotent.
"""

import json
from unittest.mock import MagicMock, patch

from agent.cloud_api import api_keys as ak

ENV = "sccb0-test"
INVOKE_URL = f"https://{ENV}.api.tcloudbasegateway.com/v1/functions/myAPIKeygen"


class _FakeResp:
    status = 200

    def __init__(self, payload):
        self._raw = json.dumps(payload).encode()

    def read(self, n=-1):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _run(fn, server_payload, *args, **kwargs):
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["headers"] = dict(req.headers)
        captured["body"] = json.loads(req.data.decode())
        return _FakeResp(server_payload)

    with patch("agent.cloud_api.cloud_api.req_api_key",
               return_value={"errorType": "TEST", "message": "graphql off"}), \
         patch.object(ak, "_env_id", return_value=ENV), \
         patch.object(ak, "_candidate_tokens",
                      side_effect=lambda g: [ak._strip_bearer(g)] if g else []), \
         patch.object(ak, "_mint_access_token_from_refresh", return_value=""), \
         patch("urllib.request.urlopen", fake_urlopen):
        result = fn(*args, **kwargs)
    return result, captured


def test_mask_matches_web_format():
    assert ak.mask_api_key("abcdef123456uvwxyz") == "abcdef******uvwxyz"
    assert ak.mask_api_key("short") == "short"


def test_create_invokes_gateway_with_bearer():
    result, cap = _run(ak.create_api_key, {"apiKey": "k123", "message": "ok"},
                       "Bearer ACCTOK", customer="guest")
    assert cap["url"] == INVOKE_URL
    assert cap["headers"]["Authorization"] == "Bearer ACCTOK"
    assert cap["body"] == {"action": "createApiKey", "customer": "guest"}
    assert result["apiKey"] == "k123" and result["success"]


def test_get_absent_key_is_success():
    result, cap = _run(ak.get_api_key,
                       {"apiKey": None, "status": "not_found"}, "TOK")
    assert cap["body"] == {"action": "getApiKey"}
    assert result["success"] and result["apiKey"] is None


def test_remove_and_test_actions():
    result, cap = _run(ak.remove_api_keys, {"removed": [{"id": "x"}]},
                       "TOK", ["abc***xyz"])
    assert cap["body"] == {"action": "removeApiKeys", "keys": ["abc***xyz"]}
    assert result["success"]
    result2, cap2 = _run(ak.test_api_key, {"apiKey": "k123", "status": "active"},
                         "TOK", "k123")
    assert cap2["body"] == {"action": "queryApiKey", "apiKey": "k123"}
    assert result2["success"]


def test_401_falls_through_to_next_candidate():
    import urllib.error
    calls = []

    def fake_urlopen(req, timeout=None):
        tok = req.headers.get("Authorization")
        calls.append(tok)
        if tok == "Bearer BAD":
            raise urllib.error.HTTPError(req.full_url, 401, "unauth", None,
                                         __import__("io").BytesIO(b'{"code":"INVALID_CREDENTIALS"}'))
        return _FakeResp({"apiKey": "k9"})

    with patch.object(ak, "_env_id", return_value=ENV), \
         patch.object(ak, "_candidate_tokens", return_value=["BAD", "GOOD"]), \
         patch.object(ak, "_mint_access_token_from_refresh", return_value=""), \
         patch("urllib.request.urlopen", fake_urlopen):
        result = ak.get_api_key("BAD")
    assert calls == ["Bearer BAD", "Bearer GOOD"]
    assert result["apiKey"] == "k9"


def test_mint_persists_rotated_refresh_token():
    saved = {}
    fake_keyring = MagicMock()
    fake_keyring.get_password.return_value = "OLD_RT"
    fake_keyring.set_password.side_effect = lambda s, u, v: saved.update({(s, u): v})

    def fake_urlopen(req, timeout=None):
        return _FakeResp({"access_token": "AT1", "refresh_token": "NEW_RT"})

    import sys
    with patch.dict(sys.modules, {"keyring": fake_keyring}), \
         patch.object(ak, "_env_id", return_value=ENV), \
         patch.dict("os.environ", {"ECAN_CLI_USER": "u@x"}), \
         patch("urllib.request.urlopen", fake_urlopen):
        token = ak._mint_access_token_from_refresh()
    assert token == "AT1"
    assert saved.get(("ecan_cloudbase_refresh", "u@x")) == "NEW_RT"


def test_ensure_existing_key_does_not_create():
    with patch.object(ak, "get_api_key", return_value={"apiKey": "k1", "success": True}), \
         patch.object(ak, "create_api_key") as create:
        result = ak.ensure_api_key("tok")
    assert result["apiKey"] == "k1" and result["created"] is False
    create.assert_not_called()


def test_ensure_absent_key_creates():
    with patch.object(ak, "get_api_key", return_value={"apiKey": None, "success": True}), \
         patch.object(ak, "create_api_key", return_value={"apiKey": "k2", "success": True}):
        result = ak.ensure_api_key("tok")
    assert result["apiKey"] == "k2" and result["created"] is True


def test_no_token_no_mint_reports_no_token():
    with patch.object(ak, "_env_id", return_value=ENV), \
         patch.object(ak, "_candidate_tokens", return_value=[]), \
         patch.object(ak, "_mint_access_token_from_refresh", return_value=""):
        result = ak.create_api_key("")
    assert not result["success"] and result["error"] == "no_token"


def test_local_fallback_prefers_synced_key():
    with patch.object(ak, "get_local_synced_api_key", return_value="LOCALKEY"), \
         patch.object(ak, "get_api_key") as cloud:
        result = ak.get_api_key_with_local_fallback("tok")
    assert result["apiKey"] == "LOCALKEY" and result["source"] == "local"
    cloud.assert_not_called()


def test_live_key_test_hits_models_route():
    def fake_urlopen(req, timeout=None):
        assert req.full_url.endswith("/v1/models")
        assert req.headers.get("Authorization") == "Bearer THEKEY"
        return _FakeResp({"data": [{"id": "qwen-plus"}, {"id": "qwen-max"}]})

    with patch.object(ak, "_llm_proxy_base",
                      return_value="https://x.example/api/llm-proxy"), \
         patch("urllib.request.urlopen", fake_urlopen):
        result = ak.test_api_key_live("THEKEY")
    assert result["valid"] and result["status"] == "active"
    assert result["models"] == ["qwen-plus", "qwen-max"]


def test_live_key_test_invalid_key_reports_http_status():
    import io
    import urllib.error

    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 401, "unauth", None,
                                     io.BytesIO(b'{"error":{"message":"invalid bearer token"}}'))

    with patch.object(ak, "_llm_proxy_base",
                      return_value="https://x.example/api/llm-proxy"), \
         patch("urllib.request.urlopen", fake_urlopen):
        result = ak.test_api_key_live("BADKEY")
    assert not result["valid"] and result["http_status"] == 401


def test_create_prefers_graphql_mutation():
    # CN v21: the standard reqApiKey mutation with the eCan bearer is the
    # primary path (works for WeChat logins); gateway invoke is fallback-only.
    with patch("agent.cloud_api.cloud_api.req_api_key",
               return_value={"apiKey": "kG", "apiKeyId": "id", "message": "ok"}) as gql, \
         patch.object(ak, "_post") as gateway:
        result = ak.create_api_key("Bearer SESSTOK", customer="guest")
    assert result["apiKey"] == "kG" and result["success"]
    gql.assert_called_once()
    assert gql.call_args.args[1] == "SESSTOK"  # bearer stripped, passed through
    gateway.assert_not_called()


def test_create_falls_back_to_gateway_on_pre_v21_backend():
    with patch("agent.cloud_api.cloud_api.req_api_key",
               return_value={"errorType": "GRAPHQL_VALIDATION_FAILED",
                             "message": "Unknown argument input"}), \
         patch.object(ak, "_post", return_value={"apiKey": "kF", "success": True}) as gateway:
        result = ak.create_api_key("TOK")
    assert result["apiKey"] == "kF"
    gateway.assert_called_once()
