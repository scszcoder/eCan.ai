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
    """The logged-in user's id, or None when not resolvable."""
    try:
        from app_context import AppContext

        login = AppContext.get_login()
        user = getattr(getattr(login, "auth_manager", None), "current_user", None)
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

        cmd = [
            sys.executable, "-m", "cli.main",
            "deploy", "scenario",
            "--config", str(cfg_path),
            "--output", str(res_path),
        ]
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
        proc = subprocess.run(
            cmd, cwd=str(PROJECT_ROOT),
            capture_output=True, text=True, timeout=_CLI_TIMEOUT_S,
            env=env,
        )

        result: Dict[str, Any] = {}
        if res_path.exists():
            try:
                with open(res_path, "r", encoding="utf-8") as f:
                    result = json.load(f)
            except Exception as e:
                logger.warning(f"[FastDeploy] could not read result file: {e}")

        status = result.get("status") or ("success" if proc.returncode == 0 else "failure")
        log = result.get("log") or []
        if not log and proc.stderr.strip():
            log = [proc.stderr.strip()]

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
