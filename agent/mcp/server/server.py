import os
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
from gui.LoginoutGUI import Login
from utils.logger_helper import login
from bot.seleniumSkill import *
from agent.ec_skill import *
from app_context import AppContext
from utils.logger_helper import logger_helper as logger

server_main_win = None
logger = logging.getLogger(__name__)

Context = TypeVar('Context')

mouse = Controller()

load_dotenv()  # load environment variables from .env

# meca_mcp_server = FastMCP("E-Commerce Agents Service")
meca_mcp_server = Server("E-Commerce Agents Service")
meca_sse = SseServerTransport("/messages/")

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
    login: Login = ctx.login
    # 获取用户名和密码
    if tool_name in tool_function_mapping:
        try:
            result = await tool_function_mapping[tool_name](login.main_win, args)
            print("unified_tool_handler after call", type(result), result)
        except Exception as e:
            # Get the traceback information
            traceback_info = traceback.extract_tb(e.__traceback__)
            # Extract the file name and line number from the last entry in the traceback
            if traceback_info:
                ex_stat = "ErrorCallTool:" + traceback.format_exc() + " " + str(e)
            else:
                ex_stat = "ErrorCallTool: traceback information not available:" + str(e)
            result  = CallToolResult(content=[TextContent(type="text", text=ex_stat)], isError=True)
    else:
        result = CallToolResult(content=[TextContent(type="text", text="ErrorCallTool: tool NOT found!")], isError=False)

    print("unified_tool_handler.......", type(result), result)
    return result

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
    return CallToolResult(content=[TextContent(type="text", text=msg)], meta={"# bots": len(login.main_win.bots)}, include_in_memory=False)


async def os_wait(mainwin, args):
    msg = f'🕒  Waiting for {args["seconds"]} seconds'
    logger.info(msg)
    await asyncio.sleep(args["seconds"])
    return CallToolResult(content=[TextContent(type="text", text=msg)], isError=False)


async def in_browser_wait_for_element(mainwin, args):
    """Waits for the element specified by the CSS selector to become visible within the given timeout."""
    try:
        web_driver = mainwin.web_driver
        wait = WebDriverWait(web_driver, args.timeout)

        args.tool_result = wait.until(EC.element_to_be_clickable((args.tool_input["element_type"], args.tool_input["element_name"])))

        return CallToolResult(content=[TextContent(type="text", text=msg)], isError=False)
    except Exception as e:
        err_msg = f'❌  Failed to wait for element "{args.selector}" within {args.timeout}ms: {str(e)}'
        logger.error(err_msg)
        raise Exception(err_msg)


# Element Interaction Actions
async def in_browser_click_element_by_index(mainwin, params):
    browser_context = login.main_win.getBrowserContextById(params["context_id"])
    browser = browser_context.browser
    session = await browser.get_session()

    if params.index not in await browser.get_selector_map():
        raise Exception(f'Element with index {params.index} does not exist - retry or use alternative actions')

    element_node = await browser.get_dom_element_by_index(params.index)
    initial_pages = len(session.pages)

    # if element has file uploader then dont click
    if await browser.is_file_uploader(element_node):
        msg = f'Index {params.index} - has an element which opens file upload dialog. To upload files please use a specific function to upload files '
        logger.info(msg)
        return CallToolResult(content=[TextContent(type="text", text=msg)], isError=False)

    msg = None

    try:
        download_path = await browser._click_element_node(element_node)
        if download_path:
            msg = f'💾  Downloaded file to {download_path}'
        else:
            msg = f'🖱️  Clicked button with index {params.index}: {element_node.get_all_text_till_next_clickable_element(max_depth=2)}'

        logger.info(msg)
        logger.debug(f'Element xpath: {element_node.xpath}')
        if len(session.pages) > initial_pages:
            new_tab_msg = 'New tab opened - switching to it'
            msg += f' - {new_tab_msg}'
            logger.info(new_tab_msg)
            await browser.switch_to_tab(-1)
        return CallToolResult(content=[TextContent(type="text", text=msg)], isError=False)
    except Exception as e:
        logger.warning(f'Element not clickable with index {params.index} - most likely the page changed')
        return CallToolResult(error=str(e))


async def in_browser_click_element_by_selector(mainwin, params):
    try:
        browser_context = login.main_win.getBrowserContextById(params["context_id"])
        browser = browser_context.browser
        element_node = await browser.get_locate_element_by_css_selector(params.css_selector)
        if element_node:
            try:
                await element_node.scroll_into_view_if_needed()
                await element_node.click(timeout=1500, force=True)
            except Exception:
                try:
                    # Handle with js evaluate if fails to click using playwright
                    await element_node.evaluate('el => el.click()')
                except Exception as e:
                    logger.warning(f"Element not clickable with css selector '{params.css_selector}' - {e}")
                    return CallToolResult(error=str(e))
            msg = f'🖱️  Clicked on element with text "{params.css_selector}"'
            return CallToolResult(content=[TextContent(type="text", text=msg)], isError=False)
    except Exception as e:
        logger.warning(f'Element not clickable with selector {params.css_selector} - most likely the page changed')
        return CallToolResult(error=str(e))


async def in_browser_click_element_by_xpath(mainwin, params):
    try:
        browser_context = login.main_win.getBrowserContextById(params["context_id"])
        browser = browser_context.browser
        element_node = await browser.get_locate_element_by_xpath(params.xpath)
        if element_node:
            try:
                await element_node.scroll_into_view_if_needed()
                await element_node.click(timeout=1500, force=True)
            except Exception:
                try:
                    # Handle with js evaluate if fails to click using playwright
                    await element_node.evaluate('el => el.click()')
                except Exception as e:
                    logger.warning(f"Element not clickable with xpath '{params.xpath}' - {e}")
                    return CallToolResult(error=str(e))
            msg = f'🖱️  Clicked on element with text "{params.xpath}"'
            return CallToolResult(content=[TextContent(type="text", text=msg)], isError=False)
    except Exception as e:
        logger.warning(f'Element not clickable with xpath {params.xpath} - most likely the page changed')
        return CallToolResult(error=str(e))


async def in_browser_click_element_by_text(mainwin, params):
    try:
        browser_context = login.main_win.getBrowserContextById(params["context_id"])
        browser = browser_context.browser
        element_node = await browser.get_locate_element_by_text(
            text=params.text, nth=params.nth, element_type=params.element_type
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
                    logger.warning(f"Element not clickable with text '{params.text}' - {e}")
                    return CallToolResult(error=str(e))
            msg = f'🖱️  Clicked on element with text "{params.text}"'
            return CallToolResult(content=[TextContent(type="text", text=msg)], isError=False)
        else:
            return CallToolResult(error=f"No element found for text '{params.text}'")
    except Exception as e:
        logger.warning(f"Element not clickable with text '{params.text}' - {e}")
        return CallToolResult(error=str(e))


async def in_browser_input_text(mainwin, params):
    browser_context = login.main_win.getBrowserContextById(params["context_id"])
    browser = browser_context.browser
    if params.index not in await browser.get_selector_map():
        raise Exception(f'Element index {params.index} does not exist - retry or use alternative actions')

    element_node = await browser.get_dom_element_by_index(params.index)
    await browser._input_text_element_node(element_node, params.text)
    if not has_sensitive_data:
        msg = f'⌨️  Input {params.text} into index {params.index}'
    else:
        msg = f'⌨️  Input sensitive data into index {params.index}'
    logger.info(msg)
    logger.debug(f'Element xpath: {element_node.xpath}')
    return CallToolResult(content=[TextContent(type="text", text=msg)], isError=False)


# Save PDF
async def in_browser_save_pdf(mainwin, params):
    page = await browser.get_current_page()
    short_url = re.sub(r'^https?://(?:www\.)?|/$', '', page.url)
    slug = re.sub(r'[^a-zA-Z0-9]+', '-', short_url).strip('-').lower()
    sanitized_filename = f'{slug}.pdf'

    await page.emulate_media('screen')
    await page.pdf(path=sanitized_filename, format='A4', print_background=False)
    msg = f'Saving page with URL {page.url} as PDF to ./{sanitized_filename}'
    logger.info(msg)
    return CallToolResult(content=[TextContent(type="text", text=msg)], isError=False)


# Tab Management Actions
async def in_browser_switch_tab(mainwin, params):
    await browser.switch_to_tab(params.page_id)
    # Wait for tab to be ready
    page = await browser.get_current_page()
    await page.wait_for_load_state()
    msg = f'🔄  Switched to tab {params.page_id}'
    logger.info(msg)
    return CallToolResult(content=[TextContent(type="text", text=msg)], isError=False)


async def in_browser_open_tab(mainwin, params):
    browser_context = mainwin.getBrowserContextById(params["context_id"])
    browser = browser_context.browser
    await browser.create_new_tab(params.url)
    msg = f'🔗  Opened new tab with {params.url}'
    logger.info(msg)
    return CallToolResult(content=[TextContent(type="text", text=msg)], isError=False)


async def in_browser_close_tab(mainwin, params):
    browser_context = mainwin.getBrowserContextById(params["context_id"])
    browser = browser_context.browser
    await browser.switch_to_tab(params.page_id)
    page = await browser.get_current_page()
    url = page.url
    await page.close()
    msg = f'❌  Closed tab #{params.page_id} with url {url}'
    logger.info(msg)
    return CallToolResult(content=[TextContent(type="text", text=msg)], isError=False)


# Content Actions
async def in_browser_scrape_content(mainwin, params):
    try:
        web_driver = mainwin.web_driver
        dom_service = mainwin.dom_service
        dom_service.get_clickable_elements()

    except Exception as e:
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorCallToolScrapeContents:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorCallToolScrapeContents: traceback information not available:" + str(e)
        print("ex_stat:", ex_stat)
        err_text_content = [TextContent(type="text", text=f"Error in scheduler: {ex_stat}")]
        return CallToolResult(content=err_text_content, isError=True)


async def in_browser_execute_javascript(mainwin, state: NodeState) -> NodeState:
    try:
        web_driver = mainwin.web_driver
        result = execute_js_script(web_driver, state.tool_input["script"], state.tool_input["target"])

    except Exception as e:
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorCallToolScrapeContents:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorCallToolScrapeContents: traceback information not available:" + str(e)
        print("ex_stat:", ex_stat)
        err_text_content = [TextContent(type="text", text=f"Error in scheduler: {ex_stat}")]
        return CallToolResult(content=err_text_content, isError=True)



async def in_browser_build_dom_tree(mainwin, params):
    try:
        global server_main_win
        web_driver = server_main_win.web_driver
        dom_service = server_main_win.dom_service
        dom_service.get_clickable_elements()

    except Exception as e:
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorCallToolScrapeContents:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorCallToolScrapeContents: traceback information not available:" + str(e)
        print("ex_stat:", ex_stat)
        err_text_content = [TextContent(type="text", text=f"Error in scheduler: {ex_stat}")]
        return CallToolResult(content=err_text_content, isError=True)




# HTML Download
async def in_browser_save_html_to_file(mainwin, params) -> CallToolResult:
    """Retrieves and returns the full HTML content of the current page to a file"""
    try:
        browser_context = login.main_win.getBrowserContextById(params["context_id"])
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
        return CallToolResult(content=[TextContent(type="text", text=msg)], isError=False)
    except Exception as e:
        error_msg = f'Failed to save HTML content: {str(e)}'
        logger.error(error_msg)
        return CallToolResult(error=error_msg, content='')


async def in_browser_scroll_down(mainwin, params):
    browser_context = login.main_win.getBrowserContextById(params["context_id"])
    browser = browser_context.browser
    page = await browser.get_current_page()
    if params.amount is not None:
        await page.evaluate(f'window.scrollBy(0, {params.amount});')
    else:
        await page.evaluate('window.scrollBy(0, window.innerHeight);')

    amount = f'{params.amount} pixels' if params.amount is not None else 'one page'
    msg = f'🔍  Scrolled down the page by {amount}'
    logger.info(msg)
    return CallToolResult(
        content=[msg],
        isError=False,
    )


# scroll up
async def in_browser_scroll_up(mainwin, params):
    browser_context = login.main_win.getBrowserContextById(params["context_id"])
    browser = browser_context.browser
    page = await browser.get_current_page()
    if params.amount is not None:
        await page.evaluate(f'window.scrollBy(0, -{params.amount});')
    else:
        await page.evaluate('window.scrollBy(0, -window.innerHeight);')

    amount = f'{params.amount} pixels' if params.amount is not None else 'one page'
    msg = f'🔍  Scrolled up the page by {amount}'
    logger.info(msg)
    return CallToolResult(
        content=[msg],
        isError=False,
    )


# send keys
async def in_browser_send_keys(mainwin, params):
    browser_context = login.main_win.getBrowserContextById(params["context_id"])
    browser = browser_context.browser
    page = await browser.get_current_page()

    try:
        await page.keyboard.press(params.keys)
    except Exception as e:
        if 'Unknown key' in str(e):
            # loop over the keys and try to send each one
            for key in params.keys:
                try:
                    await page.keyboard.press(key)
                except Exception as e:
                    logger.debug(f'Error sending key {key}: {str(e)}')
                    raise e
        else:
            raise e
    msg = f'⌨️  Sent keys: {params.keys}'
    logger.info(msg)
    return CallToolResult(content=[msg], isError=False)


async def in_browser_scroll_to_text(mainwin, params):  # type: ignore
    page = await browser.get_current_page()
    try:
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
        return CallToolResult(content=[TextContent(type="text", text=msg)], isError=False)

    except Exception as e:
        msg = f"Failed to scroll to text '{text}': {str(e)}"
        logger.error(msg)
        return CallToolResult(error=[TextContent(type="text", text=msg)], isError=False)


async def in_browser_get_dropdown_options(mainwin, params) -> CallToolResult:
    """Get all options from a native dropdown"""
    browser_context = login.main_win.getBrowserContextById(params["context_id"])
    browser = browser_context.browser
    page = await browser.get_current_page()
    selector_map = await browser.get_selector_map()
    dom_element = selector_map[index]

    try:
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
            return CallToolResult(content=[TextContent(type="text", text=msg)], isError=False)
        else:
            msg = 'No options found in any frame for dropdown'
            logger.info(msg)
            return CallToolResult(content=[TextContent(type="text", text=msg)], isError=False)

    except Exception as e:
        logger.error(f'Failed to get dropdown options: {str(e)}')
        msg = f'Error getting options: {str(e)}'
        logger.info(msg)
        return CallToolResult(content=[TextContent(type="text", text=msg)], isError=False)


async def in_browser_select_dropdown_option(mainwin, params) -> CallToolResult:
    """Select dropdown option by the text of the option you want to select"""
    browser_context = login.main_win.getBrowserContextById(params["context_id"])
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

    try:
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
        return CallToolResult(content=[TextContent(type="text", text=msg)], isError=False)

    except Exception as e:
        msg = f'Selection failed: {str(e)}'
        logger.error(msg)
        return CallToolResult(error=[TextContent(type="text", text=msg)], isError=False)


async def in_browser_drag_drop(mainwin, params) -> CallToolResult:
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
        # Initialize variables
        source_x: Optional[int] = None
        source_y: Optional[int] = None
        target_x: Optional[int] = None
        target_y: Optional[int] = None

        # Normalize parameters
        steps = max(1, params.steps or 10)
        delay_ms = max(0, params.delay_ms or 5)

        # Case 1: Element selectors provided
        if params.element_source and params.element_target:
            logger.debug('Using element-based approach with selectors')

            source_element, target_element = await get_drag_elements(
                page,
                params.element_source,
                params.element_target,
            )

            if not source_element or not target_element:
                error_msg = f'Failed to find {"source" if not source_element else "target"} element'
                return CallToolResult(content = [TextContent(type="text", text=error_msg)], isError=False)

            source_coords, target_coords = await get_element_coordinates(
                source_element, target_element, params.element_source_offset, params.element_target_offset
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
                [params.coord_source_x, params.coord_source_y, params.coord_target_x, params.coord_target_y]
        ):
            logger.debug('Using coordinate-based approach')
            source_x = params.coord_source_x
            source_y = params.coord_source_y
            target_x = params.coord_target_x
            target_y = params.coord_target_y
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
        if params.element_source and params.element_target:
            msg = f"🖱️ Dragged element '{params.element_source}' to '{params.element_target}'"
        else:
            msg = f'🖱️ Dragged from ({source_x}, {source_y}) to ({target_x}, {target_y})'

        logger.info(msg)
        return CallToolResult(content=[TextContent(type="text", text=msg)], isError=False)

    except Exception as e:
        error_msg = f'Failed to perform drag and drop: {str(e)}'
        logger.error(error_msg)
        return CallToolResult(content=[TextContent(type="text", text=error_msg)], isError=True)


async def mouse_click(mainwin, params):
    print("INPUT:", params)
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
        pyautogui.moveTo(params.loc.x, params.loc.y)
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


async def mouse_move(mainwin, params):
    browser_context = login.main_win.getBrowserContextById(params["context_id"])
    browser = browser_context.browser
    if params.index not in await browser.get_selector_map():
        raise Exception(f'Element index {params.index} does not exist - retry or use alternative actions')

    pyautogui.moveTo(params.loc.x, params.loc.y)

    logger.debug(f'Element xpath: {params.loc.x},  {params.loc.y}')
    msg = ""
    return CallToolResult(content=[TextContent(type="text", text=msg)], isError=False)


async def mouse_drag_drop(mainwin, params):
    browser_context = login.main_win.getBrowserContextById(params["context_id"])
    browser = browser_context.browser
    if params.index not in await browser.get_selector_map():
        raise Exception(f'Element index {params.index} does not exist - retry or use alternative actions')

    pyautogui.moveTo(params.pick_loc.x, params.pick_loc.y)
    pyautogui.dragTo(params.drop_loc.x, params.drop_loc.y, duration=params.duration)

    logger.debug(f'dragNdrop: {params.pick_loc.x}, {params.pick_loc.y} to {params.drop_loc.x}, {params.drop_loc.y}')
    msg = ""
    return CallToolResult(content=[TextContent(type="text", text=msg)], isError=False)


async def mouse_scroll(mainwin, params):
    browser_context = login.main_win.getBrowserContextById(params["context_id"])
    browser = browser_context.browser
    if params.index not in await browser.get_selector_map():
        raise Exception(f'Element index {params.index} does not exist - retry or use alternative actions')

    if params.direction == "down":
        scroll_amount = 0 - params.amount
    else:
        scroll_amount = params.amount
    mouse.scroll(0, scroll_amount)

    logger.debug(f'Element xpath: {scroll_amount}')
    msg = ""
    return CallToolResult(content=[TextContent(type="text", text=msg)], isError=False)


async def keyboard_text_input(mainwin, params):
    browser_context = login.main_win.getBrowserContextById(params["context_id"])
    browser = browser_context.browser
    if params.index not in await browser.get_selector_map():
        raise Exception(f'Element index {params.index} does not exist - retry or use alternative actions')

    pyautogui.write(params.text, interval=params.interval)

    logger.debug(f'Element xpath: {params.text},  {params.interval}')
    msg = ""
    return CallToolResult(content=[TextContent(type="text", text=msg)], isError=False)


async def keyboard_keys_input(mainwin, params):
    browser_context = login.main_win.getBrowserContextById(params["context_id"])
    browser = browser_context.browser
    if params.index not in await browser.get_selector_map():
        raise Exception(f'Element index {params.index} does not exist - retry or use alternative actions')

    pyautogui.hotkey(*params.combo)

    logger.debug(f'hot keys: {params.combo[0]}')
    msg = ""
    return CallToolResult(content=[TextContent(type="text", text=msg)], isError=False)


async def http_call_api(mainwin, params):
    browser_context = login.main_win.getBrowserContextById(params["context_id"])
    browser = browser_context.browser
    if params.index not in await browser.get_selector_map():
        raise Exception(f'Element index {params.index} does not exist - retry or use alternative actions')

    pyautogui.moveTo(params.loc.x, params.loc.y)

    logger.debug(f'Element xpath: {params.loc.x},  {params.loc.y}')
    msg = ""
    return CallToolResult(content=[TextContent(type="text", text=msg)], isError=False)

async def os_connect_to_adspower(mainwin, params):
    browser_context = login.main_win.getBrowserContextById(params["context_id"])
    browser = browser_context.browser
    if params.index not in await browser.get_selector_map():
        raise Exception(f'Element index {params.index} does not exist - retry or use alternative actions')

    DETACHED_PROCESS = 0x00000008
    subprocess.Popen(params.app_name, creationflags=DETACHED_PROCESS, shell=True, close_fds=True,
                     stdout=subprocess.PIPE,
                     stderr=subprocess.PIPE)

    logger.debug(f'Element xpath: {params.loc.x},  {params.loc.y}')
    msg = ""
    return CallToolResult(content=[TextContent(type="text", text=msg)], isError=False)



async def os_open_app(mainwin, params):
    browser_context = login.main_win.getBrowserContextById(params["context_id"])
    browser = browser_context.browser
    if params.index not in await browser.get_selector_map():
        raise Exception(f'Element index {params.index} does not exist - retry or use alternative actions')

    DETACHED_PROCESS = 0x00000008
    subprocess.Popen(params.app_name, creationflags=DETACHED_PROCESS, shell=True, close_fds=True,
                     stdout=subprocess.PIPE,
                     stderr=subprocess.PIPE)

    logger.debug(f'Element xpath: {params.loc.x},  {params.loc.y}')
    msg = ""
    return CallToolResult(content=[TextContent(type="text", text=msg)], isError=False)


async def os_close_app(mainwin, params):
    browser_context = login.main_win.getBrowserContextById(params["context_id"])
    browser = browser_context.browser
    if params.index not in await browser.get_selector_map():
        raise Exception(f'Element index {params.index} does not exist - retry or use alternative actions')

    app_window = gw.getWindowsWithTitle(params.win_title)[0]
    app_window.close()

    logger.debug(f'Element xpath: {params.loc.x},  {params.loc.y}')
    msg = ""
    return CallToolResult(content=[TextContent(type="text", text=msg)], isError=False)


async def os_switch_to_app(mainwin, params):
    browser_context = login.main_win.getBrowserContextById(params["context_id"])
    browser = browser_context.browser
    if params.index not in await browser.get_selector_map():
        raise Exception(f'Element index {params.index} does not exist - retry or use alternative actions')

    # Find the window by its title
    target_window = gw.getWindowsWithTitle(params.win_title)[0]

    # Activate the window (bring it to front)
    target_window.activate()

    logger.debug(f'Element xpath: {params.loc.x},  {params.loc.y}')
    msg = ""
    return CallToolResult(content=[TextContent(type="text", text=msg)], isError=False)


async def python_run_extern(mainwin, params):
    browser_context = login.main_win.getBrowserContextById(params["context_id"])
    browser = browser_context.browser
    if params.index not in await browser.get_selector_map():
        raise Exception(f'Element index {params.index} does not exist - retry or use alternative actions')

    time.sleep(params.time)

    logger.debug(f'Element xpath: {params.loc.x},  {params.loc.y}')
    msg = ""
    return CallToolResult(content=[TextContent(type="text", text=msg)], isError=False)


async def os_make_dir(mainwin, params):
    browser_context = login.main_win.getBrowserContextById(params["context_id"])
    browser = browser_context.browser
    if params.index not in await browser.get_selector_map():
        raise Exception(f'Element index {params.index} does not exist - retry or use alternative actions')

    if not os.path.exists(params.dir_path):
        # create only if the dir doesn't exist
        os.makedirs(params.dir_path)

    logger.debug(f'Element xpath: {params.loc.x},  {params.loc.y}')
    msg = ""
    return CallToolResult(content=[TextContent(type="text", text=msg)], isError=False)


async def os_delete_dir(mainwin, params):
    browser_context = login.main_win.getBrowserContextById(params["context_id"])
    browser = browser_context.browser
    if params.index not in await browser.get_selector_map():
        raise Exception(f'Element index {params.index} does not exist - retry or use alternative actions')

    if os.path.exists(params.dir_path):
        # create only if the dir doesn't exist
        os.remove(params.dir_path)

    logger.debug(f'Element xpath: {params.loc.x},  {params.loc.y}')
    msg = ""
    return CallToolResult(content=[TextContent(type="text", text=msg)], isError=False)


async def os_delete_file(mainwin, params):
    browser_context = login.main_win.getBrowserContextById(params["context_id"])
    browser = browser_context.browser
    if params.index not in await browser.get_selector_map():
        raise Exception(f'Element index {params.index} does not exist - retry or use alternative actions')

    if os.path.exists(params.file):
        # create only if the dir doesn't exist
        os.remove(params.file)

    logger.debug(f'Element xpath: {params.loc.x},  {params.loc.y}')
    msg = ""
    return CallToolResult(content=[TextContent(type="text", text=msg)], isError=False)


async def os_move_file(mainwin, params):
    browser_context = login.main_win.getBrowserContextById(params["context_id"])
    browser = browser_context.browser
    if params.index not in await browser.get_selector_map():
        raise Exception(f'Element index {params.index} does not exist - retry or use alternative actions')

    # default_download_dir = getDefaultDownloadDirectory()
    # new_file = getMostRecentFile(default_download_dir, prefix=step["prefix"], extension=step["extension"])

    shutil.move(params.src, params.dest)

    logger.debug(f'Element xpath: {params.loc.x},  {params.loc.y}')

    msg = ""
    return CallToolResult(content=[TextContent(type="text", text=msg)], isError=False)


async def os_copy_file_dir(mainwin, params):
    browser_context = login.main_win.getBrowserContextById(params["context_id"])
    browser = browser_context.browser
    if params.index not in await browser.get_selector_map():
        raise Exception(f'Element index {params.index} does not exist - retry or use alternative actions')

    shutil.copy(params.src, params.dest)

    logger.debug(f'Element xpath: {params.loc.x},  {params.loc.y}')
    msg = ""
    return CallToolResult(content=[TextContent(type="text", text=msg)], isError=False)


async def os_screen_analyze(mainwin, params):
    browser_context = login.main_win.getBrowserContextById(params["context_id"])
    browser = browser_context.browser
    if params.index not in await browser.get_selector_map():
        raise Exception(f'Element index {params.index} does not exist - retry or use alternative actions')

    element_node = await browser.get_dom_element_by_index(params.index)
    nClicks = 1
    interval = 0.1
    pyautogui.click(clicks=nClicks, interval=interval)
    if not has_sensitive_data:
        msg = f'⌨️  Input {params.text} into index {params.index}'
    else:
        msg = f'⌨️  Input sensitive data into index {params.index}'
    logger.info(msg)
    logger.debug(f'Element xpath: {element_node.xpath}')
    return CallToolResult(content=[TextContent(type="text", text=msg)], isError=False)


async def os_screen_capture(mainwin, params):
    browser_context = login.main_win.getBrowserContextById(params["context_id"])
    browser = browser_context.browser
    if params.index not in await browser.get_selector_map():
        raise Exception(f'Element index {params.index} does not exist - retry or use alternative actions')

    screen_img, window_rect = await takeScreenShot(params.win_title_kw)
    img_section = carveOutImage(screen_img, params.sub_area, "")
    maskOutImage(img_section, params.sub_area, "")

    saveImageToFile(img_section, params.file, "png")

    logger.debug(f'Element xpath: {params.win_title_kw}')
    msg = ""
    return CallToolResult(content=[TextContent(type="text", text=msg)], isError=False)


async def os_seven_zip(mainwin, params):
    browser_context = login.main_win.getBrowserContextById(context_id)
    browser = browser_context.browser
    if params.index not in await browser.get_selector_map():
        raise Exception(f'Element index {params.index} does not exist - retry or use alternative actions')

    logger.debug(f'Element xpath: {params.file}')
    msg = ""
    return CallToolResult(content=[TextContent(type="text", text=msg)], meta={}, isError=False)



async def os_kill_processes(mainwin, params):
    browser_context = login.main_win.getBrowserContextById(params["context_id"])
    browser = browser_context.browser
    if params.index not in await browser.get_selector_map():
        raise Exception(f'Element index {params.index} does not exist - retry or use alternative actions')

    logger.debug(f'Kill Processes: {params.pids[0]}')
    msg = ""
    return CallToolResult(content=[TextContent(type="text", text=msg)], isError=False)


# Element Interaction Actions
async def rpa_supervisor_scheduling_work(mainwin, params) -> CallToolResult:
    print("INPUT:", params)
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
            ex_stat = "ErrorCallTool:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorCallTool: traceback information not available:" + str(e)
        print("ex_stat:", ex_stat)
        err_text_content = [TextContent(type="text", text=f"Error in scheduler: {ex_stat}")]
        return CallToolResult(content=err_text_content, isError=True)


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
async def rpa_operator_dispatch_works(mainwin, params):
    # call put work received from A2A channel, put into today's work data structure
    # the runbotworks task will then take over.....
    # including put reactive work into it.
    try:
        works_to_be_dispatched = login.main_win.handleCloudScheduledWorks(workable)
        text_content = [TextContent(type="text", text=f"works dispatched")]
        return CallToolResult(content=text_content, isError=False)
    except Exception as e:
        logger.warning(f'RPA Supervisor Work failure')
        text_content = [TextContent(type="text", text=str(e))]
        return CallToolResult(content=text_content, isError=False)


async def rpa_supervisor_process_work_results(mainwin, params):
    # handle RPA work results from a platoon host.
    # mostly bookkeeping.
    try:
        works_to_be_dispatched = login.main_win.handleCloudScheduledWorks(workable)
        text_content = [TextContent(type="text", text=f"works dispatched")]
        return CallToolResult(content=text_content, isError=False)
    except Exception as e:
        logger.warning(f'RPA Supervisor Work failure')
        text_content = [TextContent(type="text", text=str(e))]
        return CallToolResult(content=text_content, isError=False)


async def rpa_supervisor_run_daily_housekeeping(mainwin, params):
    # call put work received from A2A channel, put into today's work data structure
    # the runbotworks task will then take over.....
    # including put reactive work into it.
    try:
        works_to_be_dispatched = login.main_win.handleCloudScheduledWorks(workable)
        text_content = [TextContent(type="text", text=f"works dispatched")]
        return CallToolResult(content=text_content, isError=False)
    except Exception as e:
        logger.warning(f'RPA Supervisor Work failure')
        text_content = [TextContent(type="text", text=str(e))]
        return CallToolResult(content=text_content, isError=False)

async def rpa_operator_report_work_results(mainwin, params):
    # call put work received from A2A channel, put into today's work data structure
    # the runbotworks task will then take over.....
    # including put reactive work into it.
    try:
        works_to_be_dispatched = login.main_win.handleCloudScheduledWorks(workable)
        text_content = [TextContent(type="text", text=f"works dispatched")]
        return CallToolResult(content=text_content, isError=False)
    except Exception as e:
        logger.warning(f'RPA Supervisor Work failure')
        text_content = [TextContent(type="text", text=str(e))]
        return CallToolResult(content=text_content, isError=True)


async def reconnect_wifi(mainwin, params):
    # Disconnect current Wi-Fi
    subprocess.run(["netsh", "wlan", "disconnect"])
    time.sleep(2)

    # Reconnect to a specific network
    cmd = ["netsh", "wlan", "connect", f"name={params['network_name']}"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    print(result.stdout)


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
        "reconnect_wifi": reconnect_wifi
    }

def set_server_main_win(mw):
    global server_main_win
    server_main_win = mw


async def handle_sse(scope, receive, send):
    print(">>> sse connected")
    async with meca_sse.connect_sse(scope, receive, send) as streams:
        print("handling meca_mcp_server.run", streams)
        await meca_mcp_server.run(streams[0], streams[1], meca_mcp_server.create_initialization_options())

async def sse_handle_messages(scope, receive, send):
    print(">>> sse handle messages connected")
    await meca_sse.handle_post_message(scope, receive, send)

