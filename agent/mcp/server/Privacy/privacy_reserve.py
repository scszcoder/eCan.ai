import os
import re
from datetime import datetime
from typing import Any

from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback
from mcp.types import CallToolResult, TextContent

# Import the new privacy filter system
try:
    from agent.ec_skills.browser_use_extension.privacy import (
        RegexMaskFilter,
        PrivacyConfig,
        load_privacy_config,
        FilterResult,
    )
    PRIVACY_FILTER_AVAILABLE = True
except ImportError:
    PRIVACY_FILTER_AVAILABLE = False
    logger.warning("Privacy filter module not available")

# Global filter instance (lazy initialized)
_privacy_filter = None


def get_privacy_filter():
    """Get or create the global privacy filter instance."""
    global _privacy_filter
    if _privacy_filter is None and PRIVACY_FILTER_AVAILABLE:
        config = load_privacy_config()
        _privacy_filter = RegexMaskFilter(config)
    return _privacy_filter


def privacy_filter(dom_tree, options):
    """
    Filter sensitive data from a DOM tree.
    
    Args:
        dom_tree: DOM tree data (can be dict, string, or browser-use object)
        options: Filtering options including:
            - url: Current page URL for per-domain rules
            - patterns: Additional patterns to apply
            - disabled_patterns: Patterns to skip
            
    Returns:
        Filtered DOM tree with sensitive data masked
    """
    filter_instance = get_privacy_filter()
    
    if filter_instance is None:
        logger.warning("Privacy filter not available, returning unfiltered")
        return dom_tree
    
    url = options.get("url", "")
    
    # Handle different input types
    if isinstance(dom_tree, str):
        # Simple text filtering
        filtered_text, stats = filter_instance.filter_text(dom_tree, url)
        if stats:
            logger.info(f"[privacy_filter] Redacted {sum(stats.values())} items from text")
        return filtered_text
    
    elif isinstance(dom_tree, dict):
        # Dict-based DOM tree - filter text values recursively
        return _filter_dict_recursive(dom_tree, filter_instance, url)
    
    else:
        # Try browser-use BrowserStateSummary filtering
        try:
            result = filter_instance.filter_browser_state(dom_tree, url)
            return result.filtered_data
        except Exception as e:
            logger.warning(f"[privacy_filter] Could not filter object: {e}")
            return dom_tree


def _filter_dict_recursive(data, filter_instance, url):
    """Recursively filter string values in a dictionary."""
    result = {}
    for key, value in data.items():
        if isinstance(value, str):
            filtered, _ = filter_instance.filter_text(value, url)
            result[key] = filtered
        elif isinstance(value, dict):
            result[key] = _filter_dict_recursive(value, filter_instance, url)
        elif isinstance(value, list):
            result[key] = [
                _filter_dict_recursive(item, filter_instance, url) if isinstance(item, dict)
                else filter_instance.filter_text(item, url)[0] if isinstance(item, str)
                else item
                for item in value
            ]
        else:
            result[key] = value
    return result


async def privacy_reserve(mainwin, args):
    """
    reserve privacy related contents from a dom-tree

    Args:
        driver: Selenium WebDriver instance
        gmail_url: Gmail inbox URL
        recent_hours: Number of hours to look back for emails (default 72)

    Returns:
        dict: {"emails_per_page": int, "titles": [{"from": str, "datetime": str, "title": str}, ...]}
    """
    try:
        dom_tree = {}
        options = {}
        if args["input"]:
            logger.debug(f"[MCP][PRIVACY RESERVE]: {args['input']}")
            dom_tree = args["input"].get("dom_tree", {})
            options = args["input"].get("options", {})

        if not dom_tree:
            msg = "ERROR: no dom_tree provided."
            logger.error(f"[MCP][PRIVACY RESERVE]:{msg}")
            exposable_dom_tree = dom_tree
        else:
            exposable_dom_tree = privacy_filter(dom_tree, options)
            msg = "completed filtering dom-tree."

        result = TextContent(type="text", text=msg)
        result.meta = {"exposable_dom_tree": exposable_dom_tree}
        logger.debug("[MCP][PRIVACY RESERVE]:exposable_dom_tree:", exposable_dom_tree)
        return [result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorPrivacyReserve")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]



def add_privacy_reserve_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="privacy_reserve",
        description="preserve privacy by either removing or anonymizing related contents from a dom-tree.",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["options"],
                    "properties": {
                        "options": {
                            "type": "object",
                            "description": "some options in json format",
                        }
                    },
                }
            }
        },
    )

    tool_schemas.append(tool_schema)
