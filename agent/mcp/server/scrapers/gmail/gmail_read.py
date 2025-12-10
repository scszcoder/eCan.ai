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
GMAIL_PLACEHOLDER_MODE = True


# {
#     "n_new_orders": integer,
#     "n_pages": integer,
#     "orders_per_page": integer,
# }


def scrape_gmail_titles(driver, gmail_url: str, recent_hours: int = 72) -> dict:
    """
    Scrape unread Gmail titles from the inbox within the specified time window.
    
    Args:
        driver: Selenium WebDriver instance
        gmail_url: Gmail inbox URL
        recent_hours: Number of hours to look back for emails (default 72)
    
    Returns:
        dict: {"emails_per_page": int, "titles": [{"from": str, "datetime": str, "title": str}, ...]}
    """
    from datetime import datetime, timedelta
    import time
    
    result = {
        "emails_per_page": 0,
        "titles": []
    }
    
    try:
        # Navigate to Gmail inbox
        driver.get(gmail_url)
        
        # Wait for the email list to load
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "tr.zA"))
        )
        time.sleep(2)  # Allow dynamic content to fully render
        
        # Get emails per page from pagination info
        # Format: "1-50 of 25,587" - the spans with class "ts" contain: [1, 50, 25587]
        try:
            pagination_spans = driver.find_elements(By.CSS_SELECTOR, "div.ar5 span.ts")
            if len(pagination_spans) >= 2:
                # First span is start (1), second is end (50)
                result["emails_per_page"] = int(pagination_spans[1].text.replace(",", ""))
        except Exception as e:
            logger.debug(f"[GMAIL] Could not extract emails_per_page: {e}")
            result["emails_per_page"] = 50  # Default
        
        # Calculate cutoff time
        cutoff_time = datetime.now() - timedelta(hours=recent_hours)
        
        # Find all unread email rows (class "zA zE" where zE indicates unread)
        unread_rows = driver.find_elements(By.CSS_SELECTOR, "tr.zA.zE")
        logger.debug(f"[GMAIL] Found {len(unread_rows)} unread emails on current page")
        
        for row in unread_rows:
            try:
                email_data = _extract_email_data(row, cutoff_time)
                logger.debug(f"[GMAIL] Extracted email data: {email_data}")
                if email_data:
                    result["titles"].append(email_data)
            except Exception as e:
                logger.debug(f"[GMAIL] Error extracting email row: {e}")
                continue
        
        logger.debug(f"[GMAIL] Extracted {len(result['titles'])} emails within {recent_hours} hours")
        
    except TimeoutException:
        logger.error("[GMAIL] Timeout waiting for Gmail inbox to load")
    except Exception as e:
        logger.error(f"[GMAIL] Error scraping Gmail: {get_traceback(e, 'ErrorScrapeGmail')}")
    
    return result


def _extract_email_data(row, cutoff_time):
    """
    Extract full email data from a single row element including clickable elements.
    
    Args:
        row: Selenium WebElement for the email row
        cutoff_time: datetime cutoff - emails older than this are skipped
    
    Returns:
        dict with from, datetime, title (for return) plus full_data with all extracted info,
        or None if email is too old or already read
    """
    from datetime import datetime as dt
    
    # ===== UNREAD CHECK =====
    # Verify the row still has the unread class (zE)
    row_classes = row.get_attribute("class") or ""
    is_unread = "zE" in row_classes
    if not is_unread:
        logger.debug(f"[GMAIL] Skipping read email (no zE class): {row_classes}")
        return None
    
    # ===== DATETIME EXTRACTION =====
    datetime_str = ""
    email_datetime = None
    try:
        time_span = row.find_element(By.CSS_SELECTOR, "td.xW span[title]")
        datetime_str = time_span.get_attribute("title")
        
        # Parse the datetime string (e.g., "Fri, Dec 5, 2025, 9:17 PM")
        if datetime_str:
            try:
                email_datetime = dt.strptime(datetime_str, "%a, %b %d, %Y, %I:%M %p")
            except ValueError:
                try:
                    email_datetime = dt.strptime(datetime_str, "%a, %b %d, %Y %I:%M %p")
                except ValueError:
                    pass
    except Exception:
        try:
            time_text = row.find_element(By.CSS_SELECTOR, "td.xW span.bq3, td.xW span").text
            datetime_str = time_text
        except Exception:
            pass
    
    # Check if email is within the time window
    if email_datetime and email_datetime < cutoff_time:
        return None
    
    # ===== CHECKBOX ELEMENT (for selecting email) =====
    checkbox_elem = None
    try:
        # The checkbox is in a td with role="gridcell" containing a div with role="checkbox"
        checkbox_elem = row.find_element(By.CSS_SELECTOR, "td.oZ-x3 div[role='checkbox'], div.oZ-jc[role='checkbox']")
    except Exception:
        try:
            # Fallback: first clickable checkbox-like element
            checkbox_elem = row.find_element(By.CSS_SELECTOR, "td:first-child div[aria-checked]")
        except Exception:
            pass
    
    # ===== SENDER EXTRACTION =====
    sender = ""
    sender_email = ""
    try:
        # Primary: span.zF has both name and email attributes
        sender_elem = row.find_element(By.CSS_SELECTOR, "span.zF")
        sender = sender_elem.get_attribute("name") or sender_elem.text or ""
        sender_email = sender_elem.get_attribute("email") or ""
    except Exception:
        try:
            # Fallback: span.yP
            sender_elem = row.find_element(By.CSS_SELECTOR, "span.yP")
            sender = sender_elem.get_attribute("name") or sender_elem.text or ""
            sender_email = sender_elem.get_attribute("email") or ""
        except Exception:
            try:
                # Last fallback: div.yW span
                sender_div = row.find_element(By.CSS_SELECTOR, "div.yW span")
                sender = sender_div.get_attribute("name") or sender_div.text or ""
                sender_email = sender_div.get_attribute("email") or ""
            except Exception:
                pass
    
    # ===== TITLE/SUBJECT EXTRACTION + CLICKABLE ELEMENT =====
    title = ""
    title_clickable_elem = None
    try:
        # Primary: span.bqe contains the subject text (inside div.y6 > span.bog > span.bqe)
        title_elem = row.find_element(By.CSS_SELECTOR, "div.y6 span.bqe")
        title = title_elem.text or ""
        title_clickable_elem = title_elem
    except Exception:
        try:
            # Fallback: just span.bqe anywhere in the row
            title_elem = row.find_element(By.CSS_SELECTOR, "span.bqe")
            title = title_elem.text or ""
            title_clickable_elem = title_elem
        except Exception:
            try:
                # Last fallback: span.bog span
                title_elem = row.find_element(By.CSS_SELECTOR, "span.bog span")
                title = title_elem.text or ""
                title_clickable_elem = title_elem
            except Exception:
                try:
                    # Final fallback: div.y6 first span
                    title_elem = row.find_element(By.CSS_SELECTOR, "div.y6 span")
                    title = title_elem.text or ""
                    title_clickable_elem = title_elem
                except Exception:
                    pass
    
    # If no specific title element, the row itself is clickable
    if title_clickable_elem is None:
        title_clickable_elem = row
    
    title = title.strip()
    logger.debug(f"[GMAIL] Extracted title: '{title}', sender: '{sender}', email: '{sender_email}'")
    # ===== EMAIL SNIPPET/PREVIEW =====
    snippet = ""
    try:
        # The snippet is in span.y2 after the subject
        snippet_elem = row.find_element(By.CSS_SELECTOR, "span.y2")
        snippet = snippet_elem.text
        # Remove leading dash/separator if present
        snippet = snippet.lstrip(" -–—").strip()
    except Exception:
        pass

    # ===== ATTACHMENT INDICATOR =====
    has_attachment = False
    attachment_elem = None
    try:
        # Attachment icon is typically in a span with specific class or aria-label
        attachment_elem = row.find_element(By.CSS_SELECTOR, "span.brd, div.brg, span[aria-label*='attachment'], img[alt*='Attachment']")
        has_attachment = True
    except Exception:
        pass
    
    # ===== STAR/IMPORTANT INDICATOR =====
    is_starred = False
    star_elem = None
    try:
        star_elem = row.find_element(By.CSS_SELECTOR, "td.apU span[aria-label], span.T-KT")
        is_starred = "starred" in (star_elem.get_attribute("aria-label") or "").lower()
    except Exception:
        pass
    
    # ===== ROW ELEMENT (for clicking to open email) =====
    row_clickable_elem = row
    
    # ===== BUILD FULL DATA (internal use) =====
    full_data = {
        "from": sender,
        "from_email": sender_email,
        "datetime": datetime_str,
        "datetime_parsed": email_datetime,
        "title": title,
        "snippet": snippet,
        "has_attachment": has_attachment,
        "is_starred": is_starred,
        # Clickable elements (WebElements for interaction)
        "elements": {
            "checkbox": checkbox_elem,
            "title_clickable": title_clickable_elem,
            "row": row_clickable_elem,
            "star": star_elem,
            "attachment": attachment_elem,
        }
    }
    
    # Log full data for debugging
    logger.debug(f"[GMAIL] Extracted email: from={sender}, title={title[:50] if len(title) > 50 else title}..., has_attachment={has_attachment}")
    
    # Return only the title-related fields as per original spec
    # Full data is available via "_full_data" key for internal use
    return {
        "from": sender,
        "from_email": sender_email,
        "datetime": datetime_str,
        "title": title,
        "_full_data": full_data  # Contains all extracted info including WebElements
    }


async def gmail_read_titles(mainwin, args):
    try:
        gmail_titles = []
        if args["input"]:
            logger.debug(f"[MCP][GMAIL READ TITLES]: {args['input']}")
            gmail_url = args["input"].get("gmail_url", "")
            recent = args["input"].get("recent", 72)          # number of hours.
            if not gmail_url:
                gmail_url = "https://mail.google.com/mail/u/0/#inbox"
            options = args["input"].get("options", {})
            web_driver = mainwin.getWebDriver()
            if not web_driver:
                # Use the first site's URL to initialize/connect the driver
                web_driver = connect_to_adspower(mainwin, gmail_url)
                logger.debug(f"[MCP][GMAIL READ TITLES]:WebDriver acquired via adspower: {type(web_driver)}")
            
            if web_driver:
                gmail_titles = scrape_gmail_titles(web_driver, gmail_url, recent)
                # Strip non-serializable WebElement objects from response
                if isinstance(gmail_titles, dict) and "titles" in gmail_titles:
                    for title_item in gmail_titles.get("titles", []):
                        if "_full_data" in title_item:
                            del title_item["_full_data"]
                msg = "completed getting gmail titles"
            else:
                logger.error("[MCP][GMAIL READ TITLES]:WebDriver not available")
                msg = "Error: web driver not available."
        else:
            msg = "ERROR: no input provided."
            logger.error(f"[MCP][GMAIL READ TITLES]:{msg}")

        result = TextContent(type="text", text=msg)
        result.meta = {"gmail_titles": gmail_titles}
        logger.debug(f"[MCP][GMAIL READ TITLES]:gmail_titles: {gmail_titles}")
        return [result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorGmailReadTitles")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]



async def gmail_read_full_email(mainwin, args):
    try:
        ebay_summary = {}
        if args["input"]:
            logger.debug(f"[MCP][GMAIL READ FULL EMAIL]: {args['input']}")
            gmail_url = args["input"].get("gmail_url", "")
            recent = args["input"].get("recent", 72)          # number of hours.
            if not gmail_url:
                gmail_url = "https://mail.google.com/mail/u/0/#inbox"
            options = args["input"].get("options", {})
            web_driver = mainwin.getWebDriver()
            if not web_driver:
                # Use the first site's URL to initialize/connect the driver
                web_driver = connect_to_adspower(mainwin, gmail_url)
                logger.debug(f"[MCP][GMAIL READ FULL EMAIL]:WebDriver acquired for ebay work: {type(web_driver)}")
                gmail_titles = scrape_gmail_titles(web_driver, gmail_url, recent)
                msg = "completed getting ebay shop summary"
            else:
                logger.error(f"[MCP][GMAIL READ FULL EMAIL]:WebDriver acquired for ebay work: {type(web_driver)}")
                msg = "Error: web driver not available."
        else:
            msg = "ERROR: no input provided."
            logger.error(f"[MCP][GMAIL READ FULL EMAIL]:{msg}")

        result = TextContent(type="text", text=msg)
        result.meta = {"gmail_titles": gmail_titles}
        logger.debug("[MCP][GMAIL READ FULL EMAIL]:gmail_titles:", gmail_titles)
        return [result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorGmailReadFullEmail")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def gmail_write_new(mainwin, args):  # type: ignore
    try:
        ebay_summary = {}
        if args["input"]:
            logger.debug(f"[MCP][GMAIL WRITE NEW]: {args['input']}")
            gmail_url = args["input"].get("gmail_url", "")
            recent = args["input"].get("recent", 72)  # number of hours.
            if not gmail_url:
                gmail_url = "https://mail.google.com/mail/u/0/#inbox"
            options = args["input"].get("options", {})
            web_driver = mainwin.getWebDriver()
            if not web_driver:
                # Use the first site's URL to initialize/connect the driver
                web_driver = connect_to_adspower(mainwin, gmail_url)
                logger.debug(f"[MCP][GMAIL WRITE NEW]:WebDriver acquired for ebay work: {type(web_driver)}")
                gmail_titles = scrape_gmail_titles(web_driver, gmail_url, recent)
                msg = "completed getting ebay shop summary"
            else:
                logger.error(f"[MCP][GMAIL WRITE NEW]:WebDriver acquired for ebay work: {type(web_driver)}")
                msg = "Error: web driver not available."
        else:
            msg = "ERROR: no input provided."
            logger.error(f"[MCP][GMAIL WRITE NEW]:{msg}")

        result = TextContent(type="text", text=msg)
        result.meta = {"gmail_titles": gmail_titles}
        logger.debug("[MCP][GMAIL WRITE NEW]:gmail_titles:", gmail_titles)
        return [result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorGmailWriteNew")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def gmail_delete_email(mainwin, args):  # type: ignore
    try:
        ebay_summary = {}
        if args["input"]:
            logger.debug(f"[MCP][GMAIL DELETE EMAIL]: {args['input']}")
            gmail_url = args["input"].get("gmail_url", "")
            recent = args["input"].get("recent", 72)  # number of hours.
            if not gmail_url:
                gmail_url = "https://mail.google.com/mail/u/0/#inbox"
            options = args["input"].get("options", {})
            web_driver = mainwin.getWebDriver()
            if not web_driver:
                # Use the first site's URL to initialize/connect the driver
                web_driver = connect_to_adspower(mainwin, gmail_url)
                logger.debug(f"[MCP][GMAIL DELETE EMAIL]:WebDriver acquired for ebay work: {type(web_driver)}")
                gmail_titles = scrape_gmail_titles(web_driver, gmail_url, recent)
                msg = "completed getting ebay shop summary"
            else:
                logger.error(f"[MCP][GMAIL DELETE EMAIL]:WebDriver acquired for ebay work: {type(web_driver)}")
                msg = "Error: web driver not available."
        else:
            msg = "ERROR: no input provided."
            logger.error(f"[MCP][GMAIL DELETE EMAIL]:{msg}")

        result = TextContent(type="text", text=msg)
        result.meta = {"gmail_titles": gmail_titles}
        logger.debug("[MCP][GMAIL DELETE EMAIL]:gmail_titles:", gmail_titles)
        return [result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorGmailDeleteEmail")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]



async def gmail_respond(mainwin, args):  # type: ignore
    try:
        ebay_summary = {}
        if args["input"]:
            logger.debug(f"[MCP][GMAIL RESPOND]: {args['input']}")
            gmail_url = args["input"].get("gmail_url", "")
            recent = args["input"].get("recent", 72)  # number of hours.
            if not gmail_url:
                gmail_url = "https://mail.google.com/mail/u/0/#inbox"
            options = args["input"].get("options", {})
            web_driver = mainwin.getWebDriver()
            if not web_driver:
                # Use the first site's URL to initialize/connect the driver
                web_driver = connect_to_adspower(mainwin, gmail_url)
                logger.debug(f"[MCP][GMAIL RESPOND]:WebDriver acquired for ebay work: {type(web_driver)}")
                gmail_titles = scrape_gmail_titles(web_driver, gmail_url, recent)
                msg = "completed getting ebay shop summary"
            else:
                logger.error(f"[MCP][GMAIL RESPOND]:WebDriver acquired for ebay work: {type(web_driver)}")
                msg = "Error: web driver not available."
        else:
            msg = "ERROR: no input provided."
            logger.error(f"[MCP][GMAIL RESPOND]:{msg}")

        result = TextContent(type="text", text=msg)
        result.meta = {"gmail_titles": gmail_titles}
        logger.debug("[MCP][GMAIL RESPOND]:gmail_titles:", gmail_titles)
        return [result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorGmailRespond")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def gmail_move_email(mainwin, args):  # type: ignore
    try:
        ebay_summary = {}
        if args["input"]:
            logger.debug(f"[MCP][GMAIL MOVE EMAIL]: {args['input']}")
            gmail_url = args["input"].get("gmail_url", "")
            recent = args["input"].get("recent", 72)  # number of hours.
            if not gmail_url:
                gmail_url = "https://mail.google.com/mail/u/0/#inbox"
            options = args["input"].get("options", {})
            web_driver = mainwin.getWebDriver()
            if not web_driver:
                # Use the first site's URL to initialize/connect the driver
                web_driver = connect_to_adspower(mainwin, gmail_url)
                logger.debug(f"[MCP][GMAIL MOVE EMAIL]:WebDriver acquired for ebay work: {type(web_driver)}")
                gmail_titles = scrape_gmail_titles(web_driver, gmail_url, recent)
                msg = "completed getting ebay shop summary"
            else:
                logger.error(f"[MCP][GMAIL MOVE EMAIL]:WebDriver acquired for ebay work: {type(web_driver)}")
                msg = "Error: web driver not available."
        else:
            msg = "ERROR: no input provided."
            logger.error(f"[MCP][GMAIL MOVE EMAIL]:{msg}")

        result = TextContent(type="text", text=msg)
        result.meta = {"gmail_titles": gmail_titles}
        logger.debug("[MCP][GMAIL MOVE EMAIL]:gmail_titles:", gmail_titles)
        return [result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorGmailMoveEmail")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]



def _find_email_row(driver, target_title: str, target_from: str, target_datetime: str):
    """
    Find an email row matching the given criteria.
    
    Args:
        driver: Selenium WebDriver instance
        target_title: Email subject/title to match
        target_from: Sender name to match
        target_datetime: Datetime string to match (e.g., "Mon, Dec 8, 2025, 8:15 PM")
    
    Returns:
        WebElement of the matching row, or None if not found
    """
    import time
    
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "tr.zA"))
        )
        time.sleep(1)
        
        all_rows = driver.find_elements(By.CSS_SELECTOR, "tr.zA")
        logger.debug(f"[GMAIL] Searching {len(all_rows)} rows for: title='{target_title}', from='{target_from}'")
        
        for row in all_rows:
            try:
                row_title = ""
                row_from = ""
                row_datetime = ""
                
                try:
                    title_elem = row.find_element(By.CSS_SELECTOR, "div.y6 span.bqe")
                    row_title = title_elem.text or ""
                except Exception:
                    try:
                        title_elem = row.find_element(By.CSS_SELECTOR, "span.bqe")
                        row_title = title_elem.text or ""
                    except Exception:
                        pass
                
                try:
                    sender_elem = row.find_element(By.CSS_SELECTOR, "span.zF")
                    row_from = sender_elem.get_attribute("name") or sender_elem.text or ""
                except Exception:
                    pass
                
                try:
                    time_span = row.find_element(By.CSS_SELECTOR, "td.xW span[title]")
                    row_datetime = time_span.get_attribute("title") or ""
                except Exception:
                    pass
                
                title_match = target_title.strip().lower() in row_title.strip().lower() or row_title.strip().lower() in target_title.strip().lower()
                from_match = target_from.strip().lower() in row_from.strip().lower() or row_from.strip().lower() in target_from.strip().lower()
                datetime_match = target_datetime.strip() in row_datetime.strip() if target_datetime else True
                
                logger.debug(f"[GMAIL] Row check: title='{row_title[:30]}...', from='{row_from}', matches: title={title_match}, from={from_match}, datetime={datetime_match}")
                
                if title_match and from_match:
                    logger.debug(f"[GMAIL] Found matching email row")
                    return row
                    
            except Exception as e:
                logger.debug(f"[GMAIL] Error checking row: {e}")
                continue
        
        logger.debug(f"[GMAIL] No matching email found")
        return None
        
    except Exception as e:
        logger.error(f"[GMAIL] Error finding email row: {get_traceback(e, 'ErrorFindEmailRow')}")
        return None


def _mark_email_status(driver, row, status: str) -> bool:
    """
    Mark an email as read or unread using right-click context menu.
    
    Args:
        driver: Selenium WebDriver instance
        row: WebElement of the email row
        status: "read" or "unread"
    
    Returns:
        True if successful, False otherwise
    """
    import time
    
    try:
        row_classes = row.get_attribute("class") or ""
        is_currently_unread = "zE" in row_classes
        
        if status.lower() == "read" and not is_currently_unread:
            logger.debug("[GMAIL] Email is already marked as read")
            return True
        if status.lower() == "unread" and is_currently_unread:
            logger.debug("[GMAIL] Email is already marked as unread")
            return True
        
        actions = ActionChains(driver)
        actions.context_click(row).perform()
        time.sleep(0.5)
        
        if status.lower() == "read":
            menu_text = "Mark as read"
        else:
            menu_text = "Mark as unread"
        
        try:
            menu_item = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, f"//div[@role='menuitem']//span[contains(text(), '{menu_text}')]"))
            )
            menu_item.click()
            logger.debug(f"[GMAIL] Clicked '{menu_text}' menu item")
            time.sleep(0.5)
            return True
        except TimeoutException:
            try:
                menu_item = driver.find_element(By.XPATH, f"//div[contains(@class, 'J-N') and contains(., '{menu_text}')]")
                menu_item.click()
                logger.debug(f"[GMAIL] Clicked '{menu_text}' via fallback selector")
                time.sleep(0.5)
                return True
            except Exception:
                actions.send_keys(Keys.ESCAPE).perform()
                logger.debug("[GMAIL] Context menu item not found, trying keyboard shortcut")
                
                row.click()
                time.sleep(0.3)
                
                if status.lower() == "read":
                    actions = ActionChains(driver)
                    actions.key_down(Keys.SHIFT).send_keys('i').key_up(Keys.SHIFT).perform()
                else:
                    actions = ActionChains(driver)
                    actions.key_down(Keys.SHIFT).send_keys('u').key_up(Keys.SHIFT).perform()
                
                logger.debug(f"[GMAIL] Used keyboard shortcut for '{status}'")
                time.sleep(0.5)
                return True
                
    except Exception as e:
        logger.error(f"[GMAIL] Error marking email status: {get_traceback(e, 'ErrorMarkEmailStatus')}")
        return False


async def gmail_mark_status(mainwin, args):  # type: ignore
    """
    Mark an email as read or unread.
    
    Args:
        mainwin: Main window object with getWebDriver()
        args: Dict with input containing: title, from, datetime, status (read/unread)
    """
    try:
        if not args.get("input"):
            msg = "ERROR: no input provided."
            logger.error(f"[MCP][GMAIL MARK STATUS]: {msg}")
            result = TextContent(type="text", text=msg)
            result.meta = {"success": False}
            return [result]
        
        logger.debug(f"[MCP][GMAIL MARK STATUS]: {args['input']}")
        
        target_title = args["input"].get("title", "")
        target_from = args["input"].get("from", "")
        target_datetime = args["input"].get("datetime", "")
        target_status = args["input"].get("status", "read")
        gmail_url = args["input"].get("gmail_url", "https://mail.google.com/mail/u/0/#inbox")
        
        if not target_title:
            msg = "ERROR: email title is required."
            logger.error(f"[MCP][GMAIL MARK STATUS]: {msg}")
            result = TextContent(type="text", text=msg)
            result.meta = {"success": False}
            return [result]
        
        web_driver = mainwin.getWebDriver()
        if not web_driver:
            web_driver = connect_to_adspower(mainwin, gmail_url)
            logger.debug(f"[MCP][GMAIL MARK STATUS]: WebDriver acquired via adspower: {type(web_driver)}")
        
        if not web_driver:
            msg = "ERROR: WebDriver not available."
            logger.error(f"[MCP][GMAIL MARK STATUS]: {msg}")
            result = TextContent(type="text", text=msg)
            result.meta = {"success": False}
            return [result]
        
        current_url = web_driver.current_url
        if "mail.google.com" not in current_url:
            web_driver.get(gmail_url)
            import time
            time.sleep(2)
        
        email_row = _find_email_row(web_driver, target_title, target_from, target_datetime)
        
        if not email_row:
            msg = f"ERROR: Could not find email with title '{target_title}' from '{target_from}'"
            logger.error(f"[MCP][GMAIL MARK STATUS]: {msg}")
            result = TextContent(type="text", text=msg)
            result.meta = {"success": False, "title": target_title, "from": target_from}
            return [result]
        
        success = _mark_email_status(web_driver, email_row, target_status)
        
        if success:
            msg = f"Successfully marked email '{target_title}' as {target_status}"
            logger.debug(f"[MCP][GMAIL MARK STATUS]: {msg}")
        else:
            msg = f"Failed to mark email '{target_title}' as {target_status}"
            logger.error(f"[MCP][GMAIL MARK STATUS]: {msg}")
        
        result = TextContent(type="text", text=msg)
        result.meta = {"success": success, "title": target_title, "from": target_from, "status": target_status}
        return [result]
        
    except Exception as e:
        err_trace = get_traceback(e, "ErrorGmailMarkStatus")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]

def add_gmail_delete_email_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="gmail_delete_email",
        description="gmail delete emails.",
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


def add_gmail_write_new_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="gmail_write_new",
        description="gmail write an new email.",
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


def add_gmail_respond_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="gmail_respond",
        description="gmail respond to an email",
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


def add_gmail_read_full_email_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="gmail_read_full_email",
        description="read unread gmails for the past N days.",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["from", "from_email", "title", "datetime"],
                    "properties": {
                        "from": {
                            "type": "string",
                            "description": "from whom (nick name) this email is sent.",
                        },
                        "from_email": {
                            "type": "string",
                            "description": "the email of the sender.",
                        },
                        "title": {
                            "type": "string",
                            "description": "the title of the email.",
                        },
                        "datetime": {
                            "type": "string",
                            "description": "example: Mon, Dec 8, 2025, 8:15\u202fPM",
                        }
                    },
                }
            }
        },
    )

    tool_schemas.append(tool_schema)


def add_gmail_read_titles_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="gmail_read_titles",
        description="read titles of unread gmails for the past N hours.",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["gmail_url", "recent", "options"],
                    "properties": {
                        "gmail_url": {
                            "type": "string",
                            "description": "gmail inbox page URL (can be blank if using default).",
                        },
                        "recent": {
                            "type": "integer",
                            "description": "number of hours to look back and search unread emails in inbox",
                        },
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


def add_gmail_move_email_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="gmail_move_email",
        description="gmail move email to a different folder.",
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


def add_gmail_mark_status_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="gmail_mark_status",
        description="gmail mark en email as read/unread.",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["title", "from", "datetime", "status"],
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "the title of the email.",
                        },
                        "from": {
                            "type": "string",
                            "description": "from whom (nick name) this email is sent.",
                        },
                        "datetime": {
                            "type": "string",
                            "description": "example: Mon, Dec 8, 2025, 8:15\u202fPM",
                        },
                        "status": {
                            "type": "string",
                            "description": "read/unread",
                        }
                    },
                }
            }
        },
    )

    tool_schemas.append(tool_schema)