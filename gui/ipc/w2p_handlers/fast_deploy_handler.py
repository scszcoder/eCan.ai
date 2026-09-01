"""Fast Deploy IPC handler.

Backs the app's "Fast Deploy / 快速生成" panel: saves the scenario config to
a JSON file, then invokes the CLI (`ecan deploy scenario`) to generate the
related resources (agents, skills, tasks), and returns the structured result
so the panel can show a success/failure conclusion.

Requires a logged-in session — deliberately NOT in the IPC whitelist.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import (
    IPCRequest,
    IPCResponse,
    create_error_response,
    create_success_response,
)
from utils.logger_helper import logger_helper as logger

PROJECT_ROOT = Path(__file__).resolve().parents[3]

_CLI_TIMEOUT_S = 280


def _current_user_id() -> Optional[str]:
    """The logged-in user's id, or None when not resolvable.

    Prefer MainWindow.user — the @local-normalized identity every DB owner
    column and owner-scoped query uses. auth_manager.current_user can be the
    RAW id for new-flow WeChat logins (e.g. 'wechat_<openid>' without
    '@local'); deploying with that owner made the 9 agents invisible to
    get_agents_by_owner('...@local') on a customer machine (2026-09-01).
    """
    try:
        from app_context import AppContext

        mainwin = AppContext.get_main_window()
        mw_user = getattr(mainwin, "user", None) if mainwin else None
        if mw_user:
            return str(mw_user)
        login = AppContext.get_login()
        user = getattr(getattr(login, "auth_manager", None), "current_user", None)
        if user and "@" not in str(user):
            # Match MainWindow._init_user_environment's normalization.
            return f"{user}@local"
        return str(user) if user else None
    except Exception:
        return None


def _fast_deploy_dir() -> Path:
    """User-scoped config dir when resolvable, else a project resource dir."""
    try:
        from utils.user_path_helper import ensure_user_data_dir

        return Path(ensure_user_data_dir(_current_user_id() or "default", "fast_deploy"))
    except Exception:
        d = PROJECT_ROOT / "resource" / "fast_deploy_configs"
        d.mkdir(parents=True, exist_ok=True)
        return d


@IPCHandlerRegistry.handler("fast_deploy.generate")
def handle_fast_deploy_generate(request: IPCRequest,
                                params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Save the scenario config and run the resource-generation CLI."""
    try:
        params = params or {}
        scenario = str(params.get("scenario") or "").strip()
        config = params.get("config") or {}
        if not scenario:
            return create_error_response(request, "INVALID_PARAMS", "scenario is required")
        if not isinstance(config, dict) or not config.get("store_urls"):
            return create_error_response(request, "INVALID_PARAMS", "config.store_urls is required")

        out_dir = _fast_deploy_dir()
        ts = time.strftime("%Y%m%d-%H%M%S")
        cfg_path = out_dir / f"{scenario}-{ts}.json"
        res_path = out_dir / f"{scenario}-{ts}.result.json"

        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump({"scenario": scenario, "config": config}, f, ensure_ascii=False, indent=2)
        logger.info(f"[FastDeploy] wrote config {cfg_path}")

        cli_args = ["deploy", "scenario", "--config", str(cfg_path), "--output", str(res_path)]
        if getattr(sys, "frozen", False):
            # Packaged app: sys.executable is the GUI exe, not Python —
            # `-m cli.main` would just launch a second app instance that
            # exits 0 having done nothing (v0.9.95o customer incident:
            # panel showed success, nothing generated). Use the same
            # ECAN_RUN_SCRIPT worker mechanism as the LightRAG server:
            # the exe executes the script instead of booting the GUI.
            runner_path = out_dir / f"{scenario}-{ts}.runner.py"
            runner_path.write_text(
                "import sys\n"
                f"sys.argv = {json.dumps(['ecan'] + cli_args)}\n"
                "from cli.main import main\n"
                "main()\n"
                "sys.exit(0)\n",
                encoding="utf-8",
            )
            cmd = [sys.executable]
        else:
            runner_path = None
            cmd = [sys.executable, "-m", "cli.main"] + cli_args
        # Scope the CLI subprocess to the logged-in user so real deployments
        # land in that user's DB with the correct owner (the CLI has no session
        # file of its own — it reads ECAN_CLI_USER; see CLIContext.username).
        env = dict(os.environ)
        uid = _current_user_id()
        if uid:
            env["ECAN_CLI_USER"] = uid
            env["ECAN_DEPLOY_OWNER"] = uid
        # Per-user data dirs (my_prompts etc.) are keyed by MainWindow.log_user,
        # not the raw username — pass it so the CLI validates against the same
        # system prompt/skill lists the running app loaded at initialization.
        try:
            from app_context import AppContext
            log_user = getattr(AppContext.get_main_window(), "log_user", None)
            if log_user:
                env["ECAN_LOG_USER"] = str(log_user)
        except Exception:
            pass
        # Auth token for the CLI's cloud fallbacks (e.g. prompt-visibility
        # check for prompts not yet in the local stores).
        try:
            from app_context import AppContext
            token = AppContext.get_main_window().get_auth_token()
            if token:
                env["ECAN_CLI_AUTH_TOKEN"] = str(token)
        except Exception:
            pass
        if runner_path is not None:
            env["ECAN_RUN_SCRIPT"] = str(runner_path)
        proc = subprocess.run(
            cmd, cwd=str(PROJECT_ROOT),
            capture_output=True, text=True, timeout=_CLI_TIMEOUT_S,
            env=env,
        )
        logger.info(
            f"[FastDeploy] CLI exited rc={proc.returncode} "
            f"(mode={'frozen-run-script' if runner_path else 'python -m'}); "
            f"stderr tail: {(proc.stderr or '').strip()[-300:] or '(empty)'}"
        )

        result: Dict[str, Any] = {}
        if res_path.exists():
            try:
                with open(res_path, "r", encoding="utf-8") as f:
                    result = json.load(f)
            except Exception as e:
                logger.warning(f"[FastDeploy] could not read result file: {e}")
        else:
            logger.warning(f"[FastDeploy] no result file at {res_path} — CLI did not complete")

        # Success requires an actual result file — a 0 exit code alone is not
        # proof of work (a mislaunched child can exit 0 having done nothing).
        if result:
            status = result.get("status") or ("success" if proc.returncode == 0 else "failure")
        else:
            status = "failure"
        log = result.get("log") or []
        if not log and proc.stderr.strip():
            log = [proc.stderr.strip()]
        if not result and not log:
            log = ["Resource generation did not produce a result — see eCan.log for the CLI error."]

        return create_success_response(request, {
            "status": status,
            "scenario": scenario,
            "config_path": str(cfg_path),
            "plan": result.get("plan"),
            "log": log,
            "message": result.get("message") or "",
        })
    except subprocess.TimeoutExpired:
        logger.error("[FastDeploy] CLI timed out")
        return create_error_response(request, "TIMEOUT", "Resource generation timed out")
    except Exception as e:
        logger.error(f"[FastDeploy] error: {e}")
        return create_error_response(request, "FAST_DEPLOY_ERROR", str(e))
