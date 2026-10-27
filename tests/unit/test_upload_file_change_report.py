"""Our upload_file reports what the page did, so the agent can tell an accepted
upload from a failed or still-running one (browser-use's says "Successfully
uploaded" whatever happened; KEN 2026-10-28 拼多多 lost ~50 steps to that)."""
from agent.ec_skills.browser_use_extension.extension_tools_service import (
    custom_controller,
    describe_upload_change,
)

BASE = {"text": "本地上传", "media": 0, "input": True, "uploading": 0, "failed": 0}


def test_accepted_upload_is_reported_as_such():
    assert "redrawn" in describe_upload_change(BASE, {"redrawn": True})
    gone = describe_upload_change(BASE, {**BASE, "input": False, "media": 1, "text": "燕麦色 删除"})
    assert "control is gone" in gone and "1 new image" in gone and "燕麦色" in gone


def test_failed_and_running_uploads_are_called_out():
    assert "上传失败" in describe_upload_change(BASE, {**BASE, "failed": 1})
    assert "still uploading" in describe_upload_change(BASE, {**BASE, "uploading": 1})
    assert "no visible change" in describe_upload_change(BASE, dict(BASE))


def test_ours_replaces_browser_use_upload_and_ends_the_step():
    action = custom_controller.registry.registry.actions["upload_file"]
    assert action.function.__module__.endswith("extension_tools_service")
    assert action.terminates_sequence


class _FakeClient:
    """Enough of a cdp_use client for _open_file_chooser: records calls and fires
    Page.fileChooserOpened when the element is clicked, if the page would."""

    def __init__(self, opens_chooser: bool):
        import types
        self.calls, self.handler, self.opens = [], None, opens_chooser
        self._event_registry = types.SimpleNamespace(unregister=lambda m: setattr(self, "handler", None))
        self.register = types.SimpleNamespace(Page=types.SimpleNamespace(
            fileChooserOpened=lambda cb: setattr(self, "handler", cb)))

        async def call(name, params=None, session_id=None):
            self.calls.append((name, params))
            if name == "Runtime.callFunctionOn" and self.opens and self.handler:
                self.handler({"backendNodeId": 42, "mode": "selectMultiple"}, session_id)
            return {}
        domain = lambda d: types.SimpleNamespace(**{m: (lambda m=m: (lambda params=None, session_id=None:
                                                                     call(f"{d}.{m}", params, session_id)))()
                                                    for m in ("setInterceptFileChooserDialog", "callFunctionOn")})
        self.send = types.SimpleNamespace(Page=domain("Page"), Runtime=domain("Runtime"))


def test_a_click_that_opens_a_file_picker_hands_back_its_input():
    # 拼多多 选择图片 makes its own input per click; only the picker it opens takes a file.
    import asyncio
    from agent.ec_skills.browser_use_extension.extension_tools_service import _open_file_chooser
    c = _FakeClient(opens_chooser=True)
    assert asyncio.run(_open_file_chooser(c, "s1", "obj")) == 42
    click = next(p for n, p in c.calls if n == "Runtime.callFunctionOn")
    assert click["userGesture"] is True
    assert [p["enabled"] for n, p in c.calls if n == "Page.setInterceptFileChooserDialog"] == [True, False]
    assert c.handler is None


def test_a_click_that_opens_no_picker_returns_none_and_cleans_up():
    import asyncio
    from agent.ec_skills.browser_use_extension.extension_tools_service import _open_file_chooser
    c = _FakeClient(opens_chooser=False)
    assert asyncio.run(_open_file_chooser(c, "s1", "obj", wait_s=0.2)) is None
    assert [p["enabled"] for n, p in c.calls if n == "Page.setInterceptFileChooserDialog"] == [True, False]
    assert c.handler is None
