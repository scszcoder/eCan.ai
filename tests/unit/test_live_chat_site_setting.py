"""Settings switch: which live-chat platform this machine serves, saved to run.env."""

import os
from unittest.mock import patch

import pytest

from utils import run_env


@pytest.fixture
def home(tmp_path):
    with patch("config.envi.getECBotDataHome", return_value=str(tmp_path)):
        yield tmp_path


def test_set_replaces_and_keeps_other_lines(home):
    (home / "run.env").write_text("A=1\nECAN_LIVE_CHAT_SITE=feige_chat\nB=2\n", encoding="utf-8")
    run_env.set_value("ECAN_LIVE_CHAT_SITE", "pdd_chat")
    assert (home / "run.env").read_text(encoding="utf-8") == "A=1\nECAN_LIVE_CHAT_SITE=pdd_chat\nB=2\n"
    assert run_env.read_value("ECAN_LIVE_CHAT_SITE") == "pdd_chat"


def test_empty_removes_the_key(home):
    (home / "run.env").write_text("ECAN_LIVE_CHAT_SITE=pdd_chat\nB=2\n", encoding="utf-8")
    run_env.set_value("ECAN_LIVE_CHAT_SITE", None)
    assert (home / "run.env").read_text(encoding="utf-8") == "B=2\n"
    assert run_env.read_value("ECAN_LIVE_CHAT_SITE") is None


def test_missing_file_is_created(home):
    run_env.set_value("ECAN_LIVE_CHAT_SITE", "pdd_chat")
    assert run_env.read_value("ECAN_LIVE_CHAT_SITE") == "pdd_chat"


def test_handler_saves_and_flags_restart(home):
    from gui.ipc.w2p_handlers import live_chat_site_handler as h
    req = {"id": "1", "method": "live_chat_site.set", "params": {}}
    with patch.dict(os.environ, {"ECAN_LIVE_CHAT_SITE": ""}):
        res = h.handle_set(req, {"site": "pdd_chat"})
        data = res["result"] if isinstance(res, dict) and "result" in res else getattr(res, "result", None)
        assert run_env.read_value("ECAN_LIVE_CHAT_SITE") == "pdd_chat"
        assert data["site"] == "pdd_chat" and data["restart_needed"] is True
        h.handle_set(req, {"site": ""})
        assert run_env.read_value("ECAN_LIVE_CHAT_SITE") is None


def test_handler_refuses_unknown_sites(home):
    from gui.ipc.w2p_handlers import live_chat_site_handler as h
    req = {"id": "1", "method": "live_chat_site.set", "params": {}}
    h.handle_set(req, {"site": "evil; rm"})
    assert not (home / "run.env").exists()
