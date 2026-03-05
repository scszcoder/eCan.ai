"""
Browser Event Service - Bridges CDP browser events to eCan.ai's pend_event system.

Manages subscriptions to Chrome DevTools Protocol events and dispatches them
as "browser_event" messages through the agent runner queue system, analogous
to how TimerService dispatches "timer" events.

Usage:
    svc = get_browser_event_service()
    sub = await svc.subscribe(
        agent_id="...",
        cdp_client=cdp_client,
        domain="Network",
        event_method="Network.responseReceived",
        label="price_api",
        filter_expr="url contains 'api/price'",
    )
    # Later:
    svc.unsubscribe(sub.sub_id)
"""

import asyncio
import re
import time
import uuid
import threading
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from utils.logger_helper import logger_helper as logger

if TYPE_CHECKING:
    pass


# ==================== Known CDP Domains & Enable Commands ====================

# Domains that require an explicit .enable() call before events flow.
# Maps domain name -> CDP enable method string.
DOMAIN_ENABLE_METHODS: Dict[str, str] = {
    "Network": "Network.enable",
    "Page": "Page.enable",
    "DOM": "DOM.enable",
    "CSS": "CSS.enable",
    "Runtime": "Runtime.enable",
    "Console": "Console.enable",
    "Log": "Log.enable",
    "Security": "Security.enable",
    "Performance": "Performance.enable",
    "DOMStorage": "DOMStorage.enable",
    "Debugger": "Debugger.enable",
    "Overlay": "Overlay.enable",
}

# Domains that are enabled via special commands (not a simple .enable())
# These are handled case-by-case in _ensure_domain_enabled.
SPECIAL_ENABLE_DOMAINS = {"Target", "Fetch", "Browser"}


class BrowserEventSubscription:
    """One active CDP event subscription."""

    def __init__(
        self,
        sub_id: str,
        agent_id: str,
        domain: str,
        event_method: str,
        label: str,
        filter_expr: str,
        created_at: float,
    ):
        self.sub_id = sub_id
        self.agent_id = agent_id
        self.domain = domain
        self.event_method = event_method  # e.g. "Network.responseReceived"
        self.label = label                # user-friendly name, used as composite key
        self.filter_expr = filter_expr    # e.g. "url contains 'api/price'"
        self.created_at = created_at
        self.fire_count: int = 0
        self.cancelled: bool = False
        self._compiled_filter: Optional[Callable[[dict], bool]] = None

        # Pre-compile the filter expression
        if filter_expr:
            self._compiled_filter = _compile_filter(filter_expr)

    def matches(self, event_params: dict) -> bool:
        """Check if an incoming CDP event matches this subscription's filter."""
        if self.cancelled:
            return False
        if not self._compiled_filter:
            return True  # no filter = match everything
        try:
            return self._compiled_filter(event_params)
        except Exception as e:
            logger.debug(f"[BROWSER_EVENT] Filter eval error for '{self.label}': {e}")
            return False

    def to_dict(self) -> dict:
        return {
            "sub_id": self.sub_id,
            "agent_id": self.agent_id,
            "domain": self.domain,
            "event_method": self.event_method,
            "label": self.label,
            "filter_expr": self.filter_expr,
            "fire_count": self.fire_count,
            "created_at": self.created_at,
            "cancelled": self.cancelled,
        }


# ==================== Filter Compiler ====================

def _compile_filter(expr: str) -> Callable[[dict], bool]:
    """
    Compile a simple filter expression into a callable.

    Supported syntax:
        "url contains 'some_string'"
        "status == 200"
        "method == 'POST'"
        "type == 'XHR'"

    The filter operates on the flattened CDP event params dict.
    Nested fields are accessed via dot notation: "response.url contains 'price'"
    """
    expr = expr.strip()
    if not expr:
        return lambda params: True

    # Pattern: <field> <op> <value>
    m = re.match(
        r"^([\w.]+)\s+(contains|==|!=|startswith|endswith)\s+['\"]?(.*?)['\"]?\s*$",
        expr,
        re.IGNORECASE,
    )
    if not m:
        logger.warning(f"[BROWSER_EVENT] Could not parse filter: '{expr}', will match all")
        return lambda params: True

    field_path = m.group(1)
    op = m.group(2).lower()
    value = m.group(3)

    def _resolve(params: dict, path: str):
        """Resolve a dot-separated path against a nested dict."""
        parts = path.split(".")
        cur = params
        for p in parts:
            if isinstance(cur, dict):
                cur = cur.get(p)
            else:
                return None
        return cur

    def _filter_fn(params: dict) -> bool:
        resolved = _resolve(params, field_path)
        if resolved is None:
            return False
        resolved_str = str(resolved)
        if op == "contains":
            return value in resolved_str
        elif op == "==":
            return resolved_str == value or resolved_str == str(value)
        elif op == "!=":
            return resolved_str != value and resolved_str != str(value)
        elif op == "startswith":
            return resolved_str.startswith(value)
        elif op == "endswith":
            return resolved_str.endswith(value)
        return False

    return _filter_fn


# ==================== Browser Event Service (singleton) ====================

class BrowserEventService:
    """
    Manages CDP event subscriptions and dispatches matching events to
    agent runners as "browser_event" messages.
    """

    def __init__(self):
        self._lock = threading.Lock()
        # sub_id -> BrowserEventSubscription
        self._subscriptions: Dict[str, BrowserEventSubscription] = {}
        # Track which CDP domains have been enabled (per cdp_client id)
        self._enabled_domains: Dict[int, set] = {}
        # Track which CDP event methods have a handler registered (per cdp_client id)
        # so we don't double-register when multiple subscriptions watch the same method
        self._registered_methods: Dict[int, set] = {}

    # -------------------- Public API --------------------

    async def subscribe(
        self,
        agent_id: str,
        cdp_client,
        domain: str,
        event_method: str,
        label: str,
        filter_expr: str = "",
        sub_id: Optional[str] = None,
    ) -> BrowserEventSubscription:
        """
        Subscribe to a CDP event and route matching events to runners.

        Args:
            agent_id: The owning agent's ID.
            cdp_client: The cdp_use.CDPClient instance.
            domain: CDP domain (e.g. "Network", "Page", "DOM", "Runtime").
            event_method: Full CDP method (e.g. "Network.responseReceived").
            label: User-friendly label used as routing key ("browser_event:<label>").
            filter_expr: Optional filter (e.g. "response.url contains 'price'").
            sub_id: Optional explicit subscription ID.

        Returns:
            BrowserEventSubscription
        """
        sub_id = sub_id or str(uuid.uuid4())[:12]

        sub = BrowserEventSubscription(
            sub_id=sub_id,
            agent_id=agent_id,
            domain=domain,
            event_method=event_method,
            label=label,
            filter_expr=filter_expr,
            created_at=time.time(),
        )

        # 1. Enable the CDP domain if not already enabled
        await self._ensure_domain_enabled(cdp_client, domain)

        # 2. Register a CDP event handler if not already registered for this method
        self._ensure_handler_registered(cdp_client, event_method)

        # 3. Store the subscription
        with self._lock:
            self._subscriptions[sub_id] = sub

        logger.info(
            f"[BROWSER_EVENT] Subscribed: label='{label}', method={event_method}, "
            f"filter='{filter_expr}', sub_id={sub_id}"
        )
        return sub

    def unsubscribe(self, sub_id: str) -> bool:
        """Remove a subscription by ID."""
        with self._lock:
            sub = self._subscriptions.pop(sub_id, None)
        if sub:
            sub.cancelled = True
            logger.info(f"[BROWSER_EVENT] Unsubscribed: label='{sub.label}', sub_id={sub_id}")
            return True
        return False

    def unsubscribe_by_label(self, label: str, agent_id: str = "") -> bool:
        """Remove subscription(s) by label (and optionally agent_id)."""
        removed = False
        with self._lock:
            to_remove = [
                sid for sid, sub in self._subscriptions.items()
                if sub.label == label and (not agent_id or sub.agent_id == agent_id)
            ]
            for sid in to_remove:
                sub = self._subscriptions.pop(sid, None)
                if sub:
                    sub.cancelled = True
                    removed = True
        if removed:
            logger.info(f"[BROWSER_EVENT] Unsubscribed by label: '{label}'")
        return removed

    def list_subscriptions(self, agent_id: str = "") -> List[BrowserEventSubscription]:
        """List all (or per-agent) active subscriptions."""
        with self._lock:
            subs = list(self._subscriptions.values())
        if agent_id:
            subs = [s for s in subs if s.agent_id == agent_id]
        return [s for s in subs if not s.cancelled]

    def find_by_label(self, label: str, agent_id: str = "") -> Optional[BrowserEventSubscription]:
        """Find a subscription by label."""
        with self._lock:
            for sub in self._subscriptions.values():
                if sub.label == label and not sub.cancelled:
                    if not agent_id or sub.agent_id == agent_id:
                        return sub
        return None

    def clear_all(self):
        """Cancel and remove all subscriptions."""
        with self._lock:
            for sub in self._subscriptions.values():
                sub.cancelled = True
            self._subscriptions.clear()
            self._enabled_domains.clear()
            self._registered_methods.clear()
        logger.info("[BROWSER_EVENT] Cleared all subscriptions")

    # -------------------- Internal --------------------

    async def _ensure_domain_enabled(self, cdp_client, domain: str):
        """Enable a CDP domain if we haven't already for this client."""
        client_id = id(cdp_client)
        if client_id not in self._enabled_domains:
            self._enabled_domains[client_id] = set()

        if domain in self._enabled_domains[client_id]:
            return  # already enabled

        if domain in DOMAIN_ENABLE_METHODS:
            try:
                await cdp_client.send_raw(DOMAIN_ENABLE_METHODS[domain], {})
                self._enabled_domains[client_id].add(domain)
                logger.info(f"[BROWSER_EVENT] Enabled CDP domain: {domain}")
            except Exception as e:
                logger.warning(f"[BROWSER_EVENT] Failed to enable domain {domain}: {e}")
        elif domain in SPECIAL_ENABLE_DOMAINS:
            # These are typically already enabled by browser_use itself
            self._enabled_domains[client_id].add(domain)
            logger.debug(f"[BROWSER_EVENT] Domain '{domain}' uses special enable — assumed active")
        else:
            # Unknown domain — try generic enable
            try:
                await cdp_client.send_raw(f"{domain}.enable", {})
                self._enabled_domains[client_id].add(domain)
                logger.info(f"[BROWSER_EVENT] Enabled CDP domain (generic): {domain}")
            except Exception as e:
                logger.debug(f"[BROWSER_EVENT] Generic enable for '{domain}' failed: {e}")
                self._enabled_domains[client_id].add(domain)  # mark to avoid retrying

    def _ensure_handler_registered(self, cdp_client, event_method: str):
        """Register a CDP event handler for a method if not already registered."""
        client_id = id(cdp_client)
        if client_id not in self._registered_methods:
            self._registered_methods[client_id] = set()

        if event_method in self._registered_methods[client_id]:
            return  # already have a handler

        # Chain with any existing handler (browser_use may have registered one)
        existing_handler = cdp_client._event_registry._handlers.get(event_method)

        def _on_cdp_event(params, session_id=None):
            """Called synchronously by cdp_use when a CDP event fires."""
            # Dispatch to matching subscriptions
            self._dispatch_to_subscriptions(event_method, params, session_id)
            # Call the original handler if one existed
            if existing_handler:
                try:
                    existing_handler(params, session_id)
                except Exception as e:
                    logger.debug(f"[BROWSER_EVENT] Original handler error for {event_method}: {e}")

        # Register via the raw registry (avoids needing domain-specific register API)
        cdp_client._event_registry.register(event_method, _on_cdp_event)
        self._registered_methods[client_id].add(event_method)
        logger.debug(f"[BROWSER_EVENT] Registered CDP handler for {event_method} (chained={existing_handler is not None})")

    def _dispatch_to_subscriptions(self, event_method: str, params: dict, session_id: Optional[str]):
        """Check all subscriptions for this event_method and dispatch matches."""
        with self._lock:
            matching_subs = [
                sub for sub in self._subscriptions.values()
                if sub.event_method == event_method and not sub.cancelled
            ]

        for sub in matching_subs:
            if sub.matches(params):
                sub.fire_count += 1
                self._dispatch_to_runners(sub, params, session_id)

    def _dispatch_to_runners(
        self,
        sub: BrowserEventSubscription,
        params: dict,
        session_id: Optional[str],
    ):
        """Dispatch a browser event to all agent runners (broadcast, like timer)."""
        try:
            browser_event = {
                "type": "browser_event",
                "sub_type": sub.label,
                "sub_id": sub.sub_id,
                "event_method": sub.event_method,
                "domain": sub.domain,
                "fire_count": sub.fire_count,
                "agent_id": sub.agent_id,
                "session_id": session_id,
                "params": _truncate_params(params),
                "timestamp": int(time.time() * 1000),
            }

            # Broadcast to ALL agent runners (same pattern as timer_mcp_tools)
            from app_context import AppContext
            runners = []
            try:
                mw = AppContext.get_main_window()
                if mw and hasattr(mw, "agents"):
                    for ag in (mw.agents or []):
                        r = getattr(ag, "runner", None)
                        if r:
                            runners.append(r)
            except Exception:
                pass

            if not runners:
                logger.warning(
                    f"[BROWSER_EVENT] No runners available for '{sub.label}' "
                    f"(method={sub.event_method})"
                )
                return

            dispatched = 0
            for runner in runners:
                try:
                    runner.sync_task_wait_in_line("browser_event", browser_event, source="browser_event_service")
                    dispatched += 1
                except Exception as re:
                    logger.debug(f"[BROWSER_EVENT] Runner dispatch failed: {re}")

            logger.debug(
                f"[BROWSER_EVENT] Dispatched '{sub.label}' "
                f"(fire #{sub.fire_count}, method={sub.event_method}) "
                f"to {dispatched}/{len(runners)} runner(s)"
            )
        except Exception as e:
            logger.error(f"[BROWSER_EVENT] Failed to dispatch: {e}")


def _truncate_params(params: dict, max_depth: int = 3, max_str_len: int = 500) -> dict:
    """Truncate large CDP event params to avoid bloating the event queue."""
    if not isinstance(params, dict):
        return params

    def _truncate(obj, depth):
        if depth <= 0:
            return "...(truncated)"
        if isinstance(obj, dict):
            return {k: _truncate(v, depth - 1) for k, v in list(obj.items())[:30]}
        elif isinstance(obj, list):
            return [_truncate(v, depth - 1) for v in obj[:20]]
        elif isinstance(obj, str) and len(obj) > max_str_len:
            return obj[:max_str_len] + f"...(+{len(obj) - max_str_len})"
        return obj

    return _truncate(params, max_depth)


# ==================== Singleton ====================

_instance: Optional[BrowserEventService] = None
_instance_lock = threading.Lock()


def get_browser_event_service() -> BrowserEventService:
    """Get or create the singleton BrowserEventService."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = BrowserEventService()
    return _instance
