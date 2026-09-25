"""Entry point for a worker process: run one isolation domain's agents.

Launched by the app's supervisor, never by a person. It boots the minimum an
agent needs, starts the agents belonging to its domain, and then does nothing
but stay alive — the agents' own schedulers and event loops do the work, the
same ones they would run inside the app.

Lifecycle contract with the supervisor
--------------------------------------
* ``--key`` / ``ECAN_WORKER_KEY`` says which domain this worker serves.
* **stdin closing means "no more work, drain and exit".** That is the graceful
  stop, chosen because it is the only signal that behaves the same on Windows,
  where ``terminate()`` gives a process no chance to finish delivering a reply
  it is part-way through. The supervisor escalates to terminate and then kill
  if this takes too long, so the drain here has to be honest about finishing.

The placement gate inside ``EC_Agent.start()`` decides what actually runs: this
process starts *every* agent it built, and the gate skips the ones belonging to
another domain or to the parent. Keeping that decision in one place is why the
worker does not filter the list itself.
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
from typing import List

from utils.logger_helper import logger_helper as logger


def _resolve_user() -> str:
    """Which account's data this worker runs against.

    Handed down by the parent, because a worker has no login UI and must not
    invent an identity — it shares the parent's data home, and reading it as
    the wrong user would point at a different profile directory.
    """
    for var in ("ECAN_LOG_USER", "ECAN_CLI_USER", "ECAN_WORKER_USER"):
        value = (os.environ.get(var) or "").strip()
        if value:
            return value
    return ""


def _data_home(user: str) -> str:
    from config.app_info import app_info
    return os.path.join(app_info.appdata_path, user) if user else app_info.appdata_path


def start_domain_agents(ctx, key: str) -> List:
    """Start the agents this worker is responsible for. Returns those started."""
    from agent.ec_tasks.worker_context import load_agents_from_db
    from agent.ec_tasks.worker_placement import placement_for_agent, PLACE_HERE

    agents = load_agents_from_db(ctx)
    ctx.agents = agents

    started = []
    for agent in agents:
        decision, _ = placement_for_agent(agent)
        if decision != PLACE_HERE:
            continue
        try:
            agent.start()
            started.append(agent)
        except Exception as exc:
            name = getattr(getattr(agent, "card", None), "name", "?")
            logger.error(f"[Worker {key}] agent {name!r} failed to start: {exc}")
    logger.info(
        f"[Worker {key}] agents started: {len(started)} of {len(agents)} built"
    )
    return started


def _wait_for_stdin_close() -> None:
    """Block until the parent closes our stdin — the graceful stop signal."""
    try:
        sys.stdin.read()
    except Exception:
        # A closed or absent stdin means the same thing as EOF: stop.
        pass


def main() -> int:
    parser = argparse.ArgumentParser(prog="ecan-worker")
    parser.add_argument("--key", default=os.environ.get("ECAN_WORKER_KEY", ""),
                        help="the isolation domain this worker serves")
    args = parser.parse_args()

    key = str(args.key or "").strip()
    if not key:
        logger.error("[Worker] no isolation key given; refusing to start")
        return 2
    # The placement gate reads this, and argparse may have supplied it.
    os.environ["ECAN_WORKER_KEY"] = key

    user = _resolve_user()
    home = _data_home(user)
    logger.info(f"[Worker {key}] starting (user={user or '?'} data_home={home})")

    ctx = None
    started: List = []
    try:
        from agent.ec_tasks.worker_context import WorkerContext
        ctx = WorkerContext(user=user, data_home=home)

        # Same registration the app does, so this process is reachable and so
        # its runner-bridge and supervisor singletons exist.
        try:
            from app_context import AppContext
            AppContext().set_main_window(ctx)
        except Exception as exc:
            logger.warning(f"[Worker {key}] AppContext not set ({exc})")

        started = start_domain_agents(ctx, key)
        if not started:
            # Not fatal: the domain may simply have no agents on this host yet,
            # and exiting would make the supervisor treat it as a crash loop.
            logger.warning(
                f"[Worker {key}] no agents started — staying up in case they "
                f"appear; the supervisor will stop this worker when its domain "
                f"is no longer wanted"
            )

        logger.info(f"[Worker {key}] ready; waiting for the parent to close stdin")
        _wait_for_stdin_close()
        logger.info(f"[Worker {key}] stdin closed — draining")
    except KeyboardInterrupt:
        logger.info(f"[Worker {key}] interrupted — draining")
    except Exception as exc:
        logger.error(f"[Worker {key}] failed: {exc}", exc_info=True)
        return 1
    finally:
        _drain(key, started, ctx)
    return 0


def _drain(key: str, started: List, ctx) -> None:
    """Finish what is in flight, then let the process end.

    Live-chat deliveries get the same drain the app runs at shutdown; without
    it a reply already handed to the send path is lost when the worker exits,
    which the customer experiences as silence.
    """
    try:
        from agent.ec_tasks.runner import TaskRunnerRegistry
        TaskRunnerRegistry.prepare_live_chat_shutdown(reason="worker_shutdown")
    except Exception as exc:
        logger.warning(f"[Worker {key}] live-chat drain skipped: {exc}")
    try:
        from agent.ec_tasks.runner import TaskRunnerRegistry
        TaskRunnerRegistry.stop_all()
    except Exception as exc:
        logger.warning(f"[Worker {key}] runner shutdown: {exc}")
    for agent in started:
        try:
            stop = getattr(agent, "stop", None)
            if callable(stop):
                stop()
        except Exception:
            pass
    if ctx is not None:
        ctx.shutdown()
    logger.info(f"[Worker {key}] stopped")


if __name__ == "__main__":
    sys.exit(main())
