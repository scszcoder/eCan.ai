"""
Regression test for the browser-extension WS thread leak.

Before the fix (`appsync_passive_client.py` and `appsync_passive_transport.py`),
`_ws_thread` was a daemon thread not registered in the global
`_appsync_ws_threads` registry, so `cleanup_appsync_ws_threads()` (called on
logout/shutdown) couldn't join it. The fix threads each `_ws_thread` and the
inner reconnect thread through `_track_appsync_ws_thread()` so the global
cleanup path drains them.

These tests verify the tracking wiring at a unit level, without requiring a
live AppSync connection.
"""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

import pytest


def test_passive_transport_module_imports_and_references_tracker():
    """The transport module must import and call the global tracker."""
    import agent.ec_skills.browser_use_extension.appsync_passive_transport as pt
    import agent.cloud_api.cloud_api as ca

    # Direct check: the module binds _track_appsync_ws_thread into its namespace
    # at import time, so any future code in this module can call it.
    assert hasattr(pt, "_track_appsync_ws_thread")
    assert pt._track_appsync_ws_thread is ca._track_appsync_ws_thread


def test_passive_client_module_imports_and_references_tracker():
    """The client module must import and call the global tracker."""
    import agent.ec_skills.browser_use_extension.appsync_passive_client as pc
    import agent.cloud_api.cloud_api as ca

    assert hasattr(pc, "_track_appsync_ws_thread")
    assert pc._track_appsync_ws_thread is ca._track_appsync_ws_thread


def test_passive_transport_ws_thread_registers_into_global_registry():
    """
    When _ensure_subscription_started() runs, the WS thread it spawns must
    appear in `_appsync_ws_threads` immediately.
    """
    import agent.cloud_api.cloud_api as ca
    import agent.ec_skills.browser_use_extension.appsync_passive_transport as pt

    # Patch _build_ws_url so we don't need a real signed URL.
    initial_names = {t.name for t in ca._appsync_ws_threads}

    config = pt.AppSyncPassiveTransportConfig(
        http_endpoint="https://example.invalid",
        ws_endpoint="wss://example.invalid",
        api_host="example.invalid",
        auth_token="token",
        client_id="cid",
    )
    transport = pt.AppSyncPassivePubSubTransport(config=config)

    # Mock WebSocketApp so run_forever blocks on an event we control.
    connect_event = threading.Event()
    release_event = threading.Event()
    mock_ws = MagicMock()
    mock_ws.run_forever.side_effect = lambda *a, **kw: (
        connect_event.set(),
        release_event.wait(timeout=5.0),
    )
    mock_ws.close.side_effect = lambda: release_event.set()

    with patch.object(pt.websocket, "WebSocketApp", return_value=mock_ws):
        transport._ensure_subscription_started(run_id="r-1")

    try:
        # Wait for the thread to actually be alive and registered.
        assert transport._ws_thread is not None, (
            "_ensure_subscription_started must populate _ws_thread"
        )
        assert transport._ws_thread.name.startswith("PassiveTransport-ws-"), (
            f"WS thread must have a debuggable name, got {transport._ws_thread.name!r}"
        )
        # Allow the lambda to set connect_event so run_forever is reached.
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and not connect_event.is_set():
            time.sleep(0.02)
        assert connect_event.is_set(), "mock run_forever was never invoked"

        tracked_names = {t.name for t in ca._appsync_ws_threads}
        assert transport._ws_thread.name in tracked_names, (
            f"{transport._ws_thread.name!r} not in registry: {tracked_names}"
        )
    finally:
        transport.close()


def test_passive_transport_close_joins_per_instance_thread():
    """
    Per-instance close() must wait for the run_forever thread to exit. Without
    this, every passive browser session leaves an 8 MB daemon thread behind.
    """
    import agent.ec_skills.browser_use_extension.appsync_passive_transport as pt

    config = pt.AppSyncPassiveTransportConfig(
        http_endpoint="https://example.invalid",
        ws_endpoint="wss://example.invalid",
        api_host="example.invalid",
        auth_token="token",
        client_id="cid",
    )
    transport = pt.AppSyncPassivePubSubTransport(config=config)

    connect_event = threading.Event()
    release_event = threading.Event()
    mock_ws = MagicMock()
    mock_ws.run_forever.side_effect = lambda *a, **kw: (
        connect_event.set(),
        release_event.wait(timeout=5.0),
    )
    mock_ws.close.side_effect = lambda: release_event.set()

    with patch.object(pt.websocket, "WebSocketApp", return_value=mock_ws):
        transport._ensure_subscription_started(run_id="r-2")

    thread = transport._ws_thread
    assert thread is not None
    # wait until the lambda actually entered run_forever
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and not connect_event.is_set():
        time.sleep(0.02)
    assert connect_event.is_set()

    transport.close()

    assert transport._ws is None
    assert transport._ws_thread is None
    assert not thread.is_alive(), (
        f"close() did not join thread {thread.name!r}"
    )


def test_global_cleanup_drains_passive_transport_threads_after_ws_closed():
    """
    Simulates the real MainWindow logout path: when the WS has been closed
    (so run_forever() returns), cleanup_appsync_ws_threads() must drain the
    thread. Pre-fix, these threads weren't even in the registry, so neither
    per-instance close() nor the global cleanup could find them.
    """
    import agent.cloud_api.cloud_api as ca
    import agent.ec_skills.browser_use_extension.appsync_passive_transport as pt

    config = pt.AppSyncPassiveTransportConfig(
        http_endpoint="https://example.invalid",
        ws_endpoint="wss://example.invalid",
        api_host="example.invalid",
        auth_token="token",
        client_id="cid",
    )
    transport = pt.AppSyncPassivePubSubTransport(config=config)

    connect_event = threading.Event()
    release_event = threading.Event()
    mock_ws = MagicMock()
    mock_ws.run_forever.side_effect = lambda *a, **kw: (
        connect_event.set(),
        release_event.wait(timeout=5.0),
    )
    mock_ws.close.side_effect = lambda: release_event.set()

    with patch.object(pt.websocket, "WebSocketApp", return_value=mock_ws):
        transport._ensure_subscription_started(run_id="r-3")

    thread = transport._ws_thread
    assert thread is not None
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and not connect_event.is_set():
        time.sleep(0.02)
    assert connect_event.is_set()

    # Simulate the MainWindow closeEvent pattern: close the WS handle,
    # then global cleanup joins the thread.
    pre_count = ca.get_appsync_ws_thread_count()
    assert thread.name in {t.name for t in ca._appsync_ws_threads}, (
        f"{thread.name!r} not registered globally; registry={pre_count}"
    )

    # Mimic MainGUI._close_appsync_ws_subscriptions() pattern: close ws
    # (release_event.set makes run_forever return), then call global cleanup.
    mock_ws.close()
    ca.cleanup_appsync_ws_threads(timeout=5.0)

    assert not thread.is_alive(), (
        f"global cleanup did not join transport thread {thread.name!r}"
    )
    transport._ws_thread = None  # cleanup completed; pretend transport is gone
