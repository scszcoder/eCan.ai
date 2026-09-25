"""Make the store agents running here match the store assignments, once per heartbeat.

``EC_Agent.start()`` asks store placement once, at launch. This is what makes a
later ``store_assign`` actually move a store: each heartbeat it re-asks for
every store-bound agent and

    placement says run, in-process          -> start it here if not running
    placement says run, own store process   -> stop it here; the store process runs it
    placement says skip                     -> stop it here (the next store_report
                                               then releases the store)

"Own store process" is the store-isolation policy (store_isolation.py: two or
more stores of one platform on this machine). The pass runs in three phases so
a store is never live in two places at once:

    1. stop every in-process agent that must not run here in-process;
    2. make the store processes match (supervisor.reconcile);
    3. start the in-process agents that should now run here.

A store moving INTO its own process is stopped here (1) before its process
starts (2); a store moving back OUT has its process drained (2) before the
agent starts here (3).

It runs BEFORE the store report of the same heartbeat, so a stop and its
release go out together and the machine taking over sees the release one
heartbeat later -- the "gap over duplicate" hand-over.

Left alone, deliberately:
* agents whose tasks declare an explicit isolation key -- configured by hand;
* disabled agents -- the owner turned them off;
* an agent this process already stopped -- EC_Agent.stop() leaves its tasks
  cancelled, so it needs an app restart to run here again (warned once);
* an agent whose start raised -- retried after a restart, not every minute.
"""

from __future__ import annotations

from typing import Any, Dict, List, Set

from utils.logger_helper import logger_helper as logger


def _name(agent: Any) -> str:
    return getattr(getattr(agent, "card", None), "name", "") or "?"


def _is_isolated(agent: Any) -> bool:
    """An EXPLICIT isolation key in the agent's tasks (hand-configured)."""
    try:
        from agent.ec_tasks.worker_supervisor import isolation_keys_for_tasks
        return bool(isolation_keys_for_tasks(getattr(agent, "tasks", None) or []))
    except Exception:
        return False


def _store_process_key(agent: Any) -> str:
    try:
        from agent.ec_agents.store_isolation import store_isolation_key
        return store_isolation_key(agent)
    except Exception:
        return ""


def _reconcile_store_processes(keys: Set[str]) -> Dict[str, List[str]]:
    try:
        from agent.ec_tasks import worker_supervisor as ws
        return ws.supervisor().reconcile(sorted(keys))
    except Exception as e:
        logger.error(f"[StoreReconciler] store processes not reconciled: {e}")
        return {"started": [], "stopped": []}


def reconcile(mainwin: Any) -> Dict[str, List[str]]:
    """One pass. Returns ``{"started", "stopped", "processes_started", "processes_stopped"}``. Never raises."""
    from agent.ec_agents.store_placement import (
        RUN, SKIP, placement_for_agent, refresh, store_ids_of_agent,
    )

    done: Dict[str, List[str]] = {"started": [], "stopped": [],
                                  "processes_started": [], "processes_stopped": []}
    try:
        refresh(mainwin, force=True)
    except Exception as e:
        logger.warning(f"[StoreReconciler] could not refresh assignments: {e}")

    to_start: List[Any] = []
    process_keys: Set[str] = set()

    # Phase 1: decide; stop what must not run in-process.
    for agent in list(getattr(mainwin, "agents", None) or []):
        try:
            if not store_ids_of_agent(agent):
                continue
            if (getattr(agent, "status", "active") or "active") == "disabled" or _is_isolated(agent):
                continue
            verdict, why = placement_for_agent(agent)
            key = _store_process_key(agent) if verdict == RUN else ""
            if key:
                process_keys.add(key)
            running = bool(getattr(agent, "_running", False))
            if running and (verdict == SKIP or key):
                reason = (f"store placement: {why}" if verdict == SKIP
                          else f"store {key!r} moves to its own store process")
                agent.stop(reason=reason)
                done["stopped"].append(_name(agent))
            elif verdict == RUN and not key and not running:
                to_start.append(agent)
        except Exception as e:
            logger.error(f"[StoreReconciler] '{_name(agent)}': {e}")

    # Phase 2: store processes follow (start new ones, drain ones no longer wanted).
    res = _reconcile_store_processes(process_keys)
    done["processes_started"], done["processes_stopped"] = res.get("started", []), res.get("stopped", [])

    # Phase 3: in-process starts, after any process that ran them has drained.
    for agent in to_start:
        try:
            if getattr(agent, "_stopped", False):
                if not getattr(agent, "_restart_warned", False):
                    agent._restart_warned = True
                    logger.warning(f"[StoreReconciler] '{_name(agent)}' should run here again "
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

    if any(done.values()):
        logger.info(f"[StoreReconciler] started={done['started']} stopped={done['stopped']} "
                    f"store processes started={done['processes_started']} "
                    f"stopped={done['processes_stopped']}")
    return done
