"""Debug log collection and upload handler.

Collects skill JSON files, prompt files, and the main eCan.log, zips them,
uploads to S3 via a presigned URL obtained from AppSync, then notifies the
server that the upload is complete.

Before anything is packaged, the problem description goes through the
server-side intake gate (``requestDebug`` answers ok / incomplete / rejected),
so a report that says only "it broke" is turned back with a follow-up question
instead of costing an upload. The gate judges intent, not tone — an
angry-but-detailed report passes.

IPC methods:
  validate_bug_description  params: { description, skillIds? }
  request_log_analysis      params: { skillIds, description?, attachments?, grant? }

Public functions:
  local_description_issue(description)          -> 'empty' | 'too_short' | None
  validate_bug_description(description, skills) -> {status, question, message, grant}
  perform_log_analysis_upload(skill_ids, ...)   -> str
  Called directly by the GUI dialog (runs in a QThread) and by the CLI.
"""
from __future__ import annotations

import json
import os
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import requests as http_requests

from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_success_response, create_error_response
from utils.logger_helper import logger_helper as logger
from utils.user_path_helper import get_user_data_dir

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _get_my_skills_dir() -> Path:
    return Path(get_user_data_dir(subdir="my_skills"))


def _get_my_prompts_dir() -> Path:
    return Path(get_user_data_dir(subdir="my_prompts"))


def _get_log_path() -> Path:
    """Return the path to eCan.log (works in dev and PyInstaller production)."""
    try:
        from config.app_info import app_info
        appdata = getattr(app_info, "appdata_path", None)
        if appdata:
            candidate = Path(appdata) / "runlogs" / "eCan.log"
            if candidate.exists():
                return candidate
    except Exception:
        pass
    # Dev fallback
    return PROJECT_ROOT / "runlogs" / "eCan.log"


def _get_zip_output_path(ts: str) -> Path:
    """Return the temp zip path in the runlogs directory."""
    try:
        from config.app_info import app_info
        appdata = getattr(app_info, "appdata_path", None)
        if appdata:
            runlogs = Path(appdata) / "runlogs"
            runlogs.mkdir(parents=True, exist_ok=True)
            return runlogs / f"log_{ts}.zip"
    except Exception:
        pass
    runlogs = PROJECT_ROOT / "runlogs"
    runlogs.mkdir(parents=True, exist_ok=True)
    return runlogs / f"log_{ts}.zip"


# ---------------------------------------------------------------------------
# Skill JSON parsing - extract prompt IDs
# ---------------------------------------------------------------------------

def _collect_prompt_ids_from_skill_json(skill_json_path: Path) -> Set[str]:
    """Walk a skill JSON diagram and return all referenced prompt IDs (pr-XXXXXX)."""
    prompt_ids: Set[str] = set()
    try:
        data = json.loads(skill_json_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning(f"[debug_log] Could not parse {skill_json_path}: {exc}")
        return prompt_ids

    nodes = []
    # diagram_dir structure: workFlow.nodes or nodes at top level
    for key in ("workFlow", "workflow"):
        wf = data.get(key)
        if isinstance(wf, dict):
            nodes = wf.get("nodes", [])
            break
    if not nodes:
        nodes = data.get("nodes", [])

    for node in nodes:
        node_data = node.get("data", {}) if isinstance(node, dict) else {}
        inputs_values = node_data.get("inputsValues", {})
        for field_val in inputs_values.values():
            if not isinstance(field_val, dict):
                continue
            pid_node = field_val.get("promptId")
            if isinstance(pid_node, dict):
                pid = pid_node.get("content", "")
                if pid and pid != "in-line" and pid.startswith("pr-"):
                    prompt_ids.add(pid)

    return prompt_ids


def _find_skill_dirs(skill_ids: List[str]) -> Dict[str, Path]:
    """Map skill_id → local skill directory.  Uses agent_skills in memory, then dir scan."""
    result: Dict[str, Path] = {}
    remaining = set(skill_ids)

    # Try in-memory agent_skills first (fastest, has path attribute)
    try:
        from app_context import AppContext
        mainwin = AppContext.get_main_window()
        if mainwin:
            skills = getattr(mainwin, "agent_skills", None) or []
            for sk in skills:
                sid = str(getattr(sk, "id", "") or "")
                if sid in remaining:
                    p = getattr(sk, "path", None)
                    if p and Path(p).is_dir():
                        result[sid] = Path(p)
                        remaining.discard(sid)
    except Exception as exc:
        logger.debug(f"[debug_log] Could not access agent_skills: {exc}")

    # Fallback: scan my_skills directory looking for diagram JSON with matching skillId
    if remaining:
        skills_base = _get_my_skills_dir()
        if skills_base.is_dir():
            for skill_dir in skills_base.iterdir():
                if not skill_dir.is_dir():
                    continue
                diagram_dir = skill_dir / "diagram_dir"
                if not diagram_dir.is_dir():
                    continue
                for json_file in diagram_dir.glob("*.json"):
                    try:
                        data = json.loads(json_file.read_text(encoding="utf-8"))
                        sid = str(data.get("skillId") or data.get("id") or "")
                        if sid in remaining:
                            result[sid] = skill_dir
                            remaining.discard(sid)
                            if not remaining:
                                break
                    except Exception:
                        continue
                if not remaining:
                    break

    if remaining:
        logger.warning(f"[debug_log] Could not resolve dirs for skill IDs: {remaining}")
    return result


# ---------------------------------------------------------------------------
# Cloud API helpers (reuse skill_file_sync pattern)
# ---------------------------------------------------------------------------

_REQUEST_DEBUG_MUTATION = """
mutation RequestDebug($input: RequestDebugInput!) {
  requestDebug(input: $input) {
    status
    uploadUrl
    zipKey
    expiresIn
    question
    message
  }
}
"""

# The shape this client spoke before the intake gate shipped. eCan runs on two
# backends (AWS AppSync + Tencent TCB) that are not guaranteed to carry the same
# SDL at the same moment; if one still predates the gate it answers
# GRAPHQL_VALIDATION_FAILED for the new fields and we retry with this. The gate
# is a quality filter, not a security boundary (the server itself fails open),
# so an ungated backend is a degraded path, not an error.
_REQUEST_DEBUG_MUTATION_LEGACY = """
mutation RequestDebug($input: RequestDebugInput!) {
  requestDebug(input: $input) {
    uploadUrl
    zipKey
    expiresIn
  }
}
"""

_REQUEST_DEBUG_DONE_MUTATION = """
mutation RequestDebugDone($zipKey: String!, $owner: String!, $description: String) {
  requestDebugDone(zipKey: $zipKey, owner: $owner, description: $description) {
    success
    message
  }
}
"""

_REQUEST_DEBUG_DONE_MUTATION_LEGACY = """
mutation RequestDebugDone($zipKey: String!, $owner: String!) {
  requestDebugDone(zipKey: $zipKey, owner: $owner) {
    success
    message
  }
}
"""


class BugIntakeNotAccepted(RuntimeError):
    """The intake gate did not accept the problem description.

    ``status`` is "incomplete" (ask ``question`` and let the user revise) or
    "rejected" (show ``message`` and stop — no retry loop).
    """

    def __init__(self, status: str, question: str = "", message: str = ""):
        self.status = status or "rejected"
        self.question = question or ""
        self.message = message or ""
        super().__init__(self.question or self.message
                         or "Bug report not accepted ({}).".format(self.status))


# Weighted length below which we turn the description back locally instead of
# spending a server round-trip (every gate round costs a classifier call).
MIN_DESCRIPTION_WEIGHT = 12

_GATE_FIELD_NAMES = ("status", "question", "message", "description")


def _description_weight(text: str) -> int:
    """Length weighted so CJK isn't under-counted.

    A CJK character carries far more meaning than a Latin one, so "点击登录后闪退"
    (7 chars) is a real report while "it broke" (8 chars) is not. Counting CJK
    double keeps the local pre-check from turning back legitimate short Chinese.
    """
    return sum(2 if "\u4e00" <= ch <= "\u9fff" else 1 for ch in text)


def local_description_issue(description: str) -> Optional[str]:
    """Cheap local pre-check. Returns 'empty', 'too_short', or None.

    None means "worth asking the server" — it is NOT a verdict of acceptable.
    """
    text = (description or "").strip()
    if not text:
        return "empty"
    if _description_weight(text) < MIN_DESCRIPTION_WEIGHT:
        return "too_short"
    return None


def _is_gate_schema_error(resp: Dict[str, Any]) -> bool:
    """True when the backend's SDL doesn't know the intake-gate fields yet."""
    for err in (resp.get("errors") or []):
        msg = str(err.get("message") or "")
        code = str(((err.get("extensions") or {}).get("code")) or "")
        looks_schema = ("GRAPHQL_VALIDATION_FAILED" in code
                        or "Cannot query field" in msg
                        or "Unknown field" in msg
                        or "Unknown argument" in msg
                        or "unknown field" in msg)
        if looks_schema and any(f in msg for f in _GATE_FIELD_NAMES):
            return True
    return False


def _request_debug(ctx: Dict[str, Any], owner: str, skill_ids: List[str],
                   description: str):
    """Call requestDebug. Returns (status, payload).

    ``status`` is "ok" | "incomplete" | "rejected". A backend that predates the
    gate returns no status; we read that as ungated "ok" when a URL came back.
    """
    variables: Dict[str, Any] = {
        "input": {"owner": owner, "skillIds": list(skill_ids or [])}}
    if description:
        variables["input"]["description"] = description

    resp = _appsync_request(_REQUEST_DEBUG_MUTATION, ctx, variables)
    if _is_gate_schema_error(resp):
        logger.warning("[debug_log] Backend predates the bug-intake gate; "
                       "falling back to the legacy requestDebug shape (ungated)")
        resp = _appsync_request(
            _REQUEST_DEBUG_MUTATION_LEGACY, ctx,
            {"input": {"owner": owner, "skillIds": list(skill_ids or [])}})

    if "errors" in resp or not (resp.get("data") or {}).get("requestDebug"):
        errs = resp.get("errors", [{}])
        raise RuntimeError("requestDebug failed: {}".format(
            errs[0].get("message", str(errs))))

    payload = resp["data"]["requestDebug"] or {}
    status = str(payload.get("status") or "").strip().lower()
    if not status:
        status = "ok" if payload.get("uploadUrl") else "rejected"
    return status, payload


def validate_bug_description(description: str,
                             skill_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    """Run the intake gate WITHOUT packaging or uploading anything.

    On "ok" the returned ``grant`` carries the presigned uploadUrl/zipKey; hand
    it to ``perform_log_analysis_upload(..., grant=grant)`` so an already
    accepted description is not classified a second time.
    """
    ctx = _get_cloud_context()
    if not ctx:
        raise RuntimeError("Not logged in or no cloud connection available.")

    status, payload = _request_debug(ctx, ctx["owner"], list(skill_ids or []), description)
    result: Dict[str, Any] = {
        "status": status,
        "question": payload.get("question") or "",
        "message": payload.get("message") or "",
        "grant": {},
    }
    if status == "ok" and payload.get("uploadUrl") and payload.get("zipKey"):
        result["grant"] = {
            "uploadUrl": payload["uploadUrl"],
            "zipKey": payload["zipKey"],
            "expiresIn": payload.get("expiresIn"),
            "grantedAt": time.time(),
        }
    logger.info("[debug_log] Intake gate: status={} desc_len={}".format(
        status, len((description or "").strip())))
    return result


def _get_cloud_context() -> Optional[Dict[str, Any]]:
    try:
        from app_context import AppContext
        from agent.cloud_api.cloud_api import normalize_cloud_owner
        mainwin = AppContext.get_main_window()
        token = mainwin.get_auth_token() if mainwin is not None else None
        if mainwin is not None and token:
            return {
                "session": mainwin.session,
                "token": token,
                "endpoint": mainwin.getWanApiEndpoint() if hasattr(mainwin, "getWanApiEndpoint") else None,
                "owner": normalize_cloud_owner(getattr(mainwin, "user", "") or ""),
            }
    except Exception as exc:
        logger.warning(f"[debug_log] Failed to get GUI cloud context: {exc}")
    # Headless fallback (CLI / agent, no GUI): auth from the CLI env token the
    # app sets for its subprocesses (ECAN_CLI_AUTH_TOKEN), a plain requests
    # session, and the standard AppSync endpoint. Lets `ecan support upload`
    # run without a MainWindow.
    return _get_cli_cloud_context()


def _get_cli_cloud_context() -> Optional[Dict[str, Any]]:
    try:
        token = os.environ.get("ECAN_CLI_AUTH_TOKEN") or ""
        if not token:
            return None
        user = (os.environ.get("ECAN_DEPLOY_OWNER")
                or os.environ.get("ECAN_CLI_USER") or "")
        from agent.cloud_api.cloud_api import normalize_cloud_owner, get_appsync_endpoint
        return {
            "session": http_requests.Session(),
            "token": token,
            "endpoint": get_appsync_endpoint(),
            "owner": normalize_cloud_owner(user),
        }
    except Exception as exc:
        logger.warning(f"[debug_log] CLI cloud context unavailable: {exc}")
        return None


def _appsync_request(query: str, ctx: Dict[str, Any], variables: Optional[Dict] = None) -> Dict:
    from agent.cloud_api.cloud_api import get_appsync_endpoint, _http_auth_header
    endpoint = ctx.get("endpoint") or get_appsync_endpoint()
    headers = {
        "Content-Type": "application/json",
        # CN needs the session-token bearer; Intl passes the token through.
        "Authorization": _http_auth_header(ctx["token"]),
        "cache-control": "no-cache",
    }
    payload: Dict[str, Any] = {"query": query}
    if variables:
        payload["variables"] = variables
    try:
        resp = ctx["session"].request(url=endpoint, method="POST", timeout=30, headers=headers, json=payload)
        return resp.json()
    except Exception as exc:
        logger.warning(f"[debug_log] AppSync request failed: {exc}")
        return {"errors": [{"message": str(exc)}]}


# ---------------------------------------------------------------------------
# Runlogs packaging
# ---------------------------------------------------------------------------
# The whole runlogs folder goes into the package (eCan.log, eCan.wscap.log,
# lightrag.log, memory.log, rotated backups, runs/…), not just eCan.log — the
# ws-capture log is usually what support needs. Guard rails so a long-lived
# install can't produce a multi-GB upload: previous upload zips are skipped, a
# single file over MAX_RUNLOG_FILE_BYTES is skipped, and the walk stops once
# MAX_RUNLOG_TOTAL_BYTES of uncompressed data has been added. Whatever was
# skipped is listed in runlogs/_manifest.txt inside the zip.
MAX_RUNLOG_FILE_BYTES = 200 * 1024 * 1024
MAX_RUNLOG_TOTAL_BYTES = 1024 * 1024 * 1024


def _add_runlogs_dir(zf: "zipfile.ZipFile", runlogs_dir: Path,
                     exclude: Optional[Path] = None) -> Dict[str, Any]:
    """Add every file under runlogs_dir to zf as runlogs/<relative path>.

    Returns {"added": n, "bytes": total_uncompressed, "skipped": [(rel, reason), ...]}.
    """
    added, total, skipped = 0, 0, []
    if not runlogs_dir.is_dir():
        return {"added": 0, "bytes": 0, "skipped": [(str(runlogs_dir), "runlogs directory not found")]}
    exclude_resolved = exclude.resolve() if exclude else None
    # Newest files first so the budget, if hit, drops the oldest run artefacts.
    entries = []
    for root, _dirs, files in os.walk(runlogs_dir):
        for fname in files:
            abs_path = Path(root) / fname
            try:
                st = abs_path.stat()
            except OSError:
                continue
            entries.append((st.st_mtime, st.st_size, abs_path))
    entries.sort(key=lambda e: e[0], reverse=True)
    for _mtime, size, abs_path in entries:
        rel = abs_path.relative_to(runlogs_dir).as_posix()
        if exclude_resolved and abs_path.resolve() == exclude_resolved:
            continue
        if abs_path.suffix.lower() == ".zip" and abs_path.name.startswith("log_"):
            skipped.append((rel, "previous debug upload"))
            continue
        if size > MAX_RUNLOG_FILE_BYTES:
            skipped.append((rel, f"file too large ({size // (1024 * 1024)} MB)"))
            continue
        if total + size > MAX_RUNLOG_TOTAL_BYTES:
            skipped.append((rel, "total size budget exhausted"))
            continue
        try:
            zf.write(abs_path, f"runlogs/{rel}")
        except OSError as exc:  # locked / vanished mid-walk
            skipped.append((rel, f"unreadable: {exc}"))
            continue
        added += 1
        total += size
    if skipped:
        lines = [f"{rel}\t{reason}" for rel, reason in skipped]
        zf.writestr("runlogs/_manifest.txt",
                    "skipped files (relative to runlogs)\n" + "\n".join(lines) + "\n")
    return {"added": added, "bytes": total, "skipped": skipped}


# ---------------------------------------------------------------------------
# Issue report (user problem description + attachments)
# ---------------------------------------------------------------------------
ISSUE_REPORT_NAME = "current_issues.md"     # per spec: description saved here
ISSUE_ATTACH_SUBDIR = "issue_attachments"   # screenshots / screen recordings


def save_issue_report(runlogs_dir: Path, description: str = "",
                      attachments: Optional[List[str]] = None) -> Dict[str, Any]:
    """Write the user's problem description to runlogs/current_issues.md and copy
    each attachment (screenshot / screen recording) into
    runlogs/issue_attachments/, so the runlogs packager sweeps them into the
    upload automatically. Pure file I/O — no cloud auth — so the GUI dialog, the
    CLI, and an agent can all call it. Returns {report, copied, skipped}.
    """
    import shutil
    from datetime import datetime as _dt
    result: Dict[str, Any] = {"report": "", "copied": [], "skipped": []}
    try:
        runlogs_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    desc = (description or "").strip()
    if desc:
        report = runlogs_dir / ISSUE_REPORT_NAME
        ts = _dt.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            report.write_text(f"# Issue report / 问题描述\n\n- Time: {ts}\n\n{desc}\n",
                              encoding="utf-8")
            result["report"] = str(report)
        except Exception as e:
            result["skipped"].append((ISSUE_REPORT_NAME, f"write failed: {e}"))
    for src in (attachments or []):
        try:
            sp = Path(src)
            if not sp.is_file():
                result["skipped"].append((str(src), "not a file"))
                continue
            dest_dir = runlogs_dir / ISSUE_ATTACH_SUBDIR
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / sp.name
            i = 1
            while dest.exists() and dest.resolve() != sp.resolve():
                dest = dest_dir / f"{sp.stem}_{i}{sp.suffix}"
                i += 1
            if dest.resolve() != sp.resolve():
                shutil.copy2(sp, dest)
            result["copied"].append(str(dest))
        except Exception as e:
            result["skipped"].append((str(src), f"copy failed: {e}"))
    logger.info(f"[debug_log] issue report: desc={'yes' if desc else 'no'} "
                f"copied={len(result['copied'])} skipped={len(result['skipped'])}")
    return result


# ---------------------------------------------------------------------------
# Core upload logic
# ---------------------------------------------------------------------------

def _put_zip(upload_url: str, zip_path: Path):
    """PUT the package to the presigned URL."""
    with open(zip_path, "rb") as f:
        return http_requests.put(
            upload_url,
            data=f,
            headers={"Content-Type": "application/zip"},
            timeout=300,
        )


def perform_log_analysis_upload(skill_ids: List[str], description: str = "",
                                attachments: Optional[List[str]] = None,
                                grant: Optional[Dict[str, Any]] = None) -> str:
    """
    Collect skills + prompts + logs → zip → upload to S3 via presigned URL.

    ``grant`` is the {uploadUrl, zipKey} handed back by
    ``validate_bug_description`` when the intake gate accepted the description;
    passing it avoids classifying the same text twice. Without it this runs the
    gate itself and raises ``BugIntakeNotAccepted`` when the description is
    turned back — callers that can prompt the user should validate first.

    Returns a success message string. Raises on fatal errors.
    """
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    zip_path = _get_zip_output_path(ts)

    ctx = _get_cloud_context()
    if not ctx:
        raise RuntimeError("Not logged in or no cloud connection available.")
    owner = ctx["owner"]

    # 1. Resolve skill directories
    skill_dir_map = _find_skill_dirs(skill_ids)

    # 2. Collect prompt IDs from all selected skill JSONs
    prompt_ids: Set[str] = set()
    for skill_dir in skill_dir_map.values():
        diagram_dir = skill_dir / "diagram_dir"
        if diagram_dir.is_dir():
            for json_file in diagram_dir.glob("*.json"):
                prompt_ids |= _collect_prompt_ids_from_skill_json(json_file)

    logger.info(f"[debug_log] Collected {len(prompt_ids)} prompt IDs from {len(skill_dir_map)} skills")

    # 3. Build zip
    prompts_dir = _get_my_prompts_dir()
    log_path = _get_log_path()

    # Persist the user's problem description + attachments INTO runlogs first, so
    # the whole-folder packaging below includes current_issues.md and the
    # issue_attachments/ files.
    if description or attachments:
        save_issue_report(log_path.parent, description, attachments)

    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            # Whole runlogs folder — eCan.log, eCan.wscap.log (the ws-capture log
            # support usually needs), lightrag.log, memory.log, rotated backups,
            # runs/… — not just eCan.log. `_add_runlogs_dir` applies the size
            # guards and writes runlogs/_manifest.txt for anything skipped, and
            # excludes THIS run's in-progress zip. (Previously only eCan.log was
            # added — the helper existed but was never wired in.)
            runlogs_dir = log_path.parent
            rl = _add_runlogs_dir(zf, runlogs_dir, exclude=zip_path)
            if rl["added"]:
                logger.info(
                    f"[debug_log] Added runlogs dir: {rl['added']} file(s), "
                    f"{rl['bytes'] // 1024} KB uncompressed, "
                    f"{len(rl['skipped'])} skipped")
            elif log_path.exists():
                # Dir walk found nothing (e.g. runlogs not a dir) — fall back to
                # the single log so support still gets something.
                zf.write(log_path, "runlogs/eCan.log")
                logger.warning(f"[debug_log] runlogs dir empty; added eCan.log only: {log_path}")
            else:
                logger.warning(f"[debug_log] No runlogs found at {runlogs_dir}")

            # Prompt files
            for pid in sorted(prompt_ids):
                # Prompts may be stored as "{pid}.json" or "{name}_{pid}.json"
                found = False
                if prompts_dir.is_dir():
                    # Exact match first
                    exact = prompts_dir / f"{pid}.json"
                    if exact.exists():
                        zf.write(exact, f"prompts/{pid}.json")
                        found = True
                    else:
                        # Glob for files ending in _{pid}.json
                        for candidate in prompts_dir.glob(f"*_{pid}.json"):
                            zf.write(candidate, f"prompts/{candidate.name}")
                            found = True
                            break
                if not found:
                    logger.debug(f"[debug_log] Prompt file not found locally: {pid}")

            # Skill directories
            for sid, skill_dir in skill_dir_map.items():
                for root, _dirs, files in os.walk(skill_dir):
                    for fname in files:
                        abs_path = Path(root) / fname
                        rel = abs_path.relative_to(skill_dir.parent)
                        zf.write(abs_path, f"skills/{rel}")

        logger.info(f"[debug_log] Zip created: {zip_path} ({zip_path.stat().st_size // 1024} KB)")

        # 4. Presigned upload URL. Reuse the grant the intake gate already
        #    issued so an accepted description isn't classified twice; callers
        #    that skipped validation get gated here instead.
        if grant and grant.get("uploadUrl") and grant.get("zipKey"):
            upload_url = grant["uploadUrl"]
            zip_key = grant["zipKey"]
            logger.info(f"[debug_log] Reusing intake grant, key={zip_key}")
        else:
            status, payload = _request_debug(ctx, owner, skill_ids, description)
            if status != "ok":
                raise BugIntakeNotAccepted(
                    status, payload.get("question"), payload.get("message"))
            upload_url = payload["uploadUrl"]
            zip_key = payload["zipKey"]
            logger.info(f"[debug_log] Got presigned URL, key={zip_key}")

        # 5. PUT zip to S3
        put_resp = _put_zip(upload_url, zip_path)
        if put_resp.status_code == 403 and grant:
            # The grant is issued before packaging now, so a large runlogs zip
            # can outlive the presigned URL. Re-request once with the already
            # accepted description and retry.
            logger.warning("[debug_log] Upload URL expired (403); re-requesting")
            status, payload = _request_debug(ctx, owner, skill_ids, description)
            if status == "ok" and payload.get("uploadUrl"):
                upload_url = payload["uploadUrl"]
                zip_key = payload["zipKey"]
                put_resp = _put_zip(upload_url, zip_path)
        if put_resp.status_code not in (200, 204):
            raise RuntimeError(f"S3 upload failed: HTTP {put_resp.status_code}")
        logger.info(f"[debug_log] Upload complete: {zip_key}")

        # 6. Notify server (the accepted description is stored on the job and
        #    fed to the analysis agent).
        done_vars = {"zipKey": zip_key, "owner": owner, "description": description or None}
        resp2 = _appsync_request(_REQUEST_DEBUG_DONE_MUTATION, ctx, done_vars)
        if _is_gate_schema_error(resp2):
            resp2 = _appsync_request(
                _REQUEST_DEBUG_DONE_MUTATION_LEGACY, ctx,
                {"zipKey": zip_key, "owner": owner})
        done_data = (resp2.get("data") or {}).get("requestDebugDone") or {}
        logger.info(f"[debug_log] requestDebugDone: {done_data}")

        return done_data.get("message") or "Debug package uploaded successfully."

    finally:
        # Always clean up local zip
        try:
            if zip_path.exists():
                zip_path.unlink()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# IPC handler wrapper
# ---------------------------------------------------------------------------

@IPCHandlerRegistry.background_handler("validate_bug_description")
def handle_validate_bug_description(request: IPCRequest,
                                    params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Run the intake gate on a description. No packaging, no upload."""
    p = params or {}
    description = (p.get("description") or "").strip()
    issue = local_description_issue(description)
    if issue:
        # Caught locally — no server round-trip, no classifier call.
        return create_success_response({"status": "incomplete", "localIssue": issue,
                                        "question": "", "message": "", "grant": {}})
    try:
        return create_success_response(validate_bug_description(description, p.get("skillIds") or []))
    except Exception as exc:
        logger.error(f"[debug_log] Description validation failed: {exc}", exc_info=True)
        return create_error_response(str(exc))


@IPCHandlerRegistry.background_handler("request_log_analysis")
def handle_request_log_analysis(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    p = params or {}
    skill_ids = p.get("skillIds") or []
    if not skill_ids:
        return create_error_response("No skill IDs provided.")
    try:
        message = perform_log_analysis_upload(
            skill_ids,
            p.get("description") or "",
            p.get("attachments") or [],
            p.get("grant") or None,
        )
        return create_success_response({"message": message})
    except BugIntakeNotAccepted as exc:
        # Not a failure — the gate wants a better description.
        return create_success_response({"status": exc.status, "question": exc.question,
                                        "message": exc.message})
    except Exception as exc:
        logger.error(f"[debug_log] Upload failed: {exc}", exc_info=True)
        return create_error_response(str(exc))
