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

REQUIRED_COMPUTED_STYLES = [
    # example:
    "display",
    "visibility",
    "opacity",
    "background-color",
    # etc...
]


def create_snapshot_request(driver):
    return driver.execute_cdp_cmd(
        "DOMSnapshot.captureSnapshot",
        {
            "computedStyles": REQUIRED_COMPUTED_STYLES,
            "includePaintOrder": True,
            "includeDOMRects": True,
            "includeBlendedBackgroundColors": False,
            "includeTextColorOpacities": False,
        }
    )

async def get_page_dom(mainwin, args):  # type: ignore
    try:
        logger.debug("get_page_dom started....")
        executed = []
        messages_todos = args["input"]["messages_todos"]
        web_driver = mainwin.getWebDriver()

        dom_tree = web_driver.execute_cdp_cmd(
            "DOM.getDocument",
            {"depth": -1, "pierce": True}
        )

        snapshot = create_snapshot_request(web_driver)

        msg = f"completed in getting page dome."
        tool_result = TextContent(type="text", text=msg)
        tool_result.meta = {"dom_tree": dom_tree, "snapshot": snapshot}
        return [tool_result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorAnswerEbayMessages")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]


def add_get_page_dom_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="get_page_dom",
        description="get a page's dom tree data structure.",
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