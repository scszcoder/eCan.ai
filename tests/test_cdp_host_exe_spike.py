"""ECAN_CDP_HOST_EXE: launch an Electron/Chromium-shell app with the CDP switch
instead of Google Chrome (spike for attaching to a vendor desktop workbench)."""

import os
from unittest.mock import patch

import gui.unified_browser_manager as ubm


def test_unset_env_means_no_host(monkeypatch):
    monkeypatch.delenv(ubm._CDP_HOST_EXE_ENV, raising=False)
    assert ubm._resolve_cdp_host_exe() is None


def test_full_path_is_used_verbatim(monkeypatch, tmp_path):
    exe = tmp_path / "Workbench.exe"
    exe.write_bytes(b"MZ")
    monkeypatch.setenv(ubm._CDP_HOST_EXE_ENV, f'"{exe}"')
    assert ubm._resolve_cdp_host_exe() == str(exe)


def test_host_app_launched_with_only_the_debug_switch(monkeypatch, tmp_path):
    exe = tmp_path / "Workbench.exe"
    exe.write_bytes(b"MZ")
    monkeypatch.setenv(ubm._CDP_HOST_EXE_ENV, str(exe))

    class _Proc:
        returncode = None

        def poll(self):
            return None

    popen_calls = []

    def _popen(args, **kw):
        popen_calls.append((args, kw))
        return _Proc()

    port_probe = iter([False, False, True])  # pre-check, first wait tick, ready
    with patch.object(ubm, "_is_port_in_use", side_effect=lambda p: next(port_probe)), \
         patch.object(ubm, "_kill_running_host_app") as kill, \
         patch.object(ubm, "_log_cdp_targets") as log_targets, \
         patch("subprocess.Popen", side_effect=_popen), \
         patch("threading.Timer") as timer, \
         patch("time.sleep"):
        assert ubm._start_chrome_with_cdp(9333) is True

    kill.assert_called_once_with(str(exe), 9333)
    args, kw = popen_calls[0]
    assert args == [str(exe), "--remote-debugging-port=9333"]
    assert not any("--user-data-dir" in a or "--profile-directory" in a for a in args)
    assert kw["cwd"] == str(tmp_path)
    log_targets.assert_called_once_with(9333)
    timer.assert_called_once()
    assert ubm._chrome_processes[9333] is not None


def test_host_app_exit_before_port_is_a_verdict(monkeypatch, tmp_path, caplog):
    exe = tmp_path / "Workbench.exe"
    exe.write_bytes(b"MZ")
    monkeypatch.setenv(ubm._CDP_HOST_EXE_ENV, str(exe))

    class _Dead:
        returncode = 1

        def poll(self):
            return 1

    with patch.object(ubm, "_is_port_in_use", return_value=False), \
         patch.object(ubm, "_kill_running_host_app"), \
         patch("subprocess.Popen", return_value=_Dead()), \
         patch("time.sleep"):
        assert ubm._start_chrome_with_cdp(9333) is False


def test_chrome_path_untouched_when_env_unset(monkeypatch):
    monkeypatch.delenv(ubm._CDP_HOST_EXE_ENV, raising=False)
    with patch.object(ubm, "_is_port_in_use", return_value=False), \
         patch.object(ubm, "_start_cdp_host_app") as host, \
         patch("os.path.exists", return_value=False):
        # No Chrome found on this fake filesystem -> False, but the host
        # branch must never have been consulted.
        assert ubm._start_chrome_with_cdp(9334) is False
    host.assert_not_called()
