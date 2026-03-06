"""
Browser Event MCP Tools - MCP tools for subscribing to CDP browser events.

Tools:
- subscribe_browser_event: Subscribe to a CDP event and route matches to pend_event nodes
- unsubscribe_browser_event: Remove a subscription by ID or label
- list_browser_event_subscriptions: List all active browser event subscriptions

Browser events fire in real-time and generate "browser_event" messages that are
routed through the agent's event routing system to resume pend_event nodes,
analogous to how timer events work.
"""

import json
import time
from typing import Any, Dict, List, Optional

from mcp.types import TextContent

from agent.agent_service import get_agent_by_id
from utils.logger_helper import logger_helper as logger, get_traceback


# ==================== Helpers ====================

def _resolve_agent(mainwin, agent_id: str = ""):
    """Resolve an agent from mainwin by ID, or return the first available agent."""
    if agent_id:
        agent = get_agent_by_id(agent_id)
        if agent:
            return agent
    if hasattr(mainwin, "agents") and mainwin.agents:
        return mainwin.agents[0]
    return None


def _get_agent_id(agent) -> str:
    """Extract agent ID from agent object."""
    return getattr(getattr(agent, "card", None), "id", "") or ""


def _error(msg: str) -> Dict[str, Any]:
    return {"success": False, "error": msg, "timestamp": int(time.time() * 1000)}


def _ok(msg: str, **extra) -> Dict[str, Any]:
    result = {"success": True, "message": msg, "timestamp": int(time.time() * 1000)}
    result.update(extra)
    return result


async def _get_cdp_client(mainwin):
    """
    Get the CDP client from the current browser session.
    Tries mainwin.getBrowserSession() first, then BrowserManager.
    """
    browser_session = None

    # Try mainwin direct accessor
    if hasattr(mainwin, "getBrowserSession"):
        browser_session = mainwin.getBrowserSession()

    # Try BrowserManager
    if not browser_session:
        browser_manager = getattr(mainwin, "browser_manager", None)
        if browser_manager:
            auto_browser = browser_manager.find_available_browser()
            if auto_browser and auto_browser.browser_session:
                browser_session = auto_browser.browser_session

    if not browser_session:
        return None, "No active browser session found. Start a browser first."

    # Get the CDP client
    cdp_client = getattr(browser_session, "cdp_client", None) or getattr(browser_session, "_cdp_client_root", None)
    if not cdp_client:
        return None, "Browser session has no CDP client. Ensure browser_use is connected."

    return cdp_client, None


# ==================== Tool Implementations ====================

async def subscribe_browser_event(mainwin, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Subscribe to a CDP browser event.

    Args:
        mainwin: Main window instance
        config: {
            agent_id: str (optional),
            domain: str (required, e.g. "Network", "Page", "DOM", "Runtime"),
            event_method: str (required, e.g. "Network.responseReceived"),
            label: str (required, user-friendly name for routing),
            filter_expr: str (optional, e.g. "response.url contains 'price'"),
        }
    """
    try:
        agent_id = config.get("agent_id", "")
        domain = config.get("domain", "").strip()
        event_method = config.get("event_method", "").strip()
        label = config.get("label", "").strip()
        filter_expr = config.get("filter_expr", "").strip()

        if not domain:
            return _error("domain is required (e.g. 'Network', 'Page', 'DOM', 'Runtime')")
        if not event_method:
            return _error("event_method is required (e.g. 'Network.responseReceived')")
        if not label:
            return _error("label is required (user-friendly name for event routing)")

        # Validate event_method format: "Domain.eventName"
        if "." not in event_method:
            return _error(f"event_method must be 'Domain.eventName' format, got: '{event_method}'")

        agent = _resolve_agent(mainwin, agent_id)
        if not agent:
            return _error(f"Agent not found: {agent_id or '(default)'}")
        agent_id = _get_agent_id(agent)

        cdp_client, err = await _get_cdp_client(mainwin)
        if err:
            return _error(err)

        from agent.ec_tasks.browser_event_service import get_browser_event_service
        svc = get_browser_event_service()

        # Check if label already exists — update-or-create (idempotent)
        existing = svc.find_by_label(label, agent_id)
        if existing:
            svc.unsubscribe(existing.sub_id)
            logger.info(f"[BROWSER_EVENT_TOOL] Replacing existing subscription: label='{label}'")

        sub = await svc.subscribe(
            agent_id=agent_id,
            cdp_client=cdp_client,
            domain=domain,
            event_method=event_method,
            label=label,
            filter_expr=filter_expr,
        )

        return _ok(
            f"Subscribed to {event_method} as '{label}'"
            + (f" with filter: {filter_expr}" if filter_expr else ""),
            subscription=sub.to_dict(),
        )

    except Exception as e:
        err = get_traceback(e, "ErrorSubscribeBrowserEvent")
        logger.error(err)
        return _error(err)


async def unsubscribe_browser_event(mainwin, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Unsubscribe from a CDP browser event.

    Args:
        mainwin: Main window instance
        config: {
            sub_id: str (optional),
            label: str (optional),
            agent_id: str (optional),
        }
    """
    try:
        sub_id = config.get("sub_id", "").strip()
        label = config.get("label", "").strip()
        agent_id = config.get("agent_id", "")

        if not sub_id and not label:
            return _error("Either sub_id or label must be provided")

        from agent.ec_tasks.browser_event_service import get_browser_event_service
        svc = get_browser_event_service()

        if sub_id:
            removed = svc.unsubscribe(sub_id)
            if removed:
                return _ok(f"Unsubscribed (sub_id={sub_id})")
            return _error(f"Subscription not found: sub_id={sub_id}")

        # Resolve by label
        if agent_id:
            agent = _resolve_agent(mainwin, agent_id)
            if agent:
                agent_id = _get_agent_id(agent)

        removed = svc.unsubscribe_by_label(label, agent_id)
        if removed:
            return _ok(f"Unsubscribed: label='{label}'")
        return _error(f"Subscription not found: label='{label}'")

    except Exception as e:
        err = get_traceback(e, "ErrorUnsubscribeBrowserEvent")
        logger.error(err)
        return _error(err)


async def list_browser_event_subscriptions(mainwin, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    List all active browser event subscriptions.

    Args:
        mainwin: Main window instance
        config: {
            agent_id: str (optional),
        }
    """
    try:
        agent_id = config.get("agent_id", "")

        if agent_id:
            agent = _resolve_agent(mainwin, agent_id)
            if agent:
                agent_id = _get_agent_id(agent)

        from agent.ec_tasks.browser_event_service import get_browser_event_service
        svc = get_browser_event_service()

        subs = svc.list_subscriptions(agent_id)
        return _ok(
            f"Found {len(subs)} subscription(s)",
            subscriptions=[s.to_dict() for s in subs],
        )

    except Exception as e:
        err = get_traceback(e, "ErrorListBrowserEventSubs")
        logger.error(err)
        return _error(err)


# ==================== Async Wrappers (for MCP server dispatch) ====================

async def async_subscribe_browser_event(mainwin, args: Dict[str, Any]) -> List[TextContent]:
    """Async wrapper for subscribe_browser_event tool."""
    try:
        input_config = args.get("input", args)
        result = await subscribe_browser_event(mainwin, input_config)

        if result.get("success"):
            sub = result.get("subscription", {})
            msg = (
                f"✅ Subscribed to browser event:\n"
                f"  Label: {sub.get('label')}\n"
                f"  Method: {sub.get('event_method')}\n"
                f"  Domain: {sub.get('domain')}\n"
                f"  Filter: {sub.get('filter_expr') or '(none)'}\n"
                f"  Sub ID: {sub.get('sub_id')}\n\n"
                f"Configure a pend_event node with eventType='browser_event' to receive these events."
            )
        else:
            msg = f"Failed to subscribe: {result.get('error', 'Unknown error')}"

        text_result = TextContent(type="text", text=msg)
        text_result.meta = {"browser_event_result": result}
        return [text_result]

    except Exception as e:
        err_trace = get_traceback(e, "ErrorAsyncSubscribeBrowserEvent")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def async_unsubscribe_browser_event(mainwin, args: Dict[str, Any]) -> List[TextContent]:
    """Async wrapper for unsubscribe_browser_event tool."""
    try:
        input_config = args.get("input", args)
        result = await unsubscribe_browser_event(mainwin, input_config)

        if result.get("success"):
            msg = result.get("message", "Unsubscribed successfully")
        else:
            msg = f"Failed to unsubscribe: {result.get('error', 'Unknown error')}"

        text_result = TextContent(type="text", text=msg)
        text_result.meta = {"browser_event_result": result}
        return [text_result]

    except Exception as e:
        err_trace = get_traceback(e, "ErrorAsyncUnsubscribeBrowserEvent")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def async_list_browser_event_subscriptions(mainwin, args: Dict[str, Any]) -> List[TextContent]:
    """Async wrapper for list_browser_event_subscriptions tool."""
    try:
        input_config = args.get("input", args)
        result = await list_browser_event_subscriptions(mainwin, input_config)

        if result.get("success"):
            subs = result.get("subscriptions", [])
            if subs:
                lines = [f"Found {len(subs)} browser event subscription(s):"]
                for s in subs:
                    lines.append(
                        f"  - {s['label']} ({s['event_method']}, "
                        f"filter='{s.get('filter_expr') or 'none'}', "
                        f"fired={s['fire_count']}, sub_id={s['sub_id']})"
                    )
                msg = "\n".join(lines)
            else:
                msg = "No active browser event subscriptions."
        else:
            msg = f"Failed to list subscriptions: {result.get('error', 'Unknown error')}"

        text_result = TextContent(type="text", text=msg)
        text_result.meta = {"browser_event_result": result}
        return [text_result]

    except Exception as e:
        err_trace = get_traceback(e, "ErrorAsyncListBrowserEventSubs")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]
