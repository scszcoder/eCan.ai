"""On startup, find tasks that the previous process started and never
finished — and let the runner clean them up.

Every task a worker takes moves through three DB states: ``running`` (set
when the task is claimed), ``completed`` / ``failed`` (set when it ends,
success or failure). A *crash* leaves it stuck at ``running`` -- the worker
is gone, no happy/sad ending was ever written.

``identify_orphans`` is the missing piece. It walks the lease directory and
returns task ids that are eligible for recovery:

* the lease has expired (no one owns it now), *or* the worker that wrote
  it is provably gone — a SIGKILLed worker never renews its lease, so
  waiting out the TTL only leaves the user's task visibly stuck.

A recovered task is not retried automatically: the caller (the runner) decides
whether to mark it failed, queue a retry, or surface the choice to the
operator. This module exposes ``run_startup_recovery`` which pairs the
identification step with an injected ``on_orphan`` callback, so the same
recovery path can be tested with a fake handler and wired to a real DB
updater later.

Forensic note: the lease file is left in place on purpose. The runner is
expected to call ``mark_orphan_resolved`` once it has decided what to do with
the orphan, so the next startup does not see the same id again.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, List, Optional

from utils import task_lease as tl
from utils.worker_boot import read_boot
from utils.logger_helper import logger_helper as logger


#: Default orphan handler: log and move on. Production callers inject a real
#: updater (e.g. ``db_task_service.update_task_status(task_id, 'failed')``).
#: Stays a default to keep this module dependency-free at import time.
def _log_orphan(task_id: str) -> None:
    logger.warning(
        f"[ZombieRecovery] orphan task {task_id!r} found; "
        "no recovery handler registered — leaving to caller"
    )


DEFAULT_ORPHAN_HANDLER = _log_orphan


def _leases_dir(log_dir: Optional[str] = None) -> str:
    """The directory where task leases live; shared with utils.task_lease.

    Returned as a string because the rest of the API is string-keyed.
    """
    root = tl._leases_root(log_dir)
    return str(root.parent) if root.name == tl.LEASE_DIR_NAME else str(root)


def _walk_lease_files(leases_dir: Optional[str] = None) -> list[Path]:
    """Return every ``*.lease.json`` file under the leases directory."""
    return list(tl._leases_root(leases_dir).glob(f"*.{tl.LEASE_NAME}"))


def identify_orphans(leases_dir: Optional[str] = None,
                     log_dir: Optional[str] = None) -> List[str]:
    """Return the task ids of leases that look orphaned *now*.

    A lease looks orphaned when its TTL has elapsed: the previous run had
    it checked out, the worker died before releasing, and time has now
    passed. A lease inside its TTL is assumed live (the worker may simply
    be running it) — *unless* the worker is provably gone, in which case
    the lease is orphaned right away rather than after the TTL.
    """
    leases_root = tl._leases_root(leases_dir)
    if not leases_root.exists():
        return []
    import time as _time
    wall_now = _time.time()
    out: List[str] = []
    for path in _walk_lease_files(leases_dir):
        try:
            lease = tl._read_path(path)
        except Exception:
            continue
        if not lease:
            continue
        task_id = str(lease.get("task_id") or "")
        if not task_id:
            continue
        try:
            ttl = float(lease["ttl_s"])
            started = float(lease["started_at"])
        except Exception:
            continue
        # A lease still inside its TTL belongs to whoever wrote it -- do
        # not snapshot it as orphan just because the pid is unknown. But a
        # worker that is provably dead will never renew it, so waiting out
        # the TTL only leaves the task stuck.
        inside_ttl = (wall_now - started) < ttl
        if inside_ttl and tl._holder_alive(lease) is not False:
            continue
        out.append(task_id)
    out.sort()
    return out


def run_startup_recovery(leases_dir: Optional[str] = None,
                         log_dir: Optional[str] = None,
                         on_orphan: Optional[Callable[[str], None]] = None
                         ) -> List[str]:
    """Walk the orphan list and feed each id to *on_orphan*.

    The returned list is the task ids handed off, in stable order. The
    lease file for each id is dropped only after *on_orphan* returns
    without raising — that way a handler that fails still gets its retry
    on the next startup, never silently lost.

    Pass ``on_orphan=DEFAULT_ORPHAN_HANDLER`` (or a custom function) to
    decide what "recover" means. The default is intentionally
    dependency-free so this module can be imported anywhere.
    """
    handler = on_orphan or DEFAULT_ORPHAN_HANDLER
    orphans = identify_orphans(leases_dir=leases_dir, log_dir=log_dir)
    handled: List[str] = []
    for task_id in orphans:
        try:
            handler(task_id)
        except Exception as exc:
            # Leave the lease in place; the next startup will retry the
            # handler. Logging at WARNING is the right level — if the
            # handler is in a tight loop this is a real fault worth
            # telling an operator about.
            logger.warning(
                f"[ZombieRecovery] orphan handler raised for "
                f"{task_id!r}: {exc}"
            )
            continue
        mark_orphan_resolved(task_id=task_id, leases_dir=leases_dir)
        handled.append(task_id)
    return handled


def mark_orphan_resolved(task_id: str, leases_dir: Optional[str] = None) -> None:
    """Drop the lease for *task_id*. The runner calls this once it has
    decided what to do with the orphan (mark failed, queue retry, etc.) so
    that the next startup does not see the same task again."""
    path = tl.lease_path(task_id, leases_dir)
    try:
        if path.exists():
            path.unlink()
    except Exception as exc:
        logger.debug(f"[ZombieRecovery] could not drop lease for {task_id}: {exc}")
