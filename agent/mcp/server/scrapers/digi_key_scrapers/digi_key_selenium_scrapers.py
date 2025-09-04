import re
import traceback
from selenium.webdriver.common.by import By
from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_agent_by_id, get_traceback
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException, ElementClickInterceptedException, ElementNotInteractableException, WebDriverException
from utils.logger_helper import get_agent_by_id, get_traceback

def extract_categories_page(web_driver):
    try:
        main_ul = web_driver.find_element(By.CSS_SELECTOR, "ul[data-testid='n-lvl-ul-0']")
        categories = extract_categories_dict(main_ul)
        return categories
    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorExtractCategoriesPage:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorExtractCategoriesPage: traceback information not available:" + str(e)
        logger.debug(f"{ex_stat}")
        return {}

def parse_items(items_text):
    # Extract numbers (remove commas), e.g. '145,686 Items' -> 145686
    match = re.search(r'([\d,]+)', items_text)
    if match:
        return int(match.group(1).replace(',', ''))
    return None

def get_category_info(a_tag):
    full_text = a_tag.text.strip()
    try:
        span = a_tag.find_element(By.TAG_NAME, "span")
        items_text = span.text.strip()
        name = full_text.replace(items_text, "").strip()
    except:
        items_text = ""
        name = full_text
    href = a_tag.get_attribute("href")
    items = parse_items(items_text)
    return name, href, items

def extract_categories_dict(ul_elem):
    cats = {}
    for li in ul_elem.find_elements(By.XPATH, "./li"):
        try:
            a_tag = li.find_element(By.TAG_NAME, "a")
        except:
            continue
        name, href, items = get_category_info(a_tag)
        # Check for nested sub-categories
        sub_ul = None
        try:
            sub_ul = li.find_element(By.XPATH, "./ul")
        except:
            pass

        if sub_ul:
            # Has nested subcategories: recurse
            cats[name] = extract_categories_dict(sub_ul)
            cats[name]['_self'] = {'href': href, 'items': items}
        else:
            # Leaf node
            cats[name] = {'href': href, 'items': items}
    return cats

def extract_common_options(web_driver):
    common_blocks = web_driver.find_elements(By.CSS_SELECTOR, "div.tss-css-19wjlyw-commonFilterContainer")
    common_options = {}
    for block in common_blocks:
        title = block.find_element(By.CSS_SELECTOR, ".tss-css-1pyh5um-title").text.strip()
        options = []
        labels = block.find_elements(By.CSS_SELECTOR, "label.MuiFormControlLabel-root")
        for label in labels:
            # Option visible text
            text = label.find_element(By.CSS_SELECTOR,
                                      "span[data-testid^='filter-'][data-testid$='-text-']").text.strip()
            # Get key/value/etc. from label attributes
            filter_key = label.get_attribute('data-filter-key')
            filter_value = label.get_attribute('data-filter-value')
            radio = label.get_attribute('data-radio')
            common = label.get_attribute('data-common')
            disabled = label.get_attribute('data-disabled')
            title_attr = label.get_attribute('title')
            option = {
                "label": text,
                "title": title_attr,
                "filter_key": filter_key,
                "filter_value": filter_value,
                "radio": radio == "true",
                "common": common == "true",
                "disabled": disabled == "true"
            }
            options.append(option)
        common_options[title] = options
    return common_options

def extract_apply_all_button(web_driver):
    try:
        apply_btn = web_driver.find_element(By.CSS_SELECTOR, 'button[data-testid="apply-all-button"]')
        apply_all = {
            "text": apply_btn.text.strip(),
            "enabled": apply_btn.is_enabled(),
            "class": apply_btn.get_attribute("class"),
        }
        return apply_btn
    except Exception as e:
        apply_all = None  # Button not found


def extract_search_parametric(web_driver):
    parametric = {}

    # Find all cards in the parametric filter section
    cards = web_driver.find_elements(By.CSS_SELECTOR, 'div.div-card')

    for card in cards:
        # Card title
        try:
            title = card.find_element(By.CSS_SELECTOR, '.tss-css-oy50zv-cardHeader').text.strip()
        except Exception:
            continue  # Skip if title not found

        card_info = {}

        # Check for min/max fields (range filter)
        min_inputs = card.find_elements(By.CSS_SELECTOR, 'input[data-filter-type="min"]')
        max_inputs = card.find_elements(By.CSS_SELECTOR, 'input[data-filter-type="max"]')
        select_units = card.find_elements(By.CSS_SELECTOR, 'select[data-filter-type="unit"]')

        if min_inputs or max_inputs:
            # This card has a min/max filter
            min_value = min_inputs[0].get_attribute("placeholder") if min_inputs else None
            max_value = max_inputs[0].get_attribute("placeholder") if max_inputs else None
            card_info["min_input_placeholder"] = min_value
            card_info["max_input_placeholder"] = max_value

            if select_units:
                options = [o.text for o in select_units[0].find_elements(By.TAG_NAME, "option")]
                card_info["unit_options"] = options
        else:
            # Otherwise, collect checkbox or radio options
            options = []
            for opt_span in card.find_elements(By.CSS_SELECTOR, '[class*="tss-css-1w97wf3-options"]'):
                opt_label = opt_span.text.strip()
                if opt_label:  # Only non-empty
                    options.append(opt_label)
            # For some cards, labels might be under <label> elements
            if not options:
                for label in card.find_elements(By.CSS_SELECTOR, 'label'):
                    opt = label.text.strip()
                    if opt: options.append(opt)
            card_info["options"] = options

        parametric[title] = card_info

    return parametric

# pip install selenium webdriver-manager pandas
# Optional: pip install pandas  (only if you want to also save xlsx)

import csv
import re
import time
from pathlib import Path
from typing import Dict, List, Tuple

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


START_URL = "https://www.digikey.com/en/products/filter/programmable-logic-ics/696"  # <-- put your results URL here
OUT_CSV = Path("digikey_results_dynamic_selenium.csv")
MAX_PAGES = 1         # set >1 to paginate
HEADLESS = True
PAGELOAD_TIMEOUT = 45
WAIT_TIMEOUT = 20

ROW_SELECTOR = ".SearchResults-productRow, .ProductResults .ProductRow, .SearchResults .ProductRow"

def _wait(driver, timeout: int = 30):
    return WebDriverWait(driver, timeout, poll_frequency=0.25, ignored_exceptions=(StaleElementReferenceException,))


def _visible(driver, css: str, timeout: int = 30):
    return _wait(driver, timeout).until(EC.visibility_of_element_located((By.CSS_SELECTOR, css)))


def _present(driver, css: str, timeout: int = 30):
    return _wait(driver, timeout).until(EC.presence_of_element_located((By.CSS_SELECTOR, css)))


def _visible_all(driver, css: str, timeout: int = 30):
    return _wait(driver, timeout).until(EC.visibility_of_all_elements_located((By.CSS_SELECTOR, css)))


def _safe_text(el) -> str:
    try:
        return el.text.strip()
    except Exception:
        return ""


def _js(driver, script: str, *args):
    return driver.execute_script(script, *args)


def selenium_accept_cookies(driver):
    # OneTrust common ID
    try:
        btn = driver.find_elements(By.CSS_SELECTOR, "#onetrust-accept-btn-handler")
        if btn:
            btn[0].click()
            print("✅ Accepted cookies (OneTrust)")
            time.sleep(0.2)
            return
    except Exception:
        pass
    # Generic accept button
    try:
        btns = driver.find_elements(By.XPATH, "//button[normalize-space()='Accept']")
        if btns:
            btns[0].click()
            print("✅ Accepted cookies (generic)")
            time.sleep(0.2)
    except Exception:
        pass


def selenium_wait_for_results_container(driver, timeout_ms: int = 60000):
    timeout = max(1, timeout_ms // 1000)
    selectors = [
        "#productSearchContainer, .SearchResults.ProductResults",
        ".SearchResults.ProductResults",
        ".SearchResults",
        ".ProductResults",
        ".SearchResults-productTable",
    ]

    # Strategy 1: try in current context
    for sel in selectors:
        try:
            el = _visible(driver, sel, timeout=3)
            if el:
                return el
        except Exception:
            pass

    # Strategy 2: probe iframes for the container
    try:
        frames = driver.find_elements(By.CSS_SELECTOR, "iframe, frame")
    except Exception:
        frames = []
    for fr in frames[:10]:
        try:
            driver.switch_to.frame(fr)
            for sel in selectors:
                try:
                    el = _visible(driver, sel, timeout=3)
                    if el:
                        print("[results_container] Found inside an iframe")
                        return el
                except Exception:
                    pass
            driver.switch_to.default_content()
        except Exception:
            try:
                driver.switch_to.default_content()
            except Exception:
                pass

    # Strategy 3: wait for any row to appear (some pages omit the wrapper selectors)
    try:
        _visible(driver, ROW_SELECTOR, timeout=timeout)
        # Return the body or closest container to keep API consistent
        try:
            return driver.find_element(By.TAG_NAME, "body")
        except Exception:
            return driver
    except Exception:
        # Final attempt with presence instead of visibility
        try:
            _present(driver, ROW_SELECTOR, timeout=timeout)
            return driver.find_element(By.TAG_NAME, "body")
        except Exception:
            # Propagate timeout with context
            raise TimeoutException("Results container and rows not found within timeout")


def clean_text(txt: str) -> str:
    return re.sub(r"\s+", " ", (txt or "").strip())


def preferred_key(raw_key: str) -> str:
    mapping = {
        "tr-product": "Product",
        "tr-qtyAvailable": "Qty Available",
        "tr-unitPrice": "Unit Price",
        "tr-tariff": "Tariff",
        "tr-series": "Series",
        "tr-packaging": "Packaging",
        "tr-productstatus": "Product Status",
    }
    return mapping.get(raw_key, raw_key)


def setup_driver() -> webdriver.Chrome:
    chrome_opts = Options()
    if HEADLESS:
        chrome_opts.add_argument("--headless=new")
    chrome_opts.add_argument("--window-size=1440,1000")
    chrome_opts.add_argument("--disable-gpu")
    chrome_opts.add_argument("--no-sandbox")
    chrome_opts.add_argument("--disable-dev-shm-usage")
    chrome_opts.add_argument("--disable-blink-features=AutomationControlled")
    # a realistic UA helps JS-heavy sites
    chrome_opts.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_opts)
    driver.set_page_load_timeout(PAGELOAD_TIMEOUT)
    return driver


def selenium_wait_for_page_load(driver):
    try:
        _wait(driver, 60).until(lambda d: d.execute_script("return document.readyState") == "complete")
    except TimeoutException:
        pass
    selenium_accept_cookies(driver)



def selenium_apply_parametric_filters(webdriver, pfs):
    try:
        selenium_wait_for_results_container(driver, timeout_ms=60000)
    except TimeoutException:
        print("⚠️ Results container not found yet; continuing")

    # Ensure filter blocks present/visible if possible
    try:
        _present(driver, ".FilterContainer-filter--native", timeout=60)
    except TimeoutException:
        try:
            _present(driver, ".FilterContainer-filter", timeout=60)
        except TimeoutException:
            print("⚠️ Filter blocks not found; proceeding anyway")

    # Apply filters incrementally
    print("ready to fill parametric filters")
    for pf in pfs:
        set_values = pf.get("setValues") or []
        if not set_values:
            continue
        filter_name = pf.get("name", "")
        css_name = pf.get("css_name")
        for val in set_values:
            try:
                vals = selenium_pick_parameter(driver, filter_name, css_name, [val])
                print(f"➡️ Selected values for {filter_name}: {vals}")
                selenium_apply_now(driver)
            except Exception as e:
                print(f"❌ Failed to set {filter_name} to {val}: {e}")



def selenium_extract_search_results(webdriver):
    search_results = []



    return search_results

def click_if_exists(driver, by, selector, timeout=2):
    try:
        el = WebDriverWait(driver, timeout).until(EC.presence_of_element_located((by, selector)))
        el.click()
        return True
    except Exception:
        return False


def try_dismiss_banners(driver):
    # try a handful of common consent/close buttons
    candidates = [
        (By.XPATH, "//button[normalize-space()='Accept']"),
        (By.XPATH, "//button[contains(.,'I Accept')]"),
        (By.XPATH, "//button[contains(.,'AGREE')]"),
        (By.CSS_SELECTOR, "button[aria-label='Close']"),
    ]
    for by, sel in candidates:
        try:
            btns = driver.find_elements(by, sel)
            if btns:
                btns[0].click()
                time.sleep(0.4)
        except Exception:
            pass


def extract_links_from_td(td) -> Dict[str, str]:
    out = {}
    # MPN + Product URL
    try:
        mpn_a = td.find_element(By.CSS_SELECTOR, "[data-testid='data-table-product-number']")
        out["MPN"] = clean_text(mpn_a.text)
        href = mpn_a.get_attribute("href")
        if href:
            out["Product URL"] = href if href.startswith("http") else f"https://www.digikey.com{href}"
    except Exception:
        pass

    # Manufacturer + URL
    try:
        mfr_a = td.find_element(By.CSS_SELECTOR, "[data-testid='data-table-mfr-link']")
        out["Manufacturer"] = clean_text(mfr_a.text)
        href = mfr_a.get_attribute("href")
        if href:
            out["Manufacturer URL"] = href if href.startswith("http") else f"https://www.digikey.com{href}"
    except Exception:
        pass

    # Datasheet URL (PDF icon link)
    try:
        ds_a = td.find_element(By.CSS_SELECTOR, "a:has(svg[data-testid='icon-alt-pdf'])")
        href = ds_a.get_attribute("href")
        if href:
            out["Datasheet URL"] = href
    except Exception:
        # older Chromes don't support :has; try a fallback
        try:
            ds_svg = td.find_elements(By.CSS_SELECTOR, "svg[data-testid='icon-alt-pdf']")
            if ds_svg:
                parent_link = ds_svg[0].find_element(By.XPATH, "./ancestor::a[1]")
                href = parent_link.get_attribute("href")
                if href:
                    out["Datasheet URL"] = href
        except Exception:
            pass

    # Image URL
    try:
        img = td.find_element(By.CSS_SELECTOR, "img[data-testid='data-table-product-image']")
        src = img.get_attribute("src")
        if src:
            out["Image URL"] = src if src.startswith("http") else f"https:{src}"
    except Exception:
        pass

    return out


def parse_rows_on_page(driver) -> Tuple[List[Dict[str, str]], List[str]]:
    rows_out: List[Dict[str, str]] = []
    dynamic_keys_in_order: List[str] = []

    # wait for row presence
    try:
        WebDriverWait(driver, WAIT_TIMEOUT).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "tr[class*='muwdap-tr'], tbody tr"))
        )
    except Exception:
        return rows_out, dynamic_keys_in_order

    # prefer specific class; fallback to generic
    rows = driver.find_elements(By.CSS_SELECTOR, "tr[class*='muwdap-tr']")
    if not rows:
        rows = driver.find_elements(By.CSS_SELECTOR, "tbody tr")

    for tr in rows:
        tds = tr.find_elements(By.CSS_SELECTOR, "td")
        row: Dict[str, str] = {}

        for j, td in enumerate(tds):
            # find a child carrying data-atag
            key_raw = None
            try:
                atag_node = td.find_element(By.CSS_SELECTOR, "[data-atag]")
                key_raw = atag_node.get_attribute("data-atag")
            except Exception:
                pass

            key = preferred_key(key_raw) if key_raw else f"col{j}"
            if key not in dynamic_keys_in_order:
                dynamic_keys_in_order.append(key)

            # cell text
            val = clean_text(td.text)
            if val:
                row[key] = val

            # links (only set if not already present)
            try:
                links = extract_links_from_td(td)
                for k, v in links.items():
                    row.setdefault(k, v)
            except Exception:
                pass

        if any(v for v in row.values()):
            rows_out.append(row)

    return rows_out, dynamic_keys_in_order


def compute_header_order(all_rows: List[Dict[str, str]], dynamic_order: List[str]) -> List[str]:
    special = ["MPN", "Product URL", "Manufacturer", "Manufacturer URL", "Datasheet URL", "Image URL"]
    dyn = [k for k in dynamic_order if k not in special]
    leftovers = []
    seen = set(special) | set(dyn)
    for r in all_rows:
        for k in r.keys():
            if k not in seen:
                leftovers.append(k)
                seen.add(k)
    return special + dyn + leftovers


def write_csv(rows: List[Dict[str, str]], header_order: List[str], out_path: Path):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=header_order, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def jiggle_scroll(driver):
    # assist lazy content to mount
    driver.execute_script("window.scrollTo(0, 1200);")
    time.sleep(0.3)
    driver.execute_script("window.scrollTo(0, 300);")
    time.sleep(0.2)


def click_next_if_present(driver) -> bool:
    # Several possible selectors
    candidates = [
        (By.CSS_SELECTOR, "button[aria-label='Next']"),
        (By.CSS_SELECTOR, "a[aria-label='Next']"),
        (By.XPATH, "//button[.//text()[contains(.,'Next')]]"),
        (By.XPATH, "//a[.//text()[contains(.,'Next')]]"),
    ]
    for by, sel in candidates:
        try:
            ele = WebDriverWait(driver, 2).until(EC.element_to_be_clickable((by, sel)))
            ele.click()
            # wait for new content
            WebDriverWait(driver, WAIT_TIMEOUT).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "tr[class*='muwdap-tr'], tbody tr"))
            )
            time.sleep(0.5)
            return True
        except Exception:
            pass
    return False


def extract_search_results_table(driver):
    try:
        driver.get(START_URL)
        try_dismiss_banners(driver)

        all_rows: List[Dict[str, str]] = []
        dynamic_key_order: List[str] = []

        for page_idx in range(MAX_PAGES):
            jiggle_scroll(driver)
            rows, dyn_keys = parse_rows_on_page(driver)
            all_rows.extend(rows)
            for k in dyn_keys:
                if k not in dynamic_key_order:
                    dynamic_key_order.append(k)

            if page_idx + 1 >= MAX_PAGES:
                break
            if not click_next_if_present(driver):
                break

        if not all_rows:
            print("No rows found. Is this a results grid URL?")
            return

        header_order = compute_header_order(all_rows, dynamic_key_order)
        write_csv(all_rows, header_order, OUT_CSV)
        print(f"Wrote {len(all_rows)} rows to {OUT_CSV.resolve()} with {len(header_order)} columns.")

    finally:
        driver.quit()


def digi_key_selenium_search_component(driver, pfs, site_url):
    try:
        selenium_wait_for_page_load(driver)

        selenium_apply_parametric_filters(webdriver, pfs)

        selenium_wait_for_results_container(driver)

        results = selenium_extract_search_results(webdriver)

    except Exception as e:
        err_msg = get_traceback(e, "ErrorDigikeySeleniumSearchComponent")
        results = []

    return results




if __name__ == "__main__":
    driver = setup_driver()
    extract_search_results_table(driver)

