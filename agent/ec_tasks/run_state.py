"""What the task list shows besides running/idle: a run waiting for a resource
(and behind whom), a scheduled run held for its prerequisites, the last missed
run.  Read-only view over resource_gate, task_deps and task metadata."""
from __future__ import annotations

from typing import Any, Dict, Iterable

from agent.ec_tasks import resource_gate, task_deps


def _resource_label(key: str) -> str:
    # "agent:<id>/browser:<profile>" -> "browser:<profile>"; "user:<name>" -> "<name>"
    tail = key.split("/", 1)[1] if key.startswith("agent:") and "/" in key else key
    return tail[5:] if tail.startswith("user:") else tail


def task_run_states(agents: Iterable[Any]) -> Dict[str, Dict[str, Any]]:
    tasks: Dict[str, Any] = {}
    runners: Dict[str, Any] = {}
    for agent in agents or []:
        for t in getattr(agent, "tasks", None) or []:
            if getattr(t, "id", None):
                tasks[t.id] = t
                runners[t.id] = getattr(agent, "runner", None)
    name = lambda tid: getattr(tasks.get(tid), "name", "") or tid  # noqa: E731

    states: Dict[str, Dict[str, Any]] = {}
    snap = resource_gate.get_gate().snapshot()
    for w in snap["waiting"]:
        holders = sorted({snap["held"][k]["holder"] for k in w["keys"] if k in snap["held"]})
        states.setdefault(w["holder"], {})["waiting_resource"] = {
            "resources": [_resource_label(k) for k in w["keys"]],
            "behind": [name(h) for h in holders],
            "since": w["since"],
            "class": w["class"],
        }

    for tid, t in tasks.items():
        runner = runners.get(tid)
        held = getattr(runner, "__dict__", {}).get("_after_held", {}) if runner is not None else {}
        if tid in held:
            tracker = runner.__dict__.get("_after_tracker_obj")
            missing = tracker.status(t)[1] if tracker else task_deps.after_config(t)[0]
            states.setdefault(tid, {})["waiting_after"] = [
                (name(m[:-len(" (failed)")]) + " (failed)") if m.endswith(" (failed)") else name(m)
                for m in missing]
        meta = getattr(t, "metadata", None)
        if isinstance(meta, dict) and isinstance(meta.get("last_missed"), dict):
            states.setdefault(tid, {})["last_missed"] = dict(meta["last_missed"])
    return states
