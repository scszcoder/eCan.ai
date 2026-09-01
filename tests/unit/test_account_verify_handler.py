"""Contact-verification handshake IPC handlers (CN).

Contract (server 92e8741, 2026-09-01): verify_send_code / verify_confirm /
verify_status POST to {origin}/ecbAccountManager with Authorization: Bearer
(CloudBase AccessToken preferred, eCan session token fallback). Typed server
error codes (invalid_code, retry_later, …) pass through as the IPC error
code with the parsed body in details.
"""

import json
from unittest.mock import patch

from gui.ipc.w2p_handlers import account_verify_handler as avh


REQ = {"id": "1", "method": "verify_send_code", "params": {}, "type": "request"}


class _FakeResp:
    def __init__(self, payload, status=200):
        self._raw = json.dumps(payload).encode()
        self.status = status

    def read(self, n=-1):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _run(handler, params, server_payload, status=200):
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["headers"] = dict(req.headers)
        captured["body"] = json.loads(req.data.decode())
        if status >= 400:
            import io
            import urllib.error
            raise urllib.error.HTTPError(
                req.full_url, status, "err", None,
                io.BytesIO(json.dumps(server_payload).encode()))
        return _FakeResp(server_payload, status)

    with patch.object(avh, "is_cn", return_value=True), \
         patch.object(avh, "_bearer_token", return_value="TOK"), \
         patch.object(avh, "_account_manager_url",
                      return_value="https://x.example/ecbAccountManager"), \
         patch("urllib.request.urlopen", fake_urlopen):
        resp = handler(dict(REQ), params)
    return resp, captured


def test_send_code_posts_action_with_bearer():
    resp, cap = _run(avh.handle_verify_send_code,
                     {"channel": "email", "target": "u@x.com"},
                     {"success": True, "channel": "email",
                      "target": "u***@x.com", "expiresInSeconds": 600})
    assert cap["url"].endswith("/ecbAccountManager")
    assert cap["headers"]["Authorization"] == "Bearer TOK"
    assert cap["body"] == {"action": "verify_send_code",
                           "channel": "email", "target": "u@x.com"}
    assert resp["status"] == "success"
    assert resp["result"]["target"] == "u***@x.com"


def test_confirm_success_returns_account():
    account = {"email": "u@x.com", "email_verified": True,
               "phone": "", "phone_verified": False, "verify_deadline": None}
    resp, cap = _run(avh.handle_verify_confirm,
                     {"channel": "email", "code": "123456"},
                     {"success": True, "verified": True, "account": account})
    assert cap["body"] == {"action": "verify_confirm",
                           "channel": "email", "code": "123456"}
    assert resp["result"]["account"]["email_verified"] is True


def test_invalid_code_passes_typed_error_and_attempts():
    resp, _ = _run(avh.handle_verify_confirm,
                   {"channel": "email", "code": "000000"},
                   {"success": False, "error": "invalid_code",
                    "remaining_attempts": 3}, status=400)
    assert resp["status"] == "error"
    assert resp["error"]["code"] == "invalid_code"
    assert resp["error"]["details"]["remaining_attempts"] == 3


def test_channel_not_configured_503():
    resp, _ = _run(avh.handle_verify_send_code,
                   {"channel": "phone", "target": "13812345678"},
                   {"success": False, "error": "channel_not_configured"},
                   status=503)
    assert resp["error"]["code"] == "channel_not_configured"


def test_status_action():
    resp, cap = _run(avh.handle_verify_status, {},
                     {"success": True, "email_verified": False, "pending": []})
    assert cap["body"] == {"action": "verify_status"}
    assert resp["status"] == "success"


def test_invalid_params_rejected_locally():
    resp = avh.handle_verify_send_code(dict(REQ), {"channel": "fax", "target": "x"})
    assert resp["error"]["code"] == "INVALID_PARAMS"
    resp2 = avh.handle_verify_confirm(dict(REQ), {"channel": "email"})
    assert resp2["error"]["code"] == "INVALID_PARAMS"


def test_no_token_is_clean_error():
    with patch.object(avh, "is_cn", return_value=True), \
         patch.object(avh, "_bearer_token", return_value=""), \
         patch.object(avh, "_account_manager_url",
                      return_value="https://x.example/ecbAccountManager"):
        resp = avh.handle_verify_status(dict(REQ), {})
    assert resp["error"]["code"] == "NO_TOKEN"


def test_intl_rejected():
    with patch.object(avh, "is_cn", return_value=False):
        resp = avh.handle_verify_status(dict(REQ), {})
    assert resp["error"]["code"] == "CN_ONLY"
