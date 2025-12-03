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
EBAY_PLACEHOLDER_MODE = True


# {
#     "n_new_orders": integer,
#     "n_pages": integer,
#     "orders_per_page": integer,
# }

async def gmail_read(mainwin, args):
    try:
        ebay_summary = {}
        if args["input"]:
            logger.debug(f"[MCP][GET EBAY SUMMARY]: {args['input']}")
            store_url = args["input"]["store_url"]
            if not store_url:
                store_url = "https://www.ebay.com/sh/ord/?filter=status:AWAITING_SHIPMENT"
            options = args["input"]["options"]
            web_driver = mainwin.getWebDriver()
            if not web_driver:
                # Use the first site's URL to initialize/connect the driver
                web_driver = connect_to_adspower(mainwin, store_url)
                logger.debug(f"[MCP][GET EBAY SUMMARY]:WebDriver acquired for ebay work: {type(web_driver)}")
                ebay_summary = scrape_ebay_orders_summary(web_driver, store_url)
                msg = "completed getting ebay shop summary"
            else:
                logger.error(f"[MCP][GET EBAY SUMMARY]:WebDriver acquired for ebay work: {type(web_driver)}")
                msg = "Error: web driver not available."
        else:
            msg = "ERROR: no input provided."
            logger.error(f"[MCP][GET EBAY SUMMARY]:{msg}")

        result = TextContent(type="text", text=msg)
        result.meta = {"ebay_summary": ebay_summary}
        logger.debug("[MCP][GET EBAY SUMMARY]:ebay_summary:", ebay_summary)
        return [result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorGetEbaySummary")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def gmail_write_new(mainwin, args):  # type: ignore
    try:
        logger.debug("fullfill_ebay_orders started....", args["input"])
        new_orders = []
        fullfilled_orders = []
        options = args["input"]["options"]
        if options.get("use_ads", False):
            webdriver = connect_to_adspower(mainwin, url)
            if webdriver:
                mainwin.setWebDriver(webdriver)
        else:
            webdriver = mainwin.getWebDriver()

        if webdriver:
            print("fullfill_ebay_orders:", site)
            site_results = selenium_search_component(webdriver, pf, sites[site])
            ebay_new_orders = scrape_ebay_orders(webdriver)
            logger.debug("ebay_new_orders:", ebay_new_orders)

        msg = f"completed in fullfilling ebay new orders: {len(new_orders)} new orders came in, {len(fullfilled_orders)} orders processed."
        tool_result = TextContent(type="text", text=msg)
        tool_result.meta = {"new_orders": new_orders, "fullfilled_orders": fullfilled_orders}
        return [tool_result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorFullfillEbayOrders")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def gmail_delete_mail(mainwin, args):  # type: ignore
    try:
        logger.debug("fullfill_ebay_orders started....", args["input"])
        new_orders = []
        fullfilled_orders = []
        options = args["input"]["options"]
        if options.get("use_ads", False):
            webdriver = connect_to_adspower(mainwin, url)
            if webdriver:
                mainwin.setWebDriver(webdriver)
        else:
            webdriver = mainwin.getWebDriver()

        if webdriver:
            print("fullfill_ebay_orders:", site)
            site_results = selenium_search_component(webdriver, pf, sites[site])
            ebay_new_orders = scrape_ebay_orders(webdriver)
            logger.debug("ebay_new_orders:", ebay_new_orders)

        msg = f"completed in fullfilling ebay new orders: {len(new_orders)} new orders came in, {len(fullfilled_orders)} orders processed."
        tool_result = TextContent(type="text", text=msg)
        tool_result.meta = {"new_orders": new_orders, "fullfilled_orders": fullfilled_orders}
        return [tool_result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorFullfillEbayOrders")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]



async def gmail_respond(mainwin, args):  # type: ignore
    try:
        logger.debug("fullfill_ebay_orders started....", args["input"])
        new_orders = []
        fullfilled_orders = []
        options = args["input"]["options"]
        if options.get("use_ads", False):
            webdriver = connect_to_adspower(mainwin, url)
            if webdriver:
                mainwin.setWebDriver(webdriver)
        else:
            webdriver = mainwin.getWebDriver()

        if webdriver:
            print("fullfill_ebay_orders:", site)
            site_results = selenium_search_component(webdriver, pf, sites[site])
            ebay_new_orders = scrape_ebay_orders(webdriver)
            logger.debug("ebay_new_orders:", ebay_new_orders)

        msg = f"completed in fullfilling ebay new orders: {len(new_orders)} new orders came in, {len(fullfilled_orders)} orders processed."
        tool_result = TextContent(type="text", text=msg)
        tool_result.meta = {"new_orders": new_orders, "fullfilled_orders": fullfilled_orders}
        return [tool_result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorFullfillEbayOrders")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def gmail_move_email(mainwin, args):  # type: ignore
    try:
        logger.debug("fullfill_ebay_orders started....", args["input"])
        new_orders = []
        fullfilled_orders = []
        options = args["input"]["options"]
        if options.get("use_ads", False):
            webdriver = connect_to_adspower(mainwin, url)
            if webdriver:
                mainwin.setWebDriver(webdriver)
        else:
            webdriver = mainwin.getWebDriver()

        if webdriver:
            print("fullfill_ebay_orders:", site)
            site_results = selenium_search_component(webdriver, pf, sites[site])
            ebay_new_orders = scrape_ebay_orders(webdriver)
            logger.debug("ebay_new_orders:", ebay_new_orders)

        msg = f"completed in fullfilling ebay new orders: {len(new_orders)} new orders came in, {len(fullfilled_orders)} orders processed."
        tool_result = TextContent(type="text", text=msg)
        tool_result.meta = {"new_orders": new_orders, "fullfilled_orders": fullfilled_orders}
        return [tool_result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorFullfillEbayOrders")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]




def add_gmail_delete_email_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="gmail_del_email",
        description="gmail delete emails.",
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


def add_get_gmail_write_new_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="gmail_write_new",
        description="gmail write an new email.",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["store_url", "options"],
                    "properties": {
                        "store_url": {
                            "type": "string",
                            "description": "ebay store url",
                        },
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


def add_gmail_respond_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="gmail_respond",
        description="gmail respond to an email",
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
                            "description": "some options in json format including printer name, label format, etc. will use default if these info are missing anyways.",
                        }
                    },
                }
            }
        },
    )

    tool_schemas.append(tool_schema)


def add_gmail_read_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="gmail_read",
        description="read unread gmails for the past N days.",
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
                            "description": "some options in json format including printer name, label format, etc. will use default if these info are missing anyways.",
                        }
                    },
                }
            }
        },
    )

    tool_schemas.append(tool_schema)


def add_gmail_move_email_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="gmail_move_email",
        description="gmail move email to a different folder.",
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