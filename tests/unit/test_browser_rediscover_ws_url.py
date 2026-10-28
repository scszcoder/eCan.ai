"""Tab rediscovery must connect to the browser's websocket, not its http
address ("http://127.0.0.1:57751 isn't a valid URI: scheme isn't ws", KEN
2026-10-28: every listing run then failed its focus preflight)."""
import io
import json
from unittest import mock

from agent.ec_skills.browser_node.runner import _debugger_ws_url


def test_ws_urls_pass_through():
    assert _debugger_ws_url("ws://127.0.0.1:9222/devtools/browser/x") == "ws://127.0.0.1:9222/devtools/browser/x"


def test_http_address_is_resolved_to_the_websocket():
    body = io.BytesIO(json.dumps({"webSocketDebuggerUrl": "ws://127.0.0.1:57751/devtools/browser/abc"}).encode())
    body.__enter__ = lambda *a: body
    body.__exit__ = lambda *a: False
    with mock.patch("urllib.request.urlopen", return_value=body) as op:
        assert _debugger_ws_url("http://127.0.0.1:57751") == "ws://127.0.0.1:57751/devtools/browser/abc"
        assert op.call_args[0][0] == "http://127.0.0.1:57751/json/version"
