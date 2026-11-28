"""A store's shipping work for one day, kept as work_status.json in that day's label folder.

The run writes its to-do list first (every step "todo"), marks each step as it ends, and
records per order what was done: label bought or reprinted, filed, sent to the printer.
A rerun after an interruption reads it back, so nothing done is done twice (no second
label, no second print) and nothing left undone is skipped.
"""
import json
import os
import time
from typing import Any, Dict, List

FILE = "work_status.json"


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def load(day_dir: str) -> Dict[str, Any]:
    try:
        with open(os.path.join(day_dir, FILE), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(day_dir: str, data: Dict[str, Any]) -> None:
    os.makedirs(day_dir, exist_ok=True)
    tmp = os.path.join(day_dir, FILE + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, os.path.join(day_dir, FILE))


def start_run(day_dir: str, store: str, steps: List[str]) -> Dict[str, Any]:
    """Begin a run: a new to-do list for its steps; what earlier runs did to orders is kept."""
    data = load(day_dir)
    data.setdefault("store", store)
    data.setdefault("orders", {})
    data["runs"] = (data.get("runs") or []) + [{"started": _now(), "finished": None}]
    data["steps"] = {s: {"status": "todo"} for s in steps}
    _save(day_dir, data)
    return data


def mark_step(day_dir: str, step: str, status: str, **info) -> None:
    data = load(day_dir)
    data.setdefault("steps", {})[step] = {"status": status, "at": _now(), **info}
    if all((s or {}).get("status") != "todo" for s in data["steps"].values()) and data.get("runs"):
        data["runs"][-1]["finished"] = _now()
    _save(day_dir, data)


def update_order(day_dir: str, order_id: str, **fields) -> Dict[str, Any]:
    """Merge *fields* into the order's entry (empty values do not erase earlier ones)."""
    data = load(day_dir)
    entry = data.setdefault("orders", {}).setdefault(str(order_id), {})
    entry.update({k: v for k, v in fields.items() if v not in (None, "")})
    entry["updated"] = _now()
    _save(day_dir, data)
    return entry


def order(day_dir: str, order_id: str) -> Dict[str, Any]:
    return (load(day_dir).get("orders") or {}).get(str(order_id)) or {}


def handled_before(label_root: str, order_id: str, today: str, days: int = 14):
    """(day, entry) of the latest earlier day whose label folder filed and printed this order, or None.

    A store keeps listing an order with a bought label until it ships, so the next day's run saw
    yesterday's label again and printed it a second time (Etsy, 2026-11-24)."""
    for day in sorted(earlier_days(label_root, today, days), reverse=True):
        entry = order(os.path.join(label_root, day), order_id)
        if entry.get("printed"):
            return day, entry
    return None


def handled_recently(label_root: str, today: str, days: int = 14) -> List[str]:
    """Orders filed and printed on one of the *days* before *today*."""
    done = set()
    for day in earlier_days(label_root, today, days):
        done |= {k for k, v in (load(os.path.join(label_root, day)).get("orders") or {}).items() if v.get("printed")}
    return sorted(done)


def filed_unprinted(label_root: str, today: str, days: int = 3) -> List[tuple]:
    """(day folder, order id, file) for labels filed today or on one of the *days* before but never
    printed. Once its label is bought the store counts the order as fulfilled and stops listing it,
    so nothing else would print it: eCan crashed between filing and printing #1094 (2026-11-25),
    and a print that failed in the morning run left #1095 unprinted all day (2026-11-27)."""
    out = []
    today_dir = [today] if os.path.isdir(os.path.join(label_root, today)) else []
    for day in sorted(earlier_days(label_root, today, days)) + today_dir:
        day_dir = os.path.join(label_root, day)
        for oid, v in (load(day_dir).get("orders") or {}).items():
            if v.get("file") and not v.get("printed") and os.path.exists(v["file"]):
                out.append((day_dir, oid, v["file"]))
    return out


def earlier_days(label_root: str, today: str, days: int) -> List[str]:
    """The dated folders (YYYY-MM-DD) under *label_root* from the *days* before *today*."""
    from datetime import date, timedelta
    first = (date.fromisoformat(today) - timedelta(days=days)).isoformat()
    try:
        names = os.listdir(label_root)
    except OSError:
        return []
    return [n for n in names if len(n) == 10 and first <= n < today and n[4] == "-" and n[7] == "-"]
