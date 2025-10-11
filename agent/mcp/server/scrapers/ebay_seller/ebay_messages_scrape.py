from datetime import datetime
import base64
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback
from mcp.types import CallToolResult, TextContent


async def fetch_ebay_messages(mainwin, args):  # type: ignore
    try:
        logger.debug("fetch_ebay_messages started....")
        new_messages = []
        options = args["input"]["options"]
        web_driver = mainwin.getWebDriver()

        msg = f"completed in fetching ebay messages: {len(new_messages)} messages fetched."
        tool_result = TextContent(type="text", text=msg)
        tool_result.meta = {"new_messages": new_messages}
        return [tool_result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorFetchEbayMessages")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]



async def answer_ebay_messages(mainwin, args):  # type: ignore
    try:
        logger.debug("answer_ebay_messages started....")
        executed = []
        messages_todos = args["input"]["messages_todos"]
        web_driver = mainwin.getWebDriver()

        msg = f"completed in answering ebay messages: {len(executed)} messages answered."
        tool_result = TextContent(type="text", text=msg)
        tool_result.meta = {"executed": executed}
        return [tool_result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorAnswerEbayMessages")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]