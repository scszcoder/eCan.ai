from datetime import datetime
import base64
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback
from mcp.types import CallToolResult, TextContent


def scrape_amz_fas_orders(web_driver):
    try:
        # Navigate to Amazon Seller Central Unshipped (MFN) orders
        web_driver.get("https://sellercentral.amazon.com/orders-v3/mfn/unshipped?page=1")

        wait = WebDriverWait(web_driver, 30)

        # Ensure we are logged in (detect sign-in form vs. orders table)
        logged_in = ensure_logged_in(web_driver, wait)
        if not logged_in:
            logger.debug("Amazon Seller Central login required. Aborting scrape.")
            return "LOGIN_REQUIRED"

        # Wait for the orders table or a zero-state to appear
        try:
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#orders-table")))
        except TimeoutException:
            # No table found; return empty list gracefully
            logger.debug("Amazon orders table not found within timeout; returning empty list.")
            return []

        def safe_text(el):
            return el.text.strip() if el is not None else None

        def find_opt_text(container, css):
            try:
                el = container.find_element(By.CSS_SELECTOR, css)
                return safe_text(el)
            except Exception:
                return None

        def find_opt_attr(container, css, attr):
            try:
                el = container.find_element(By.CSS_SELECTOR, css)
                return el.get_attribute(attr)
            except Exception:
                return None

        def find_value_in_body(container, td_data_test_id, label_prefix):
            try:
                cell = container.find_element(By.CSS_SELECTOR, f'td[data-test-id="{td_data_test_id}"] .cell-body')
                divs = cell.find_elements(By.CSS_SELECTOR, "div")
                for d in divs:
                    txt = d.text.strip()
                    if txt.lower().startswith(label_prefix.lower() + ":"):
                        return txt.split(":", 1)[1].strip()
                return None
            except Exception:
                return None

        orders = []

        def parse_current_page():
            rows = web_driver.find_elements(By.CSS_SELECTOR, "#orders-table tbody > tr")
            for tr in rows:
                try:
                    # Order ID and URL
                    order_id = None
                    order_url = None
                    try:
                        order_link = tr.find_element(By.CSS_SELECTOR, 'td[data-test-id="oth-order-details"] .cell-body-title a')
                        order_id = order_link.text.strip()
                        order_url = order_link.get_attribute("href")
                    except Exception:
                        pass

                    # Order date/time display (optional)
                    order_date_display = find_opt_text(tr, 'td[data-test-id="oth-order-date"] .cell-body > div:nth-of-type(2)')
                    order_time_display = find_opt_text(tr, 'td[data-test-id="oth-order-date"] .cell-body > div:nth-of-type(3)')

                    # Buyer name
                    buyer_name = find_opt_text(tr, 'td[data-test-id="oth-order-details"] [data-test-id="buyer-name-with-link"]')

                    # Product fields
                    product_name = find_opt_text(tr, 'td[data-test-id="oth-product-info"] .myo-list-orders-product-name-cell a[target="_blank"]')
                    asin = find_value_in_body(tr, "oth-product-info", "ASIN")
                    sku = find_value_in_body(tr, "oth-product-info", "SKU")
                    quantity = find_value_in_body(tr, "oth-product-info", "Quantity")
                    item_subtotal = find_value_in_body(tr, "oth-product-info", "Item subtotal")
                    image_url = find_opt_attr(tr, 'td[data-test-id="oth-image"] img', 'src')

                    # Order type + shipping dates
                    order_type = find_opt_text(tr, 'td[data-test-id="oth-customer-option"] .cell-body .cell-body-title')
                    ship_by = find_value_in_body(tr, "oth-customer-option", "Ship by date")
                    deliver_by = find_value_in_body(tr, "oth-customer-option", "Deliver by date")

                    # Status
                    status = find_opt_text(tr, 'td[data-test-id="oth-order-status"] .order-status-column .main-status')

                    orders.append({
                        "order_id": order_id,
                        "order_url": order_url,
                        "order_date_display": order_date_display,
                        "order_time_display": order_time_display,
                        "buyer_name": buyer_name,
                        "product_name": product_name,
                        "asin": asin,
                        "sku": sku,
                        "quantity": quantity,
                        "item_subtotal": item_subtotal,
                        "image_url": image_url,
                        "order_type": order_type,
                        "ship_by": ship_by,
                        "deliver_by": deliver_by,
                        "status": status,
                    })
                except Exception as row_err:
                    logger.debug(f"Error parsing order row: {row_err}")

        # Parse first page and then iterate pages while Next is enabled (safety-capped)
        parse_current_page()

        max_pages = 10
        pagesVisited = 1
        while pagesVisited < max_pages:
            try:
                pagination = web_driver.find_element(By.CSS_SELECTOR, ".pagination-controls .a-pagination")
                next_li = pagination.find_element(By.CSS_SELECTOR, "li.a-last")
                if "a-disabled" in (next_li.get_attribute("class") or ""):
                    break
                next_link = next_li.find_element(By.TAG_NAME, "a")
                web_driver.execute_script("arguments[0].click();", next_link)
                # Wait for table to update: wait for any row and small delay
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#orders-table tbody > tr")))
                parse_current_page()
                pagesVisited += 1
            except Exception:
                # No pagination or failed to navigate further
                break

        return orders

    except Exception as e:
        err_msg = get_traceback(e, "ErrorScrapeAmazonOrders")
        logger.debug(err_msg)
        return err_msg


def click_buy_shipping_on_details_page(driver, wait: WebDriverWait, timeout: int = 20) -> bool:
    """On the Order Details page, click the lower-right 'Buy shipping' button.
    Returns True if the click was performed and navigation started.
    """
    try:
        # Ensure we are on an order details page
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '[data-test-id="order-details-label"]')))

        # Primary selector: data-test-id anchor/button
        try:
            buy_anchor = driver.find_element(By.CSS_SELECTOR, '[data-test-id="buy-shipping-button"]')
            # If disabled container present, skip
            disabled_container = buy_anchor.find_element(By.XPATH, "ancestor::*[contains(@class,'disabled')]")
            if disabled_container:
                logger.debug("Buy shipping button is disabled on details page.")
                return False
        except Exception:
            buy_anchor = None

        # Fallback: locate button by visible text
        if buy_anchor is None:
            try:
                buy_anchor = driver.find_element(By.XPATH, "//span[normalize-space(.)='Buy shipping']/ancestor::a | //button[normalize-space(.)='Buy shipping']")
            except Exception:
                logger.debug("Buy shipping button not found on details page.")
                return False

        # Scroll into view and click via JS to avoid overlay issues
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", buy_anchor)
        driver.execute_script("arguments[0].click();", buy_anchor)

        # Optionally wait for Buy Shipping UI to appear (service list or label form)
        try:
            WebDriverWait(driver, timeout).until(
                EC.any_of(
                    EC.presence_of_element_located((By.CSS_SELECTOR, '[data-test-id^="shipping-service-name-"]')),
                    EC.presence_of_element_located((By.CSS_SELECTOR, '#modal-order-details-shipping-service-selector')),
                    EC.url_contains('/buy-shipping')
                )
            )
        except Exception:
            # Navigation/UI might be on same page; that's acceptable
            pass

        target_pdf = "/path/to/labels/order_114-8723145-4091425.pdf"
        ok = save_page_pdf_via_cdp(driver, target_pdf, options={
            "printBackground": True,
            # Optional: "paperWidth": 8.5, "paperHeight": 11, "marginTop": 0.25, ...
        })
        if not ok:
            logger.debug("CDP printToPDF failed to save PDF.")

        return True
    except Exception as e:
        logger.debug(f"Failed to click Buy shipping on details page: {e}")
        return False
 
 
def ensure_logged_in(driver, wait: WebDriverWait, timeout: int = 30) -> bool:
    """Return True if orders table is present; False if on the sign-in page.
    Detects by presence of Seller Central sign-in elements or URL patterns.
    """
    try:
        # Quick URL-based check
        url = driver.current_url or ""
        if any(x in url for x in ["/ap/signin", "signin", "authportal"]):
            return False
 
        # DOM-based wait: either table present or login form present
        def condition(d):
            try:
                if d.find_elements(By.CSS_SELECTOR, "#orders-table"):
                    return True
                if d.find_elements(By.CSS_SELECTOR, "#ap_email") or d.find_elements(By.CSS_SELECTOR, "form[name='signIn']"):
                    return False
            except Exception:
                pass
            return None
 
        result = wait.until(lambda d: condition(d) is not None and condition(d))
        return bool(result)
    except TimeoutException:
        # If we didn't find table nor explicit login, assume not logged in
        return False
    except Exception:
        return False
 
 
def click_buy_shipping_for_unshipped_on_page(driver, wait: WebDriverWait, max_clicks: int = 1) -> int:
    """Iterate the current page orders; for rows with status containing 'Unshipped',
    click the primary 'Buy shipping' button in the action dropdown.
    Returns the number of clicks performed. Note: Clicking typically navigates away.
    """
    clicks = 0
    try:
        rows = driver.find_elements(By.CSS_SELECTOR, "#orders-table tbody > tr")
        for tr in rows:
            if clicks >= max_clicks:
                break
            try:
                status_el = tr.find_element(By.CSS_SELECTOR, 'td[data-test-id="oth-order-status"] .order-status-column .main-status')
                status_text = status_el.text.strip().lower()
            except Exception:
                status_text = ""
 
            if "unshipped" in status_text:
                if _click_buy_shipping_in_row(driver, tr):
                    clicks += 1
                    break
    except Exception as e:
        logger.debug(f"Error during buy-shipping iteration: {e}")
    return clicks
 
 
def _click_buy_shipping_in_row(driver, tr) -> bool:
    """Attempt to click the 'Buy shipping' button within a row. Handles shadow DOM fallback.
    Returns True if a click was performed.
    """
    # Try kat-dropdown-button shadow root first
    try:
        host = tr.find_element(By.CSS_SELECTOR, 'td.myo-table-action-column kat-dropdown-button')
        shadow_root = driver.execute_script('return arguments[0].shadowRoot', host)
        if shadow_root:
            buy_btn = driver.execute_script(
                'return arguments[0].querySelector("button[data-action=\\"buyShipping\\"]")',
                shadow_root,
            )
            if buy_btn:
                driver.execute_script("arguments[0].click();", buy_btn)
                return True
    except Exception:
        pass
 
    # Fallback: find a button by visible text
    try:
        btn = tr.find_element(By.XPATH, ".//button[contains(normalize-space(.), 'Buy shipping')]")
        driver.execute_script("arguments[0].click();", btn)
        return True
    except Exception:
        pass
 
    # Fallback: open toggle and then choose option with data-action="buyShipping"
    try:
        host = tr.find_element(By.CSS_SELECTOR, 'td.myo-table-action-column kat-dropdown-button')
        shadow_root = driver.execute_script('return arguments[0].shadowRoot', host)
        if shadow_root:
            toggle = driver.execute_script(
                'return arguments[0].querySelector("button.indicator")',
                shadow_root,
            )
            if toggle:
                driver.execute_script("arguments[0].click();", toggle)
                opt = driver.execute_script(
                    'return arguments[0].querySelector(".options .option[data-action=\\"buyShipping\\"]")',
                    shadow_root,
                )
                if opt:
                    driver.execute_script("arguments[0].click();", opt)
                    return True
    except Exception:
        pass
 
    logger.debug("Failed to locate 'Buy shipping' button in row")
    return False



def scrape_buyer_details_on_order_page(driver, wait: WebDriverWait, timeout: int = 20) -> dict:
    """Assumes the driver is currently on an Order Details page.
    Extract buyer name, phone, and address if available.
    Returns a dict with keys: order_id, recipient_name, phone, address_lines, address_type.
    """
    details = {
        "order_id": None,
        "recipient_name": None,
        "phone": None,
        "address_lines": None,
        "address_type": None,
    }
    try:
        # Wait for the Order details header to load
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '[data-test-id="order-details-label"]')))
    except TimeoutException:
        logger.debug("Order details header not found; cannot scrape buyer details.")
        return details

    # Order ID
    try:
        el = driver.find_element(By.CSS_SELECTOR, '[data-test-id="order-id-value"]')
        details["order_id"] = el.text.strip()
    except Exception:
        pass

    # Phone
    try:
        phone_el = driver.find_element(By.CSS_SELECTOR, '[data-test-id="shipping-section-phone"]')
        details["phone"] = phone_el.text.strip()
    except Exception:
        pass

    # Address type
    try:
        addr_type_el = driver.find_element(By.CSS_SELECTOR, '[data-test-id="shipping-section-buyer-address-type"]')
        details["address_type"] = addr_type_el.text.strip()
    except Exception:
        # In provided HTML, Address Type appeared as static text followed by value 'Residential'
        try:
            # Fallback: find the row containing 'Address Type' and read its trailing text
            row = driver.find_element(By.XPATH, "//span[contains(., 'Address Type')]/ancestor::div[contains(@class,'a-row')]")
            details["address_type"] = row.text.replace("Address Type:", "").strip()
        except Exception:
            pass

    # Recipient name and full address block
    try:
        # The address block contains multiple lines; get innerText as lines
        addr_block = driver.find_element(By.CSS_SELECTOR, '[data-test-id="shipping-section-buyer-address"]')
        full = addr_block.text.splitlines()
        lines = [ln.strip() for ln in full if ln.strip()]
        details["address_lines"] = lines
        # Try to infer recipient from the first line if present
        if lines:
            details["recipient_name"] = lines[0]
    except Exception:
        # Alternate: recipient might be in a dedicated element
        try:
            recip = driver.find_element(By.CSS_SELECTOR, '[data-test-id="shipping-section-recipient-name"]')
            details["recipient_name"] = recip.text.strip()
        except Exception:
            pass

    return details


def open_order_details_and_scrape_buyer(driver, wait: WebDriverWait, order_url: str) -> dict:
    """Navigate to the given order details URL, scrape buyer details, then navigate back.
    Returns the buyer details dict. If navigation fails, returns empty fields dict.
    """
    original_url = driver.current_url
    details = {
        "order_id": None,
        "recipient_name": None,
        "phone": None,
        "address_lines": None,
        "address_type": None,
    }
    try:
        driver.get(order_url)
        details = scrape_buyer_details_on_order_page(driver, wait)
    except Exception as e:
        logger.debug(f"Failed to scrape buyer details for {order_url}: {e}")
    finally:
        try:
            driver.get(original_url)
            # Wait for orders table to ensure we're back
            WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, '#orders-table')))
        except Exception:
            pass
    return details


def enrich_orders_with_buyer_details(driver, wait: WebDriverWait, orders: list, max_to_fetch: int | None = None) -> list:
    """Visit each order_url to collect buyer details and add under 'buyer' key.
    Optionally limit how many to fetch via max_to_fetch.
    Returns the modified orders list.
    """
    count = 0
    for o in orders:
        if max_to_fetch is not None and count >= max_to_fetch:
            break
        url = o.get("order_url")
        if not url:
            continue
        try:
            buyer = open_order_details_and_scrape_buyer(driver, wait, url)
            o["buyer"] = buyer
            count += 1
        except Exception as e:
            logger.debug(f"Failed to enrich order with buyer details: {e}")
            continue
    return orders



async def fullfill_amazon_fbs_orders(mainwin, args):  # type: ignore
    try:
        logger.debug("fullfill_amazon_fbs_orders started....")
        new_orders = []
        fullfilled_orders = []
        options = args["input"]["options"]
        web_driver = mainwin.getWebDriver()

        msg = f"completed in fullfilling amazon FBS new orders: {len(new_orders)} new orders came in, {len(fullfilled_orders)} orders processed."
        tool_result = TextContent(type="text", text=msg)
        tool_result.meta = {"new_orders": new_orders, "fullfilled_orders": fullfilled_orders}
        return [tool_result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorFullfillEtsyOrders")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]



def add_fullfill_amazon_fbs_orders_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="fullfill_amazon_fbs_orders",
        description="fullfill amazon FBS orders by scraping orders list, for unshipped ones, click on buy shipping to obtain the cheapest shipping labels, save them and return the list of labels files fullpath.",
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


def add_get_amazon_summary_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="get_amazon_summary",
        description="get amazon numer of new orders and number of new messages.",
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

def add_amazon_fullfill_next_order_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="amazon_fullfill_next_order",
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