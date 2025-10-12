import base64
import os
from typing import Optional, Dict, Any
from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback
from selenium.webdriver.remote.webdriver import WebDriver
from mcp.types import CallToolResult, TextContent


def save_page_pdf_via_cdp(driver: WebDriver, output_path: str, options: Optional[Dict[str, Any]] = None) -> bool:
    """
    Cross-platform way to save the CURRENT page as a PDF using Chrome DevTools Protocol.
    - Works on Windows, macOS, and Linux (no native dialogs).
    - Requires a Chromium-based driver (Chrome/Edge) with CDP support.

    Args:
        driver: A Selenium WebDriver instance (Chrome/Edge).
        output_path: Full file path where the PDF will be written. Directory must exist.
        options: Page.printToPDF options. Examples:
            {
                "printBackground": True,
                "landscape": False,
                "paperWidth": 8.27,  # inches (A4 width)
                "paperHeight": 11.69, # inches (A4 height)
                "scale": 1,
                "marginTop": 0.4,
                "marginBottom": 0.4,
                "marginLeft": 0.4,
                "marginRight": 0.4,
            }

    Returns:
        True if the file was saved successfully, else False.
    """
    if not output_path:
        return False

    out_dir = os.path.dirname(output_path)
    if out_dir and not os.path.isdir(out_dir):
        return False

    opts = {
        "printBackground": True,
    }
    if options:
        opts.update(options)

    try:
        # Execute CDP: Page.printToPDF returns a base64-encoded PDF
        pdf_result = driver.execute_cdp_cmd("Page.printToPDF", opts)
        data_b64 = pdf_result.get("data")
        if not data_b64:
            return False
        pdf_bytes = base64.b64decode(data_b64)
        with open(output_path, "wb") as f:
            f.write(pdf_bytes)
        return True
    except Exception:
        return False


def ensure_download_dir(path: str) -> bool:
    """
    Ensure the parent directory for the given file path exists (cross-platform).
    Returns True if exists/created, else False.
    """
    try:
        parent = os.path.dirname(path)
        if not parent:
            return True
        os.makedirs(parent, exist_ok=True)
        return True
    except Exception:
        return False


async def reformat_and_print_labels(mainwin, args):  # type: ignore
    try:
        logger.debug("reformat_and_print_labels started....")
        new_orders = []
        fullfilled_orders = []
        options = args["input"]["options"]
        web_driver = mainwin.getWebDriver()

        msg = f"completed in fullfilling amazon FBS new orders: {len(new_orders)} new orders came in, {len(fullfilled_orders)} orders processed."
        tool_result = TextContent(type="text", text=msg)
        tool_result.meta = {"new_orders": new_orders, "fullfilled_orders": fullfilled_orders}
        return [tool_result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorReformatAndPrintLabels")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]


def add_reformat_and_print_labels_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="reformat_and_print_labels",
        description="reformat pdf to 2 labels per sheet and add product + quantity info as footnote, then send the label to printer to print (assume printer is conencted on LAN).",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["printer", "product_labels"],
                    "properties": {
                        "printer": {
                            "type": "string",
                            "description": "name of printer to print the label.",
                        },
                        "product_labels": {
                            "type": "array",
                            "description": "list of json objects with basic attributes of original_label(full path file name), product_name_short, quantity, and customer_name.",
                            "items": {
                                "type": "object",
                                "required": ["original_label", "product_name_short", "quantity", "customer_name"],
                                "properties": {
                                    "original_label": {"type": "string"},
                                    "product_name_short": {"type": "string"},
                                    "quantity": {"type": "integer"},
                                    "customer_name": {"type": "string"}
                                }
                            }
                        }
                    },
                }
            }
        },
    )

    tool_schemas.append(tool_schema)
