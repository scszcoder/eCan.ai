"""A Chrome left behind by an exited app owns its profile with no lock file on
Windows; a new launch on that user-data-dir then times out. The cleaner must
find the owner by its command line, kill it only when orphaned, and never touch
a browser on another profile."""
import os
from unittest.mock import patch

import psutil

from agent.ec_skills.browser_use_extension import profile_lock_cleaner as plc

PROFILE = r"C:\data\browser_profiles\default"


class FakeProc:
    def __init__(self, pid, name, cmd, parent=None, created=100.0):
        self.pid, self.info = pid, {"name": name}
        self._cmd, self._parent, self._created = cmd, parent, created
        self.killed = False

    def cmdline(self):
        return self._cmd

    def parent(self):
        return self._parent

    def create_time(self):
        return self._created

    def children(self, recursive=False):
        return []

    def kill(self):
        self.killed = True


def _chrome(pid, profile, parent=None, extra=(), created=100.0):
    return FakeProc(pid, "chrome.exe",
                    ["chrome.exe", *extra, f"--user-data-dir={profile}"], parent, created)


def _run(procs):
    with patch.object(psutil, "process_iter", return_value=procs), \
         patch.object(psutil, "wait_procs", return_value=([], [])):
        return plc.reclaim_orphaned_profile(PROFILE)


def test_user_data_dir_is_read_in_both_cli_forms():
    assert plc._cmdline_user_data_dir(["c", "--user-data-dir=X"]) == "X"
    assert plc._cmdline_user_data_dir(["c", "--user-data-dir", "Y"]) == "Y"
    assert plc._cmdline_user_data_dir(["c", "--foo"]) is None


def test_an_orphaned_owner_is_killed():
    orphan = _chrome(1, PROFILE, parent=None)
    out = _run([orphan])
    assert orphan.killed and out == {"orphans_killed": [1], "live_owners": []}


def test_a_reused_parent_pid_still_counts_as_orphaned():
    newer = FakeProc(9, "explorer.exe", [], created=500.0)  # started after the browser
    orphan = _chrome(2, PROFILE, parent=newer, created=100.0)
    assert _run([orphan])["orphans_killed"] == [2]


def test_a_browser_with_a_live_parent_is_left_alone_and_reported():
    app = FakeProc(9, "python.exe", [], created=50.0)
    live = _chrome(3, PROFILE, parent=app, created=100.0)
    out = _run([live])
    assert not live.killed and out == {"orphans_killed": [], "live_owners": [3]}


def test_other_profiles_renderers_and_non_chrome_are_never_touched():
    personal = _chrome(4, r"C:\Users\me\AppData\Local\Google\Chrome\User Data")
    renderer = _chrome(5, PROFILE, extra=("--type=renderer",))
    other = FakeProc(6, "python.exe", ["python.exe", f"--user-data-dir={PROFILE}"])
    out = _run([personal, renderer, other])
    assert out == {"orphans_killed": [], "live_owners": []}
    assert not (personal.killed or renderer.killed or other.killed)


def test_path_match_ignores_quotes_and_on_windows_case():
    assert _run([_chrome(7, f'"{PROFILE}"')])["orphans_killed"] == [7]
    if os.name == "nt":  # Windows paths are case-insensitive; normcase folds them
        assert _run([_chrome(8, PROFILE.upper())])["orphans_killed"] == [8]
