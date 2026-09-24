"""Make the store agents running here match the store assignments, once per heartbeat.

``EC_Agent.start()`` asks store placement once, at launch. This is what makes a
later ``store_assign`` actually move a store: each heartbeat it re-asks for
every store-bound agent and

    placement says run, agent not running  -> start it
    placement says skip, agent running     -> stop it (the next store_report
                                              then releases the store)

It runs BEFORE the store report of the same heartbeat, so a stop and its
release go out together and the machine taking over sees the release one
heartbeat later -- the "gap over duplicate" hand-over.

Left alone, deliberately:
* agents whose tasks declare an isolation key -- the worker supervisor owns
  them, and starting them here would bypass it;
* disabled agents -- the owner turned them off;
* an agent this process already stopped -- EC_Agent.stop() leaves its tasks
  cancelled, so it needs an app restart to run here again (warned once);
* an agent whose start raised -- retried after a restart, not every minute.
"""

from __future__ import annotations

from typing import Any, Dict, List

from utils.logger_helper import logger_helper as logger


def _name(agent: Any) -> str:
    return getattr(getattr(agent, "card", None), "name", "") or "?"


def _is_isolated(agent: Any) -> bool:
    try:
        from agent.ec_tasks.worker_placement import agent_isolation_key
        return bool(agent_isolation_key(agent))
    except Exception:
        return False


def reconcile(mainwin: Any) -> Dict[str, List[str]]:
    """One pass. Returns ``{"started": [...], "stopped": [...]}`` agent names. Never raises."""
    from agent.ec_agents.store_placement import (
        RUN, SKIP, placement_for_agent, refresh, store_ids_of_agent,
    )

    done: Dict[str, List[str]] = {"started": [], "stopped": []}
    try:
        refresh(mainwin, force=True)
    except Exception as e:
        logger.warning(f"[StoreReconciler] could not refresh assignments: {e}")

    for agent in list(getattr(mainwin, "agents", None) or []):
        try:
            if not store_ids_of_agent(agent):
                continue
            if (getattr(agent, "status", "active") or "active") == "disabled" or _is_isolated(agent):
                continue
            verdict, why = placement_for_agent(agent)
            running = bool(getattr(agent, "_running", False))
            if verdict == SKIP and running:
                agent.stop(reason=f"store placement: {why}")
                done["stopped"].append(_name(agent))
            elif verdict == RUN and not running:
                if getattr(agent, "_stopped", False):
                    if not getattr(agent, "_restart_warned", False):
                        agent._restart_warned = True
                        logger.warning(f"[StoreReconciler] '{_name(agent)}' is assigned here again "
                                       f"but was stopped in this process; restart the app to run it")
                    continue
                if getattr(agent, "_store_start_failed", False):
                    continue
                try:
                    agent.start()
                except Exception as e:
                    agent._store_start_failed = True
                    logger.error(f"[StoreReconciler] starting '{_name(agent)}' failed: {e}")
                    continue
                if getattr(agent, "_running", False):
                    done["started"].append(_name(agent))
        except Exception as e:
            logger.error(f"[StoreReconciler] '{_name(agent)}': {e}")

    if done["started"] or done["stopped"]:
        logger.info(f"[StoreReconciler] started={done['started']} stopped={done['stopped']}")
    return done
