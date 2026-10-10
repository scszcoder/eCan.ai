"""Fast Deploy IPC handler.

Backs the app's "Fast Deploy / 快速生成" panel: saves the scenario config to
a JSON file, then invokes the CLI (`ecan deploy scenario`) to generate the
related resources (agents, skills, tasks), and returns the structured result
so the panel can show a success/failure conclusion. A store new to the
catalog is created first with `ecan stores create` (an edited URL of an
existing store is saved with `ecan stores update`).

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


def _tr(en: str, zh: str) -> str:
    """Panel-facing error text in the app's language (Chinese on the CN build)."""
    try:
        from utils.app_env import is_cn
        return zh if is_cn() else en
    except Exception:
        return en


def _cli_env() -> Dict[str, str]:
    """Environment for a CLI child scoped to the logged-in user."""
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
    return env


def _run_cli(cli_args: list, runner_path: Path) -> subprocess.CompletedProcess:
    """Run `ecan <cli_args>` in a child process."""
    env = _cli_env()
    frozen = getattr(sys, "frozen", False)
    if frozen:
        # Packaged app: sys.executable is the GUI exe, not Python —
        # `-m cli.main` would just launch a second app instance that
        # exits 0 having done nothing (v0.9.95o customer incident:
        # panel showed success, nothing generated). Use the same
        # ECAN_RUN_SCRIPT worker mechanism as the LightRAG server:
        # the exe executes the script instead of booting the GUI.
        runner_path.write_text(
            "import sys\n"
            f"sys.argv = {json.dumps(['ecan'] + cli_args)}\n"
            "from cli.main import main\n"
            "main()\n"
            "sys.exit(0)\n",
            encoding="utf-8",
        )
        cmd = [sys.executable]
        env["ECAN_RUN_SCRIPT"] = str(runner_path)
    else:
        cmd = [sys.executable, "-m", "cli.main"] + cli_args
    proc = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True,
                          timeout=_CLI_TIMEOUT_S, env=env)
    logger.info(
        f"[FastDeploy] CLI {' '.join(cli_args[:2])} exited rc={proc.returncode} "
        f"(mode={'frozen-run-script' if frozen else 'python -m'}); "
        f"stderr tail: {(proc.stderr or '').strip()[-300:] or '(empty)'}"
    )
    return proc


def _cli_error(proc: subprocess.CompletedProcess) -> str:
    """'' when the CLI command succeeded, else its last error line."""
    if proc.returncode == 0:
        return ""
    text = ((proc.stderr or "") + "\n" + (proc.stdout or "")).strip()
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return (lines[-1] if lines else f"exit code {proc.returncode}")[:300]


def _create_store(store_id: Any, new_store: Dict[str, Any], runner_path: Path) -> str:
    """Create a catalog store with `ecan stores create`; '' on success, else the error."""
    sid = str(store_id or "").strip()
    name = str(new_store.get("name") or "").strip()
    platform = str(new_store.get("platform") or "").strip()
    if not sid or not name or not platform:
        return _tr("A new store needs a name and a platform", "新店铺需要名称和平台")
    args = ["stores", "create", "--id", sid, "--name", name, "--platform", platform]
    for url in new_store.get("urls") or []:
        if str(url).strip():
            args += ["--url", str(url).strip()]
    err = _cli_error(_run_cli(args, runner_path))
    return _tr(f"Could not create store {sid}: {err}", f"无法创建店铺 {sid}：{err}") if err else ""


@IPCHandlerRegistry.handler("fast_deploy.generate")
def handle_fast_deploy_generate(request: IPCRequest,
                                params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Save the scenario config and run the resource-generation CLI."""
    try:
        params = params or {}
        scenario = str(params.get("scenario") or "").strip()
        config = params.get("config") or {}
        if not scenario:
            return create_error_response(request, "INVALID_PARAMS", _tr("scenario is required", "缺少场景"))
        # A store deploy names its store(s) -- their URLs are on the store records;
        # the other scenarios name URLs.
        if not isinstance(config, dict) or not (config.get("store_urls") or config.get("stores")
                                                or config.get("store_id")):
            return create_error_response(request, "INVALID_PARAMS",
                                         _tr("config.store_id, config.stores or config.store_urls is required",
                                             "请选择店铺"))

        out_dir = _fast_deploy_dir()
        ts = time.strftime("%Y%m%d-%H%M%S")

        # The store: create it (new) or save its edited URL, then deploy into it.
        new_store = config.pop("new_store", None)
        store_url = str(config.pop("store_url", "") or "").strip()
        store_log: list = []
        store_created = store_url_saved = False
        if isinstance(new_store, dict):
            err = _create_store(config.get("store_id"), new_store, out_dir / f"store-{ts}.runner.py")
            if err:
                return create_success_response(request, {"status": "failure", "scenario": scenario,
                                                         "log": [err], "message": err})
            store_created = True
            store_log.append(_tr(f"Store {config.get('store_id')} created", f"已创建店铺 {config.get('store_id')}"))
        elif store_url and config.get("store_id"):
            err = _cli_error(_run_cli(["stores", "update", str(config["store_id"]), "--url", store_url],
                                      out_dir / f"store-{ts}.runner.py"))
            if err:
                store_log.append(_tr(f"Store URL not saved: {err}", f"店铺链接未保存：{err}"))
            else:
                store_url_saved = True
                store_log.append(_tr("Store URL saved", "已保存店铺链接"))
        cfg_path = out_dir / f"{scenario}-{ts}.json"
        res_path = out_dir / f"{scenario}-{ts}.result.json"

        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump({"scenario": scenario, "config": config}, f, ensure_ascii=False, indent=2)
        logger.info(f"[FastDeploy] wrote config {cfg_path}")

        cli_args = ["deploy", "scenario", "--config", str(cfg_path), "--output", str(res_path)]
        proc = _run_cli(cli_args, out_dir / f"{scenario}-{ts}.runner.py")

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
            log = [_tr("Resource generation did not produce a result — see eCan.log for the CLI error.",
                       "生成未产生结果，请查看 eCan.log 中的错误信息。")]
        log = store_log + log

        return create_success_response(request, {
            "status": status,
            "scenario": scenario,
            "config_path": str(cfg_path),
            "plan": result.get("plan"),
            # A scenario with no generation yet (e.g. tmall_cs) returns a plan
            # only; the panel must not present that as a deployment.
            "stub": bool(result.get("stub")),
            "log": log,
            "message": result.get("message") or "",
            "store_created": store_created,
            "store_url_saved": store_url_saved,
        })
    except subprocess.TimeoutExpired:
        logger.error("[FastDeploy] CLI timed out")
        return create_error_response(request, "TIMEOUT", _tr("Resource generation timed out", "生成超时"))
    except Exception as e:
        logger.error(f"[FastDeploy] error: {e}")
        return create_error_response(request, "FAST_DEPLOY_ERROR", str(e))
