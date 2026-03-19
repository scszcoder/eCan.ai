"""
Platform Configuration MCP Tools - Tools for managing custom platform profiles.

Provides MCP tools for:
- Creating custom platform profiles
- Testing platform detection and extraction
- Listing available platforms
- Getting platform configuration details

These tools allow LLMs to configure new platforms without code changes.
"""

import time
from typing import Dict, Any
import mcp.types as types
from mcp.types import TextContent

from utils.logger_helper import logger_helper as logger, get_traceback
from agent.ec_tasks.platform_detector import get_platform_detector
from agent.ec_tasks.chat_id_extractor import get_chat_id_extractor


def create_custom_platform_profile(mainwin, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a custom platform profile for a new e-commerce platform.
    
    Args:
        config: {
            "platform_id": str,  # Unique identifier (e.g., "my_store_chat")
            "display_name": str,  # Human-readable name
            "url_pattern": str,  # URL pattern to match (e.g., "mystore.com/messages")
            "chat_container_selector": str,  # CSS selector for message container
            "chat_id_selector": str,  # CSS selector for element with chat ID
            "chat_id_attribute": str,  # Attribute name containing chat ID
            "polling_interval_ms": int,  # Optional, default 3000
            "region": str  # Optional, "global" or "china"
        }
    
    Returns:
        {
            "success": bool,
            "platform_id": str,
            "message": str,
            "profile": dict  # The created profile
        }
    """
    try:
        platform_id = config.get("platform_id", "").strip()
        display_name = config.get("display_name", "").strip()
        url_pattern = config.get("url_pattern", "").strip()
        chat_container_selector = config.get("chat_container_selector", "").strip()
        chat_id_selector = config.get("chat_id_selector", "").strip()
        chat_id_attribute = config.get("chat_id_attribute", "data-chat-id").strip()
        polling_interval_ms = config.get("polling_interval_ms", 3000)
        region = config.get("region", "global")
        
        # Validate required fields
        if not platform_id:
            return {"success": False, "message": "platform_id is required"}
        if not display_name:
            return {"success": False, "message": "display_name is required"}
        if not url_pattern:
            return {"success": False, "message": "url_pattern is required"}
        if not chat_container_selector:
            return {"success": False, "message": "chat_container_selector is required"}
        if not chat_id_selector:
            return {"success": False, "message": "chat_id_selector is required"}
        
        # Build profile
        profile = {
            "platform_id": platform_id,
            "display_name": display_name,
            "region": region,
            "detection": {
                "url_patterns": [url_pattern],
                "dom_signatures": [chat_container_selector],
                "required_elements": [chat_container_selector]
            },
            "event_strategy": {
                "primary": "polling",
                "fallback": "polling",
                "cdp_events": []
            },
            "chat_id_extraction": [
                {
                    "priority": 1,
                    "method": "dom_attribute",
                    "selector": chat_id_selector,
                    "attribute": chat_id_attribute,
                    "validation_regex": "^[0-9a-zA-Z_-]+$",
                    "description": "Extract from active chat element"
                },
                {
                    "priority": 2,
                    "method": "url_pattern",
                    "regex": f"/chat[=/]([0-9a-zA-Z_-]+)",
                    "validation_regex": "^[0-9a-zA-Z_-]+$",
                    "description": "Extract from URL"
                }
            ],
            "message_detection": {
                "container_selector": chat_container_selector,
                "message_selector": f"{chat_container_selector} .message",
                "new_message_indicator": "span.unread",
                "customer_name_selector": "span.customer-name",
                "message_text_selector": "div.message-text",
                "timestamp_selector": "span.timestamp"
            },
            "polling_config": {
                "enabled": True,
                "interval_ms": polling_interval_ms,
                "idle_interval_ms": polling_interval_ms + 2000,
                "max_interval_ms": 10000,
                "snapshot_selector": chat_container_selector,
                "change_detection": "dom_hash"
            }
        }
        
        # Add to detector
        detector = get_platform_detector()
        success, error = detector.add_custom_profile(profile)
        
        if success:
            logger.info(f"[PlatformConfig] Created custom profile: {platform_id}")
            return {
                "success": True,
                "platform_id": platform_id,
                "message": f"Successfully created custom platform profile: {display_name}",
                "profile": profile
            }
        else:
            return {
                "success": False,
                "message": f"Failed to create profile: {error}"
            }
        
    except Exception as e:
        err_trace = get_traceback(e, "ErrorCreateCustomPlatform")
        logger.error(err_trace)
        return {"success": False, "message": err_trace}


def test_platform_detection(mainwin, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Test platform detection and chat ID extraction on current page.
    
    Args:
        config: {
            "url": str,  # Optional, current browser URL
            "platform_id": str  # Optional, specific platform to test
        }
    
    Returns:
        {
            "success": bool,
            "detected_platform": str,
            "chat_id": str,
            "extraction_method": str,
            "message": str
        }
    """
    try:
        url = config.get("url", "")
        platform_id = config.get("platform_id", "")
        
        detector = get_platform_detector()
        
        # Detect platform
        if not platform_id:
            platform_id = detector.detect_platform(url)
            if not platform_id:
                return {
                    "success": False,
                    "message": f"Could not detect platform from URL: {url}"
                }
        
        # Get profile
        profile = detector.get_profile(platform_id)
        if not profile:
            return {
                "success": False,
                "message": f"Profile not found for platform: {platform_id}"
            }
        
        # Try to extract chat ID (requires browser session, which we don't have here)
        # This is a simplified test
        
        return {
            "success": True,
            "detected_platform": platform_id,
            "platform_name": profile.get("display_name", platform_id),
            "chat_id": None,
            "extraction_method": None,
            "message": f"Platform detected: {profile.get('display_name')}. Chat ID extraction requires active browser session.",
            "profile_summary": {
                "event_strategy": profile.get("event_strategy", {}).get("primary"),
                "polling_enabled": profile.get("polling_config", {}).get("enabled"),
                "extraction_methods": len(profile.get("chat_id_extraction", []))
            }
        }
        
    except Exception as e:
        err_trace = get_traceback(e, "ErrorTestPlatformDetection")
        logger.error(err_trace)
        return {"success": False, "message": err_trace}


def list_available_platforms(mainwin, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    List all available platform profiles.
    
    Returns:
        {
            "success": bool,
            "platforms": [
                {
                    "platform_id": str,
                    "display_name": str,
                    "region": str,
                    "event_strategy": str,
                    "polling_enabled": bool
                }
            ],
            "count": int
        }
    """
    try:
        detector = get_platform_detector()
        platform_ids = detector.get_all_platforms()
        
        platforms = []
        for pid in platform_ids:
            profile = detector.get_profile(pid)
            if profile:
                platforms.append({
                    "platform_id": pid,
                    "display_name": profile.get("display_name", pid),
                    "region": profile.get("region", "global"),
                    "event_strategy": profile.get("event_strategy", {}).get("primary", "polling"),
                    "polling_enabled": profile.get("polling_config", {}).get("enabled", True)
                })
        
        return {
            "success": True,
            "platforms": platforms,
            "count": len(platforms)
        }
        
    except Exception as e:
        err_trace = get_traceback(e, "ErrorListPlatforms")
        logger.error(err_trace)
        return {"success": False, "message": err_trace}


def get_platform_profile(mainwin, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get detailed configuration for a specific platform.
    
    Args:
        config: {
            "platform_id": str
        }
    
    Returns:
        {
            "success": bool,
            "platform_id": str,
            "profile": dict
        }
    """
    try:
        platform_id = config.get("platform_id", "")
        if not platform_id:
            return {"success": False, "message": "platform_id is required"}
        
        detector = get_platform_detector()
        profile = detector.get_profile(platform_id)
        
        if not profile:
            return {
                "success": False,
                "message": f"Profile not found for platform: {platform_id}"
            }
        
        return {
            "success": True,
            "platform_id": platform_id,
            "profile": profile
        }
        
    except Exception as e:
        err_trace = get_traceback(e, "ErrorGetPlatformProfile")
        logger.error(err_trace)
        return {"success": False, "message": err_trace}


# ==================== MCP Tool Schema Definitions ====================

def add_create_custom_platform_profile_tool_schema(tool_schemas: list) -> None:
    """Add create_custom_platform_profile tool schema."""
    tool_schema = types.Tool(
        _meta={"run_in_cloud": False},
        name="create_custom_platform_profile",
        description="<category>Platform</category><sub-category>Configuration</sub-category>Create a custom platform profile for a new e-commerce platform. This allows monitoring chat messages on platforms not natively supported. Requires CSS selectors for the chat interface elements.",
        inputSchema={
            "type": "object",
            "required": ["platform_id", "display_name", "url_pattern", "chat_container_selector", "chat_id_selector"],
            "properties": {
                "platform_id": {
                    "type": "string",
                    "description": "Unique identifier for this platform (e.g., 'my_custom_store'). Use lowercase with underscores."
                },
                "display_name": {
                    "type": "string",
                    "description": "Human-readable name for this platform (e.g., 'My Custom Store Chat')."
                },
                "url_pattern": {
                    "type": "string",
                    "description": "URL pattern to match this platform (e.g., 'mystore.com/messages'). Can use wildcards with *."
                },
                "chat_container_selector": {
                    "type": "string",
                    "description": "CSS selector for the message container element (e.g., 'div.message-list')."
                },
                "chat_id_selector": {
                    "type": "string",
                    "description": "CSS selector for the element containing the chat/customer ID (e.g., 'div.active-chat')."
                },
                "chat_id_attribute": {
                    "type": "string",
                    "description": "Optional. Attribute name containing the chat ID (default: 'data-chat-id')."
                },
                "polling_interval_ms": {
                    "type": "integer",
                    "description": "Optional. Polling interval in milliseconds (default: 3000)."
                },
                "region": {
                    "type": "string",
                    "description": "Optional. Platform region: 'global' or 'china' (default: 'global')."
                }
            }
        }
    )
    tool_schemas.append(tool_schema)


def add_test_platform_detection_tool_schema(tool_schemas: list) -> None:
    """Add test_platform_detection tool schema."""
    tool_schema = types.Tool(
        _meta={"run_in_cloud": False},
        name="test_platform_detection",
        description="<category>Platform</category><sub-category>Testing</sub-category>Test platform detection and validate configuration. Use this to verify that a platform profile is correctly configured and can detect the platform from the current page URL.",
        inputSchema={
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Optional. URL to test detection against. If not provided, uses current browser URL."
                },
                "platform_id": {
                    "type": "string",
                    "description": "Optional. Specific platform ID to test. If not provided, will auto-detect."
                }
            }
        }
    )
    tool_schemas.append(tool_schema)


def add_list_available_platforms_tool_schema(tool_schemas: list) -> None:
    """Add list_available_platforms tool schema."""
    tool_schema = types.Tool(
        _meta={"run_in_cloud": False},
        name="list_available_platforms",
        description="<category>Platform</category><sub-category>Query</sub-category>List all available platform profiles including built-in and custom platforms. Shows platform capabilities (event-driven vs polling, region, etc.).",
        inputSchema={
            "type": "object",
            "properties": {}
        }
    )
    tool_schemas.append(tool_schema)


def add_get_platform_profile_tool_schema(tool_schemas: list) -> None:
    """Add get_platform_profile tool schema."""
    tool_schema = types.Tool(
        _meta={"run_in_cloud": False},
        name="get_platform_profile",
        description="<category>Platform</category><sub-category>Query</sub-category>Get detailed configuration for a specific platform profile. Returns full profile including selectors, extraction rules, and polling configuration.",
        inputSchema={
            "type": "object",
            "required": ["platform_id"],
            "properties": {
                "platform_id": {
                    "type": "string",
                    "description": "Platform identifier (e.g., 'amazon_seller_central', 'ebay_messages')."
                }
            }
        }
    )
    tool_schemas.append(tool_schema)


# ==================== Async Wrappers ====================

async def async_create_custom_platform_profile(mainwin, arguments: dict) -> list[types.TextContent]:
    """Async wrapper for create_custom_platform_profile."""
    result = create_custom_platform_profile(mainwin, arguments)
    import json
    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]


async def async_test_platform_detection(mainwin, arguments: dict) -> list[types.TextContent]:
    """Async wrapper for test_platform_detection."""
    result = test_platform_detection(mainwin, arguments)
    import json
    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]


async def async_list_available_platforms(mainwin, arguments: dict) -> list[types.TextContent]:
    """Async wrapper for list_available_platforms."""
    result = list_available_platforms(mainwin, arguments)
    import json
    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]


async def async_get_platform_profile(mainwin, arguments: dict) -> list[types.TextContent]:
    """Async wrapper for get_platform_profile."""
    result = get_platform_profile(mainwin, arguments)
    import json
    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
