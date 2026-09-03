"""Chrome launcher tool (agent/mcp/server/chrome_launcher.py).

Contract: launch_chrome_debug detects/launches a CDP-ready Chrome and NEVER
installs; a missing Chrome returns not_installed so the LLM asks the user
before install_chrome runs (consent is also enforced structurally in the
MCP wrapper / browser-use action via confirmed_by_user).
"""

from unittest.mock import MagicMock, patch

from agent.mcp.server import chrome_launcher as cl


def test_not_installed_reports_and_does_not_launch():
    with patch.object(cl, "find_chrome", return_value={"found": False, "path": "", "in_path": False}), \
         patch.object(cl, "is_debug_chrome_running", return_value={"running": False}), \
         patch("subprocess.Popen") as popen:
        result = cl.launch_chrome_debug(port=9331)
    assert result["status"] == "not_installed"
    assert "permission" in result["message"]
    popen.assert_not_called()


def test_already_running_short_circuits():
    with patch.object(cl, "is_debug_chrome_running",
                      return_value={"running": True, "browser": "Chrome/1", "ws_url": "ws://x"}), \
         patch.object(cl, "find_chrome") as find:
        result = cl.launch_chrome_debug(port=9331)
    assert result["status"] == "already_running"
    find.assert_not_called()


def test_launch_uses_debug_flags(tmp_path):
    captured = {}

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        proc = MagicMock()
        proc.pid = 4242
        return proc

    probes = iter([{"running": False}, {"running": True, "browser": "Chrome/1", "ws_url": "ws://y"}])
    with patch.object(cl, "find_chrome",
                      return_value={"found": True, "path": "/opt/chrome", "in_path": True}), \
         patch.object(cl, "is_debug_chrome_running", side_effect=lambda p: next(probes)), \
         patch("utils.subprocess_helper.popen_no_window", side_effect=fake_popen):
        result = cl.launch_chrome_debug(port=9331, user_data_dir=str(tmp_path / "prof"))
    assert result["status"] == "launched" and result["pid"] == 4242
    cmd = captured["cmd"]
    assert "--remote-debugging-port=9331" in cmd
    assert any(a.startswith("--user-data-dir=") for a in cmd)
    assert "--disable-features=SharedStorage,InterestCohort" in cmd


def test_install_skips_when_already_installed():
    with patch.object(cl, "find_chrome",
                      return_value={"found": True, "path": "/opt/chrome", "in_path": True}), \
         patch("urllib.request.urlretrieve") as dl:
        result = cl.install_chrome()
    assert result["status"] == "already_installed"
    dl.assert_not_called()


def test_add_to_path_updates_process_env(tmp_path, monkeypatch):
    chrome = tmp_path / "app" / "chrome"
    chrome.parent.mkdir(parents=True)
    chrome.write_text("x")
    monkeypatch.setenv("PATH", str(tmp_path))
    with patch.object(cl.platform, "system", return_value="Linux"), \
         patch("os.symlink") as ln, \
         patch("os.access", return_value=False):
        cl.add_chrome_to_path(str(chrome))
    import os
    assert str(chrome.parent) in os.environ["PATH"].split(os.pathsep)
    ln.assert_not_called()
