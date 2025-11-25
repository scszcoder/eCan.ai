from datetime import datetime
import base64
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback
from mcp.types import CallToolResult, TextContent


async def ebay_gen_labels(mainwin, args):  # type: ignore
    try:
        logger.debug("ebay_gen_labels started....")
        new_messages = []
        options = args["input"]["options"]
        web_driver = mainwin.getWebDriver()

        msg = f"completed in purchasing ebay labels: {len(new_messages)} messages fetched."
        tool_result = TextContent(type="text", text=msg)
        tool_result.meta = {"new_messages": new_messages}
        return [tool_result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorEBAYGenLabels")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]



async def ebay_cancel_labels(mainwin, args):  # type: ignore
    try:
        logger.debug("ebay_cancel_labels started....")
        executed = []
        messages_todos = args["input"]["messages_todos"]
        web_driver = mainwin.getWebDriver()

        msg = f"completed in cancelling ebay labels: {len(executed)} messages answered."
        tool_result = TextContent(type="text", text=msg)
        tool_result.meta = {"executed": executed}
        return [tool_result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorEBAYCancelLabels")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]




def add_ebay_cancel_labels_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="ebay_cancel_labels",
        description="ebay cancel already bought shipping labels.",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["messages_todos"],
                    "properties": {
                        "type": "array",
                        "description": "list of json objects with basic attributes of original_label(full path file name), product_name_short, quantity, and customer_name.",
                        "items": {
                            "type": "object",
                            "required": ["message_id", "reply_text", "reply_attachments", "actions"],
                            "properties": {
                                "message_id": {"type": "string"},
                                "reply_text": {"type": "string"},
                                "reply_attachments": {"type": "array"},
                                "actions": {"type": "array"}
                            }
                        }
                    }
                }
            }
        },
    )

    tool_schemas.append(tool_schema)


def add_ebay_gen_labels_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="ebay_gen_labels",
        description="in ebay seller hub, purchase shipping labels.",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["reason"],
                    "properties": {
                        "reason": {
                            "type": "string",
                            "description": "new order/return/resend/other",
                        }
                    },
                }
            }
        },
    )

    tool_schemas.append(tool_schema)