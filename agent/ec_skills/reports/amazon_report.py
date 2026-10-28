"""Turn the Amazon after-sales browser run's final answer into the run report.

The browser step ends with a JSON report (see the amazon_after_sales prompt).
This finds it in the run state, renders a readable report.md next to
report.json, and saves both through report_store (local dated folder, then S3).
An answer that is not valid JSON is kept as raw_result.txt, never dropped.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from agent.ec_skills.reports.report_store import save_and_upload


def browser_final(state: Dict[str, Any]) -> Any:
    """The last browser step's final answer: state["tool_result"][<step>]["final"]."""
    final = None
    for value in (state.get("tool_result") or {}).values():
        if isinstance(value, dict) and value.get("final"):
            final = value["final"]
    return final


_REPORT_KEYS = ("fbm_orders", "buyer_messages", "account_health", "red_flags", "login_required")


def parse_report(final: Any) -> Optional[Dict[str, Any]]:
    """The report dict, or None. A dict without any report field (e.g. the browser
    step's {"status": "failed", "error": ...}) is not a report: rendering it gave
    an all-clear "0 red flags" page for a run that never looked."""
    report = final
    if not isinstance(report, dict):
        match = re.search(r"\{.*\}", str(final or ""), re.S)
        if not match:
            return None
        try:
            report = json.loads(match.group(0))
        except ValueError:
            return None
    if not isinstance(report, dict) or not any(k in report for k in _REPORT_KEYS):
        return None
    return report


def render_failure(final: Any) -> str:
    error = final.get("error") if isinstance(final, dict) else None
    return "\n".join([
        "# Amazon after-sales report: CHECK DID NOT COMPLETE", "",
        "The browser check failed before it could read Seller Central, so this report says",
        "nothing about orders, messages or Account Health. Nothing was sent or changed on Amazon.", "",
        f"**Error:** {error or str(final or 'the browser step returned no answer')}", "",
        "The full browser result is in raw_result.json.", "",
    ])


def _rows(items: List[Dict[str, Any]], cols: List[str]) -> List[str]:
    if not items:
        return ["_None._", ""]
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for it in items:
        cells = [str(it.get(c) if it.get(c) is not None else "").replace("|", "/").replace("\n", " ") for c in cols]
        out.append("| " + " | ".join(cells) + " |")
    return out + [""]


def render_markdown(report: Dict[str, Any]) -> str:
    flags = report.get("red_flags") or []
    order = {"high": 0, "medium": 1, "low": 2}
    flags = sorted(flags, key=lambda f: order.get(str(f.get("severity")).lower(), 3))
    orders = report.get("fbm_orders") or []
    msgs = report.get("buyer_messages") or []
    health = report.get("account_health") or {}
    lines = [
        f"# Amazon after-sales report: {report.get('store') or ''} ({report.get('marketplace') or ''})",
        "",
        f"Checked at {report.get('checked_at') or 'unknown time'}. Read-only run: nothing was sent or changed on Amazon.",
        "",
    ]
    if report.get("login_required"):
        lines += ["**Seller Central needs a sign-in.** Sign in in the automation Chrome window and run again.", ""]
    lines += [
        "## Summary", "",
        f"- Red flags: {len(flags)} ({sum(1 for f in flags if str(f.get('severity')).lower() == 'high')} high)",
        f"- Unshipped FBM orders: {len(orders)} ({sum(1 for o in orders if o.get('late'))} late)",
        f"- Buyer messages needing a reply: {len(msgs)}",
        f"- Account Health: {health.get('status') or 'not read'}"
        + (f" (AHR {health.get('ahr_score')})" if health.get("ahr_score") is not None else ""),
        "",
        "## Red flags", "",
        *_rows(flags, ["severity", "type", "detail", "deadline", "recommended_action"]),
        "## Unshipped FBM orders", "",
        *_rows([{**o, "items": ", ".join(f"{i.get('qty', '')}x {i.get('sku') or i.get('title') or ''}"
                                         for i in (o.get("items") or []))} for o in orders],
               ["order_id", "ship_by", "late", "items", "action_needed", "draft_action"]),
        "## Buyer messages", "",
        *_rows(msgs, ["order_id", "buyer", "respond_by", "urgency", "request"]),
    ]
    for m in msgs:
        if m.get("draft_reply"):
            lines += [f"**Draft reply, order {m.get('order_id') or '?'}:**", "", "> " + str(m["draft_reply"]).replace("\n", "\n> "), ""]
    lines += ["## Account Health", "",
              *_rows(health.get("metrics") or [], ["name", "value", "target", "status"]),
              *_rows(health.get("policy_items") or [], ["name", "count", "detail"])]
    details = report.get("red_flag_details") or []
    if details:
        lines += ["## Red flag details", ""]
        for d in details:
            lines += [f"### {d.get('title') or 'Untitled notice'}", "",
                      f"- Source: {d.get('source') or ''}; date: {d.get('date') or 'not shown'}; "
                      f"status: {d.get('status') or 'not shown'}",
                      f"- ASINs: {', '.join(map(str, d.get('asins') or [])) or 'none listed'}",
                      f"- Reason: {d.get('reason') or 'not shown'}",
                      f"- Amazon's action: {d.get('amazon_action') or 'not shown'}",
                      f"- Required fix: {d.get('required_fix') or 'not shown'}",
                      f"- Deadline: {d.get('deadline') or 'not shown'}; appeal available: "
                      f"{'not shown' if d.get('appeal_available') is None else d.get('appeal_available')}"]
            if d.get("excerpt"):
                lines += ["", "> " + str(d["excerpt"]).replace("\n", "\n> ")]
            if d.get("link"):
                lines += ["", f"Link: {d['link']}"]
            lines += [""]
    if report.get("notes"):
        lines += ["## Notes", "", *[f"- {n}" for n in report["notes"]], ""]
    return "\n".join(lines)


def save_amazon_run_report(state: Dict[str, Any], store_name: str = "", date: Optional[str] = None) -> Dict[str, Any]:
    final = browser_final(state)
    report = parse_report(final)
    if report is None:
        raw = final if isinstance(final, (dict, list)) else {"final": str(final or "The browser step returned no final answer.")}
        files = {"report.md": render_failure(final), "raw_result.json": raw}
        store = store_name or "unknown_store"
    else:
        store = store_name or report.get("store") or "unknown_store"
        files = {"report.md": render_markdown(report), "report.json": report}
    # A rerun on the same day replaces the earlier run's files of the other kind.
    from agent.ec_skills.reports.report_store import report_dir
    for stale in {"report.json", "raw_result.json"} - set(files):
        (report_dir("amazon", store, date) / stale).unlink(missing_ok=True)
    out = save_and_upload("amazon", store, files, date)
    out["parsed"] = report is not None
    out["login_required"] = bool((report or {}).get("login_required"))
    return out
