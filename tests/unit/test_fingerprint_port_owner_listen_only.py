"""Who serves a debug port: listening sockets only (alpha 2026-10-22, a 抖店
browser refused because a 拼多多 Chrome had an OUTGOING connection whose local
end used the same ephemeral port number)."""
import types

import psutil

from agent.ec_skills.browser_use_extension.fingerprint import fingerprint_browser as fb


def _conn(port, pid, status):
    return types.SimpleNamespace(laddr=types.SimpleNamespace(port=port), pid=pid, status=status)


def test_an_outgoing_connection_on_the_same_local_port_is_not_a_server(monkeypatch):
    conns = [_conn(63171, 22552, psutil.CONN_ESTABLISHED),     # pdd Chrome, outgoing
             _conn(63171, 30000, psutil.CONN_LISTEN)]          # the 抖店 Chrome we launched
    dirs = {22552: r"C:\ecan_browser_data\pdd_main_x", 30000: r"C:\ecan_browser_data\douyin_x"}
    monkeypatch.setattr(psutil, "net_connections", lambda kind="inet": conns)
    monkeypatch.setattr(psutil, "Process", lambda pid: types.SimpleNamespace(
        cmdline=lambda: ["chrome.exe", f"--user-data-dir={dirs[pid]}"]))
    assert fb._data_dirs_on_port(63171) == [(30000, dirs[30000])]
    assert fb._port_serves_profile(63171, dirs[30000]) is True
