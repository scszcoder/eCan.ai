import contextlib
from collections.abc import AsyncIterator
from typing import Any, Optional, Dict
from starlette.types import Receive, Scope, Send
from starlette.applications import Starlette
from mcp.server.sse import SseServerTransport
from selenium import webdriver
import pyautogui
from pynput.mouse import Controller
import pygetwindow as gw
import time
import asyncio
from typing import Optional, Tuple, TypeVar, cast
import re
import subprocess
from mcp.server.lowlevel import Server
import traceback
from mcp.server.fastmcp.prompts import base
from mcp.types import CallToolResult, TextContent, ContentBlock
from mcp.server.streamable_http import (
    MCP_PROTOCOL_VERSION_HEADER,
    MCP_SESSION_ID_HEADER,
    SESSION_ID_PATTERN,
    EventCallback,
    EventId,
    EventMessage,
    EventStore,
    StreamableHTTPServerTransport,
    StreamId,
)
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from pydantic import AnyUrl

from agent.mcp.server.tool_schemas import *
import json
from dotenv import load_dotenv
import logging
from datetime import datetime
from agent.runner.models import (
    Position,
)
import shutil
from bot.basicSkill import takeScreenShot, carveOutImage, maskOutImage, saveImageToFile
from utils.logger_helper import login
from bot.seleniumSkill import *
from bot.adsAPISkill import startADSWebDriver, queryAdspowerProfile

from agent.ec_skill import *
from app_context import AppContext
from utils.logger_helper import logger_helper as logger
from .event_store import InMemoryEventStore

server_main_win = None
logger = logging.getLogger(__name__)

Context = TypeVar('Context')

mouse = Controller()

load_dotenv()  # load environment variables from .env

# meca_mcp_server = FastMCP("E-Commerce Agents Service")
meca_mcp_server = Server("E-Commerce Agents Service")
meca_sse = SseServerTransport("/messages/")
meca_streamable_http = StreamableHTTPServerTransport("/mcp_messages/")

#MCP resource
# [protocol]://[host]/[path]
# file:///home/user/documents/report.pdf
# postgres://database/customers/schema
# screen://localhost/display1
# @mcp.resource("dir://desktop")

# ========================== resource section =============================================
@meca_mcp_server.read_resource()
def read_resource() -> dict:
    """Provide the database schema as a resource"""
    all_resources = {}
    return all_resources



# ================= tools section ============================================
@meca_mcp_server.list_tools()
async def list_tools() -> list[types.Tool]:
    print("listing tools requested.........")
    all_tools = get_tool_schemas()
    print(f"# of listed mcp tools:{len(all_tools)}, {all_tools[-1]}")
    return all_tools



@meca_mcp_server.call_tool()
async def unified_tool_handler(tool_name, args):
    ctx = AppContext()
    login = ctx.login
    try:
        tool_func = tool_function_mapping[tool_name]
        # very key make sure each tool_func returns: [ContentBlock]
        # ContentBlock = TextContent | ImageContent | AudioContent | ResourceLink | EmbeddedResource
        # [TextContent(type="text", text=f"all completed fine")]

        toolResult = await tool_func(login.main_win, args)

        return toolResult
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorCallTool:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorCallTool: traceback information not available:" + str(e)
        print(ex_stat)
        return CallToolResult(
                    content=[TextContent(type="text", text=str(ex_stat))],
                    isError=True
                )

# async def unified_tool_handler(tool_name, args):
#     ctx = AppContext()
#     login = ctx.login
#     # 获取用户名和密码
#     if tool_name in tool_function_mapping:
#         try:
#             result = await tool_function_mapping[tool_name](login.main_win, args)
#             print("unified_tool_handler after call", type(result), result)
#         except Exception as e:
#             # Get the traceback information
#             traceback_info = traceback.extract_tb(e.__traceback__)
#             # Extract the file name and line number from the last entry in the traceback
#             if traceback_info:
#                 ex_stat = "ErrorCallTool:" + traceback.format_exc() + " " + str(e)
#             else:
#                 ex_stat = "ErrorCallTool: traceback information not available:" + str(e)
#             result  = CallToolResult(content=[TextContent(type="text", text=ex_stat)], isError=True)
#     else:
#         result = CallToolResult(content=[TextContent(type="text", text="ErrorCallTool: tool NOT found!")], isError=False)
#
#     print("unified_tool_handler.......", type(result), result)
#     return result

######################### Prompts Section ##################################

@meca_mcp_server.get_prompt()
def ads_rpa_help_prompt(step_description: str, failure:str) -> list[base.Message]:
    return [
        base.UserMessage(f"I am running a robotic process automation (RPA) script automating ADS Power software and on this step where "),
        base.UserMessage(step_description),
        base.UserMessage(f" I got this failure:"),
        base.UserMessage(failure),
        base.AssistantMessage("help me fix this error using the tools available, it could be a series of actions. Quite often it was due to ADS Power pops up an advertising banner and blocks its real contents, so you can use screen capture to confirm that and use mouse click action to close the banner, once done, please return a dict result with 'reason' which is a string, and 'fixed' which is a boolean flag in it."),
    ]


async def say_hello(mainwin, args):
    msg = f'Hi There!'
    logger.info(msg)
    result = [TextContent(type="text", text=msg)]
    return result

async def os_wait(mainwin, args):
    try:
        msg = f"🕒  Waited for {args['input']['seconds']} seconds"
        logger.info(msg)
        await asyncio.sleep(args['input']["seconds"])
        result = [TextContent(type="text", text=msg)]
        return result
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorOSWait:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorOSWait: traceback information not available:" + str(e)
        msg = ex_stat
        logger.info(msg)
        return [TextContent(type="text", text=ex_stat)]

async def in_browser_wait_for_element(mainwin, args):
    """Waits for the element specified by the CSS selector to become visible within the given timeout."""
    try:
        web_driver = mainwin.getWebDriver()
        wait = WebDriverWait(web_driver, args.timeout)

        args.tool_result = wait.until(EC.element_to_be_clickable((args['input']["element_type"], args['input']["element_name"])))
        msg=f"completed loading element{args['input']['element_name']}."
        result = [TextContent(type="text", text=msg)]
        return result
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorInBrowserWaitForElement:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorInBrowserWaitForElement: traceback information not available:" + str(e)
        msg = ex_stat
        logger.info(msg)
        return [TextContent(type="text", text=ex_stat)]


# Element Interaction Actions
async def in_browser_click_element_by_index(mainwin, args):
    web_driver = mainwin.getWebDriver()
    browser_context = login.main_win.getBrowserContextById(args['input']["context_id"])
    browser = browser_context.browser
    session = await browser.get_session()

    if args['input']['index'] not in await browser.get_selector_map():
        raise Exception(f"Element with index {args['input']['index']} does not exist - retry or use alternative actions")

    element_node = await browser.get_dom_element_by_index(args['input']['index'])
    initial_pages = len(session.pages)

    # if element has file uploader then dont click
    if await browser.is_file_uploader(element_node):
        msg = f"Index {args['input']['index']} - has an element which opens file upload dialog. To upload files please use a specific function to upload files "
        logger.info(msg)
        return CallToolResult(content=[TextContent(type="text", text=msg)], isError=False)

    msg = None

    try:
        download_path = await browser._click_element_node(element_node)
        if download_path:
            msg = f'💾  Downloaded file to {download_path}'
        else:
            msg = f"🖱️  Clicked button with index {args['input']['index']}: {element_node.get_all_text_till_next_clickable_element(max_depth=2)}"

        logger.info(msg)
        logger.debug(f'Element xpath: {element_node.xpath}')
        if len(session.pages) > initial_pages:
            new_tab_msg = 'New tab opened - switching to it'
            msg += f' - {new_tab_msg}'
            logger.info(new_tab_msg)
            await browser.switch_to_tab(-1)
        msg = f"completed loading element by index {args['input']['index']}."
        result = [TextContent(type="text", text=msg)]
        return result
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorInBrowserClickElementByIndex:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorInBrowserClickElementByIndex: traceback information not available:" + str(e)
        msg = ex_stat
        logger.info(msg)
        return [TextContent(type="text", text=ex_stat)]


async def in_browser_click_element_by_selector(mainwin, args):
    try:
        web_driver = mainwin.getWebDriver()
        browser_context = login.main_win.getBrowserContextById(args['input']["context_id"])
        browser = browser_context.browser
        element_node = await browser.get_locate_element_by_css_selector(args['input']["css_selector"])
        if element_node:
            try:
                await element_node.scroll_into_view_if_needed()
                await element_node.click(timeout=1500, force=True)
            except Exception:
                try:
                    # Handle with js evaluate if fails to click using playwright
                    await element_node.evaluate('el => el.click()')
                except Exception as e:
                    logger.warning(f"Element not clickable with css selector '{args['input']['css_selector']}' - {e}")
                    return CallToolResult(error=str(e))
            msg = f"completed loading element by index {args['input']['css_selector']}."
            result = [TextContent(type="text", text=msg)]
            return result
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorInBrowserClickElementBySelector:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorInBrowserClickElementBySelector: traceback information not available:" + str(e)
        msg = ex_stat
        logger.info(msg)
        return [TextContent(type="text", text=ex_stat)]


async def in_browser_click_element_by_xpath(mainwin, args):
    try:
        web_driver = mainwin.getWebDriver()
        browser_context = login.main_win.getBrowserContextById(args['input']["context_id"])
        browser = browser_context.browser
        element_node = await browser.get_locate_element_by_xpath(args['input']["xpath"])
        if element_node:
            try:
                await element_node.scroll_into_view_if_needed()
                await element_node.click(timeout=1500, force=True)
            except Exception:
                try:
                    # Handle with js evaluate if fails to click using playwright
                    await element_node.evaluate('el => el.click()')
                except Exception as e:
                    logger.warning(f"Element not clickable with xpath '{args['input']['xpath']}' - {e}")
                    return CallToolResult(error=str(e))
            msg = f"completed loading element by index {args['input']['xpath']}."
            result = [TextContent(type="text", text=msg)]
            return result
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorInBrowserClickElementByXpath:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorInBrowserClickElementByXpath: traceback information not available:" + str(e)
        msg = ex_stat
        logger.info(msg)
        return [TextContent(type="text", text=ex_stat)]


async def in_browser_click_element_by_text(mainwin, args):
    try:
        web_driver = mainwin.getWebDriver()
        browser_context = login.main_win.getBrowserContextById(args['input']["context_id"])
        browser = browser_context.browser
        element_node = await browser.get_locate_element_by_text(
            text=args.text, nth=args.nth, element_type=args.element_type
        )

        if element_node:
            try:
                await element_node.scroll_into_view_if_needed()
                await element_node.click(timeout=1500, force=True)
            except Exception:
                try:
                    # Handle with js evaluate if fails to click using playwright
                    await element_node.evaluate('el => el.click()')
                except Exception as e:
                    logger.warning(f"Element not clickable with text '{args.text}' - {e}")
                    return CallToolResult(error=str(e))
            msg = f'🖱️  Clicked on element with text "{args.text}"'
            return CallToolResult(content=[TextContent(type="text", text=msg)], isError=False)
        else:
            return CallToolResult(error=f"No element found for text '{args.text}'")
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorInBrowserClickElementByText:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorInBrowserClickElementByText: traceback information not available:" + str(e)
        msg = ex_stat
        logger.info(msg)
        return [TextContent(type="text", text=ex_stat)]


async def in_browser_input_text(mainwin, args):
    try:
        web_driver = mainwin.getWebDriver()
        browser_context = login.main_win.getBrowserContextById(args['input']["context_id"])
        browser = browser_context.browser
        if args.index not in await browser.get_selector_map():
            raise Exception(f'Element index {args.index} does not exist - retry or use alternative actions')

        element_node = await browser.get_dom_element_by_index(args.index)
        await browser._input_text_element_node(element_node, args.text)
        if not has_sensitive_data:
            msg = f'⌨️  Input {args.text} into index {args.index}'
        else:
            msg = f'⌨️  Input sensitive data into index {args.index}'
        logger.info(msg)
        logger.debug(f'Element xpath: {element_node.xpath}')
        msg = f"completed loading element by index {args['input']['index']}."
        result = [TextContent(type="text", text=msg)]
        return result
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorInBrowserInputText:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorInBrowserInputText: traceback information not available:" + str(e)
        msg = ex_stat
        logger.info(msg)
        return [TextContent(type="text", text=ex_stat)]

# Save PDF
async def in_browser_save_pdf(mainwin, args):
    try:
        web_driver = mainwin.getWebDriver()
        page = await browser.get_current_page()
        short_url = re.sub(r'^https?://(?:www\.)?|/$', '', page.url)
        slug = re.sub(r'[^a-zA-Z0-9]+', '-', short_url).strip('-').lower()
        sanitized_filename = f'{slug}.pdf'

        await page.emulate_media('screen')
        await page.pdf(path=sanitized_filename, format='A4', print_background=False)
        msg = f'Saving page with URL {page.url} as PDF to ./{sanitized_filename}'
        logger.info(msg)
        msg = f"completed loading element by index {args['input']['index']}."
        result = [TextContent(type="text", text=msg)]
        return result
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorInBrowserSavePDF:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorInBrowserSavePDF: traceback information not available:" + str(e)
        msg = ex_stat
        logger.info(msg)
        return [TextContent(type="text", text=ex_stat)]

# Tab Management Actions
async def in_browser_switch_tab(mainwin, args):
    try:
        web_driver = mainwin.getWebDriver()
        await browser.switch_to_tab(args.page_id)
        # Wait for tab to be ready
        page = await browser.get_current_page()
        await page.wait_for_load_state()
        msg = f'🔄  Switched to tab {args.page_id}'
        logger.info(msg)
        msg = f"completed loading element by index {args['input']['index']}."
        result = [TextContent(type="text", text=msg)]
        return result
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorInBrowserSwitchTab:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorInBrowserSwitchTab: traceback information not available:" + str(e)
        msg = ex_stat
        logger.info(msg)
        return [TextContent(type="text", text=ex_stat)]

async def in_browser_open_tab(mainwin, args):

    try:
        web_driver = mainwin.getWebDriver()
        url = args["url"]
        webdriver = mainwin.getWebDriver()
        webdriver.switch_to.window(webdriver.window_handles[0])
        time.sleep(3)
        webdriver.execute_script(f"window.open('{url}', '_blank');")

        # Switch to the new tab
        webdriver.switch_to.window(webdriver.window_handles[-1])
        time.sleep(3)
        # Navigate to the new URL in the new tab
        if url:
            webdriver.get(url)  # Replace with the new URL
            print("open URL: " + url)

        msg = f'completed'
        logger.info(msg)
        msg = f"completed loading element by index {args['input']['index']}."
        result = [TextContent(type="text", text=msg)]
        return result
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorInBrowserOpenTab:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorInBrowserOpenTab: traceback information not available:" + str(e)
        msg = ex_stat
        logger.info(msg)
        return [TextContent(type="text", text=ex_stat)]


async def in_browser_close_tab(mainwin, args):
    try:
        web_driver = mainwin.getWebDriver()
        browser_context = mainwin.getBrowserContextById(args['input']["context_id"])
        browser = browser_context.browser
        await browser.switch_to_tab(args.page_id)
        page = await browser.get_current_page()
        url = page.url
        await page.close()
        msg = f'❌  Closed tab #{args.page_id} with url {url}'
        logger.info(msg)
        msg = f"completed loading element by index {args['input']['index']}."
        result = [TextContent(type="text", text=msg)]
        return result
    except Exception as e:
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorInBrowserCloseTab:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorInBrowserCloseTab: traceback information not available:" + str(e)
        print("ex_stat:", ex_stat)
        err_text_content = [TextContent(type="text", text=f"Error in scheduler: {ex_stat}")]
        return [TextContent(type="text", text=ex_stat)]

# Content Actions
async def in_browser_scrape_content(mainwin, args):
    try:
        web_driver = mainwin.getWebDriver()
        web_driver = mainwin.web_driver
        dom_service = mainwin.dom_service
        dom_service.get_clickable_elements()

        msg = f"completed loading element by index {args['input']['index']}."
        result = [TextContent(type="text", text=msg)]
        return result
    except Exception as e:
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorCallToolScrapeContents:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorCallToolScrapeContents: traceback information not available:" + str(e)
        print("ex_stat:", ex_stat)
        err_text_content = [TextContent(type="text", text=f"Error in scheduler: {ex_stat}")]
        return [TextContent(type="text", text=ex_stat)]


async def in_browser_execute_javascript(mainwin, args):
    try:
        web_driver = mainwin.getWebDriver()
        result = execute_js_script(web_driver, args['input']["script"], args['input']["target"])
        msg = f"completed loading element by index {args['input']['index']}."
        tool_result = [TextContent(type="text", text=msg)]
        return tool_result
    except Exception as e:
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorCallToolScrapeContents:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorCallToolScrapeContents: traceback information not available:" + str(e)
        print("ex_stat:", ex_stat)
        err_text_content = [TextContent(type="text", text=f"Error in scheduler: {ex_stat}")]
        return [TextContent(type="text", text=ex_stat)]



async def in_browser_build_dom_tree(mainwin, args):
    try:
        webdriver = mainwin.getWebDriver()
        script = mainwin.load_build_dom_tree_script()
        # print("dom tree build script to be executed", script)
        target = None
        domTree = execute_js_script(webdriver, script, target)
        print(">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
        print("obtained dom tree:", domTree)
        with open("domtree.json", 'w', encoding="utf-8") as f:
            json.dump(domTree, f, ensure_ascii=False, indent=4)
            # self.rebuildHTML()
            f.close()

        domTreeJSString = json.dumps(domTree)            # clear error
        time.sleep(1)

        result_text_content = [TextContent(type="text", text=f"{domTreeJSString}")]
        result = CallToolResult(content=result_text_content, isError=True)
        print("call tool build dome tree result:", result)
        msg = f"completed loading element by index {args['input']['index']}."
        tool_result = [TextContent(type="text", text=msg)]
        return tool_result

    except Exception as e:
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorCallBuildDomTree:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorCallBuildDomTree: traceback information not available:" + str(e)
        print("ex_stat:", ex_stat)
        err_text_content = [TextContent(type="text", text=f"Error in scheduler: {ex_stat}")]
        return [TextContent(type="text", text=ex_stat)]




# HTML Download
async def in_browser_save_html_to_file(mainwin, args) -> CallToolResult:
    """Retrieves and returns the full HTML content of the current page to a file"""
    try:
        web_driver = mainwin.getWebDriver()
        browser_context = login.main_win.getBrowserContextById(args["context_id"])
        browser = browser_context.browser
        page = await browser.get_current_page()
        html_content = await page.content()

        # Create a filename based on the page URL
        short_url = re.sub(r'^https?://(?:www\.)?|/$', '', page.url)
        slug = re.sub(r'[^a-zA-Z0-9]+', '-', short_url).strip('-').lower()[:64]
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        sanitized_filename = f'{slug}_{timestamp}.html'

        # Save HTML to file
        with open(sanitized_filename, 'w', encoding='utf-8') as f:
            f.write(html_content)

        msg = f'Saved HTML content of page with URL {page.url} to ./{sanitized_filename}'

        logger.info(msg)
        msg = f"completed loading element by index {args['input']['index']}."
        tool_result = [TextContent(type="text", text=msg)]
        return tool_result
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extractthe file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorInBrowserSaveHtmlToFile:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorInBrowserSaveHtmlToFile: traceback information not available:" + str(e)
        log3(ex_stat)
        return [TextContent(type="text", text=ex_stat)]


async def in_browser_scroll_down(mainwin, args):
    try:
        web_driver = mainwin.getWebDriver()
        browser_context = login.main_win.getBrowserContextById(args["context_id"])
        browser = browser_context.browser
        page = await browser.get_current_page()
        if args.amount is not None:
            await page.evaluate(f'window.scrollBy(0, {args.amount});')
        else:
            await page.evaluate('window.scrollBy(0, window.innerHeight);')

        amount = f'{args.amount} pixels' if args.amount is not None else 'one page'
        msg = f'🔍  Scrolled down the page by {amount}'
        logger.info(msg)

        msg = f"completed loading element by index {args['input']['index']}."
        tool_result = [TextContent(type="text", text=msg)]
        return tool_result
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extractthe file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorInBrowserScrollUp:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorInBrowserScrollUp: traceback information not available:" + str(e)
        log3(ex_stat)
        return [TextContent(type="text", text=ex_stat)]

# scroll up
async def in_browser_scroll_up(mainwin, args):
    try:
        web_driver = mainwin.getWebDriver()
        browser_context = login.main_win.getBrowserContextById(args["context_id"])
        browser = browser_context.browser
        page = await browser.get_current_page()
        if args.amount is not None:
            await page.evaluate(f'window.scrollBy(0, -{args.amount});')
        else:
            await page.evaluate('window.scrollBy(0, -window.innerHeight);')

        amount = f'{args.amount} pixels' if args.amount is not None else 'one page'
        msg = f'🔍  Scrolled up the page by {amount}'
        logger.info(msg)
        msg = f"completed loading element by index {args['input']['index']}."
        tool_result = [TextContent(type="text", text=msg)]
        return tool_result
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extractthe file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorInBrowserScrollUp:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorInBrowserScrollUp: traceback information not available:" + str(e)
        log3(ex_stat)
        return [TextContent(type="text", text=ex_stat)]

# send keys
async def in_browser_send_keys(mainwin, args):
    try:
        web_driver = mainwin.getWebDriver()
        browser_context = login.main_win.getBrowserContextById(args["context_id"])
        browser = browser_context.browser
        page = await browser.get_current_page()


        await page.keyboard.press(args.keys)

        msg = f'⌨️  Sent keys: {args.keys}'
        logger.info(msg)
        msg = f"completed loading element by index {args['input']['index']}."
        tool_result = [TextContent(type="text", text=msg)]
        return tool_result
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extractthe file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorInBrowserScrollToText:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorInBrowserScrollToText: traceback information not available:" + str(e)
        log3(ex_stat)
        return [TextContent(type="text", text=ex_stat)]

async def in_browser_scroll_to_text(mainwin, args):  # type: ignore
    try:
        web_driver = mainwin.getWebDriver()
        page = await browser.get_current_page()
        # Try different locator strategies
        locators = [
            page.get_by_text(text, exact=False),
            page.locator(f'text={text}'),
            page.locator(f"//*[contains(text(), '{text}')]"),
        ]

        for locator in locators:
            try:
                # First check if element exists and is visible
                if await locator.count() > 0 and await locator.first.is_visible():
                    await locator.first.scroll_into_view_if_needed()
                    await asyncio.sleep(0.5)  # Wait for scroll to complete
                    msg = f'🔍  Scrolled to text: {text}'
                    logger.info(msg)
                    return CallToolResult(content=[TextContent(type="text", text=msg)], isError=False)
            except Exception as e:
                logger.debug(f'Locator attempt failed: {str(e)}')
                continue

        msg = f"Text '{text}' not found or not visible on page"
        logger.info(msg)
        msg = f"completed loading element by index {args['input']['index']}."
        tool_result = [TextContent(type="text", text=msg)]
        return tool_result
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extractthe file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorInBrowserScrollToText:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorInBrowserScrollToText: traceback information not available:" + str(e)
        log3(ex_stat)
        return [TextContent(type="text", text=ex_stat)]


async def in_browser_get_dropdown_options(mainwin, args) -> CallToolResult:
    try:
        index = args["index"]
        web_driver = mainwin.getWebDriver()
        """Get all options from a native dropdown"""
        browser_context = login.main_win.getBrowserContextById(args["context_id"])
        browser = browser_context.browser
        page = await browser.get_current_page()
        selector_map = await browser.get_selector_map()
        dom_element = selector_map[index]

        # Frame-aware approach since we know it works
        all_options = []
        frame_index = 0

        for frame in page.frames:
            try:
                options = await frame.evaluate(
                    """
                    (xpath) => {
                        const select = document.evaluate(xpath, document, null,
                            XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                        if (!select) return null;

                        return {
                            options: Array.from(select.options).map(opt => ({
                                text: opt.text, //do not trim, because we are doing exact match in select_dropdown_option
                                value: opt.value,
                                index: opt.index
                            })),
                            id: select.id,
                            name: select.name
                        };
                    }
                """,
                    dom_element.xpath,
                )

                if options:
                    logger.debug(f'Found dropdown in frame {frame_index}')
                    logger.debug(f'Dropdown ID: {options["id"]}, Name: {options["name"]}')

                    formatted_options = []
                    for opt in options['options']:
                        # encoding ensures AI uses the exact string in select_dropdown_option
                        encoded_text = json.dumps(opt['text'])
                        formatted_options.append(f'{opt["index"]}: text={encoded_text}')

                    all_options.extend(formatted_options)

            except Exception as frame_e:
                logger.debug(f'Frame {frame_index} evaluation failed: {str(frame_e)}')

            frame_index += 1

        if all_options:
            msg = '\n'.join(all_options)
            msg += '\nUse the exact text string in select_dropdown_option'
            logger.info(msg)
            msg = f"completed loading element by index {args['input']['index']}."
            tool_result = [TextContent(type="text", text=msg)]
            return tool_result
        else:
            msg = 'No options found in any frame for dropdown'
            logger.info(msg)
            msg = f"completed loading element by index {args['input']['index']}."
            tool_result = [TextContent(type="text", text=msg)]
            return tool_result


    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extractthe file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorInBrowserGetDropdownOption:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorInBrowserGetDropdownOption: traceback information not available:" + str(e)
        log3(ex_stat)
        return [TextContent(type="text", text=ex_stat)]


async def in_browser_select_dropdown_option(mainwin, args) -> CallToolResult:
    try:
        """Select dropdown option by the text of the option you want to select"""
        web_driver = mainwin.getWebDriver()
        browser_context = mainwin.getBrowserContextById(args["context_id"])
        browser = browser_context.browser
        page = await browser.get_current_page()
        selector_map = await browser.get_selector_map()
        dom_element = selector_map[index]

        # Validate that we're working with a select element
        if dom_element.tag_name != 'select':
            logger.error(f'Element is not a select! Tag: {dom_element.tag_name}, Attributes: {dom_element.attributes}')
            msg = f'Cannot select option: Element with index {index} is a {dom_element.tag_name}, not a select'
            return CallToolResult(content=[TextContent(type="text", text=msg)], isError=False)

        text = ""
        logger.debug(f"Attempting to select '{text}' using xpath: {dom_element.xpath}")
        logger.debug(f'Element attributes: {dom_element.attributes}')
        logger.debug(f'Element tag: {dom_element.tag_name}')

        xpath = '//' + dom_element.xpath

        frame_index = 0
        for frame in page.frames:
            try:
                logger.debug(f'Trying frame {frame_index} URL: {frame.url}')

                # First verify we can find the dropdown in this frame
                find_dropdown_js = """
					(xpath) => {
						try {
							const select = document.evaluate(xpath, document, null,
								XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
							if (!select) return null;
							if (select.tagName.toLowerCase() !== 'select') {
								return {
									error: `Found element but it's a ${select.tagName}, not a SELECT`,
									found: false
								};
							}
							return {
								id: select.id,
								name: select.name,
								found: true,
								tagName: select.tagName,
								optionCount: select.options.length,
								currentValue: select.value,
								availableOptions: Array.from(select.options).map(o => o.text.trim())
							};
						} catch (e) {
							return {error: e.toString(), found: false};
						}
					}
				"""

                dropdown_info = await frame.evaluate(find_dropdown_js, dom_element.xpath)

                if dropdown_info:
                    if not dropdown_info.get('found'):
                        logger.error(f'Frame {frame_index} error: {dropdown_info.get("error")}')
                        continue

                    logger.debug(f'Found dropdown in frame {frame_index}: {dropdown_info}')
                    text = ""
                    # "label" because we are selecting by text
                    # nth(0) to disable error thrown by strict mode
                    # timeout=1000 because we are already waiting for all network events, therefore ideally we don't need to wait a lot here (default 30s)
                    selected_option_values = (
                        await frame.locator('//' + dom_element.xpath).nth(0).select_option(label=text, timeout=1000)
                    )

                    msg = f'selected option {text} with value {selected_option_values}'
                    logger.info(msg + f' in frame {frame_index}')

                    return CallToolResult(content=[TextContent(type="text", text=msg)], isError=False)

            except Exception as frame_e:
                logger.error(f'Frame {frame_index} attempt failed: {str(frame_e)}')
                logger.error(f'Frame type: {type(frame)}')
                logger.error(f'Frame URL: {frame.url}')

            frame_index += 1

        msg = f"Could not select option '{text}' in any frame"
        logger.info(msg)
        msg = f"completed loading element by index {args['input']['index']}."
        tool_result = [TextContent(type="text", text=msg)]
        return tool_result
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorInBrowserSelectDropdownOption:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorInBrowserSelectDropdownOption: traceback information not available:" + str(e)
        log3(ex_stat)
        return [TextContent(type="text", text=ex_stat)]


async def in_browser_drag_drop(mainwin, args) -> CallToolResult:
    """
    Performs a precise drag and drop operation between elements or coordinates.
    """

    async def get_drag_elements(
            web_driver: webdriver,
            source_selector: str,
            target_selector: str,
    ) -> Tuple[Optional[ElementHandle], Optional[ElementHandle]]:
        """Get source and target elements with appropriate error handling."""
        source_element = None
        target_element = None

        try:
            # page.locator() auto-detects CSS and XPath
            source_locator = page.locator(source_selector)
            target_locator = page.locator(target_selector)

            # Check if elements exist
            source_count = await source_locator.count()
            target_count = await target_locator.count()

            if source_count > 0:
                source_element = await source_locator.first.element_handle()
                logger.debug(f'Found source element with selector: {source_selector}')
            else:
                logger.warning(f'Source element not found: {source_selector}')

            if target_count > 0:
                target_element = await target_locator.first.element_handle()
                logger.debug(f'Found target element with selector: {target_selector}')
            else:
                logger.warning(f'Target element not found: {target_selector}')

        except Exception as e:
            logger.error(f'Error finding elements: {str(e)}')

        return source_element, target_element

    async def get_element_coordinates(
            source_element: ElementHandle,
            target_element: ElementHandle,
            source_position: Optional[Position],
            target_position: Optional[Position],
    ) -> Tuple[Optional[Tuple[int, int]], Optional[Tuple[int, int]]]:
        """Get coordinates from elements with appropriate error handling."""
        source_coords = None
        target_coords = None

        try:
            # Get source coordinates
            if source_position:
                source_coords = (source_position.x, source_position.y)
            else:
                source_box = await source_element.bounding_box()
                if source_box:
                    source_coords = (
                        int(source_box['x'] + source_box['width'] / 2),
                        int(source_box['y'] + source_box['height'] / 2),
                    )

            # Get target coordinates
            if target_position:
                target_coords = (target_position.x, target_position.y)
            else:
                target_box = await target_element.bounding_box()
                if target_box:
                    target_coords = (
                        int(target_box['x'] + target_box['width'] / 2),
                        int(target_box['y'] + target_box['height'] / 2),
                    )
        except Exception as e:
            logger.error(f'Error getting element coordinates: {str(e)}')

        return source_coords, target_coords

    async def execute_drag_operation(
            web_driver: webdriver,
            source_x: int,
            source_y: int,
            target_x: int,
            target_y: int,
            steps: int,
            delay_ms: int,
    ) -> Tuple[bool, str]:
        """Execute the drag operation with comprehensive error handling."""
        try:
            # Try to move to source position
            try:
                await page.mouse.move(source_x, source_y)
                logger.debug(f'Moved to source position ({source_x}, {source_y})')
            except Exception as e:
                logger.error(f'Failed to move to source position: {str(e)}')
                return False, f'Failed to move to source position: {str(e)}'

            # Press mouse button down
            await page.mouse.down()

            # Move to target position with intermediate steps
            for i in range(1, steps + 1):
                ratio = i / steps
                intermediate_x = int(source_x + (target_x - source_x) * ratio)
                intermediate_y = int(source_y + (target_y - source_y) * ratio)

                await page.mouse.move(intermediate_x, intermediate_y)

                if delay_ms > 0:
                    await asyncio.sleep(delay_ms / 1000)

            # Move to final target position
            await page.mouse.move(target_x, target_y)

            # Move again to ensure dragover events are properly triggered
            await page.mouse.move(target_x, target_y)

            # Release mouse button
            await page.mouse.up()

            return True, 'Drag operation completed successfully'

        except Exception as e:
            return False, f'Error during drag operation: {str(e)}'

    browser_context = login.main_win.getBrowserContextById(context_id)
    browser = browser_context.browser
    page = await browser.get_current_page()

    try:
        web_driver = mainwin.getWebDriver()
        # Initialize variables
        source_x: Optional[int] = None
        source_y: Optional[int] = None
        target_x: Optional[int] = None
        target_y: Optional[int] = None

        # Normalize parameters
        steps = max(1, args.steps or 10)
        delay_ms = max(0, args.delay_ms or 5)

        # Case 1: Element selectors provided
        if args.element_source and args.element_target:
            logger.debug('Using element-based approach with selectors')

            source_element, target_element = await get_drag_elements(
                page,
                args.element_source,
                args.element_target,
            )

            if not source_element or not target_element:
                error_msg = f'Failed to find {"source" if not source_element else "target"} element'
                return CallToolResult(content = [TextContent(type="text", text=error_msg)], isError=False)

            source_coords, target_coords = await get_element_coordinates(
                source_element, target_element, args.element_source_offset, args.element_target_offset
            )

            if not source_coords or not target_coords:
                error_msg = f'Failed to determine {"source" if not source_coords else "target"} coordinates'
                return CallToolResult(content = [TextContent(type="text", text=error_msg)], isError=False)

            source_x, source_y = source_coords
            target_x, target_y = target_coords

        # Case 2: Coordinates provided directly
        elif all(
                coord is not None
                for coord in
                [args.coord_source_x, args.coord_source_y, args.coord_target_x, args.coord_target_y]
        ):
            logger.debug('Using coordinate-based approach')
            source_x = args.coord_source_x
            source_y = args.coord_source_y
            target_x = args.coord_target_x
            target_y = args.coord_target_y
        else:
            error_msg = 'Must provide either source/target selectors or source/target coordinates'

            return CallToolResult(content=[TextContent(type="text", text=error_msg)], isError=False)

        # Validate coordinates
        if any(coord is None for coord in [source_x, source_y, target_x, target_y]):
            error_msg = 'Failed to determine source or target coordinates'
            return CallToolResult(content=[TextContent(type="text", text=error_msg)], isError=False)

        # Perform the drag operation
        success, message = await execute_drag_operation(
            page,
            cast(int, source_x),
            cast(int, source_y),
            cast(int, target_x),
            cast(int, target_y),
            steps,
            delay_ms,
        )

        if not success:
            logger.error(f'Drag operation failed: {message}')
            return CallToolResult(content=[TextContent(type="text", text=message)], isError=True)

        # Create descriptive message
        if args.element_source and args.element_target:
            msg = f"🖱️ Dragged element '{args.element_source}' to '{args.element_target}'"
        else:
            msg = f'🖱️ Dragged from ({source_x}, {source_y}) to ({target_x}, {target_y})'

        logger.info(msg)
        return CallToolResult(content=[TextContent(type="text", text=msg)], isError=False)


    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorHTTPCallAPI:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorHTTPCallAPI: traceback information not available:" + str(e)
        log3(ex_stat)
        return [TextContent(type="text", text=ex_stat)]


async def mouse_click(mainwin, args):
    try:
        print("INPUT:", args)
        # if tool_name != "rpa_supervisor_scheduling_work":
        #     raise ValueError(f"Unexpected tool name: {tool_name}")

        web_driver = mainwin.getWebDriver()
        # mainwin = params["agent"].mainwin
        print(f"[MCP] Running supervisor scheduler tool... ")
        print(f"[MCP] Running supervisor scheduler tool... Bots: {len(server_main_win.bots)}")
        schedule = server_main_win.fetchSchedule("", server_main_win.get_vehicle_settings())
        print("MCP fetched schedule.......", schedule)
        # workable = server_main_win.runTeamPrepHook(schedule)
        # works_to_be_dispatched = server_main_win.handleCloudScheduledWorks(workable)
        pyautogui.moveTo(args.loc.x, args.loc.y)
        # ctr = CallToolResult(content=[TextContent(type="text", text=msg)], _meta=workable, isError=False)
        ctr = CallToolResult(content=[TextContent(type="text", text=msg)])
        print("ABOUT TO return call tool result", type(ctr), ctr)
        print("ABOUT CTR Type", ctr.model_dump(by_alias=True, exclude_none=True, mode="json"))
        tool_result = {
            "content": [{"type": "text", "text": msg}],
            # "meta": workable,
            "isError": False
        }
        print("[DEBUG] Returning result:", json.dumps(tool_result, indent=2))
        # return ctr.model_dump(by_alias=True, exclude_none=True, mode="json", round_trip=False)
        return [TextContent(type="text", text=msg), TextContent(type="text", text=json.dumps(workable))]
    except Exception as e:
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorCallToolMouseClick:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorCallToolMouseClick: traceback information not available:" + str(e)
        print("ex_stat:", ex_stat)
        err_text_content = [TextContent(type="text", text=f"Error in mouse click: {ex_stat}")]
        return CallToolResult(content=err_text_content, isError=True)


async def mouse_move(mainwin, args):
    try:
        browser_context = mainwin.getBrowserContextById(args["context_id"])
        browser = browser_context.browser
        if params.index not in await browser.get_selector_map():
            raise Exception(f'Element index {args.index} does not exist - retry or use alternative actions')

        pyautogui.moveTo(args.loc.x, args.loc.y)

        logger.debug(f'Element xpath: {args.loc.x},  {args.loc.y}')
        msg = ""
        return CallToolResult(content=[TextContent(type="text", text=msg)], isError=False)
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorHTTPCallAPI:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorHTTPCallAPI: traceback information not available:" + str(e)
        log3(ex_stat)
        return [TextContent(type="text", text=ex_stat)]

async def mouse_drag_drop(mainwin, args):
    try:
        browser_context = mainwin.getBrowserContextById(args["context_id"])
        browser = browser_context.browser
        if args.index not in await browser.get_selector_map():
            raise Exception(f'Element index {args.index} does not exist - retry or use alternative actions')

        pyautogui.moveTo(args.pick_loc.x, args.pick_loc.y)
        pyautogui.dragTo(args.drop_loc.x, args.drop_loc.y, duration=args.duration)

        logger.debug(f'dragNdrop: {args.pick_loc.x}, {args.pick_loc.y} to {args.drop_loc.x}, {args.drop_loc.y}')
        msg = ""
        return CallToolResult(content=[TextContent(type="text", text=msg)], isError=False)
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorHTTPCallAPI:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorHTTPCallAPI: traceback information not available:" + str(e)
        log3(ex_stat)
        return [TextContent(type="text", text=ex_stat)]

async def mouse_scroll(mainwin, args):
    try:
        browser_context = mainwin.getBrowserContextById(args["context_id"])
        browser = browser_context.browser
        if args.index not in await browser.get_selector_map():
            raise Exception(f'Element index {args.index} does not exist - retry or use alternative actions')

        if args.direction == "down":
            scroll_amount = 0 - args.amount
        else:
            scroll_amount = args.amount
        mouse.scroll(0, scroll_amount)

        logger.debug(f'Element xpath: {scroll_amount}')
        msg = ""
        return CallToolResult(content=[TextContent(type="text", text=msg)], isError=False)
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorHTTPCallAPI:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorHTTPCallAPI: traceback information not available:" + str(e)
        log3(ex_stat)
        return [TextContent(type="text", text=ex_stat)]

async def keyboard_text_input(mainwin, args):
    try:
        browser_context = mainwin.getBrowserContextById(args["context_id"])
        browser = browser_context.browser
        if args.index not in await browser.get_selector_map():
            raise Exception(f'Element index {args.index} does not exist - retry or use alternative actions')

        pyautogui.write(args.text, interval=args.interval)

        logger.debug(f'Element xpath: {args.text},  {args.interval}')
        msg = ""
        return CallToolResult(content=[TextContent(type="text", text=msg)], isError=False)
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorHTTPCallAPI:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorHTTPCallAPI: traceback information not available:" + str(e)
        log3(ex_stat)
        return [TextContent(type="text", text=ex_stat)]

async def keyboard_keys_input(mainwin, args):
    try:
        browser_context = mainwin.getBrowserContextById(args["context_id"])
        browser = browser_context.browser
        if args.index not in await browser.get_selector_map():
            raise Exception(f'Element index {args.index} does not exist - retry or use alternative actions')

        pyautogui.hotkey(*args.combo)

        logger.debug(f'hot keys: {args.combo[0]}')
        msg = ""
        return CallToolResult(content=[TextContent(type="text", text=msg)], isError=False)
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorHTTPCallAPI:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorHTTPCallAPI: traceback information not available:" + str(e)
        log3(ex_stat)
        return [TextContent(type="text", text=ex_stat)]

async def http_call_api(mainwin, args):
    try:
        browser_context = mainwin.getBrowserContextById(args["context_id"])
        browser = browser_context.browser
        if args.index not in await browser.get_selector_map():
            raise Exception(f'Element index {args.index} does not exist - retry or use alternative actions')

        pyautogui.moveTo(args.loc.x, args.loc.y)

        logger.debug(f'Element xpath: {args.loc.x},  {args.loc.y}')
        msg = ""
        return CallToolResult(content=[TextContent(type="text", text=msg)], isError=False)
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorHTTPCallAPI:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorHTTPCallAPI: traceback information not available:" + str(e)
        log3(ex_stat)
        return [TextContent(type="text", text=ex_stat)]

async def os_connect_to_adspower(mainwin, args):
    webdriver_path = mainwin.default_webdriver_path

    print("inital state:", args)
    try:
        url = args['input']["url"]
        # global ads_config, local_api_key, local_api_port, sk_work_settings
        ads_port = mainwin.ads_settings['ads_port']
        ads_api_key = mainwin.ads_settings['ads_api_key']
        ads_chrome_version = mainwin.ads_settings['chrome_version']
        scraper_email = mainwin.ads_settings.get("default_scraper_email", "")
        web_driver_options = ""
        print('check_browser_and_drivers:', 'ads_port:', ads_port, 'ads_api_key:', ads_api_key, 'ads_chrome_version:',
              ads_chrome_version)
        profiles = queryAdspowerProfile(ads_api_key, ads_port)
        loaded_profiles = {}
        for profile in profiles:
            loaded_profiles[profile['username']] = {"uid": profile['user_id'], "remark": profile['remark']}

        ads_profile_id = loaded_profiles[scraper_email]['uid']
        ads_profile_remark = loaded_profiles[scraper_email]['remark']
        print('ads_profile_id, ads_profile_remark:', ads_profile_id, ads_profile_remark)

        webdriver, result = startADSWebDriver(ads_api_key, ads_port, ads_profile_id, webdriver_path, web_driver_options)

        webdriver.switch_to.window(webdriver.window_handles[0])
        time.sleep(3)
        webdriver.execute_script(f"window.open('{url}', '_blank');")

        # Switch to the new tab
        webdriver.switch_to.window(webdriver.window_handles[-1])
        time.sleep(3)
        # Navigate to the new URL in the new tab
        if url:
            webdriver.get(url)  # Replace with the new URL
            print("open URL: " + url)

        mainwin.setWebDriver(webdriver)
        # set up output.
        msg = "completed connect to adspower."

        result = TextContent(type="text", text=f"{msg}")
        result.meta = {"page": url}

        return [result]

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorCheckADSPowerAndDrivers:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorCheckADSPowerAndDrivers: traceback information not available:" + str(e)
        log3(ex_stat)
        return [TextContent(type="text", text=ex_stat)]


async def os_connect_to_chrome(mainwin, args):
    webdriver_path = mainwin.default_webdriver_path

    print("inital state:", args)
    try:
        url = args["url"]
        # global ads_config, local_api_key, local_api_port, sk_work_settings
        ads_port = mainwin.ads_settings['ads_port']
        ads_api_key = mainwin.ads_settings['ads_api_key']
        ads_chrome_version = mainwin.ads_settings['chrome_version']
        scraper_email = mainwin.ads_settings.get("default_scraper_email", "")
        web_driver_options = ""
        print('check_browser_and_drivers:', 'ads_port:', ads_port, 'ads_api_key:', ads_api_key, 'ads_chrome_version:',
              ads_chrome_version)
        profiles = queryAdspowerProfile(ads_api_key, ads_port)
        loaded_profiles = {}
        for profile in profiles:
            loaded_profiles[profile['username']] = {"uid": profile['user_id'], "remark": profile['remark']}

        ads_profile_id = loaded_profiles[scraper_email]['uid']
        ads_profile_remark = loaded_profiles[scraper_email]['remark']
        print('ads_profile_id, ads_profile_remark:', ads_profile_id, ads_profile_remark)

        webdriver, result = startADSWebDriver(ads_api_key, ads_port, ads_profile_id, webdriver_path, web_driver_options)

        webdriver.switch_to.window(webdriver.window_handles[0])
        time.sleep(3)
        webdriver.execute_script(f"window.open('{url}', '_blank');")

        # Switch to the new tab
        webdriver.switch_to.window(webdriver.window_handles[-1])
        time.sleep(3)
        # Navigate to the new URL in the new tab
        if url:
            webdriver.get(url)  # Replace with the new URL
            print("open URL: " + url)

        mainwin.setWebDriver(webdriver)
        # set up output.
        msg = "completed"
        result = [TextContent(type="text", text=msg)]
        return result

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorCheckChromeAndDrivers:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorCheckChromeAndDrivers: traceback information not available:" + str(e)
        log3(ex_stat)
        return [TextContent(type="text", text=ex_stat)]



async def os_open_app(mainwin, args):
    try:
        browser_context = mainwin.getBrowserContextById(args["context_id"])
        browser = browser_context.browser
        if args.index not in await browser.get_selector_map():
            raise Exception(f'Element index {args.index} does not exist - retry or use alternative actions')

        DETACHED_PROCESS = 0x00000008
        subprocess.Popen(args.app_name, creationflags=DETACHED_PROCESS, shell=True, close_fds=True,
                         stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE)

        logger.debug(f'Element xpath: {args.loc.x},  {args.loc.y}')
        msg = ""
        result = [TextContent(type="text", text=msg)]
        return result

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorOpenApp:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorOpenApp: traceback information not available:" + str(e)
        log3(ex_stat)
        return [TextContent(type="text", text=ex_stat)]


async def os_close_app(mainwin, args):
    try:
        browser_context = mainwin.getBrowserContextById(args["context_id"])
        browser = browser_context.browser
        if args.index not in await browser.get_selector_map():
            raise Exception(f'Element index {args.index} does not exist - retry or use alternative actions')

        app_window = gw.getWindowsWithTitle(args.win_title)[0]
        app_window.close()

        logger.debug(f'Element xpath: {args.loc.x},  {args.loc.y}')
        msg = ""
        result = [TextContent(type="text", text=msg)]
        return result
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorCloseApp:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorCloseApp: traceback information not available:" + str(e)
        log3(ex_stat)
        return [TextContent(type="text", text=ex_stat)]

async def os_switch_to_app(mainwin, args):
    try:
        browser_context = mainwin.getBrowserContextById(args["context_id"])
        browser = browser_context.browser
        if args.index not in await browser.get_selector_map():
            raise Exception(f'Element index {args.index} does not exist - retry or use alternative actions')

        # Find the window by its title
        target_window = gw.getWindowsWithTitle(args.win_title)[0]

        # Activate the window (bring it to front)
        target_window.activate()

        logger.debug(f'Element xpath: {args.loc.x},  {args.loc.y}')
        msg = ""
        result = [TextContent(type="text", text=msg)]
        return result
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorSwitchToApp:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorSwitchToApp: traceback information not available:" + str(e)
        log3(ex_stat)
        return [TextContent(type="text", text=ex_stat)]

async def python_run_extern(mainwin, args):
    try:
        browser_context = mainwin.getBrowserContextById(args["context_id"])
        browser = browser_context.browser
        if args.index not in await browser.get_selector_map():
            raise Exception(f'Element index {args.index} does not exist - retry or use alternative actions')

        time.sleep(args.time)

        logger.debug(f'Element xpath: {args.loc.x},  {args.loc.y}')
        msg = ""
        result = [TextContent(type="text", text=msg)]
        return result
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorRunExternPython:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorRunExternPython: traceback information not available:" + str(e)
        log3(ex_stat)
        return [TextContent(type="text", text=ex_stat)]

async def os_make_dir(mainwin, args):
    try:
        browser_context = mainwin.getBrowserContextById(args["context_id"])
        browser = browser_context.browser
        if args.index not in await browser.get_selector_map():
            raise Exception(f'Element index {args.index} does not exist - retry or use alternative actions')

        if not os.path.exists(args.dir_path):
            # create only if the dir doesn't exist
            os.makedirs(args.dir_path)

        logger.debug(f'Element xpath: {args.loc.x},  {args.loc.y}')
        msg = ""
        result = [TextContent(type="text", text=msg)]
        return result
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorOSMakeDir:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorOSMakeDir: traceback information not available:" + str(e)
        log3(ex_stat)
        return [TextContent(type="text", text=ex_stat)]


async def os_delete_dir(mainwin, args):
    try:
        browser_context = mainwin.getBrowserContextById(args["context_id"])
        browser = browser_context.browser
        if args.index not in await browser.get_selector_map():
            raise Exception(f'Element index {args.index} does not exist - retry or use alternative actions')

        if os.path.exists(args.dir_path):
            # create only if the dir doesn't exist
            os.remove(args.dir_path)

        logger.debug(f'Element xpath: {args.loc.x},  {args.loc.y}')
        msg = ""
        result = [TextContent(type="text", text=msg)]
        return result
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorOSDeleteDir:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorOSDeleteDir: traceback information not available:" + str(e)
        log3(ex_stat)
        return [TextContent(type="text", text=ex_stat)]


async def os_delete_file(mainwin, args):
    try:
        browser_context = mainwin.getBrowserContextById(args["context_id"])
        browser = browser_context.browser
        if args.index not in await browser.get_selector_map():
            raise Exception(f'Element index {args.index} does not exist - retry or use alternative actions')

        if os.path.exists(args.file):
            # create only if the dir doesn't exist
            os.remove(args.file)

        logger.debug(f'Element xpath: {args.loc.x},  {args.loc.y}')
        msg = ""
        result = [TextContent(type="text", text=msg)]
        return result
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorOSDeleteFile:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorOSDeleteFile: traceback information not available:" + str(e)
        log3(ex_stat)
        return [TextContent(type="text", text=ex_stat)]


async def os_move_file(mainwin, args):
    try:
        browser_context = mainwin.getBrowserContextById(args["context_id"])
        browser = browser_context.browser
        if args.index not in await browser.get_selector_map():
            raise Exception(f'Element index {args.index} does not exist - retry or use alternative actions')

        # default_download_dir = getDefaultDownloadDirectory()
        # new_file = getMostRecentFile(default_download_dir, prefix=step["prefix"], extension=step["extension"])

        shutil.move(args.src, args.dest)

        logger.debug(f'Element xpath: {args.loc.x},  {args.loc.y}')

        msg = ""
        result = [TextContent(type="text", text=msg)]
        return result
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorOSMoveFile:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorOSMoveFile: traceback information not available:" + str(e)
        log3(ex_stat)
        return [TextContent(type="text", text=ex_stat)]


async def os_copy_file_dir(mainwin, args):
    try:
        browser_context = mainwin.getBrowserContextById(args["context_id"])
        browser = browser_context.browser
        if args.index not in await browser.get_selector_map():
            raise Exception(f'Element index {args.index} does not exist - retry or use alternative actions')

        shutil.copy(args.src, args.dest)

        logger.debug(f'Element xpath: {args.loc.x},  {args.loc.y}')
        msg = ""
        result = [TextContent(type="text", text=msg)]
        return result
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorOSCopyFileDir:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorOSCopyFileDir: traceback information not available:" + str(e)
        log3(ex_stat)
        return [TextContent(type="text", text=ex_stat)]


async def os_screen_analyze(mainwin, args):
    try:
        browser_context = mainwin.getBrowserContextById(args["context_id"])
        browser = browser_context.browser
        if args.index not in await browser.get_selector_map():
            raise Exception(f'Element index {args.index} does not exist - retry or use alternative actions')

        element_node = await browser.get_dom_element_by_index(args.index)
        nClicks = 1
        interval = 0.1
        pyautogui.click(clicks=nClicks, interval=interval)
        if not has_sensitive_data:
            msg = f'⌨️  Input {args.text} into index {args.index}'
        else:
            msg = f'⌨️  Input sensitive data into index {args.index}'
        logger.info(msg)
        logger.debug(f'Element xpath: {element_node.xpath}')
        result = [TextContent(type="text", text=msg)]
        return result

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorOSScreenAnalyze:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorOSScreenAnalyze: traceback information not available:" + str(e)
        log3(ex_stat)
        return [TextContent(type="text", text=ex_stat)]


async def os_screen_capture(mainwin, args):
    try:
        browser_context = mainwin.getBrowserContextById(args["context_id"])
        browser = browser_context.browser
        if args.index not in await browser.get_selector_map():
            raise Exception(f'Element index {args.index} does not exist - retry or use alternative actions')

        screen_img, window_rect = await takeScreenShot(args.win_title_kw)
        img_section = carveOutImage(screen_img, args.sub_area, "")
        maskOutImage(img_section, args.sub_area, "")

        saveImageToFile(img_section, args.file, "png")

        logger.debug(f'Element xpath: {args.win_title_kw}')
        msg = ""
        result = [TextContent(type="text", text=msg)]
        return result
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorOSScreenCapture:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorOSScreenCapture: traceback information not available:" + str(e)
        log3(ex_stat)
        return [TextContent(type="text", text=ex_stat)]


async def os_seven_zip(mainwin, args):
    try:
        context_id = args["context_id"]
        browser_context = mainwin.getBrowserContextById(context_id)
        browser = browser_context.browser
        if args.index not in await browser.get_selector_map():
            raise Exception(f'Element index {args.index} does not exist - retry or use alternative actions')

        logger.debug(f'Element xpath: {args.file}')
        msg = ""
        result = [TextContent(type="text", text=msg)]
        return result
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorOSSevenZip:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorOSSevenZip: traceback information not available:" + str(e)
        log3(ex_stat)
        return [TextContent(type="text", text=ex_stat)]


async def os_kill_processes(mainwin, args):
    try:
        browser_context = mainwin.getBrowserContextById(args["context_id"])
        browser = browser_context.browser
        if args.index not in await browser.get_selector_map():
            raise Exception(f'Element index {args.index} does not exist - retry or use alternative actions')

        logger.debug(f'Kill Processes: {args.pids[0]}')
        msg = ""
        result = [TextContent(type="text", text=msg)]
        return result
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorOSKillProcesses:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorOSKillProcesses: traceback information not available:" + str(e)
        log3(ex_stat)
        return [TextContent(type="text", text=ex_stat)]

# Element Interaction Actions
async def rpa_supervisor_scheduling_work(mainwin, args) -> CallToolResult:
    print("INPUT:", args)
    # if tool_name != "rpa_supervisor_scheduling_work":
    #     raise ValueError(f"Unexpected tool name: {tool_name}")
    global server_main_win
    try:
        # mainwin = params["agent"].mainwin
        print(f"[MCP] Running supervisor scheduler tool... ")
        print(f"[MCP] Running supervisor scheduler tool... Bots: {len(server_main_win.bots)}")
        schedule = server_main_win.fetchSchedule("", server_main_win.get_vehicle_settings())
        print("MCP fetched schedule.......", schedule)
        # workable = server_main_win.runTeamPrepHook(schedule)
        # works_to_be_dispatched = server_main_win.handleCloudScheduledWorks(workable)
        workable = schedule
        msg = "Here are works to be dispatched to the troops."
        print("MCP MSG:", msg, workable)
        # ctr = CallToolResult(content=[TextContent(type="text", text=msg)], _meta=workable, isError=False)
        ctr = CallToolResult(content=[TextContent(type="text", text=msg)])
        print("ABOUT TO return call tool result", type(ctr), ctr)
        print("ABOUT CTR Type", ctr.model_dump(by_alias=True, exclude_none=True, mode="json"))
        tool_result =  {
            "content": [{"type": "text", "text": msg}],
            # "meta": workable,
            "isError": False
        }
        print("[DEBUG] Returning result:", json.dumps(tool_result, indent=2))
        # return ctr.model_dump(by_alias=True, exclude_none=True, mode="json", round_trip=False)
        return [TextContent(type="text", text=msg), TextContent(type="text", text=json.dumps(workable))]
    except Exception as e:
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorRPASupervisorSchedulingWork:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorRPASupervisorSchedulingWork: traceback information not available:" + str(e)
        print("ex_stat:", ex_stat)
        return [TextContent(type="text", text=ex_stat)]

# class Result(BaseModel):
#     """Base class for JSON-RPC results."""
#
#     model_config = ConfigDict(extra="allow")
#
#     meta: dict[str, Any] | None = Field(alias="_meta", default=None)
#     """
#     This result property is reserved by the protocol to allow clients and servers to
#     attach additional metadata to their responses.
#     """
# class CallToolResult(Result):
#     """The server's response to a tool call."""
#
#     content: list[TextContent | ImageContent | EmbeddedResource]
#     isError: bool = False
async def rpa_operator_dispatch_works(mainwin, args):
    # call put work received from A2A channel, put into today's work data structure
    # the runbotworks task will then take over.....
    # including put reactive work into it.
    try:
        works_to_be_dispatched = mainwin.handleCloudScheduledWorks(workable)
        text_content = [TextContent(type="text", text=f"works dispatched")]
        return text_content
    except Exception as e:
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorRPAOperatorDispatchWorks:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorRPAOperatorDispatchWorks: traceback information not available:" + str(e)
        print("ex_stat:", ex_stat)
        return [TextContent(type="text", text=ex_stat)]


async def rpa_supervisor_process_work_results(mainwin, args):
    # handle RPA work results from a platoon host.
    # mostly bookkeeping.
    try:
        works_to_be_dispatched = mainwin.handleCloudScheduledWorks(workable)
        text_content = [TextContent(type="text", text=f"works dispatched")]
        return text_content
    except Exception as e:
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorRPASupervisorProcessWorkResults:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorRPASupervisorProcessWorkResults: traceback information not available:" + str(e)
        print("ex_stat:", ex_stat)
        return [TextContent(type="text", text=ex_stat)]


async def rpa_supervisor_run_daily_housekeeping(mainwin, args):
    # call put work received from A2A channel, put into today's work data structure
    # the runbotworks task will then take over.....
    # including put reactive work into it.
    try:
        works_to_be_dispatched = mainwin.handleCloudScheduledWorks(workable)
        text_content = [TextContent(type="text", text=f"works dispatched")]
        return text_content
    except Exception as e:
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorRPASupervisorRunDailyHousekeeping:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorRPASupervisorRunDailyHousekeeping: traceback information not available:" + str(e)
        print("ex_stat:", ex_stat)
        return [TextContent(type="text", text=ex_stat)]

async def rpa_operator_report_work_results(mainwin, args):
    # call put work received from A2A channel, put into today's work data structure
    # the runbotworks task will then take over.....
    # including put reactive work into it.
    try:
        works_to_be_dispatched = mainwin.handleCloudScheduledWorks(workable)
        text_content = [TextContent(type="text", text=f"works dispatched")]
        return text_content
    except Exception as e:
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorRPAOperatorReportWorkResults:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorRPAOperatorReportWorkResults: traceback information not available:" + str(e)
        print("ex_stat:", ex_stat)
        return [TextContent(type="text", text=ex_stat)]


async def os_reconnect_wifi(mainwin, args):
    try:
        # Disconnect current Wi-Fi
        subprocess.run(["netsh", "wlan", "disconnect"])
        time.sleep(2)

        # Reconnect to a specific network
        cmd = ["netsh", "wlan", "connect", f"name={args['network_name']}"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        print(result.stdout)
        return [TextContent(type="text", text=result.stdout)]
    except Exception as e:
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorOSReconnectWifi:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorOSReconnectWifi: traceback information not available:" + str(e)
        print("ex_stat:", ex_stat)
        return [TextContent(type="text", text=ex_stat)]


tool_function_mapping = {
        "say_hello": say_hello,
        "wait": os_wait,
        "in_browser_wait_for_element": in_browser_wait_for_element,
        "in_browser_click_element_by_index": in_browser_click_element_by_index,
        "in_browser_click_element_by_selector": in_browser_click_element_by_selector,
        "in_browser_click_element_by_xpath": in_browser_click_element_by_xpath,
        "in_browser_click_element_by_text": in_browser_click_element_by_text,
        "in_browser_input_text": in_browser_input_text,
        "in_browser_save_pdf": in_browser_save_pdf,
        "in_browser_switch_tab": in_browser_switch_tab,
        "in_browser_open_tab": in_browser_open_tab,
        "in_browser_close_tab": in_browser_close_tab,
        "in_browser_extract_content": in_browser_scrape_content,
        "in_browser_save_html_to_file": in_browser_save_html_to_file,
        "in_browser_execute_javascript": in_browser_execute_javascript,
        "in_browser_build_dom_tree": in_browser_build_dom_tree,
        "in_browser_scroll_down": in_browser_scroll_down,
        "in_browser_scroll_up": in_browser_scroll_up,
        "in_browser_send_keys": in_browser_send_keys,
        "in_browser_scroll_to_text": in_browser_scroll_to_text,
        "in_browser_get_dropdown_options": in_browser_get_dropdown_options,
        "in_browser_select_dropdown_option": in_browser_select_dropdown_option,
        "in_browser_drag_drop": in_browser_drag_drop,
        "mouse_click": mouse_click,
        "mouse_move": mouse_move,
        "mouse_drag_drop": mouse_drag_drop,
        "mouse_scroll": mouse_scroll,
        "keyboard_text_input": keyboard_text_input,
        "keyboard_keys_input": keyboard_keys_input,
        "http_call_api": http_call_api,
        "os_open_app": os_open_app,
        "os_close_app": os_close_app,
        "os_switch_to_app": os_switch_to_app,
        "python_run_extern": python_run_extern,
        "os_make_dir": os_make_dir,
        "os_delete_dir": os_delete_dir,
        "os_delete_file": os_delete_file,
        "os_move_file": os_move_file,
        "os_copy_file_dir": os_copy_file_dir,
        "os_screen_analyze": os_screen_analyze,
        "os_screen_capture": os_screen_capture,
        "os_seven_zip": os_seven_zip,
        "os_kill_processes": os_kill_processes,
        "rpa_supervisor_scheduling_work": rpa_supervisor_scheduling_work,
        "rpa_operator_dispatch_works": rpa_operator_dispatch_works,
        "rpa_supervisor_process_work_results": rpa_supervisor_process_work_results,
        "rpa_supervisor_run_daily_housekeeping": rpa_supervisor_run_daily_housekeeping,
        "rpa_operator_report_work_results": rpa_operator_report_work_results,
        "os_connect_to_adspower": os_connect_to_adspower,
        "os_connect_to_chrome": os_connect_to_chrome,
        "os_reconnect_wifi": os_reconnect_wifi
    }

def set_server_main_win(mw):
    global server_main_win
    server_main_win = mw


# Create event store for resumability
# The InMemoryEventStore enables resumability support for StreamableHTTP transport.
# It stores SSE events with unique IDs, allowing clients to:
#   1. Receive event IDs for each SSE message
#   2. Resume streams by sending Last-Event-ID in GET requests
#   3. Replay missed events after reconnection
# Note: This in-memory implementation is for demonstration ONLY.
# For production, use a persistent storage solution.
event_store = InMemoryEventStore()

# Create the session manager with our app and event store
session_manager = StreamableHTTPSessionManager(
    app=meca_mcp_server,
    event_store=None,  # set to event_store to Enable resumability
    json_response=True,
)

# ASGI handler for streamable HTTP connections
async def handle_streamable_http(
    scope: Scope, receive: Receive, send: Send
) -> None:
    await session_manager.handle_request(scope, receive, send)

@contextlib.asynccontextmanager
async def lifespan(app: Starlette) -> AsyncIterator[None]:
    """Context manager for managing session manager lifecycle."""
    async with session_manager.run():
        logger.info("Application started with StreamableHTTP session manager!")
        try:
            yield
        finally:
            logger.info("Application shutting down...")

# async def handle_sse(scope, receive, send):
#     print(">>> sse connected")
#     async with meca_sse.connect_sse(scope, receive, send) as streams:
#         print("handling meca_mcp_server.run", streams)
#         await meca_mcp_server.run(streams[0], streams[1], meca_mcp_server.create_initialization_options())

async def handle_sse(scope, receive, send):
    print(">>> sse connected")
    async with meca_sse.connect_sse(scope, receive, send) as (read_stream, write_stream, is_new):
        # Start MCP server only on the very first GET (= new session)
        if is_new:
            print("handling meca_mcp_server.run", read_stream, write_stream)
            await meca_mcp_server.run(
                read_stream,
                write_stream,
                meca_mcp_server.create_initialization_options(),
            )

async def sse_handle_messages(scope, receive, send):
    print(">>> sse handle messages connected")
    await meca_sse.handle_post_message(scope, receive, send)


