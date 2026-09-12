"""HeadlessAppContext — the service locator a cloud pod uses instead of MainWindow.

Path 1.5, Phase 1.3. Skill code never touches a widget: every
``mainwin.<service>`` call is a service lookup, and there are two ways in —
``AppContext.get_main_window()`` (35 sites) and the ``mainwin`` parameter that
every ``create_*_skill(mainwin)`` / ``build_skill(..., mainwin=...)`` entrypoint
already takes. This object satisfies both, so skill code needs no changes.

Built to a verified inventory of the runtime surface (``agent/ec_skills/**``,
``agent/ec_skill.py``, ``agent/ec_tasks/**``, ``agent/ec_agents/**``), not a
guess. Ten services carry roughly 270 of ~380 call sites::

    llm  agent_skills  agents  user  config_manager  agent_tasks
    mcp_client  getWanApiEndpoint()  get_auth_token()  browser_use_llm

Three classes of service, three behaviours:

* **provided** — handed to the constructor, returned as-is. Names in
  ``METHOD_SERVICES`` may be given as a plain value and are wrapped into a
  zero-arg callable, because call sites invoke them (``mainwin.get_auth_token()``).
* **browser** — only present on a browser-capable vehicle. Otherwise the lookup
  raises, naming ``requires=['browser_local']`` (the Phase 0.3 declaration that
  should have kept this work off this pod in the first place).
* **desktop-only** — Qt/RPA plumbing with no headless meaning
  (``channel_bridge``, the RPA queues). Always raises, and says so.

Anything unrecognised raises too. Nothing returns ``None`` silently: a headless
gap must look like a failure, not like a working run behaving differently.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, Optional, Set

from app_context import MissingService

# Services that call sites invoke rather than read. A plain value given for one
# of these is wrapped into a callable so `mainwin.get_auth_token()` works.
METHOD_SERVICES: Set[str] = {
    "getWanApiEndpoint", "getWanApiKey", "get_auth_token", "getAcctSiteID",
    "getWSApiEndpoint", "getWSApiHost",
    # browser-capable vehicles only
    "getWebDriver", "getWebDriverPath", "getBrowserSession",
    "get_local_server_port",
}

# Present only when the vehicle can drive a local browser.
BROWSER_SERVICES: Set[str] = {
    "getWebDriver", "getWebDriverPath", "setWebDriver", "browser_manager",
    "unified_browser_manager", "getBrowserSession", "get_local_server_port",
}

# Desktop/Qt plumbing with no headless equivalent. Asking for one of these on a
# pod is a routing mistake, not a missing implementation.
DESKTOP_ONLY_SERVICES: Set[str] = {
    "todo_wait_in_line", "rpa_wait_in_line", "bots", "channel_bridge",
    "get_vehicle_ecbot_op_agent", "wan_connected",
    "register_wan_connected_callback", "_route_passive_command_to_task",
}

# The plain services a headless runtime is expected to provide. Listed so an
# incomplete context can be reported up front instead of one failure at a time.
EXPECTED_SERVICES: Set[str] = {
    "llm", "browser_use_llm", "mcp_client", "config_manager", "agents",
    "agent_skills", "agent_tasks", "user", "session", "db_chat_service",
    "ec_db_mgr", "my_ecb_data_homepath",
    "getWanApiEndpoint", "get_auth_token", "getAcctSiteID",
}


class HeadlessAppContext:
    """Duck-typed stand-in for MainWindow, holding only services.

    >>> ctx = HeadlessAppContext(llm=my_llm, user="a@b.c",
    ...                          getWanApiEndpoint="https://api.example.com")
    >>> ctx.user
    'a@b.c'
    >>> ctx.getWanApiEndpoint()
    'https://api.example.com'
    """

    def __init__(self, *, browser_capable: bool = False,
                 services: Optional[Dict[str, Any]] = None, **kwargs: Any):
        # _-prefixed so __getattr__ (below) never intercepts them.
        self._services: Dict[str, Any] = dict(services or {})
        self._services.update(kwargs)
        self._browser_capable = bool(browser_capable)

    # -- introspection -------------------------------------------------

    @property
    def browser_capable(self) -> bool:
        return self._browser_capable

    def provided(self) -> Set[str]:
        return set(self._services)

    def missing_expected(self) -> Set[str]:
        """Expected services this context does not provide.

        Call it at startup to fail fast on an incomplete context rather than
        discovering the gap mid-conversation.
        """
        return EXPECTED_SERVICES - set(self._services)

    def provide(self, name: str, value: Any) -> None:
        self._services[name] = value

    # -- the locator ---------------------------------------------------

    def __getattr__(self, name: str) -> Any:
        # Only reached when normal attribute lookup fails.
        if name.startswith("_"):
            raise AttributeError(name)

        services = self.__dict__.get("_services") or {}
        if name in services:
            value = services[name]
            if name in METHOD_SERVICES and not callable(value):
                return lambda *a, **k: value
            return value

        if name in BROWSER_SERVICES:
            if not self.__dict__.get("_browser_capable"):
                raise MissingService(
                    f"'{name}' needs a browser-capable vehicle; this headless "
                    f"context has browser_capable=False. Declare the skill with "
                    f"requires=['browser_local'] so it is scheduled onto one."
                )
            raise MissingService(
                f"'{name}' is a browser service and this browser-capable "
                f"context did not provide it."
            )

        if name in DESKTOP_ONLY_SERVICES:
            raise MissingService(
                f"'{name}' is desktop/Qt-only plumbing with no headless "
                f"equivalent; it cannot be served from a pod."
            )

        raise MissingService(
            f"HeadlessAppContext provides no service '{name}'. Add it to the "
            f"context, or declare the requirement on the skill."
        )

    # -- write-backs ---------------------------------------------------

    def setWebDriver(self, driver: Any) -> None:
        """Call sites write the driver back onto the locator.

        ``browser_node/session.py`` and ``build_helpers.py`` both do this, so a
        read-only locator would break them.
        """
        if not self._browser_capable:
            raise MissingService(
                "setWebDriver needs a browser-capable vehicle; this headless "
                "context has browser_capable=False."
            )
        self._services["getWebDriver"] = driver


# ---------------------------------------------------------------------------
# Installation
# ---------------------------------------------------------------------------

def install_headless_context(context: HeadlessAppContext,
                             *, strict: bool = True) -> HeadlessAppContext:
    """Make ``context`` what ``AppContext.get_main_window()`` returns.

    Also turns headless mode on, so an unprovided service anywhere else in
    ``AppContext`` is loud rather than ``None``.
    """
    import app_context as ac

    ac.set_headless(True)
    ac.AppContext.get_instance().main_window = context

    if strict:
        missing = context.missing_expected()
        if missing:
            raise MissingService(
                f"Headless context is incomplete; missing "
                f"{sorted(missing)}. Provide them, or pass strict=False to "
                f"start anyway (each missing service will still raise on use)."
            )
    return context


def uninstall_headless_context() -> None:
    """Restore desktop behaviour (tests, and a process that goes back to GUI)."""
    import app_context as ac

    ac.AppContext.get_instance().main_window = None
    ac.set_headless(None)
