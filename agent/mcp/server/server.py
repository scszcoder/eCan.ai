# Standard library imports
import asyncio
import json
import os
import shutil
import subprocess
import time
import traceback

# Configure browser_use timeouts BEFORE importing browser_use modules
# Increase screenshot timeout from default 8s to 30s for complex pages
os.environ.setdefault('TIMEOUT_ScreenshotEvent', '30')

# Third-party library imports
import pyautogui
import pygetwindow as gw
from pynput.mouse import Controller
from starlette.types import Receive, Scope, Send

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC

# MCP library imports
from mcp.server.fastmcp.prompts import base
from mcp.server.lowlevel import Server
from mcp.server.sse import SseServerTransport
from mcp.server.streamable_http import StreamableHTTPServerTransport
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import CallToolResult, TextContent, Tool
from browser_use.actor import Page, Element, Mouse
from browser_use.browser.events import SwitchTabEvent
# Local application imports
from agent.mcp.server.ads_power.ads_power import connect_to_adspower, connect_to_existing_chrome
from agent.mcp.server.tool_schemas import get_tool_schemas
from agent.mcp.server.api.ecan_ai.ecan_ai_api import (
    api_ecan_ai_get_nodes_prompts,
    api_ecan_ai_ocr_read_screen,
    ecan_ai_api_query_components,
    ecan_ai_api_query_fom,
    ecan_ai_api_rerank_results,
)
from agent.mcp.server.scrapers.amazon_seller.amazon_search import amazon_search
from agent.mcp.server.scrapers.amazon_seller.amazon_listing import (
    amazon_add_listings,
    amazon_remove_listings,
    amazon_update_listings,
    amazon_get_listings,
    amazon_add_listing_templates,
    amazon_remove_listing_templates,
    amazon_update_listing_templates,
)
from agent.mcp.server.scrapers.amazon_seller.amazon_cancel_return import (
    amazon_handle_return,
    amazon_handle_refund,
)
from agent.mcp.server.scrapers.amazon_seller.amazon_campaign import (
    amazon_collect_campaigns_stats,
    amazon_adjust_campaigns,
)
from agent.mcp.server.scrapers.amazon_seller.amazon_performance import (
    amazon_collect_shop_products_stats,
)
from agent.mcp.server.scrapers.amazon_seller.amazon_utils import (
    amazon_generate_work_summary,
)
from agent.mcp.server.scrapers.api_ecan_ai_cloud_search.api_ecan_ai_cloud_search import api_ecan_ai_cloud_search
from agent.mcp.server.scrapers.ebay_seller.ebay_messages_scrape import ebay_read_all_messages, ebay_respond_to_message, ebay_read_next_message
from agent.mcp.server.scrapers.ebay_seller.ebay_orders_scrape import ebay_fullfill_next_order, get_ebay_summary, ebay_cancel_orders
from agent.mcp.server.scrapers.ebay_seller.ebay_search import ebay_search
from agent.mcp.server.scrapers.ebay_seller.ebay_labels import ebay_gen_labels
from agent.mcp.server.scrapers.ebay_seller.ebay_cancel_return import ebay_handle_return, ebay_handle_refund
from agent.mcp.server.scrapers.ebay_seller.ebay_utils import ebay_generate_work_summary


from agent.mcp.server.scrapers.etsy_seller.etsy_search import etsy_search
from agent.mcp.server.scrapers.etsy_seller.etsy_listing import (
    etsy_add_listings,
    etsy_remove_listings,
    etsy_update_listings,
    etsy_get_listings,
    etsy_add_listing_templates,
    etsy_remove_listing_templates,
    etsy_update_listing_templates,
)
from agent.mcp.server.scrapers.etsy_seller.etsy_cancel_return import (
    etsy_handle_return,
    etsy_handle_refund,
)
from agent.mcp.server.scrapers.etsy_seller.etsy_campaign import (
    etsy_collect_campaigns_stats,
    etsy_adjust_campaigns,
)
from agent.mcp.server.scrapers.etsy_seller.etsy_performance import (
    etsy_collect_shop_products_stats,
)
from agent.mcp.server.scrapers.etsy_seller.etsy_utils import (
    etsy_generate_work_summary,
)
from agent.mcp.server.scrapers.pirate_shipping.purchase_label import pirate_shipping_purchase_labels
from agent.mcp.server.scrapers.selenium_search_component import (
    selenium_search_component,
    selenium_sort_search_results,
)
from agent.mcp.server.scrapers.gmail.gmail_read import (
    gmail_delete_email,
    gmail_move_email,
    gmail_respond,
    gmail_write_new,
    gmail_read_titles,
    gmail_mark_status,
    gmail_read_full_email,
)
from agent.mcp.server.Privacy.privacy_reserve import privacy_reserve
from agent.ec_skills.rag.local_rag_mcp import ragify, rag_query, wait_for_rag_completion, ragify_async
from agent.mcp.server.self_utils.self_tools import (
    async_describe_self,
    async_start_task_using_skill,
    async_stop_task_using_skill,
    async_schedule_task,
)
from agent.mcp.server.code_utils.code_tools import (
    async_run_code,
    async_run_shell_script,
    async_grep_search,
    async_find_files,
)
from agent.mcp.server.chat_utils.chat_tools import (
    async_send_chat,
    async_list_chat_agents,
    async_get_chat_history,
)
from agent.ec_skills.label_utils.print_label import reformat_labels, print_labels
from agent.ec_skills.browser_use_extension.extension_tools_service import *
from app_context import AppContext
from agent.ec_skills.ocr.image_prep import readRandomWindow8
from utils.logger_helper import get_traceback
from utils.logger_helper import logger_helper as logger
from .event_store import InMemoryEventStore


server_main_win = None

mouse = Controller()

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
async def list_tools() -> list[Tool]:
    logger.debug("=" * 80)
    logger.debug("📋 MCP Tools List Request")
    logger.debug("=" * 80)
    
    all_tools = get_tool_schemas()
    
    logger.debug(f"\n✅ Total MCP Tools: {len(all_tools)}\n")
    # logger.debug("📝 Tool List:")
    # logger.debug("-" * 80)
    
    # for idx, tool in enumerate(all_tools, 1):
    #     tool_name = tool.name if hasattr(tool, 'name') else str(tool)
    #     tool_desc = tool.description if hasattr(tool, 'description') else 'No description'
        
    #     # 截断过长的描述
    #     if len(tool_desc) > 60:
    #         tool_desc = tool_desc[:57] + "..."
        
    #     logger.debug(f"  {idx:2d}. {tool_name:<40s} | {tool_desc}")
    
    # logger.debug("-" * 80)
    # logger.debug(f"✅ Listed {len(all_tools)} MCP tools successfully\n")
    
    return all_tools



@meca_mcp_server.call_tool()
async def unified_tool_handler(tool_name, args):
    logger.debug(f"[unified_tool_handler] Received call for tool: {tool_name}")
    login = AppContext.login
    
    # Debug: Check if login and main_win are available
    if login is None:
        logger.error(f"[unified_tool_handler] AppContext.login is None!")
        return CallToolResult(
            content=[TextContent(type="text", text="Error: AppContext.login is None - MCP server not properly initialized")],
            isError=True
        )
    
    if not hasattr(login, 'main_win') or login.main_win is None:
        logger.error(f"[unified_tool_handler] login.main_win is None!")
        return CallToolResult(
            content=[TextContent(type="text", text="Error: login.main_win is None - MainGUI not connected to MCP server")],
            isError=True
        )
    
    try:
        if tool_name not in tool_function_mapping:
            logger.error(f"[unified_tool_handler] Tool '{tool_name}' not found in tool_function_mapping!")
            return CallToolResult(
                content=[TextContent(type="text", text=f"Error: Tool '{tool_name}' not registered in tool_function_mapping")],
                isError=True
            )
        
        tool_func = tool_function_mapping[tool_name]
        logger.debug(f"[unified_tool_handler] Calling {tool_name} with args: {args}")
        # very key make sure each tool_func returns: [ContentBlock]
        # ContentBlock = TextContent | ImageContent | AudioContent | ResourceLink | EmbeddedResource
        # [TextContent(type="text", text=f"all completed fine")]

        toolResult = await tool_func(login.main_win, args)
        logger.debug(f"[unified_tool_handler] {tool_name} completed successfully")

        return toolResult
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorCallTool:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorCallTool: traceback information not available:" + str(e)
        logger.error(ex_stat)
        return CallToolResult(
                    content=[TextContent(type="text", text=str(ex_stat))],
                    isError=True
                )

# async def unified_tool_handler(tool_name, args):
#     login = AppContext.login
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
        msg = f'🕒  Waited for {args["input"]["seconds"]} seconds'
        logger.info(msg)
        await asyncio.sleep(args['input']["seconds"])
        result = [TextContent(type="text", text=msg)]
        return result
    except Exception as e:
        # Get the traceback information
        err_trace = get_traceback(e, "ErrorOSWait")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]

def get_selector(element_type):
    """Convert element type string to Selenium By locator.
    
    Args:
        element_type: String like 'css', 'xpath', 'id', 'name', 'class', 'tag', 'link_text', 'partial_link_text'
    
    Returns:
        Corresponding By.* locator
    """
    selectors = {
        'css': By.CSS_SELECTOR,
        'css_selector': By.CSS_SELECTOR,
        'xpath': By.XPATH,
        'id': By.ID,
        'name': By.NAME,
        'class': By.CLASS_NAME,
        'class_name': By.CLASS_NAME,
        'tag': By.TAG_NAME,
        'tag_name': By.TAG_NAME,
        'link_text': By.LINK_TEXT,
        'partial_link_text': By.PARTIAL_LINK_TEXT,
    }
    return selectors.get(element_type.lower(), By.CSS_SELECTOR)


# ============================================================================
# Dual-Mode Browser Helpers: WebDriver vs CDP (BrowserSession)
# ============================================================================

def _get_browser_type_enum(browser_type_str: str):
    """Convert browser_type string to BrowserType enum."""
    from gui.manager.browser_manager import BrowserType
    mapping = {
        "adspower": BrowserType.ADSPOWER,
        "existing chrome": BrowserType.CHROME,
        "chrome": BrowserType.CHROME,
        "chromium": BrowserType.CHROMIUM,
    }
    return mapping.get(browser_type_str.lower(), BrowserType.CHROME)


def _get_driver_mode(args) -> str:
    """
    Determine driver mode from args.
    Returns: 'webdriver' or 'cdp'
    """
    driver_type = args.get("input", {}).get("driver_type", "webdriver")
    return driver_type.lower() if driver_type else "webdriver"


async def _get_browser_session_by_type(mainwin, browser_type_str: str):
    """
    Get or create a BrowserSession based on browser_type.
    
    Args:
        mainwin: Main window instance
        browser_type_str: One of "adspower", "existing chrome", "chromium"
    
    Returns:
        BrowserSession instance
    """
    from gui.manager.browser_manager import BrowserManager, BrowserType
    
    browser_type = _get_browser_type_enum(browser_type_str)
    
    # Try to get from mainwin first
    browser_session = mainwin.getBrowserSession() if hasattr(mainwin, 'getBrowserSession') else None
    if browser_session:
        return browser_session
    
    # Try to get from BrowserManager
    browser_manager = getattr(mainwin, 'browser_manager', None)
    if browser_manager:
        auto_browser = browser_manager.find_available_browser(browser_type=browser_type)
        if auto_browser and auto_browser.browser_session:
            return auto_browser.browser_session
    
    # Create new session if needed
    if hasattr(mainwin, 'createBrowserSession'):
        browser_session = mainwin.createBrowserSession(browser_type_str)
        await browser_session.start()
        return browser_session
    
    return None


async def _get_current_page(browser_session):
    """Get the current page from a BrowserSession."""
    if browser_session:
        return await browser_session.get_current_page()
    return None


def _get_webdriver(mainwin):
    """Get WebDriver from mainwin."""
    return mainwin.getWebDriver() if hasattr(mainwin, 'getWebDriver') else None


async def in_browser_wait_for_element(mainwin, args):
    """Waits for the element specified by the CSS selector to become visible within the given timeout."""
    try:
        driver_mode = _get_driver_mode(args)
        element_type = args['input'].get("element_type", "css_selector")
        element_name = args['input'].get("element_name", "")
        timeout = args['input'].get("timeout", 10)
        found = False
        
        if driver_mode == "webdriver":
            web_driver = _get_webdriver(mainwin)
            if web_driver:
                wait = WebDriverWait(web_driver, timeout)
                sel = get_selector(element_type)
                args.tool_result = wait.until(EC.element_to_be_clickable((sel, element_name)))
                found = args.tool_result is not None
        else:
            # CDP mode using BrowserSession
            browser_type = args['input'].get("browser_type", "existing chrome")
            browser_session = await _get_browser_session_by_type(mainwin, browser_type)
            if browser_session:
                page = await _get_current_page(browser_session)
                if page:
                    # Poll for element visibility - handle both CSS selector and XPath
                    for _ in range(int(timeout * 2)):
                        if element_type == "xpath":
                            # Use JS to find element by XPath
                            escaped_xpath = element_name.replace('"', '\\"')
                            js_code = f'() => {{ const result = document.evaluate("{escaped_xpath}", document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null); return result.singleNodeValue ? true : false; }}'
                            result = await page.evaluate(js_code)
                            if result:
                                found = True
                                break
                        else:
                            # CSS selector
                            elements = await page.get_elements_by_css_selector(element_name)
                            if elements:
                                args.tool_result = elements[0]
                                found = True
                                break
                        await asyncio.sleep(0.5)
        
        if found:
            msg = f"completed loading element {element_name}."
        else:
            msg = f"timeout waiting for element {element_name}."
        result = [TextContent(type="text", text=msg)]
        return result
    except Exception as e:
        err_trace = get_traceback(e, "ErrorInBrowserWaitForElement")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


# Element Interaction Actions
async def in_browser_click_element_by_index(mainwin, args):
    """Click element by DOM index (primarily used with browser_use DOM tree)."""
    try:
        driver_mode = _get_driver_mode(args)
        index = args['input'].get('index', 0)
        clicked = False
        
        if driver_mode == "webdriver":
            # WebDriver doesn't have native DOM index support
            # This requires a DOM tree to be built first with indexed elements
            web_driver = _get_webdriver(mainwin)
            if web_driver:
                # Try to find element by data-index attribute if DOM was indexed
                element = web_driver.find_element(By.CSS_SELECTOR, f"[data-dom-index='{index}']")
                if element:
                    element.click()
                    clicked = True
                else:
                    raise Exception(f"Element with index {index} not found. Build DOM tree first.")
        else:
            # CDP mode using BrowserSession - use browser_use's indexed DOM
            browser_type = args['input'].get("browser_type", "existing chrome")
            browser_session = await _get_browser_session_by_type(mainwin, browser_type)
            if browser_session:
                page = await _get_current_page(browser_session)
                if page:
                    # Get the DOM state's selector_map which maps index -> DOMElementNode
                    browser_state = await browser_session.get_browser_state_summary(include_screenshot=False)
                    selector_map = browser_state.dom_state.selector_map
                    if index in selector_map:
                        # selector_map[index] is a DOMElementNode with backend_node_id
                        dom_element = selector_map[index]
                        # Get Element from backend_node_id and click it
                        element = await page.get_element(dom_element.backend_node_id)
                        await element.click()
                        await asyncio.sleep(0.5)
                        clicked = True
                    else:
                        raise Exception(f"Element with index {index} not found in selector_map. Available indices: {list(selector_map.keys())[:10]}...")

        if clicked:
            msg = f"completed clicking element by index {index}."
        else:
            msg = f"failed to click element by index {index}."
        result = [TextContent(type="text", text=msg)]
        return result
    except Exception as e:
        err_trace = get_traceback(e, "ErrorInBrowserClickElementByIndex")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]

def webDriverWaitForVisibility(web_driver, by, selector, timeout):
    wait = WebDriverWait(web_driver, timeout)
    locator = (by, selector)
    return wait.until(EC.presence_of_element_located(locator))

async def in_browser_click_element_by_selector(mainwin, args):
    try:
        driver_mode = _get_driver_mode(args)
        css_selector = args['input'].get('css_selector', '')
        timeout = args['input'].get('timeout', 10)
        
        if driver_mode == "webdriver":
            web_driver = _get_webdriver(mainwin)
            if web_driver:
                element_handle = webDriverWaitForVisibility(web_driver, By.CSS_SELECTOR, css_selector, timeout)
                element_handle.click()
        else:
            # CDP mode using BrowserSession
            browser_type = args['input'].get("browser_type", "existing chrome")
            browser_session = await _get_browser_session_by_type(mainwin, browser_type)
            if browser_session:
                page = await _get_current_page(browser_session)
                if page:
                    elements = await page.get_elements_by_css_selector(css_selector)
                    if elements:
                        await elements[0].click()
                        await asyncio.sleep(0.5)

        msg = f"completed clicking element by selector {css_selector}."
        result = [TextContent(type="text", text=msg)]
        return result
    except Exception as e:
        err_trace = get_traceback(e, "ErrorInBrowserClickElementBySelector")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def in_browser_click_element_by_xpath(mainwin, args):
    try:
        driver_mode = _get_driver_mode(args)
        xpath = args['input'].get('xpath', '')
        timeout = args['input'].get('timeout', 10)
        
        if driver_mode == "webdriver":
            web_driver = _get_webdriver(mainwin)
            if web_driver:
                element_handle = webDriverWaitForVisibility(web_driver, By.XPATH, xpath, timeout)
                element_handle.click()
        else:
            # CDP mode using BrowserSession - convert xpath to JS evaluation
            browser_type = args['input'].get("browser_type", "existing chrome")
            browser_session = await _get_browser_session_by_type(mainwin, browser_type)
            if browser_session:
                page = await _get_current_page(browser_session)
                if page:
                    # Use JavaScript to find element by xpath and click
                    escaped_xpath = xpath.replace('"', '\\"')
                    js_code = f'() => {{ const result = document.evaluate("{escaped_xpath}", document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null); const elem = result.singleNodeValue; if (elem) elem.click(); return elem ? "clicked" : "not found"; }}'
                    await page.evaluate(js_code)
                    await asyncio.sleep(0.5)

        msg = f"completed clicking element by xpath {xpath}."
        result = [TextContent(type="text", text=msg)]
        return result
    except Exception as e:
        err_trace = get_traceback(e, "ErrorInBrowserClickElementByXpath")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def in_browser_click_element_by_text(mainwin, args):
    try:
        driver_mode = _get_driver_mode(args)
        element_type = args['input'].get("element_type", "css_selector")
        element_name = args['input'].get("element_name", "")
        element_text = args['input'].get("element_text", "")
        nth = args['input'].get("nth", 0)
        post_wait = args['input'].get("post_wait", 0)
        clicked = False
        
        if driver_mode == "webdriver":
            web_driver = _get_webdriver(mainwin)
            if web_driver:
                web_elements = web_driver.find_elements(get_selector(element_type), element_name)
                # find element by text match
                targets = [ele for ele in web_elements if ele.text == element_text]
                target = targets[nth] if targets and nth < len(targets) else None

                if target:
                    target.click()
                    clicked = True

                if post_wait:
                    time.sleep(post_wait)
        else:
            # CDP mode using BrowserSession - use JavaScript text search
            browser_type = args['input'].get("browser_type", "existing chrome")
            browser_session = await _get_browser_session_by_type(mainwin, browser_type)
            if browser_session:
                page = await _get_current_page(browser_session)
                if page:
                    escaped_text = element_text.replace('"', '\\"')
                    escaped_selector = element_name.replace('"', '\\"') if element_name else "*"
                    
                    # JavaScript to find elements by selector and filter by text content
                    js_code = f'''() => {{
                        const selector = "{escaped_selector}";
                        const targetText = "{escaped_text}";
                        const nth = {nth};
                        
                        // Get all elements matching selector
                        const elements = document.querySelectorAll(selector);
                        const matches = [];
                        
                        for (const el of elements) {{
                            // Check if element's text content matches (exact or contains)
                            const text = el.textContent.trim();
                            if (text === targetText || text.includes(targetText)) {{
                                matches.push(el);
                            }}
                        }}
                        
                        // Click the nth match
                        if (matches.length > nth) {{
                            matches[nth].click();
                            return true;
                        }}
                        return false;
                    }}'''
                    
                    result = await page.evaluate(js_code)
                    clicked = result == "true" or result is True
                    
                    if post_wait:
                        await asyncio.sleep(post_wait)

        if clicked:
            msg = f"completed in-browser click by text '{element_text}'."
        else:
            msg = f"element with text '{element_text}' not found."
        result = [TextContent(type="text", text=msg)]
        return result
    except Exception as e:
        err_trace = get_traceback(e, "ErrorInBrowserClickElementByText")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


def webDriverKeyIn(web_driver, element, text, clear_first=True):
    """Type text into a web element using Selenium.
    
    Args:
        web_driver: Selenium WebDriver instance
        element: Target web element to type into
        text: Text string to type
        clear_first: If True, clear the element before typing (default: True)
    """
    if element is None:
        raise ValueError("Target element is None")
    element.click()  # Focus the element
    if clear_first:
        element.clear()
    element.send_keys(text)


async def in_browser_input_text(mainwin, args):
    try:
        driver_mode = _get_driver_mode(args)
        element_type = args['input'].get("element_type", "css_selector")
        element_name = args['input'].get("element_name", "")
        element_text = args['input'].get("element_text", "")
        text_to_input = args['input'].get("text", "")
        nth = args['input'].get("nth", 0)
        post_enter = args['input'].get("post_enter", False)
        post_wait = args['input'].get("post_wait", 0)
        
        if driver_mode == "webdriver":
            web_driver = _get_webdriver(mainwin)
            if web_driver:
                web_elements = web_driver.find_elements(get_selector(element_type), element_name)
                # find element by text match
                targets = [ele for ele in web_elements if ele.text == element_text] if element_text else web_elements
                target = targets[nth] if targets and nth < len(targets) else (web_elements[0] if web_elements else None)

                if target:
                    webDriverKeyIn(web_driver, target, text_to_input)
                    if post_enter:
                        target.send_keys(Keys.ENTER)

                if post_wait:
                    time.sleep(post_wait)
        else:
            # CDP mode using BrowserSession
            browser_type = args['input'].get("browser_type", "existing chrome")
            browser_session = await _get_browser_session_by_type(mainwin, browser_type)
            if browser_session:
                page = await _get_current_page(browser_session)
                if page:
                    elements = await page.get_elements_by_css_selector(element_name)
                    if elements:
                        target_elem = elements[nth] if nth < len(elements) else elements[0]
                        await target_elem.fill(text_to_input)
                        if post_enter:
                            await page.press("Enter")
                    if post_wait:
                        await asyncio.sleep(post_wait)

        msg = f"completed input text to element {element_name}."
        result = [TextContent(type="text", text=msg)]
        return result
    except Exception as e:
        err_trace = get_traceback(e, "ErrorInBrowserInputText")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]

# Save PDF

# Tab Management Actions
def webDriverSwitchTab(web_driver, tab_title_txt=None, url=None):
    """Switch to a browser tab by title text or URL.
    
    Args:
        web_driver: Selenium WebDriver instance
        tab_title_txt: Partial or full title text to match (optional)
        url: Partial or full URL to match (optional)
    
    Returns:
        True if tab was found and switched, False otherwise
    """
    original_handle = web_driver.current_window_handle
    
    for handle in web_driver.window_handles:
        web_driver.switch_to.window(handle)
        
        # Match by title if provided
        if tab_title_txt and tab_title_txt in web_driver.title:
            return True
        
        # Match by URL if provided
        if url and url in web_driver.current_url:
            return True
    
    # If no match found, switch back to original
    web_driver.switch_to.window(original_handle)
    return False


async def in_browser_switch_tab(mainwin, args):
    try:
        driver_mode = _get_driver_mode(args)
        tab_title_txt = args['input'].get("tab_title_txt", "")
        url = args['input'].get("url", "")
        switched = False
        
        if driver_mode == "webdriver":
            web_driver = _get_webdriver(mainwin)
            if web_driver:
                switched = webDriverSwitchTab(web_driver, tab_title_txt, url)
        else:
            # CDP mode using BrowserSession
            browser_type = args['input'].get("browser_type", "existing chrome")
            browser_session = await _get_browser_session_by_type(mainwin, browser_type)
            if browser_session:
                pages = await browser_session.get_pages()
                for page in pages:
                    page_url = await page.get_url()
                    page_title = await page.get_title()
                    if (url and url in page_url) or (tab_title_txt and tab_title_txt in page_title):
                        # Switch to this page using event
                        target_info = await page.get_target_info()
                        # target_info is a TypedDict with 'targetId' key
                        target_id = target_info.get("targetId") if target_info else None
                        if target_id:
                            await browser_session.event_bus.dispatch(SwitchTabEvent(target_id=target_id))
                            switched = True
                        break

        if switched:
            msg = f"completed in-browser switch tab to '{url or tab_title_txt}'."
        else:
            msg = f"tab not found matching '{url or tab_title_txt}'."
        result = [TextContent(type="text", text=msg)]
        return result
    except Exception as e:
        err_trace = get_traceback(e, "ErrorInBrowserSwitchTab")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def in_browser_open_tab(mainwin, args):
    try:
        driver_mode = _get_driver_mode(args)
        url = args['input'].get("url", "")
        
        if driver_mode == "webdriver":
            web_driver = _get_webdriver(mainwin)
            if web_driver:
                web_driver.switch_to.window(web_driver.window_handles[0])
                time.sleep(1)
                web_driver.execute_script(f"window.open('{url}', '_blank');")
                # Switch to the new tab
                web_driver.switch_to.window(web_driver.window_handles[-1])
                time.sleep(1)
                if url:
                    web_driver.get(url)
                    logger.info("open URL: " + url)
        else:
            # CDP mode using BrowserSession
            browser_type = args['input'].get("browser_type", "existing chrome")
            browser_session = await _get_browser_session_by_type(mainwin, browser_type)
            if browser_session:
                page = await browser_session.new_page(url)
                logger.info(f'browser_use: opened new tab with URL: {url}')

        msg = f'completed opening tab and go to site: {url}.'
        logger.info(msg)
        result = [TextContent(type="text", text=msg)]
        return result
    except Exception as e:
        err_trace = get_traceback(e, "ErrorInBrowserOpenTab")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def in_browser_go_to_url(mainwin, args):
    """Navigate the current tab to a specified URL."""
    try:
        driver_mode = _get_driver_mode(args)
        url = args['input'].get("url", "")
        
        if not url:
            return [TextContent(type="text", text="Error: url is required")]
        
        if driver_mode == "webdriver":
            web_driver = _get_webdriver(mainwin)
            if web_driver:
                web_driver.get(url)
                logger.info(f"navigated to URL: {url}")
        else:
            # CDP mode using BrowserSession
            browser_type = args['input'].get("browser_type", "existing chrome")
            browser_session = await _get_browser_session_by_type(mainwin, browser_type)
            if browser_session:
                page = await _get_current_page(browser_session)
                if page:
                    await page.goto(url)
                    logger.info(f'browser_use: navigated to URL: {url}')

        msg = f'completed navigating to: {url}.'
        result = [TextContent(type="text", text=msg)]
        return result
    except Exception as e:
        err_trace = get_traceback(e, "ErrorInBrowserGoToUrl")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def in_browser_close_tab(mainwin, args):
    try:
        driver_mode = _get_driver_mode(args)
        tab_title = args['input'].get("tab_title", "")
        closed = False
        
        if driver_mode == "webdriver":
            web_driver = _get_webdriver(mainwin)
            if web_driver:
                if tab_title:
                    for handle in web_driver.window_handles:
                        web_driver.switch_to.window(handle)
                        if tab_title in web_driver.title or tab_title in web_driver.current_url:
                            break
                web_driver.close()
                closed = True
                # Switch to remaining tab if any
                if web_driver.window_handles:
                    web_driver.switch_to.window(web_driver.window_handles[0])
        else:
            # CDP mode using BrowserSession
            browser_type = args['input'].get("browser_type", "existing chrome")
            browser_session = await _get_browser_session_by_type(mainwin, browser_type)
            if browser_session:
                if tab_title:
                    # Find the tab by title/url first
                    pages = await browser_session.get_pages()
                    for page in pages:
                        page_url = await page.get_url()
                        page_title = await page.get_title()
                        if tab_title in page_title or tab_title in page_url:
                            await browser_session.close_page(page)
                            closed = True
                            break
                else:
                    # Close current tab
                    page = await _get_current_page(browser_session)
                    if page:
                        await browser_session.close_page(page)
                        closed = True

        if closed:
            msg = f"completed closing tab '{tab_title or 'current'}'."
        else:
            msg = f"tab not found matching '{tab_title}'."
        result = [TextContent(type="text", text=msg)]
        return result
    except Exception as e:
        err_trace = get_traceback(e, "ErrorInBrowserCloseTab")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]

async def get_page_info(page):
    return (await page.get_title(), await page.get_url(), await page.get_target_info())

# Content Actions
async def in_browser_extract_content(mainwin, args):
    """
    Extract browser content using CDP mode via browser_use.
    Returns DOM state, page info, and interactive elements.
    """
    try:
        # CDP mode only - piggyback on browser_use's rich functionalities
        browser_type = args['input'].get("browser_type", "existing chrome")
        include_screenshot = args['input'].get("include_screenshot", False)
        
        browser_session = await _get_browser_session_by_type(mainwin, browser_type)
        if not browser_session:
            return [TextContent(type="text", text="Error: Could not get browser session")]
        
        # Note: include_screenshot=False by default to avoid CDP timeout issues with existing Chrome
        # instances that have many tabs. Screenshot capture via CDP can hang on complex browser states.
        browser_state_summary = await browser_session.get_browser_state_summary(
            include_screenshot=include_screenshot,
            include_recent_events=True
        )

        # Build serializable state
        serializable_state = {
            "url": browser_state_summary.url,
            "title": browser_state_summary.title,
            "tabs": [tab.model_dump() for tab in browser_state_summary.tabs],
            "screenshot": browser_state_summary.screenshot,  # base64 string or None
            "dom_text": browser_state_summary.dom_state.llm_representation(),
            "interactive_elements": list(browser_state_summary.dom_state.selector_map.keys()),
        }

        msg = f"completed extracting browser content from '{browser_state_summary.title}'."
        result = TextContent(type="text", text=msg)
        result.meta = {"browser_state": serializable_state}
        return [result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorInBrowserExtractContent")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


def execute_js_script(web_driver, script, target=None):
    """Execute JavaScript in the browser.
    
    Args:
        web_driver: Selenium WebDriver instance
        script: JavaScript code to execute
        target: Optional target element (CSS selector string or WebElement)
    
    Returns:
        Result of the JavaScript execution
    """
    if target:
        # If target is a string, find the element first
        if isinstance(target, str):
            element = web_driver.find_element(By.CSS_SELECTOR, target)
        else:
            element = target
        return web_driver.execute_script(script, element)
    else:
        return web_driver.execute_script(script)


async def in_browser_execute_javascript(mainwin, args):
    try:
        driver_mode = _get_driver_mode(args)
        script = args['input'].get("script", "")
        target = args['input'].get("target", None)
        
        js_result = None
        if driver_mode == "webdriver":
            web_driver = _get_webdriver(mainwin)
            if web_driver:
                js_result = execute_js_script(web_driver, script, target)
        else:
            # CDP mode using BrowserSession
            browser_type = args['input'].get("browser_type", "existing chrome")
            browser_session = await _get_browser_session_by_type(mainwin, browser_type)
            if browser_session:
                page = await _get_current_page(browser_session)
                if page:
                    # Wrap script in arrow function if not already
                    if not script.strip().startswith("("):
                        script = f"() => {{ {script} }}"
                    js_result = await page.evaluate(script)

        msg = f"completed in browser execute javascript."
        tool_result = TextContent(type="text", text=msg)
        tool_result.meta = {"result": js_result}
        return [tool_result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorInBrowserExecuteJavascript")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]



def webDriverDownloadFile(web_driver, ele_type, ele_text, dl_dir, dl_file):
    """Download a file by finding an element with href and saving its content.
    
    Args:
        web_driver: Selenium WebDriver instance
        ele_type: Element type to search for (e.g., 'a', 'link', 'button')
        ele_text: Text content to match in the element
        dl_dir: Directory to save the file
        dl_file: Filename to save as
    
    Returns:
        Full path of the saved file
    """
    import requests
    import os
    
    # Find element by type and text
    elements = web_driver.find_elements(By.TAG_NAME, ele_type)
    target_element = None
    
    for elem in elements:
        if ele_text in elem.text or ele_text in elem.get_attribute('innerHTML'):
            target_element = elem
            break
    
    if not target_element:
        raise ValueError(f"Element with type '{ele_type}' and text '{ele_text}' not found")
    
    # Get the href attribute
    href = target_element.get_attribute('href')
    if not href:
        # Try onclick or data attributes
        href = target_element.get_attribute('data-href') or target_element.get_attribute('data-url')
    
    if not href:
        raise ValueError(f"No href found on element with text '{ele_text}'")
    
    # Ensure download directory exists
    os.makedirs(dl_dir, exist_ok=True)
    
    # Get cookies from webdriver for authenticated downloads
    cookies = {cookie['name']: cookie['value'] for cookie in web_driver.get_cookies()}
    
    # Download the file
    response = requests.get(href, cookies=cookies, stream=True)
    response.raise_for_status()
    
    # Save to file
    file_path = os.path.join(dl_dir, dl_file)
    with open(file_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
    
    return file_path


async def cdp_download_file(browser_session, page, href, saved_file_path):
    """Download a file using CDP session and aiohttp.
    
    Args:
        browser_session: BrowserSession instance
        page: Current page
        href: URL to download
        saved_file_path: Full path to save the file
    
    Returns:
        Full path of the saved file
    """
    import aiohttp
    
    # Get cookies from the browser via JavaScript
    cookies_js = '() => document.cookie'
    cookie_string = await page.evaluate(cookies_js)
    
    # Parse cookie string into dict
    cookie_dict = {}
    if cookie_string:
        for item in cookie_string.split(';'):
            item = item.strip()
            if '=' in item:
                key, value = item.split('=', 1)
                cookie_dict[key.strip()] = value.strip()
    
    # Ensure download directory exists
    dl_dir = os.path.dirname(saved_file_path)
    if dl_dir:
        os.makedirs(dl_dir, exist_ok=True)
    
    # Download using aiohttp
    async with aiohttp.ClientSession() as session:
        # Set cookies in the request
        async with session.get(href, cookies=cookie_dict) as response:
            response.raise_for_status()
            with open(saved_file_path, 'wb') as f:
                async for chunk in response.content.iter_chunked(8192):
                    f.write(chunk)
    
    return saved_file_path


# File Download
async def in_browser_save_href_to_file(mainwin, args) -> CallToolResult:
    """Download a file from a URL (href) and save it to a specified path."""
    try:
        driver_mode = _get_driver_mode(args)
        href = args["input"].get("href", "")
        saved_file_path = args["input"].get("saved_file_path", "")
        
        if not href:
            return [TextContent(type="text", text="Error: href is required")]
        if not saved_file_path:
            return [TextContent(type="text", text="Error: saved_file_path is required")]
        
        if driver_mode == "webdriver":
            web_driver = _get_webdriver(mainwin)
            if web_driver:
                import requests
                
                # Get cookies from webdriver for authenticated downloads
                cookies = {cookie['name']: cookie['value'] for cookie in web_driver.get_cookies()}
                
                # Ensure download directory exists
                dl_dir = os.path.dirname(saved_file_path)
                if dl_dir:
                    os.makedirs(dl_dir, exist_ok=True)
                
                # Download the file
                response = requests.get(href, cookies=cookies, stream=True)
                response.raise_for_status()
                
                # Save to file
                with open(saved_file_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
        else:
            # CDP mode using BrowserSession
            browser_type = args['input'].get("browser_type", "existing chrome")
            browser_session = await _get_browser_session_by_type(mainwin, browser_type)
            if browser_session:
                page = await _get_current_page(browser_session)
                if page:
                    await cdp_download_file(browser_session, page, href, saved_file_path)

        msg = f"completed downloading file to {saved_file_path}."
        tool_result = [TextContent(type="text", text=msg)]
        return tool_result
    except Exception as e:
        err_trace = get_traceback(e, "ErrorInBrowserSaveHrefToFile")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def in_browser_upload_file(mainwin, args) -> CallToolResult:
    """Upload a file to a file input element on the page."""
    try:
        driver_mode = _get_driver_mode(args)
        file_input_selector = args["input"].get("file_input_selector", "")
        upload_file_path = args["input"].get("upload_file_path", "")
        
        if not upload_file_path:
            return [TextContent(type="text", text="Error: upload_file_path is required")]
        
        # Verify file exists
        if not os.path.exists(upload_file_path):
            return [TextContent(type="text", text=f"Error: file not found: {upload_file_path}")]
        
        uploaded = False
        if driver_mode == "webdriver":
            web_driver = _get_webdriver(mainwin)
            if web_driver:
                # Find file input element
                if file_input_selector:
                    file_input = web_driver.find_element(By.CSS_SELECTOR, file_input_selector)
                else:
                    # Try to find any file input
                    file_input = web_driver.find_element(By.CSS_SELECTOR, "input[type='file']")
                
                if file_input:
                    # Send the file path to the input element
                    file_input.send_keys(upload_file_path)
                    uploaded = True
        else:
            # CDP mode using BrowserSession
            browser_type = args['input'].get("browser_type", "existing chrome")
            browser_session = await _get_browser_session_by_type(mainwin, browser_type)
            if browser_session:
                page = await _get_current_page(browser_session)
                if page:
                    # Use JavaScript to set file on input element via CDP
                    selector = file_input_selector if file_input_selector else "input[type='file']"
                    elements = await page.get_elements_by_css_selector(selector)
                    if elements:
                        # Get the backend node id for the file input
                        file_input_element = elements[0]
                        # Use CDP DOM.setFileInputFiles to set the file
                        session_id = await page.session_id
                        # Get node id from backend node id
                        node_id = await file_input_element._get_node_id()
                        await browser_session.cdp_client.send.DOM.setFileInputFiles(
                            params={
                                'files': [upload_file_path],
                                'nodeId': node_id
                            },
                            session_id=session_id
                        )
                        uploaded = True

        if uploaded:
            msg = f"completed uploading file: {upload_file_path}."
        else:
            msg = f"failed to upload file: {upload_file_path}."
        tool_result = [TextContent(type="text", text=msg)]
        return tool_result
    except Exception as e:
        err_trace = get_traceback(e, "ErrorInBrowserUploadFile")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def in_browser_scroll(mainwin, args):
    try:
        driver_mode = _get_driver_mode(args)
        direction = args["input"].get("direction", "down").lower()
        amount = args["input"].get("amount", 300)
        post_wait = args["input"].get("post_wait", 0)
        
        # Calculate scroll amount (negative for down in CDP)
        scroll_y = -amount if direction == "down" else amount
        
        if driver_mode == "webdriver":
            web_driver = _get_webdriver(mainwin)
            if web_driver:
                js_amount = amount if direction == "down" else -amount
                web_driver.execute_script(f"window.scrollBy(0, {js_amount});")
                if post_wait:
                    time.sleep(post_wait)
        else:
            # CDP mode using BrowserSession
            browser_type = args['input'].get("browser_type", "existing chrome")
            browser_session = await _get_browser_session_by_type(mainwin, browser_type)
            if browser_session:
                page = await _get_current_page(browser_session)
                if page:
                    mouse = await page.mouse
                    await mouse.scroll(x=0, y=0, delta_x=0, delta_y=scroll_y)
                    if post_wait:
                        await asyncio.sleep(post_wait)

        msg = f"completed in browser scroll {direction} {amount}."
        tool_result = [TextContent(type="text", text=msg)]
        return tool_result
    except Exception as e:
        err_trace = get_traceback(e, "ErrorInBrowserScrollDown")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]

# send keys
async def in_browser_send_keys(mainwin, args):
    try:
        driver_mode = _get_driver_mode(args)
        keys = args['input'].get('keys', '')
        
        if driver_mode == "webdriver":
            web_driver = _get_webdriver(mainwin)
            if web_driver:
                # Send keys to active element
                from selenium.webdriver.common.action_chains import ActionChains
                actions = ActionChains(web_driver)
                actions.send_keys(keys).perform()
        else:
            # CDP mode using BrowserSession
            browser_type = args['input'].get("browser_type", "existing chrome")
            browser_session = await _get_browser_session_by_type(mainwin, browser_type)
            if browser_session:
                page = await _get_current_page(browser_session)
                if page:
                    await page.press(keys)

        msg = f'⌨️  Sent keys: {keys}'
        logger.info(msg)
        tool_result = [TextContent(type="text", text=msg)]
        return tool_result
    except Exception as e:
        err_trace = get_traceback(e, "ErrorInBrowserSendKeys")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def in_browser_scroll_to_text(mainwin, args):  # type: ignore
    try:
        driver_mode = _get_driver_mode(args)
        text = args['input'].get('text', '')
        
        if driver_mode == "webdriver":
            web_driver = _get_webdriver(mainwin)
            if web_driver:
                escaped_text = text.replace("'", "\\'")
                element = web_driver.find_element("xpath", f"//*[contains(text(), '{escaped_text}')]")
                # Scroll to the element
                web_driver.execute_script("arguments[0].scrollIntoView({block: 'center', behavior: 'smooth'});", element)
        else:
            # CDP mode using BrowserSession
            browser_type = args['input'].get("browser_type", "existing chrome")
            browser_session = await _get_browser_session_by_type(mainwin, browser_type)
            if browser_session:
                page = await _get_current_page(browser_session)
                if page:
                    # Use JS to find and scroll to text
                    escaped_text = text.replace('"', '\\"')
                    js_code = f'() => {{ const xpath = "//*[contains(text(), \"{escaped_text}\")]"; const result = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null); const elem = result.singleNodeValue; if (elem) elem.scrollIntoView({{block: "center", behavior: "smooth"}}); return elem ? "scrolled" : "not found"; }}'
                    await page.evaluate(js_code)

        msg = f"completed in browser scroll to text '{text}'."
        tool_result = [TextContent(type="text", text=msg)]
        return tool_result
    except Exception as e:
        err_trace = get_traceback(e, "ErrorInBrowserScrollToText")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def in_browser_get_dropdown_options(mainwin, args) -> CallToolResult:
    try:
        driver_mode = _get_driver_mode(args)
        selector = args['input'].get('selector', '')
        options = []
        
        if driver_mode == "webdriver":
            web_driver = _get_webdriver(mainwin)
            if web_driver:
                select_element = web_driver.find_element(By.CSS_SELECTOR, selector)
                select = Select(select_element)
                options = [opt.text for opt in select.options]
        else:
            # CDP mode using BrowserSession
            browser_type = args['input'].get("browser_type", "existing chrome")
            browser_session = await _get_browser_session_by_type(mainwin, browser_type)
            if browser_session:
                page = await _get_current_page(browser_session)
                if page:
                    # Use JavaScript to get option text content reliably
                    escaped_selector = selector.replace('"', '\\"')
                    js_code = f'() => {{ const select = document.querySelector("{escaped_selector}"); if (!select) return []; return Array.from(select.options).map(opt => ({{ text: opt.textContent.trim(), value: opt.value }})); }}'
                    result = await page.evaluate(js_code)
                    if result:
                        import json
                        option_list = json.loads(result) if isinstance(result, str) else result
                        options = [opt.get("text", "") for opt in option_list]

        msg = f"completed getting dropdown options: {options}."
        tool_result = TextContent(type="text", text=msg)
        tool_result.meta = {"options": options}
        return [tool_result]

    except Exception as e:
        err_trace = get_traceback(e, "ErrorInBrowserGetDropdownOptions")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def in_browser_select_dropdown_option(mainwin, args) -> CallToolResult:
    try:
        driver_mode = _get_driver_mode(args)
        selector = args['input'].get('selector', '')
        option_value = args['input'].get('option_value', '')
        option_text = args['input'].get('option_text', '')
        option_index = args['input'].get('option_index', None)
        selected = False
        
        if driver_mode == "webdriver":
            web_driver = _get_webdriver(mainwin)
            if web_driver:
                select_element = web_driver.find_element(By.CSS_SELECTOR, selector)
                select = Select(select_element)
                if option_value:
                    select.select_by_value(option_value)
                    selected = True
                elif option_text:
                    select.select_by_visible_text(option_text)
                    selected = True
                elif option_index is not None:
                    select.select_by_index(option_index)
                    selected = True
        else:
            # CDP mode using BrowserSession
            browser_type = args['input'].get("browser_type", "existing chrome")
            browser_session = await _get_browser_session_by_type(mainwin, browser_type)
            if browser_session:
                page = await _get_current_page(browser_session)
                if page:
                    # browser_use element.select_option takes values: str | list[str]
                    # Use JavaScript for more reliable selection with value/text/index support
                    escaped_selector = selector.replace('"', '\\"')
                    if option_value:
                        escaped_value = option_value.replace('"', '\\"')
                        js_code = f'() => {{ const select = document.querySelector("{escaped_selector}"); if (select) {{ select.value = "{escaped_value}"; select.dispatchEvent(new Event("change", {{ bubbles: true }})); return true; }} return false; }}'
                    elif option_text:
                        escaped_text = option_text.replace('"', '\\"')
                        js_code = f'() => {{ const select = document.querySelector("{escaped_selector}"); if (select) {{ for (const opt of select.options) {{ if (opt.textContent.trim() === "{escaped_text}") {{ select.value = opt.value; select.dispatchEvent(new Event("change", {{ bubbles: true }})); return true; }} }} }} return false; }}'
                    elif option_index is not None:
                        js_code = f'() => {{ const select = document.querySelector("{escaped_selector}"); if (select && select.options[{option_index}]) {{ select.selectedIndex = {option_index}; select.dispatchEvent(new Event("change", {{ bubbles: true }})); return true; }} return false; }}'
                    else:
                        js_code = '() => false'
                    
                    result = await page.evaluate(js_code)
                    selected = result == "true" or result is True

        if selected:
            msg = f"completed selecting dropdown option."
        else:
            msg = f"failed to select dropdown option (selector: {selector})."
        tool_result = [TextContent(type="text", text=msg)]
        return tool_result
    except Exception as e:
        err_trace = get_traceback(e, "ErrorInBrowserSelectDropdownOption")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def in_browser_drag_drop(mainwin, args) -> CallToolResult:
    """
    Drag and drop operation supporting both element-based (CSS selectors) and coordinate-based modes.
    
    Element-based: Use source_selector and target_selector to drag from one element to another.
    Coordinate-based: Use source_x/source_y and target_x/target_y for precise coordinate control.
    """
    try:
        driver_mode = _get_driver_mode(args)
        # Element-based parameters
        source_selector = args["input"].get("source_selector", "")
        target_selector = args["input"].get("target_selector", "")
        # Coordinate-based parameters
        source_x = args["input"].get("source_x", None)
        source_y = args["input"].get("source_y", None)
        target_x = args["input"].get("target_x", None)
        target_y = args["input"].get("target_y", None)
        
        # Determine mode: element-based or coordinate-based
        use_element_mode = bool(source_selector)
        
        if driver_mode == "webdriver":
            web_driver = _get_webdriver(mainwin)
            if web_driver:
                from selenium.webdriver.common.action_chains import ActionChains
                actions = ActionChains(web_driver)
                
                if use_element_mode:
                    # Element-based drag and drop
                    source_element = web_driver.find_element(By.CSS_SELECTOR, source_selector)
                    if target_selector:
                        target_element = web_driver.find_element(By.CSS_SELECTOR, target_selector)
                        actions.drag_and_drop(source_element, target_element).perform()
                    elif target_x is not None and target_y is not None:
                        # Drag element to coordinates
                        actions.click_and_hold(source_element)
                        actions.move_by_offset(target_x, target_y)
                        actions.release()
                        actions.perform()
                else:
                    # Coordinate-based drag and drop
                    if source_x is not None and source_y is not None:
                        actions.move_by_offset(source_x, source_y)
                        actions.click_and_hold()
                        if target_x is not None and target_y is not None:
                            actions.move_by_offset(target_x - source_x, target_y - source_y)
                        actions.release()
                        actions.perform()
        else:
            # CDP mode using BrowserSession
            browser_type = args['input'].get("browser_type", "existing chrome")
            browser_session = await _get_browser_session_by_type(mainwin, browser_type)
            if browser_session:
                page = await _get_current_page(browser_session)
                if page:
                    if use_element_mode:
                        # Element-based drag and drop using element.drag_to()
                        source_elements = await page.get_elements_by_css_selector(source_selector)
                        if source_elements:
                            source_element = source_elements[0]
                            if target_selector:
                                # Drag to target element
                                target_elements = await page.get_elements_by_css_selector(target_selector)
                                if target_elements:
                                    await source_element.drag_to(target_elements[0])
                            elif target_x is not None and target_y is not None:
                                # Drag to coordinates using Position dict
                                await source_element.drag_to({"x": target_x, "y": target_y})
                    else:
                        # Coordinate-based drag and drop using mouse operations
                        if source_x is not None and source_y is not None:
                            mouse = await page.mouse
                            await mouse.move(source_x, source_y)
                            await mouse.down()
                            if target_x is not None and target_y is not None:
                                await mouse.move(target_x, target_y)
                            await mouse.up()

        # Build result message
        if use_element_mode:
            msg = f'🖱️ Dragged from "{source_selector}" to "{target_selector or f"({target_x}, {target_y})"}"'
        else:
            msg = f'🖱️ Dragged from ({source_x}, {source_y}) to ({target_x}, {target_y})'
        logger.info(msg)
        return [TextContent(type="text", text=msg)]

    except Exception as e:
        err_trace = get_traceback(e, "ErrorInBrowserDragDrop")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]

async def in_browser_multi_actions(mainwin, args):
    try:
        crawler = mainwin.getWebCrawler()
        if not crawler:
            web_driver = mainwin.getWebDriver()
        else:
            actions = args["input"]["actions"]

            def fill_parametric_cards(driver, filled_json):
                # Get all cards again
                cards = driver.find_elements(By.CSS_SELECTOR, 'div.div-card')

                for card in cards:
                    # Get card title
                    try:
                        title = card.find_element(By.CSS_SELECTOR, '.tss-css-oy50zv-cardHeader').text.strip()
                    except Exception:
                        continue
                    if title not in filled_json:
                        continue
                    card_data = filled_json[title]

                    # --- Range input handling ---
                    min_inputs = card.find_elements(By.CSS_SELECTOR, 'input[data-filter-type="min"]')
                    max_inputs = card.find_elements(By.CSS_SELECTOR, 'input[data-filter-type="max"]')
                    select_units = card.find_elements(By.CSS_SELECTOR, 'select[data-filter-type="unit"]')

                    if min_inputs or max_inputs:
                        # Fill min/max values
                        if min_inputs and "min_value" in card_data:
                            min_input = min_inputs[0]
                            min_input.clear()
                            min_input.send_keys(str(card_data["min_value"]))
                        if max_inputs and "max_value" in card_data:
                            max_input = max_inputs[0]
                            max_input.clear()
                            max_input.send_keys(str(card_data["max_value"]))
                        # Select unit
                        if select_units and "unit_value" in card_data:
                            select = Select(select_units[0])
                            select.select_by_visible_text(card_data["unit_value"])
                        continue

                    # --- Options handling (checkboxes, radio) ---
                    # options can be a single value or a list
                    selected_options = card_data.get("options", [])
                    if isinstance(selected_options, str):
                        selected_options = [selected_options]

                    # Check all <label> with matching text or data-testid
                    for option in selected_options:
                        # Look for option by label's text or inner <span>
                        found = False
                        for label in card.find_elements(By.CSS_SELECTOR, "label"):
                            label_text = label.text.strip()
                            # Try direct match or in nested span with data-testid
                            if option == label_text:
                                # Click the checkbox/radio
                                try:
                                    # The clickable part is often the first <span> inside the label
                                    span_checkbox = label.find_element(By.CSS_SELECTOR,
                                                                       "span[role=checkbox],span.MuiButtonBase-root")
                                    driver.execute_script("arguments[0].scrollIntoView();", span_checkbox)
                                    if not span_checkbox.is_selected():
                                        span_checkbox.click()
                                    found = True
                                    break
                                except Exception:
                                    # fallback: click the whole label
                                    label.click()
                                    found = True
                                    break
                            # Sometimes the label has a <span> with data-testid containing the option text
                            try:
                                inner_spans = label.find_elements(By.CSS_SELECTOR, 'span[data-testid]')
                                for span in inner_spans:
                                    if option == span.text.strip():
                                        driver.execute_script("arguments[0].scrollIntoView();", span)
                                        span.click()
                                        found = True
                                        break
                                if found:
                                    break
                            except Exception:
                                continue
                        if not found:
                            logger.warning(f"Could not find and select option '{option}' for '{title}'")

                logger.info("All filters filled!")
                return("completed fill parametric cards")

        msg = "completed filling empty actions."
        if actions:
            msg =fill_parametric_cards(web_driver, actions)

        result = [TextContent(type="text", text=msg)]

        return result

    except Exception as e:
        err_trace = get_traceback(e, "ErrorInBrowserMultiCardAction")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]

async def mouse_click(mainwin, args):
    try:
        logger.debug(f"MOUSE CLICKINPUT: {args}")

        pyautogui.moveTo(args["input"]["loc"][0], args["input"]["loc"][1])
        time.sleep(args["input"]["post_move_delay"])
        pyautogui.click(clicks=2, interval=0.3)
        time.sleep(args["input"]["post_click_delay"])

        msg = "completed mouse click"
        result = [TextContent(type="text", text=msg)]

        return [result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorMouseClick")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def mouse_press_hold(mainwin, args):
    try:
        logger.debug(f"MOUSE CLICKINPUT: {args}")
        press_time = args["input"]["press_time"]
        pyautogui.moveTo(args["input"]["loc"][0], args["input"]["loc"][1])
        time.sleep(args["input"]["post_move_delay"])
        pyautogui.mouseDown()
        time.sleep(press_time)
        pyautogui.mouseUp()
        time.sleep(args["input"]["post_delay"])

        msg = "completed mouse press and hold"
        result = [TextContent(type="text", text=msg)]

        return [result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorMousePressHold")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def mouse_move(mainwin, args):
    try:
        logger.debug(f"MOUSE HOVER INPUT: {args}")
        pyautogui.moveTo(args["input"]["loc"][0], args["input"]["loc"][1])
        # ctr = CallToolResult(content=[TextContent(type="text", text=msg)], _meta=workable, isError=False)
        time.sleep(args["input"]["post_delay"])

        msg = "completed mouse move"
        result = [TextContent(type="text", text=msg)]
        return result

    except Exception as e:
        err_trace = get_traceback(e, "ErrorMouseMove")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]

async def mouse_drag_drop(mainwin, args):
    try:
        pyautogui.moveTo(args["input"]["pick_loc"][0], args["input"]["pick_loc"][1])
        pyautogui.dragTo(args["input"]["drop_loc"][0], args["input"]["drop_loc"][1], duration=args["input"]["duration"])

        logger.debug(f'dragNdrop: {args["input"]["pick_loc"][0]}, {args["input"]["pick_loc"][1]} to {args["input"]["drop_loc"][0]}, {args["input"]["drop_loc"][1]}')
        msg = "completed mouse drag and drop"
        result = [TextContent(type="text", text=msg)]
        return [result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorMouseDragDrop")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]

async def mouse_scroll(mainwin, args):
    try:
        if args["input"]["direction"] == "down":
            scroll_amount = 0 - args["input"]["amount"]
        else:
            scroll_amount = args["input"]["amount"]
        mouse.scroll(0, scroll_amount)

        msg = "completed mouse scroll"
        result = [TextContent(type="text", text=msg)]
        return [result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorMouseScroll")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]



async def mouse_act_on_screen(mainwin, args):
    from agent.ec_skills.ocr.post_ocr import mousePressAndHoldOnScreenWord
    try:
        screen_data = args["input"]["screen_data"]
        action = args["input"]["action"]
        target = args["input"]["target"]
        target_params = args["input"]["target_params"]
        action_params = args["input"]["action_params"]

        if action == "click":
            time.sleep(args["input"].get("post_move_delay",1))
            mousePressAndHoldOnScreenWord(screen_data, target, duration=0, nth=0)
        elif action == "press_hold":
            time.sleep(args["input"].get("post_move_delay", 1))
            mousePressAndHoldOnScreenWord(screen_data, target, duration= 12, nth=0)

        time.sleep(args["input"].get("post_delay", 0))
        msg = "completed action on screen."
        result = [TextContent(type="text", text=msg)]
        return [result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorMouseActOnScreen")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def keyboard_text_input(mainwin, args):
    try:
        pyautogui.write(args["input"]["text"], interval=args["input"]["interval"])

        if args['input']["post_wait"]:
            time.sleep(args['input']["post_wait"])

        msg = "completed text input"
        result = [TextContent(type="text", text=msg)]
        return [result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorKeyboardTextInput")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]

async def keyboard_keys_input(mainwin, args):
    try:
        pyautogui.hotkey(*args["input"]["keys"])

        if args['input']["post_wait"]:
            time.sleep(args['input']["post_wait"])

        msg = "completed keys press"
        result = [TextContent(type="text", text=msg)]
        return [result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorKeyboardKeysInput")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]

async def http_call_api(mainwin, args):
    try:

        msg = "completed calling API"
        result = [TextContent(type="text", text=msg)]
        return [result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorHttpCallApi")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


def page_scroll(web_driver, mainwin):
    try:
        if mainwin:
            js_file_dir = os.path.dirname(mainwin.build_dom_tree_script_path)
        else:
            js_file_dir = "c:/users/songc/pycharmprojects/ecbot/agent/ec_skills/dom"
        auto_scroll_file_path = os.path.join(js_file_dir, "auto_scroll.js")
        with open(auto_scroll_file_path, 'r') as f:
            scrolling_functions_js = f.read()
    except FileNotFoundError:
        logger.error("Error: auto_scroll.js not found. Please check the path.")
        # Handle error appropriately
        exit()

    # 2. To scroll DOWN, append the call to scrollToPageBottom()
    logger.debug("Starting full page scroll-down...")
    scroll_down_command = scrolling_functions_js + "\nvar cb = arguments[arguments.length - 1]; scrollToPageBottom(cb);"
    down_scroll_count = web_driver.execute_async_script(scroll_down_command)
    logger.debug(f"Page fully scrolled down in {down_scroll_count} steps.")

    time.sleep(1)  # A brief pause

    # 3. To scroll UP, append the call to scrollToPageTop() and pass arguments
    logger.debug("Scrolling back to the top of the page...")
    scroll_up_command = scrolling_functions_js + "\nvar cb = arguments[arguments.length - 1]; scrollToPageTop(arguments[0], arguments[1], cb);"
    # The arguments for the JS function are passed after the script string
    up_scroll_count = web_driver.execute_async_script(scroll_up_command, down_scroll_count, 600)
    logger.debug(f"Scrolled back to top in {up_scroll_count} steps.")

    # Now the page is ready for your buildDomTree.js script
    logger.debug("Page is ready for DOM analysis.")



async def os_connect_to_adspower(mainwin, args):
    """
    Connect to AdsPower browser via BrowserManager.
    Creates both WebDriver and BrowserSession connections.
    """
    from gui.manager.browser_manager import BrowserManager, BrowserType, BrowserStatus
    
    logger.debug(f"[os_connect_to_adspower] args: {args}")
    try:
        url = args['input'].get("url")
        browser_id = ""
        
        # Get or create BrowserManager
        if not hasattr(mainwin, 'browser_manager') or mainwin.browser_manager is None:
            mainwin.browser_manager = BrowserManager(default_webdriver_path=mainwin.getWebDriverPath())
        
        browser_manager: BrowserManager = mainwin.browser_manager
        
        # Try to find existing AdsPower browser or create new one
        auto_browser = browser_manager.acquire_browser(
            agent_id=getattr(mainwin, 'current_agent_id', 'default_agent'),
            task=f"connect_to_adspower: {url}",
            browser_type=BrowserType.ADSPOWER,
            webdriver_path=mainwin.getWebDriverPath(),
        )
        
        if auto_browser and auto_browser.status != BrowserStatus.ERROR:
            browser_id = auto_browser.id
            
            # Set webdriver on mainwin for backward compatibility
            if auto_browser.webdriver:
                mainwin.setWebDriver(auto_browser.webdriver)
                page_scroll(mainwin, auto_browser.webdriver)
            
            # Start browser session if not already started
            if auto_browser.browser_session:
                logger.info(f"[os_connect_to_adspower] Starting browser session: {auto_browser.browser_session.id}")
                await auto_browser.browser_session.start()
                logger.info(f"[os_connect_to_adspower] Browser session started!")
            
            # Navigate to URL if provided
            if url and auto_browser.webdriver:
                auto_browser.webdriver.get(url)
                time.sleep(1)
            
            msg = f"completed connect to adspower. browser_id={browser_id}"
        else:
            mainwin.setWebDriver(None)
            error_msg = auto_browser.last_error if auto_browser else "Unknown error"
            msg = f"failed connect to adspower: {error_msg}"

        result = TextContent(type="text", text=msg)
        result.meta = {"browser_id": browser_id}
        return [result]

    except Exception as e:
        err_trace = get_traceback(e, "ErrorOSConnectToAdspower")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def os_connect_to_chrome(mainwin, args):
    """
    Connect to existing Chrome browser via BrowserManager.
    Creates both WebDriver and BrowserSession connections.
    """
    from gui.manager.browser_manager import BrowserManager, BrowserType, BrowserStatus
    
    logger.debug(f"[os_connect_to_chrome] args: {args}")
    try:
        url = args["input"].get("url")
        driver_path = args["input"].get("driver_path", mainwin.getWebDriverPath())
        cdp_port = args["input"].get("ads_port", 9228)
        browser_id = ""
        
        # Get or create BrowserManager
        if not hasattr(mainwin, 'browser_manager') or mainwin.browser_manager is None:
            mainwin.browser_manager = BrowserManager(default_webdriver_path=mainwin.getWebDriverPath())
        
        browser_manager: BrowserManager = mainwin.browser_manager
        
        # Try to find existing Chrome browser on same port or create new one
        auto_browser = browser_manager.acquire_browser(
            agent_id=getattr(mainwin, 'current_agent_id', 'default_agent'),
            task=f"connect_to_chrome: {url}",
            browser_type=BrowserType.CHROME,
            cdp_port=cdp_port,
            webdriver_path=driver_path,
        )
        
        if auto_browser and auto_browser.status != BrowserStatus.ERROR:
            browser_id = auto_browser.id
            
            # Set webdriver on mainwin for backward compatibility
            if auto_browser.webdriver:
                mainwin.setWebDriver(auto_browser.webdriver)
                # Switch to the last tab
                auto_browser.webdriver.switch_to.window(auto_browser.webdriver.window_handles[-1])
                time.sleep(1)
            
            # Start browser session if not already started
            if auto_browser.browser_session:
                logger.info(f"[os_connect_to_chrome] Starting browser session: {auto_browser.browser_session.id}")
                await auto_browser.browser_session.start()
                logger.info(f"[os_connect_to_chrome] Browser session started!")
            
            # Navigate to URL if provided
            if url and auto_browser.webdriver:
                auto_browser.webdriver.get(url)
                time.sleep(1)
            
            msg = f"completed connect to chrome. browser_id={browser_id}"
        else:
            mainwin.setWebDriver(None)
            error_msg = auto_browser.last_error if auto_browser else "Unknown error"
            msg = f"failed connect to chrome: {error_msg}"

        result = TextContent(type="text", text=msg)
        result.meta = {"browser_id": browser_id}
        return [result]

    except Exception as e:
        err_trace = get_traceback(e, "ErrorOSConnectToChrome")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]



async def ecan_ai_new_chromiunm(mainwin, args):
    """
    Launch/connect to a new Chromium browser instance via BrowserManager.
    Creates both WebDriver and BrowserSession connections.
    """
    from gui.manager.browser_manager import BrowserManager, BrowserType, BrowserStatus
    
    logger.debug(f"[ecan_ai_new_chromiunm] args: {args}")
    try:
        driver_path = args["input"].get("driver_path", mainwin.getWebDriverPath())
        url = args["input"].get("url")
        cdp_port = args["input"].get("port", 9228)
        profile = args["input"].get("profile")
        browser_id = ""
        
        # Get or create BrowserManager
        if not hasattr(mainwin, 'browser_manager') or mainwin.browser_manager is None:
            mainwin.browser_manager = BrowserManager(default_webdriver_path=mainwin.getWebDriverPath())
        
        browser_manager: BrowserManager = mainwin.browser_manager
        
        # Create new Chromium browser (always create new, don't reuse)
        auto_browser = browser_manager.create_browser(
            browser_type=BrowserType.CHROMIUM,
            cdp_port=cdp_port,
            webdriver_path=driver_path,
            profile=profile,
            connect_webdriver=True,
            connect_browser_session=True,
        )
        
        if auto_browser and auto_browser.status != BrowserStatus.ERROR:
            browser_id = auto_browser.id
            
            # Mark as in use
            auto_browser.mark_in_use(
                agent_id=getattr(mainwin, 'current_agent_id', 'default_agent'),
                task=f"new_chromium: {url}"
            )
            
            # Set webdriver on mainwin for backward compatibility
            if auto_browser.webdriver:
                mainwin.setWebDriver(auto_browser.webdriver)
                # Switch to the last tab
                auto_browser.webdriver.switch_to.window(auto_browser.webdriver.window_handles[-1])
                time.sleep(1)
            
            # Start browser session if available
            if auto_browser.browser_session:
                logger.info(f"[ecan_ai_new_chromiunm] Starting browser session: {auto_browser.browser_session.id}")
                await auto_browser.browser_session.start()
                logger.info(f"[ecan_ai_new_chromiunm] Browser session started!")
            
            # Navigate to URL if provided
            if url and auto_browser.webdriver:
                auto_browser.webdriver.get(url)
                time.sleep(1)
            
            msg = f"completed launch chromium. browser_id={browser_id}"
        else:
            mainwin.setWebDriver(None)
            error_msg = auto_browser.last_error if auto_browser else "Unknown error"
            msg = f"failed launch chromium: {error_msg}"

        result = TextContent(type="text", text=msg)
        result.meta = {"browser_id": browser_id}
        return [result]

    except Exception as e:
        err_trace = get_traceback(e, "ErrorEcanAiNewChromium")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]



async def os_open_app(mainwin, args):
    try:
        # 将应用名称转换为列表格式以避免 shell=True
        app_cmd = args["input"]["app_name"]
        if isinstance(app_cmd, str):
            app_cmd = [app_cmd]
        
        # Use subprocess helper to prevent console window popup in frozen environment
        from utils.subprocess_helper import popen_no_window
        popen_no_window(app_cmd, close_fds=True,
                       stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE)

        msg = "completed opening app"
        result = [TextContent(type="text", text=msg)]
        return result

    except Exception as e:
        err_trace = get_traceback(e, "ErrorOSOpenApp")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def os_close_app(mainwin, args):
    try:
        app_window = gw.getWindowsWithTitle(args["input"]["win_title"])[0]
        app_window.close()

        msg = "completed closing app"
        result = [TextContent(type="text", text=msg)]
        return result
    except Exception as e:
        err_trace = get_traceback(e, "ErrorOSCloseApp")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]

async def os_switch_to_app(mainwin, args):
    try:
        target_window = gw.getWindowsWithTitle(args["input"]["win_title"])[0]

        # Activate the window (bring it to front)
        target_window.activate()

        msg = "completed switching to app"
        result = [TextContent(type="text", text=msg)]
        return result
    except Exception as e:
        err_trace = get_traceback(e, "ErrorOSSwitchToApp")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def python_run_extern(mainwin, args):
    try:
        if args["input"]["code"]:
            ext_py_code = args["input"]["code"]
            exec(ext_py_code)

        msg = "completed python run extern"
        result = [TextContent(type="text", text=msg)]
        return result
    except Exception as e:
        err_trace = get_traceback(e, "ErrorPythonRunExtern")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]

async def os_list_dir(mainwin, args):
    """List files and directories in a given path with optional pattern filtering."""
    try:
        import glob
        dir_path = args["input"]["dir_path"]
        pattern = args["input"].get("pattern", "*")
        recursive = args["input"].get("recursive", False)
        
        if not os.path.exists(dir_path):
            return [TextContent(type="text", text=f"Error: Directory '{dir_path}' does not exist")]
        
        if not os.path.isdir(dir_path):
            return [TextContent(type="text", text=f"Error: '{dir_path}' is not a directory")]
        
        # Build the search pattern
        if recursive:
            search_pattern = os.path.join(dir_path, "**", pattern)
            files = glob.glob(search_pattern, recursive=True)
        else:
            search_pattern = os.path.join(dir_path, pattern)
            files = glob.glob(search_pattern)
        
        # Get relative paths and sort
        result_files = []
        for f in sorted(files):
            rel_path = os.path.relpath(f, dir_path)
            is_dir = os.path.isdir(f)
            result_files.append({
                "name": rel_path,
                "is_dir": is_dir,
                "full_path": f
            })
        
        import json
        result_json = json.dumps({
            "dir_path": dir_path,
            "pattern": pattern,
            "recursive": recursive,
            "count": len(result_files),
            "files": result_files
        }, indent=2)
        
        return [TextContent(type="text", text=result_json)]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorOSListDir")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def os_make_dir(mainwin, args):
    try:
        if not os.path.exists(args["input"]["dir_path"]):
            # create only if the dir doesn't exist
            os.makedirs(args["input"]["dir_path"])

        msg = "completed making dir"
        result = [TextContent(type="text", text=msg)]
        return result
    except Exception as e:
        err_trace = get_traceback(e, "ErrorOSMakeDir")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def os_delete_dir(mainwin, args):
    try:
        if os.path.exists(args["input"]["dir_path"]):
            # create only if the dir doesn't exist
            os.remove(args["input"]["dir_path"])

        msg = "completed deleting dir"
        result = [TextContent(type="text", text=msg)]
        return result
    except Exception as e:
        err_trace = get_traceback(e, "ErrorOSDeleteDir")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def os_delete_file(mainwin, args):
    try:
        if os.path.exists(args["input"]["file"]):
            # create only if the dir doesn't exist
            os.remove(args["input"]["file"])

        msg = "completed deleting file"
        result = [TextContent(type="text", text=msg)]
        return result
    except Exception as e:
        err_trace = get_traceback(e, "ErrorOSDeleteFile")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def os_move_file(mainwin, args):
    try:
        # default_download_dir = getDefaultDownloadDirectory()
        # new_file = getMostRecentFile(default_download_dir, prefix=step["prefix"], extension=step["extension"])

        shutil.move(args["input"]["src"], args["input"]["dest"])

        msg = "completed moving file"
        result = [TextContent(type="text", text=msg)]
        return result
    except Exception as e:
        err_trace = get_traceback(e, "ErrorOSMoveFile")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def os_copy_file_dir(mainwin, args):
    try:
        shutil.copy(args["input"]["src"], args["input"]["dest"])

        msg = "completed copying file dir"
        result = [TextContent(type="text", text=msg)]
        return result
    except Exception as e:
        err_trace = get_traceback(e, "ErrorOSCopyFileDir")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def os_screen_analyze(mainwin, args):
    try:
        win_title_kw = args["input"]["win_title_kw"]
        sub_area = args["input"]["sub_area"]
        site = args["input"]["site"]
        engine = args["input"]["engine"]
        # Use readRandomWindow8 instead of read_screen8 (which doesn't exist)
        screen_content = await readRandomWindow8(mainwin, win_title_kw, sub_area, site, engine)

        msg = "completed screen analysis"
        result = TextContent(type="text", text=msg)
        result.meta = screen_content
        return [result]

    except Exception as e:
        err_trace = get_traceback(e, "ErrorOSScreenAnalyze")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def os_screen_capture(mainwin, args):
    from agent.ec_skills.ocr.image_prep import carveOutImage, maskOutImage, saveImageToFile, takeScreenShot
    try:
        screen_img, window_rect = await takeScreenShot(args["input"]["win_title_kw"])
        img_section = carveOutImage(screen_img, args["input"]["sub_area"], "")
        maskOutImage(img_section, args["input"]["sub_area"], "")

        saveImageToFile(img_section, args["input"]["file"], "png")

        logger.debug(f'Element xpath: {args["input"]["win_title_kw"]}')
        msg = "completed screen capture"
        result = [TextContent(type="text", text=msg)]
        return result
    except Exception as e:
        err_trace = get_traceback(e, "ErrorOSScreenCapture")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def os_seven_zip(mainwin, args):
    try:
        import glob
        exe = 'C:/Program Files/7-Zip/7z.exe'
        from utils.subprocess_helper import run_no_window, popen_no_window
        src = args["input"]["src"]
        dest = args["input"]["dest"]
        
        # Determine if we're zipping or unzipping based on dest extension
        is_zipping = dest.endswith(('.7z', '.zip', '.tar', '.gz', '.bz2', '.xz'))
        
        if is_zipping:
            # Zipping: 7z a <archive_name> <source_files>
            # src can be a string (single path/wildcard) or array of paths
            
            # Normalize src to a list
            if isinstance(src, str):
                src_list = [src]
            else:
                src_list = src
            
            # Expand wildcards and collect all files
            expanded_files = []
            for s in src_list:
                # Check if path contains wildcards
                if '*' in s or '?' in s:
                    # Use glob to expand wildcards (Windows doesn't do this automatically)
                    matches = glob.glob(s)
                    if matches:
                        expanded_files.extend(matches)
                    else:
                        logger.warning(f"[os_seven_zip] No files matched pattern: {s}")
                else:
                    expanded_files.append(s)
            
            if not expanded_files:
                msg = f"Error: No files found to compress. Patterns: {src_list}"
                logger.error(f"[os_seven_zip] {msg}")
                return [TextContent(type="text", text=msg)]
            
            # Build command: 7z a <archive> <file1> <file2> ...
            cmd = [exe, "a", dest] + expanded_files
            logger.info(f"[os_seven_zip] Zipping {len(expanded_files)} file(s): {cmd}")
            cmd_output = run_no_window(cmd)
            msg = f"completed seven zip {len(expanded_files)} file(s) -> {dest}"
        else:
            # Unzipping: 7z e <archive> -o<output_dir>
            if dest != "":
                cmd = [exe, 'e', src, f'-o{dest}', '-y']
                logger.info(f"[os_seven_zip] Unzipping: {cmd}")
                cmd_output = popen_no_window(cmd)
            else:
                cmd = [exe, "e", src, '-y']
                logger.info(f"[os_seven_zip] Unzipping: {cmd}")
                cmd_output = run_no_window(cmd)
            msg = f"completed seven unzip {src}"

        result = [TextContent(type="text", text=msg)]
        return result
    except Exception as e:
        err_trace = get_traceback(e, "ErrorOSSevenZip")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def os_kill_processes(mainwin, args):
    try:

        logger.debug(f'Kill Processes: {args.pids[0]}')
        msg = "completed kill processes"
        result = [TextContent(type="text", text=msg)]
        return result
    except Exception as e:
        err_trace = get_traceback(e, "ErrorOSKillProcesses")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]

# Element Interaction Actions
async def rpa_supervisor_scheduling_work(mainwin, args) -> CallToolResult:
    logger.debug(f"INPUT: {args}")
    # if tool_name != "rpa_supervisor_scheduling_work":
    #     raise ValueError(f"Unexpected tool name: {tool_name}")
    global server_main_win
    try:
        # mainwin = params["agent"].mainwin
        logger.info("[MCP] Running supervisor scheduler tool...")
        logger.info(f"[MCP] Running supervisor scheduler tool... Bots: {len(server_main_win.bots)}")
        schedule = server_main_win.fetchSchedule("", server_main_win.get_vehicle_settings())
        logger.debug(f"MCP fetched schedule: {schedule}")
        # workable = server_main_win.runTeamPrepHook(schedule)
        # works_to_be_dispatched = server_main_win.handleCloudScheduledWorks(workable)
        workable = schedule
        msg = "Here are works to be dispatched to the troops."
        logger.debug(f"MCP MSG: {msg}, workable: {workable}")
        # ctr = CallToolResult(content=[TextContent(type="text", text=msg)], _meta=workable, isError=False)
        ctr = CallToolResult(content=[TextContent(type="text", text=msg)])
        logger.debug(f"About to return call tool result, type: {type(ctr)}, ctr: {ctr}")
        logger.debug(f"CTR Type: {ctr.model_dump(by_alias=True, exclude_none=True, mode='json')}")
        tool_result =  {
            "content": [{"type": "text", "text": msg}],
            # "meta": workable,
            "isError": False
        }
        logger.debug(f"Returning result: {json.dumps(tool_result, indent=2)}")
        # return ctr.model_dump(by_alias=True, exclude_none=True, mode="json", round_trip=False)
        msg = "completed rpa supervisor scheduling work"
        result = [TextContent(type="text", text=msg)]
        return result
    except Exception as e:
        err_trace = get_traceback(e, "ErrorRPASupervisorSchedulingWork")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]

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
        workable = args.get("input", {}).get("workable", {})
        works_to_be_dispatched = mainwin.handleCloudScheduledWorks(workable)
        msg = "completed rpa operator dispatch works"
        result = [TextContent(type="text", text=msg)]
        return result
    except Exception as e:
        err_trace = get_traceback(e, "ErrorRPAOperatorDispatchWorks")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def rpa_supervisor_process_work_results(mainwin, args):
    # handle RPA work results from a platoon host.
    # mostly bookkeeping.
    try:
        workable = args.get("input", {}).get("workable", {})
        works_to_be_dispatched = mainwin.handleCloudScheduledWorks(workable)
        msg = "completed rpa supervisor process work results"
        result = [TextContent(type="text", text=msg)]
        return result
    except Exception as e:
        err_trace = get_traceback(e, "ErrorRPASupervisorProcessWorkResults")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def rpa_supervisor_run_daily_housekeeping(mainwin, args):
    # call put work received from A2A channel, put into today's work data structure
    # the runbotworks task will then take over.....
    # including put reactive work into it.
    try:
        workable = args.get("input", {}).get("workable", {})
        works_to_be_dispatched = mainwin.handleCloudScheduledWorks(workable)
        text_content = [TextContent(type="text", text=f"works dispatched")]
        return text_content
    except Exception as e:
        err_trace = get_traceback(e, "ErrorRPASupervisorRunDailyHousekeeping")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]

async def rpa_operator_report_work_results(mainwin, args):
    # call put work received from A2A channel, put into today's work data structure
    # the runbotworks task will then take over.....
    # including put reactive work into it.
    try:
        workable = args.get("input", {}).get("workable", {})
        works_to_be_dispatched = mainwin.handleCloudScheduledWorks(workable)
        msg = "completed rpa operator report work results"
        result = [TextContent(type="text", text=msg)]
        return result
    except Exception as e:
        err_trace = get_traceback(e, "ErrorRPAOperatorReportWorkResults")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def os_reconnect_wifi(mainwin, args):
    try:
        from utils.subprocess_helper import run_no_window
        # Disconnect current Wi-Fi
        run_no_window(["netsh", "wlan", "disconnect"])
        time.sleep(2)
        # Reconnect to a specific network
        cmd = ["netsh", "wlan", "connect", f"name={args['input']['network_name']}"]
        result = run_no_window(cmd, capture_output=True, text=True)
        msg = f"completed reconnecting wifi ({result.stdout})."
        result = [TextContent(type="text", text=msg)]
        return result
    except Exception as e:
        err_trace = get_traceback(e, "ErrorOSReconnectWifi")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def api_ecan_ai_query_components(mainwin, args):
    # call put work received from A2A channel, put into today's work data structure
    # the runbotworks task will then take over.....
    # including put reactive work into it.
    try:
        print("api_ecan_ai_query_components args: ", args['input']['components'])
        components = ecan_ai_api_query_components(mainwin, args['input']['components'])
        msg = "completed API query components results"
        result = TextContent(type="text", text=msg)
        # meta must be a dict – wrap components list under a key to satisfy pydantic
        result.meta = {"components": components}
        print("api_ecan_ai_query_components about to return: ", result)
        return [result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorAPIECANAIQueryComponents")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def api_ecan_ai_query_fom(mainwin, args):
    # call put work received from A2A channel, put into today's work data structure
    # the runbotworks task will then take over.....
    # including put reactive work into it.
    try:
        print("api_ecan_ai_query_fom args: ", args['input'])
        foms = ecan_ai_api_query_fom(mainwin, args['input']['component_results_info'])
        msg = "completed API query components results"
        result = TextContent(type="text", text=msg)
        # meta must be a dict – wrap components list under a key to satisfy pydantic
        result.meta = {"fom_template": foms}
        print("api_ecan_ai_query_fom about to return: ", result)
        return [result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorAPIECANAIQueryComponents")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]




async def api_ecan_ai_rerank_results(mainwin, args):
    # call put work received from A2A channel, put into today's work data structure
    # the runbotworks task will then take over.....
    # including put reactive work into it.
    try:
        print("api_ecan_ai_rerank_results args: ", args['input'])
        cloud_task_id = ecan_ai_api_rerank_results(mainwin, args['input'])
        msg = f"Starting cloud side re-rank result task completed- with task id of {cloud_task_id}"

        result = TextContent(type="text", text=msg)
        # meta must be a dict – wrap components list under a key to satisfy pydantic
        result.meta = {"cloud_task_id": cloud_task_id}
        print("api_ecan_ai_rerank_results about to return: ", result)
        return [result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorAPIECANAIReRankResults")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]



async def api_ecan_ai_show_status(mainwin, args):
    from agent.mcp.server.api.ecan_ai.ecan_ai_api import ecan_ai_api_get_agent_status
    # call put work received from A2A channel, put into today's work data structure
    # the runbotworks task will then take over.....
    # including put reactive work into it.
    try:
        print("api_ecan_ai_show_status args: ", args['input'])
        agent_status = ecan_ai_api_get_agent_status(mainwin, args['input'])
        agent_id = args.get('input', {}).get('agent_id', 'unknown')

        msg = f"Get agent current status completed- with agent id of {agent_id}"

        result = TextContent(type="text", text=msg)
        # meta must be a dict – wrap components list under a key to satisfy pydantic
        result.meta = {"agent_status": agent_status}
        print("api_ecan_ai_show_status about to return: ", result)
        return [result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorAPIECANAIReRankResults")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]




async def ecan_local_search_components(mainwin, args):
    from agent.mcp.server.scrapers.eval_util import get_default_fom_form
    logger.debug(f"ecan_local_search_components initial state: {args['input']}")
    try:
        vendors = list(args['input']["urls"].keys())
        print("vendors::", vendors)
        vendor = vendors[0]
        print("vendor::", vendor)
        url = args['input']["urls"][vendor][0][-1]["url"]
        logger.debug(f"conncting to ads power: {url}")
        webdriver = connect_to_adspower(mainwin, url)
        if webdriver:
            mainwin.setWebDriver(webdriver)
            logger.debug(f"conncted to ads power and webdriver: {args['input']['urls']}")
            log_user = mainwin.user.replace("@", "_").replace(".", "_")
            pfs = args['input']["parametric_filters"]
            logger.debug(f"Received pf in ecan_local_search_components: {pfs}")
            sites = args['input']['urls']
            fom_form = args['input'].get('fom_form', {})
            if not fom_form:
                fom_form = get_default_fom_form()

            max_n_results = args['input']['max_n_results']
            logger.debug(f"parameters ready: {len(pfs)} {pfs}")
            search_results = []
            for pf in pfs:
                for site in sites:
                    try:
                        # Pass a list of URLs and the target category phrase to the selenium search helper
                        print("searching site:", site)
                        site_results = selenium_search_component(webdriver, pf, sites[site])
                        # extend accumulates in place; do not assign the None return value
                        search_results.extend(site_results)
                    except Exception as e:
                        # record error and continue
                        err_trace = get_traceback(e, "ErrorSeleniumSiteSearchComponent")
                        logger.error(err_trace)
                        continue

            logger.debug(f"all collected search results: {search_results}")


            msg = "completed applying parametric filter to search for results"
            result = TextContent(type="text", text=msg)
            # meta must be a dictionary per MCP spec
            result.meta = {"results": search_results}
            return [result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorECANAILocalSearchComponents")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]




async def ecan_local_sort_search_results(mainwin, args):
    logger.debug(f"ecan_local_sort_search_results initial state: {args}")
    try:
        search_results = []
        sites = args['input']['sites']
        # Acquire a real Selenium WebDriver instance (avoid passing a module)
        web_driver = mainwin.getWebDriver()
        if not web_driver and sites:
            try:
                # Use the first site's URL to initialize/connect the driver
                first_site_url = sites[0]['url']
                web_driver = connect_to_adspower(mainwin, first_site_url)
            except Exception:
                web_driver = None
        logger.debug(f"WebDriver acquired for sorting: {type(web_driver)}")

        for site in sites:
            try:
                # Pass a list of URLs and the target category phrase to the selenium search helper
                site_url = site['url']
                asc = site["ascending"]
                header_text = site["header_text"]
                max_n = site["max_n"]

                # Ensure we have a valid driver before calling into selenium pipeline
                if not web_driver:
                    logger.error("No WebDriver available for sorting operation; skipping site %s", site_url)
                    continue

                site_results = selenium_sort_search_results(web_driver, header_text, asc, max_n, site_url)

                # extend accumulates in place; do not assign the None return value
                search_results.extend(site_results)
            except Exception as e:
                # record error and continue
                err_trace = get_traceback(e, "ErrorSeleniumSiteSortSearchResults")
                logger.error(err_trace)
                continue


        msg = "completed applying sort to search results and export those results"
        result = TextContent(type="text", text=msg)
        # meta must be a dictionary per MCP spec
        result.meta = {"results": search_results}
        return [result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorECANAILocalSortSearchResults")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]




async def api_ecan_ai_img2text_icons(mainwin, args):
    # call put work received from A2A channel, put into today's work data structure
    # the runbotworks task will then take over.....
    # including put reactive work into it.
    try:
        log_user = mainwin.user.replace("@", "_").replace(".", "_")
        session = mainwin.session
        token = mainwin.get_auth_token()

        mission = mainwin.getTrialRunMission()

        screen_data = await readRandomWindow8(mission, args["input"]["win_title_keyword"], log_user, session, token)

        # Check if screen_data contains an error
        if isinstance(screen_data, dict) and "error" in screen_data:
            error_msg = f"Image analysis failed: {screen_data.get('message', 'Unknown error')}"
            logger.warning(f"⚠️ {error_msg}")
            logger.debug(f"Error details: {screen_data.get('details', 'No details')}")
            result = TextContent(type="text", text=error_msg)
            result.meta = {"error": screen_data, "status": "failed"}
            return [result]

        msg = "completed rpa operator report work results"
        result = TextContent(type="text", text=msg)
        # meta must be a dictionary
        result.meta = {"screen_data": screen_data, "status": "success"}
        return [result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorAPIECANAIImg2TextIcons")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]



tool_function_mapping = {
        "say_hello": say_hello,
        "os_wait": os_wait,
        "in_browser_wait_for_element": in_browser_wait_for_element,
        "in_browser_click_element_by_index": in_browser_click_element_by_index,
        "in_browser_click_element_by_selector": in_browser_click_element_by_selector,
        "in_browser_click_element_by_xpath": in_browser_click_element_by_xpath,
        "in_browser_click_element_by_text": in_browser_click_element_by_text,
        "in_browser_input_text": in_browser_input_text,
        "in_browser_switch_tab": in_browser_switch_tab,
        "in_browser_open_tab": in_browser_open_tab,
        "in_browser_go_to_url": in_browser_go_to_url,
        "in_browser_close_tab": in_browser_close_tab,
        "in_browser_extract_content": in_browser_extract_content,
        "in_browser_save_href_to_file": in_browser_save_href_to_file,
        "in_browser_upload_file": in_browser_upload_file,
        "in_browser_execute_javascript": in_browser_execute_javascript,
        "in_browser_scroll": in_browser_scroll,
        "in_browser_send_keys": in_browser_send_keys,
        "in_browser_scroll_to_text": in_browser_scroll_to_text,
        "in_browser_get_dropdown_options": in_browser_get_dropdown_options,
        "in_browser_select_dropdown_option": in_browser_select_dropdown_option,
        "in_browser_drag_drop": in_browser_drag_drop,
        "in_browser_multi_actions": in_browser_multi_actions,
        "mouse_click": mouse_click,
        "mouse_press_hold": mouse_press_hold,
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
        "os_list_dir": os_list_dir,
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
        "ecan_ai_new_chromiunm": ecan_ai_new_chromiunm,
        "os_reconnect_wifi": os_reconnect_wifi,
        "api_ecan_ai_query_components": api_ecan_ai_query_components,
        "api_ecan_ai_query_fom": api_ecan_ai_query_fom,
        "api_ecan_ai_img2text_icons": api_ecan_ai_img2text_icons,
        "api_ecan_ai_get_nodes_prompts": api_ecan_ai_get_nodes_prompts,
        "api_ecan_ai_ocr_read_screen": api_ecan_ai_ocr_read_screen,
        "api_ecan_ai_cloud_search": api_ecan_ai_cloud_search,
        "api_ecan_ai_rerank_results": api_ecan_ai_rerank_results,
        "api_ecan_ai_show_status": api_ecan_ai_show_status,
        "mouse_act_on_screen": mouse_act_on_screen,
        "ecan_local_search_components": ecan_local_search_components,
        "ecan_local_sort_search_results": ecan_local_sort_search_results,
        "get_ebay_summary": get_ebay_summary,
        "ebay_fullfill_next_order": ebay_fullfill_next_order,
        "ebay_read_next_message": ebay_read_next_message,
        "ebay_respond_to_message": ebay_respond_to_message,
        "ebay_read_all_messages": ebay_read_all_messages,
        "ebay_handle_return": ebay_handle_return,
        "ebay_cancel_orders": ebay_cancel_orders,
        "ebay_gen_labels": ebay_gen_labels,
        "ebay_handle_refund": ebay_handle_refund,
        "ebay_generate_work_summary": ebay_generate_work_summary,
        "ebay_search": ebay_search,

        "etsy_search": etsy_search,
        "etsy_add_listings": etsy_add_listings,
        "etsy_remove_listings": etsy_remove_listings,
        "etsy_update_listings": etsy_update_listings,
        "etsy_get_listings": etsy_get_listings,
        "etsy_add_listing_templates": etsy_add_listing_templates,
        "etsy_remove_listing_templates": etsy_remove_listing_templates,
        "etsy_update_listing_templates": etsy_update_listing_templates,
        "etsy_handle_return": etsy_handle_return,
        "etsy_handle_refund": etsy_handle_refund,
        "etsy_collect_campaigns_stats": etsy_collect_campaigns_stats,
        "etsy_adjust_campaigns": etsy_adjust_campaigns,
        "etsy_collect_shop_products_stats": etsy_collect_shop_products_stats,
        "etsy_generate_work_summary": etsy_generate_work_summary,

        "amazon_search": amazon_search,
        "amazon_add_listings": amazon_add_listings,
        "amazon_remove_listings": amazon_remove_listings,
        "amazon_update_listings": amazon_update_listings,
        "amazon_get_listings": amazon_get_listings,
        "amazon_add_listing_templates": amazon_add_listing_templates,
        "amazon_remove_listing_templates": amazon_remove_listing_templates,
        "amazon_update_listing_templates": amazon_update_listing_templates,
        "amazon_handle_return": amazon_handle_return,
        "amazon_handle_refund": amazon_handle_refund,
        "amazon_collect_campaigns_stats": amazon_collect_campaigns_stats,
        "amazon_adjust_campaigns": amazon_adjust_campaigns,
        "amazon_collect_shop_products_stats": amazon_collect_shop_products_stats,
        "amazon_generate_work_summary": amazon_generate_work_summary,

        # "get_custom_shop_summary": get_custom_shop_summary,
        # "custom_shop_fullfill_next_order": custom_shop_fullfill_next_order,
        # "custom_shop_read_next_message": custom_shop_read_next_message,
        # "custom_shop_respond_to_message": custom_shop_respond_to_message,
        # "custom_shop_handle_return": custom_shop_handle_return,
        # "custom_shop_cancel_order": custom_shop_cancel_order,
        # "custom_shop_gen_label": custom_shop_gen_label,
        # "custom_shop_handle_refund": custom_shop_handle_refund,
        # "custom_shop_fullfill_mcn_order": custom_shop_fullfill_mcn_order,
        # "custom_shop_generate_work_summary": custom_shop_generate_work_summary,
        "gmail_delete_email": gmail_delete_email,
        "gmail_move_email": gmail_move_email,
        "gmail_respond": gmail_respond,
        "gmail_write_new": gmail_write_new,
        "gmail_read_titles": gmail_read_titles,
        "gmail_mark_status": gmail_mark_status,
        "gmail_read_full_email": gmail_read_full_email,
        "privacy_reserve": privacy_reserve,
        "pirate_shipping_purchase_labels": pirate_shipping_purchase_labels,
        "reformat_labels": reformat_labels,
        "print_labels": print_labels,
        "ragify": ragify,
        "rag_query": rag_query,
        "wait_for_rag_completion": wait_for_rag_completion,
        "ragify_async": ragify_async,
        # Self-introspection tools
        "describe_self": async_describe_self,
        "start_task_using_skill": async_start_task_using_skill,
        "stop_task_using_skill": async_stop_task_using_skill,
        "schedule_task": async_schedule_task,
        # Code execution tools
        "run_code": async_run_code,
        "run_shell_script": async_run_shell_script,
        # Search tools
        "grep_search": async_grep_search,
        "find_files": async_find_files,
        # Chat/communication tools
        "send_chat": async_send_chat,
        "list_chat_agents": async_list_chat_agents,
        "get_chat_history": async_get_chat_history,
    }

def set_server_main_win(mw):
    # Ensure server_main_win is only set from the GUI thread
    # If needed from worker threads, dispatch via gui_dispatch
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



# async def handle_sse(scope, receive, send):
#     logger.debug(">>> sse connected")
#     async with meca_sse.connect_sse(scope, receive, send) as streams:
#         logger.debug("handling meca_mcp_server.run", streams)
#         await meca_mcp_server.run(streams[0], streams[1], meca_mcp_server.create_initialization_options())

async def handle_sse(scope, receive, send):
    logger.debug(">>> sse connected")
    async with meca_sse.connect_sse(scope, receive, send) as (read_stream, write_stream, is_new):
        # Start MCP server only on the very first GET (= new session)
        if is_new:
            logger.debug(f"handling meca_mcp_server.run {read_stream} {write_stream}")
            await meca_mcp_server.run(
                read_stream,
                write_stream,
                meca_mcp_server.create_initialization_options(),
            )

async def sse_handle_messages(scope, receive, send):
    logger.debug(">>> sse handle messages connected")
    await meca_sse.handle_post_message(scope, receive, send)
