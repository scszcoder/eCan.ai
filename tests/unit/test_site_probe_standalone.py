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
