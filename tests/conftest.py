"""
Pytest configuration for eCan.ai tests.

Overrides asyncio mode to 'auto' so all async test functions and fixtures
are automatically recognized without per-method @pytest.mark.asyncio decorators.
"""

import pytest


def pytest_configure(config):
    """Set asyncio mode."""
    config.option.asyncio_mode = "auto"
    config.option.asyncio_default_fixture_loop_scope = "function"


def pytest_collection_modifyitems(config, items):
    """Automatically mark cloud tests to skip unless explicitly requested."""
    for item in items:
        if "cloud" in item.keywords:
            item.add_marker(pytest.mark.skip(reason="Cloud tests skipped by default. Run with --run-cloud to enable."))


@pytest.fixture(autouse=True)
def _no_real_desktop_input(monkeypatch):
    """Tests never touch the real mouse, keyboard or clipboard. Without this the
    千牛 tests pasted a buyer name + Enter into whatever window had focus (the
    developer's terminal, 2026-10-19: '大作战panda' sent as a chat message, tool
    prompts cancelled). A test that patches one of these itself still wins."""
    try:
        import pyautogui
    except Exception:
        pyautogui = None
    if pyautogui is not None:
        for name in ("click", "doubleClick", "rightClick", "moveTo", "moveRel", "dragTo", "press",
                     "hotkey", "keyDown", "keyUp", "typewrite", "write", "scroll"):
            if hasattr(pyautogui, name):
                monkeypatch.setattr(pyautogui, name, lambda *a, **k: None)
    import sys
    for mod_name in ("agent.mcp.server.wechat.platform_utils", "agent.mcp.server.qianniu.qianniu_tools"):
        mod = sys.modules.get(mod_name)
        if mod is None:
            try:
                mod = __import__(mod_name, fromlist=["_"])
            except Exception:
                continue
        for name in ("paste_hotkey", "clipboard_set_text", "bring_window_to_front", "_force_front"):
            if hasattr(mod, name):
                monkeypatch.setattr(mod, name, lambda *a, **k: None)
