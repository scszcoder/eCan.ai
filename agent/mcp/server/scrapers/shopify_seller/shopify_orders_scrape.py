from datetime import datetime
import base64
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback
from mcp.types import CallToolResult, TextContent




def scrape_shopify_summaries(web_driver):
    try:
        logger.debug("scrape_shopify_summaries started....")
        wait = WebDriverWait(web_driver, 15)
        try:
            wait.until(EC.presence_of_element_located((By.XPATH, "//h1[normalize-space()='Orders']")))
        except TimeoutException:
            pass

        summaries = {
            "orders": None,
            "items_ordered": None,
            "returns": None,
            "orders_fulfilled": None,
            "orders_delivered": None,
        }

        def _parse_number(txt):
            if not txt:
                return None
            t = txt.strip()
            t = t.replace("$", "").replace(",", "")
            try:
                if "." in t:
                    return float(t)
                return int(t)
            except Exception:
                try:
                    return float(t)
                except Exception:
                    return None

        cards = web_driver.find_elements(By.CSS_SELECTOR, "a[data-testid='compact-metric-card-button']")
        for card in cards:
            try:
                title_el = card.find_element(By.CSS_SELECTOR, "h2")
                title = title_el.get_attribute("textContent").strip().lower()
            except Exception:
                continue
            try:
                value_el = card.find_element(By.CSS_SELECTOR, ".Analytics-UI-Components-PrimaryMetric__PrimaryMetricWrapper p")
                value_text = value_el.get_attribute("textContent").strip()
            except Exception:
                value_text = None
            val = _parse_number(value_text)

            if "orders delivered" in title:
                summaries["orders_delivered"] = val
            elif "orders fulfilled" in title:
                summaries["orders_fulfilled"] = val
            elif title == "returns":
                summaries["returns"] = val
            elif title == "items ordered":
                summaries["items_ordered"] = val
            elif title == "orders":
                summaries["orders"] = val

        return summaries
    except Exception as e:
        err_trace = get_traceback(e, "ErrorScrapeShopifySummaries")
        logger.debug(err_trace)
        return {
            "orders": None,
            "items_ordered": None,
            "returns": None,
            "orders_fulfilled": None,
            "orders_delivered": None,
        }


def open_first_order_details(web_driver):
    try:
        wait = WebDriverWait(web_driver, 20)
        try:
            wait.until(EC.presence_of_element_located((By.XPATH, "//h1[normalize-space()='Orders']")))
        except TimeoutException:
            pass

        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "[role='table']")))
        rows = web_driver.find_elements(By.CSS_SELECTOR, "[role='table'] [role='row']")
        for row in rows:
            try:
                link = row.find_element(By.CSS_SELECTOR, "a[href*='/orders/']")
                txt = link.get_attribute("textContent").strip()
                link.click()
                return {"clicked": True, "order_id": txt}
            except Exception:
                continue
        return {"clicked": False, "order_id": None}
    except Exception as e:
        err_trace = get_traceback(e, "ErrorOpenFirstOrderDetails")
        logger.debug(err_trace)
        return {"clicked": False, "order_id": None}


def open_buy_shipping_label_flow(web_driver):
    try:
        wait = WebDriverWait(web_driver, 20)
        wait.until(EC.presence_of_element_located((By.XPATH, "//h1[contains(normalize-space(), '#') or contains(normalize-space(), 'Order')]")))

        clicked = False
        buttons = []
        try:
            buttons = web_driver.find_elements(By.CSS_SELECTOR, "button[id^='PURCHASE_LABEL-']")
        except Exception:
            buttons = []
        if not buttons:
            try:
                buttons = web_driver.find_elements(By.XPATH, "//button[normalize-space()='Buy shipping label']")
            except Exception:
                buttons = []
        if not buttons:
            try:
                buttons = web_driver.find_elements(By.XPATH, "//button[contains(normalize-space(), 'Create shipping label')]")
            except Exception:
                buttons = []
        if not buttons:
            try:
                buttons = web_driver.find_elements(By.CSS_SELECTOR, "button[data-testid='BuyShippingLabelButton']")
            except Exception:
                buttons = []

        for b in buttons:
            try:
                if b.is_enabled():
                    b.click()
                    clicked = True
                    break
            except Exception:
                continue

        if not clicked:
            return {"opened": False}

        try:
            wait.until(EC.presence_of_element_located((By.XPATH, "//*[contains(normalize-space(), 'Shipping label') or contains(normalize-space(), 'Packages') or contains(normalize-space(), 'Package')]")))
        except TimeoutException:
            pass

        return {"opened": True}
    except Exception as e:
        err_trace = get_traceback(e, "ErrorOpenBuyShippingLabelFlow")
        logger.debug(err_trace)
        return {"opened": False}


def scrape_shopify_order_details(web_driver):
    try:
        wait = WebDriverWait(web_driver, 20)
        try:
            wait.until(EC.presence_of_element_located((By.XPATH, "//h1[starts-with(normalize-space(), '#')]")))
        except TimeoutException:
            pass

        def _gettext(el):
            try:
                return el.get_attribute("textContent").strip()
            except Exception:
                return None

        data = {
            "order_id": None,
            "financial_status": None,
            "fulfillment_status": None,
            "delivery_method": None,
            "email": None,
            "shipping_address_text": None,
            "phone": None,
            "line_items": [],
            "subtotal": None,
            "shipping_line": None,
            "shipping_price": None,
            "total": None,
        }

        try:
            h1 = web_driver.find_element(By.XPATH, "//h1[starts-with(normalize-space(), '#')]")
            data["order_id"] = _gettext(h1)
        except Exception:
            pass

        try:
            badge_paid = web_driver.find_elements(By.XPATH, "//*[normalize-space()='Paid']")
            if badge_paid:
                data["financial_status"] = "Paid"
        except Exception:
            pass

        try:
            badge_unfulfilled = web_driver.find_elements(By.XPATH, "//*[normalize-space()='Unfulfilled']")
            if badge_unfulfilled:
                data["fulfillment_status"] = "Unfulfilled"
        except Exception:
            pass

        try:
            dm = web_driver.find_elements(By.CSS_SELECTOR, "[id^='deliveryMethodDescriptor-'] span")
            for el in dm:
                t = _gettext(el)
                if t:
                    data["delivery_method"] = t
                    break
        except Exception:
            pass

        try:
            email_el = web_driver.find_elements(By.XPATH, "//button[contains(@class,'Polaris-Link')][contains(., '@')] | //a[contains(@href,'mailto')]")
            if email_el:
                data["email"] = _gettext(email_el[0])
        except Exception:
            pass

        try:
            ship_block = web_driver.find_elements(By.XPATH, "//h3[normalize-space()='Shipping address']/ancestor::div[1]/following::div[contains(@class,'Polaris-BlockStack')][1]//p")
            if ship_block:
                ship_text = _gettext(ship_block[0])
                data["shipping_address_text"] = ship_text
                if ship_text and "+" in ship_text:
                    parts = ship_text.split("\n")
                    for part in parts[::-1]:
                        pt = part.strip()
                        if pt.startswith("+") or pt.replace(" ", "").isdigit():
                            data["phone"] = pt
                            break
        except Exception:
            pass

        try:
            items = []
            rows = web_driver.find_elements(By.XPATH, "//a[contains(@href,'/products/')]/ancestor::*[contains(@class,'_MainRow')][1]")
            seen = set()
            for r in rows:
                try:
                    title_a = r.find_element(By.XPATH, ".//a[contains(@href,'/products/')]")
                    title = _gettext(title_a)
                except Exception:
                    title = None
                try:
                    qty_el = r.find_element(By.XPATH, ".//span[contains(@class,'Polaris-Tag')]//span[contains(@class,'Polaris-Text--root')]")
                    qty = _gettext(qty_el)
                except Exception:
                    qty = None
                try:
                    price_el = r.find_element(By.XPATH, ".//span[contains(@class,'Polaris-Text--numeric')][starts-with(normalize-space(),'$')]")
                    price = _gettext(price_el)
                except Exception:
                    price = None
                key = (title, price, qty)
                if title and key not in seen:
                    items.append({"title": title, "price": price, "quantity": qty})
                    seen.add(key)
            data["line_items"] = items
        except Exception:
            pass

        try:
            sub_el = web_driver.find_elements(By.XPATH, "//span[normalize-space()='Subtotal']/ancestor::div[1]/following::div[1]//span[contains(@class,'Polaris-Text--numeric')]")
            if sub_el:
                data["subtotal"] = _gettext(sub_el[-1])
        except Exception:
            pass

        try:
            ship_label = web_driver.find_elements(By.XPATH, "//span[normalize-space()='Shipping']/ancestor::div[1]/following::div[1]//*[contains(@class,'Polaris-Text--numeric')]")
            if ship_label:
                data["shipping_line"] = "Shipping"
                data["shipping_price"] = _gettext(ship_label[-1])
        except Exception:
            pass

        try:
            total_el = web_driver.find_elements(By.XPATH, "//span[normalize-space()='Total']/ancestor::div[1]/following::div[1]//span[contains(@class,'Polaris-Text--numeric')]")
            if total_el:
                data["total"] = _gettext(total_el[-1])
        except Exception:
            pass

        return data
    except Exception as e:
        err_trace = get_traceback(e, "ErrorScrapeShopifyOrderDetails")
        logger.debug(err_trace)
        return {}


def select_cheapest_rate_and_purchase(web_driver, price_tolerance=0.05):
    try:
        wait = WebDriverWait(web_driver, 20)
        try:
            wait.until(EC.presence_of_element_located((By.XPATH, "//*[contains(normalize-space(), 'Shipping label') or contains(normalize-space(), 'Packages') or contains(normalize-space(), 'Package')]")))
        except TimeoutException:
            pass

        candidates = []
        rate_containers = web_driver.find_elements(By.XPATH, "//*[self::label or self::button or self::div][.//span[contains(@class,'Polaris-Text--numeric')] and (.//*[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'ups') or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'usps') or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'fedex') or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'dhl')])]" )
        if not rate_containers:
            rate_containers = web_driver.find_elements(By.XPATH, "//label[.//*[starts-with(normalize-space(),'$') or contains(@class,'Polaris-Text--numeric')]]")

        def _parse_price(s):
            if not s:
                return None
            t = s.strip().replace('$','').replace(',','').split()[0]
            try:
                return float(t)
            except Exception:
                return None

        for rc in rate_containers:
            try:
                text = rc.get_attribute("textContent") or ""
                price_els = rc.find_elements(By.XPATH, ".//span[contains(@class,'Polaris-Text--numeric')][starts-with(normalize-space(),'$')] | .//*[starts-with(normalize-space(),'$')]")
                price_txt = price_els[0].get_attribute("textContent").strip() if price_els else None
                price = _parse_price(price_txt)
                if price is not None:
                    candidates.append((price, rc))
            except Exception:
                continue

        selected = None
        if candidates:
            candidates.sort(key=lambda x: x[0])
            cheapest = candidates[0]
            try:
                try:
                    input_el = cheapest[1].find_element(By.XPATH, ".//input[@type='radio' or @type='checkbox']")
                    web_driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", input_el)
                    input_el.click()
                except Exception:
                    web_driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", cheapest[1])
                    cheapest[1].click()
                selected = {"price": cheapest[0]}
            except Exception:
                selected = None

        buy_btn = None
        try:
            buy_btn = web_driver.find_element(By.XPATH, "//button[normalize-space()='Buy shipping label']")
        except Exception:
            try:
                buy_btn = web_driver.find_element(By.XPATH, "//button[contains(normalize-space(),'Create shipping label')]")
            except Exception:
                try:
                    buy_btn = web_driver.find_element(By.CSS_SELECTOR, "button[data-testid='BuyShippingLabelButton']")
                except Exception:
                    buy_btn = None
        if buy_btn:
            web_driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", buy_btn)
            buy_btn.click()

        try:
            wait.until(EC.presence_of_element_located((By.XPATH, "//h1[contains(normalize-space(),'label purchased') or contains(normalize-space(),'labels purchased')] | //h1[normalize-space()='1 label purchased']")))
        except TimeoutException:
            pass

        return {"selected": selected is not None, "selected_price": selected.get("price") if selected else None}
    except Exception as e:
        err_trace = get_traceback(e, "ErrorSelectCheapestRateAndPurchase")
        logger.debug(err_trace)
        return {"selected": False, "selected_price": None}


def click_print_shipping_label_on_purchased_page(web_driver):
    try:
        wait = WebDriverWait(web_driver, 20)
        try:
            wait.until(EC.presence_of_element_located((By.XPATH, "//h1[contains(normalize-space(),'label purchased')] | //h1[normalize-space()='1 label purchased']")))
        except TimeoutException:
            pass

        print_btn = None
        try:
            print_btn = web_driver.find_element(By.XPATH, "//button[normalize-space()='Print shipping label']")
        except Exception:
            try:
                print_btn = web_driver.find_element(By.XPATH, "//button[starts-with(normalize-space(), 'Print ') and contains(normalize-space(), 'shipping label')]")
            except Exception:
                print_btn = None
        if print_btn:
            web_driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", print_btn)
            print_btn.click()
            return {"clicked": True}
        return {"clicked": False}
    except Exception as e:
        err_trace = get_traceback(e, "ErrorClickPrintOnPurchasedPage")
        logger.debug(err_trace)
        return {"clicked": False}

async def fullfill_shopify_orders(mainwin, args):  # type: ignore
    try:
        logger.debug("fullfill_shopify_orders started....")
        new_orders = []
        fullfilled_orders = []
        options = args["input"]["options"]
        web_driver = mainwin.getWebDriver()
        summaries = scrape_shopify_summaries(web_driver)
        nav = open_first_order_details(web_driver)
        order_info = scrape_shopify_order_details(web_driver) if nav.get("clicked") else {}
        opened = open_buy_shipping_label_flow(web_driver) if nav.get("clicked") else {"opened": False}
        purchased = select_cheapest_rate_and_purchase(web_driver) if opened.get("opened") else {"selected": False}
        printed = click_print_shipping_label_on_purchased_page(web_driver) if purchased.get("selected") else {"clicked": False}

        msg = f"completed scraping shopify orders summary."
        tool_result = TextContent(type="text", text=msg)
        tool_result.meta = {"new_orders": new_orders, "fullfilled_orders": fullfilled_orders, "summary": summaries, "nav_first_order": nav, "order": order_info, "open_label_flow": opened, "purchased": purchased, "printed": printed}
        return [tool_result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorFullfillEtsyOrders")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]