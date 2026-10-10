"""FastDeploy CLI launch in packaged builds (v0.9.95o incident).

In the frozen app ``sys.executable`` is the GUI exe — ``-m cli.main``
launched a SECOND app instance that exited 0 having done nothing, and
the handler reported success (0 exit + no result file). Now: frozen
builds launch the exe with ECAN_RUN_SCRIPT pointing at a generated
runner that invokes cli.main directly, and success REQUIRES a result
file — exit code 0 alone is a failure.
"""

import json
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import gui.ipc.w2p_handlers.fast_deploy_handler as fd


def _run_handler(tmp_path, frozen, write_result=None):
    captured = {}

    def fake_run(cmd, cwd=None, capture_output=None, text=None, timeout=None, env=None):
        captured["cmd"] = cmd
        captured["env"] = env
        if write_result is not None:
            for p in tmp_path.glob("douyin_cs-*.result.json"):
                p.unlink()
            res = next(tmp_path.glob("douyin_cs-*.json"), None)
            # result path mirrors the config path naming
            res_path = str(res).replace(".json", ".result.json")
            with open(res_path, "w", encoding="utf-8") as f:
                json.dump(write_result, f)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    resp_holder = {}
    with patch.object(fd, "_fast_deploy_dir", return_value=tmp_path), \
         patch.object(fd, "_current_user_id", return_value="u@x"), \
         patch.object(fd.subprocess, "run", side_effect=fake_run), \
         patch.object(fd.sys, "frozen", frozen, create=True), \
         patch.object(fd, "create_success_response",
                      side_effect=lambda req, data: resp_holder.update(data) or resp_holder), \
         patch.object(fd, "create_error_response",
                      side_effect=lambda req, code, msg: {"error": code, "message": msg}):
        fd.handle_fast_deploy_generate(
            MagicMock(), {"scenario": "douyin_cs", "config": {"store_urls": ["https://x"]}}
        )
    return resp_holder, captured


class TestCliUserPrecedence:
    """ECAN_CLI_USER (set by the app for its subprocess) must beat a stale
    .ecan_session.json — deep-trace 2026-08-27: an old `ecan auth login`
    session silently redirected the deploy into a different user's DB."""

    def test_env_beats_stale_session(self, tmp_path, monkeypatch):
        from cli.base.context import CLIContext
        (tmp_path / ".ecan_session.json").write_text(
            '{"username": "old-login@stale"}', encoding="utf-8")
        monkeypatch.setenv("ECAN_CLI_USER", "current@app")
        ctx = CLIContext(project_root=tmp_path)
        assert ctx.username == "current@app"

    def test_session_used_when_no_env(self, tmp_path, monkeypatch):
        from cli.base.context import CLIContext
        (tmp_path / ".ecan_session.json").write_text(
            '{"username": "logged-in@cli"}', encoding="utf-8")
        monkeypatch.delenv("ECAN_CLI_USER", raising=False)
        ctx = CLIContext(project_root=tmp_path)
        assert ctx.username == "logged-in@cli"


class TestFrozenLaunch:
    def test_frozen_uses_run_script_mechanism(self, tmp_path):
        resp, cap = _run_handler(tmp_path, frozen=True,
                                 write_result={"status": "success", "plan": {"agents": 7}})
        assert cap["cmd"] == [sys.executable]  # no -m cli.main against the exe
        runner = cap["env"].get("ECAN_RUN_SCRIPT")
        assert runner and runner.endswith(".runner.py")
        src = open(runner, encoding="utf-8").read()
        assert "from cli.main import main" in src
        assert "deploy" in src and "scenario" in src
        assert "sys.exit(0)" in src  # must not fall through into the GUI boot
        assert resp["status"] == "success"

    def test_dev_mode_uses_python_dash_m(self, tmp_path):
        resp, cap = _run_handler(tmp_path, frozen=False,
                                 write_result={"status": "success"})
        assert cap["cmd"][:3] == [sys.executable, "-m", "cli.main"]
        assert "ECAN_RUN_SCRIPT" not in (cap["env"] or {})
        assert resp["status"] == "success"

    def test_no_result_file_is_failure_even_with_rc0(self, tmp_path):
        """The exact 95o symptom: child exits 0, no result file → must NOT
        report success."""
        resp, _ = _run_handler(tmp_path, frozen=True, write_result=None)
        assert resp["status"] == "failure"
        assert resp["log"]  # actionable hint surfaced to the panel


class TestNewStoreViaCli:
    """Fast Deploy 2026-10-10: a store picked as "new store" is created with
    `ecan stores create` before the scenario deploy runs."""

    def _call(self, tmp_path, config, create_rc=0):
        calls = []

        def fake_run(cmd, cwd=None, capture_output=None, text=None, timeout=None, env=None):
            calls.append(cmd)
            if "stores" in cmd:
                return SimpleNamespace(returncode=create_rc, stdout="",
                                       stderr="" if create_rc == 0 else "Error: store exists")
            res = next(p for p in tmp_path.glob("douyin_cs-*.json") if not p.name.endswith(".result.json"))
            with open(str(res).replace(".json", ".result.json"), "w", encoding="utf-8") as f:
                json.dump({"status": "success", "log": ["deployed"]}, f)
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        out = {}
        with patch.object(fd, "_fast_deploy_dir", return_value=tmp_path), \
             patch.object(fd, "_current_user_id", return_value="u@x"), \
             patch.object(fd.subprocess, "run", side_effect=fake_run), \
             patch.object(fd.sys, "frozen", False, create=True), \
             patch.object(fd, "create_success_response", side_effect=lambda req, data: out.update(data) or out), \
             patch.object(fd, "create_error_response", side_effect=lambda req, code, msg: {"error": code}):
            fd.handle_fast_deploy_generate(MagicMock(), {"scenario": "douyin_cs", "config": config})
        return out, calls

    def test_new_store_is_created_first(self, tmp_path):
        out, calls = self._call(tmp_path, {"store_id": "douyin-小店", "qa_agents": 2,
                                           "new_store": {"name": "小店", "platform": "douyin", "urls": []}})
        assert calls[0][-8:] == ["stores", "create", "--id", "douyin-小店", "--name", "小店", "--platform", "douyin"]
        assert calls[1][-6:-4] == ["deploy", "scenario"]
        assert out["status"] == "success" and out["store_created"] is True
        saved = json.loads(next(p for p in tmp_path.glob("douyin_cs-*.json")
                                if not p.name.endswith(".result.json")).read_text(encoding="utf-8"))
        assert "new_store" not in saved["config"]          # the deploy sees only its own config

    def test_failed_create_stops_before_deploy(self, tmp_path):
        out, calls = self._call(tmp_path, {"store_id": "douyin-小店",
                                           "new_store": {"name": "小店", "platform": "douyin"}}, create_rc=1)
        assert len(calls) == 1 and out["status"] == "failure" and "store exists" in out["message"]

    def test_edited_url_of_existing_store_is_saved(self, tmp_path):
        out, calls = self._call(tmp_path, {"store_id": "douyin-a", "store_url": "https://x.example"})
        assert calls[0][-5:] == ["stores", "update", "douyin-a", "--url", "https://x.example"]
        assert out["store_url_saved"] is True
