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
    gmail_read_full_email,
)
from agent.mcp.server.Privacy.privacy_reserve import privacy_reserve
from agent.ec_skills.rag.local_rag_mcp import ragify, rag_query
from agent.mcp.server.utils.print_utils import reformat_and_print_labels
from agent.ec_skills.browser_use_for_ai.browser_use_tools import *
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
    login = AppContext.login
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


async def in_browser_wait_for_element(mainwin, args):
    """Waits for the element specified by the CSS selector to become visible within the given timeout."""
    try:
        crawler = mainwin.getWebCrawler()
        if not crawler:
            web_driver = mainwin.getWebDriver()
            wait = WebDriverWait(web_driver, args["input"]["timeout"])
            sel = get_selector(args['input']["element_type"])
            args.tool_result = wait.until(EC.element_to_be_clickable((sel, args['input']["element_name"])))
        else:
            browser_use_wait_for_element(args['input']['element_type'], args['input']['element_name'], args['input']['timeout'])
        msg=f"completed loading element{args['input']['element_name']}."
        result = [TextContent(type="text", text=msg)]
        return result
    except Exception as e:
        err_trace = get_traceback(e, "ErrorInBrowserWaitForElement")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


# Element Interaction Actions
async def in_browser_click_element_by_index(mainwin, args):
    try:
        crawler = mainwin.getWebCrawler()
        if not crawler:
            web_driver = mainwin.getWebDriver()
            raise Exception(f"Element with index {args['input']['index']} without crawler not implemented")
        else:
            br_result = await browser_use_click_element_by_index(mainwin, args['input']['index'])

        msg = f"completed loading element by index {args['input']['index']}."
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
        crawler = mainwin.getWebCrawler()
        if not crawler:
            web_driver = mainwin.getWebDriver()
            if web_driver:
                element_handle = webDriverWaitForVisibility(web_driver, By.CSS_SELECTOR, args['input']['css_selector'], args['input']['timeout'])
                element_handle.click()
        else:
            browser_session = mainwin.browser_session
            element_handle = await browser_session.get_locate_element_by_css_selector(args['input']["css_selector"])
            await element_handle.click()
            await asyncio.sleep(0.8)

        msg = f"completed loading element by index {args['input']['css_selector']}."
        result = [TextContent(type="text", text=msg)]
        return result
    except Exception as e:
        err_trace = get_traceback(e, "ErrorInBrowserClickElementBySelector")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def in_browser_click_element_by_xpath(mainwin, args):
    try:
        crawler = mainwin.getWebCrawler()
        if not crawler:
            web_driver = mainwin.getWebDriver()
            if web_driver:
                element_handle = webDriverWaitForVisibility(web_driver, By.XPATH, args['input']['xpath'],
                                                            args['input']['timeout'])
                element_handle.click()
        else:
            browser_session = mainwin.browser_session
            element_handle = await browser_session.get_locate_element_by_xpath(args['input']["xpath"])
            await element_handle.click()
            await asyncio.sleep(0.8)

        msg = f"completed loading element by index {args['input']['xpath']}."
        result = [TextContent(type="text", text=msg)]
        return result
    except Exception as e:
        err_trace = get_traceback(e, "ErrorInBrowserClickElementByXpath")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def in_browser_click_element_by_text(mainwin, args):
    try:
        crawler = mainwin.getWebCrawler()
        if not crawler:
            web_driver = mainwin.getWebDriver()
            web_elements = web_driver.find_elements(args['input']["element_type"], args['input']["element_name"])
            # find element
            targets = [ele for ele in web_elements if ele.text == args['input']["element_text"]]
            if targets and args['input']["nth"] < len(targets):
                target = targets[args['input']["nth"]]
            else:
                target = None

            if target:
                target.click()

            if args['input']["post_wait"]:
                time.sleep(args['input']["post_wait"])
        else:
            br_result = await browser_use_click_element_by_index(mainwin,args['input']['element_text'])

        msg = f"completed in-browser click."
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
        crawler = mainwin.getWebCrawler()
        if not crawler:
            web_driver = mainwin.getWebDriver()

            web_elements = web_driver.find_elements(args['input']["element_type"], args['input']["element_name"])
            # find element
            targets = [ele for ele in web_elements if ele.text == args['input']["element_text"]]
            if targets and args['input']["nth"] < len(targets):
                target = targets[args['input']["nth"]]
            else:
                target = None

            webDriverKeyIn(web_driver, target, args['input']["text"])
            if args['input']["post_enter"]:
                target.send_keys(Keys.ENTER)

            if args['input']["post_wait"]:
                time.sleep(args['input']["post_wait"])
        else:
            dom_index = args['input']["text"]
            bu_result = await browser_use_input_text(mainwin, dom_index, args['input']['text'])

        msg = f"completed loading element by index {args['input']['index']}."
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
        crawler = mainwin.getWebCrawler()
        if not crawler:
            web_driver = mainwin.getWebDriver()
            webDriverSwitchTab(web_driver, args['input']["tab_title_txt"], args['input']["url"])
        else:
            page_id = args['input']["url"]
            bu_result = await browser_use_switch_tab(mainwin, page_id, args['input']['url'])

        msg = f"completed in-browser switch tab {args['input']['url']}."
        result = [TextContent(type="text", text=msg)]
        return result
    except Exception as e:
        err_trace = get_traceback(e, "ErrorInBrowserSwitchTab")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def in_browser_open_tab(mainwin, args):

    try:
        crawler = mainwin.getWebCrawler()
        if not crawler:
            web_driver = mainwin.getWebDriver()
            url = args['input']["url"]
            web_driver.switch_to.window(web_driver.window_handles[0])
            time.sleep(3)
            web_driver.execute_script(f"window.open('{url}', '_blank');")

            # Switch to the new tab
            web_driver.switch_to.window(web_driver.window_handles[-1])
            time.sleep(3)
            # Navigate to the new URL in the new tab
            if url:
                web_driver.get(url)  # Replace with the new URL
                logger.info("open URL: " + url)
        else:
            logger.info('browser_use: in_browser_open_tab:' + args["input"]["url"])
            bu_result = await browser_use_go_to_url(mainwin, args["input"]["url"])

        msg = f'completed openning tab and go to site:{args["input"]["url"]}.'
        logger.info(msg)
        result = [TextContent(type="text", text=msg)]
        return result
    except Exception as e:
        err_trace = get_traceback(e, "ErrorInBrowserOpenTab")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def in_browser_close_tab(mainwin, args):
    try:
        crawler = mainwin.getWebCrawler()
        if not crawler:
            web_driver = mainwin.getWebDriver()
            if args['input']["tab_title"]:
                for handle in web_driver.window_handles:
                    web_driver.switch_to.window(handle)
                    if args['input']["tab_title"] in web_driver.current_url:
                        break
            web_driver.close()
        else:
            page_id = args['input']["url"]
            bu_result = await browser_use_close_tab(mainwin, page_id, args['input']["url"])

        msg = f"completed closing tab {args['input']['url']}."
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
    from browser_use.actor import Page, Element, Mouse
    from browser_use.browser.events import SwitchTabEvent

    try:

        # web_driver = mainwin.getWebDriver()
        # dom_tree = web_driver.execute_cdp_cmd(
        #     "DOM.getDocument",
        #     {"depth": -1, "pierce": True}
        # )

        # let's piggy back on browser_use's rich functionalities.
        browser_session = mainwin.getBrowserSession()
        if not browser_session:
            print("creating session....")
            browser_session = mainwin.createBrowserSession("existing_chrome")
            # browser_session = mainwin.createBrowserSession("new_chromium")
            print("starting browser session...")
            await browser_session.start()
            print("browser session started!")
        # Note: include_screenshot=False to avoid CDP timeout issues with existing Chrome instances
        # that have many tabs. Screenshot capture via CDP can hang on complex browser states.
        # If you need screenshots, consider using a fresh browser instance or fewer tabs.
        browser_state_summary = await browser_session.get_browser_state_summary(
            include_screenshot=False,  # Disabled due to CDP timeout issues with existing Chrome
            include_recent_events=True
        )

        msg = f"completed extracting browser content."
        result = TextContent(type="text", text=msg)
        # SimplifiedNode has __json__() that breaks circular refs
        # if browser_state_summary.dom_state._root:
        #     json_tree = browser_state_summary.dom_state._root.__json__()
        #     print("json_tree:", json_tree)

        pages = await browser_session.get_pages()
        print("pages:", [await get_page_info(page) for page in pages])



        current_page = await browser_session.get_current_page()
        print("current_page:", await get_page_info(current_page))

        # switch to a tab.
        target_id = "6A806E3DD394DB15724B5B09FB83494C"
        event = browser_session.event_bus.dispatch(SwitchTabEvent(target_id=target_id))
        await event
        target_page = await browser_session.get_current_page()
        content, content_stats = await target_page._extract_clean_markdown()
        print("target_page:", content, content_stats)

        # target_page = Page(browser_session, target_id, session_id)
        # print("current_page:", current_page)
        browser_state_summary = await browser_session.get_browser_state_summary(
            include_screenshot=False,  # Disabled due to CDP timeout issues with existing Chrome
            include_recent_events=True
        )

        serializable_state = {
            "url": browser_state_summary.url,
            "title": browser_state_summary.title,
            "tabs": [tab.model_dump() for tab in browser_state_summary.tabs],
            "screenshot": browser_state_summary.screenshot,  # base64 string or None
            "dom_text": browser_state_summary.dom_state.llm_representation(),
            "interactive_elements": list(browser_state_summary.dom_state.selector_map.keys()),
        }
        logger.debug("browser_state_summary: ",serializable_state)

        result.meta = {"browser_state": serializable_state}
        return [result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorInBrowserScrapeContents")
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
        crawler = mainwin.getWebCrawler()
        if not crawler:
            web_driver = mainwin.getWebDriver()
            result = execute_js_script(web_driver, args['input']["script"], args['input']["target"])
        else:
            bu_result = await browser_use_execute_javascript(mainwin, args['input']['script'])

        msg = f"completed in browser execute javascript {args['input']['script']}."
        tool_result = [TextContent(type="text", text=msg)]
        return tool_result
    except Exception as e:
        err_trace = get_traceback(e, "ErrorInBrowserExecuteJavascript")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def in_browser_build_dom_tree(mainwin, args):
    try:
        crawler = mainwin.getWebCrawler()
        if not crawler:
            webdriver = mainwin.getWebDriver()
            script = mainwin.load_build_dom_tree_script()
            # logger.debug("dom tree build script to be executed", script)
            target = None
            domTree = execute_js_script(webdriver, script, target)
            logger.debug(">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
            logger.debug(f"obtained dom tree: {domTree}")
            with open("domtree.json", 'w', encoding="utf-8") as dtjf:
                json.dump(domTree, dtjf, ensure_ascii=False, indent=4)
                # self.rebuildHTML()
                dtjf.close()
        else:
            logger.debug("build dom tree....")
            # bu_result = await browser_use_build_dom_tree(mainwin)

        domTreeJSString = json.dumps(domTree)            # clear error
        time.sleep(1)

        result_text_content = "completed building DOM tree."

        tool_result = TextContent(type="text", text=result_text_content)

        tool_result.meta = {"dom_tree": domTree}
        return [tool_result]

    except Exception as e:
        err_trace = get_traceback(e, "ErrorInBrowserBuildDomTree")
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


async def browser_use_download_file(mainwin, ele_type, ele_text, dl_dir, dl_file):
    """Download a file using browser_use session.
    
    Args:
        mainwin: Main window instance with browser_session
        ele_type: Element type to search for
        ele_text: Text content to match in the element
        dl_dir: Directory to save the file
        dl_file: Filename to save as
    
    Returns:
        Full path of the saved file
    """
    import aiohttp
    import os
    
    browser_session = mainwin.browser_session
    page = await browser_session.get_current_page()
    
    # Find element by text
    element = await page.query_selector(f'{ele_type}:has-text("{ele_text}")')
    if not element:
        # Try broader search
        elements = await page.query_selector_all(ele_type)
        for elem in elements:
            text = await elem.inner_text()
            if ele_text in text:
                element = elem
                break
    
    if not element:
        raise ValueError(f"Element with type '{ele_type}' and text '{ele_text}' not found")
    
    # Get href
    href = await element.get_attribute('href')
    if not href:
        href = await element.get_attribute('data-href') or await element.get_attribute('data-url')
    
    if not href:
        raise ValueError(f"No href found on element with text '{ele_text}'")
    
    # Ensure download directory exists
    os.makedirs(dl_dir, exist_ok=True)
    
    # Get cookies from browser context
    context = page.context
    cookies = await context.cookies()
    cookie_dict = {cookie['name']: cookie['value'] for cookie in cookies}
    
    # Download using aiohttp
    async with aiohttp.ClientSession(cookies=cookie_dict) as session:
        async with session.get(href) as response:
            response.raise_for_status()
            file_path = os.path.join(dl_dir, dl_file)
            with open(file_path, 'wb') as f:
                async for chunk in response.content.iter_chunked(8192):
                    f.write(chunk)
    
    return file_path


# HTML Download
async def in_browser_save_href_to_file(mainwin, args) -> CallToolResult:
    """Retrieves and returns the full HTML content of the current page to a file"""
    try:
        crawler = mainwin.getWebCrawler()
        if not crawler:
            web_driver = mainwin.getWebDriver()

            saved = webDriverDownloadFile(web_driver, args["input"]["ele_type"], args["input"]["ele_text"], args["input"]["dl_dir"], args["input"]["dl_file"])
        else:
            br_result = await browser_use_download_file(mainwin, args["input"]["ele_type"], args["input"]["ele_text"], args["input"]["dl_dir"], args["input"]["dl_file"])

        msg = f"completed loading {saved}."
        tool_result = [TextContent(type="text", text=msg)]
        return tool_result
    except Exception as e:
        err_trace = get_traceback(e, "ErrorInBrowserSaveHtmlToFile")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def in_browser_scroll(mainwin, args):
    try:
        crawler = mainwin.getWebCrawler()
        if not crawler:
            web_driver = mainwin.getWebDriver()

            if args["input"]["direction"].lower() == "down":
                scroll_amount = 0 - args["input"]["amount"]
            else:
                scroll_amount = args["input"]["amount"]
            web_driver.execute_script(f"window.scrollBy(0, {args['input']['amount']});")

            if args["input"]["post_wait"]:
                time.sleep(args["input"]["post_wait"])
        else:
            br_result = await browser_use_scroll(mainwin, args["input"]["direction"], args["input"]["amount"], args["input"]["post_wait"])

        msg = f"completed in browser scroll {args['input']['direction']} {args['input']['amount']}."
        tool_result = [TextContent(type="text", text=msg)]
        return tool_result
    except Exception as e:
        err_trace = get_traceback(e, "ErrorInBrowserScrollDown")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]

# send keys
async def in_browser_send_keys(mainwin, args):
    try:
        crawler = mainwin.getWebCrawler()
        if not crawler:
            web_driver = mainwin.getWebDriver()
            browser_context = AppContext.get_main_window().getBrowserContextById(args["context_id"])
            browser = browser_context.browser
            page = await browser.get_current_page()


            await page.keyboard.press(args.keys)
        else:
            br_result = await browser_use_send_keys(mainwin, args["context_id"], args['input']['keys'])

        msg = f'⌨️  Sent keys: {args.keys}'
        logger.info(msg)
        msg = f"completed loading element by index {args['input']['index']}."
        tool_result = [TextContent(type="text", text=msg)]
        return tool_result
    except Exception as e:
        err_trace = get_traceback(e, "ErrorInBrowserSendKeys")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def in_browser_scroll_to_text(mainwin, args):  # type: ignore
    try:
        crawler = mainwin.getWebCrawler()
        if not crawler:
            web_driver = mainwin.getWebDriver()

            element = web_driver.find_element("xpath", "//*[contains(text(), args['input']['text'])]")

            # Scroll to the element
            web_driver.execute_script("arguments[0].scrollIntoView({block: 'center', behavior: 'smooth'});", element)
        else:
            br_result = await browser_use_scroll_to_text(mainwin, args["input"]["text"])

        msg = f"completed in browser scroll to text {args['input']['text']}."
        tool_result = [TextContent(type="text", text=msg)]
        return tool_result
    except Exception as e:
        err_trace = get_traceback(e, "ErrorInBrowserScrollToText")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def in_browser_get_dropdown_options(mainwin, args) -> CallToolResult:
    try:
        crawler = mainwin.getWebCrawler()
        if not crawler:
            web_driver = mainwin.getWebDriver()
        else:
            br_result = await browser_use_get_dropdown_options(mainwin, args["context_id"], args['input']['index'])


        msg = f"completed loading element by index {args['input']['index']}."
        tool_result = [TextContent(type="text", text=msg)]
        return tool_result


    except Exception as e:
        err_trace = get_traceback(e, "ErrorInBrowserGetDropdownOptions")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def in_browser_select_dropdown_option(mainwin, args) -> CallToolResult:
    try:
        crawler = mainwin.getWebCrawler()
        if not crawler:
            web_driver = mainwin.getWebDriver()
        else:
            br_result = await browser_use_select_dropdown_option(mainwin, args["context_id"], args['input']['index'])

        msg = f"completed loading element by index {args['input']['index']}."
        tool_result = [TextContent(type="text", text=msg)]
        return tool_result
    except Exception as e:
        err_trace = get_traceback(e, "ErrorInBrowserSelectDropdownOption")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def in_browser_drag_drop(mainwin, args) -> CallToolResult:
    try:
        crawler = mainwin.getWebCrawler()
        if not crawler:
            web_driver = mainwin.getWebDriver()
        else:
            source_x = args["input"]["source_x"]
            source_y = args["input"]["source_y"]
            target_x = args["input"]["target_x"]
            target_y = args["input"]["target_y"]
            br_result = await browser_use_drag_drop(mainwin, args["context_id"], args['input']['index'])

        msg = f'🖱️ Dragged from ({source_x}, {source_y}) to ({target_x}, {target_y})'
        logger.info(msg)
        return CallToolResult(content=[TextContent(type="text", text=msg)], isError=False)


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
    logger.debug(f"initial state: {args}")
    try:
        webdriver = connect_to_adspower(mainwin, args['input']["url"])
        if webdriver:
            page_scroll(mainwin, webdriver)

            dom_tree = webdriver.execute_cdp_cmd(
                "DOM.getDocument",
                {"depth": -1, "pierce": True}
            )

            logger.debug(f"dom tree: {type(dom_tree)}, {dom_tree}")
            # logs = response.get("logs", [])
            # if len(logs) > 128:
            #     llen = 128
            # else:
            #     llen = len(logs)
            #
            # for i in range(llen):
            #     logger.debug(logs[i])

            # with open("domtree.json", 'w', encoding="utf-8") as dtjf:
            #     json.dump(domTree, dtjf, ensure_ascii=False, indent=4)
            #     # self.rebuildHTML()
            #     dtjf.close()

            # logger.debug(f"dom tree: {type(domTree)}, {domTree.keys()}")
            # top_level_nodes = find_top_level_nodes(domTree)
            # logger.debug(f"top level nodes: {type(top_level_nodes)}, {top_level_nodes}")
            # top_level_texts = get_shallowest_texts(top_level_nodes, domTree)
            # tls = collect_text_nodes_by_level(domTree)
            # logger.debug(f"level texts: {tls}")
            # logger.debug(f"level N texts: {[len(tls[i]) for i in range(len(tls))]}")
            # for l in tls:
            #     if l:
            #         logger.debug(f"level texts: {[domTree['map'][nid]['text'] for nid in l]}")
            #
            # sects = sectionize_dt_with_subsections(domTree)
            # logger.debug(f"sections: {sects}")
            mainwin.setWebDriver(webdriver)
            # set up output.
            msg = "completed connect to adspower."
        else:
            mainwin.setWebDriver(None)
            # set up output.
            msg = "failed connect to adspower."

        result = TextContent(type="text", text=f"{msg}")
        return [result]

    except Exception as e:
        err_trace = get_traceback(e, "ErrorOSConnectToAdspower")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def os_connect_to_chrome(mainwin, args):
    webdriver_path = mainwin.default_webdriver_path

    logger.debug(f"initial state: {args}")
    try:
        url = args["input"]["url"]
        port = args["input"]["ads_port"]
        webdriver = connect_to_existing_chrome(args["input"]["driver_path"], url, port)
        time.sleep(1)

        # Switch to the new tab
        if webdriver:
            webdriver.switch_to.window(webdriver.window_handles[-1])
            time.sleep(3)
            # set up output.
            msg = "completed connect to chrome."
        else:
            msg = "failed connect to chrome."

        mainwin.setWebDriver(webdriver)

        result = [TextContent(type="text", text=msg)]
        return result

    except Exception as e:
        err_trace = get_traceback(e, "ErrorOSConnectToChrome")
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
        exe = 'C:/Program Files/7-Zip/7z.exe'
        from utils.subprocess_helper import run_no_window, popen_no_window
        if "zip" in args["input"]["dest"]:
            # we are zipping a folder or file
            if args["input"]["dest"] != "":
                cmd_output = run_no_window([exe, "a", args["input"]["src"], "-o" + args["input"]["dest"]])
            else:
                cmd_output = run_no_window([exe, "e", args["input"]["src"]])
            msg = f"completed seven zip {args['input']['src']}"
        else:
            # we are unzipping a single file
            if args["input"]["dest"] != "":
                cmd = [exe, 'e', args["input"]["src"],  f'-o{args["input"]["dest"]}']
                cmd_output = popen_no_window(cmd)
            else:
                cmd_output = run_no_window([exe, "e", args["input"]["src"]])
            msg = f"completed seven unzip {args['input']['src']}"

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
        "in_browser_close_tab": in_browser_close_tab,
        "in_browser_extract_content": in_browser_extract_content,
        "in_browser_save_href_to_file": in_browser_save_href_to_file,
        "in_browser_execute_javascript": in_browser_execute_javascript,
        "in_browser_build_dom_tree": in_browser_build_dom_tree,
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
        "gmail_read_full_email": gmail_read_full_email,
        "privacy_reserve": privacy_reserve,
        "pirate_shipping_purchase_labels": pirate_shipping_purchase_labels,
        "reformat_and_print_labels": reformat_and_print_labels,
        "ragify": ragify,
        "rag_query": rag_query
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
