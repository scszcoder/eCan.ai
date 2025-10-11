import base64
import os
from typing import Optional, Dict, Any

from selenium.webdriver.remote.webdriver import WebDriver


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
