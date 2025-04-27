import os
from mcp.server.sse import SseServerTransport
from mcp.server.fastmcp.prompts import base
from starlette.applications import Starlette
from starlette.routing import Route
from selenium import webdriver
from mcp.server.fastmcp import FastMCP, Image, Context
from PIL import Image as PILImage
import httpx
import pyautogui
import pynput
from pynput.mouse import Controller
import pygetwindow as gw
import sqlite3
import time
import asyncio
from typing import Dict, Generic, Optional, Tuple, Type, TypeVar, cast
from contextlib import AsyncExitStack
import re
import subprocess
import mcp.types as types
from mcp.server.lowlevel import Server
import traceback
from mcp.client.sse import sse_client
from mcp.client.session import ClientSession
from mcp.server.fastmcp.prompts import base
from mcp.types import CallToolResult, TextContent, Prompt, PromptMessage, Tool, ImageContent, EmbeddedResource, Resource, GetPromptResult, PromptArgument
from agent.mcp.server.tool_schemas import *
from pydantic import FileUrl
from agent.a2a.common.types import AgentCard
import json
from dotenv import load_dotenv
import logging
from agent.models import ActionResult
from browser.context import BrowserContext
from agent.runner.registry.service import Registry
from datetime import datetime
from agent.runner.models import (
	ClickElementAction,
	ClickElementBySelectorAction,
	ClickElementByTextAction,
	ClickElementByXpathAction,
	CloseTabAction,
	DoneAction,
	DragDropAction,
	GoToUrlAction,
	InputTextAction,
	NoParamsAction,
	OpenTabAction,
	Position,
	ScrollAction,
	SearchGoogleAction,
	SendKeysAction,
	SwitchTabAction,
	WaitForElementAction,
	MouseClickAction,
	MouseMoveAction,
	MouseDragDropAction,
	MouseScrollAction,
	TextInputAction,
	KeysAction,
	OpenAppAction,
	CloseAppAction,
	SwitchToAppAction,
	CallAPIAction,
	WaitAction,
	RunExternAction,
	MakeDirAction,
	DeleteFileAction,
	DeleteDirAction,
	MoveFileAction,
	CopyFileDirAction,
	ScreenAnalyzeAction,
	ScreenCaptureAction,
	SevenZipAction,
	KillProcessesAction,
)
import shutil
from bot.basicSkill import takeScreenShot, carveOutImage, maskOutImage, saveImageToFile
from utils.logger_helper import login
from langchain_core.language_models.chat_models import BaseChatModel

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
    all_tools = get_tool_schemas()
    print(f"# of listed mcp tools:{len(all_tools)}, {all_tools[-1]}")
    return all_tools



@meca_mcp_server.call_tool()
async def unified_tool_handler(tool_name, args):
    if tool_name in tool_function_mapping:
        try:
            result = await tool_function_mapping[tool_name](args)
        except Exception as e:
            # Get the traceback information
            traceback_info = traceback.extract_tb(e.__traceback__)
            # Extract the file name and line number from the last entry in the traceback
            if traceback_info:
                ex_stat = "ErrorCallTool:" + traceback.format_exc() + " " + str(e)
            else:
                ex_stat = "ErrorCallTool: traceback information not available:" + str(e)
            result  = CallToolResult(content=[ex_stat], isError=False)
    else:
        result = CallToolResult(content=['ErrorCallTool: tool NOT found!'], isError=False)
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


async def say_hello(params):
    msg = f'Hi There!'
    logger.info(msg)
    return CallToolResult(content=[msg], meta={"# bots": len(login.main_win.bots)}, include_in_memory=False)


async def wait(params):
    msg = f'🕒  Waiting for {params["seconds"]} seconds'
    logger.info(msg)
    await asyncio.sleep(params["seconds"])
    return CallToolResult(content=[msg], isError=False)


async def in_browser_wait_for_element(params):
    """Waits for the element specified by the CSS selector to become visible within the given timeout."""
    try:
        browser_context = login.main_win.getBrowserContextById(params["context_id"])
        browser = browser_context.browser
        await browser.wait_for_element(params.selector, params.timeout)
        msg = f'👀  Element with selector "{params.selector}" became visible within {params.timeout}ms.'
        logger.info(msg)
        return CallToolResult(content=[msg], isError=False)
    except Exception as e:
        err_msg = f'❌  Failed to wait for element "{params.selector}" within {params.timeout}ms: {str(e)}'
        logger.error(err_msg)
        raise Exception(err_msg)


# Element Interaction Actions
async def in_browser_click_element_by_index(params):
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
        return CallToolResult(content=[msg], isError=False)

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
        return CallToolResult(content=[msg], isError=False)
    except Exception as e:
        logger.warning(f'Element not clickable with index {params.index} - most likely the page changed')
        return CallToolResult(error=str(e))


async def in_browser_click_element_by_selector(params):
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
            return CallToolResult(content=[msg], isError=False)
    except Exception as e:
        logger.warning(f'Element not clickable with selector {params.css_selector} - most likely the page changed')
        return CallToolResult(error=str(e))


async def in_browser_click_element_by_xpath(params):
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
            return CallToolResult(content=[msg], isError=False)
    except Exception as e:
        logger.warning(f'Element not clickable with xpath {params.xpath} - most likely the page changed')
        return CallToolResult(error=str(e))


async def in_browser_click_element_by_text(params):
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
            return CallToolResult(content=[msg], isError=False)
        else:
            return CallToolResult(error=f"No element found for text '{params.text}'")
    except Exception as e:
        logger.warning(f"Element not clickable with text '{params.text}' - {e}")
        return CallToolResult(error=str(e))


async def in_browser_input_text(params):
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
    return CallToolResult(content=[msg], isError=False)


# Save PDF
async def in_browser_save_pdf(params):
    page = await browser.get_current_page()
    short_url = re.sub(r'^https?://(?:www\.)?|/$', '', page.url)
    slug = re.sub(r'[^a-zA-Z0-9]+', '-', short_url).strip('-').lower()
    sanitized_filename = f'{slug}.pdf'

    await page.emulate_media('screen')
    await page.pdf(path=sanitized_filename, format='A4', print_background=False)
    msg = f'Saving page with URL {page.url} as PDF to ./{sanitized_filename}'
    logger.info(msg)
    return CallToolResult(content=[msg], isError=False)


# Tab Management Actions
async def in_browser_switch_tab(params):
    await browser.switch_to_tab(params.page_id)
    # Wait for tab to be ready
    page = await browser.get_current_page()
    await page.wait_for_load_state()
    msg = f'🔄  Switched to tab {params.page_id}'
    logger.info(msg)
    return CallToolResult(content=[msg], isError=False)


async def in_browser_open_tab(params):
    browser_context = login.main_win.getBrowserContextById(params["context_id"])
    browser = browser_context.browser
    await browser.create_new_tab(params.url)
    msg = f'🔗  Opened new tab with {params.url}'
    logger.info(msg)
    return CallToolResult(content=[msg], isError=False)


async def in_browser_close_tab(params):
    browser_context = login.main_win.getBrowserContextById(params["context_id"])
    browser = browser_context.browser
    await browser.switch_to_tab(params.page_id)
    page = await browser.get_current_page()
    url = page.url
    await page.close()
    msg = f'❌  Closed tab #{params.page_id} with url {url}'
    logger.info(msg)
    return CallToolResult(content=[msg], isError=False)


# Content Actions
async def in_browser_extract_content(params):
    browser_context = login.main_win.getBrowserContextById(params["context_id"])
    browser = browser_context.browser
    page = await browser.get_current_page()
    import markdownify

    strip = []
    if should_strip_link_urls:
        strip = ['a', 'img']

    content = markdownify.markdownify(await page.content(), strip=strip)

    # manually append iframe text into the content so it's readable by the LLM (includes cross-origin iframes)
    for iframe in page.frames:
        if iframe.url != page.url and not iframe.url.startswith('data:'):
            content += f'\n\nIFRAME {iframe.url}:\n'
            content += markdownify.markdownify(await iframe.content())

    prompt = 'Your task is to extract the content of the page. You will be given a page and a goal and you should extract all relevant information around this goal from the page. If the goal is vague, summarize the page. Respond in json format. Extraction goal: {goal}, Page: {page}'
    template = PromptTemplate(input_variables=['goal', 'page'], template=prompt)
    try:
        output = page_extraction_llm.invoke(template.format(goal=goal, page=content))
        msg = f'📄  Extracted from page\n: {output.content}\n'
        logger.info(msg)
        return CallToolResult(content=[msg], isError=False)
    except Exception as e:
        logger.debug(f'Error extracting content: {e}')
        msg = f'📄  Extracted from page\n: {content}\n'
        logger.info(msg)
        return CallToolResult(content=[msg])


# HTML Download
async def in_browser_save_html_to_file(params) -> CallToolResult:
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
        return CallToolResult(content=[msg], isError=False)
    except Exception as e:
        error_msg = f'Failed to save HTML content: {str(e)}'
        logger.error(error_msg)
        return CallToolResult(error=error_msg, content='')


async def in_browser_scroll_down(params):
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
async def in_browser_scroll_up(params):
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
async def in_browser_send_keys(params):
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


async def in_browser_scroll_to_text(params):  # type: ignore
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
                    return CallToolResult(content=[msg], isError=False)
            except Exception as e:
                logger.debug(f'Locator attempt failed: {str(e)}')
                continue

        msg = f"Text '{text}' not found or not visible on page"
        logger.info(msg)
        return CallToolResult(content=[msg], isError=False)

    except Exception as e:
        msg = f"Failed to scroll to text '{text}': {str(e)}"
        logger.error(msg)
        return CallToolResult(error=[msg], isError=False)


async def in_browser_get_dropdown_options(params) -> CallToolResult:
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
            return CallToolResult(content=[msg], isError=False)
        else:
            msg = 'No options found in any frame for dropdown'
            logger.info(msg)
            return CallToolResult(content=[msg], isError=False)

    except Exception as e:
        logger.error(f'Failed to get dropdown options: {str(e)}')
        msg = f'Error getting options: {str(e)}'
        logger.info(msg)
        return CallToolResult(content=[msg], isError=False)


async def in_browser_select_dropdown_option(params) -> CallToolResult:
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
        return CallToolResult(content=[msg], isError=False)

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

                    # "label" because we are selecting by text
                    # nth(0) to disable error thrown by strict mode
                    # timeout=1000 because we are already waiting for all network events, therefore ideally we don't need to wait a lot here (default 30s)
                    selected_option_values = (
                        await frame.locator('//' + dom_element.xpath).nth(0).select_option(label=text, timeout=1000)
                    )

                    msg = f'selected option {text} with value {selected_option_values}'
                    logger.info(msg + f' in frame {frame_index}')

                    return CallToolResult(content=[msg], isError=False)

            except Exception as frame_e:
                logger.error(f'Frame {frame_index} attempt failed: {str(frame_e)}')
                logger.error(f'Frame type: {type(frame)}')
                logger.error(f'Frame URL: {frame.url}')

            frame_index += 1

        msg = f"Could not select option '{text}' in any frame"
        logger.info(msg)
        return CallToolResult(content=[msg], isError=False)

    except Exception as e:
        msg = f'Selection failed: {str(e)}'
        logger.error(msg)
        return CallToolResult(error=[msg], isError=False)


async def in_browser_drag_drop(params) -> CallToolResult:
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
                return CallToolResult(error=error_msg, isError=False)

            source_coords, target_coords = await get_element_coordinates(
                source_element, target_element, params.element_source_offset, params.element_target_offset
            )

            if not source_coords or not target_coords:
                error_msg = f'Failed to determine {"source" if not source_coords else "target"} coordinates'
                return CallToolResult(error=error_msg, isError=False)

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
            return CallToolResult(error=error_msg, isError=False)

        # Validate coordinates
        if any(coord is None for coord in [source_x, source_y, target_x, target_y]):
            error_msg = 'Failed to determine source or target coordinates'
            return CallToolResult(error=error_msg, isError=False)

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
            return CallToolResult(error=message, isError=False)

        # Create descriptive message
        if params.element_source and params.element_target:
            msg = f"🖱️ Dragged element '{params.element_source}' to '{params.element_target}'"
        else:
            msg = f'🖱️ Dragged from ({source_x}, {source_y}) to ({target_x}, {target_y})'

        logger.info(msg)
        return CallToolResult(content=[msg], isError=False)

    except Exception as e:
        error_msg = f'Failed to perform drag and drop: {str(e)}'
        logger.error(error_msg)
        return CallToolResult(error=error_msg, isError=False)


async def mouse_click(params):
    browser_context = login.main_win.getBrowserContextById(context_id)
    browser = browser_context.browser
    if params.index not in await browser.get_selector_map():
        raise Exception(f'Element index {params.index} does not exist - retry or use alternative actions')

    nClicks = 1
    interval = 0.1
    pyautogui.moveTo(params.loc.x, params.loc.y)
    pyautogui.click(clicks=nClicks, interval=interval)

    logger.debug(f'Element xpath: {params.loc.x},  {params.loc.y}')
    return CallToolResult(content="", isError=False)


async def mouse_move(params):
    browser_context = login.main_win.getBrowserContextById(params["context_id"])
    browser = browser_context.browser
    if params.index not in await browser.get_selector_map():
        raise Exception(f'Element index {params.index} does not exist - retry or use alternative actions')

    pyautogui.moveTo(params.loc.x, params.loc.y)

    logger.debug(f'Element xpath: {params.loc.x},  {params.loc.y}')
    return CallToolResult(content="", isError=False)


async def mouse_drag_drop(params):
    browser_context = login.main_win.getBrowserContextById(params["context_id"])
    browser = browser_context.browser
    if params.index not in await browser.get_selector_map():
        raise Exception(f'Element index {params.index} does not exist - retry or use alternative actions')

    pyautogui.moveTo(params.pick_loc.x, params.pick_loc.y)
    pyautogui.dragTo(params.drop_loc.x, params.drop_loc.y, duration=params.duration)

    logger.debug(f'dragNdrop: {params.pick_loc.x}, {params.pick_loc.y} to {params.drop_loc.x}, {params.drop_loc.y}')
    return CallToolResult(content="", isError=False)


async def mouse_scroll(params):
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
    return CallToolResult(content="", isError=False)


async def text_input(params):
    browser_context = login.main_win.getBrowserContextById(params["context_id"])
    browser = browser_context.browser
    if params.index not in await browser.get_selector_map():
        raise Exception(f'Element index {params.index} does not exist - retry or use alternative actions')

    pyautogui.write(params.text, interval=params.interval)

    logger.debug(f'Element xpath: {params.text},  {params.interval}')
    return CallToolResult(content="", isError=False)


async def keys_input(params):
    browser_context = login.main_win.getBrowserContextById(params["context_id"])
    browser = browser_context.browser
    if params.index not in await browser.get_selector_map():
        raise Exception(f'Element index {params.index} does not exist - retry or use alternative actions')

    pyautogui.hotkey(*params.combo)

    logger.debug(f'hot keys: {params.combo[0]}')
    return CallToolResult(content="", isError=False)


async def call_api(params):
    browser_context = login.main_win.getBrowserContextById(params["context_id"])
    browser = browser_context.browser
    if params.index not in await browser.get_selector_map():
        raise Exception(f'Element index {params.index} does not exist - retry or use alternative actions')

    pyautogui.moveTo(params.loc.x, params.loc.y)

    logger.debug(f'Element xpath: {params.loc.x},  {params.loc.y}')
    return CallToolResult(content="", isError=False)


async def open_app(params):
    browser_context = login.main_win.getBrowserContextById(params["context_id"])
    browser = browser_context.browser
    if params.index not in await browser.get_selector_map():
        raise Exception(f'Element index {params.index} does not exist - retry or use alternative actions')

    DETACHED_PROCESS = 0x00000008
    subprocess.Popen(params.app_name, creationflags=DETACHED_PROCESS, shell=True, close_fds=True,
                     stdout=subprocess.PIPE,
                     stderr=subprocess.PIPE)

    logger.debug(f'Element xpath: {params.loc.x},  {params.loc.y}')
    return CallToolResult(content="", isError=False)


async def close_app(params):
    browser_context = login.main_win.getBrowserContextById(params["context_id"])
    browser = browser_context.browser
    if params.index not in await browser.get_selector_map():
        raise Exception(f'Element index {params.index} does not exist - retry or use alternative actions')

    app_window = gw.getWindowsWithTitle(params.win_title)[0]
    app_window.close()

    logger.debug(f'Element xpath: {params.loc.x},  {params.loc.y}')
    return CallToolResult(content="", isError=False)


async def switch_to_app(params):
    browser_context = login.main_win.getBrowserContextById(params["context_id"])
    browser = browser_context.browser
    if params.index not in await browser.get_selector_map():
        raise Exception(f'Element index {params.index} does not exist - retry or use alternative actions')

    # Find the window by its title
    target_window = gw.getWindowsWithTitle(params.win_title)[0]

    # Activate the window (bring it to front)
    target_window.activate()

    logger.debug(f'Element xpath: {params.loc.x},  {params.loc.y}')
    return CallToolResult(content="", isError=False)


async def run_extern(params):
    browser_context = login.main_win.getBrowserContextById(params["context_id"])
    browser = browser_context.browser
    if params.index not in await browser.get_selector_map():
        raise Exception(f'Element index {params.index} does not exist - retry or use alternative actions')

    time.sleep(params.time)

    logger.debug(f'Element xpath: {params.loc.x},  {params.loc.y}')
    return CallToolResult(content="", isError=False)


async def make_dir(params):
    browser_context = login.main_win.getBrowserContextById(params["context_id"])
    browser = browser_context.browser
    if params.index not in await browser.get_selector_map():
        raise Exception(f'Element index {params.index} does not exist - retry or use alternative actions')

    if not os.path.exists(params.dir_path):
        # create only if the dir doesn't exist
        os.makedirs(params.dir_path)

    logger.debug(f'Element xpath: {params.loc.x},  {params.loc.y}')
    return CallToolResult(content="", isError=False)


async def delete_dir(params):
    browser_context = login.main_win.getBrowserContextById(params["context_id"])
    browser = browser_context.browser
    if params.index not in await browser.get_selector_map():
        raise Exception(f'Element index {params.index} does not exist - retry or use alternative actions')

    if os.path.exists(params.dir_path):
        # create only if the dir doesn't exist
        os.remove(params.dir_path)

    logger.debug(f'Element xpath: {params.loc.x},  {params.loc.y}')
    return CallToolResult(content="", isError=False)


async def delete_file(params):
    browser_context = login.main_win.getBrowserContextById(params["context_id"])
    browser = browser_context.browser
    if params.index not in await browser.get_selector_map():
        raise Exception(f'Element index {params.index} does not exist - retry or use alternative actions')

    if os.path.exists(params.file):
        # create only if the dir doesn't exist
        os.remove(params.file)

    logger.debug(f'Element xpath: {params.loc.x},  {params.loc.y}')
    return CallToolResult(content="", isError=False)


async def move_file(params):
    browser_context = login.main_win.getBrowserContextById(params["context_id"])
    browser = browser_context.browser
    if params.index not in await browser.get_selector_map():
        raise Exception(f'Element index {params.index} does not exist - retry or use alternative actions')

    # default_download_dir = getDefaultDownloadDirectory()
    # new_file = getMostRecentFile(default_download_dir, prefix=step["prefix"], extension=step["extension"])

    shutil.move(params.src, params.dest)

    logger.debug(f'Element xpath: {params.loc.x},  {params.loc.y}')
    return CallToolResult(content="", isError=False)


async def copy_file_dir(params):
    browser_context = login.main_win.getBrowserContextById(params["context_id"])
    browser = browser_context.browser
    if params.index not in await browser.get_selector_map():
        raise Exception(f'Element index {params.index} does not exist - retry or use alternative actions')

    shutil.copy(params.src, params.dest)

    logger.debug(f'Element xpath: {params.loc.x},  {params.loc.y}')
    return CallToolResult(content="", isError=False)


async def screen_analyze(params):
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
    return CallToolResult(content=[msg], isError=False)


async def screen_capture(params):
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
    return CallToolResult(content=[msg], isError=False)


async def seven_zip(params):
    browser_context = login.main_win.getBrowserContextById(context_id)
    browser = browser_context.browser
    if params.index not in await browser.get_selector_map():
        raise Exception(f'Element index {params.index} does not exist - retry or use alternative actions')

    logger.debug(f'Element xpath: {params.file}')
    msg = ""
    return CallToolResult(content=[msg], meta={}, isError=False)



async def kill_processes(params):
    browser_context = login.main_win.getBrowserContextById(params["context_id"])
    browser = browser_context.browser
    if params.index not in await browser.get_selector_map():
        raise Exception(f'Element index {params.index} does not exist - retry or use alternative actions')

    logger.debug(f'Kill Processes: {params.pids[0]}')
    msg = ""
    return CallToolResult(content=[msg], isError=False)


# Element Interaction Actions
async def rpa_supervisor_scheduling_work(params):
    print("INPUT:", params)
    # if tool_name != "rpa_supervisor_scheduling_work":
    #     raise ValueError(f"Unexpected tool name: {tool_name}")
    global server_main_win
    try:
        # mainwin = params["agent"].mainwin
        print(f"[MCP] Running supervisor scheduler tool... ")
        print(f"[MCP] Running supervisor scheduler tool... Bots: {len(server_main_win.bots)}")
        schedule = server_main_win.fetchSchedule("", server_main_win.get_vehicle_settings())
        workable = server_main_win.runTeamPrepHook(schedule)
        works_to_be_dispatched = server_main_win.handleCloudScheduledWorks(workable)
        msg = "Here are works to be dispatched to the troops."
        return [types.TextContent(type="text", text=msg)]
    except Exception as e:
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorCallTool:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorCallTool: traceback information not available:" + str(e)
        return [types.TextContent(type="text", text=f"Error in scheduler: {ex_stat}")]


async def rpa_operator_dispatch_works(params):
    # call put work received from A2A channel, put into today's work data structure
    # the runbotworks task will then take over.....
    # including put reactive work into it.
    try:
        works_to_be_dispatched = login.main_win.handleCloudScheduledWorks(workable)
        return CallToolResult(content="works dispatched.", isError=False)
    except Exception as e:
        logger.warning(f'RPA Supervisor Work failure')
        return CallToolResult(error=str(e))


async def rpa_supervisor_process_work_results(params):
    # handle RPA work results from a platoon host.
    # mostly bookkeeping.
    try:
        works_to_be_dispatched = login.main_win.handleCloudScheduledWorks(workable)
        return CallToolResult(content="works dispatched.", isError=False)
    except Exception as e:
        logger.warning(f'RPA Supervisor Work failure')
        return CallToolResult(error=str(e))


async def rpa_supervisor_run_daily_housekeeping(params):
    # call put work received from A2A channel, put into today's work data structure
    # the runbotworks task will then take over.....
    # including put reactive work into it.
    try:
        works_to_be_dispatched = login.main_win.handleCloudScheduledWorks(workable)
        return CallToolResult(content="works dispatched.", isError=False)
    except Exception as e:
        logger.warning(f'RPA Supervisor Work failure')
        return CallToolResult(error=str(e))

async def rpa_operator_report_work_results(params):
    # call put work received from A2A channel, put into today's work data structure
    # the runbotworks task will then take over.....
    # including put reactive work into it.
    try:
        works_to_be_dispatched = login.main_win.handleCloudScheduledWorks(workable)
        return CallToolResult(content="works dispatched.", isError=False)
    except Exception as e:
        logger.warning(f'RPA Supervisor Work failure')
        return CallToolResult(error=str(e))


async def reconnect_wifi(params):
    # Disconnect current Wi-Fi
    subprocess.run(["netsh", "wlan", "disconnect"])
    time.sleep(2)

    # Reconnect to a specific network
    cmd = ["netsh", "wlan", "connect", f"name={params['network_name']}"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    print(result.stdout)


tool_function_mapping = {
        "say_hello": say_hello,
        "wait": wait,
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
        "in_browser_extract_content": in_browser_extract_content,
        "in_browser_save_html_to_file": in_browser_save_html_to_file,
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
        "text_input": text_input,
        "keys_input": keys_input,
        "call_api": call_api,
        "open_app": open_app,
        "close_app": close_app,
        "switch_to_app": switch_to_app,
        "run_extern": run_extern,
        "make_dir": make_dir,
        "delete_dir": delete_dir,
        "delete_file": delete_file,
        "move_file": move_file,
        "copy_file_dir": copy_file_dir,
        "screen_analyze": screen_analyze,
        "screen_capture": screen_capture,
        "seven_zip": seven_zip,
        "kill_processes": kill_processes,
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
    # print(">>> sse connected")
    async with meca_sse.connect_sse(scope, receive, send) as streams:
        await meca_mcp_server.run(streams[0], streams[1], meca_mcp_server.create_initialization_options())

async def sse_handle_messages(scope, receive, send):
    await meca_sse.handle_post_message(scope, receive, send)

