"""save_store_report: the MCP tool a store skill's last step calls to file its daily report
the way the store checks do (local dated folder, then the cloud upload), so the cloud
Manager can read it.

A run that could not read the site (a sign-in page, an account chooser, a page that would
not load) still files a report, titled "CHECK DID NOT COMPLETE" with the reason, so it never
reads as an all-clear.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

from mcp import types
from mcp.types import TextContent

from agent.ec_skills.reports.report_store import report_dir, safe_part, save_and_upload
from utils.logger_helper import logger_helper as logger

NOT_COMPLETE = "CHECK DID NOT COMPLETE"


def save_store_report(mainwin: Any, config: Dict[str, Any]) -> Dict[str, Any]:
    """config: store_id, kind (e.g. "google_ads"), complete, report (dict, with proposals[]
    when the skill drafts changes), report_md, error (why it did not complete)."""
    store_id = str(config.get("store_id") or "").strip()
    kind = str(config.get("kind") or "").strip().lower()
    if not store_id or not kind:
        return {"success": False, "error": "store_id and kind are required"}
    kind = safe_part(kind)
    report = config.get("report")
    if isinstance(report, str):
        try:
            report = json.loads(report)
        except ValueError:
            report = {"text": report}
    complete = bool(config.get("complete")) and isinstance(report, dict) and bool(report)
    error = str(config.get("error") or "").strip()
    md = str(config.get("report_md") or "").strip()
    if complete:
        files: Dict[str, Any] = {"report.json": report, "report.md": md or f"# {kind} report\n"}
    else:
        reason = error or "the run did not finish reading the site"
        files = {"report.md": f"# {NOT_COMPLETE}\n\n**Error:** {reason}\n\n{md}\n".rstrip() + "\n",
                 "raw_result.json": {"error": reason, "report": report}}
    files["run.json"] = {"store_id": store_id, "kind": kind}
    for stale in {"report.json", "raw_result.json"} - set(files):      # a rerun the same day
        (report_dir(kind, store_id) / stale).unlink(missing_ok=True)
    out = save_and_upload(kind, store_id, files)
    proposals = report.get("proposals") if isinstance(report, dict) else None
    logger.info(f"[save_store_report] {kind}/{store_id}: complete={complete} "
                f"proposals={len(proposals) if isinstance(proposals, list) else 0} upload={out['upload'].get('status')}")
    return {"success": True, "complete": complete, "title": "report saved" if complete else NOT_COMPLETE,
            "folder": out["folder"], "upload_status": out["upload"].get("status")}


def add_save_store_report_tool_schema(tool_schemas: list) -> None:
    tool_schemas.append(types.Tool(
        _meta={"run_in_cloud": False},
        name="save_store_report",
        description=(
            "<category>Report</category><sub-category>Store Report</sub-category>"
            "Save and upload a store skill's daily report the standard way (report.json, report.md, "
            "run.json with store_id), so the cloud Manager can read it. Call it before replying in chat. "
            "If the run could not read the site (sign-in page, account chooser, page failed), call it with "
            "complete=false and the reason in error: it is filed as CHECK DID NOT COMPLETE."
        ),
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": ["store_id", "kind", "complete"],
                    "properties": {
                        "store_id": {"type": "string", "description": "The store's id, e.g. mystore_shopify_000."},
                        "kind": {"type": "string", "description": "What the report covers, e.g. google_ads."},
                        "complete": {"type": "boolean", "description": "False when the site could not be read."},
                        "report": {"type": "object", "description": "The report; drafted changes go in proposals[] "
                                   "as {id, kind, summary, numbers}."},
                        "report_md": {"type": "string", "description": "The report as Markdown for people."},
                        "error": {"type": "string", "description": "Why the run did not complete."},
                    },
                }
            },
        },
    ))


async def async_save_store_report(mainwin: Any, args: Dict[str, Any]) -> List[TextContent]:
    try:
        result = save_store_report(mainwin, args.get("input") if isinstance(args.get("input"), dict) else args)
    except Exception as e:
        logger.warning(f"[save_store_report] failed: {e}")
        result = {"success": False, "error": str(e)}
    text = (f"{result['title']}: saved to {result['folder']} (cloud: {result['upload_status']})"
            if result.get("success") else f"Failed to save the report: {result.get('error')}")
    out = TextContent(type="text", text=text)
    out.meta = {"task_result": result}
    return [out]
