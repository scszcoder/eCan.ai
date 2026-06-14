"""Process-wide registry for an optional in-process A2A local-delivery hook.

Deliberately STANDALONE (stdlib only, no project imports) so it can be imported by both the A2A
send core (`agent.ec_agent`) and the Feige hook module without a circular import.

Why this exists: `ec_agent` imports `agent.ec_tasks` at module load. The Feige hook bundle is
loaded during `build_node` / `ec_tasks` initialization, so a hook that did
`from agent.ec_agent import ...` at registration time hit `ec_tasks` while it was half-imported
-> "cannot import name 'TaskRunner' from partially initialized module 'agent.ec_tasks'" (ws062
live failure). Routing the registry through this dependency-free module breaks that cycle: both
sides import only stdlib here.
"""

_hook = None


def register_a2a_local_delivery_hook(fn) -> None:
    """Register (or clear, with None) the in-process local-delivery hook."""
    global _hook
    _hook = fn


def get_a2a_local_delivery_hook():
    """Return the registered hook, or None when none is set."""
    return _hook
