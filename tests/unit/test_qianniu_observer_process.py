"""千牛 observer: which AliWorkbench process it scans.

0.9.99x alpha: the observer scanned "the first AliWorkbench.exe" -- the CHILD
process -- for 8 hours and never saw a message. The process table below is the
real one from probe run 2026-09-30 (run_20260930_130917_cc24): every chat hit
was in the parent pid 12040, none in its child 9320.
"""
from types import SimpleNamespace
from unittest.mock import patch

from agent.ec_skills.browser_use_extension.hooks.external.qianniu_chat import observer

_PROBE_TABLE = [
    {"pid": 1748, "ppid": 12040, "name": "AliRender.exe"},
    {"pid": 6132, "ppid": 12040, "name": "AliRender.exe"},
    {"pid": 7268, "ppid": 1, "name": "explorer.exe"},
    {"pid": 9320, "ppid": 12040, "name": "AliWorkbench.exe"},
    {"pid": 12040, "ppid": 7268, "name": "AliWorkbench.exe"},
]


def _procs(table):
    return [SimpleNamespace(info=dict(r)) for r in table]


def test_root_aliworkbench_comes_first_although_the_child_has_the_lower_pid():
    with patch("psutil.process_iter", return_value=_procs(_PROBE_TABLE)):
        assert observer._qianniu_pids() == [12040, 9320]


def test_no_qianniu_running():
    with patch("psutil.process_iter", return_value=_procs(_PROBE_TABLE[:3])):
        assert observer._qianniu_pids() == []


def test_scan_pass_finds_the_message_process_and_sticks_to_it():
    obs = observer.QianniuMemObserver(dispatch_fn=lambda item: 0)
    scanned = []

    def fake_scan(pid):
        scanned.append(pid)
        return pid == 9320          # messages here this time (e.g. another 千牛 build)

    with patch("psutil.process_iter", return_value=_procs(_PROBE_TABLE)), \
            patch.object(obs, "_scan_once", side_effect=fake_scan):
        obs._scan_pass()
        assert scanned == [12040, 9320] and obs._hit_pid == 9320   # root tried first, falls back
        scanned.clear()
        obs._scan_pass()
        assert scanned == [9320]                                   # then the hit process only


def test_scan_pass_stops_at_the_root_when_it_holds_messages():
    obs = observer.QianniuMemObserver(dispatch_fn=lambda item: 0)
    scanned = []
    with patch("psutil.process_iter", return_value=_procs(_PROBE_TABLE)), \
            patch.object(obs, "_scan_once", side_effect=lambda pid: scanned.append(pid) or pid == 12040):
        obs._scan_pass()
    assert scanned == [12040] and obs._hit_pid == 12040 and obs._pids == [12040, 9320]
