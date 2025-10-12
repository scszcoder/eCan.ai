from datetime import datetime
import base64
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback
from mcp.types import CallToolResult, TextContent




async def fullfill_etsy_orders(mainwin, args):  # type: ignore
    try:
        logger.debug("fullfill_etsy_orders started....")
        new_orders = []
        fullfilled_orders = []
        options = args["input"]["options"]
        web_driver = mainwin.getWebDriver()

        msg = f"completed in fullfilling etsy new orders: {len(new_orders)} new orders came in, {len(fullfilled_orders)} orders processed."
        tool_result = TextContent(type="text", text=msg)
        tool_result.meta = {"new_orders": new_orders, "fullfilled_orders": fullfilled_orders}
        return [tool_result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorFullfillEtsyOrders")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]


def add_fullfill_etsy_orders_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="fullfill_etsy_orders",
        description="fullfill etsy orders by scraping orders list, for unshipped ones, click on buy shipping to obtain the cheapest shipping labels, save them and return the list of labels files fullpath.",
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