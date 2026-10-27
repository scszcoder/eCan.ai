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
