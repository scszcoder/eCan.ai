"""Pull what other machines created, without restarting (Agents page -> 从云端同步).

Startup already brings the local database up to date from the cloud
(agent/ec_agents/cloud_hydrate.py). This runs the same pass on demand, then
brings what is NEW into the running app:

* tasks this machine did not have -> added to the task list;
* agents this machine did not have -> built and started (the launch gate still
  decides whether each runs HERE -- a store elsewhere, a pin to another machine,
  a disabled agent all stay put).

What cannot be swapped under a running agent is reported instead of forced: a
task that changed, a new link for an agent that is already running, a task
whose skill is not loaded yet. Those apply on the next start of eCan.
"""

import asyncio
from typing import Any, Dict, Optional

from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response
from utils.logger_helper import logger_helper as logger


def _ids(items) -> set:
    out = set()
    for it in items or []:
        card = getattr(it, "card", None)
        out.add(str(getattr(card, "id", None) or getattr(it, "id", "") or ""))
    out.discard("")
    return out


def _name(agent) -> str:
    return str(getattr(getattr(agent, "card", None), "name", "") or "?")


async def _apply_in_app(mainwin, hydrated: Dict[str, Any]) -> Dict[str, Any]:
    """Runs on the app's main loop: add new tasks and agents, launch the agents."""
    from agent.ec_agents.create_agent_tasks import _load_agent_tasks_from_database_async
    from agent.agent_converter import convert_agent_dict_to_ec_agent

    result: Dict[str, Any] = {"tasks_added": [], "agents_added": [], "needs_restart": []}

    # tasks: every DB task this app does not hold yet
    have_tasks = _ids(getattr(mainwin, "agent_tasks", None))
    db_tasks = await _load_agent_tasks_from_database_async(mainwin) or []
    skill_ids = _ids(getattr(mainwin, "agent_skills", None))
    new_tasks = [t for t in db_tasks if str(getattr(t, "id", "")) not in have_tasks]
    if new_tasks:
        mainwin.agent_tasks = list(getattr(mainwin, "agent_tasks", None) or []) + new_tasks
    result["tasks_added"] = [t.name for t in new_tasks]
    svc = mainwin.ec_db_mgr.task_service
    for t in new_tasks:
        rels = (svc.get_task_skills(str(t.id)) or {}).get("data") or []
        missing = [r.get("skill_id") for r in rels if str(r.get("skill_id")) not in skill_ids]
        if missing and getattr(t, "skill", None) is None:
            result["needs_restart"].append(f"task {t.name}: its skill is not loaded yet")

    # agents: every DB agent of this user this app does not hold yet
    agents = list(getattr(mainwin, "agents", None) or [])
    have_agents = _ids(agents)
    rows = (mainwin.ec_db_mgr.agent_service.get_agents_by_owner(mainwin.user) or {}).get("data") or []
    new_agents = []
    for row in rows:
        if str(row.get("id") or "") in have_agents:
            continue
        try:
            agent = convert_agent_dict_to_ec_agent(row, mainwin)
        except Exception as e:
            logger.warning(f"[cloud.refresh] could not build agent {row.get('name')!r}: {e}")
            continue
        if agent is not None:
            new_agents.append(agent)
    if new_agents:
        mainwin.agents = agents + new_agents
        launch = getattr(mainwin, "_launch_agents_async", None)
        if callable(launch):
            launch(new_agents)           # disabled / placed-elsewhere agents are skipped there
    result["agents_added"] = [_name(a) for a in new_agents]

    # what a running agent only picks up after a restart
    task_names = {str(getattr(t, "id", "")): getattr(t, "name", "") for t in mainwin.agent_tasks}
    for tid in (hydrated.get("tasks") or {}).get("updated_ids") or []:
        if tid in have_tasks:
            result["needs_restart"].append(f"task {task_names.get(tid, tid)} changed")
    running_ids = have_agents
    for agent_id, task_id in hydrated.get("agent_task_links_added") or []:
        if agent_id in running_ids:
            result["needs_restart"].append(
                f"agent {agent_id} got task {task_names.get(task_id, task_id)}")
    return result


@IPCHandlerRegistry.background_handler('cloud.refresh')
def handle_cloud_refresh(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    try:
        from app_context import AppContext
        from agent.ec_agents.cloud_hydrate import hydrate_local_db_from_cloud
        mainwin = AppContext.get_main_window()
        if mainwin is None or getattr(mainwin, "ec_db_mgr", None) is None:
            return create_error_response(request, 'NOT_READY', 'the app is still starting')
        hydrated = hydrate_local_db_from_cloud(mainwin)
        if not hydrated.get("ok"):
            return create_error_response(
                request, 'CLOUD_UNAVAILABLE',
                hydrated.get("skipped") or hydrated.get("error") or "the cloud copy could not be read")
        loop = AppContext.get_main_loop()
        if loop is None or not loop.is_running():
            return create_error_response(request, 'NOT_READY', 'the app loop is not running')
        applied = asyncio.run_coroutine_threadsafe(_apply_in_app(mainwin, hydrated), loop).result(timeout=90)
        logger.info(f"[cloud.refresh] {applied}")
        return create_success_response(request, {
            "cloud": hydrated.get("cloud"),
            "tasks_added": applied["tasks_added"],
            "agents_added": applied["agents_added"],
            "needs_restart": applied["needs_restart"],
        })
    except Exception as e:
        logger.warning(f"[cloud.refresh] failed: {e}")
        return create_error_response(request, 'CLOUD_REFRESH_ERROR', str(e))
