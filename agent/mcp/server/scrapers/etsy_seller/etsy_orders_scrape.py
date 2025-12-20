from datetime import datetime
import base64
import os
from urllib.request import Request, urlopen
from urllib.parse import urlparse, parse_qs
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback
from mcp.types import CallToolResult, TextContent


def scrape_etsy_summaries(web_driver):
    try:
        logger.debug("scrape_etsy_summaries started....")
        wait = WebDriverWait(web_driver, 15)
        orders_count = 0
        try:
            orders_container = wait.until(
                EC.presence_of_element_located(
                    (By.XPATH, "//p[contains(@class,'wt-text-title-small') and normalize-space()='Orders']/ancestor::div[contains(@class,'wt-display-inline-flex-xs')][1]")
                )
            )
            try:
                counter_el = orders_container.find_element(By.CSS_SELECTOR, "span.wt-counter-indicator")
                counter_text = counter_el.get_attribute("textContent").strip()
                digits = "".join(ch for ch in counter_text if ch.isdigit())
                if digits:
                    orders_count = int(digits)
            except Exception:
                pass
        except TimeoutException:
            pass

        messages_count = 0
        try:
            messages_container = wait.until(
                EC.presence_of_element_located(
                    (By.XPATH, "//p[contains(@class,'wt-text-title-small') and normalize-space()='Messages']/ancestor::*[self::a or self::div][1]")
                )
            )
            try:
                counter_el = messages_container.find_element(By.CSS_SELECTOR, "span.wt-counter-indicator")
                counter_text = counter_el.get_attribute("textContent").strip()
                digits = "".join(ch for ch in counter_text if ch.isdigit())
                if digits:
                    messages_count = int(digits)
            except Exception:
                pass
        except TimeoutException:
            pass

        return {"orders_count": orders_count, "messages_count": messages_count}
    except Exception as e:
        err_trace = get_traceback(e, "ErrorScrapeEtsySummaries")
        logger.debug(err_trace)
        return {"orders_count": 0, "messages_count": 0}



def scrape_etsy_pageful_of_orders(web_driver):
    try:
        logger.debug("scrape_etsy_pageful_of_orders started....")
        wait = WebDriverWait(web_driver, 15)
        section = wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "section[aria-label='orders']"))
        )
        rows = section.find_elements(By.CSS_SELECTOR, ".panel-body .panel-body-row.has-hover-state")
        results = []
        for row in rows:
            buyer_name = None
            try:
                buyer_el = row.find_element(By.XPATH, ".//button[@data-dropdown-button='true']//span[@data-test-id='unsanitize']")
                buyer_name = buyer_el.get_attribute("textContent").strip()
            except Exception:
                pass

            order_id = None
            try:
                order_link = row.find_element(By.XPATH, ".//a[contains(@href,'order_id=')]")
                href = order_link.get_attribute("href")
                parsed = urlparse(href)
                q = parse_qs(parsed.query)
                if "order_id" in q and len(q["order_id"]) > 0:
                    order_id = q["order_id"][0]
                if not order_id:
                    text = order_link.get_attribute("textContent").strip().lstrip("#")
                    if text.isdigit():
                        order_id = text
            except Exception:
                pass

            quantity = None
            try:
                qty_el = row.find_element(By.XPATH, ".//span[normalize-space()='Quantity']/following-sibling::span[contains(@class,'strong')]")
                quantity_text = qty_el.get_attribute("textContent").strip()
                if quantity_text.isdigit():
                    quantity = int(quantity_text)
            except Exception:
                pass

            product_title = None
            try:
                title_el = row.find_element(By.XPATH, ".//div[contains(@class,'break-word')]//span[@data-test-id='unsanitize']")
                product_title = title_el.get_attribute("textContent").strip()
            except Exception:
                pass

            product_price = None
            try:
                price_el = row.find_element(By.XPATH, ".//span[starts-with(normalize-space(),'$')]")
                product_price = price_el.get_attribute("textContent").strip()
            except Exception:
                pass

            shipping_label_button_xpath = None
            if order_id:
                shipping_label_button_xpath = f"//a[contains(@href,'order_id={order_id}')]/ancestor::div[contains(@class,'panel-body-row')][1]//button[@data-test-id='purchase-shipping-label-button']"

            order_actions_button_xpath = None
            if order_id:
                order_actions_button_xpath = f"//a[contains(@href,'order_id={order_id}')]/ancestor::div[contains(@class,'panel-body-row')][1]//button[@aria-label='Order actions']"

            complete_order_button_xpath = None
            if order_id:
                complete_order_button_xpath = f"//a[contains(@href,'order_id={order_id}')]/ancestor::div[contains(@class,'panel-body-row')][1]//span[@data-test-id='no-user-defined-steps-update-progress-button']//button"

            results.append({
                "buyer_name": buyer_name,
                "order_id": order_id,
                "quantity": quantity,
                "product_title": product_title,
                "product_price": product_price,
                "shipping_label_button_xpath": shipping_label_button_xpath,
                "order_actions_button_xpath": order_actions_button_xpath,
                "complete_order_button_xpath": complete_order_button_xpath,
            })

        return results
    except Exception as e:
        err_trace = get_traceback(e, "ErrorScrapeEtsySummaries")
        logger.debug(err_trace)
        return []



def parse_recipient_address_contact(web_driver):
    try:
        wait = WebDriverWait(web_driver, 15)
        side = wait.until(EC.presence_of_element_located((By.XPATH, "//h4[normalize-space()='Ship to']/following-sibling::div[1]")))
        name = None
        first_line = None
        city = None
        state = None
        zip_code = None
        country = None
        try:
            name = side.find_element(By.CSS_SELECTOR, ".address .name").get_attribute("textContent").strip()
        except Exception:
            pass
        try:
            first_line = side.find_element(By.CSS_SELECTOR, ".address .first-line").get_attribute("textContent").strip()
        except Exception:
            pass
        try:
            city = side.find_element(By.CSS_SELECTOR, ".address .city").get_attribute("textContent").strip()
        except Exception:
            pass
        try:
            state = side.find_element(By.CSS_SELECTOR, ".address .state").get_attribute("textContent").strip()
        except Exception:
            pass
        try:
            zip_code = side.find_element(By.CSS_SELECTOR, ".address .zip").get_attribute("textContent").strip()
        except Exception:
            pass
        try:
            country = side.find_element(By.CSS_SELECTOR, ".address .country-name").get_attribute("textContent").strip()
        except Exception:
            pass
        return {
            "name": name,
            "first_line": first_line,
            "city": city,
            "state": state,
            "zip": zip_code,
            "country": country,
        }
    except Exception:
        return {}


def fill_package_details(web_driver, ref):
    try:
        wait = WebDriverWait(web_driver, 10)
        try:
            if ref.get("package_type"):
                select_el = wait.until(EC.presence_of_element_located((By.ID, "package-type")))
                Select(select_el).select_by_value(ref.get("package_type"))
        except Exception:
            pass
        try:
            fieldset = wait.until(EC.presence_of_element_located((By.XPATH, "//fieldset[.//legend[contains(normalize-space(),'Package weight')]]")))
            inputs = fieldset.find_elements(By.XPATH, ".//input[@type='number']")
            pounds = ref.get("pounds")
            ounces = ref.get("ounces")
            if len(inputs) >= 1 and pounds is not None:
                inputs[0].clear(); inputs[0].send_keys(str(pounds))
            if len(inputs) >= 2 and ounces is not None:
                inputs[1].clear(); inputs[1].send_keys(str(ounces))
        except Exception:
            pass
        try:
            if all(k in ref for k in ("length", "width", "height")):
                length_el = wait.until(EC.presence_of_element_located((By.ID, "length")))
                width_el = wait.until(EC.presence_of_element_located((By.ID, "width")))
                height_el = wait.until(EC.presence_of_element_located((By.ID, "height")))
                length_el.clear(); length_el.send_keys(str(ref.get("length")))
                width_el.clear(); width_el.send_keys(str(ref.get("width")))
                height_el.clear(); height_el.send_keys(str(ref.get("height")))
        except Exception:
            pass
        return True
    except Exception:
        return False


def select_cheapest_service(web_driver):
    try:
        wait = WebDriverWait(web_driver, 15)
        containers = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".delivery-service-selectable .delivery-service-selectable__item")))
        cheapest = None
        cheapest_price = None
        cheapest_radio = None
        for c in containers:
            try:
                price_el = c.find_element(By.CSS_SELECTOR, "[data-test-id='delivery-service-cost']")
                price_text = price_el.get_attribute("textContent").strip()
                price_num = None
                try:
                    price_num = float(price_text.replace("$", "").replace(",", "").strip())
                except Exception:
                    continue
                try:
                    radio = c.find_element(By.XPATH, ".//input[@type='radio']")
                except Exception:
                    radio = None
                if price_num is not None and (cheapest_price is None or price_num < cheapest_price):
                    cheapest_price = price_num
                    cheapest = c
                    cheapest_radio = radio
            except Exception:
                continue
        if cheapest is not None and cheapest_radio is not None:
            try:
                web_driver.execute_script("arguments[0].click();", cheapest_radio)
            except Exception:
                try:
                    label = cheapest.find_element(By.XPATH, ".//label[@for=substring(@for,'dg-panels-preact__selectables-') or @class='wt-btn wt-action-group__item wt-btn--small']")
                    label.click()
                except Exception:
                    pass
        return {"price": cheapest_price}
    except Exception:
        return {"price": None}

def confirm_label_purchase(web_driver, expected_price, tolerance=0.05):
    try:
        wait = WebDriverWait(web_driver, 20)
        try:
            eula = WebDriverWait(web_driver, 2).until(
                EC.presence_of_element_located((By.XPATH, "//h2[contains(normalize-space(),'Accept the FedEx user agreement to complete your purchase')]/ancestor::div[contains(@class,'wt-overlay__modal')]"))
            )
            try:
                cb = eula.find_element(By.XPATH, ".//input[@type='checkbox']")
                web_driver.execute_script("arguments[0].click();", cb)
            except Exception:
                pass
            try:
                accept_btn = WebDriverWait(eula, 10).until(
                    EC.element_to_be_clickable((By.XPATH, ".//button[normalize-space()='I accept' and not(@disabled) and not(@aria-disabled='true') ]"))
                )
                accept_btn.click()
            except Exception:
                pass
        except Exception:
            pass
        wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "[data-test-id='shipping-label-purchase-confirmation-header']"))
        )
        view = wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "[data-test-id='shipping-label-purchase-confirmation-view']"))
        )
        total_el = view.find_element(By.XPATH, ".//div[contains(@class,'display-flex-xs') and .//div[normalize-space()='Total']]/div[last()]")
        total_text = total_el.get_attribute("textContent").strip()
        total_num = float(total_text.replace("$", "").replace(",", "").strip()) if total_text else None
        ok = False
        if expected_price is not None and total_num is not None:
            ok = abs(total_num - float(expected_price)) <= float(tolerance)
        if ok:
            try:
                purchase_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "[data-test-id='shipping-purchase-labels-button']")))
                purchase_btn.click()
                try:
                    eula = WebDriverWait(web_driver, 3).until(
                        EC.presence_of_element_located((By.XPATH, "//h2[contains(normalize-space(),'Accept the FedEx user agreement to complete your purchase')]/ancestor::div[contains(@class,'wt-overlay__modal')]"))
                    )
                    try:
                        cb = eula.find_element(By.XPATH, ".//input[@type='checkbox']")
                        web_driver.execute_script("arguments[0].click();", cb)
                    except Exception:
                        pass
                    try:
                        accept_btn = WebDriverWait(eula, 10).until(
                            EC.element_to_be_clickable((By.XPATH, ".//button[normalize-space()='I accept' and not(@disabled) and not(@aria-disabled='true') ]"))
                        )
                        accept_btn.click()
                    except Exception:
                        pass
                    try:
                        purchase_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "[data-test-id='shipping-purchase-labels-button']")))
                        purchase_btn.click()
                    except Exception:
                        pass
                except Exception:
                    pass
                return {"purchased": True, "price": total_num}
            except Exception:
                pass
        try:
            cancel_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "[data-test-id='shipping-purchase-labels-cancel-button']")))
            cancel_btn.click()
        except Exception:
            pass
        return {"purchased": False, "price": total_num}
    except Exception:
        return {"purchased": False, "price": None}

def handle_post_purchase_and_download(web_driver, order, download_opts):
    try:
        wait = WebDriverWait(web_driver, 20)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "[data-test-id='post-purchase-view-title']")))
        try:
            container = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "[data-test-id='post-purchase-view-content']")))
        except Exception:
            container = None
        try:
            buttons = web_driver.find_elements(By.CSS_SELECTOR, ".wt-content-toggle--btn")
            for b in buttons:
                try:
                    expanded = b.get_attribute("aria-expanded")
                    if expanded == "false":
                        b.click()
                except Exception:
                    continue
        except Exception:
            pass
        try:
            joined_radio = web_driver.find_element(By.XPATH, "//input[@type='radio' and @id='joined' and @name='downloadPreference']")
            if not joined_radio.is_selected():
                web_driver.execute_script("arguments[0].click();", joined_radio)
        except Exception:
            pass
        try:
            scope = container if container else web_driver
            cbs = scope.find_elements(By.XPATH, ".//input[@type='checkbox']")
            for cb in cbs:
                try:
                    if not cb.is_selected():
                        web_driver.execute_script("arguments[0].click();", cb)
                except Exception:
                    continue
        except Exception:
            pass
        link_el = wait.until(EC.presence_of_element_located((By.XPATH, "//a[normalize-space()='Print shipping labels']")))
        href = link_el.get_attribute("href")
        cookies = web_driver.get_cookies()
        cookie_header = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
        req = Request(href, headers={"Cookie": cookie_header, "User-Agent": "Mozilla/5.0"})
        resp = urlopen(req)
        data = resp.read()
        dir_path = download_opts.get("dir") if isinstance(download_opts, dict) else None
        if not dir_path:
            dir_path = os.path.join(os.path.expanduser("~"), "Downloads")
        try:
            os.makedirs(dir_path, exist_ok=True)
        except Exception:
            pass
        order_id = None
        try:
            order_id = order.get("order_id") if isinstance(order, dict) else None
        except Exception:
            order_id = None
        filename = None
        if isinstance(download_opts, dict):
            filename = download_opts.get("filename")
        if not filename:
            base = f"etsy_label_{order_id}.pdf" if order_id else "etsy_label.pdf"
            filename = base
        save_path = os.path.join(dir_path, filename)
        with open(save_path, "wb") as f:
            f.write(data)
        try:
            done_btn = web_driver.find_element(By.XPATH, "//div[contains(@class,'wt-overlay__footer')]//button[normalize-space()='Done']")
            done_btn.click()
        except Exception:
            pass
        return {"saved_path": save_path, "href": href}
    except Exception:
        return {"saved_path": None, "href": None}

async def fullfill_one_etsy_orders(mainwin, args):  # type: ignore
    try:
        logger.debug("fullfill_etsy_orders started....")
        web_driver = mainwin.getWebDriver()
        new_orders = []
        fullfilled_orders = []
        options = args["input"]["options"]
        summaries = scrape_etsy_summaries(web_driver)
        orders_count = summaries.get("orders_count", 0)
        messages_count = summaries.get("messages_count", 0)
        logger.debug(f"etsy orders count detected: {orders_count}")
        logger.debug(f"etsy messages count detected: {messages_count}")
        orders = scrape_etsy_pageful_of_orders(web_driver)
        if orders:
            try:
                xpath = orders[0].get("shipping_label_button_xpath")
                if xpath:
                    btn = WebDriverWait(web_driver, 10).until(EC.element_to_be_clickable((By.XPATH, xpath)))
                    btn.click()
                    logger.debug("clicked shipping label button for first order")
            except Exception:
                logger.debug("failed clicking shipping label button for first order")
        try:
            overlay_ready = WebDriverWait(web_driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "[data-test-id='shipping-review-purchase-button']"))
            )
            addr = parse_recipient_address_contact(web_driver)
            pkg_ref = options.get("package", {})
            fill_package_details(web_driver, pkg_ref)
            cheapest = select_cheapest_service(web_driver)
            try:
                review_btn = WebDriverWait(web_driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "[data-test-id='shipping-review-purchase-button']"))
                )
                review_btn.click()
                logger.debug("clicked review button after selecting cheapest service")
            except Exception:
                pass
            confirm = confirm_label_purchase(web_driver, cheapest.get("price"))
            post_purchase = None
            if confirm.get("purchased"):
                try:
                    post_purchase = handle_post_purchase_and_download(
                        web_driver,
                        orders[0] if orders else {},
                        options.get("download", {})
                    )
                except Exception:
                    post_purchase = {"saved_path": None}
            tool_overlay = {"recipient": addr, "cheapest_price": cheapest.get("price"), "confirm": confirm, "post_purchase": post_purchase}
        except Exception:
            tool_overlay = {"recipient": {}, "cheapest_price": None, "confirm": {"purchased": False, "price": None}}

        msg = f"completed in fullfilling etsy new orders: {len(new_orders)} new orders came in, {len(fullfilled_orders)} orders processed."
        tool_result = TextContent(type="text", text=msg)
        tool_result.meta = {
            "new_orders": new_orders,
            "fullfilled_orders": fullfilled_orders,
            "summary": {"orders_count": orders_count, "messages_count": messages_count},
            "orders": orders,
            "overlay": tool_overlay,
        }
        return [tool_result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorFullfillEtsyOrders")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def fullfill_etsy_orders(mainwin, args):  # type: ignore
    return await fullfill_one_etsy_orders(mainwin, args)



def add_get_etsy_summary_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="get_etsy_summary",
        description="get etsy numer of new orders and number of new messages.",
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
                            "description": "etsy store url",
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

def add_etsy_fullfill_next_order_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="etsy_fullfill_next_order",
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
