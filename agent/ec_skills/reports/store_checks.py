"""The latest saved store-check report of each store, for the cloud Manager.

A store check saves C:\\reports\\<platform>\\<folder>\\<date>\\ (report_store). The folder is
the name the skill was given (a store name, a shop handle, a seller id), not always the
store id, so a folder belongs to a store when:
  1. its run.json names the store id (written by store checks since 2026-11-12), or
  2. it is the store's id or name, or a part of one of its URLs (admin.shopify.com/store/<x>), or
  3. the platform has one store and one folder left over.

Only store-level facts are returned: counts, red flags, account health. No buyer names,
messages or order lines.
"""
from __future__ import annotations

import json
import re
from datetime import date as _date
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent.ec_skills.reports.report_store import reports_root, safe_part
from agent.ec_skills.reports.store_report import PLATFORMS

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TEXT_MAX = 500
_PROPOSALS_MAX = 30


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _days(folder: Path) -> List[Path]:
    """Dated subfolders holding a report, newest first."""
    out = [d for d in folder.iterdir() if d.is_dir() and _DATE.match(d.name)
           and ((d / "report.json").exists() or (d / "raw_result.json").exists())]
    return sorted(out, key=lambda d: d.name, reverse=True)


def _names(store: Dict[str, Any]) -> set:
    names = {str(store.get("store_id") or ""), str(store.get("name") or "")}
    for url in store.get("store_urls") or []:
        names.update(p for p in re.split(r"[/.?=&:]+", str(url)) if p)
    return {safe_part(n).lower() for n in names if n}


def _owner(folder: Path) -> str:
    for day in _days(folder):
        sid = (_read_json(day / "run.json") or {}).get("store_id")
        if sid:
            return str(sid)
    return ""


def match_folders(stores: List[Dict[str, Any]], root: Optional[Path] = None) -> Dict[str, Path]:
    """{store_id: its report folder}."""
    root = root or reports_root()
    found: Dict[str, Path] = {}
    by_platform: Dict[str, List[Dict[str, Any]]] = {}
    for s in stores:
        by_platform.setdefault(str(s.get("platform") or "").lower(), []).append(s)
    for platform, members in by_platform.items():
        base = root / safe_part(platform)
        folders = [f for f in base.iterdir() if f.is_dir() and _days(f)] if base.is_dir() else []
        left = list(folders)
        for f in list(left):                                   # 1. run.json names the store
            sid = _owner(f)
            if sid and any(s.get("store_id") == sid for s in members) and sid not in found:
                found[sid] = f
                left.remove(f)
        for s in members:                                      # 2. a name the store goes by
            if s.get("store_id") in found:
                continue
            names = _names(s)
            hit = next((f for f in left if f.name.lower() in names), None)
            if hit:
                found[s["store_id"]] = hit
                left.remove(hit)
        unmatched = [s for s in members if s.get("store_id") not in found]
        if len(members) == 1 and unmatched and len(left) == 1:  # 3. the only one there
            found[unmatched[0]["store_id"]] = left[0]
    return found


def _clip(value: Any) -> Any:
    return value[:_TEXT_MAX] if isinstance(value, str) else value


def summarize(day: Path, platform: str) -> Dict[str, Any]:
    """One day's report: complete or not, counts, red flags, account health."""
    today = _date.today()
    age = (today - _date.fromisoformat(day.name)).days
    upload = (_read_json(day / "upload_status.json") or {}).get("status") or "not tried"
    report = _read_json(day / "report.json")
    if not isinstance(report, dict):
        md = (day / "report.md").read_text(encoding="utf-8", errors="replace") if (day / "report.md").exists() else ""
        error = next((ln.split("**Error:**", 1)[1].strip() for ln in md.splitlines() if "**Error:**" in ln), "")
        return {"date": day.name, "age_days": age, "complete": False,
                "title": "CHECK DID NOT COMPLETE", "error": _clip(error), "cloud_upload": upload}
    names = PLATFORMS.get(platform) or PLATFORMS["shopify"]
    orders = report.get(names["orders"]) or report.get("orders") or []
    msgs = report.get(names["messages"]) or report.get("buyer_messages") or report.get("customer_messages") or []
    flags = [{k: _clip(f.get(k)) for k in ("severity", "type", "detail", "deadline", "recommended_action")
              if f.get(k) not in (None, "")} for f in report.get("red_flags") or [] if isinstance(f, dict)]
    details = [{k: _clip(d.get(k)) for k in ("title", "status", "reason", "required_fix", "deadline")
                if d.get(k) not in (None, "")} for d in report.get("red_flag_details") or [] if isinstance(d, dict)]
    out = {"date": day.name, "age_days": age, "complete": True, "checked_at": report.get("checked_at"),
           "login_required": bool(report.get("login_required")),
           "orders_needing_action": sum(1 for o in orders if isinstance(o, dict) and o.get("action_needed")),
           "orders_listed": len(orders), "messages_awaiting_reply": len(msgs),
           "red_flags": flags, "cloud_upload": upload}
    if details:
        out["red_flag_details"] = details
    proposals = [{k: _clip(p.get(k)) for k in ("id", "kind", "summary", "numbers", "status") if p.get(k) not in (None, "")}
                 for p in report.get("proposals") or [] if isinstance(p, dict)]
    if proposals:                       # drafted changes waiting for the owner's approval
        out["proposals"] = proposals[:_PROPOSALS_MAX]
    health = report.get("account_health")
    if isinstance(health, dict) and health:
        out["account_health"] = {k: health.get(k) for k in ("status", "ahr_score") if health.get(k) is not None}
    return out


def latest_reports(stores: List[Dict[str, Any]], store_id: str = "", days: int = 1,
                   root: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Per store: its newest ``days`` reports, or ``checked: False`` when there are none."""
    if store_id:
        stores = [s for s in stores if s.get("store_id") == store_id]
    folders = match_folders(stores, root)
    out = []
    for s in stores:
        entry = {"store_id": s.get("store_id"), "name": s.get("name"), "platform": s.get("platform")}
        folder = folders.get(s.get("store_id"))
        reports = [summarize(d, str(s.get("platform") or "").lower()) for d in _days(folder)[:max(1, days)]] \
            if folder else []
        entry.update({"checked": bool(reports), "reports": reports} if reports else
                     {"checked": False, "note": "no saved store check for this store yet"})
        other = _other_reports(s, root or reports_root(), days)
        if other:
            entry["other_reports"] = other
        out.append(entry)
    return out


def _other_reports(store: Dict[str, Any], root: Path, days: int) -> Dict[str, List[Dict[str, Any]]]:
    """{kind: newest reports} a store's other skills filed for it (e.g. google_ads), found by
    the store id in their run.json."""
    own = safe_part(str(store.get("platform") or "").lower())
    out: Dict[str, List[Dict[str, Any]]] = {}
    for base in (d for d in root.iterdir() if d.is_dir() and d.name != own) if root.is_dir() else []:
        for folder in (f for f in base.iterdir() if f.is_dir()):
            if _owner(folder) == store.get("store_id"):
                out[base.name] = [summarize(d, base.name) for d in _days(folder)[:max(1, days)]]
    return out
