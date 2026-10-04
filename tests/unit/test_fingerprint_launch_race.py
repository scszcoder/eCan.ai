"""Two profiles launched at the same moment on the same requested CDP port.

Customer run 99r: the PDD and Douyin front desks both asked for 9228 and started
together. Both saw the port free, both started Chromium on it, each then found
the OTHER browser answering, refused it and terminated its own -- both windows
closed ("Chrome 闪退") and neither agent got a browser. Launches are serialized
now, so the second one finds 9228 taken and steps aside to a free port.
"""

import itertools
import sys
import threading
import time

import pytest

from agent.ec_skills.browser_use_extension.fingerprint import (
    fingerprint_browser as fb,
    profile_registry as reg,
)


@pytest.fixture
def two_profiles(tmp_path, monkeypatch):
    monkeypatch.setattr(reg, "_registry_path", lambda: tmp_path / "browser_profiles.json")
    monkeypatch.setenv("ECAN_BROWSER_DATA_ROOT", str(tmp_path / "data"))

    class _Keyring:
        store = {}
        def set_password(self, s, a, p): self.store[(s, a)] = p
        def get_password(self, s, a): return self.store.get((s, a))
        def delete_password(self, s, a): self.store.pop((s, a), None)

    monkeypatch.setitem(sys.modules, "keyring", _Keyring())
    for pid in ("pdd_main", "douyin_login"):
        reg.save_profile(reg.make_profile(pid))
    monkeypatch.setattr(fb, "_RUNNING", {})
    return {pid: reg.get_profile(pid)["user_data_dir"] for pid in ("pdd_main", "douyin_login")}


def _fake_machine(monkeypatch, startup_s=0.3):
    """Ports bind only once a fake Chromium has started; the first one to bind wins."""
    owner = {}                         # port -> user_data_dir of the browser serving it
    lock = threading.Lock()
    free_ports = itertools.count(50000)
    terminated = []

    monkeypatch.setattr(fb, "_running_browser_for", lambda udd: None)
    monkeypatch.setattr(fb, "resolve_browser_path", lambda p: "chrome.exe")
    monkeypatch.setattr(fb, "_proxy_flags", lambda p: ([], None, None))
    monkeypatch.setattr(fb, "_free_port", lambda: next(free_ports))
    monkeypatch.setattr(fb, "_port_open", lambda port, timeout=1.0: port in owner)
    monkeypatch.setattr(fb, "_cdp_version",
                        lambda port, timeout=1.0: {"Browser": "Chrome/1"} if port in owner else None)
    monkeypatch.setattr(fb, "_port_serves_profile", lambda port, udd: owner.get(port) == str(udd))

    class _Proc:
        def __init__(self, port, udd):
            self.pid, self.port, self.udd = 1000 + port % 1000, port, udd
            def _start():
                time.sleep(startup_s)
                with lock:
                    owner.setdefault(port, udd)
            threading.Thread(target=_start, daemon=True).start()
        def poll(self): return None
        def terminate(self): terminated.append(self.udd)

    def _popen(argv, **kw):
        port = int(next(a for a in argv if a.startswith("--remote-debugging-port=")).split("=")[1])
        udd = next(a for a in argv if a.startswith("--user-data-dir=")).split("=", 1)[1]
        return _Proc(port, udd)

    monkeypatch.setattr(fb.subprocess, "Popen", _popen)
    return terminated


def test_two_front_desks_starting_together_both_get_a_browser(two_profiles, monkeypatch):
    terminated = _fake_machine(monkeypatch)
    results, errors = {}, {}

    def _launch(pid):
        try:
            results[pid] = fb.launch_profile(pid, debug_port=9228, timeout=5)
        except Exception as e:          # the 99r failure: "served by a different browser"
            errors[pid] = e

    threads = [threading.Thread(target=_launch, args=(p,)) for p in two_profiles]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)

    assert not errors, errors
    assert not terminated, "no browser window may be closed"
    ports = {results[p].debug_port for p in two_profiles}
    assert len(ports) == 2 and 9228 in ports
