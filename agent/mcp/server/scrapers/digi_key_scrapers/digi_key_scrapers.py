import re
import traceback
from selenium.webdriver.common.by import By
from utils.logger_helper import logger_helper as logger

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

