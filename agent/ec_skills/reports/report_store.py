r"""Where a skill's run report goes: a dated local folder, then the account's
S3 report area.

Local:  C:\reports\<category>\<store>\<YYYY-MM-DD>\<file>   (~/reports/... off Windows)
S3:     ecan-reports/<user_id>/<category>/<store>/<date>/<file>, through a presigned
        PUT from ``requestReportUploadUrl``; the server takes user_id from the login
        token, so the client never names it.

The local copy is the record. An upload that cannot happen yet (signed out, the
server mutation not deployed) is reported as ``pending`` and never fails the run.
"""
from __future__ import annotations

import json
import os
import platform
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from utils.logger_helper import logger_helper as logger

_UPLOAD_MUTATION = """
    mutation RequestReportUploadUrl($input: ReportUploadInput!) {
        requestReportUploadUrl(input: $input) { uploadUrl s3Key expiresIn }
    }
"""
_CONTENT_TYPES = {".md": "text/markdown", ".json": "application/json", ".html": "text/html",
                  ".csv": "text/csv", ".pdf": "application/pdf"}


def reports_root() -> Path:
    return Path(r"C:\reports") if platform.system() == "Windows" else Path.home() / "reports"


def safe_part(name: str) -> str:
    """One path segment: no separators, no '..', no characters Windows refuses."""
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", str(name or "").strip())
    s = s.strip(" .")
    return s if s and s not in (".", "..") else "unnamed"


def report_dir(category: str, store: str, date: Optional[str] = None) -> Path:
    date = date or datetime.now().strftime("%Y-%m-%d")
    return reports_root() / safe_part(category) / safe_part(store) / safe_part(date)


def save_report(category: str, store: str, files: Dict[str, Any], date: Optional[str] = None) -> Path:
    """Write ``files`` ({file name: text or JSON-able value}) and return the folder."""
    folder = report_dir(category, store, date)
    folder.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False, indent=2)
        (folder / safe_part(name)).write_text(text, encoding="utf-8")
    return folder


def _request_upload_url(category: str, store: str, date: str, file_name: str) -> Dict[str, Any]:
    import requests
    from agent.cloud_api.cloud_api import appsync_http_request, get_appsync_endpoint
    from agent.cloud_api.turn_queue import _session_bearer_token
    token = _session_bearer_token()
    if not token:
        return {"error": "not signed in"}
    resp = appsync_http_request(_UPLOAD_MUTATION, requests.Session(), token, get_appsync_endpoint(),
                                timeout=30, variables={"input": {"category": category, "storeName": store,
                                                                 "date": date, "fileName": file_name}})
    if resp.get("errors"):
        msg = "; ".join(str(e.get("message") or e.get("errorType")) for e in resp["errors"] if isinstance(e, dict))
        return {"error": msg or "upload address refused"}
    data = (resp.get("data") or {}).get("requestReportUploadUrl")
    return data if data and data.get("uploadUrl") else {"error": "the cloud returned no upload address"}


def upload_report(folder: Path, category: str, store: str, date: str) -> Dict[str, Any]:
    """Upload every file in ``folder``. Returns {"status": "uploaded"|"pending"|"partial",
    "keys": [...], "reason": ...}."""
    from agent.cloud_api.cloud_api import upload_file_to_presigned_url
    keys, failed = [], []
    for path in sorted(p for p in Path(folder).iterdir() if p.is_file()):
        grant = _request_upload_url(safe_part(category), safe_part(store), date, path.name)
        if grant.get("error"):
            failed.append(f"{path.name}: {grant['error']}")
            continue
        res = upload_file_to_presigned_url(str(path), grant["uploadUrl"],
                                           content_type=_CONTENT_TYPES.get(path.suffix.lower()))
        if res.get("success"):
            keys.append(grant.get("s3Key"))
        else:
            failed.append(f"{path.name}: {res.get('error')}")
    status = "uploaded" if keys and not failed else ("partial" if keys else "pending")
    if failed:
        logger.warning(f"[report_store] report upload {status} for {folder}: {failed[0]}")
    return {"status": status, "keys": keys, "reason": "; ".join(failed)}


def save_and_upload(category: str, store: str, files: Dict[str, Any], date: Optional[str] = None) -> Dict[str, Any]:
    date = date or datetime.now().strftime("%Y-%m-%d")
    folder = save_report(category, store, files, date)
    try:
        upload = upload_report(folder, category, store, date)
    except Exception as exc:
        upload = {"status": "pending", "keys": [], "reason": str(exc)}
    (folder / "upload_status.json").write_text(json.dumps(upload, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"[report_store] report saved to {folder} (cloud: {upload['status']})")
    return {"folder": str(folder), "upload": upload}


def day_title(orders: int, processed: int, todos: int, redflags: int) -> str:
    """The end-of-day report's one-line title, the same for every store skill."""
    return f"{orders} orders, {processed} processed, {todos} todos, {redflags} redflags"
