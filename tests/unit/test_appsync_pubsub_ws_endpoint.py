# -*- coding: utf-8 -*-
"""The task-status subscription must connect to the WS endpoint, not the HTTP one.

On CN/TCB the realtime WS endpoint is a SEPARATE host from the HTTP GraphQL
endpoint (wss://ecan-graphql-ws-….run.tcloudbase.com/ws vs
https://<env>.service.tcloudbase.com/api/graphql). If AppSyncApiKeyConfig is
built without ws_endpoint, resolved_ws_endpoint() falls back to the HTTP
endpoint, ws_connect gets HTTP 200 instead of a 101 upgrade, and the
subscription fails every retry ("Invalid response status") — the front desk
never receives cloud task events. The runner must pass ws_endpoint
(mainwin.getWSApiEndpoint()); this test pins the config contract that makes the
distinction load-bearing.
"""
from agent.ec_tasks.appsync_pubsub import AppSyncApiKeyConfig

TCB_HTTP = "https://sccb0-d0gc5398xf028be6a.service.tcloudbase.com/api/graphql"
TCB_WS = "wss://ecan-graphql-ws-288118-5-1251680599.sh.run.tcloudbase.com/ws"


def test_explicit_ws_endpoint_is_used_not_http():
    cfg = AppSyncApiKeyConfig(http_endpoint=TCB_HTTP, api_key="k", ws_endpoint=TCB_WS)
    assert cfg.resolved_ws_endpoint() == TCB_WS
    assert cfg.resolved_ws_endpoint() != TCB_HTTP


def test_missing_ws_endpoint_falls_back_to_http_the_footgun():
    # Documents WHY the caller must pass ws_endpoint on TCB: without it the WS
    # connect targets the HTTP /api/graphql endpoint and fails.
    cfg = AppSyncApiKeyConfig(http_endpoint=TCB_HTTP, api_key="k")
    assert cfg.resolved_ws_endpoint() == TCB_HTTP  # <- not connectable as a websocket


def test_aws_appsync_derives_realtime_endpoint():
    http = "https://abc123.appsync-api.us-east-1.amazonaws.com/graphql"
    cfg = AppSyncApiKeyConfig(http_endpoint=http, api_key="k")
    ws = cfg.resolved_ws_endpoint()
    assert ws.startswith("wss://")
    assert "appsync-realtime-api" in ws


def test_explicit_ws_endpoint_wins_over_aws_derivation():
    http = "https://abc123.appsync-api.us-east-1.amazonaws.com/graphql"
    cfg = AppSyncApiKeyConfig(http_endpoint=http, api_key="k", ws_endpoint=TCB_WS)
    assert cfg.resolved_ws_endpoint() == TCB_WS


def test_ssl_context_is_built_once_and_reused():
    """The TLS context must be a process-wide singleton. Building it per call
    (httpx.AsyncClient() / ssl.create_default_context()) loads the CA bundle
    from disk synchronously; on the event loop the A2A heartbeat did that once
    per registered agent every cycle and froze the loop up to 3.5s. Reuse keeps
    it to one disk load for the whole process."""
    import ssl as _ssl

    from agent.ec_tasks import appsync_pubsub as ap
    from utils import shared_ssl

    shared_ssl._shared_ssl_ctx = None  # reset any context a prior test warmed
    first = ap._get_shared_ssl_context()
    second = shared_ssl.get_shared_ssl_context()
    assert isinstance(first, _ssl.SSLContext)
    assert first is second  # one object process-wide — not rebuilt per call
