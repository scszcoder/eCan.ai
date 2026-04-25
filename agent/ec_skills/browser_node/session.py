"""Browser session lifecycle + cache for the browser-automation node.

``BrowserSessionManager`` owns:
  * a per-scope cache of live ``BrowserSession`` instances
  * per-scope last-known focus target ids (survive session recreation)
  * per-CDP-port startup locks (serialise concurrent ``start()`` calls)
  * lifecycle/aliveness predicates
  * scope-key resolution (chat-id-based or node-based)
  * one-shot lifecycle debug hooks (``reset``/``reconnect`` tracing)

A single instance is created per compiled node (lifetime = same as
``build_browser_automation_node``'s factory closure used to be).
"""

from __future__ import annotations

import asyncio
import json
import threading
import traceback
from typing import Any
from urllib.parse import urlparse

from utils.logger_helper import logger_helper as logger

from agent.ec_skills.browser_node.config import (
    NodeConfig,
    MAX_BROWSER_CACHE_SIZE,
    NEW_TAB_WAIT_SEC,
)


# ─────────────────────────────────────────────────────────────────────
# Module-level cache (cross-instance) — passive agents are keyed by
# BrowserSession id and shared so cleanup logic in this manager can
# evict them when their underlying session goes away.
# ─────────────────────────────────────────────────────────────────────
try:
    from agent.ec_skills.browser_use_extension.passive_agent import PassiveAgent  # noqa: F401
except Exception:
    pass

_cached_passive_agents: dict[int, Any] = {}


# ─────────────────────────────────────────────────────────────────────
# BrowserSessionManager
# ─────────────────────────────────────────────────────────────────────

class BrowserSessionManager:
    """Manages BrowserSession acquisition, caching, and lifecycle.

    Replaces the closure-scoped helpers
    (`_cached_browser_sessions`, `_is_session_alive`,
    `_get_or_create_browser_session`, `_patch_browser_session_lifecycle_debug`,
    etc.) that previously lived inside ``build_browser_automation_node``.
    """

    def __init__(self, cfg: NodeConfig):
        self.cfg = cfg
        self._cached_sessions: dict[str, Any] = {}
        self._last_focus_ids: dict[str, str] = {}
        self._start_locks: dict[int, threading.Lock] = {}

    # ── Public predicates ────────────────────────────────────────

    @property
    def cached_sessions(self) -> dict[str, Any]:
        """Direct dict access (used by hook-context factory)."""
        return self._cached_sessions

    @property
    def last_focus_ids(self) -> dict[str, str]:
        return self._last_focus_ids

    # ── Scope key resolution ──────────────────────────────────────

    def resolve_scope_key(self, state: dict | None = None) -> str:
        """Stable scope key for cache + isolation.

        Prefers chat/session identity when present
        (``chat:<id>``); otherwise falls back to ``node:<node_name>``
        so simple per-node flows still get a stable cache slot.
        """
        try:
            state = state or {}
            attrs = state.get("attributes", {}) if isinstance(state, dict) else {}
            params = attrs.get("params", {}) if isinstance(attrs, dict) else {}
            meta_params: dict = {}
            if isinstance(params.get("metadata"), dict):
                meta_params = params.get("metadata", {}).get("params", {}) or {}

            candidates = [
                attrs.get("chat_id"),
                params.get("chatId"),
                meta_params.get("chatId"),
            ]
            if isinstance(state, dict):
                messages = state.get("messages")
                if isinstance(messages, list) and len(messages) > 1:
                    candidates.append(messages[1])

            for value in candidates:
                if value:
                    return f"chat:{value}"
        except Exception:
            pass
        return f"node:{self.cfg.node_name}"

    @staticmethod
    def extract_assignment_scope(runtime_input: str) -> dict:
        """Best-effort JSON parse of the live invocation payload."""
        if not isinstance(runtime_input, str) or not runtime_input.strip():
            return {}
        try:
            payload = json.loads(runtime_input)
            if isinstance(payload, dict):
                return payload
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
        return {}

    # ── Aliveness checks ──────────────────────────────────────────

    @staticmethod
    def is_started(session: Any) -> bool:
        """``session_manager`` non-None alone is insufficient — root CDP
        client must also be initialised."""
        if session is None:
            return False
        if getattr(session, "_ecan_fast_attach_ready", False):
            return True
        root = getattr(session, "_cdp_client_root", None) or getattr(session, "cdp_client_root", None)
        if root is not None:
            return True
        return (
            getattr(session, "session_manager", None) is not None
            and getattr(session, "event_bus", None) is not None
        )

    @classmethod
    def is_alive(cls, session: Any) -> bool:
        """``is_started`` + event bus running + CDP websocket open."""
        if not cls.is_started(session):
            return False
        try:
            eb = getattr(session, "event_bus", None)
            if eb is None:
                return False
            eq = getattr(eb, "event_queue", None)
            if eq is not None and getattr(eq, "_is_shutdown", False):
                return False
            if not getattr(eb, "_is_running", False):
                return False
            cdp = getattr(session, "_cdp_client_root", None) or getattr(session, "cdp_client_root", None)
            if cdp:
                ws = getattr(cdp, "ws", None) or getattr(cdp, "websocket", None)
                if ws is not None and (getattr(ws, "closed", False) or getattr(ws, "_closed", False)):
                    return False
            return True
        except Exception:
            return False

    def cleanup_stale_sessions(self) -> None:
        """Remove dead sessions from the cache (CDP websocket closed)."""
        with threading.Lock():
            stale: list[str] = []
            for scope, session in self._cached_sessions.items():
                try:
                    cdp = getattr(session, "_cdp_client_root", None) or getattr(session, "cdp_client_root", None)
                    if cdp:
                        ws = getattr(cdp, "ws", None) or getattr(cdp, "websocket", None)
                        if ws is not None and (getattr(ws, "closed", False) or getattr(ws, "_closed", False)):
                            stale.append(scope)
                except Exception:
                    pass
            for scope in stale:
                self._cached_sessions.pop(scope, None)
                logger.debug(f"[BrowserSessionManager] Removed dead session: {scope}")

    # ── Public acquisition entrypoint ─────────────────────────────

    async def get_or_create(
        self,
        mainwin: Any,
        state: dict | None = None,
        calling_agent_id: str | None = None,
    ) -> Any:
        """Acquire a fresh-or-cached ``BrowserSession`` for *state*."""
        scope = self.resolve_scope_key(state)
        cached = self._cached_sessions.get(scope)
        last_focus = self._last_focus_ids.get(scope)

        if cached is not None and self.is_alive(cached):
            logger.debug(f"[BrowserSessionManager] Reusing cached session: {cached.id}")
            return cached

        # Stale cache — preserve the focus target id before discarding.
        if cached is not None:
            last_focus = self._invalidate_stale(scope, cached, last_focus)

        # Browser-manager handle.
        browser_manager = self._get_or_create_browser_manager(mainwin)
        if browser_manager is None:
            return None

        # Resolve runtime slot info from state (port, profile, slot_id).
        slot_info = self._resolve_runtime_slot(state)
        cdp_port = self._resolve_cdp_port(slot_info["cdp_port"], slot_info["slot_id"], browser_manager)

        # Acquire browser via BrowserManager.
        auto_browser = self._acquire_browser(
            mainwin=mainwin,
            browser_manager=browser_manager,
            scope=scope,
            cdp_port=cdp_port,
            state_profile=slot_info["profile"],
            calling_agent_id=calling_agent_id,
        )
        if auto_browser is None:
            return None

        # Start session under per-port startup lock (with retry).
        await self._start_session_locked(auto_browser, scope)

        # Restore focus + cache the session.
        if auto_browser.browser_session is not None:
            self._restore_focus(auto_browser.browser_session, last_focus)
            self._evict_oldest_if_full(scope)
            try:
                setattr(auto_browser.browser_session, "_ecan_browser_scope_key", scope)
            except Exception:
                pass
            self._cached_sessions[scope] = auto_browser.browser_session
            return auto_browser.browser_session

        return auto_browser

    # ── Internals: invalidation + browser-manager bootstrap ──────

    def _invalidate_stale(self, scope: str, cached: Any, last_focus: str | None) -> str | None:
        """Pop a dead session from the cache, preserving the focus id."""
        old_focus = getattr(cached, "agent_focus_target_id", None)
        if old_focus:
            last_focus = old_focus
            self._last_focus_ids[scope] = old_focus
            logger.info(
                f"[BrowserSessionManager] Saved focus from dying session: ...{old_focus[-4:]}"
            )
        old_sid = id(cached)
        old_pa = _cached_passive_agents.get(old_sid)
        if old_pa is not None:
            pa_focus = getattr(old_pa, "_last_focus_target_id", None)
            if pa_focus:
                last_focus = pa_focus
                self._last_focus_ids[scope] = pa_focus
                logger.info(
                    f"[BrowserSessionManager] Saved focus from PassiveAgent: ...{pa_focus[-4:]}"
                )
        logger.info(
            f"[BrowserSessionManager] Cached session {cached.id} stale; recreating"
        )
        _cached_passive_agents.pop(old_sid, None)
        self._cached_sessions.pop(scope, None)
        return last_focus

    @staticmethod
    def _get_or_create_browser_manager(mainwin: Any) -> Any:
        """Return ``mainwin.browser_manager``, creating it if needed."""
        try:
            from gui.manager.browser_manager import BrowserManager
        except Exception as exc:
            logger.error(f"[BrowserSessionManager] BrowserManager import failed: {exc}")
            return None

        if not hasattr(mainwin, "browser_manager") or mainwin.browser_manager is None:
            slots = None
            max_agents = 0
            try:
                gs = getattr(getattr(mainwin, "config_manager", None), "general_settings", None)
                if gs:
                    slots = gs.browser_slots or None
                    max_agents = gs.browser_max_agents_per_instance or 0
            except Exception:
                pass
            mainwin.browser_manager = BrowserManager(
                default_webdriver_path=mainwin.getWebDriverPath(),
                slots=slots,
                max_agents_per_browser=max_agents,
            )
        return mainwin.browser_manager

    # ── Internals: runtime slot resolution ────────────────────────

    @staticmethod
    def _resolve_runtime_slot(state: dict | None) -> dict:
        """Read CDP port / profile / slot_id from task state.

        Task state (assigned by the scheduler or auto-assigned by
        BrowserManager) takes priority over the skill-editor config.
        Returns a dict with keys ``cdp_port``, ``profile``, ``slot_id``
        (all strings, possibly empty).
        """
        out = {"cdp_port": "", "profile": "", "slot_id": ""}
        try:
            slot_state = state if isinstance(state, dict) else {}
            attrs = slot_state.get("attributes", {}) if isinstance(slot_state, dict) else {}
            params = attrs.get("params", {}) if isinstance(attrs, dict) else {}
            out["cdp_port"] = str(
                slot_state.get("cdp_port")
                or attrs.get("cdp_port")
                or params.get("cdp_port")
                or ""
            ).strip()
            out["profile"] = str(
                slot_state.get("browser_profile")
                or attrs.get("browser_profile")
                or params.get("browser_profile")
                or ""
            ).strip()
            out["slot_id"] = str(
                slot_state.get("browser_slot_id")
                or attrs.get("browser_slot_id")
                or params.get("browser_slot_id")
                or ""
            ).strip()
            if out["cdp_port"] or out["slot_id"]:
                logger.info(
                    f"[BrowserSessionManager] Runtime slot: "
                    f"cdp_port={out['cdp_port'] or '(auto)'}, "
                    f"slot_id={out['slot_id'] or '(none)'}, "
                    f"profile={out['profile'] or '(default)'}"
                )
        except Exception as exc:
            logger.debug(f"[BrowserSessionManager] runtime slot resolve failed: {exc}")
        return out

    def _resolve_cdp_port(
        self,
        state_cdp_port: str,
        state_slot_id: str,
        browser_manager: Any,
    ) -> int:
        """Resolve final CDP port. ``0`` means "auto-assign from pool"."""
        # If we have a slot_id but no cdp_port, resolve port from slot.
        if state_slot_id and not state_cdp_port:
            try:
                slot_obj = browser_manager.get_slot(state_slot_id)
                if slot_obj:
                    state_cdp_port = str(slot_obj.cdp_port)
                    logger.info(
                        f"[BrowserSessionManager] Slot {state_slot_id} → cdp_port={state_cdp_port}"
                    )
            except Exception:
                pass

        # Priority: runtime slot > skill-editor config > default 9228.
        cdp_port_setting = self.cfg.cdp_port
        source = "default"
        if state_cdp_port:
            source = "state"
            port_str = state_cdp_port
        elif cdp_port_setting:
            source = "config"
            port_str = cdp_port_setting
        else:
            port_str = ""

        if not port_str:
            cdp_port = 9228
        elif port_str.lower() == "auto" or port_str == "0":
            cdp_port = 0
        elif port_str.isdigit():
            cdp_port = int(port_str)
        else:
            cdp_port = 9228

        logger.info(
            f"[BrowserSessionManager] Resolved cdp_port="
            f"{'auto' if cdp_port == 0 else cdp_port} (from={source})"
        )
        return cdp_port

    # ── Internals: browser acquisition ────────────────────────────

    _BROWSER_TYPE_MAP_HINTS = {
        "new chromium": "CHROME",
        "existing chrome": "CHROME",
        "ads power": "ADSPOWER",
        "adspower": "ADSPOWER",
        "ziniao": "CHROME",
        "multi-login": "CHROME",
    }

    def _acquire_browser(
        self,
        *,
        mainwin: Any,
        browser_manager: Any,
        scope: str,
        cdp_port: int,
        state_profile: str,
        calling_agent_id: str | None,
    ) -> Any:
        """Acquire a browser via BrowserManager + log on failure."""
        from gui.manager.browser_manager import BrowserType, BrowserStatus

        bt_name = self._BROWSER_TYPE_MAP_HINTS.get(self.cfg.browser_type, "CHROME")
        browser_type = getattr(BrowserType, bt_name, BrowserType.CHROME)

        agent_id_base = (
            calling_agent_id
            or getattr(mainwin, "current_agent_id", "default_agent")
            or "default_agent"
        )
        isolate_scope = scope.startswith("chat:")
        node_agent_id = (
            f"{agent_id_base}:{self.cfg.node_name}:{scope}"
            if isolate_scope
            else f"{agent_id_base}:{self.cfg.node_name}"
        )
        task_label = (
            f"browser_automation_{self.cfg.node_name}:{scope}"
            if isolate_scope
            else f"browser_automation_{self.cfg.node_name}"
        )

        auto_browser = browser_manager.acquire_browser(
            agent_id=node_agent_id,
            task=task_label,
            browser_type=browser_type,
            cdp_port=cdp_port,
            webdriver_path=mainwin.getWebDriverPath(),
            downloads_path=self.cfg.downloads_path,
            profile=self.cfg.profile or state_profile,
        )

        if not auto_browser or auto_browser.status == BrowserStatus.ERROR:
            err = auto_browser.last_error if auto_browser else "Unknown error"
            logger.error(f"[BrowserSessionManager] Failed to acquire browser: {err}")
            return None

        # When cdp_port was auto (0), update to the actual assigned port.
        if cdp_port == 0 and auto_browser.cdp_port:
            logger.info(
                f"[BrowserSessionManager] Auto-assigned browser on cdp_port={auto_browser.cdp_port}"
            )

        if auto_browser.webdriver:
            mainwin.setWebDriver(auto_browser.webdriver)

        return auto_browser

    # ── Internals: session start (with per-port lock + retry) ─────

    async def _start_session_locked(self, auto_browser: Any, scope: str) -> None:
        """Start the session under a per-port lock with one retry."""
        if self.cfg.browser_driver != "native" or not auto_browser.browser_session:
            return

        session = auto_browser.browser_session
        cdp_port = auto_browser.cdp_port or 0

        # Fast-attach: existing-chrome scope where session is already started.
        fast_attach = scope.startswith("chat:") and self.cfg.browser_type == "existing chrome"
        if fast_attach:
            try:
                sm = getattr(session, "session_manager", None)
                eb = getattr(session, "event_bus", None)
                if sm and hasattr(sm, "get_all_targets"):
                    targets = sm.get_all_targets() or {}
                else:
                    targets = {}
                page_targets = [
                    tid for tid, t in targets.items()
                    if getattr(t, "target_type", "") in ("page", "tab")
                ]
                if eb is not None and page_targets:
                    setattr(session, "_ecan_fast_attach_ready", True)
                    logger.info(
                        f"[BrowserSessionManager] Fast-attach ready {session.id}: "
                        f"page_targets={len(page_targets)} scope={scope}"
                    )
                    return
            except Exception as exc:
                logger.warning(
                    f"[BrowserSessionManager] Fast-attach probe failed for {session.id}: {exc}"
                )

        if self.is_started(session):
            logger.info(
                f"[BrowserSessionManager] Session already started: {session.id} scope={scope}"
            )
            return

        # Acquire per-port startup lock (serialise concurrent start()s).
        start_lock = self._start_locks.setdefault(cdp_port, threading.Lock())
        logger.info(
            f"[BrowserSessionManager] Waiting startup lock cdp_port={cdp_port} "
            f"scope={scope} session={session.id}"
        )
        acquired = await asyncio.to_thread(lambda: start_lock.acquire(timeout=60))
        if not acquired:
            logger.error(
                f"[BrowserSessionManager] Startup lock timeout 60s cdp_port={cdp_port} scope={scope}"
            )
            return
        try:
            if self.is_started(session):
                return
            await self._do_session_start_with_retry(session, scope, cdp_port)
        finally:
            try:
                start_lock.release()
            except Exception:
                pass

    @staticmethod
    async def _do_session_start_with_retry(session: Any, scope: str, cdp_port: int) -> None:
        """Attempt ``session.start()`` with one retry after timeout."""
        async def _start_once() -> None:
            task = asyncio.create_task(session.start())
            await asyncio.wait_for(asyncio.shield(task), timeout=30)

        logger.info(
            f"[BrowserSessionManager] Starting session {session.id} scope={scope} cdp_port={cdp_port}"
        )
        try:
            await _start_once()
        except asyncio.TimeoutError:
            logger.warning(
                f"[BrowserSessionManager] start() timed out for {session.id}; retrying once"
            )
            try:
                await _start_once()
                logger.info(f"[BrowserSessionManager] Retry start() succeeded for {session.id}")
            except (asyncio.TimeoutError, Exception) as exc:
                logger.error(f"[BrowserSessionManager] Retry start() failed for {session.id}: {exc}")

    # ── Internals: focus restore + cache eviction ─────────────────

    @staticmethod
    def _restore_focus(session: Any, last_focus: str | None) -> None:
        if not last_focus:
            return
        try:
            from browser_use.browser.events import SwitchTabEvent

            cur = session.agent_focus_target_id
            if cur != last_focus:
                asyncio.ensure_future(
                    session.event_bus.dispatch(SwitchTabEvent(target_id=last_focus))
                )
                logger.info(
                    f"[BrowserSessionManager] Restored focus "
                    f"...{cur[-4:] if cur else 'None'} → ...{last_focus[-4:]}"
                )
        except Exception as exc:
            logger.warning(f"[BrowserSessionManager] Focus restore failed: {exc}")

    def _evict_oldest_if_full(self, current_scope: str) -> None:
        """Evict up to 2 non-chat scopes when cache exceeds the limit."""
        if len(self._cached_sessions) < MAX_BROWSER_CACHE_SIZE:
            return
        evicted = 0
        for scope in list(self._cached_sessions.keys()):
            if scope == current_scope or scope.startswith("chat:"):
                continue
            old = self._cached_sessions.pop(scope, None)
            self._last_focus_ids.pop(scope, None)
            if old is not None:
                _cached_passive_agents.pop(id(old), None)
            evicted += 1
            if evicted >= 2:
                break

    # ── Lifecycle debug instrumentation ───────────────────────────

    def patch_lifecycle_debug(self, session: Any, source: str) -> None:
        """Attach one-time debug hooks to ``session`` (idempotent)."""
        try:
            if session is None:
                return
            scope_key = getattr(session, "_ecan_browser_scope_key", "")
            cached_for_scope = self._cached_sessions.get(scope_key) if scope_key else None
            logger.info(
                f"[BrowserSessionManager][LifecycleDebug] Patch source={source} "
                f"session_obj={id(session)} cached_obj={id(cached_for_scope) if cached_for_scope else 'none'} "
                f"scope={scope_key or 'unscoped'}"
            )
            if not getattr(session, "_ecan_lifecycle_debug_patched", False):
                self._wrap_lifecycle_method(session, "reset")
                self._wrap_lifecycle_method(session, "reconnect")
                self._wrap_lifecycle_method(session, "_auto_reconnect")
                setattr(session, "_ecan_lifecycle_debug_patched", True)

            cdp_root = getattr(session, "_cdp_client_root", None)
            if cdp_root and hasattr(cdp_root, "stop") and not getattr(cdp_root, "_ecan_debug_patched", False):
                orig_stop = cdp_root.stop

                async def _debug_cdp_stop(*a, **kw):
                    logger.warning(
                        "[BrowserSessionManager][LifecycleDebug] CDPClient.stop() called.\n"
                        + "".join(traceback.format_stack(limit=20))
                    )
                    return await orig_stop(*a, **kw)

                cdp_root.stop = _debug_cdp_stop
                setattr(cdp_root, "_ecan_debug_patched", True)
        except Exception as exc:
            logger.warning(f"[BrowserSessionManager] Lifecycle patch failed: {exc}")

    @staticmethod
    def _wrap_lifecycle_method(session: Any, name: str) -> None:
        orig = getattr(session, name, None)
        if not orig:
            return

        async def _debug_wrap(*a, **kw):
            logger.warning(
                f"[BrowserSessionManager][LifecycleDebug] BrowserSession.{name}() called.\n"
                + "".join(traceback.format_stack(limit=20))
            )
            return await orig(*a, **kw)

        setattr(session, name, _debug_wrap)

    # ── Misc helpers ──────────────────────────────────────────────

    def get_profile_settings(self) -> dict:
        """Load browser profile settings via the GUI handler."""
        try:
            from gui.ipc.w2p_handlers.browser_use_handler import (
                get_profile_by_name,
                get_default_profile,
            )

            profile = (
                get_profile_by_name(self.cfg.profile)
                if self.cfg.profile
                else get_default_profile()
            )
            if profile:
                logger.debug(
                    f"[BrowserSessionManager] Loaded profile: {profile.get('name', 'unknown')}"
                )
                return profile
        except Exception as exc:
            logger.warning(f"[BrowserSessionManager] profile load failed: {exc}")
        return {}

    @staticmethod
    def is_matching_control_url(actual: str, preferred: str) -> bool:
        """Treat ``localhost`` and ``127.0.0.1`` as equivalent for /control."""
        if not actual or not preferred:
            return False
        try:
            a = urlparse(actual)
            p = urlparse(preferred)
            a_host = (a.hostname or "").lower()
            p_host = (p.hostname or "").lower()
            local = {"127.0.0.1", "localhost"}
            if a_host not in local or p_host not in local:
                return actual.rstrip("/") == preferred.rstrip("/")
            return (
                (a.port or 80) == (p.port or 80)
                and a.path.rstrip("/").startswith("/control")
                and p.path.rstrip("/").startswith("/control")
            )
        except Exception:
            return actual.rstrip("/") == preferred.rstrip("/")
