import time
import asyncio
from utils.logger_helper import logger_helper as logger
from browser_use.agent.views import ActionModel, ActionResult
from playwright.async_api import ElementHandle
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from browser_use.dom.views import EnhancedDOMTreeNode as DOMElementNode
from pydantic import create_model
import markdownify

    
async def browser_use_locate_element(mainwin, element: 'DOMElementNode') -> ElementHandle | None:
    found = await mainwin.browser_session.get_locate_element(element)
    return found
async def browser_use_wait_for_element(mainwin, element):
    found = await mainwin.browser_session.wait_for_element(element)
    return found


async def browser_use_locate_element_by_xpath(mainwin, xpath: str) -> ElementHandle | None:
    found = await mainwin.browser_session.get_locate_element_by_xpath(xpath)
    return found

async def browser_use_locate_element_by_css_selector(mainwin, css_selector: str) -> ElementHandle | None:
    found = await mainwin.browser_session.get_locate_element_by_css_selector(css_selector)
    return found

async def browser_use_locate_element_by_text(mainwin, text, nth, ele_type):
    found = await mainwin.browser_session.get_locate_element_by_text(text, nth, ele_type)
    return found

async def browser_use_refresh(mainwin, element):
    result = await mainwin.browser_session.refresh()
    return result

async def browser_use_wait(mainwin, seconds):
    WaitAction = mainwin.browser_use_controller.registry.actions['wait'].param_model

    action = WaitAction(
        seconds=seconds
    )

    action_result = await mainwin.browser_use_controller.act(
        action=action,
        browser_session=mainwin.browser_session,
        page_extraction_llm=mainwin.llm,
        file_system=mainwin.browser_use_file_system,
    )

    return action_result.extracted_content or "No content."


async def browser_use_click(mainwin, text, nth, ele_type):
    node_element = await mainwin.browser_session.get_locate_element_by_text(text, nth, ele_type)
    print("found element", node_element)
    if node_element is None:
        return
    bustat = await mainwin.browser_session._click_element_node(node_element)
    return bustat



async def browser_use_execute_javascript(mainwin, script):
    return await mainwin.browser_session.execute_javascript(script)


async def browser_use_search_google(mainwin, query):
    SearchGoogleAction = create_model(
        'SearchGoogleAction',
        __base__=ActionModel,
        query=(str, query)
    )

    action = SearchGoogleAction()
    action_result = await mainwin.browser_use_controller.act(
        action=action,
        browser_session=mainwin.browser_session,
        page_extraction_llm=mainwin.llm,
        file_system=mainwin.browser_use_file_system,
    )

    return action_result.extracted_content or "No content."

#'Navigate to URL, set new_tab=True to open in new tab, False to navigate in current tab',
async def browser_use_go_to_url(mainwin, url):
    GoToUrlAction = create_model(
        'GoToUrlAction',
        __base__=ActionModel,
        url=(str, url)
    )

    action = GoToUrlAction()
    action_result = await mainwin.browser_use_controller.act(
        action=action,
        browser_session=mainwin.browser_session,
        page_extraction_llm=mainwin.llm,
        file_system=mainwin.browser_use_file_system,
    )

    return action_result.extracted_content or "No content."

#'Go back'
async def browser_use_go_back(mainwin,):
    NoParamsAction = create_model(
        'NoParamsAction',
        __base__=ActionModel,
    )

    action = NoParamsAction()
    action_result = await mainwin.browser_use_controller.act(
        action=action,
        browser_session=mainwin.browser_session,
        page_extraction_llm=mainwin.llm,
        file_system=mainwin.browser_use_file_system,
    )

    return action_result.extracted_content or "No content."


#'Click element by index', param_model=ClickElementAction), index is the index of the dom element selector map node index
async def browser_use_click_element_by_index(mainwin, index):
    ClickElementAction = create_model(
        'ClickElementAction',
        __base__=ActionModel,
        index=(int, index)
    )

    action = ClickElementAction()
    action_result = await mainwin.browser_use_controller.act(
        action=action,
        browser_session=mainwin.browser_session,
        page_extraction_llm=mainwin.llm,
        file_system=mainwin.browser_use_file_system,
    )

    return action_result.extracted_content or "No content."


#'Click and input text into a input interactive element', param_model=InputTextAction,
async def browser_use_input_text(mainwin, index, text):
    InputTextAction = create_model(
        'InputTextAction',
        __base__=ActionModel,
        index=index,
        text=(str, text)
    )

    action = InputTextAction()
    action_result = await mainwin.browser_use_controller.act(
        action=action,
        browser_session=mainwin.browser_session,
        page_extraction_llm=mainwin.llm,
        file_system=mainwin.browser_use_file_system,
    )

    return action_result.extracted_content or "No content."

# 'Upload file to interactive element with file path', param_model=UploadFileAction)
async def browser_use_upload_file(mainwin, index, path):
    UploadFileAction = create_model(
        'UploadFileAction',
        __base__=ActionModel,
        index=index,
        path=(str, path)
    )

    action = UploadFileAction()
    action_result = await mainwin.browser_use_controller.act(
        action=action,
        browser_session=mainwin.browser_session,
        page_extraction_llm=mainwin.llm,
        file_system=mainwin.browser_use_file_system,
    )

    return action_result.extracted_content or "No content."

# Tab Management Actions

# 'Switch tab', param_model=SwitchTabAction)
async def browser_use_switch_tab(mainwin, page_id, url):
    SwitchTabAction = create_model(
        'SwitchTabAction',
        __base__=ActionModel,
        page_id=page_id,
        url=(str, url)
    )

    action = SwitchTabAction()
    action_result = await mainwin.browser_use_controller.act(
        action=action,
        browser_session=mainwin.browser_session,
        page_extraction_llm=mainwin.llm,
        file_system=mainwin.browser_use_file_system,
    )

    return action_result.extracted_content or "No content."

# 'Close an existing tab', param_model=CloseTabAction)
async def browser_use_close_tab(mainwin, page_id, url):
    CloseTabAction = create_model(
            'CloseTabAction',
            __base__=ActionModel,
            page_id=page_id,
            url=(str, url)
        )

    action = CloseTabAction()
    action_result = await mainwin.browser_use_controller.act(
        action=action,
        browser_session=mainwin.browser_session,
        page_extraction_llm=mainwin.llm,
        file_system=mainwin.browser_use_file_system,
    )

    return action_result.extracted_content or "No content."
# Content Actions

#"""Extract structured, semantic data (e.g. product description, price, all information about XYZ) from the current webpage based on a textual query.
# This tool takes the entire markdown of the page and extracts the query from it.
# Set extract_links=True ONLY if your query requires extracting links/URLs from the page.
# Only use this for specific queries for information retrieval from the page. Don't use this to get interactive elements - the tool does not see HTML elements, only the markdown.
# """
async def browser_use_extract_structured_data(mainwin, query: str, extract_links: bool):
    ExtractStructuredDataAction = mainwin.browser_use_controller.registry.actions['extract_structured_data'].param_model

    action = ExtractStructuredDataAction(
        query=query,
        extract_links=extract_links
    )

    action_result = await mainwin.browser_use_controller.act(
        action=action,
        browser_session=mainwin.browser_session,
        page_extraction_llm=mainwin.llm,
        file_system=mainwin.browser_use_file_system,
    )

    return action_result.extracted_content or "No content."





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
async def browser_use_scroll(mainwin, down, num_pages, index):
    ScrollAction = create_model(
        'ScrollAction',
        __base__=ActionModel,
        down = (bool, down),
        num_pages = (int, num_pages),
        index = (int, index)
    )

    action = ScrollAction()
    action_result = await mainwin.browser_use_controller.act(
        action=action,
        browser_session=mainwin.browser_session,
    )

    return action_result.extracted_content or 'No content.'

# 'Send strings of special keys to use Playwright page.keyboard.press - examples include Escape, Backspace, Insert, PageDown, Delete, Enter, or Shortcuts such as `Control+o`, `Control+Shift+T`', param_model=SendKeysAction
async def browser_use_send_keys(mainwin, keys):
    SendKeysAction = create_model(
        'SendKeysAction',
        __base__=ActionModel,
        keys=keys
    )

    action = SendKeysAction()
    action_result = await mainwin.browser_use_controller.act(
        action=action,
        browser_session=mainwin.browser_session,
    )

    return action_result.extracted_content or "No content."

#'Scroll to a text in the current page',
async def browser_use_scroll_to_text(mainwin, text: str):  # type: ignore
    ScrollToTetAction = mainwin.browser_use_controller.registry.actions["scroll_to_text"].param_model

    action = ScrollToTetAction(
        text=text
    )

    action_result = await mainwin.browser_use_controller.act(
        action=action,
        browser_session=mainwin.browser_session,
    )

    return action_result.extracted_content or "No content."

# File System Actions
# 'Write or append content to file_name in file system. Allowed extensions are .md, .txt, .json, .csv, .pdf. For .pdf files, write the content in markdown format and it will automatically be converted to a properly formatted PDF document.'
async def browser_use_write_file(mainwin, file_name: str, content: str, append: bool = False, trailing_newline: bool = True, leading_newline: bool = False,):
    WriteFileAction = mainwin.browser_use_controller.registry.actions['write_file'].param_model

    action = WriteFileAction(
        file_name=file_name,
        content=content,
        append = append,
        trailing_newline = trailing_newline,
        leading_newline = leading_newline,
    )

    action_result = await mainwin.browser_use_controller.act(
        action=action,
        browser_session=mainwin.browser_session,
        page_extraction_llm=mainwin.llm,
        file_system=mainwin.browser_use_file_system,
    )

    return action_result.extracted_content or "No content."


#'Replace old_str with new_str in file_name. old_str must exactly match the string to replace in original text. Recommended tool to mark completed items in todo.md or change specific contents in a file.'
async def browser_use_replace_file_str(mainwin, file_name: str, old_str: str, new_str: str):
    ReplaceFileStrAction = mainwin.browser_use_controller.registry.actions['replace_file_str'].param_model

    action = ReplaceFileStrAction(
        file_name=file_name,
        old_str=old_str,
        new_str=new_str,
    )

    action_result = await mainwin.browser_use_controller.act(
        action=action,
        browser_session=mainwin.browser_session,
        page_extraction_llm=mainwin.llm,
        file_system=mainwin.browser_use_file_system,
    )

    return action_result.extracted_content or "No content."

async def browser_use_read_file(mainwin, file_name: str, available_file_paths: list[str]):
    ReadFileAction = mainwin.browser_use_controller.registry.actions['read_file'].param_model

    action = ReadFileAction(
        file_name=file_name,
        available_file_paths=available_file_paths,
    )

    action_result = await mainwin.browser_use_controller.act(
        action=action,
        browser_session=mainwin.browser_session,
        page_extraction_llm=mainwin.llm,
        file_system=mainwin.browser_use_file_system,
    )

    return action_result.extracted_content or "No content."

# 'Get all options from a native dropdown',
async def browser_use_get_dropdown_options(mainwin, index: int):
    GetDropdownOptionsAction = mainwin.browser_use_controller.registry.actions['get_dropdown_options'].param_model

    action = GetDropdownOptionsAction(
        index=index
    )

    action_result = await mainwin.browser_use_controller.act(
        action=action,
        browser_session=mainwin.browser_session,
        page_extraction_llm=mainwin.llm,
        file_system=mainwin.browser_use_file_system,
    )

    return action_result.extracted_content or "No content."

# 'Select dropdown option for interactive element index by the text of the option you want to select',
async def browser_use_select_dropdown_option(mainwin, index: int, text: str ):
    SelectDropdownOptionAction = mainwin.browser_use_controller.registry.actions['select_dropdown_option'].param_model

    action = SelectDropdownOptionAction(
        index=index,
        text=text
    )

    action_result = await mainwin.browser_use_controller.act(
        action=action,
        browser_session=mainwin.browser_session,
        page_extraction_llm=mainwin.llm,
        file_system=mainwin.browser_use_file_system,
    )

    return action_result.extracted_content or "No content."

# 'Google Sheets: Get the contents of the entire sheet', domains=['https://docs.google.com'])
async def browser_use_read_sheet_contents(mainwin):
    ReadSheetContentsAction = mainwin.browser_use_controller.registry.actions['read_sheet_contents'].param_model

    action = ReadSheetContentsAction()

    action_result = await mainwin.browser_use_controller.act(
        action=action,
        browser_session=mainwin.browser_session,
        page_extraction_llm=mainwin.llm,
        file_system=mainwin.browser_use_file_system,
    )

    return action_result.extracted_content or "No content."

#'Google Sheets: Get the contents of a cell or range of cells',
async def browser_use_read_cell_contents(mainwin, cell_or_range: str):
    ReadCellContentsAction = mainwin.browser_use_controller.registry.actions['read_cell_contents'].param_model

    action = ReadCellContentsAction(cell_or_range=cell_or_range)

    action_result = await mainwin.browser_use_controller.act(
        action=action,
        browser_session=mainwin.browser_session,
        page_extraction_llm=mainwin.llm,
        file_system=mainwin.browser_use_file_system,
    )

    return action_result.extracted_content or "No content."

    #'Google Sheets: Update the content of a cell or range of cells', domains=['https://docs.google.com']
async def browser_use_update_cell_contents(mainwin, cell_or_range: str, new_contents_tsv: str):
    UpdateCellContentsAction = mainwin.browser_use_controller.registry.actions['update_cell_contents'].param_model

    action = UpdateCellContentsAction(cell_or_range=cell_or_range, new_contents_tsv=new_contents_tsv)

    action_result = await mainwin.browser_use_controller.act(
        action=action,
        browser_session=mainwin.browser_session,
        page_extraction_llm=mainwin.llm,
        file_system=mainwin.browser_use_file_system,
    )

    return action_result.extracted_content or "No content."

#'Google Sheets: Clear whatever cells are currently selected',
async def browser_use_clear_cell_contents(mainwin, cell_or_range: str):
    ClearCellContentsAction = mainwin.browser_use_controller.registry.actions['clear_cell_contents'].param_model

    action = ClearCellContentsAction(cell_or_range=cell_or_range)

    action_result = await mainwin.browser_use_controller.act(
        action=action,
        browser_session=mainwin.browser_session,
        page_extraction_llm=mainwin.llm,
        file_system=mainwin.browser_use_file_system,
    )

    return action_result.extracted_content or "No content."

#'Google Sheets: Select a specific cell or range of cells'
async def browser_use_select_cell_or_range(mainwin, cell_or_range: str):
    SelectCellOrRangeAction = mainwin.browser_use_controller.registry.actions['select_cell_or_range'].param_model

    action = SelectCellOrRangeAction(cell_or_range=cell_or_range)

    action_result = await mainwin.browser_use_controller.act(
        action=action,
        browser_session=mainwin.browser_session,
        page_extraction_llm=mainwin.llm,
        file_system=mainwin.browser_use_file_system,
    )

    return action_result.extracted_content or "No content."


# 'Google Sheets: Fallback method to type text into (only one) currently selected cell',
async def browser_use_fallback_input_into_single_selected_cell(mainwin, text: str):
    FallbackInputIntoSingleSelectedCellAction = mainwin.browser_use_controller.registry.actions['fallback_input_into_single_selected_cell'].param_model

    action = FallbackInputIntoSingleSelectedCellAction(text=text)

    action_result = await mainwin.browser_use_controller.act(
        action=action,
        browser_session=mainwin.browser_session,
        page_extraction_llm=mainwin.llm,
        file_system=mainwin.browser_use_file_system,
    )

    return action_result.extracted_content or "No content."


async def browser_use_done(mainwin):
    DoneAction = create_model(
        'DoneAction',
        __base__=ActionModel
    )

    action = DoneAction()

    action_result = await mainwin.browser_use_controller.act(
        action=action,
        browser_session=mainwin.browser_session,
        page_extraction_llm=mainwin.llm,
        file_system=mainwin.browser_use_file_system,
    )

    return action_result.extracted_content or "No content."


async def browser_use_drag_drop(mainwin, cell_or_range: str):
    DragDropAction = mainwin.browser_use_controller.registry.actions['clear_cell_contents'].param_model

    action = DragDropAction(cell_or_range=cell_or_range)

    action_result = await mainwin.browser_use_controller.act(
        action=action,
        browser_session=mainwin.browser_session,
        page_extraction_llm=mainwin.llm,
        file_system=mainwin.browser_use_file_system,
    )

    return action_result.extracted_content or "No content."