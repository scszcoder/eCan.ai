import os
import re
from datetime import datetime
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback
from agent.mcp.server.utils.print_utils import save_page_pdf_via_cdp, ensure_download_dir
from mcp.types import CallToolResult, TextContent
from agent.mcp.server.ads_power.ads_power import connect_to_adspower

# Placeholder mode: when no live order/label UI is available, we can generate a
# simple HTML label page and save it via CDP as a real PDF. Toggle as needed.
EBAY_PLACEHOLDER_MODE = True

# {
#     "n_new_orders": integer,
#     "n_pages": integer,
#     "orders_per_page": integer,
# }

async def get_ebay_summary(mainwin, args):
    try:
        ebay_summary = {}
        if args["input"]:
            logger.debug(f"[MCP][GET EBAY SUMMARY]: {args['input']}")
            store_url = args["input"]["store_url"]
            if not store_url:
                store_url = "https://www.ebay.com/sh/ord/?filter=status:AWAITING_SHIPMENT"
            options = args["input"]["options"]
            web_driver = mainwin.getWebDriver()
            if not web_driver:
                # Use the first site's URL to initialize/connect the driver
                web_driver = connect_to_adspower(mainwin, store_url)
                logger.debug(f"[MCP][GET EBAY SUMMARY]:WebDriver acquired for ebay work: {type(web_driver)}")
                ebay_summary = scrape_ebay_orders_summary(web_driver, store_url)
                msg = "completed getting ebay shop summary"
            else:
                logger.error(f"[MCP][GET EBAY SUMMARY]:WebDriver acquired for ebay work: {type(web_driver)}")
                msg = "Error: web driver not available."
        else:
            msg = "ERROR: no input provided."
            logger.error(f"[MCP][GET EBAY SUMMARY]:{msg}")

        result = TextContent(type="text", text=msg)
        result.meta = {"ebay_summary": ebay_summary}
        logger.debug("[MCP][GET EBAY SUMMARY]:ebay_summary:", ebay_summary)
        return [result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorGetEbaySummary")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]

def scrape_ebay_orders_summary(web_driver, store_url):
    try:
        # Navigate to eBay Seller Hub orders
        web_driver.get(store_url)

        # Initialize wait and ensure logged in
        wait = WebDriverWait(web_driver, 30)
        _ = ensure_logged_in_ebay(web_driver, wait)
        logger.debug("ensured logged in....")

        # Wait for summary/pagination section to render and read values
        try:
            summary_el = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '.summary-h2 .summary-content')))
            logger.debug("summary_el:", summary_el)
            results_text = summary_el.text or ''
        except Exception:
            # Fallback: try standalone summary content span
            try:
                summary_el = web_driver.find_element(By.CSS_SELECTOR, '.summary-content')
                logger.debug("fallback summary_el:", summary_el)
                results_text = summary_el.text or ''
            except Exception:
                results_text = ''

        # Parse total results like 'Results: 0' -> 0
        n_results = 0
        m = re.search(r'(\d[\d,]*)', results_text)
        if m:
            try:
                n_results = int(m.group(1).replace(',', ''))
            except Exception:
                n_results = 0

        # Extract orders_per_page from the hidden select if available; fallback to visible button
        orders_per_page = 0
        try:
            native_select = web_driver.find_element(By.CSS_SELECTOR, '.listbox__native')
            selected_option = native_select.find_element(By.CSS_SELECTOR, 'option[selected]')
            val = (selected_option.get_attribute('value') or selected_option.text or '').strip()
            if val:
                orders_per_page = int(val)
        except Exception:
            try:
                btn_text_el = web_driver.find_element(By.CSS_SELECTOR, '.listbox-button.sh-core-ipp__listbox .btn__text')
                btn_text = (btn_text_el.text or '').strip()
                if btn_text:
                    orders_per_page = int(btn_text)
            except Exception:
                pass

        # Count pagination pages (visible page links)
        try:
            page_links = web_driver.find_elements(By.CSS_SELECTOR, 'ol.pagination__items a.pagination__item')
            n_pages = len(page_links) if page_links else 1
        except Exception:
            n_pages = 1

        messages_link = ""
        n_messages = 0
        try:
            messages_anchor = wait.until(
                EC.presence_of_element_located(
                    (
                        By.CSS_SELECTOR,
                        "a.shui-header__button.shui-message-button-regular.fake-btn.fake-btn--small.fake-btn--tertiary",
                    )
                )
            )
            messages_link = messages_anchor.get_attribute("href") or ""
            messages_text = (messages_anchor.text or "").strip()
            match = re.search(r"(\d[\d,]*)", messages_text)
            if match:
                try:
                    n_messages = int(match.group(1).replace(",", ""))
                except Exception:
                    logger.warning("[EBAY PAGE]WARNING: Failed to parse n_messages from messages_text: {}".format(messages_text))
                    n_messages = 0
        except Exception:
            pass

        summary = {
            "n_new_orders": n_results,
            "n_pages": n_pages,
            "orders_per_page": orders_per_page,
            "messages_link": messages_link,
            "n_messages": n_messages,
        }
        logger.debug("new order summary:", summary)
        return summary
    except Exception as e:
        err_msg = get_traceback(e, "ErrorScrapeEBayOrdersSummary")
        logger.debug(err_msg)
        return {"error": err_msg}
    
# scrape orders, strategy, just
# # scrape list of orders,
# # click on 1st one to purchase shipping label
# # save the label pdf
# # return the label pdf path
# # reformat the label pdf to a standard format
# # send the label to printer to print
# # refresh the page (the just finished order will not be there anymore)
# # repeat above steps until all done.
async def scrape_ebay_orders(web_driver):
    try:
        # open ebay seller orders website
        n_orders_to_be_fullfilled = summary.get("n_new_orders", 0)
        while n_orders_to_be_fullfilled:
            # Attempt to click 'Purchase shipping label' on current page
            click_result = click_purchase_label_for_unshipped_on_page(web_driver, wait, max_clicks=1)

            labels_dir = os.path.join(os.path.expanduser("~"), "eCanLabels")
            target_pdf = os.path.join(labels_dir, f"ebay_label_{int(datetime.now().timestamp())}.pdf")

            if clicks > 0 and wait_for_purchase_label_ui(web_driver, timeout=30):
                # Save actual label page via CDP
                save_current_label_pdf(web_driver, target_pdf)
            else:
                logger.error("ERROR: No live label UI detected!")

            n_orders_to_be_fullfilled -= 1
            if n_orders_to_be_fullfilled > 0:
                web_driver.refresh()

    except Exception as e:
        err_msg = get_traceback(e, "ErrorScrapeEBayOrders")
        logger.debug(err_msg)
        return err_msg


def ensure_logged_in_ebay(driver, wait: WebDriverWait, timeout: int = 30) -> bool:
    """Basic login detection for eBay Seller Hub.
    Returns True if orders grid or a logged-in specific element is present; False if redirected to sign-in.
    """
    try:
        url = driver.current_url or ""
        if any(x in url for x in ["signin", "passport", "auth"]):
            return False

        def condition(d):
            try:
                # Orders grid or any row
                if d.find_elements(By.CSS_SELECTOR, '[data-testid="orders"]') or d.find_elements(By.CSS_SELECTOR, 'table') or d.find_elements(By.CSS_SELECTOR, 'header.gh-header'):
                    return True
                # Sign in form markers
                if d.find_elements(By.CSS_SELECTOR, 'form#signin-form') or d.find_elements(By.CSS_SELECTOR, 'input#userid'):
                    return False
            except Exception:
                pass
            return None

        result = wait.until(lambda d: condition(d) is not None and condition(d))
        return bool(result)
    except TimeoutException:
        return False
    except Exception:
        return False


def click_purchase_label_for_unshipped_on_page(driver, wait: WebDriverWait, max_clicks: int = 1) -> int:
    """On the Awaiting Shipment page, find unshipped orders and click 'Purchase shipping label'.
    Returns number of clicks performed (usually 0 or 1 as it navigates away).
    """
    clicks = 0
    try:
        # Heuristic: find any button/link with visible text 'Purchase shipping label'
        # Search within potential order rows/containers first to reduce false positives
        candidates = driver.find_elements(
            By.XPATH,
            "(" 
            "  //button[translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')="
            "        'purchase shipping label']"
            " | //a[translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')="
            "        'purchase shipping label']"
            " | //button[.//span[translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')="
            "        'purchase shipping label']]"
            " | //a[.//span[translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')="
            "        'purchase shipping label']]"
            ")"
        )
        el = candidates[0]          #only need to do the 1st one, as the page is refreshed after the click
        if el:
            try:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
                result = driver.execute_script("arguments[0].click();", el)
            except Exception as e:
                err_msg = get_traceback(e, "ErrorClickPurchaseLabelForUnshippedOnPage0")
                logger.debug(err_msg)
                result = err_msg
        else:
            result = "ERROR:No purchase label button found"

    except Exception as e:
        err_msg = get_traceback(e, "ErrorClickPurchaseLabelForUnshippedOnPage0")
        logger.debug(err_msg)
        result = err_msg
    return result


def wait_for_purchase_label_ui(driver, timeout: int = 20) -> bool:
    """Wait until the eBay print/label UI is ready.
    Signals: URL contains 'print' or 'label', or a heading 'Print documents', or a download link with id 'download-document'.
    """
    try:
        w = WebDriverWait(driver, timeout)
        return w.until(
            EC.any_of(
                EC.url_contains("print"),
                EC.url_contains("label"),
                EC.presence_of_element_located((By.XPATH, "//*[normalize-space(.)='Print documents']")),
                EC.presence_of_element_located((By.CSS_SELECTOR, "#download-document"))
            )
        ) is not None
    except Exception:
        return False


def save_current_label_pdf(driver, output_path: str) -> bool:
    """Cross-platform save of the current page as PDF via CDP.
    Ensure parent dir exists, then call printToPDF.
    """
    if not output_path:
        return False
    if not ensure_download_dir(output_path):
        logger.debug(f"Could not ensure directory for: {output_path}")
    ok = save_page_pdf_via_cdp(driver, output_path, options={
        "printBackground": True,
    })
    if not ok:
        logger.debug("CDP printToPDF failed to save PDF (eBay).")
    return ok


def _build_placeholder_label_html(meta: dict) -> str:
    order_id = meta.get("order_id", "EBAY-PLACEHOLDER-ORDER")
    buyer = meta.get("buyer", "")
    address_lines = meta.get("address", [])
    sku = meta.get("sku", "")
    qty = meta.get("quantity", "")
    today = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    addr_html = "<br/>".join(address_lines)
    return f"""
    <!doctype html>
    <html>
    <head>
      <meta charset='utf-8' />
      <title>eBay Placeholder Label</title>
      <style>
        body {{ font-family: Arial, sans-serif; margin: 24px; }}
        .card {{ border: 1px solid #ccc; padding: 16px; border-radius: 8px; }}
        .title {{ font-size: 20px; font-weight: 600; margin-bottom: 12px; }}
        .row {{ margin: 6px 0; }}
        .muted {{ color: #666; font-size: 12px; }}
        .barcode {{ margin-top: 24px; height: 48px; background: repeating-linear-gradient(90deg,#000 0,#000 4px,#fff 4px,#fff 8px); }}
      </style>
    </head>
    <body>
      <div class='card'>
        <div class='title'>eBay Shipping Label (Placeholder)</div>
        <div class='row'><strong>Order ID:</strong> {order_id}</div>
        <div class='row'><strong>Buyer:</strong> {buyer}</div>
        <div class='row'><strong>Ship To:</strong><br/>{addr_html}</div>
        <div class='row'><strong>SKU:</strong> {sku} &nbsp; <strong>Qty:</strong> {qty}</div>
        <div class='row muted'>Generated: {today}</div>
        <div class='barcode'></div>
      </div>
    </body>
    </html>
    """


def generate_placeholder_label_pdf(driver, output_path: str, meta: dict) -> bool:
    """Create a simple HTML label as a data URL, navigate to it, and save to PDF via CDP.
    This produces a valid PDF without external dependencies.
    """
    try:
        if not ensure_download_dir(output_path):
            return False
        html = _build_placeholder_label_html(meta)
        import base64
        # Encode HTML into a data URL to avoid serving a local file
        data_url = "data:text/html;base64," + base64.b64encode(html.encode("utf-8")).decode("ascii")
        prev_url = driver.current_url
        driver.get(data_url)
        # Give the browser a moment to render
        WebDriverWait(driver, 5).until(lambda d: True)
        ok = save_page_pdf_via_cdp(driver, output_path, options={"printBackground": True})
        # Try to restore previous URL (best-effort)
        try:
            if prev_url and prev_url.startswith("http"):
                driver.get(prev_url)
        except Exception:
            pass
        return ok
    except Exception as e:
        logger.debug(f"Placeholder label generation failed: {e}")
        return False

# will use this function to scrape bulk label orders
# for now let's define bulk as 100 orders, if there are
# more than 100 orders, we will need to use bulk mode
def scrape_bulk_label_orders(webdriver):
    try:
        logger.debug("labels")
    except Exception as e:
        err_msg = get_traceback(e, "ErrorScrapeBulkLabelOrders")
        logger.debug(err_msg)
        return {"error": err_msg}



async def ebay_fullfill_next_order(mainwin, args):  # type: ignore
    try:
        logger.debug("fullfill_ebay_orders started....", args["input"])
        new_orders = []
        fullfilled_orders = []
        options = args["input"]["options"]
        if options.get("use_ads", False):
            webdriver = connect_to_adspower(mainwin, url)
            if webdriver:
                mainwin.setWebDriver(webdriver)
        else:
            webdriver = mainwin.getWebDriver()

        if webdriver:
            print("fullfill_ebay_orders:", site)
            site_results = selenium_search_component(webdriver, pf, sites[site])
            ebay_new_orders = scrape_ebay_orders(webdriver)
            logger.debug("ebay_new_orders:", ebay_new_orders)

        msg = f"completed in fullfilling ebay new orders: {len(new_orders)} new orders came in, {len(fullfilled_orders)} orders processed."
        tool_result = TextContent(type="text", text=msg)
        tool_result.meta = {"new_orders": new_orders, "fullfilled_orders": fullfilled_orders}
        return [tool_result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorFullfillEbayOrders")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]



async def ebay_cancel_orders(mainwin, args):  # type: ignore
    try:
        logger.debug("fullfill_ebay_orders started....", args["input"])
        new_orders = []
        fullfilled_orders = []
        options = args["input"]["options"]
        if options.get("use_ads", False):
            webdriver = connect_to_adspower(mainwin, url)
            if webdriver:
                mainwin.setWebDriver(webdriver)
        else:
            webdriver = mainwin.getWebDriver()

        if webdriver:
            print("fullfill_ebay_orders:", site)
            site_results = selenium_search_component(webdriver, pf, sites[site])
            ebay_new_orders = scrape_ebay_orders(webdriver)
            logger.debug("ebay_new_orders:", ebay_new_orders)

        msg = f"completed in fullfilling ebay new orders: {len(new_orders)} new orders came in, {len(fullfilled_orders)} orders processed."
        tool_result = TextContent(type="text", text=msg)
        tool_result.meta = {"new_orders": new_orders, "fullfilled_orders": fullfilled_orders}
        return [tool_result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorFullfillEbayOrders")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]



def add_fullfill_ebay_orders_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="fullfill_ebay_orders",
        description="fullfill ebay orders by scraping orders list, for unshipped ones, click on buy shipping to obtain the cheapest shipping labels, save them and return the list of labels files fullpath.",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["options"],
                    "properties": {
                        "options": {
                            "type": "object",
                            "description": "some options in json format",
                        }
                    },
                }
            }
        },
    )

    tool_schemas.append(tool_schema)


def add_get_ebay_summary_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="get_ebay_summary",
        description="get ebay numer of new orders and number of new messages.",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["store_url", "options"],
                    "properties": {
                        "store_url": {
                            "type": "string",
                            "description": "ebay store url",
                        },
                        "options": {
                            "type": "object",
                            "description": "some options in json format",
                        }
                    },
                }
            }
        },
    )

    tool_schemas.append(tool_schema)

def add_ebay_fullfill_next_order_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="ebay_fullfill_next_order",
        description="full fill next order by clicking on buy shipping to obtain the cheapest shipping label, reformat it, save it, send it to printer, and return the order details info in json format.",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["options"],
                    "properties": {
                        "options": {
                            "type": "object",
                            "description": "some options in json format including printer name, label format, etc. will use default if these info are missing anyways.",
                        }
                    },
                }
            }
        },
    )

    tool_schemas.append(tool_schema)




def add_ebay_cancel_orders_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="ebay_cancel_orders",
        description="full fill next order by clicking on buy shipping to obtain the cheapest shipping label, reformat it, save it, send it to printer, and return the order details info in json format.",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["options"],
                    "properties": {
                        "options": {
                            "type": "object",
                            "description": "some options in json format including printer name, label format, etc. will use default if these info are missing anyways.",
                        }
                    },
                }
            }
        },
    )

    tool_schemas.append(tool_schema)
