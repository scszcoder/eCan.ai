from datetime import datetime
import base64
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback
from mcp.types import CallToolResult, TextContent


async def amazon_add_listings(mainwin, args):  # type: ignore
    try:
        logger.debug("amazon_add_listings started....")
        executed = []
        messages_todos = args["input"]["messages_todos"]
        web_driver = mainwin.getWebDriver()

        msg = f"completed in adding amazon listings: {len(executed)} messages answered."
        tool_result = TextContent(type="text", text=msg)
        tool_result.meta = {"executed": executed}
        return [tool_result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorAMAZONAddListings")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def amazon_remove_listings(mainwin, args):  # type: ignore
    try:
        logger.debug("amazon_remove_listings started....")
        executed = []
        messages_todos = args["input"]["messages_todos"]
        web_driver = mainwin.getWebDriver()

        msg = f"completed in remove amazon listings: {len(executed)} messages answered."
        tool_result = TextContent(type="text", text=msg)
        tool_result.meta = {"executed": executed}
        return [tool_result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorAMAZONRemoveListings")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def amazon_update_listings(mainwin, args):  # type: ignore
    try:
        logger.debug("amazon_update_listings started....")
        executed = []
        messages_todos = args["input"]["messages_todos"]
        web_driver = mainwin.getWebDriver()

        msg = f"completed in updating amazon listings: {len(executed)} messages answered."
        tool_result = TextContent(type="text", text=msg)
        tool_result.meta = {"executed": executed}
        return [tool_result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorAMAZONUpdateListings")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def amazon_get_listings(mainwin, args):  # type: ignore
    try:
        logger.debug("amazon_get_listings started....")
        executed = []
        messages_todos = args["input"]["messages_todos"]
        web_driver = mainwin.getWebDriver()

        msg = f"completed in getting amazon listings: {len(executed)} messages answered."
        tool_result = TextContent(type="text", text=msg)
        tool_result.meta = {"executed": executed}
        return [tool_result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorAMAZONGetListings")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def amazon_add_listing_templates(mainwin, args):  # type: ignore
    try:
        logger.debug("amazon_add_listing_templates started....")
        executed = []
        messages_todos = args["input"]["messages_todos"]
        web_driver = mainwin.getWebDriver()

        msg = f"completed in add amazon listing templates: {len(executed)} messages answered."
        tool_result = TextContent(type="text", text=msg)
        tool_result.meta = {"executed": executed}
        return [tool_result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorAMAZONAddListingTemplates")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def amazon_remove_listing_templates(mainwin, args):  # type: ignore
    try:
        logger.debug("amazon_remove_listing_templates started....")
        executed = []
        messages_todos = args["input"]["messages_todos"]
        web_driver = mainwin.getWebDriver()

        msg = f"completed in removing amazon listing templates: {len(executed)} messages answered."
        tool_result = TextContent(type="text", text=msg)
        tool_result.meta = {"executed": executed}
        return [tool_result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorAMAZONRemoveListingTemplates")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def amazon_update_listing_templates(mainwin, args):  # type: ignore
    try:
        logger.debug("amazon_update_listing_templates started....")
        executed = []
        messages_todos = args["input"]["messages_todos"]
        web_driver = mainwin.getWebDriver()

        msg = f"completed in updating amazon listing templates: {len(executed)} messages answered."
        tool_result = TextContent(type="text", text=msg)
        tool_result.meta = {"executed": executed}
        return [tool_result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorAMAZONUpdateListingTemplates")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]


def add_amazon_add_listings_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="amazon_add_listings",
        description="create after work summary for easy viewing by both human and agent.",
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
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


def add_amazon_remove_listings_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="amazon_remove_listings",
        description="create after work summary for easy viewing by both human and agent.",
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
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


def add_amazon_update_listings_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="amazon_update_listings",
        description="create after work summary for easy viewing by both human and agent.",
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
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


def add_amazon_add_listing_templates_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="amazon_add_listing_templates",
        description="amazon add listing templates.",
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
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


def add_amazon_remove_listing_templates_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="amazon_remove_listing_templates",
        description="amazon remove listing templates.",
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
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


def add_amazon_update_listing_templates_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="amazon_update_listing_templates",
        description="amazon update listing templates.",
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
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


def add_amazon_get_listings_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="amazon_get_listings",
        description="amazon update listing templates.",
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
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
