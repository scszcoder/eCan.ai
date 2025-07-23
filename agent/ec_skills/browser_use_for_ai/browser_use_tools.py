import time
import asyncio
from utils.logger_helper import logger_helper as logger
from browser_use.agent.views import ActionModel, ActionResult

from browser_use.browser import BrowserSession
from browser_use.browser.types import Page
from browser_use.browser.views import BrowserError
from browser_use.controller.registry.service import Registry
from browser_use.filesystem.file_system import FileSystem
from browser_use.llm.base import BaseChatModel
from browser_use.llm.messages import UserMessage
from browser_use.observability import observe_debug
from browser_use.utils import time_execution_sync


async def crawler_wait_for_element(crawler, element_type, element_name, timeout):



async def crawler_click(crawler, element_type, element_name):






async def crawler_execute_javascript(crawler, element_type, element_name):
    browser_session = crawler.browser_session

async def search_google(params: SearchGoogleAction, browser_session: BrowserSession):



#'Navigate to URL, set new_tab=True to open in new tab, False to navigate in current tab',
async def crawler_go_to_url(browser_session: BrowserSession, new_tab, url):


#'Go back'
async def crawler_go_back(browser_session: BrowserSession):

# wait for x seconds

#'Wait for x seconds default 3 (max 10 seconds)')
async def crawler_wait(seconds: int = 3):


#'Click element by index', param_model=ClickElementAction)
async def crawler_click_element_by_index(browser_session: BrowserSession, index):


#'Click and input text into a input interactive element', param_model=InputTextAction,
async def crawler_input_text(browser_session: BrowserSession, has_sensitive_data: bool = False, index, text):


# 'Upload file to interactive element with file path', param_model=UploadFileAction)
async def crawler_upload_file(params: UploadFileAction, browser_session: BrowserSession, available_file_paths: list[str]):


# Tab Management Actions

# 'Switch tab', param_model=SwitchTabAction)
async def crawler_switch_tab(browser_session: BrowserSession, page_id):


# 'Close an existing tab', param_model=CloseTabAction)
async def crawler_close_tab(browser_session: BrowserSession, page_id):


# Content Actions

#"""Extract structured, semantic data (e.g. product description, price, all information about XYZ) from the current webpage based on a textual query.
# This tool takes the entire markdown of the page and extracts the query from it.
# Set extract_links=True ONLY if your query requires extracting links/URLs from the page.
# Only use this for specific queries for information retrieval from the page. Don't use this to get interactive elements - the tool does not see HTML elements, only the markdown.
# """
async def crawler_extract_structured_data(
        query: str,
        extract_links: bool,
        page: Page,
        page_extraction_llm: BaseChatModel,
        file_system: FileSystem,
):
    from functools import partial

    import markdownify



# @self.registry.action(
# 	'Get the accessibility tree of the page in the format "role name" with the number_of_elements to return',
# )
# async def get_ax_tree(number_of_elements: int, page: Page):
# 	node = await page.accessibility.snapshot(interesting_only=True)

# 	def flatten_ax_tree(node, lines):
# 		if not node:
# 			return
# 		role = node.get('role', '')
# 		name = node.get('name', '')
# 		lines.append(f'{role} {name}')
# 		for child in node.get('children', []):
# 			flatten_ax_tree(child, lines)

# 	lines = []
# 	flatten_ax_tree(node, lines)
# 	msg = '\n'.join(lines)
# 	logger.info(msg)
# 	return ActionResult(
# 		extracted_content=msg,
# 		include_in_memory=False,
# 		long_term_memory='Retrieved accessibility tree',
# 		include_extracted_content_only_once=True,
# 	)

#'Scroll the page by specified number of pages (set down=True to scroll down, down=False to scroll up, num_pages=number of pages to scroll like 0.5 for half page, 1.0 for one page, etc.). Optional index parameter to scroll within a specific element or its scroll container (works well for dropdowns and custom UI components).',  param_model=ScrollAction
async def crawler_scroll(browser_session: BrowserSession, params: ScrollAction) -> ActionResult:


# 'Send strings of special keys to use Playwright page.keyboard.press - examples include Escape, Backspace, Insert, PageDown, Delete, Enter, or Shortcuts such as `Control+o`, `Control+Shift+T`', param_model=SendKeysAction
async def crawler_send_keys(params: SendKeysAction, page: Page):


#'Scroll to a text in the current page',
async def crawler_scroll_to_text(text: str, page: Page):  # type: ignore


# File System Actions
# 'Write or append content to file_name in file system. Allowed extensions are .md, .txt, .json, .csv, .pdf. For .pdf files, write the content in markdown format and it will automatically be converted to a properly formatted PDF document.'
async def crawler_write_file(
        file_name: str,
        content: str,
        file_system: FileSystem,
        append: bool = False,
        trailing_newline: bool = True,
        leading_newline: bool = False,
):

#'Replace old_str with new_str in file_name. old_str must exactly match the string to replace in original text. Recommended tool to mark completed items in todo.md or change specific contents in a file.'
async def crawler_replace_file_str(file_name: str, old_str: str, new_str: str, file_system: FileSystem):

@self.registry.action('Read file_name from file system')
async def crawler_read_file(file_name: str, available_file_paths: list[str], file_system: FileSystem):


# 'Get all options from a native dropdown',
async def crawler_get_dropdown_options(index: int, browser_session: BrowserSession) -> ActionResult:


# 'Select dropdown option for interactive element index by the text of the option you want to select',
async def crawler_select_dropdown_option(
        index: int,
        text: str,
        browser_session: BrowserSession,
) -> ActionResult:


# 'Google Sheets: Get the contents of the entire sheet', domains=['https://docs.google.com'])
async def crawler_read_sheet_contents(page: Page):


#'Google Sheets: Get the contents of a cell or range of cells',
async def crawler_read_cell_contents(cell_or_range: str, browser_session: BrowserSession):


    #'Google Sheets: Update the content of a cell or range of cells', domains=['https://docs.google.com']
async def crawler_update_cell_contents(cell_or_range: str, new_contents_tsv: str, browser_session: BrowserSession):


#'Google Sheets: Clear whatever cells are currently selected',
async def crawler_clear_cell_contents(cell_or_range: str, browser_session: BrowserSession):


#'Google Sheets: Select a specific cell or range of cells'
async def crawler_select_cell_or_range(cell_or_range: str, page: Page):



# 'Google Sheets: Fallback method to type text into (only one) currently selected cell',
async def crawler_fallback_input_into_single_selected_cell(text: str, page: Page):
