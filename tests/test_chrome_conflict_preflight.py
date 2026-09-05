"""Two-Chrome-trap preflight: warn (never block) when eCan is about to drive a
blank debug Chrome while the customer's real Chrome is a separate window."""

from unittest.mock import patch

import gui.unified_browser_manager as ubm


def _targets(*urls):
    return [{"type": "page", "url": u} for u in urls]


def test_blank_debug_chrome_plus_other_chrome_is_a_trap():
    with patch.object(ubm, "_list_chrome_browser_processes",
                      return_value=[{"pid": 100, "port": 9228}, {"pid": 200, "port": None}]), \
         patch.object(ubm, "_debug_chrome_targets", return_value=_targets("about:blank")), \
         patch.object(ubm._agent_status, "report") as report:
        r = ubm.preflight_chrome_conflict(9228, auto_started=False)
    assert r["trap"] is True
    assert 200 in r["other_pids"]
    assert r["our_blank"] is True
    report.assert_called_once()
    assert report.call_args.kwargs.get("chrome") == "conflict"


def test_debug_chrome_with_store_page_is_not_a_trap():
    with patch.object(ubm, "_list_chrome_browser_processes",
                      return_value=[{"pid": 100, "port": 9228}, {"pid": 200, "port": None}]), \
         patch.object(ubm, "_debug_chrome_targets",
                      return_value=_targets("https://im.jinritemai.com/pc_seller_v2/")), \
         patch.object(ubm._agent_status, "report") as report:
        r = ubm.preflight_chrome_conflict(9228)
    assert r["trap"] is False
    report.assert_not_called()


def test_auto_started_with_other_chrome_running_is_a_trap():
    # We just launched our own blank Chrome; another Chrome already existed.
    with patch.object(ubm, "_list_chrome_browser_processes",
                      return_value=[{"pid": 100, "port": 9228}, {"pid": 200, "port": None}]), \
         patch.object(ubm, "_debug_chrome_targets", return_value=None), \
         patch.object(ubm._agent_status, "report") as report:
        r = ubm.preflight_chrome_conflict(9228, auto_started=True)
    assert r["trap"] is True
    report.assert_called_once()


def test_single_debug_chrome_no_others_is_clean():
    with patch.object(ubm, "_list_chrome_browser_processes",
                      return_value=[{"pid": 100, "port": 9228}]), \
         patch.object(ubm, "_debug_chrome_targets", return_value=_targets("about:blank")), \
         patch.object(ubm._agent_status, "report") as report:
        r = ubm.preflight_chrome_conflict(9228, auto_started=True)
    assert r["trap"] is False
    report.assert_not_called()


def test_child_processes_are_ignored_when_listing():
    class _P:
        def __init__(self, pid, name, cmd):
            self.pid = pid
            self.info = {"name": name}
            self._cmd = cmd

        def cmdline(self):
            return self._cmd

    procs = [
        _P(1, "chrome.exe", ["chrome.exe", "--remote-debugging-port=9228"]),
        _P(2, "chrome.exe", ["chrome.exe", "--type=renderer", "--remote-debugging-port=9228"]),
        _P(3, "chrome.exe", ["chrome.exe"]),  # customer's normal browser
    ]
    fake_psutil = type("M", (), {"process_iter": staticmethod(lambda attrs=None: procs)})
    with patch.dict("sys.modules", {"psutil": fake_psutil}):
        got = ubm._list_chrome_browser_processes()
    pids = {p["pid"] for p in got}
    assert pids == {1, 3}  # renderer child (pid 2) excluded
    assert next(p for p in got if p["pid"] == 1)["port"] == 9228
    assert next(p for p in got if p["pid"] == 3)["port"] is None
