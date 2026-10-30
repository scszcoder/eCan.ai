"""Turn a store-check browser run's final answer into the end-of-day report.

Each platform's browser step (Amazon Seller Central, Shopify admin, ...) ends with
a JSON report. This finds it in the run state, renders report.md (titled
"N orders, N processed, N todos, N redflags") next to report.json, and saves both
through report_store (local dated folder, then S3). A failed run is reported as
"CHECK DID NOT COMPLETE", never as an all-clear, and its raw result is kept.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from agent.ec_skills.reports.report_store import day_title, report_dir, save_and_upload

# Per-platform names for the same report parts.
PLATFORMS: Dict[str, Dict[str, str]] = {
    "amazon": {"label": "Amazon", "console": "Seller Central", "orders": "fbm_orders",
               "orders_title": "Unshipped FBM orders", "messages": "buyer_messages",
               "messages_title": "Buyer messages", "items": "asins", "items_label": "ASINs"},
    "shopify": {"label": "Shopify", "console": "Shopify admin", "orders": "orders",
                "orders_title": "Unfulfilled orders", "messages": "customer_messages",
                "messages_title": "Customer messages", "items": "products", "items_label": "Products"},
    "etsy": {"label": "Etsy", "console": "Etsy Shop Manager", "orders": "orders",
             "orders_title": "Orders to ship", "messages": "buyer_messages",
             "messages_title": "Buyer messages", "items": "listings", "items_label": "Listings"},
}
_REPORT_KEYS = ("fbm_orders", "orders", "buyer_messages", "customer_messages", "account_health",
                "red_flags", "login_required")


def browser_final(state: Dict[str, Any], node: str = "") -> Any:
    """A browser step's final answer, state["tool_result"][<step>]["final"]: the named
    step's when ``node`` matches its key, else the last one that answered."""
    results = state.get("tool_result") or {}
    if node and isinstance(results.get(node), dict):
        return results[node].get("final")
    final = None
    for value in results.values():
        if isinstance(value, dict) and value.get("final"):
            final = value["final"]
    return final


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


def render_failure(final: Any, platform: str = "amazon") -> str:
    p = PLATFORMS[platform]
    error = final.get("error") if isinstance(final, dict) else None
    return "\n".join([
        f"# {p['label']} store report: CHECK DID NOT COMPLETE", "",
        f"The browser check failed before it could read {p['console']}, so this report says",
        f"nothing about orders, messages or red flags. Nothing was sent or changed on {p['label']}.", "",
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


def _orders(report: Dict[str, Any], platform: str) -> List[Dict[str, Any]]:
    return report.get(PLATFORMS[platform]["orders"]) or []


def _messages(report: Dict[str, Any], platform: str) -> List[Dict[str, Any]]:
    return report.get(PLATFORMS[platform]["messages"]) or []


def summary_title(report: Dict[str, Any], platform: str = "amazon") -> str:
    """"N orders, N processed, N todos, N redflags": orders needing no action count as
    processed; todos are orders still needing action plus messages awaiting a reply."""
    orders = _orders(report, platform)
    processed = sum(1 for o in orders if not o.get("action_needed"))
    todos = (len(orders) - processed) + len(_messages(report, platform))
    return day_title(len(orders), processed, todos, len(report.get("red_flags") or []))


def render_markdown(report: Dict[str, Any], platform: str = "amazon") -> str:
    p = PLATFORMS[platform]
    flags = report.get("red_flags") or []
    rank = {"high": 0, "medium": 1, "low": 2}
    flags = sorted(flags, key=lambda f: rank.get(str(f.get("severity")).lower(), 3))
    orders = _orders(report, platform)
    msgs = _messages(report, platform)
    health = report.get("account_health") or {}
    where = report.get("marketplace") or report.get("store_url") or ""
    lines = [
        f"# {summary_title(report, platform)}",
        "",
        f"{p['label']} store {report.get('store') or ''}{f' ({where})' if where else ''}, "
        f"checked at {report.get('checked_at') or 'unknown time'}. "
        f"Read-only run: nothing was sent or changed on {p['label']}.",
        "",
    ]
    if report.get("login_required"):
        lines += [f"**{p['console']} needs a sign-in.** Sign in in the automation Chrome window and run again.", ""]
    lines += [
        "## Summary", "",
        f"- Red flags: {len(flags)} ({sum(1 for f in flags if str(f.get('severity')).lower() == 'high')} high)",
        f"- {p['orders_title']}: {len(orders)} ({sum(1 for o in orders if o.get('late'))} late)",
        f"- {p['messages_title']} needing a reply: {len(msgs)}",
    ]
    if health:
        lines.append(f"- Account Health: {health.get('status') or 'not read'}"
                     + (f" (AHR {health.get('ahr_score')})" if health.get("ahr_score") is not None else ""))
    lines += [
        "",
        "## Red flags", "",
        *_rows(flags, ["severity", "type", "detail", "deadline", "recommended_action"]),
        f"## {p['orders_title']}", "",
        *_rows([{**o, "items": ", ".join(f"{i.get('qty', '')}x {i.get('sku') or i.get('title') or ''}"
                                         for i in (o.get("items") or []))} for o in orders],
               ["order_id", "ship_by", "late", "items", "action_needed", "draft_action"]),
        f"## {p['messages_title']}", "",
        *_rows(msgs, ["order_id", "buyer", "respond_by", "urgency", "request"]),
    ]
    for m in msgs:
        if m.get("draft_reply"):
            lines += [f"**Draft reply, order {m.get('order_id') or '?'}:**", "", "> " + str(m["draft_reply"]).replace("\n", "\n> "), ""]
    if health:
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
                      f"- {p['items_label']}: {', '.join(map(str, d.get(p['items']) or d.get('asins') or [])) or 'none listed'}",
                      f"- Reason: {d.get('reason') or 'not shown'}",
                      f"- {p['label']}'s action: {d.get('amazon_action') or d.get('platform_action') or 'not shown'}",
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


def save_store_run_report(state: Dict[str, Any], platform: str, store_name: str = "",
                          node: str = "", date: Optional[str] = None) -> Dict[str, Any]:
    final = browser_final(state, node)
    report = parse_report(final)
    checked = str((report or {}).get("store") or "").strip().lower()
    if report is not None and store_name and checked and checked != store_name.strip().lower():
        # The browser looked at another store; filing that as this store's day would mislead.
        final = {"error": f"the check read store '{report.get('store')}', not '{store_name}'", "report": report}
        report = None
    if report is None:
        raw = final if isinstance(final, (dict, list)) else {"final": str(final or "The browser step returned no final answer.")}
        files = {"report.md": render_failure(final, platform), "raw_result.json": raw}
        store = store_name or "unknown_store"
    else:
        store = store_name or report.get("store") or "unknown_store"
        files = {"report.md": render_markdown(report, platform), "report.json": report}
    # A rerun on the same day replaces the earlier run's files of the other kind.
    for stale in {"report.json", "raw_result.json"} - set(files):
        (report_dir(platform, store, date) / stale).unlink(missing_ok=True)
    out = save_and_upload(platform, store, files, date)
    out["parsed"] = report is not None
    out["login_required"] = bool((report or {}).get("login_required"))
    out["title"] = summary_title(report, platform) if report is not None else "CHECK DID NOT COMPLETE"
    return out
