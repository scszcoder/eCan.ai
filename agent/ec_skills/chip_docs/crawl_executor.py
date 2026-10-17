"""Chip-docs crawl coordinator, Execute phase, as plain code: no LLM.

2026-10-12: the gpt-6-luna executor spent 100-660k tokens per round on pure
bookkeeping, let status.md drift from what workers were actually doing, reused
batch ids and once put a URL where the category belonged. Each round here:
apply a worker's report, reclaim stale batches, hand a batch to every idle
worker, write status.md and mirror it to the NAS.

Files under ``<docs_root>/<vendor>/``:
- ``sub_plans/*.md``: ``| # | part | product page URL | category |`` (written by the planner)
- ``status.md``: one row per part, plus a ``## Workers`` table

Once every part is done, the documents' HTML editions are saved too (``html_docs.crawl``).
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

STALE_AFTER = timedelta(minutes=30)
MAX_ATTEMPTS = 3
MAX_ABORTS = 20  # an aborted run comes back within ~1 min, so this is ~20 min of outage per batch
ABORTED = "crawler run aborted"  # what the crawler skill's RoundEnd reports
ABORTED_NOTE = "aborted x"
PART_COLS = ["part", "product page URL", "sub_plan", "state", "worker", "docs", "updated", "attempts", "note"]
WORKER_COLS = ["worker", "state", "batch id", "assigned at"]


def _cells(line: str) -> list[str] | None:
    line = line.strip()
    if not (line.startswith("|") and line.endswith("|")):
        return None
    cells = [c.strip() for c in line[1:-1].split("|")]
    if all(set(c) <= set("-: ") for c in cells):  # |---|---|
        return None
    return cells


def load_sub_plans(sub_plan_dir: Path) -> list[dict]:
    """Every sub-plan part, in file order; the first occurrence of a part wins."""
    parts, seen = [], set()
    for f in sorted(sub_plan_dir.glob("*.md")):
        for line in f.read_text(encoding="utf-8").splitlines():
            c = _cells(line)
            if not c or len(c) < 4 or c[1].lower() == "part" or not c[1]:
                continue
            key = c[1].upper()
            if key in seen:
                continue
            seen.add(key)
            parts.append({"part": c[1], "url": c[2], "sub_plan": f.stem,
                          "category": c[3].split(">")[-1].strip()})
    return parts


def parse_status(text: str) -> tuple[list[dict], dict[str, dict]]:
    rows, workers, in_workers = [], {}, False
    for line in text.splitlines():
        if line.strip().lower().startswith("## workers"):
            in_workers = True
            continue
        c = _cells(line)
        if not c or c[0].lower() in ("part", "worker"):
            continue
        if in_workers:
            c += [""] * (len(WORKER_COLS) - len(c))
            workers[c[0]] = {"state": c[1] or "idle", "batch": c[2], "at": c[3]}
        elif len(c) >= 7:
            c += [""] * (len(PART_COLS) - len(c))
            rows.append(dict(zip(PART_COLS, c)))
    return rows, workers


def render_status(rows: list[dict], workers: dict[str, dict], vendor: str) -> str:
    out = [f"# {vendor} crawl status", "", "| " + " | ".join(PART_COLS) + " |",
           "|" + "---|" * len(PART_COLS)]
    out += ["| " + " | ".join(str(r.get(k, "")) for k in PART_COLS) + " |" for r in rows]
    out += ["", "## Workers", "| " + " | ".join(WORKER_COLS) + " |", "|" + "---|" * len(WORKER_COLS)]
    out += [f"| {w} | {v['state']} | {v['batch']} | {v['at']} |" for w, v in sorted(workers.items())]
    return "\n".join(out) + "\n"


def _parse_time(s: str) -> datetime | None:
    try:
        return datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return None


def run_round(rows: list[dict], workers: dict[str, dict], plan: list[dict], report: dict | None,
              worker_names: list[str], batch_size: int, vendor: str, docs_root: str,
              coordinator: str, send: Callable[[str, dict], bool], now: datetime) -> dict:
    """One Execute round, mutating rows/workers in place. Returns counts and what happened."""
    stamp = now.isoformat(timespec="seconds")
    by_part = {r["part"].upper(): r for r in rows}
    for p in plan:  # the plan can grow; never add a part twice
        if p["part"].upper() not in by_part:
            r = {k: "" for k in PART_COLS} | {"part": p["part"], "product page URL": p["url"],
                                              "sub_plan": p["sub_plan"], "state": "pending", "updated": stamp}
            rows.append(r)
            by_part[p["part"].upper()] = r
    category = {p["part"].upper(): p["category"] for p in plan}
    log = []

    def release(r: dict) -> None:
        r.update(state="pending", worker="", updated=stamp)

    # 1. apply a worker report, only for a batch that is still out (else it is a duplicate)
    if report and report.get("type") == "scrape_report":
        owner = next((w for w, v in workers.items()
                      if v["state"] == "busy" and v["batch"] == report.get("batch_id")), None)
        if owner is None:
            log.append(f"ignored report for {report.get('batch_id')} (not outstanding)")
        else:
            for item in report.get("parts") or []:
                r = by_part.get(str((item or {}).get("part") or "").upper())
                if not r or r["state"] != "assigned" or r["worker"] != owner:
                    continue
                docs = int(item.get("docs") or 0) if str(item.get("docs") or "0").isdigit() else 0
                if str(item.get("error") or "").startswith(ABORTED):
                    # 2026-10-12: an internet outage aborted every run within a minute and
                    # burned 203 parts' attempts untried; an aborted run says nothing about
                    # the part, so requeue it and give up only after MAX_ABORTS
                    aborts = int(r["note"][len(ABORTED_NOTE):] or 0) + 1 if r["note"].startswith(ABORTED_NOTE) else 1
                    r.update(state="pending", worker="", note=f"{ABORTED_NOTE}{aborts}", updated=stamp)
                    if aborts >= MAX_ABORTS:
                        r.update(state="failed", attempts=str(MAX_ATTEMPTS))
                elif item.get("state") == "done" and docs > 0:
                    r.update(state="done", docs=str(docs), note="", updated=stamp)
                else:  # a done part with 0 docs is a failure
                    tries = int(r.get("attempts") or 0) + 1
                    r.update(state="failed", docs="0", attempts=str(tries), updated=stamp,
                             note=str(item.get("error") or "no documents")[:120].replace("|", "/"))
            for r in rows:  # parts of the batch the report left out go back to the queue
                if r["state"] == "assigned" and r["worker"] == owner:
                    release(r)
            workers[owner] = {"state": "idle", "batch": "", "at": stamp}
            log.append(f"applied {report.get('batch_id')} from {owner}")

    # 2. reclaim stale batches, and any assigned row no busy worker owns (drift)
    for w, v in workers.items():
        at = _parse_time(v["at"])
        if v["state"] == "busy" and (at is None or now - at > STALE_AFTER):
            workers[w] = {"state": "idle", "batch": "", "at": stamp}
            log.append(f"reclaimed stale batch {v['batch']} from {w}")
    busy = {w for w, v in workers.items() if v["state"] == "busy"}
    for r in rows:
        if r["state"] == "assigned" and r["worker"] not in busy:
            release(r)

    # 3. a batch for every idle worker: same sub-plan, pending parts first, then
    # failed ones under MAX_ATTEMPTS (2026-10-13: retry failures only once the rest is done)
    def retryable(r: dict) -> bool:
        return r["state"] == "failed" and int(r.get("attempts") or 0) < MAX_ATTEMPTS

    for w in worker_names:
        workers.setdefault(w, {"state": "idle", "batch": "", "at": ""})
        if workers[w]["state"] != "idle":
            continue
        pool = [r for r in rows if r["state"] == "pending"] or [r for r in rows if retryable(r)]
        if not pool:
            break
        picked = [r for r in pool if r["sub_plan"] == pool[0]["sub_plan"]][:batch_size]
        first = picked[0]
        batch_id = f"{first['sub_plan']}-{first['part']}"
        batch = {"type": "scrape_batch", "batch_id": batch_id, "part_vendor": vendor, "docs_root": docs_root,
                 "coordinator": coordinator,
                 "parts": [{"part": r["part"], "url": r["product page URL"],
                            "category": category.get(r["part"].upper(), "")} for r in picked]}
        if not send(w, batch):
            log.append(f"send to {w} failed")
            continue
        for r in picked:
            r.update(state="assigned", worker=w, updated=stamp)
        workers[w] = {"state": "busy", "batch": batch_id, "at": stamp}
        log.append(f"sent {batch_id} ({len(picked)} parts) to {w}")

    counts = {s: sum(r["state"] == s for r in rows) for s in ("pending", "assigned", "done", "failed")}
    all_done = counts["pending"] == 0 and counts["assigned"] == 0 and not any(retryable(r) for r in rows)
    return {"all_done": all_done, "work_done": True, "summary": "; ".join(log) or "nothing to do", **counts}


_html_crawl: threading.Thread | None = None
_sent_batches: set[str] = set()  # batch ids this app process handed out


def forget_batches_of_earlier_runs(workers: dict[str, dict], sent: set[str]) -> None:
    """Mark busy workers whose batch this process never sent as stale. 2026-10-16: after a
    restart, batches sent by the old app 10 minutes earlier looked busy; no worker would
    report them, and as rounds only follow a message, the coordinator waited forever."""
    for v in workers.values():
        if v["state"] == "busy" and v["batch"] not in sent:
            v["at"] = ""  # run_round reclaims a busy worker with no assignment time


def start_html_crawl(root: Path) -> bool:
    """Save the HTML editions of every crawled document in the background, unless that is
    already running. ``html_docs.crawl`` resumes from its log, so starting it again is safe."""
    global _html_crawl
    if _html_crawl is not None and _html_crawl.is_alive():
        return False
    from agent.ec_skills.chip_docs import html_docs
    from utils.logger_helper import logger_helper as logger

    def run() -> None:
        # main.py sets WindowsSelectorEventLoopPolicy, whose loops can't start Chrome
        loop_factory = asyncio.ProactorEventLoop if sys.platform == "win32" else None
        try:
            with asyncio.Runner(loop_factory=loop_factory) as runner:
                runner.run(html_docs.crawl(root, root / "raw" / "_html_browser_profile"))
        except Exception as e:
            logger.warning(f"[crawl_executor] HTML editions crawl failed: {e!r}")

    _html_crawl = threading.Thread(target=run, name="ChipHtmlCrawl", daemon=True)
    _html_crawl.start()
    return True


def parse_message(text: str) -> dict | None:
    """A worker message as a dict. Workers type their reports, and 2026-10-12 one
    wrote `{\\"part"...` mid-message, so plain json.loads dropped three reports and
    stalled their workers; repair near-JSON before giving up."""
    if not isinstance(text, str) or "{" not in text:
        return None
    try:
        msg = json.loads(text)
    except ValueError:
        import json_repair
        msg = json_repair.loads(text.replace('\\"', '"'))
    return msg if isinstance(msg, dict) else None


def node_main(state: dict) -> dict:
    """Body of the coordinator skill's Executor code node."""
    from app_context import AppContext
    from agent.mcp.server.chat_utils.chat_tools import list_chat_agents, send_chat
    from agent.ec_skills.nas import ugreen_nas
    from utils.logger_helper import logger_helper as logger

    refs = state.get("prompt_refs") or {}
    vendor, docs_root = refs.get("part_vendor") or "", (refs.get("docs_root") or "").rstrip("/\\")
    batch_size = int(refs.get("batch_size") or 3)
    # Cap on crawlers given work; each runs its own Chrome, and 3 saturated a 4-core machine.
    max_workers = int(refs.get("max_workers") or os.environ.get("ECAN_CRAWL_MAX_WORKERS") or 0)
    me = (state.get("attributes") or {}).get("agent_id") or ""
    root = Path(docs_root) / vendor
    status_path = root / "status.md"
    mainwin = AppContext.get_main_window()

    report = parse_message(state.get("input") or "")
    if report is None and "scrape_report" in str(state.get("input") or ""):
        logger.warning(f"[crawl_executor] unreadable report: {str(state.get('input'))[:300]}")
    rows, workers = parse_status(status_path.read_text(encoding="utf-8")) if status_path.exists() else ([], {})
    agents = (list_chat_agents(mainwin, {"filter_name": refs.get("worker_filter") or "", "exclude_self": me})
              or {}).get("agents") or []
    me_name = next((a["name"] for a in (list_chat_agents(mainwin, {"filter_name": me}) or {}).get("agents") or []
                    if a["id"] == me), "")

    def send(worker: str, batch: dict) -> bool:
        res = send_chat(mainwin, {"sender_agent_id": me, "recipient_agent_name": worker,
                                  "message": json.dumps(batch, ensure_ascii=False)})
        ok = bool((res or {}).get("success"))
        if ok:
            _sent_batches.add(batch["batch_id"])
        return ok

    forget_batches_of_earlier_runs(workers, _sent_batches)

    worker_names = sorted(a["name"] for a in agents if a["id"] != me)
    if max_workers > 0:
        worker_names = worker_names[:max_workers]
    result = run_round(rows, workers, load_sub_plans(root / "sub_plans"), report,
                       worker_names, batch_size, vendor,
                       docs_root, me_name, send, datetime.now(timezone.utc))
    status_path.write_text(render_status(rows, workers, vendor), encoding="utf-8")
    try:
        ugreen_nas.nas_upload(str(status_path), f"{vendor}/status.md")
    except Exception as e:  # the local status.md is the source of truth
        logger.warning(f"[crawl_executor] NAS mirror failed: {e}")
    if result["all_done"] and start_html_crawl(root):
        result["summary"] += "; started the HTML editions crawl"
    logger.info(f"[crawl_executor] {result}")
    state.setdefault("result", {})["llm_result"] = result
    return state
