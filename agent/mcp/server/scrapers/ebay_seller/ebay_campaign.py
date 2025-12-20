from datetime import datetime
import base64
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback
from mcp.types import CallToolResult, TextContent
from agent.mcp.server.ads_power.ads_power import connect_to_adspower

async def ebay_adjust_campaigns(mainwin, args):  # type: ignore
    try:
        logger.debug("ebay_adjust_campaigns started....")
        executed = []
        messages_todos = args["input"]["messages_todos"]
        web_driver = mainwin.getWebDriver()

        msg = f"completed in adjusting ebay campaign settings: {len(executed)} messages answered."
        tool_result = TextContent(type="text", text=msg)
        tool_result.meta = {"executed": executed}
        return [tool_result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorEBAYAdjustCampaigns")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]

async def ebay_collect_campaigns_stats(mainwin, args):  # type: ignore
    try:
        logger.debug("ebay_collect_campaigns_stats started....")
        executed = []
        messages_todos = args["input"]["messages_todos"]
        web_driver = mainwin.getWebDriver()

        msg = f"completed in collecting ebay campaign stats: {len(executed)} messages answered."
        tool_result = TextContent(type="text", text=msg)
        tool_result.meta = {"executed": executed}
        return [tool_result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorEBAYCollectCampaignsStats")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]

def add_ebay_adjust_campaigns_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="ebay_adjust_campaigns",
        description="create after work summary for easy viewing by both human and agent.",
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


def add_ebay_collect_campaigns_stats_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="ebay_collect_campaigns_stats",
        description="create after work summary for easy viewing by both human and agent.",
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

