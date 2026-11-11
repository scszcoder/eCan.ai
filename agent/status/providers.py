"""Status providers: the detailed status an agent, or a team of agents, reports about itself.

A provider is ``fn(ctx: StatusContext) -> dict`` returning (part of) a status report
(docs/AGENT_STATUS_PROBING_DESIGN.md section 4.1): health, headline, progress with a
percentage, rate, current work, recent results, anomalies. It is registered for skills;
every local agent running one of them is covered, and a provider with a ``team`` reports
once for all of them together (a crawl's coordinator and crawlers). Providers are read-only
and answer within ``ctx.budget_s``; one that doesn't is cut off and the report falls back to
presence and tasks with health "unknown".

An agent without a provider still gets a report: presence (running or not), its tasks, and
whatever it wrote to the ``utils.agent_status`` ledger.
"""
from __future__ import annotations

import importlib
import json
import socket
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from utils.logger_helper import logger_helper as logger

V = 1
BUDGET_S = 10.0
REPORT_MAX_BYTES = 16_000
CAPABILITIES_MAX_BYTES = 8_000
HEALTH = ("ok", "degraded", "blocked", "stalled", "down", "unknown")
# provider modules shipped with the app; each calls register() when imported
BUILTIN = ("agent.ec_skills.product_research.status",)


@dataclass(frozen=True)
class Provider:
    name: str
    fn: Callable[["StatusContext"], dict]
    skills: Tuple[str, ...]                  # skill names, or prefixes: "product_crawler" covers product_crawler_00
    team: Optional[str] = None
    team_name: str = ""
    description: str = ""
    roots: Optional[Callable[[dict], List[Path]]] = None    # folders status_diagnose may read files from


@dataclass
class StatusContext:
    subject: Dict[str, Any]                  # {"kind": "agent" | "team", "id", "name"}
    members: List[Dict[str, Any]]            # the local agents covered (see local_agents)
    since: Optional[str] = None              # ISO time of the asker's last report; None = recent hour
    depth: str = "summary"                   # summary | full
    budget_s: float = BUDGET_S
    inputs: Dict[str, Any] = field(default_factory=dict)


_providers: Dict[str, Provider] = {}
_loaded = False
_lock = threading.Lock()


def register(name: str, fn: Callable[[StatusContext], dict], *, skills, team: Optional[str] = None,
             team_name: str = "", description: str = "",
             roots: Optional[Callable[[dict], List[Path]]] = None) -> None:
    _providers[name] = Provider(name, fn, tuple(skills), team, team_name or team or name, description, roots)


def providers() -> Dict[str, Provider]:
    global _loaded
    with _lock:
        if not _loaded:
            _loaded = True
            for mod in BUILTIN:
                try:
                    importlib.import_module(mod)
                except Exception as e:
                    logger.warning(f"[agent-status] status provider {mod} not loaded: {e}")
        return dict(_providers)


def _covers(prefix: str, skill: str) -> bool:
    return skill == prefix or skill.startswith(prefix + "_")


def provider_for(skills: List[str]) -> Optional[Provider]:
    return next((p for p in providers().values() if any(_covers(s, k) for s in p.skills for k in skills)), None)


# ── this machine's agents ───────────────────────────────────────────────────────

def _name(x: Any) -> str:
    return str(getattr(x, "name", "") or "")


def _tasks(agent: Any) -> List[Dict[str, Any]]:
    from agent.ec_tasks.progress import seconds_since_progress
    out = []
    for t in list(getattr(agent, "tasks", None) or [])[:20]:
        tid = str(getattr(t, "id", "") or "")
        age = seconds_since_progress(tid) if tid else None
        out.append({"id": tid, "name": _name(t), "skill": _name(getattr(t, "skill", None)),
                    "status": str(getattr(t, "status", "") or ""),
                    "progress_age_s": None if age is None else int(age)})
    return out


def local_agents(mainwin: Any) -> List[Dict[str, Any]]:
    """Presence facts of every agent in this app: id, name, running, skills, team, tasks, ledger."""
    from utils import agent_status as ledger
    ready = ledger.snapshot_all()
    out = []
    for a in list(getattr(mainwin, "agents", None) or []):
        card = getattr(a, "card", None)
        aid, name = str(getattr(card, "id", "") or ""), _name(card)
        tasks = _tasks(a)
        skills = sorted({_name(s) for s in getattr(a, "skills", None) or []} | {t["skill"] for t in tasks} - {""})
        p = provider_for(skills)
        out.append({"id": aid, "name": name, "running": bool(getattr(a, "_running", False)),
                    "status": str(getattr(a, "status", "") or ""), "skills": skills,
                    "team": p.team if p else None, "provider": p.name if p else None, "tasks": tasks,
                    "readiness": ready.get(aid) or ready.get(name) or None})
    return out


def machine_info(machine_id: str) -> Dict[str, Any]:
    return {"id": machine_id, "name": socket.gethostname(), "build": str(getattr(logger, "_build_tag", "") or "")}


def capabilities(mainwin: Any) -> Dict[str, Any]:
    """What the machine record announces (heartbeat): its agents and teams, at most 8 KB."""
    agents, teams = local_agents(mainwin), {}
    for a in agents:
        if a["team"]:
            p = providers()[a["provider"]]
            teams.setdefault(a["team"], {"id": a["team"], "name": p.team_name, "description": p.description,
                                         "members": []})["members"].append(a["id"])
    caps = {"v": V, "status": {"v": V, "intents": ["get_agent_status", "status_diagnose"]},
            "agents": [{"id": a["id"], "name": a["name"], "running": a["running"], "skills": a["skills"],
                        "team": a["team"], "has_provider": bool(a["provider"])} for a in agents],
            "teams": list(teams.values())}
    if _size(caps) > CAPABILITIES_MAX_BYTES:
        for a in caps["agents"]:
            a.pop("skills", None)
    while _size(caps) > CAPABILITIES_MAX_BYTES and caps["agents"]:
        caps["agents"].pop()
        caps["agents_truncated"] = caps.get("agents_truncated", 0) + 1
    return caps


# ── subjects and reports ─────────────────────────────────────────────────────────

def resolve(subjects: Optional[List[Dict[str, Any]]], agents: List[Dict[str, Any]]) -> List[Tuple[dict, list]]:
    """[(subject, members)] for the asked subjects; no subjects = every team and every agent
    outside a team. A subject not on this machine comes back with no members."""
    if not subjects:
        out, done = [], set()
        for a in agents:
            if a["team"] and a["team"] not in done:
                done.add(a["team"])
                out.append(({"kind": "team", "id": a["team"], "name": providers()[a["provider"]].team_name},
                            [m for m in agents if m["team"] == a["team"]]))
            elif not a["team"]:
                out.append(({"kind": "agent", "id": a["id"], "name": a["name"]}, [a]))
        return out
    out = []
    for s in subjects:
        s = s if isinstance(s, dict) else {"name": str(s)}
        key = str(s.get("id") or s.get("name") or "").strip().lower()
        if s.get("kind") == "team":
            members = [a for a in agents if (a["team"] or "").lower() == key]
            name = providers()[members[0]["provider"]].team_name if members else s.get("name") or key
            out.append(({"kind": "team", "id": s.get("id") or s.get("name"), "name": name}, members))
        else:
            members = [a for a in agents if key and key in (a["id"].lower(), a["name"].lower())]
            asked = str(s.get("id") or s.get("name") or "")       # echoed as asked
            out.append(({"kind": "agent", "id": members[0]["id"] if members else asked,
                         "name": members[0]["name"] if members else s.get("name") or asked}, members))
    return out


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def since_local(since: Optional[str]) -> Optional[str]:
    """An ISO time as local 'YYYY-mm-dd HH:MM:SS' (how most agents stamp their files)."""
    if not since:
        return None
    try:
        t = datetime.fromisoformat(str(since).replace("Z", "+00:00"))
        return (t.astimezone() if t.tzinfo else t).strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _call(fn: Callable, ctx: StatusContext) -> Tuple[Optional[dict], Optional[str]]:
    """Run a provider in its own daemon thread: (report, None), or (None, why) on error/timeout.
    A provider that overruns is left to finish on its own; nothing waits for it."""
    box: Dict[str, Any] = {}

    def run():
        try:
            box["rep"] = fn(ctx) or {}
        except Exception as e:
            box["err"] = f"{type(e).__name__}: {e}"[:300]
    t = threading.Thread(target=run, daemon=True, name="agent-status-provider")
    t.start()
    t.join(ctx.budget_s)
    if t.is_alive():
        return None, "timeout"
    return box.get("rep"), box.get("err")


def report_for(subject: dict, members: List[dict], *, machine: dict, depth: str = "summary",
               since: Optional[str] = None, budget_s: float = BUDGET_S, inputs: Optional[dict] = None) -> dict:
    """The status report for one subject (blocking, at most ~budget_s)."""
    rep: Dict[str, Any] = {"v": V, "subject": {**subject, "members": [m["name"] or m["id"] for m in members]},
                           "machine": machine, "as_of": now_iso(), "since": since}
    if not members:
        return clamp({**rep, "health": "down", "headline": "not on this machine",
                      "anomalies": [{"id": "not-on-this-machine", "severity": "error", "needs_human": False,
                                     "what": f"no {subject.get('kind', 'agent')} {subject.get('name') or subject.get('id')!r} "
                                             f"on {machine.get('name') or 'this machine'}"}]})
    rep["presence"] = [{k: m[k] for k in ("id", "name", "running", "status", "tasks")} for m in members]
    prov = providers().get(next((m["provider"] for m in members if m["provider"]), "") or "")
    if prov is None:
        return clamp({**rep, **_ledger_report(members)})
    got, err = _call(prov.fn, StatusContext(subject, members, since, depth, budget_s, inputs or {}))
    if got is None:
        why = (f"the status provider took longer than {budget_s:g} s" if err == "timeout" else
               f"the status provider failed: {err}")
        return clamp({**rep, "health": "unknown", "headline": why,
                      "anomalies": [{"id": "status-provider-" + ("timeout" if err == "timeout" else "error"),
                                     "severity": "warn", "needs_human": False, "what": why}]})
    rep.update({k: v for k, v in got.items() if k not in ("v", "subject", "machine", "as_of", "presence")})
    if rep.get("health") not in HEALTH:
        rep["health"] = "ok"
    rep["anomalies"] = list(rep.get("anomalies") or [])
    return clamp(rep)


def _ledger_report(members: List[dict]) -> dict:
    """The report of agents without a provider: running or not, plus their ledger."""
    up = sum(1 for m in members if m["running"])
    ready = {m["name"] or m["id"]: m["readiness"] for m in members if m["readiness"]}
    return {"health": "ok" if up else "down",
            "headline": (f"{up} of {len(members)} running" if len(members) > 1 else
                         "running" if up else "not running"),
            "anomalies": [], "metrics": {"readiness": ready} if ready else {}}


def _size(obj: Any) -> int:
    return len(json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8"))


def clamp(rep: dict, limit: int = REPORT_MAX_BYTES) -> dict:
    """Keep a report under *limit* bytes: trim recent, then detail, metrics, presence tasks."""
    if _size(rep) <= limit:
        return rep
    rep = dict(rep)
    recent = list(rep.get("recent") or [])
    while recent and _size({**rep, "recent": recent}) > limit:
        recent = recent[:len(recent) // 2] if len(recent) > 1 else []
    if len(recent) < len(rep.get("recent") or []):
        rep["recent"], rep["recent_truncated"] = recent, len(rep.get("recent") or []) - len(recent)
    for key in ("detail", "metrics"):
        if _size(rep) > limit and key in rep:
            rep[key] = "(dropped: report too large)" if key == "detail" else {}
    if _size(rep) > limit:
        rep["presence"] = [{k: v for k, v in p.items() if k != "tasks"} for p in rep.get("presence") or []]
    return rep


def anomaly_key(rep: dict, anomaly: dict) -> str:
    return f"{rep['subject'].get('kind')}:{rep['subject'].get('id')}:{anomaly.get('id')}"


def roots_for(members: List[dict], inputs: Optional[dict] = None) -> List[Path]:
    """Folders status_diagnose may read files from for these agents."""
    prov = providers().get(next((m["provider"] for m in members if m["provider"]), "") or "")
    try:
        return [Path(p) for p in (prov.roots(inputs or {}) if prov and prov.roots else [])]
    except Exception:
        return []
