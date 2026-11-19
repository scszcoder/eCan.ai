"""A store browser opens on screen even when the app itself was started hidden:
Windows passes the parent's show-window state on to the browser it launches."""
import os
import subprocess

import pytest

from agent.ec_skills.browser_use_extension.fingerprint import fingerprint_browser as fb


@pytest.mark.skipif(os.name != "nt", reason="Windows show-window state")
def test_windowed_launch_asks_for_a_normal_window():
    si = fb._visible_window_startupinfo(headless=False)
    assert si.dwFlags & subprocess.STARTF_USESHOWWINDOW
    assert si.wShowWindow == 1


def test_headless_launch_needs_no_window():
    assert fb._visible_window_startupinfo(headless=True) is None
