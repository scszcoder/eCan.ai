from datetime import datetime
import base64
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback
from mcp.types import CallToolResult, TextContent


async def fetch_amazon_messages(mainwin, args):  # type: ignore
    try:
        logger.debug("fetch_amazon_messages started....")
        new_messages = []
        options = args["input"]["options"]
        web_driver = mainwin.getWebDriver()

        msg = f"completed in fetching amazon messages: {len(new_messages)} messages fetched."
        tool_result = TextContent(type="text", text=msg)
        tool_result.meta = {"new_messages": new_messages}
        return [tool_result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorFetchAmazonMessages")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]



async def answer_amazon_messages(mainwin, args):  # type: ignore
    try:
        logger.debug("answer_amazon_messages started....")
        executed = []
        messages_todos = args["input"]["messages_todos"]
        web_driver = mainwin.getWebDriver()

        msg = f"completed in answering amazon messages: {len(executed)} messages answered."
        tool_result = TextContent(type="text", text=msg)
        tool_result.meta = {"executed": executed}
        return [tool_result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorAnswerAmazonMessages")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]


def add_fetch_amazon_messages_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="fetch_amazon_messages",
        description="fetch amazon newly received messages list.",
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


def add_answer_amazon_messages_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="answer_amaozn_messages",
        description="Answer amazon messages with text, attachments, and related actions if any (for example, handle return, cancel, refund/partial refund, send replacement items, etc",
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


def add_amazon_handle_next_message_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="amazon_handle_next_message",
        description="handle next message by clicking on the message, read it, summerarize it, reaspond to it, and return the handling details info in json format including ones that require human intervention.",
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
                            "description": "some options in json format including policies, etc. will use default if these info are missing anyways.",
                        }
                    },
                }
            }
        },
    )

    tool_schemas.append(tool_schema)