"""A MainWindow-shaped context for a headless worker process.

``EC_Agent`` and everything under it reach through ``mainwin`` for the LLM, the
database, the thread pool, config and auth. A worker has no window, so it needs
an object of that shape — but not a fake MainWindow: only the parts that a
running agent actually touches, built from the data home it *shares* with the
parent app.

Sharing is the point. The worker reads the same database, the same config, the
same auth session and the same browser profiles as the app that launched it
(see ``config/instance.py`` for what is and is not scoped per worker). It is
not a second installation; it is the same installation executing one isolation
domain in its own address space.

On the attributes that are not here
-----------------------------------
``agent/`` reaches for about sixty distinct ``mainwin.`` attributes across
every path it has ever had, most of them legacy or GUI-only. Implementing all
sixty speculatively would mean inventing behaviour for code paths a worker may
never take. Instead, anything not provided raises ``AttributeError`` — normal
Python, which the heavily-guarded call sites around here already absorb — after
naming it once at WARNING.

WARNING rather than ERROR, because this codebase probes the window defensively
everywhere: ``getattr(mainwin, "x", None)`` reaches ``__getattr__`` too, and
that caller is perfectly happy with the AttributeError. From inside there is no
way to tell a probe from a real need, so the log is a *lead*, not a verdict.
The verdict comes from the worker smoke test, which asserts agents actually
build — which is how the first two real gaps (``get_free_agent_ports`` and
``agent_conversion_failures``) were found, having blocked all 18.
"""

from __future__ import annotations

import concurrent.futures
import os
from typing import Any, Dict, List, Optional

from utils.logger_helper import logger_helper as logger


class WorkerContext:
    """What a headless worker passes as ``mainwin``."""

    def __init__(self, user: str, data_home: str, *, max_workers: int = 8):
        # First, so __getattr__ can never recurse looking for it.
        object.__setattr__(self, "_reported_gaps", set())

        # ── identity and paths (shared with the parent) ──
        self.user = user
        self.owner = user
        local_part, _, domain_part = user.partition("@")
        self.log_user = f"{local_part}_{domain_part.replace('.', '_')}" if domain_part else user
        self.my_ecb_data_homepath = data_home
        self.ecb_data_homepath = os.path.dirname(data_home.rstrip("/\\"))

        # ── config, shared with the parent because the data home is shared ──
        from gui.manager.config_manager import ConfigManager
        self.config_manager = ConfigManager(data_home)

        # ── database: the SAME file the parent uses. Safe because the engine
        # already runs WAL with a 60s busy timeout, which is what lets several
        # processes hold one SQLite file (agent/db/core/base.py).
        from agent.db import initialize_ecan_database
        self.ec_db_mgr = initialize_ecan_database(data_home, auto_migrate=False)

        # ── execution ──
        self.threadPoolExecutor = concurrent.futures.ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="WorkerCtx",
        )

        # ── pools the agent converter reads; a worker builds agents straight
        # from the database rather than from compiled pools, so these stay
        # empty and the converter falls back to the per-agent data.
        self.agents: List[Any] = []
        self.agent_skills: List[Any] = []
        self.agent_tasks: List[Any] = []
        self.agent_tools: List[Any] = []
        self.knowledges: List[Any] = []

        # ── agent ports: the A2A server each agent binds. Same allocator the
        # app uses, which keeps its own lock, so parallel agent starts cannot
        # hand two agents the same port.
        from utils.port_allocator import get_port_allocator
        self._port_allocator = get_port_allocator()

        # Read back by the converter and the Agents page to explain why an
        # agent did not build. A real attribute, not a probe: it is written to.
        self.agent_conversion_failures: Dict[str, Any] = {}

        # ── session / transport state the GUI would own ──
        self.session = None
        self.mcp_client = None
        self.bots: List[Any] = []
        self._websocket = None
        self._wan_connected = False
        self._wan_msg_subscribed = False
        self._web_driver = None

        # ── auth, read from the session the parent already persisted ──
        self.auth_manager = self._build_auth_manager()

        # ── LLMs, built the same way MainGUI builds them ──
        self.llm, self.browser_use_llm = self._build_llms()

    # ── auth ─────────────────────────────────────────────────────────
    def _build_auth_manager(self) -> Any:
        try:
            from gui.LoginoutGUI import Login
            return Login()
        except Exception as exc:
            logger.warning(
                f"[WorkerContext] no auth manager ({exc}); cloud calls from this "
                f"worker will be unauthenticated"
            )
            return None

    def get_auth_token(self) -> Optional[str]:
        """The parent's token, read from the shared session store.

        Returns None rather than a stale token when the session is not signed
        in, so cloud callers fail fast with "re-login required" instead of
        looping on a token the server will reject — same contract as the app.
        """
        mgr = self.auth_manager
        if mgr is None:
            return None
        try:
            if hasattr(mgr, "get_auth_token"):
                return mgr.get_auth_token()
            if not getattr(mgr, "signed_in", False):
                return None
            tokens = getattr(mgr, "tokens", None) or {}
            return tokens.get("IdToken") or tokens.get("AccessToken")
        except Exception as exc:
            logger.warning(f"[WorkerContext] could not read the auth token: {exc}")
            return None

    # ── LLM ──────────────────────────────────────────────────────────
    def _build_llms(self):
        try:
            from agent.ec_skills.llm_utils.llm_utils import pick_llm, pick_browser_use_llm
            llm = pick_llm(
                self.config_manager.general_settings.default_llm,
                self.config_manager.llm_manager.get_all_providers(),
                self.config_manager,
            )
            browser_llm = pick_browser_use_llm(mainwin=self)
            logger.info(
                f"[WorkerContext] LLM={type(llm).__name__ if llm else None} "
                f"browser_use_llm={type(browser_llm).__name__ if browser_llm else None}"
            )
            return llm, browser_llm
        except Exception as exc:
            logger.error(f"[WorkerContext] LLM initialisation failed: {exc}")
            return None, None

    # ── small accessors the agent path uses ──────────────────────────
    def get_local_server_port(self) -> str:
        from agent.mcp.config import get_local_port
        return str(get_local_port())

    def get_server_base_url(self) -> str:
        """Base URL of this process's local server.

        Its own, not the parent's: the worker binds a different port (see
        config/instance.py), so handing out the parent's URL would point
        callbacks at the wrong process.
        """
        from agent.mcp.config import base_url
        return base_url()

    def getWanApiEndpoint(self) -> str:
        try:
            return self.config_manager.general_settings.wan_api_endpoint
        except Exception:
            return ""

    def getWanApiKey(self) -> str:
        try:
            return self.config_manager.general_settings.wan_api_key
        except Exception:
            return ""

    def getAcctSiteID(self) -> str:
        try:
            return self.config_manager.general_settings.acct_site_id
        except Exception:
            return ""

    # Selenium handle: plain state, as on the window.
    def getWebDriver(self):
        return self._web_driver

    def setWebDriver(self, driver):
        self._web_driver = driver

    def getWebDriverPath(self) -> str:
        try:
            return self.config_manager.general_settings.webdriver_path
        except Exception:
            return ""

    # WAN connectivity flags the messaging layer toggles.
    def set_wan_connected(self, value: bool) -> None:
        self._wan_connected = bool(value)

    def get_wan_connected(self) -> bool:
        return self._wan_connected

    def set_wan_msg_subscribed(self, value: bool) -> None:
        self._wan_msg_subscribed = bool(value)

    def get_wan_msg_subscribed(self) -> bool:
        return self._wan_msg_subscribed

    def set_websocket(self, ws) -> None:
        self._websocket = ws

    def get_websocket(self):
        return self._websocket

    # ── the gap reporter ─────────────────────────────────────────────
    def get_free_agent_ports(self, n: int) -> List[int]:
        """Free local ports for ``n`` agents' A2A servers."""
        try:
            port_range = self.config_manager.general_settings.local_agent_ports
        except Exception:
            port_range = []
        return self._port_allocator.get_free_ports(n, port_range, [])

    def __getattr__(self, name: str) -> Any:
        # Only reached when normal lookup failed, so this never shadows a real
        # attribute. Raising (rather than inventing a default) keeps the worker
        # from taking a path nobody designed it for.
        #
        # WARNING, not ERROR, and once per name: this codebase probes the window
        # defensively all over -- ``getattr(mainwin, "x", None)`` reaches here
        # too, and that caller is perfectly happy with the AttributeError. There
        # is no way to tell a probe from a real need from in here, so the log is
        # a lead to follow, and the proof that nothing is missing is the worker
        # smoke test asserting agents actually build.
        if name not in self._reported_gaps:
            self._reported_gaps.add(name)
            logger.warning(
                f"[WorkerContext] no {name!r} on the worker context. Harmless if "
                f"the caller probed with a default; if a worker path truly needs "
                f"it, add it here rather than guessing a value."
            )
        raise AttributeError(name)

    def shutdown(self) -> None:
        try:
            self.threadPoolExecutor.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass


def load_agents_from_db(ctx: WorkerContext) -> List[Any]:
    """Build EC_Agent objects from the shared database.

    The local database only — the parent owns cloud sync and has already merged
    into it. A worker that also synced would be a second writer racing the
    parent for the same rows.
    """
    from agent.agent_converter import convert_agent_dict_to_ec_agent

    try:
        result = ctx.ec_db_mgr.agent_service.query_agents()
    except Exception as exc:
        logger.error(f"[WorkerContext] could not read agents: {exc}")
        return []

    rows = (result or {}).get("data") or []
    agents = []
    for row in rows:
        try:
            agent = convert_agent_dict_to_ec_agent(row, ctx)
            if agent is not None:
                agents.append(agent)
        except Exception as exc:
            logger.error(
                f"[WorkerContext] could not build agent "
                f"{(row or {}).get('name', '?')!r}: {exc}"
            )
    logger.info(f"[WorkerContext] built {len(agents)} agent(s) from {len(rows)} row(s)")
    return agents
