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


def scrape_gmails(driver, gmail_url: str, recent_hours: int = 72) -> dict:
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
        gmails = []
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
                gmails = scrape_gmails(web_driver, gmail_url, recent)
                gmail_titles = []
                # Strip non-serializable WebElement objects from response
                if isinstance(gmails, dict) and "titles" in gmails:
                    for title_item in gmails.get("titles", []):
                        # Make a copy without _full_data for the response (preserve original for cache)
                        title_copy = {k: v for k, v in title_item.items() if k != "_full_data"}
                        gmail_titles.append(title_copy)
                msg = "completed getting gmail titles"
            else:
                logger.error("[MCP][GMAIL READ TITLES]:WebDriver not available")
                msg = "Error: web driver not available."
        else:
            msg = "ERROR: no input provided."
            logger.error(f"[MCP][GMAIL READ TITLES]:{msg}")

        result = TextContent(type="text", text=msg)
        result.meta = {"unread_email_titles": gmail_titles}
        mainwin.setLatestEmails("gmail", gmails)

        logger.debug(f"[MCP][GMAIL READ TITLES]:gmail_titles: {gmail_titles}")
        return [result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorGmailReadTitles")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]



async def gmail_read_full_email(mainwin, args):
    """Read full email content by finding it from cached emails and clicking to open."""
    try:
        import time
        email_content = None
        email_data = None
        attachments = []
        
        if not args.get("input"):
            msg = "ERROR: no input provided."
            logger.error(f"[MCP][GMAIL READ FULL EMAIL]: {msg}")
            result = TextContent(type="text", text=msg)
            result.meta = {"success": False}
            return [result]
        
        logger.debug(f"[MCP][GMAIL READ FULL EMAIL]: {args['input']}")
        
        # Get search criteria from input (per schema)
        title = args["input"].get("title", "")
        sender = args["input"].get("from", "")
        from_email = args["input"].get("from_email", "")
        datetime_str = args["input"].get("datetime", "")
        
        # Try to find the email from cached latest_emails
        cached_emails = mainwin.getLatestEmails("gmail")
        email_data = None
        
        # Search in cached emails
        if cached_emails and "mails" in cached_emails:
            for mail in cached_emails.get("mails", {}).get("titles", []):
                # Match by criteria
                title_match = not title or title.lower() in mail.get("title", "").lower()
                sender_match = not sender or sender.lower() in mail.get("from", "").lower()
                email_match = not from_email or from_email.lower() in mail.get("from_email", "").lower()
                datetime_match = not datetime_str or datetime_str in mail.get("datetime", "")
                
                if title_match and sender_match and email_match and datetime_match:
                    email_data = mail
                    break
        
        if not email_data:
            # Fallback: use mainwin.findLatestEmail
            email_data = mainwin.findLatestEmail(
                title=title if title else None,
                sender=sender if sender else None,
                from_email=from_email if from_email else None,
                datetime_str=datetime_str if datetime_str else None
            )
        
        if email_data:
            logger.debug(f"[MCP][GMAIL READ FULL EMAIL]: Found cached email: {email_data.get('title', 'N/A')}")
            
            full_data = email_data.get("_full_data", {})
            snippet = full_data.get("snippet", "")
            has_attachment = full_data.get("has_attachment", False)
            elements = full_data.get("elements", {})
            row_element = elements.get("row")
            
            # If no attachments and we have snippet, we can use snippet as content
            # Otherwise, click to get full body
            if row_element:
                try:
                    # Click the row to open the email
                    row_element.click()
                    time.sleep(2)  # Wait for email to load
                    
                    # Get web driver to extract content
                    web_driver = mainwin.getWebDriver()
                    if web_driver:
                        # Extract the full email body
                        body_elements = web_driver.find_elements(By.CSS_SELECTOR, "div.a3s.aiL")
                        if body_elements:
                            email_content = body_elements[0].text
                        else:
                            # Try alternative selectors
                            body_elements = web_driver.find_elements(By.CSS_SELECTOR, "div[role='listitem'] div.ii.gt")
                            if body_elements:
                                email_content = body_elements[0].text
                            else:
                                # Last fallback
                                body_elements = web_driver.find_elements(By.CSS_SELECTOR, "div.gs div.ii.gt div")
                                if body_elements:
                                    email_content = body_elements[0].text
                        
                        # Extract attachments if present
                        if has_attachment:
                            try:
                                attachment_elements = web_driver.find_elements(By.CSS_SELECTOR, "div.aQH span.aV3")
                                for att in attachment_elements:
                                    attachments.append({
                                        "name": att.text,
                                        "element": att
                                    })
                            except Exception as att_err:
                                logger.debug(f"[MCP][GMAIL READ FULL EMAIL]: Error extracting attachments: {att_err}")
                        
                        msg = f"completed reading full email: {title}"
                    else:
                        # No driver, use snippet as fallback
                        email_content = snippet
                        msg = f"completed reading email snippet (no driver): {title}"
                        
                except Exception as click_err:
                    logger.error(f"[MCP][GMAIL READ FULL EMAIL]: Error clicking email: {click_err}")
                    # Fallback to snippet
                    email_content = snippet
                    msg = f"Error clicking email, using snippet: {click_err}"
            else:
                # No row element available, use snippet
                email_content = snippet
                msg = f"completed reading email snippet (no row element): {title}"
                logger.warning(f"[MCP][GMAIL READ FULL EMAIL]: Row element not available, using snippet")
        else:
            msg = f"Email not found matching: title='{title}', from='{sender}', from_email='{from_email}', datetime='{datetime_str}'"
            logger.warning(f"[MCP][GMAIL READ FULL EMAIL]: {msg}")

        result = TextContent(type="text", text=msg)
        result.meta = {
            "success": email_content is not None,
            "email_content": email_content,
            "snippet": email_data.get("_full_data", {}).get("snippet", "") if email_data else "",
            "has_attachment": email_data.get("_full_data", {}).get("has_attachment", False) if email_data else False,
            "attachments": [{"name": a["name"]} for a in attachments],  # Strip WebElements
            "email_info": {
                "title": email_data.get("title", "") if email_data else "",
                "from": email_data.get("from", "") if email_data else "",
                "from_email": email_data.get("from_email", "") if email_data else "",
                "datetime": email_data.get("datetime", "") if email_data else "",
            }
        }
        logger.debug(f"[MCP][GMAIL READ FULL EMAIL]: content length: {len(email_content) if email_content else 0}")
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
                gmail_titles = scrape_gmails(web_driver, gmail_url, recent)
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
                gmail_titles = scrape_gmails(web_driver, gmail_url, recent)
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
    """Respond to an email by finding it from cache, opening it, and sending a reply."""
    try:
        import time
        
        if not args.get("input"):
            msg = "ERROR: no input provided."
            logger.error(f"[MCP][GMAIL RESPOND]: {msg}")
            result = TextContent(type="text", text=msg)
            result.meta = {"success": False}
            return [result]
        
        logger.debug(f"[MCP][GMAIL RESPOND]: {args['input']}")
        
        # Get input parameters per schema
        title = args["input"].get("title", "")
        sender = args["input"].get("from", "")
        from_email = args["input"].get("from_email", "")
        datetime_str = args["input"].get("datetime", "")
        response_text = args["input"].get("response_text", "")
        response_attachments = args["input"].get("response_attachments", [])
        gmail_url = args["input"].get("gmail_url", "https://mail.google.com/mail/u/0/#inbox")
        
        if not response_text:
            msg = "ERROR: response_text is required."
            logger.error(f"[MCP][GMAIL RESPOND]: {msg}")
            result = TextContent(type="text", text=msg)
            result.meta = {"success": False}
            return [result]
        
        # Try to find the email from cached latest_emails
        email_data = mainwin.findLatestEmail(
            title=title if title else None,
            sender=sender if sender else None,
            from_email=from_email if from_email else None,
            datetime_str=datetime_str if datetime_str else None
        )
        
        # Get or connect WebDriver
        web_driver = mainwin.getWebDriver()
        if not web_driver:
            web_driver = connect_to_adspower(mainwin, gmail_url)
            logger.debug(f"[MCP][GMAIL RESPOND]: WebDriver acquired via adspower: {type(web_driver)}")
        
        if not web_driver:
            msg = "ERROR: WebDriver not available."
            logger.error(f"[MCP][GMAIL RESPOND]: {msg}")
            result = TextContent(type="text", text=msg)
            result.meta = {"success": False}
            return [result]
        
        success = False
        
        if email_data:
            logger.debug(f"[MCP][GMAIL RESPOND]: Found cached email: {email_data.get('title', 'N/A')}")
            
            full_data = email_data.get("_full_data", {})
            elements = full_data.get("elements", {})
            row_element = elements.get("row")
            
            if row_element:
                try:
                    # Click the row to open the email
                    row_element.click()
                    time.sleep(2)
                    
                    # Click the Reply button
                    try:
                        # Try multiple selectors for Reply button
                        reply_btn = None
                        reply_selectors = [
                            "div[data-tooltip='Reply']",
                            "div[aria-label='Reply']",
                            "span.ams.bkH",  # Reply icon
                            "div.T-I.J-J5-Ji.T-I-Js-Gs.aap.T-I-awG.T-I-ax7.L3"  # Reply button class
                        ]
                        for selector in reply_selectors:
                            try:
                                reply_btn = WebDriverWait(web_driver, 3).until(
                                    EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                                )
                                if reply_btn:
                                    break
                            except TimeoutException:
                                continue
                        
                        if reply_btn:
                            reply_btn.click()
                            time.sleep(1)
                        else:
                            # Fallback: use keyboard shortcut 'r' for reply
                            actions = ActionChains(web_driver)
                            actions.send_keys('r').perform()
                            time.sleep(1)
                        
                        # Wait for compose area to appear and type response
                        compose_selectors = [
                            "div[aria-label='Message Body']",
                            "div.Am.Al.editable.LW-avf.tS-tW",
                            "div[role='textbox'][aria-label='Message Body']",
                            "div.editable[contenteditable='true']"
                        ]
                        compose_area = None
                        for selector in compose_selectors:
                            try:
                                compose_area = WebDriverWait(web_driver, 5).until(
                                    EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                                )
                                if compose_area:
                                    break
                            except TimeoutException:
                                continue
                        
                        if compose_area:
                            compose_area.click()
                            time.sleep(0.3)
                            compose_area.send_keys(response_text)
                            time.sleep(0.5)
                            
                            # Handle attachments if any
                            if response_attachments:
                                for attachment_path in response_attachments:
                                    try:
                                        # Find file input for attachments
                                        file_input = web_driver.find_element(By.CSS_SELECTOR, "input[type='file'][name='Filedata']")
                                        if file_input and os.path.exists(attachment_path):
                                            file_input.send_keys(attachment_path)
                                            time.sleep(1)
                                    except Exception as att_err:
                                        logger.debug(f"[MCP][GMAIL RESPOND]: Error attaching file {attachment_path}: {att_err}")
                            
                            # Click Send button
                            send_selectors = [
                                "div[aria-label*='Send']",
                                "div[data-tooltip*='Send']",
                                "div.T-I.J-J5-Ji.aoO.v7.T-I-atl.L3"
                            ]
                            send_btn = None
                            for selector in send_selectors:
                                try:
                                    send_btn = WebDriverWait(web_driver, 3).until(
                                        EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                                    )
                                    if send_btn:
                                        break
                                except TimeoutException:
                                    continue
                            
                            if send_btn:
                                send_btn.click()
                                time.sleep(2)
                                success = True
                                msg = f"Successfully sent reply to: {title}"
                            else:
                                # Fallback: Ctrl+Enter to send
                                actions = ActionChains(web_driver)
                                actions.key_down(Keys.CONTROL).send_keys(Keys.RETURN).key_up(Keys.CONTROL).perform()
                                time.sleep(2)
                                success = True
                                msg = f"Successfully sent reply (via keyboard) to: {title}"
                        else:
                            msg = f"ERROR: Could not find compose area to type response"
                            logger.error(f"[MCP][GMAIL RESPOND]: {msg}")
                            
                    except Exception as reply_err:
                        msg = f"ERROR: Failed to reply: {reply_err}"
                        logger.error(f"[MCP][GMAIL RESPOND]: {msg}")
                        
                except Exception as click_err:
                    msg = f"ERROR: Failed to click email row: {click_err}"
                    logger.error(f"[MCP][GMAIL RESPOND]: {msg}")
            else:
                # No cached row element, try to find email by searching
                current_url = web_driver.current_url
                if "mail.google.com" not in current_url:
                    web_driver.get(gmail_url)
                    time.sleep(2)
                
                email_row = _find_email_row(web_driver, title, sender, datetime_str)
                if email_row:
                    email_row.click()
                    time.sleep(2)
                    # Continue with reply logic (same as above)
                    actions = ActionChains(web_driver)
                    actions.send_keys('r').perform()
                    time.sleep(1)
                    
                    compose_area = WebDriverWait(web_driver, 5).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, "div[aria-label='Message Body'], div.Am.Al.editable"))
                    )
                    if compose_area:
                        compose_area.click()
                        compose_area.send_keys(response_text)
                        time.sleep(0.5)
                        
                        actions = ActionChains(web_driver)
                        actions.key_down(Keys.CONTROL).send_keys(Keys.RETURN).key_up(Keys.CONTROL).perform()
                        time.sleep(2)
                        success = True
                        msg = f"Successfully sent reply to: {title}"
                    else:
                        msg = f"ERROR: Could not find compose area"
                else:
                    msg = f"ERROR: Could not find email row for: {title}"
        else:
            msg = f"Email not found matching: title='{title}', from='{sender}', from_email='{from_email}', datetime='{datetime_str}'"
            logger.warning(f"[MCP][GMAIL RESPOND]: {msg}")

        result = TextContent(type="text", text=msg)
        result.meta = {
            "success": success,
            "email_title": title,
            "response_sent": success,
            "attachments_count": len(response_attachments) if response_attachments else 0
        }
        logger.debug(f"[MCP][GMAIL RESPOND]: {msg}")
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
                gmail_titles = scrape_gmails(web_driver, gmail_url, recent)
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
                    "required": ["from", "from_email", "title", "datetime", "response_text", "response_attachments"],
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
                        },
                        "response_text": {
                            "type": "string",
                            "description": "the response text.",
                        },
                        "response_attachments": {
                            "type": "array",
                            "description": "the response attachments.",
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
        description="read the unread gmail full contents given the email title, sender and datetime.",
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