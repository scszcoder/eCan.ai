from datetime import datetime
import base64
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback
from mcp.types import CallToolResult, TextContent


async def etsy_add_listings(mainwin, args):  # type: ignore
    try:
        logger.debug("etsy_add_listings started....")
        executed = []
        messages_todos = args["input"]["messages_todos"]
        web_driver = mainwin.getWebDriver()

        msg = f"completed in adding etsy listings: {len(executed)} messages answered."
        tool_result = TextContent(type="text", text=msg)
        tool_result.meta = {"executed": executed}
        return [tool_result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorETSYAddListings")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]



async def etsy_remove_listings(mainwin, args):  # type: ignore
    try:
        logger.debug("etsy_remove_listings started....")
        executed = []
        messages_todos = args["input"]["messages_todos"]
        web_driver = mainwin.getWebDriver()

        msg = f"completed in remove etsy listings: {len(executed)} messages answered."
        tool_result = TextContent(type="text", text=msg)
        tool_result.meta = {"executed": executed}
        return [tool_result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorETSYRemoveListings")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]



async def etsy_update_listings(mainwin, args):  # type: ignore
    try:
        logger.debug("etsy_update_listings started....")
        executed = []
        messages_todos = args["input"]["messages_todos"]
        web_driver = mainwin.getWebDriver()

        msg = f"completed in updating etsy listings: {len(executed)} messages answered."
        tool_result = TextContent(type="text", text=msg)
        tool_result.meta = {"executed": executed}
        return [tool_result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorETSYUpdateListings")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]



async def etsy_get_listings(mainwin, args):  # type: ignore
    try:
        logger.debug("etsy_get_listings started....")
        executed = []
        messages_todos = args["input"]["messages_todos"]
        web_driver = mainwin.getWebDriver()

        msg = f"completed in getting etsy listings: {len(executed)} messages answered."
        tool_result = TextContent(type="text", text=msg)
        tool_result.meta = {"executed": executed}
        return [tool_result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorETSYGetListings")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def etsy_add_listing_templates(mainwin, args):  # type: ignore
    try:
        logger.debug("etsy_add_listing_templates started....")
        executed = []
        messages_todos = args["input"]["messages_todos"]
        web_driver = mainwin.getWebDriver()

        msg = f"completed in add etsy listing templates: {len(executed)} messages answered."
        tool_result = TextContent(type="text", text=msg)
        tool_result.meta = {"executed": executed}
        return [tool_result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorETSYAddListingTemplates")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def etsy_remove_listing_templates(mainwin, args):  # type: ignore
    try:
        logger.debug("etsy_remove_listing_templates started....")
        executed = []
        messages_todos = args["input"]["messages_todos"]
        web_driver = mainwin.getWebDriver()

        msg = f"completed in removing etsy listing templates: {len(executed)} messages answered."
        tool_result = TextContent(type="text", text=msg)
        tool_result.meta = {"executed": executed}
        return [tool_result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorETSYRemoveListingTemplates")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def etsy_update_listing_templates(mainwin, args):  # type: ignore
    try:
        logger.debug("etsy_update_listing_templates started....")
        executed = []
        messages_todos = args["input"]["messages_todos"]
        web_driver = mainwin.getWebDriver()

        msg = f"completed in updating etsy listing templates: {len(executed)} messages answered."
        tool_result = TextContent(type="text", text=msg)
        tool_result.meta = {"executed": executed}
        return [tool_result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorETSYUpdateListingTemplates")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]


def add_etsy_add_listings_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="etsy_add_listings",
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


def add_etsy_remove_listings_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="etsy_remove_listings",
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


def add_etsy_update_listings_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="etsy_update_listings",
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


def add_etsy_add_listing_templates_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="etsy_add_listing_templates",
        description="etsy add listing templates.",
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


def add_etsy_remove_listing_templates_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="etsy_remove_listing_templates",
        description="etsy remove listing templates.",
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


def add_etsy_update_listing_templates_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="etsy_update_listing_templates",
        description="etsy update listing templates.",
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


def add_etsy_get_listings_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="etsy_get_listings",
        description="etsy update listing templates.",
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
