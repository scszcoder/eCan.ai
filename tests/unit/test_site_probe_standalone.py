"""The standalone site probe: site presets, Taobao redaction, the desktop-app restart guard."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
sp = pytest.importorskip("site_probe_standalone")


def test_the_exe_name_picks_the_site(monkeypatch):
    monkeypatch.setattr(sys, "argv", [r"C:\x\qianniu_probe.exe"])
    assert sp._site_from_name() == "qianniu"
    monkeypatch.setattr(sys, "argv", ["pdd_probe.exe"])
    assert sp._site_from_name() == "pdd"
    monkeypatch.setattr(sys, "argv", ["site_probe_standalone.py"])
    assert sp._site_from_name() == "pdd", "unchanged default"


def test_taobao_signing_headers_and_tokens_are_redacted():
    h = sp.redact_headers({"x-sign": "abc", "bx-ua": "u", "Cookie": "_m_h5_tk=1", "accept": "json"})
    assert h["accept"] == "json" and all(v.startswith("<redacted") for k, v in h.items() if k != "accept")
    url = sp.redact_url("https://h5api.m.taobao.com/h5/mtop.x/1.0/?appKey=12574478&t=1&sign=ff&_m_h5_tk=zz")
    assert "sign=redacted" in url and "_m_h5_tk=redacted" in url and "t=1" in url


def test_the_restart_never_targets_the_probe_itself(monkeypatch):
    monkeypatch.setattr(sp, "_processes", lambda: [("qianniu_probe", 1, "p"), ("AliWorkBench", 2, "a.exe"),
                                                    ("chrome", 3, "c")])
    assert sp._app_procs("qianniu") == [("AliWorkBench", 2, "a.exe")]


def test_analytics_beacon_frames_are_skipped_but_chat_frames_kept(tmp_path):
    p = sp.Probe(0, ["taobao.com"], ["taobao.com"], str(tmp_path), ignore_ws=["mmstat.com"])
    p.ws_url.update({"1": "wss://ws.mmstat.com/ws", "2": "wss://wss.taobao.com/im"})
    for rid in ("1", "2"):
        p.on_event("Network.webSocketFrameReceived", {"requestId": rid, "response": {"opcode": 1,
                                                                                    "payloadData": "{}"}}, "s")
    p.fp.close()
    frames = [json.loads(l) for l in open(p.path, encoding="utf-8") if '"ws_frame"' in l]
    assert [f["url"] for f in frames] == ["wss://wss.taobao.com/im"] and p.stats["ws_ignored"] == 1


def test_desktop_app_mode_attaches_every_app_page(tmp_path):
    p = sp.Probe(0, [], [], str(tmp_path))
    assert p.wanted("https://qn.taobao.com/x") and p.wanted("file:///C:/app/index.html")
    assert not p.wanted("devtools://devtools/bundled/inspector.html")
    p.fp.close()


# --- desktop-client diagnosis ------------------------------------------------

def test_install_scan_names_the_web_runtime(tmp_path):
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "libcef.dll").write_bytes(b"x")
    (tmp_path / "WebView2Loader.dll").write_bytes(b"x")
    exe = tmp_path / "AliWorkBench.exe"
    exe.write_bytes(b"x")
    got = sp._scan_install(str(exe))
    assert got["runtimes"] == ["cef", "webview2"]


def test_app_tree_includes_child_processes_but_not_the_probe():
    table = [{"name": "AliWorkBench.exe", "pid": 10, "ppid": 1, "path": "a", "cmd": ""},
             {"name": "msedgewebview2.exe", "pid": 11, "ppid": 10, "path": "w", "cmd": "--type=renderer"},
             {"name": "qianniu_probe.exe", "pid": 12, "ppid": 1, "path": "p", "cmd": ""},
             {"name": "chrome.exe", "pid": 13, "ppid": 1, "path": "c", "cmd": ""}]
    assert [r["pid"] for r in sp._app_tree("qianniu", table)] == [10, 11]


def test_diagnosis_tries_the_inner_exe_then_webview2_env(monkeypatch, tmp_path):
    launcher, inner = str(tmp_path / "AliWorkBench.exe"), str(tmp_path / "bin" / "qn_main.exe")
    started, state = [], {"open": False}
    monkeypatch.setattr(sp, "_process_table", lambda: [])
    monkeypatch.setattr(sp, "_scan_install", lambda exe: {"root": "", "runtimes": ["webview2"], "markers": {}})
    monkeypatch.setattr(sp, "_kill_tree", lambda site: None)
    monkeypatch.setattr(sp, "_listening_ports", lambda pids: [])
    monkeypatch.setattr(sp.time, "sleep", lambda s: None)
    monkeypatch.setattr(sp, "_app_tree", lambda site, table=None: [
        {"name": "AliWorkBench.exe", "pid": 1, "ppid": 0, "path": launcher, "cmd": launcher},
        {"name": "qn_main.exe", "pid": 2, "ppid": 1, "path": inner, "cmd": inner}] if started else [])
    monkeypatch.setattr(sp, "cdp_up", lambda port, timeout=1.5: {"Browser": "Edg/1"} if state["open"] else None)

    class Popen:
        def __init__(self, argv, env=None):
            started.append((argv[0], "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS" in (env or {})))
            state["open"] = bool(env and "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS" in env)
    monkeypatch.setattr(sp.subprocess, "Popen", Popen)
    port, report = sp.diagnose_app("qianniu", 9228, launcher, wait_s=6)
    assert port == 9228 and report["verdict"] == "OPEN:webview2_env:9228"
    assert [a["label"] for a in report["attempts"]] == ["flag", "inner_exe_flag", "webview2_env"]
    assert started[1] == (inner, False)
