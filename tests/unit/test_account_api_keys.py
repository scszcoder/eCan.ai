"""CN account API-key helper (agent/cloud_api/api_keys.py).

Contract pinned: POST <tcb-origin>/myAPIKeygen with the session token in the
BODY (gateway strips Authorization); actions mirror the web Account page's
callFunction usage (createApiKey / getApiKey / removeApiKeys / queryApiKey);
ensure_api_key is idempotent.
"""

import json
from unittest.mock import MagicMock, patch

from agent.cloud_api import api_keys as ak

GQL = "https://sccb0-x.service.tcloudbase.com/api/graphql"


class _FakeResp:
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

    ep = MagicMock()
    ep.graphql_endpoint = GQL
    with patch("agent.cloud_api.endpoints.get_endpoint_config", return_value=ep), \
         patch("urllib.request.urlopen", fake_urlopen):
        result = fn(*args, **kwargs)
    return result, captured


def test_mask_matches_web_format():
    assert ak.mask_api_key("abcdef123456uvwxyz") == "abcdef******uvwxyz"
    assert ak.mask_api_key("short") == "short"


def test_create_sends_body_token_no_auth_header():
    result, cap = _run(ak.create_api_key, {"apiKey": "k123", "message": "ok"},
                       "Bearer SESSTOK", customer="guest")
    assert cap["url"].endswith("/myAPIKeygen")
    assert "Authorization" not in cap["headers"]
    assert cap["body"] == {"action": "createApiKey", "sessionToken": "SESSTOK",
                           "customer": "guest"}
    assert result["apiKey"] == "k123" and result["success"]


def test_get_absent_key_is_success():
    result, cap = _run(ak.get_api_key,
                       {"apiKey": None, "status": "not_found"}, "SESSTOK")
    assert cap["body"]["action"] == "getApiKey"
    assert result["success"] and result["apiKey"] is None


def test_remove_and_test_actions():
    result, cap = _run(ak.remove_api_keys, {"removed": [{"id": "x"}]},
                       "SESSTOK", ["abc***xyz"])
    assert cap["body"] == {"action": "removeApiKeys", "sessionToken": "SESSTOK",
                           "keys": ["abc***xyz"]}
    assert result["success"]
    result2, cap2 = _run(ak.test_api_key, {"apiKey": "k123", "status": "active"},
                         "SESSTOK", "k123")
    assert cap2["body"]["action"] == "queryApiKey" and cap2["body"]["apiKey"] == "k123"
    assert result2["success"]


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


def test_no_token_short_circuits():
    result = ak.create_api_key("")
    assert not result["success"] and result["error"] == "no_token"
