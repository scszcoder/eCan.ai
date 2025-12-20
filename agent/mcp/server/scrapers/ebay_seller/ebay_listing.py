import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from selenium.common.exceptions import (
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.select import Select
from selenium.webdriver.support.ui import WebDriverWait

from agent.mcp.server.ads_power.ads_power import connect_to_adspower
from mcp.types import TextContent
from utils.logger_helper import get_traceback
from utils.logger_helper import logger_helper as logger

from .ebay_orders_scrape import ensure_logged_in_ebay


EBAY_ACTIVE_LISTINGS_URL = "https://www.ebay.com/sh/lst/active"
EBAY_ENDED_LISTINGS_URL = "https://www.ebay.com/sh/lst/completed"

LISTING_ROW_SELECTORS = [
    '[data-test-id="listing-row"]',
    'tr[data-test-id="listing-row"]',
    'tr[data-testid="listing-row"]',
    'tr[data-testid="list-row"]',
    'div[data-test-id="listing-row"]',
    'div[data-testid="listing-row"]',
    'div.sh-lst__row',
    'tr.l-table__row',
]

TITLE_SELECTORS = [
    '[data-test-id="listing-title"]',
    '.listing-card__title',
    '.list__item-title',
    'a.title',
]

PRICE_SELECTORS = [
    '[data-test-id="listing-price"]',
    '.listing-card__price',
    '.list__item-price',
    '.price',
]

SKU_SELECTORS = [
    '[data-test-id="listing-sku"]',
    '.listing-card__sku',
    '.sku',
]

QUANTITY_SELECTORS = [
    '[data-test-id="listing-quantity"]',
    '.listing-card__quantity',
    '.quantity',
]

STATUS_SELECTORS = [
    '[data-test-id="listing-status-chip"]',
    '.listing-card__status',
    '.status',
]

CLICKABLE_ELEMENT_SELECTORS = ",".join(
    [
        "a[href]",
        "button",
        "input[type='button']",
        "input[type='submit']",
        "div[role='button']",
        "span[role='button']",
        "a[role='button']",
    ]
)

MAX_OUTER_HTML_LENGTH = 1500

LOAD_MORE_SELECTORS = [
    "button[data-test-id='show-more']",
    "button[data-testid='show-more']",
    "button[data-test-id='pagination-next']",
    "a[data-test-id='pagination-next']",
    "button[aria-label*='Show'][aria-label*='more']",
    "button[aria-label*='Next']",
]

LISTING_FORM_FIELD_CONFIG: Dict[str, Dict[str, Any]] = {
    "title": {
        "selectors": [
            "input[name='title']",
            "input[data-test-id='listing-title']",
            "input[data-testid='listing-title']",
        ]
    },
    "subtitle": {
        "selectors": [
            "input[name='subtitle']",
            "input[data-test-id='listing-subtitle']",
            "input[data-testid='listing-subtitle']",
        ]
    },
    "custom_label": {
        "selectors": [
            "input[name='customLabel']",
            "input[name='sku']",
            "input[data-test-id='listing-custom-label']",
        ]
    },
    "price": {
        "selectors": [
            "input[name='price']",
            "input[data-test-id='price-input']",
            "input[data-testid='pricing-price']",
        ]
    },
    "quantity": {
        "selectors": [
            "input[name='quantity']",
            "input[data-test-id='quantity-input']",
            "input[data-testid='listing-quantity']",
        ]
    },
    "description_html": {
        "selectors": [
            "textarea[name='description']",
            "div[contenteditable='true'][data-test-id='description-editor']",
            "div[contenteditable='true'][data-testid='description-editor']",
        ]
    },
}

SAVE_BUTTON_CANDIDATES: List[Tuple[str, str]] = [
    ("css", "button[data-test-id='save']"),
    ("css", "button[data-testid='save']"),
    ("css", "button[data-test-id*='save']"),
    ("css", "button[type='submit'][data-testid*='save']"),
    ("css", "button[type='submit'][data-test-id*='save']"),
    ("css", "button[aria-label*='Save']"),
    ("xpath", "//button[normalize-space()='Save']"),
    ("xpath", "//button[contains(normalize-space(.), 'Save changes')]") ,
    ("xpath", "//button[contains(normalize-space(.), 'Save')]")
]


def scrape_ebay_listings(
    web_driver,
    target_url: str,
    status: str,
    max_items: Optional[int] = None,
) -> List[Dict]:
    listings: List[Dict] = []
    if not target_url:
        target_url = EBAY_ACTIVE_LISTINGS_URL if status == "active" else EBAY_ENDED_LISTINGS_URL

    try:
        web_driver.get(target_url)
    except Exception as exc:
        logger.debug(f"Failed to navigate to {target_url}: {exc}")
        return listings

    wait = WebDriverWait(web_driver, 30)
    if not ensure_logged_in_ebay(web_driver, wait):
        logger.debug("ensure_logged_in_ebay returned False. Aborting listings scrape.")
        return listings

    if not _wait_for_listing_rows(web_driver, wait):
        logger.debug("Timed out waiting for listing rows to appear")
        return listings

    seen_keys = set()

    while True:
        rows = _collect_listing_rows(web_driver)
        if not rows:
            break

        for row in rows:
            if max_items is not None and len(listings) >= max_items:
                break

            try:
                listing = _serialize_listing_row(row, status)
            except StaleElementReferenceException:
                continue
            except Exception as exc:
                logger.debug(f"Failed to serialize listing row: {exc}")
                continue

            key = _build_listing_key(listing)
            if key in seen_keys:
                continue

            seen_keys.add(key)
            listings.append(listing)

        if max_items is not None and len(listings) >= max_items:
            break

        if not _try_click_load_more(web_driver):
            break

        previous_count = len(rows)
        try:
            wait.until(
                lambda d: len(_collect_listing_rows(d)) > previous_count
            )
        except TimeoutException:
            logger.debug("No additional listing rows loaded after clicking load-more")
            break

    return listings


def _wait_for_listing_rows(web_driver, wait: WebDriverWait, timeout: int = 20) -> bool:
    for selector in LISTING_ROW_SELECTORS:
        try:
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
            return True
        except TimeoutException:
            continue
    return False


def scrape_listing_form_to_json(
    web_driver,
    field_config: Optional[Dict[str, Dict[str, Any]]] = None,
    wait_timeout: int = 15,
) -> Dict[str, Any]:
    """Scrape the revise-listing form into a structured JSON-like dict."""

    config = field_config or LISTING_FORM_FIELD_CONFIG
    wait = WebDriverWait(web_driver, wait_timeout)
    field_values: Dict[str, Any] = {}
    missing_fields: List[str] = []

    for field_name, definition in config.items():
        selectors = definition.get("selectors", [])
        element = _find_first_element(web_driver, selectors, wait)

        if not element:
            missing_fields.append(field_name)
            field_values[field_name] = None
            continue

        try:
            field_values[field_name] = _read_form_element_value(element)
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug(f"Failed reading field '{field_name}': {exc}")
            field_values[field_name] = None

    return {
        "scraped_at_utc": datetime.utcnow().isoformat(),
        "fields": field_values,
        "missing_fields": missing_fields,
    }


def update_listing_from_json(
    web_driver,
    listing_payload: Dict[str, Any],
    field_config: Optional[Dict[str, Dict[str, Any]]] = None,
    wait_timeout: int = 15,
    click_save: bool = True,
) -> Dict[str, Any]:
    """Update the revise-listing form based on the provided JSON payload."""

    config = field_config or LISTING_FORM_FIELD_CONFIG
    payload_fields = listing_payload.get("fields") if "fields" in listing_payload else listing_payload

    if not isinstance(payload_fields, dict):
        raise ValueError("listing_payload must be a dict or contain a 'fields' dict")

    wait = WebDriverWait(web_driver, wait_timeout)

    updated_fields: List[str] = []
    skipped_fields: Dict[str, str] = {}
    missing_fields: List[str] = []

    for field_name, new_value in payload_fields.items():
        if new_value is None:
            skipped_fields[field_name] = "value is None"
            continue

        definition = config.get(field_name)
        if not definition:
            skipped_fields[field_name] = "no selector configuration"
            continue

        selectors = definition.get("selectors", [])
        element = _find_first_element(web_driver, selectors, wait)
        if not element:
            missing_fields.append(field_name)
            continue

        try:
            current_value = _read_form_element_value(element)
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug(f"Failed reading current value for '{field_name}': {exc}")
            skipped_fields[field_name] = "read error"
            continue

        if _values_equal(current_value, new_value):
            skipped_fields[field_name] = "no change"
            continue

        try:
            _apply_form_element_value(web_driver, element, new_value)
            updated_fields.append(field_name)
        except Exception as exc:
            logger.debug(f"Failed updating field '{field_name}': {exc}")
            skipped_fields[field_name] = "update error"

    clicked_save = False
    if click_save and updated_fields:
        clicked_save = _click_save_button(web_driver)

    return {
        "updated_fields": updated_fields,
        "skipped_fields": skipped_fields,
        "missing_fields": missing_fields,
        "clicked_save": clicked_save,
        "updated_at_utc": datetime.utcnow().isoformat(),
    }


def _find_first_element(
    web_driver,
    selectors: List[str],
    wait: Optional[WebDriverWait] = None,
) -> Optional[WebElement]:
    for selector in selectors:
        try:
            if selector.startswith("//"):
                element = web_driver.find_element(By.XPATH, selector)
            else:
                if wait:
                    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                element = web_driver.find_element(By.CSS_SELECTOR, selector)
        except (NoSuchElementException, TimeoutException):
            continue
        except Exception:
            continue

        if element:
            return element
    return None


def _read_form_element_value(element: WebElement) -> Any:
    tag_name = (element.tag_name or "").lower()
    if tag_name == "input":
        input_type = (element.get_attribute("type") or "").lower()
        if input_type in {"checkbox", "radio"}:
            return element.is_selected()
        return (element.get_attribute("value") or "").strip()
    if tag_name == "textarea":
        return (element.get_attribute("value") or element.text or "").strip()
    if tag_name == "select":
        try:
            select = Select(element)
            option = select.first_selected_option
            return option.get_attribute("value") or option.text.strip()
        except Exception:
            return None
    if element.get_attribute("contenteditable") == "true":
        return element.get_attribute("innerHTML") or ""
    return (element.text or "").strip()


def _apply_form_element_value(web_driver, element: WebElement, value: Any) -> None:
    tag_name = (element.tag_name or "").lower()

    if tag_name == "input":
        input_type = (element.get_attribute("type") or "").lower()
        if input_type in {"checkbox", "radio"}:
            should_select = bool(value)
            if element.is_selected() != should_select:
                _ensure_element_in_view(web_driver, element)
                element.click()
            return

        _ensure_element_in_view(web_driver, element)
        try:
            element.clear()
        except Exception:
            pass
        try:
            element.send_keys(str(value))
            return
        except Exception:
            pass

        web_driver.execute_script(
            "arguments[0].value = arguments[1];"
            "arguments[0].dispatchEvent(new Event('input', { bubbles: true }));",
            element,
            str(value),
        )
        return

    if tag_name == "textarea":
        _ensure_element_in_view(web_driver, element)
        try:
            element.clear()
        except Exception:
            pass
        element.send_keys(str(value))
        return

    if tag_name == "select":
        select = Select(element)
        str_value = str(value)
        try:
            select.select_by_value(str_value)
        except Exception:
            try:
                select.select_by_visible_text(str_value)
            except Exception:
                raise
        return

    if element.get_attribute("contenteditable") == "true":
        web_driver.execute_script(
            "arguments[0].innerHTML = arguments[1];"
            "arguments[0].dispatchEvent(new Event('input', { bubbles: true }));",
            element,
            value,
        )
        return

    _ensure_element_in_view(web_driver, element)
    web_driver.execute_script(
        "arguments[0].textContent = arguments[1];"
        "arguments[0].dispatchEvent(new Event('input', { bubbles: true }));",
        element,
        value,
    )


def _values_equal(current: Any, new_value: Any) -> bool:
    if isinstance(current, str) and isinstance(new_value, str):
        return current.strip() == new_value.strip()
    return current == new_value


def _ensure_element_in_view(web_driver, element: WebElement) -> None:
    try:
        web_driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});",
            element,
        )
    except Exception:
        pass


def _click_save_button(web_driver) -> bool:
    for strategy, locator in SAVE_BUTTON_CANDIDATES:
        try:
            if strategy == "css":
                elements = web_driver.find_elements(By.CSS_SELECTOR, locator)
            else:
                elements = web_driver.find_elements(By.XPATH, locator)
        except Exception:
            continue

        for element in elements:
            try:
                if not element.is_displayed() or not element.is_enabled():
                    continue
            except StaleElementReferenceException:
                continue

            _ensure_element_in_view(web_driver, element)
            try:
                element.click()
                return True
            except Exception as exc:
                logger.debug(f"Failed clicking save button '{strategy}:{locator}': {exc}")
    return False

def _collect_listing_rows(web_driver) -> List:
    for selector in LISTING_ROW_SELECTORS:
        rows = web_driver.find_elements(By.CSS_SELECTOR, selector)
        if rows:
            return rows
    return []


def _serialize_listing_row(row, status: str) -> Dict:
    listing: Dict = {
        "status": status,
        "scraped_at_utc": datetime.utcnow().isoformat(),
    }

    listing["listing_id"] = _safe_get_attribute(row, "data-id") or _safe_get_attribute(row, "data-itemid") or row.get_attribute("id") or ""

    listing["title"] = _first_text_match(row, TITLE_SELECTORS)
    listing["price"] = _first_text_match(row, PRICE_SELECTORS)
    listing["sku"] = _first_text_match(row, SKU_SELECTORS)
    listing["quantity"] = _first_text_match(row, QUANTITY_SELECTORS)
    listing["status_label"] = _first_text_match(row, STATUS_SELECTORS)

    listing["detail_url"] = _extract_detail_url(row)

    listing["clickable_elements"] = _extract_clickable_elements(row)

    try:
        row_outer_html = row.get_attribute("outerHTML") or ""
    except StaleElementReferenceException:
        row_outer_html = ""
    listing["row_outer_html"] = _truncate_html(row_outer_html)
    listing["row_text"] = row.text.strip()

    return listing


def _extract_detail_url(row) -> str:
    for selector in TITLE_SELECTORS:
        try:
            title_el = row.find_element(By.CSS_SELECTOR, selector)
        except NoSuchElementException:
            continue

        if title_el.tag_name.lower() == "a":
            href = title_el.get_attribute("href") or ""
            if href:
                return href

        try:
            anchor = title_el.find_element(By.CSS_SELECTOR, "a[href]")
            href = anchor.get_attribute("href") or ""
            if href:
                return href
        except NoSuchElementException:
            continue

    try:
        default_anchor = row.find_element(By.CSS_SELECTOR, "a[href]")
        return default_anchor.get_attribute("href") or ""
    except NoSuchElementException:
        return ""


def _extract_clickable_elements(row) -> List[Dict]:
    elements_data: List[Dict] = []
    seen_ids = set()

    try:
        elements = row.find_elements(By.CSS_SELECTOR, CLICKABLE_ELEMENT_SELECTORS)
    except Exception as exc:
        logger.debug(f"Failed to locate clickable elements: {exc}")
        return elements_data

    for element in elements:
        element_id = getattr(element, "id", None)
        if element_id and element_id in seen_ids:
            continue
        if element_id:
            seen_ids.add(element_id)

        try:
            tag = element.tag_name.lower()
        except StaleElementReferenceException:
            continue
        except Exception:
            tag = ""

        try:
            text_value = (element.text or "").strip()
        except StaleElementReferenceException:
            text_value = ""

        aria_label = _safe_get_attribute(element, "aria-label")
        href_value = _safe_get_attribute(element, "href")
        data_test_id = _safe_get_attribute(element, "data-test-id") or _safe_get_attribute(element, "data-testid")
        element_id_attr = _safe_get_attribute(element, "id")
        element_class = _safe_get_attribute(element, "class")
        role_attr = _safe_get_attribute(element, "role")

        try:
            enabled = element.is_enabled()
        except StaleElementReferenceException:
            enabled = False
        except Exception:
            enabled = False

        try:
            displayed = element.is_displayed()
        except StaleElementReferenceException:
            displayed = False
        except Exception:
            displayed = False

        try:
            outer_html = element.get_attribute("outerHTML") or ""
        except StaleElementReferenceException:
            outer_html = ""

        elements_data.append(
            {
                "tag": tag,
                "text": text_value,
                "aria_label": aria_label,
                "href": href_value,
                "data_test_id": data_test_id,
                "id": element_id_attr,
                "class": element_class,
                "role": role_attr,
                "enabled": enabled,
                "displayed": displayed,
                "outer_html": _truncate_html(outer_html),
            }
        )

    return elements_data


def _first_text_match(root, selectors: List[str]) -> str:
    for selector in selectors:
        try:
            element = root.find_element(By.CSS_SELECTOR, selector)
        except NoSuchElementException:
            continue
        except StaleElementReferenceException:
            continue

        text_value = (element.text or "").strip()
        if text_value:
            return text_value

    return ""


def _safe_get_attribute(element, attribute: str) -> str:
    try:
        value = element.get_attribute(attribute)
        return (value or "").strip()
    except StaleElementReferenceException:
        return ""
    except Exception:
        return ""


def _truncate_html(html: str) -> str:
    if not html:
        return ""
    if len(html) <= MAX_OUTER_HTML_LENGTH:
        return html
    return f"{html[:MAX_OUTER_HTML_LENGTH]}...<!-- truncated -->"


def _build_listing_key(listing: Dict) -> str:
    key_parts = [
        listing.get("listing_id", ""),
        listing.get("sku", ""),
        listing.get("detail_url", ""),
        listing.get("title", ""),
    ]
    key = "|".join(part for part in key_parts if part)
    if not key:
        key = listing.get("row_outer_html", "")[:128]
    return key


def _try_click_load_more(web_driver) -> bool:
    for selector in LOAD_MORE_SELECTORS:
        try:
            button = web_driver.find_element(By.CSS_SELECTOR, selector)
        except NoSuchElementException:
            continue
        except Exception:
            continue

        try:
            web_driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
        except Exception:
            pass

        try:
            if button.is_enabled():
                button.click()
                time.sleep(1.2)
                return True
        except Exception as exc:
            logger.debug(f"Failed to click load-more button {selector}: {exc}")

    return False


async def ebay_add_listings(mainwin, args):  # type: ignore
    try:
        logger.debug("ebay_add_listings started....")
        executed = []
        messages_todos = args["input"]["messages_todos"]
        web_driver = mainwin.getWebDriver()

        msg = f"completed in adding ebay listings: {len(executed)} messages answered."
        tool_result = TextContent(type="text", text=msg)
        tool_result.meta = {"executed": executed}
        return [tool_result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorEBAYAddListings")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]




async def ebay_remove_listings(mainwin, args):  # type: ignore
    try:
        logger.debug("ebay_remove_listings started....")
        executed = []
        messages_todos = args["input"]["messages_todos"]
        web_driver = mainwin.getWebDriver()

        msg = f"completed in remove ebay listings: {len(executed)} messages answered."
        tool_result = TextContent(type="text", text=msg)
        tool_result.meta = {"executed": executed}
        return [tool_result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorEBAYRemoveListings")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def ebay_update_listings(mainwin, args):  # type: ignore
    try:
        logger.debug("answer_ebay_messages started....")
        executed = []
        messages_todos = args["input"]["messages_todos"]
        web_driver = mainwin.getWebDriver()

        msg = f"completed in updating ebay listings: {len(executed)} messages answered."
        tool_result = TextContent(type="text", text=msg)
        tool_result.meta = {"executed": executed}
        return [tool_result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorEBAYUpdateListings")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]



async def ebay_get_listings(mainwin, args):  # type: ignore
    try:
        logger.debug("ebay_get_listings started....")
        input_payload = args.get("input") or {}
        options = input_payload.get("options") or {}
        include_active = options.get("include_active", True)
        include_ended = options.get("include_ended", False)
        max_listings = options.get("max_listings")

        web_driver = mainwin.getWebDriver()
        if not web_driver:
            store_url = options.get("store_url", EBAY_ACTIVE_LISTINGS_URL)
            web_driver = connect_to_adspower(mainwin, store_url)

        listings_payload: Dict[str, List[Dict]] = {}

        if include_active:
            listings_payload["active_listings"] = scrape_ebay_listings(
                web_driver,
                EBAY_ACTIVE_LISTINGS_URL,
                status="active",
                max_items=max_listings,
            )

        if include_ended:
            listings_payload["ended_listings"] = scrape_ebay_listings(
                web_driver,
                EBAY_ENDED_LISTINGS_URL,
                status="ended",
                max_items=max_listings,
            )

        msg = "completed in getting ebay listings"
        tool_result = TextContent(type="text", text=msg)
        tool_result.meta = listings_payload
        return [tool_result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorEBAYGetListings")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def ebay_add_listing_templates(mainwin, args):  # type: ignore
    try:
        logger.debug("ebay_add_listing_templates started....")
        executed = []
        messages_todos = args["input"]["messages_todos"]
        web_driver = mainwin.getWebDriver()

        msg = f"completed in add ebay listing templates: {len(executed)} messages answered."
        tool_result = TextContent(type="text", text=msg)
        tool_result.meta = {"executed": executed}
        return [tool_result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorEBAYAddListingTemplates")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def ebay_remove_listing_templates(mainwin, args):  # type: ignore
    try:
        logger.debug("ebay_remove_listing_templates started....")
        executed = []
        messages_todos = args["input"]["messages_todos"]
        web_driver = mainwin.getWebDriver()

        msg = f"completed in removing ebay listing templates: {len(executed)} messages answered."
        tool_result = TextContent(type="text", text=msg)
        tool_result.meta = {"executed": executed}
        return [tool_result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorEBAYRemoveListingTemplates")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def ebay_update_listing_templates(mainwin, args):  # type: ignore
    try:
        logger.debug("ebay_update_listing_templates started....")
        executed = []
        messages_todos = args["input"]["messages_todos"]
        web_driver = mainwin.getWebDriver()

        msg = f"completed in updating ebay listing templates: {len(executed)} messages answered."
        tool_result = TextContent(type="text", text=msg)
        tool_result.meta = {"executed": executed}
        return [tool_result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorEBAYUpdateListingTemplates")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]


def add_ebay_add_listings_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="ebay_add_listings",
        description="create after work summary for easy viewing by both human and agent.",
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



def add_ebay_remove_listings_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="ebay_remove_listings",
        description="create after work summary for easy viewing by both human and agent.",
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


def add_ebay_update_listings_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="ebay_update_listings",
        description="create after work summary for easy viewing by both human and agent.",
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


def add_ebay_add_listing_templates_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="ebay_add_listing_templates",
        description="ebay add listing templates.",
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


def add_ebay_remove_listing_templates_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="ebay_remove_listing_templates",
        description="ebay remove listing templates.",
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


def add_ebay_update_listing_templates_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="ebay_update_listing_templates",
        description="ebay update listing templates.",
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




def add_ebay_get_listings_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="ebay_get_listings",
        description="ebay update listing templates.",
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