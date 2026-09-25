"""Where an agent runs: this process, a worker process, or not here at all.

The supervisor deals in opaque isolation keys and knows nothing about agents.
This module is the layer that does know — it reads an agent's tasks, works out
which isolation domain it belongs to, and answers one question:

    run it here / hand it to a worker / it is not ours

It sits beside the vehicle-affinity gate in ``EC_Agent.start()``, which answers
the same shape of question one level up ("is this agent for this *machine*?").

Why "skip" exists on both sides
-------------------------------
The rule is symmetric, and the asymmetric half is easy to get wrong. In the
parent, an agent with a key is delegated and not started here. In a worker,
an agent **without** a key is skipped — unisolated work belongs to the parent,
and a worker that ran it too would give every domain its own copy of the
account's shared agents.

``ECAN_WORKER_KEY`` unset means "I am the parent". Nothing sets an isolation
key yet, so every agent reads as unisolated and runs in the parent exactly as
it does today.
"""

from __future__ import annotations

import os
import sys
from typing import Any, List, Tuple

from utils.logger_helper import logger_helper as logger

from agent.ec_tasks.worker_supervisor import (
    WorkerSpec, isolation_key_for_task, isolation_keys_for_tasks,
)

# Set by the supervisor on a worker it spawns; absent in the app the operator
# launched.
WORKER_KEY_ENV = "ECAN_WORKER_KEY"

PLACE_HERE = "here"
PLACE_DELEGATE = "delegate"
PLACE_SKIP = "skip"


def worker_key_of_process() -> str:
    """This process's isolation key, or ``""`` when it is the parent app."""
    return str(os.environ.get(WORKER_KEY_ENV) or "").strip()


def agent_isolation_key(agent: Any) -> str:
    """The isolation domain an agent belongs to, or ``""``.

    An agent's tasks are expected to share one domain — the deploy recipe
    creates a front desk and its Q&A agents for one store together. Tasks
    spanning two domains cannot be honoured (the agent can only live in one
    process), so the first key wins and the conflict is logged loudly: running
    it in the parent instead would put it alongside everything, which is the
    sharing this exists to prevent.
    """
    tasks = getattr(agent, "tasks", None) or []
    keys: List[str] = isolation_keys_for_tasks(tasks)
    if not keys:
        return ""
    if len(keys) > 1:
        name = getattr(getattr(agent, "card", None), "name", "") or "?"
        logger.error(
            f"[WorkerPlacement] agent {name!r} has tasks in {len(keys)} isolation "
            f"domains {keys}; an agent can only live in one process, so it is "
            f"placed in {keys[0]!r}. Split it into one agent per domain."
        )
    return keys[0]


def placement_for_agent(agent: Any) -> Tuple[str, str]:
    """``(decision, key)`` for this agent in this process.

    Never raises: a placement failure must not stop an agent from starting, so
    anything unexpected reads as "run here", which is today's behaviour.
    """
    try:
        key = agent_isolation_key(agent)
        mine = worker_key_of_process()
        if not mine:
            # The parent app.
            return (PLACE_DELEGATE, key) if key else (PLACE_HERE, "")
        # A worker: run only its own domain, and never the parent's share.
        return (PLACE_HERE, key) if key == mine else (PLACE_SKIP, key)
    except Exception as exc:
        logger.warning(f"[WorkerPlacement] placement failed ({exc}); running here")
        return (PLACE_HERE, "")


# ── launching a worker ───────────────────────────────────────────────

def _worker_runner_dir() -> str:
    from config.app_info import app_info
    path = os.path.join(app_info.appdata_path, "workers")
    os.makedirs(path, exist_ok=True)
    return path


def default_spawner(key: str) -> WorkerSpec:
    """How to launch the worker for ``key``.

    Two launch shapes, because a frozen build cannot be re-run as an
    interpreter: ``sys.executable`` is the GUI exe, and ``-m something`` would
    just start a second copy of the app. The packaged path therefore reuses the
    ``ECAN_RUN_SCRIPT`` mechanism ``main.py`` already honours (and which
    explicitly keeps long-running children alive) — the same one Fast Deploy
    uses to run the CLI from inside the packaged app.
    """
    entry_module = "agent.ec_tasks.worker_entry"
    env = {
        WORKER_KEY_ENV: key,
        # Gives the worker its own log file, IPC port and single-instance lock,
        # while leaving the database, browser profiles and plugin config shared
        # with the parent. See config/instance.py.
        "ECAN_INSTANCE_ID": key,
    }
    log_path = os.path.join(_worker_runner_dir(), f"worker-{key}.out.log")

    if getattr(sys, "frozen", False):
        runner = os.path.join(_worker_runner_dir(), f"worker-{key}.py")
        with open(runner, "w", encoding="utf-8") as fh:
            fh.write(
                "import sys\n"
                f"sys.argv = ['ecan-worker', '--key', {key!r}]\n"
                f"from {entry_module} import main\n"
                "main()\n"
            )
        env["ECAN_RUN_SCRIPT"] = runner
        argv = [sys.executable]
    else:
        argv = [sys.executable, "-m", entry_module, "--key", key]

    return WorkerSpec(argv=argv, env=env, log_path=log_path)


def install_default_supervisor() -> None:
    """Point the process-wide supervisor at :func:`default_spawner`."""
    from agent.ec_tasks import worker_supervisor as ws
    ws.set_supervisor(ws.WorkerSupervisor(default_spawner))


def delegate_to_worker(key: str) -> bool:
    """Make sure the worker for ``key`` is up. True when it is running.

    Called at agent-launch time, which is the agreed trigger: the parent asks
    for a worker at the moment it decides not to run something itself.
    """
    if not key:
        return False
    try:
        from agent.ec_tasks import worker_supervisor as ws
        sup = ws.supervisor()
        status = sup.ensure_worker(key)
        if status is None:
            logger.error(
                f"[WorkerPlacement] could not place isolation domain {key!r} in a "
                f"worker; its agents will not run on this host until a worker "
                f"for it starts."
            )
            return False
        return bool(status.running)
    except Exception as exc:
        logger.error(f"[WorkerPlacement] delegating {key!r} failed: {exc}")
        return False
