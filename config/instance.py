"""Instance identity — several eCan processes side by side on one machine.

The unit model is one isolation domain per process — for e-commerce, one store:
one browser profile (a store *is* a seller login, and Chromium refuses a second
process on one ``--user-data-dir``), one front desk, N Q&A agents, one platform.
These are workers of ONE app, launched by it rather than by the operator (see
``agent/ec_tasks/worker_supervisor.py``). The app is otherwise single-instance
by construction, so the few things that genuinely cannot be shared between
those processes derive their names from here:

    log file    utils/logger_helper.py   -> one file per worker, one folder
    IPC port    agent/mcp/config.py      -> LocalServer, MCP clients, avatar URLs
    mutex       utils/single_instance.py -> the gate that permits a 2nd process

The data home is deliberately NOT in that list. Workers are workers of one
app, so the database, the browser profiles and the plugin config are shared;
scoping them would give every worker its own login and hide them from the GUI.

The mutex is listed last because it is the only one that *permits* a second
process: it must not open until the log file and the port are already
separate, or workers would truncate each other's log and fight over one port.

``ECAN_INSTANCE_ID`` unset is the default and reproduces the original
behaviour exactly — no suffix, port 4668, the original mutex name. An existing
install sees no change whatsoever unless the id is set.
"""

import os
import re

# The id becomes a directory name, a Windows mutex name and a log line, so it
# is restricted to characters that are safe in all three.
_UNSAFE = re.compile(r"[^A-Za-z0-9_-]+")
_MAX_LEN = 32

ENV_VAR = "ECAN_INSTANCE_ID"


def instance_id() -> str:
    """This process's instance id, sanitized. ``""`` is the default instance."""
    raw = (os.environ.get(ENV_VAR) or "").strip()
    if not raw:
        return ""
    return _UNSAFE.sub("-", raw).strip("-")[:_MAX_LEN]


def instance_suffix(sep: str = ".") -> str:
    """``"<sep><id>"`` for names that need one, or ``""`` for the default."""
    ident = instance_id()
    return f"{sep}{ident}" if ident else ""


def instance_log_filename(base_filename: str) -> str:
    """The log file this instance writes, e.g. ``eCan.log`` -> ``eCan-w1.log``.

    A separate FILE in the shared ``runlogs`` folder, not a separate folder:
    the support flow zips that one folder, so a worker's log ends up in the
    bundle the operator sends without anyone having to remember it exists.
    Interleaving them into one file instead would be worse than useless —
    concurrent writers from several processes corrupt each other's lines.
    """
    ident = instance_id()
    if not ident:
        return base_filename
    stem, dot, ext = base_filename.rpartition(".")
    if not dot:
        return f"{base_filename}-{ident}"
    return f"{stem}-{ident}.{ext}"


def instance_port(base: int) -> int:
    """This instance's port, derived from ``base`` and the id.

    Derived rather than allocated, so every participant — the LocalServer, the
    MCP client, the avatar URL builder, the front end — computes the same
    answer from the same env var, with no discovery file to read, no startup
    ordering to get right, and no stale value to clean up after a crash.

    The default instance is exactly ``base``, so nothing moves unless an id is
    set. Named instances land in ``base+1 .. base+199``, which keeps them in
    one predictable block.
    """
    ident = instance_id()
    if not ident:
        return base
    # Not hash(): it is salted per process in Python 3, so the same instance
    # would land on a different port each launch.
    digest = 0
    for ch in ident:
        digest = (digest * 131 + ord(ch)) & 0xFFFFFFFF
    return base + 1 + (digest % 199)
