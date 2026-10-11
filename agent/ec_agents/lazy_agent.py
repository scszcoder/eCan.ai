"""Deferred agents (Phase 5c): an agent with no tasks is not built at startup.

Building an EC_Agent costs ~0.5 s (browser_use Agent init, memory manager,
runner, A2A app) plus, once started, a memory worker and WAN subscriptions.
Most agents of an account have no tasks and only ever act when someone
messages them.  Such an agent sits in ``mainwin.agents`` as a ``LazyAgent``:
it answers the attributes that code scanning ALL agents reads (card, tasks,
skills, status, active_tasks, ...) from its definition, and builds (and, if
the launcher deferred its start, starts) the real agent the first time
anything else is touched -- a message, the chat page, a lookup that uses it.
From then on it forwards everything to the real agent, so identity checks
(``get_agent_by_id(x) is agent``) keep working.

Wake points that don't go through attribute access: the shared A2A server
(a request for a deferred agent's id) and in-process delivery.

Switch: ``ECAN_LAZY_AGENTS=1`` (default off).  Needs the shared A2A server
(a deferred agent has no server of its own).  Log grep: ``[lazy-agent]``.
"""
from __future__ import annotations

import os
import threading
import traceback
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional

from utils.logger_helper import logger_helper as logger

# Read by code that scans every agent (launcher, runtime-status poll, LAN/cloud
# advertising, store reconciler); answered without building the agent.
_CHEAP = ("card", "tasks", "skills", "active_tasks", "task_lock", "is_task_running", "status",
          "_running", "_stopped", "_starting", "_lazy_cold", "owner", "org_id", "description",
          "vehicle_id", "vehicle", "mainwin", "extra_data", "avatar")
# Values set on a cold agent that the real agent should keep.
_CARRY = ("status", "owner", "description", "extra_data")


def lazy_enabled() -> bool:
    from agent.a2a import shared_server
    return os.environ.get("ECAN_LAZY_AGENTS", "") == "1" and shared_server.enabled()


def agent_task_ids(agent_data: Dict[str, Any], mainwin: Any) -> List[str]:
    """The agent's task relations, from the same sources the converter uses."""
    from agent.agent_converter import _relation_ids_from_extra_data, _relation_ids_from_local_db
    tasks = agent_data.get("tasks") or []
    ids = [str(t.get("id") or t.get("name") or "") if isinstance(t, dict) else str(t) for t in tasks]
    ids = [i for i in ids if i]
    if not ids:
        ids = _relation_ids_from_extra_data(agent_data, "tasks")
    if not ids:
        try:
            ids = [str(t.get("id") or t.get("name")) for t in (_relation_ids_from_local_db(mainwin, agent_data.get("id"))[1] or [])]
        except Exception:
            # Can't tell: treat as having tasks (built at startup, as before).
            return ["?"]
    return ids


def _card_for(agent_data: Dict[str, Any], mainwin: Any):
    from a2a.types import AgentCapabilities
    from agent.a2a import shared_server
    from agent.a2a.langgraph_agent.utils import AgentCard, SUPPORTED_CONTENT_TYPES   # the converter's card type
    caps = agent_data.get("capabilities")
    return AgentCard(
        id=agent_data.get("id"),
        name=agent_data.get("name", "Unknown Agent"),
        description=agent_data.get("description") or "",
        url=shared_server.get_shared_server(mainwin).url_for(agent_data.get("id")),
        version=agent_data.get("version") or "1.0.0",
        capabilities=AgentCapabilities(**caps) if isinstance(caps, dict) else AgentCapabilities(streaming=True, pushNotifications=True),
        default_input_modes=agent_data.get("default_input_modes") or SUPPORTED_CONTENT_TYPES,
        default_output_modes=agent_data.get("default_output_modes") or SUPPORTED_CONTENT_TYPES,
        skills=[],
    )


def _first_caller() -> str:
    for fr in reversed(traceback.extract_stack()[:-3]):
        if "lazy_agent.py" not in fr.filename:
            return f"{os.path.basename(fr.filename)}:{fr.lineno} {fr.name}"
    return "?"


class LazyAgent:
    def __init__(self, agent_data: Dict[str, Any], mainwin: Any, build: Callable[[], Any]):
        d = self.__dict__
        d["_lz_build"] = build
        d["_lz_lock"] = threading.RLock()
        d["_lz_real"] = None
        d["_lz_start"] = False
        d["_lz_set"] = {}
        skills = []
        raw_skills = agent_data.get("skills") or []
        if not raw_skills:
            from agent.agent_converter import _relation_ids_from_extra_data
            raw_skills = _relation_ids_from_extra_data(agent_data, "skills")
        for s in raw_skills:
            sid = s.get("id") if isinstance(s, dict) else s
            skills.append(SimpleNamespace(id=sid, name=(s.get("name") if isinstance(s, dict) else None) or sid))
        d.update({
            "card": _card_for(agent_data, mainwin),
            "tasks": [],
            "skills": skills,
            "active_tasks": {},
            "task_lock": threading.Lock(),
            "is_task_running": lambda run_id: False,
            "status": agent_data.get("status") or "active",
            "_running": False,
            "_stopped": False,
            "_starting": False,
            "_lazy_cold": True,
            "owner": agent_data.get("owner"),
            "org_id": agent_data.get("org_id"),
            "description": agent_data.get("description") or "",
            "vehicle_id": agent_data.get("vehicle_id"),
            "vehicle": agent_data.get("vehicle_id"),
            "mainwin": mainwin,
            "extra_data": agent_data.get("extra_data", ""),
            "avatar": agent_data.get("avatar"),
        })

    def __repr__(self):
        state = "cold" if self.__dict__["_lz_real"] is None else "built"
        return f"<LazyAgent {getattr(self.__dict__.get('card'), 'name', '?')} ({state})>"

    @property
    def lazy_is_cold(self) -> bool:
        return self.__dict__["_lz_real"] is None

    def lazy_defer_start(self) -> None:
        """The launcher skipped start(): start it when it is built."""
        self.__dict__["_lz_start"] = True

    def lazy_materialize(self, reason: str = "") -> Any:
        d = self.__dict__
        real = d["_lz_real"]
        if real is not None:
            return real
        with d["_lz_lock"]:
            real = d["_lz_real"]
            if real is None:
                name = getattr(d.get("card"), "name", "?")
                logger.info(f"[lazy-agent] building '{name}' on first use ({reason}; from {_first_caller()}, "
                            f"thread {threading.current_thread().name})")
                real = d["_lz_build"]()
                if real is None:
                    raise RuntimeError(f"deferred agent '{name}' could not be built")
                for k, v in d["_lz_set"].items():
                    if k in _CARRY:
                        setattr(real, k, v)
                for k in _CHEAP:
                    d.pop(k, None)
                d["_lz_real"] = real
                start = d["_lz_start"]
            else:
                start = False
        if start:
            try:
                real.start()
            except Exception as e:
                logger.error(f"[lazy-agent] start of '{getattr(real.card, 'name', '?')}' failed: {e}")
        return real

    def __getattr__(self, name):
        # Only reached for names not answered above.
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        return getattr(self.lazy_materialize(f"attribute {name!r}"), name)

    def __setattr__(self, name, value):
        d = self.__dict__
        if d["_lz_real"] is not None:
            setattr(d["_lz_real"], name, value)
        elif name in _CHEAP:
            d[name] = value
            d["_lz_set"][name] = value
        else:
            setattr(self.lazy_materialize(f"set {name!r}"), name, value)


def wake(agent: Any, reason: str) -> Any:
    """Build (and start) ``agent`` if it is a deferred one; returns it either way."""
    if getattr(type(agent), "lazy_is_cold", None) is not None and agent.lazy_is_cold:
        agent.lazy_materialize(reason)
    return agent


def find_agent(mainwin: Any, agent_id: str) -> Optional[Any]:
    for ag in list(getattr(mainwin, "agents", None) or []):
        if getattr(getattr(ag, "card", None), "id", None) == agent_id:
            return ag
    return None
