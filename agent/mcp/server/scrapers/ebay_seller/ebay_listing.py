from datetime import datetime
import base64
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback
from mcp.types import CallToolResult, TextContent


def ebay_add_listings(mainwin, args):  # type: ignore
    try:
        logger.debug("ebay_add_listings started....")
        executed = []
        messages_todos = args["input"]["messages_todos"]
        web_driver = mainwin.getWebDriver()

        msg = f"completed in adding ebay listings: {len(executed)} messages answered."
        tool_result = TextContent(type="text", text=msg)
        tool_result.meta = {"executed": executed}
        return [tool_result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorEBAYAddListings")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]




def ebay_remove_listings(mainwin, args):  # type: ignore
    try:
        logger.debug("ebay_remove_listings started....")
        executed = []
        messages_todos = args["input"]["messages_todos"]
        web_driver = mainwin.getWebDriver()

        msg = f"completed in remove ebay listings: {len(executed)} messages answered."
        tool_result = TextContent(type="text", text=msg)
        tool_result.meta = {"executed": executed}
        return [tool_result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorEBAYRemoveListings")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]


def ebay_update_listings(mainwin, args):  # type: ignore
    try:
        logger.debug("answer_ebay_messages started....")
        executed = []
        messages_todos = args["input"]["messages_todos"]
        web_driver = mainwin.getWebDriver()

        msg = f"completed in updating ebay listings: {len(executed)} messages answered."
        tool_result = TextContent(type="text", text=msg)
        tool_result.meta = {"executed": executed}
        return [tool_result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorEBAYUpdateListings")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]



def ebay_get_listings(mainwin, args):  # type: ignore
    try:
        logger.debug("answer_ebay_messages started....")
        executed = []
        messages_todos = args["input"]["messages_todos"]
        web_driver = mainwin.getWebDriver()

        msg = f"completed in getting ebay listings: {len(executed)} messages answered."
        tool_result = TextContent(type="text", text=msg)
        tool_result.meta = {"executed": executed}
        return [tool_result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorEBAYGetListings")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]


def ebay_add_listing_templates(mainwin, args):  # type: ignore
    try:
        logger.debug("ebay_add_listing_templates started....")
        executed = []
        messages_todos = args["input"]["messages_todos"]
        web_driver = mainwin.getWebDriver()

        msg = f"completed in add ebay listing templates: {len(executed)} messages answered."
        tool_result = TextContent(type="text", text=msg)
        tool_result.meta = {"executed": executed}
        return [tool_result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorEBAYAddListingTemplates")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]


def ebay_remove_listing_templates(mainwin, args):  # type: ignore
    try:
        logger.debug("ebay_remove_listing_templates started....")
        executed = []
        messages_todos = args["input"]["messages_todos"]
        web_driver = mainwin.getWebDriver()

        msg = f"completed in removing ebay listing templates: {len(executed)} messages answered."
        tool_result = TextContent(type="text", text=msg)
        tool_result.meta = {"executed": executed}
        return [tool_result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorEBAYRemoveListingTemplates")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]


def ebay_update_listing_templates(mainwin, args):  # type: ignore
    try:
        logger.debug("ebay_update_listing_templates started....")
        executed = []
        messages_todos = args["input"]["messages_todos"]
        web_driver = mainwin.getWebDriver()

        msg = f"completed in updating ebay listing templates: {len(executed)} messages answered."
        tool_result = TextContent(type="text", text=msg)
        tool_result.meta = {"executed": executed}
        return [tool_result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorEBAYUpdateListingTemplates")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]


def add_ebay_add_listings_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="ebay_add_listings",
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



def add_ebay_remove_listings_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="ebay_remove_listings",
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


def add_ebay_update_listings_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="ebay_update_listings",
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


def add_ebay_add_listing_templates_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="ebay_add_listing_templates",
        description="ebay add listing templates.",
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


def add_ebay_remove_listing_templates_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="ebay_remove_listing_templates",
        description="ebay remove listing templates.",
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


def add_ebay_update_listing_templates_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="ebay_update_listing_templates",
        description="ebay update listing templates.",
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




def add_ebay_get_listings_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="ebay_get_listings",
        description="ebay update listing templates.",
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