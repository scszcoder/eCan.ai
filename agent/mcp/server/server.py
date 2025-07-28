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
from mcp.types import CallToolResult, TextContent
from mcp.server.streamable_http import (
    StreamableHTTPServerTransport
)
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from agent.mcp.server.scrapers.px_captcha.px_captcha_solver import px_captcha_solve

from agent.mcp.server.tool_schemas import *
import json
from dotenv import load_dotenv
import logging
from datetime import datetime
from agent.ec_skills.browser_use_for_ai.browser_use_extension import (
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
from utils.logger_helper import get_agent_by_id, get_traceback
from .event_store import InMemoryEventStore
from collections import defaultdict
# from agent.ec_skills.dom.dom_utils import *
from agent.mcp.server.api.ecan_ai.ecan_ai_api import ecan_ai_api_query_components
from agent.ec_skills.browser_use_for_ai.browser_use_tools import *


server_main_win = None
# logger = logging.getLogger(__name__)

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
        msg = f'🕒  Waited for {args["input"]["seconds"]} seconds'
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
        crawler = mainwin.getCrawler()
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
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]


# Element Interaction Actions
async def in_browser_click_element_by_index(mainwin, args):
    try:
        crawler = mainwin.getCrawler()
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
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def in_browser_click_element_by_selector(mainwin, args):
    try:
        crawler = mainwin.getCrawler()
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
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def in_browser_click_element_by_xpath(mainwin, args):
    try:
        crawler = mainwin.getCrawler()
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
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def in_browser_click_element_by_text(mainwin, args):
    try:
        crawler = mainwin.getCrawler()
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
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def in_browser_input_text(mainwin, args):
    try:
        crawler = mainwin.getCrawler()
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
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]

# Save PDF

# Tab Management Actions
async def in_browser_switch_tab(mainwin, args):
    try:
        crawler = mainwin.getCrawler()
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
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def in_browser_open_tab(mainwin, args):

    try:
        crawler = mainwin.getCrawler()
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
                print("open URL: " + url)
        else:
            bu_result = await browser_use_go_to_url(mainwin, args["input"]["url"])

        msg = f'completed openning tab and go to site:{args["input"]["url"]}.'
        logger.info(msg)
        result = [TextContent(type="text", text=msg)]
        return result
    except Exception as e:
        err_trace = get_traceback(e, "ErrorInBrowserOpenTab")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def in_browser_close_tab(mainwin, args):
    try:
        crawler = mainwin.getCrawler()
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
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]

# Content Actions
async def in_browser_scrape_content(mainwin, args):
    try:
        crawler = mainwin.getCrawler()
        if not crawler:
            web_driver = mainwin.web_driver
            dom_service = mainwin.dom_service
            dom_service.get_clickable_elements()
        else:
            extract_links = True
            bu_result = await browser_use_extract_structured_data(mainwin, args['input']['query'], extract_links)
            print("extracted page result: " + bu_result)

        msg = f"completed loading element by index {args['input']['index']}."
        result = [TextContent(type="text", text=msg)]
        return result
    except Exception as e:
        err_trace = get_traceback(e, "ErrorInBrowserScrapeContents")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def in_browser_execute_javascript(mainwin, args):
    try:
        crawler = mainwin.getCrawler()
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
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def in_browser_build_dom_tree(mainwin, args):
    try:
        crawler = mainwin.getCrawler()
        if not crawler:
            webdriver = mainwin.getWebDriver()
            script = mainwin.load_build_dom_tree_script()
            # print("dom tree build script to be executed", script)
            target = None
            domTree = execute_js_script(webdriver, script, target)
            print(">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
            print("obtained dom tree:", domTree)
            with open("domtree.json", 'w', encoding="utf-8") as dtjf:
                json.dump(domTree, dtjf, ensure_ascii=False, indent=4)
                # self.rebuildHTML()
                dtjf.close()
        else:
            print("build dom tree....")
            # bu_result = await browser_use_build_dom_tree(mainwin)

        domTreeJSString = json.dumps(domTree)            # clear error
        time.sleep(1)

        result_text_content = "completed building DOM tree."

        tool_result = [TextContent(type="text", text=result_text_content)]

        tool_result.meta = {"dom_tree": domTree}
        return tool_result

    except Exception as e:
        err_trace = get_traceback(e, "ErrorInBrowserBuildDomTree")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]



# HTML Download
async def in_browser_save_href_to_file(mainwin, args) -> CallToolResult:
    """Retrieves and returns the full HTML content of the current page to a file"""
    try:
        crawler = mainwin.getCrawler()
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
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def in_browser_scroll(mainwin, args):
    try:
        crawler = mainwin.getCrawler()
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
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]

# send keys
async def in_browser_send_keys(mainwin, args):
    try:
        crawler = mainwin.getCrawler()
        if not crawler:
            web_driver = mainwin.getWebDriver()
            browser_context = login.main_win.getBrowserContextById(args["context_id"])
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
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def in_browser_scroll_to_text(mainwin, args):  # type: ignore
    try:
        crawler = mainwin.getCrawler()
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
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def in_browser_get_dropdown_options(mainwin, args) -> CallToolResult:
    try:
        crawler = mainwin.getCrawler()
        if not crawler:
            web_driver = mainwin.getWebDriver()
        else:
            br_result = await browser_use_get_dropdown_options(mainwin, args["context_id"], args['input']['index'])


        msg = f"completed loading element by index {args['input']['index']}."
        tool_result = [TextContent(type="text", text=msg)]
        return tool_result


    except Exception as e:
        err_trace = get_traceback(e, "ErrorInBrowserGetDropdownOptions")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def in_browser_select_dropdown_option(mainwin, args) -> CallToolResult:
    try:
        crawler = mainwin.getCrawler()
        if not crawler:
            web_driver = mainwin.getWebDriver()
        else:
            br_result = await browser_use_select_dropdown_option(mainwin, args["context_id"], args['input']['index'])

        msg = f"completed loading element by index {args['input']['index']}."
        tool_result = [TextContent(type="text", text=msg)]
        return tool_result
    except Exception as e:
        err_trace = get_traceback(e, "ErrorInBrowserSelectDropdownOption")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def in_browser_drag_drop(mainwin, args) -> CallToolResult:
    try:
        crawler = mainwin.getCrawler()
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
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]

async def in_browser_multi_actions(mainwin, args):
    try:
        crawler = mainwin.getCrawler()
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
                            print(f"[WARN] Could not find and select option '{option}' for '{title}'")

                print("All filters filled!")
                return("completed fill parametric cards")

        msg = "completed filling empty actions."
        if actions:
            msg =fill_parametric_cards(web_driver, actions)

        result = [TextContent(type="text", text=msg)]

        return [result]

    except Exception as e:
        err_trace = get_traceback(e, "ErrorInBrowserMultiCardAction")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]

async def mouse_click(mainwin, args):
    try:
        print("MOUSE CLICKINPUT:", args)

        pyautogui.moveTo(args["input"]["loc"][0], args["input"]["loc"][1])
        time.sleep(args["input"]["post_move_delay"])
        pyautogui.click(clicks=2, interval=0.3)
        time.sleep(args["input"]["post_click_delay"])

        msg = "completed mouse click"
        result = [TextContent(type="text", text=msg)]

        return [result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorMouseClick")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def mouse_move(mainwin, args):
    try:
        print("MOUSE HOVER INPUT:", args)
        pyautogui.moveTo(args["input"]["loc"][0], args["input"]["loc"][1])
        # ctr = CallToolResult(content=[TextContent(type="text", text=msg)], _meta=workable, isError=False)
        time.sleep(args["input"]["post_delay"])

        msg = "completed mouse move"
        result = [TextContent(type="text", text=msg)]
        return [result]

    except Exception as e:
        err_trace = get_traceback(e, "ErrorMouseMove")
        logger.debug(err_trace)
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
        logger.debug(err_trace)
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
        logger.debug(err_trace)
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
        logger.debug(err_trace)
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
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]

async def http_call_api(mainwin, args):
    try:

        msg = "completed calling API"
        result = [TextContent(type="text", text=msg)]
        return [result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorHttpCallApi")
        logger.debug(err_trace)
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
        print("Error: auto_scroll.js not found. Please check the path.")
        # Handle error appropriately
        exit()

    # 2. To scroll DOWN, append the call to scrollToPageBottom()
    print("Starting full page scroll-down...")
    scroll_down_command = scrolling_functions_js + "\nvar cb = arguments[arguments.length - 1]; scrollToPageBottom(cb);"
    down_scroll_count = web_driver.execute_async_script(scroll_down_command)
    print(f"Page fully scrolled down in {down_scroll_count} steps.")

    time.sleep(1)  # A brief pause

    # 3. To scroll UP, append the call to scrollToPageTop() and pass arguments
    print("Scrolling back to the top of the page...")
    scroll_up_command = scrolling_functions_js + "\nvar cb = arguments[arguments.length - 1]; scrollToPageTop(arguments[0], arguments[1], cb);"
    # The arguments for the JS function are passed after the script string
    up_scroll_count = web_driver.execute_async_script(scroll_up_command, down_scroll_count, 600)
    print(f"Scrolled back to top in {up_scroll_count} steps.")

    # Now the page is ready for your buildDomTree.js script
    print("\nPage is ready for DOM analysis.")


async def os_connect_to_adspower(mainwin, args):
    webdriver_path = mainwin.default_webdriver_path

    print("initial state:", args)
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
        time.sleep(2)
        webdriver.execute_script(f"window.open('{url}', '_blank');")
        time.sleep(1)
        # Switch to the new tab
        webdriver.switch_to.window(webdriver.window_handles[-1])
        time.sleep(2)
        # Navigate to the new URL in the new tab
        domTree = {}
        if url:
            webdriver.get(url)  # Replace with the new URL
            print("opened URL: " + url)
            time.sleep(5)
            page_scroll(mainwin, webdriver)

            script = mainwin.load_build_dom_tree_script()
            # print("dom tree build script to be executed", script)
            target = None
            response = execute_js_script(webdriver, script, target)
            domTree = response.get("result", {})
            logs = response.get("logs", [])
            if len(logs) > 128:
                llen = 128
            else:
                llen = len(logs)

            for i in range(llen):
                print(logs[i])

            with open("domtree.json", 'w', encoding="utf-8") as dtjf:
                json.dump(domTree, dtjf, ensure_ascii=False, indent=4)
                # self.rebuildHTML()
                dtjf.close()

            print("dom tree:", type(domTree), domTree.keys())
            top_level_nodes = find_top_level_nodes(domTree)
            print("top level nodes:", type(top_level_nodes), top_level_nodes)
            top_level_texts = get_shallowest_texts(top_level_nodes, domTree)
            tls = collect_text_nodes_by_level(domTree)
            print("level texts:", tls)
            print("level N texts:", [len(tls[i]) for i in range(len(tls))])
            for l in tls:
                if l:
                    print("level texts:", [domTree["map"][nid]["text"] for nid in l])

            sects = sectionize_dt_with_subsections(domTree)
            print("sections:", sects)
        mainwin.setWebDriver(webdriver)
        # set up output.
        msg = "completed connect to adspower."

        result = TextContent(type="text", text=f"{msg}")
        result.meta = {"dome tree": top_level_texts}

        return [result]

    except Exception as e:
        err_trace = get_traceback(e, "ErrorOSConnectToAdspower")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def os_connect_to_chrome(mainwin, args):
    webdriver_path = mainwin.default_webdriver_path

    print("inital state:", args)
    try:
        url = args["input"]["url"]

        webdriver = webDriverStartExistingChrome(args["input"]["driver_path"], args["input"]["ads_port"])
        time.sleep(1)
        webdriver.execute_script(f"window.open('{url}', '_blank');")
        time.sleep(1)
        # Switch to the new tab
        webdriver.switch_to.window(webdriver.window_handles[-1])
        time.sleep(3)
        # Navigate to the new URL in the new tab
        if url:
            webdriver.get(url)  # Replace with the new URL
            print("open URL: " + url)

        mainwin.setWebDriver(webdriver)
        # set up output.
        msg = "completed connect to chrome."
        result = [TextContent(type="text", text=msg)]
        return result

    except Exception as e:
        err_trace = get_traceback(e, "ErrorOSConnectToChrome")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]



async def os_open_app(mainwin, args):
    try:
        DETACHED_PROCESS = 0x00000008
        subprocess.Popen(args["input"]["app_name"], creationflags=DETACHED_PROCESS, shell=True, close_fds=True,
                         stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE)

        msg = "completed opening app"
        result = [TextContent(type="text", text=msg)]
        return result

    except Exception as e:
        err_trace = get_traceback(e, "ErrorOSOpenApp")
        logger.debug(err_trace)
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
        logger.debug(err_trace)
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
        logger.debug(err_trace)
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
        logger.debug(err_trace)
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
        logger.debug(err_trace)
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
        logger.debug(err_trace)
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
        logger.debug(err_trace)
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
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def os_copy_file_dir(mainwin, args):
    try:
        shutil.copy(args["input"]["src"], args["input"]["dest"])

        msg = "completed copying file dir"
        result = [TextContent(type="text", text=msg)]
        return result
    except Exception as e:
        err_trace = get_traceback(e, "ErrorOSCopyFileDir")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def os_screen_analyze(mainwin, args):
    try:
        win_title_kw = args["input"]["win_title_kw"]
        sub_area = args["input"]["sub_area"]
        site = args["input"]["site"]
        engine = args["input"]["engine"]
        screen_content = await read_screen8(mainwin, win_title_kw, sub_area, site,engine)

        msg = "completed screen analysis"
        result = [TextContent(type="text", text=msg)]
        result.meta = screen_content
        return result

    except Exception as e:
        err_trace = get_traceback(e, "ErrorOSScreenAnalyze")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def os_screen_capture(mainwin, args):
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
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def os_seven_zip(mainwin, args):
    try:
        exe = 'C:/Program Files/7-Zip/7z.exe'
        if "zip" in args["input"]["dest"]:
            # we are zipping a folder or file
            if args["input"]["dest"] != "":
                cmd_output = subprocess.call(exe + " a " + args["input"]["src"] + "-o" + args["input"]["dest"])
            else:
                cmd_output = subprocess.call(exe + " e " + args["input"]["src"])
            msg = f"completed seven zip {args['input']['src']}"
        else:
            # we are unzipping a single file
            if args["input"]["dest"] != "":
                cmd = [exe, 'e', args["input"]["src"],  f'-o{args["input"]["dest"]}']
                cmd_output = subprocess.Popen(cmd)
            else:
                cmd_output = subprocess.call(exe + " e " + args["input"]["src"])
            msg = f"completed seven unzip {args['input']['src']}"

        result = [TextContent(type="text", text=msg)]
        return result
    except Exception as e:
        err_trace = get_traceback(e, "ErrorOSSevenZip")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def os_kill_processes(mainwin, args):
    try:

        logger.debug(f'Kill Processes: {args.pids[0]}')
        msg = "completed kill processes"
        result = [TextContent(type="text", text=msg)]
        return result
    except Exception as e:
        err_trace = get_traceback(e, "ErrorOSKillProcesses")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]

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
        msg = "completed rpa supervisor scheduling work"
        result = [TextContent(type="text", text=msg)]
        return result
    except Exception as e:
        err_trace = get_traceback(e, "ErrorRPASupervisorSchedulingWork")
        logger.debug(err_trace)
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
        works_to_be_dispatched = mainwin.handleCloudScheduledWorks(workable)
        msg = "completed rpa operator dispatch works"
        result = [TextContent(type="text", text=msg)]
        return result
    except Exception as e:
        err_trace = get_traceback(e, "ErrorRPAOperatorDispatchWorks")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def rpa_supervisor_process_work_results(mainwin, args):
    # handle RPA work results from a platoon host.
    # mostly bookkeeping.
    try:
        works_to_be_dispatched = mainwin.handleCloudScheduledWorks(workable)
        msg = "completed rpa supervisor process work results"
        result = [TextContent(type="text", text=msg)]
        return result
    except Exception as e:
        err_trace = get_traceback(e, "ErrorRPASupervisorProcessWorkResults")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def rpa_supervisor_run_daily_housekeeping(mainwin, args):
    # call put work received from A2A channel, put into today's work data structure
    # the runbotworks task will then take over.....
    # including put reactive work into it.
    try:
        works_to_be_dispatched = mainwin.handleCloudScheduledWorks(workable)
        text_content = [TextContent(type="text", text=f"works dispatched")]
        return text_content
    except Exception as e:
        err_trace = get_traceback(e, "ErrorRPASupervisorRunDailyHousekeeping")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]

async def rpa_operator_report_work_results(mainwin, args):
    # call put work received from A2A channel, put into today's work data structure
    # the runbotworks task will then take over.....
    # including put reactive work into it.
    try:
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
        # Disconnect current Wi-Fi
        subprocess.run(["netsh", "wlan", "disconnect"])
        time.sleep(2)
        # Reconnect to a specific network
        cmd = ["netsh", "wlan", "connect", f"name={args['input']['network_name']}"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        msg = f"completed reconnecting wifi ({result.stdout})."
        result = [TextContent(type="text", text=msg)]
        return result
    except Exception as e:
        err_trace = get_traceback(e, "ErrorOSReconnectWifi")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def api_ecan_ai_query_components(mainwin, args):
    # call put work received from A2A channel, put into today's work data structure
    # the runbotworks task will then take over.....
    # including put reactive work into it.
    try:
        components = ecan_ai_api_query_components(mainwin, args['input']['components'])
        msg = "completed rpa operator report work results"
        result = [TextContent(type="text", text=msg)]
        result.meta = components
        return result
    except Exception as e:
        err_trace = get_traceback(e, "ErrorAPIECANAIQueryComponents")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def api_ecan_ai_img2text_icons(mainwin, args):
    # call put work received from A2A channel, put into today's work data structure
    # the runbotworks task will then take over.....
    # including put reactive work into it.
    try:
        log_user = mainwin.user.replace("@", "_").replace(".", "_")
        session = mainwin.session
        token = mainwin.tokens['AuthenticationResult']['IdToken']

        mission = mainwin.getTrialRunMission()

        screen_data = await readRandomWindow8(mission, args["input"]["win_title_keyword"], log_user, session, token)

        msg = "completed rpa operator report work results"
        result = [TextContent(type="text", text=msg)]
        result.meta = screen_data
        return result
    except Exception as e:
        err_trace = get_traceback(e, "ErrorAPIECANAIImg2TextIcons")
        logger.debug(err_trace)
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
        "in_browser_extract_content": in_browser_scrape_content,
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
        "api_ecan_ai_img2text_icons": api_ecan_ai_img2text_icons
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
