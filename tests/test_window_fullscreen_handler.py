"""Regression test: window_toggle_fullscreen must marshal Qt window-state
changes onto the Qt main thread.

The GraphQL/IPC handler runs in the uvicorn (HTTP) worker thread, not the Qt
GUI thread. Calling ``QWidget.showFullScreen()`` off the main thread crashes on
macOS with::

    NSInternalInconsistencyException, reason:
    'NSWindow geometry should only be modified on the main thread!'

(seen in runlogs at 2026-11-09 13:51:17 right after a window_toggle_fullscreen
GraphQL call). The handler must therefore dispatch the toggle to the main
thread via ``utils.gui_dispatch.run_on_main_thread``.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from gui.ipc import handlers as handlers_module


def _req(method):
    return {"id": "1", "method": method, "source": "local_server"}


def _install_fake(monkeypatch, web_gui):
    fake_app_ctx = SimpleNamespace(get_instance=lambda: SimpleNamespace(web_gui=web_gui))
    monkeypatch.setattr(handlers_module, "AppContext", fake_app_ctx)


def test_toggle_fullscreen_runs_on_main_thread(monkeypatch):
    events: list[str] = []

    class FakeWebGui:
        def _toggle_fullscreen(self):
            # Must only be reached through the dispatcher.
            assert events and events[-1] == "dispatched", (
                "_toggle_fullscreen was called directly on the worker thread "
                "instead of being marshaled to the Qt main thread"
            )
            events.append("toggled")

        def isFullScreen(self):
            assert events and events[-1] == "toggled"
            return True

    web_gui = FakeWebGui()
    _install_fake(monkeypatch, web_gui)

    def fake_run_on_main_thread(fn, timeout=None):
        events.append("dispatched")
        return fn()

    monkeypatch.setattr(
        "utils.gui_dispatch.run_on_main_thread", fake_run_on_main_thread
    )

    resp = handlers_module.handle_window_toggle_fullscreen(
        _req("window_toggle_fullscreen"), {}
    )

    assert resp["status"] == "success"
    assert resp["result"]["is_fullscreen"] is True
    assert events == ["dispatched", "toggled"]


def test_toggle_fullscreen_missing_window(monkeypatch):
    _install_fake(monkeypatch, None)
    resp = handlers_module.handle_window_toggle_fullscreen(
        _req("window_toggle_fullscreen"), {}
    )
    assert resp["status"] == "error"
    assert resp["error"]["code"] == "WINDOW_NOT_AVAILABLE"
