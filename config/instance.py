"""Instance identity — several eCan processes side by side on one machine.

The multi-store unit model is one store per process: one browser profile (a
store *is* a seller login, and Chromium refuses a second process on one
``--user-data-dir``), one front desk, N Q&A agents, one platform. The app is
otherwise single-instance by construction, so everything that must not be
shared between instances derives its name from here:

    data home   config/app_info.py       -> ecan.db, runlogs, profiles, plugins
    IPC port    agent/mcp/config.py      -> LocalServer, MCP clients, avatar URLs
    mutex       utils/single_instance.py -> the gate that permits a 2nd process

That ordering is deliberate. The mutex is listed last because it is the only
one that *permits* a second process: it must not open until the data home and
the port are already separate, or two instances will share one SQLite file and
one log.

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
