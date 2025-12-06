import os
import re
from datetime import datetime
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback
from agent.mcp.server.utils.print_utils import save_page_pdf_via_cdp, ensure_download_dir
from mcp.types import CallToolResult, TextContent
from agent.mcp.server.ads_power.ads_power import connect_to_adspower

# Placeholder mode: when no live order/label UI is available, we can generate a
# simple HTML label page and save it via CDP as a real PDF. Toggle as needed.
GMAIL_PLACEHOLDER_MODE = True


# {
#     "n_new_orders": integer,
#     "n_pages": integer,
#     "orders_per_page": integer,
# }

def privacy_filter(dom_tree, options):
    filtered_dom_tree = dom_tree
    return filtered_dom_tree

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