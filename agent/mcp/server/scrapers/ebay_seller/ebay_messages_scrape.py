import os
from datetime import datetime
import base64
import time
from urllib.parse import urljoin
from typing import Optional, List
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    StaleElementReferenceException,
    ElementClickInterceptedException,
)
from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback
from mcp.types import CallToolResult, TextContent
from .ebay_orders_scrape import ensure_logged_in_ebay


async def ebay_read_all_messages(mainwin, args):  # type: ignore
    try:
        logger.debug("eBay read all unread messages started....")
        new_messages = []
        options = args["input"]["options"]
        msgs_url = args["input"].get("msgs_url", "")
        web_driver = mainwin.getWebDriver()

        n_new_messages = None
        if options:
            n_new_messages = options.get("n_new_messages")

        new_messages = scrape_ebay_unread_messages(
            web_driver,
            msgs_url,
            n_new_messages=n_new_messages,
        )

        msg = f"completed in fetching ebay messages: {len(new_messages)} messages fetched."
        tool_result = TextContent(type="text", text=msg)
        tool_result.meta = {"new_messages": new_messages}
        return [tool_result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorFetchEbayMessages")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]



def scrape_ebay_unread_messages(web_driver, msgs_url, n_new_messages=None):
    try:
        # Navigate to eBay Seller Hub orders
        if not msgs_url:
            msgs_url = "https://www.ebay.com/cnt/ViewMessage?_caprdt=1&group_type=CORE"

        web_driver.get(msgs_url)
        new_messages = []
        # Initialize wait and ensure logged in
        wait = WebDriverWait(web_driver, 30)
        if not ensure_logged_in_ebay(web_driver, wait):
            logger.debug("ensure_logged_in_ebay returned False. Aborting message scrape.")
            return {"error": "NOT_LOGGED_IN"}
        logger.debug("ensured logged in....")

        try:
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '.msg-inbox-list .card__item')))
        except TimeoutException:
            logger.debug("Timed out waiting for message cards to render")
            return []

        # Attempt to scroll through the infinite list to load unread messages
        try:
            list_container = web_driver.find_element(By.CSS_SELECTOR, '.msg-inbox-list .app-infinite-scroll__outer-container')
        except NoSuchElementException:
            list_container = None

        scroll_target = None
        if list_container:
            scroll_target = list_container
        try:
            scroller = web_driver.find_element(By.CSS_SELECTOR, '.msg-inbox-list .app-infinite-scroll__scroller')
            if scroller:
                scroll_target = scroller
        except NoSuchElementException:
            pass

        desired_unread = None
        if n_new_messages is not None:
            try:
                desired_unread = int(n_new_messages)
            except (ValueError, TypeError):
                desired_unread = None
            if desired_unread is not None and desired_unread <= 0:
                desired_unread = None

        def count_unread(card_elements):
            unread = 0
            for card in card_elements:
                try:
                    content_el = card.find_element(By.CSS_SELECTOR, '.card__content')
                except NoSuchElementException:
                    continue
                classes = content_el.get_attribute("class") or ""
                if "card__content-unread" in classes:
                    unread += 1
            return unread

        last_loaded = -1
        stagnant_iterations = 0
        max_attempts = 40 if desired_unread else 12
        max_stagnant_allowed = 5 if desired_unread else 3

        for attempt in range(max_attempts):
            cards = web_driver.find_elements(By.CSS_SELECTOR, '.msg-inbox-list .card__item')

            if desired_unread and count_unread(cards) >= desired_unread:
                break

            if len(cards) == last_loaded:
                stagnant_iterations += 1
            else:
                stagnant_iterations = 0
            last_loaded = len(cards)

            try:
                if scroll_target:
                    web_driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight;", scroll_target)
                elif cards:
                    web_driver.execute_script("arguments[0].scrollIntoView({block: 'end'});", cards[-1])
                else:
                    web_driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            except Exception:
                break

            wait_timeout = 3 if desired_unread else 2
            try:
                WebDriverWait(web_driver, wait_timeout).until(
                    lambda d: len(d.find_elements(By.CSS_SELECTOR, '.msg-inbox-list .card__item')) > last_loaded
                )
            except TimeoutException:
                pass

            time.sleep(0.2)

            if stagnant_iterations >= max_stagnant_allowed:
                break

        cards = web_driver.find_elements(By.CSS_SELECTOR, '.msg-inbox-list .card__item')
        logger.debug(f"Located {len(cards)} message cards (desired_unread={desired_unread})")

        for card in cards:
            try:
                content = card.find_element(By.CSS_SELECTOR, '.card__content')
            except NoSuchElementException:
                continue

            classes = content.get_attribute("class") or ""
            if "card__content-unread" not in classes:
                # Skip read messages when we are specifically asked for unread
                continue

            message = {
                "card_id": card.get_attribute("id") or "",
                "status": "unread",
            }

            try:
                sender_el = content.find_element(By.CSS_SELECTOR, '.card__username')
                message["sender"] = sender_el.text.strip()
            except NoSuchElementException:
                message["sender"] = ""

            try:
                title_el = content.find_element(By.CSS_SELECTOR, '.card__conversation-title')
                message["subject"] = title_el.text.strip()
            except NoSuchElementException:
                message["subject"] = ""

            snippet = ""
            try:
                snippet_el = content.find_element(By.CSS_SELECTOR, '.card__latest-message')
                snippet = snippet_el.text.strip()
            except NoSuchElementException:
                # Unread system messages may not have a snippet; attempt aria-label as fallback
                try:
                    checkbox = card.find_element(By.CSS_SELECTOR, 'input[type="checkbox"]')
                    snippet = checkbox.get_attribute("aria-label") or ""
                except NoSuchElementException:
                    pass
            message["snippet"] = snippet

            try:
                date_el = content.find_element(By.CSS_SELECTOR, '.card__datetime .ux-textspans')
                message["received_at"] = date_el.text.strip()
            except NoSuchElementException:
                message["received_at"] = ""

            try:
                checkbox = card.find_element(By.CSS_SELECTOR, 'input[type="checkbox"]')
                message["aria_label"] = checkbox.get_attribute("aria-label") or ""
            except NoSuchElementException:
                message["aria_label"] = ""

            try:
                wrapper = card.find_element(By.CSS_SELECTOR, '.card__message-content-wrapper')
                message["conversation_url"] = wrapper.get_attribute("data-href") or ""
            except NoSuchElementException:
                message["conversation_url"] = ""

            try:
                detail_data = _fetch_message_detail(web_driver, message, card)
                if detail_data:
                    message.update(detail_data)
            except Exception as detail_exc:
                logger.debug(f"Failed to fetch message detail for {message.get('card_id')}: {detail_exc}")

            new_messages.append(message)

            if desired_unread and len(new_messages) >= desired_unread:
                break

        logger.debug(f"new_messages collected: {len(new_messages)}", new_messages)
        return new_messages

    except Exception as e:
        err_msg = get_traceback(e, "ErrorScrapeEBayOrdersSummary")
        logger.debug(err_msg)
        return {"error": err_msg}


def _fetch_message_detail(web_driver, message, card):
    conversation_url = message.get("conversation_url") or ""
    if not conversation_url:
        return {}

    detail_url = conversation_url
    if not detail_url.startswith("http"):
        detail_url = urljoin(web_driver.current_url, detail_url)

    original_window = web_driver.current_window_handle
    existing_handles = set(web_driver.window_handles)

    web_driver.execute_script("window.open(arguments[0], '_blank');", detail_url)

    try:
        WebDriverWait(web_driver, 15).until(lambda d: len(d.window_handles) > len(existing_handles))
    except TimeoutException:
        return {}

    new_handle = None
    for handle in web_driver.window_handles:
        if handle not in existing_handles:
            new_handle = handle
            break

    if not new_handle:
        return {}

    web_driver.switch_to.window(new_handle)

    detail_data = {}
    try:
        detail_data = _extract_message_detail(web_driver)
        _mark_message_unread_from_detail(web_driver)
    finally:
        web_driver.close()
        web_driver.switch_to.window(original_window)
        time.sleep(0.2)
        try:
            _restore_card_unread_state(web_driver, card, message.get("card_id"))
        except Exception as restore_exc:
            logger.debug(f"Failed to restore unread state for {message.get('card_id')}: {restore_exc}")

    return detail_data


def _extract_message_detail(driver):
    wait = WebDriverWait(driver, 20)
    possible_roots = [
        '.msg-thread',
        '.message-thread',
        '.msg-conversation',
        'main',
    ]

    root_el = None
    for selector in possible_roots:
        try:
            root_el = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
            if root_el:
                break
        except TimeoutException:
            continue

    if root_el is None:
        return {}

    thread_messages = _extract_thread_messages(driver)
    attachments = _extract_attachment_names(driver)

    combined_text = []
    for msg in thread_messages:
        parts = [msg.get("author", ""), msg.get("sent_at", ""), msg.get("body", "")] 
        combined_text.append(" - ".join(filter(None, [parts[0], parts[1]])).strip())
        if msg.get("body"):
            combined_text.append(msg["body"])

    detail_body = "\n\n".join([line for line in combined_text if line])

    return {
        "thread_messages": thread_messages,
        "attachments": attachments,
        "body": detail_body,
    }


def _extract_thread_messages(driver) -> List[dict]:
    selectors = [
        '.msg-thread__message',
        '.message-thread__message',
        '.msg-conversation__message',
    ]

    messages: List[dict] = []
    message_elements = []
    for selector in selectors:
        elems = driver.find_elements(By.CSS_SELECTOR, selector)
        if elems:
            message_elements = elems
            break

    if not message_elements:
        # fallback: attempt to capture standalone message body
        body_candidates = driver.find_elements(By.CSS_SELECTOR, '.msg-thread, .message-thread, .msg-conversation')
        text = "\n".join([el.text for el in body_candidates if el.text])
        if text:
            messages.append({"body": text})
        return messages

    for element in message_elements:
        try:
            author = ""
            sent_at = ""
            body = ""

            try:
                author_el = element.find_element(By.CSS_SELECTOR, '.msg-thread__author, .message__author, .msg-conversation__author')
                author = author_el.text.strip()
            except NoSuchElementException:
                pass

            try:
                time_el = element.find_element(By.CSS_SELECTOR, '.msg-thread__time, .message__timestamp, .msg-conversation__timestamp')
                sent_at = time_el.text.strip()
            except NoSuchElementException:
                pass

            body_selectors = [
                '.msg-thread__message-body',
                '.message__body',
                '.msg-conversation__message-body',
            ]
            for body_selector in body_selectors:
                try:
                    body_el = element.find_element(By.CSS_SELECTOR, body_selector)
                    body = body_el.text.strip()
                    if body:
                        break
                except NoSuchElementException:
                    continue

            if not body:
                body = element.text.strip()

            messages.append({
                "author": author,
                "sent_at": sent_at,
                "body": body,
            })
        except StaleElementReferenceException:
            continue

    return messages


def _extract_attachment_names(driver) -> List[str]:
    attachment_selectors = [
        '.msg-attachment__item .msg-attachment__filename',
        '.message-attachment__item .message-attachment__filename',
        '.attachment__filename',
        'a[data-test-id="attachment-link"]',
    ]

    names: List[str] = []
    seen = set()
    for selector in attachment_selectors:
        elements = driver.find_elements(By.CSS_SELECTOR, selector)
        for element in elements:
            text = element.text.strip()
            if not text:
                text = element.get_attribute("title") or element.get_attribute("aria-label") or ""
                text = text.strip()
            if text and text not in seen:
                seen.add(text)
                names.append(text)

    return names


def _mark_message_unread_from_detail(driver):
    selectors = [
        (By.CSS_SELECTOR, '[data-test-id="mark-unread"], button[data-test-id="mark-unread"]'),
        (By.CSS_SELECTOR, 'button[aria-label*="Mark unread" i]'),
        (By.XPATH, "//button[contains(translate(., 'UNREAD', 'unread'), 'mark as unread')]"),
    ]

    for by, value in selectors:
        try:
            btn = WebDriverWait(driver, 3).until(EC.element_to_be_clickable((by, value)))
            btn.click()
            time.sleep(0.2)
            return
        except Exception:
            continue


def _restore_card_unread_state(driver, card, card_id):
    if card is None:
        return

    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'nearest'});", card)
    except Exception:
        pass

    unread_selectors = [
        'button[aria-label*="Mark unread" i]',
        '[data-test-id="mark-unread"]',
    ]

    for selector in unread_selectors:
        try:
            button = card.find_element(By.CSS_SELECTOR, selector)
            if button.is_enabled():
                button.click()
                time.sleep(0.2)
                return
        except NoSuchElementException:
            continue
        except ElementClickInterceptedException:
            driver.execute_script("arguments[0].click();", button)
            time.sleep(0.2)
            return

    # Fallback: try context menu
    try:
        more_button = card.find_element(By.CSS_SELECTOR, 'button[aria-label*="More" i]')
        more_button.click()
        time.sleep(0.2)
        menu_selectors = [
            (By.CSS_SELECTOR, 'button[aria-label*="Mark unread" i]'),
            (By.XPATH, "//span[contains(translate(., 'UNREAD', 'unread'), 'mark as unread')]")
        ]
        for by, value in menu_selectors:
            try:
                menu_item = WebDriverWait(driver, 3).until(EC.element_to_be_clickable((by, value)))
                menu_item.click()
                time.sleep(0.2)
                return
            except Exception:
                continue
    except NoSuchElementException:
        pass

    # Final fallback: re-find card by id and attempt again
    if card_id:
        try:
            refreshed_card = driver.find_element(By.CSS_SELECTOR, f'#{card_id}')
            if refreshed_card:
                _restore_card_unread_state(driver, refreshed_card, None)
        except NoSuchElementException:
            pass



async def ebay_read_next_message(mainwin, args):  # type: ignore
    try:
        logger.debug("eBay read next unread message started....")
        new_messages = []
        options = args["input"]["options"]
        web_driver = mainwin.getWebDriver()

        msg = f"completed in reading next unread ebay message: {len(new_messages)} messages fetched."
        tool_result = TextContent(type="text", text=msg)
        tool_result.meta = {"new_messages": new_messages}
        return [tool_result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorEBAYReadingNextMessage")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]



async def ebay_respond_to_message(mainwin, args):  # type: ignore
    try:
        logger.debug("ebay_respond_to_message started....")
        executed = []

        input_payload = args.get("input") or {}
        msgs_url = input_payload.get("msgs_url")
        messages = input_payload.get("messages") or input_payload.get("messages_todos") or []

        if not messages:
            logger.debug("No messages provided to respond.")
            msg = "No messages to respond to."
            tool_result = TextContent(type="text", text=msg)
            tool_result.meta = {"executed": executed}
            return [tool_result]

        web_driver = mainwin.getWebDriver()
        if not web_driver:
            logger.debug("Web driver not available for responding to messages.")
            return [TextContent(type="text", text="ERROR: WebDriver unavailable.")]

        if msgs_url:
            web_driver.get(msgs_url)

        wait = WebDriverWait(web_driver, 30)
        if not ensure_logged_in_ebay(web_driver, wait):
            logger.debug("ensure_logged_in_ebay returned False. Aborting respond flow.")
            return [TextContent(type="text", text="ERROR: NOT_LOGGED_IN")]

        for idx, message in enumerate(messages, start=1):
            response_payload = message.get("response") or {}
            response_text = (response_payload.get("text") or "").strip()
            attachment_paths = response_payload.get("attachments") or []

            if not response_text and not attachment_paths:
                logger.debug(f"[{idx}] Response empty; skipping message {message.get('card_id')}")
                executed.append({
                    "card_id": message.get("card_id"),
                    "status": "skipped",
                    "reason": "empty-response",
                })
                continue

            try:
                detail_url = _resolve_conversation_url(web_driver, message)
                if not detail_url:
                    executed.append({
                        "card_id": message.get("card_id"),
                        "status": "failed",
                        "reason": "missing-conversation-url",
                    })
                    continue

                _send_response_to_message(
                    web_driver,
                    detail_url,
                    response_text,
                    attachment_paths,
                )

                executed.append({
                    "card_id": message.get("card_id"),
                    "status": "sent",
                    "response_text": response_text,
                    "attachments": attachment_paths,
                })
            except Exception as respond_exc:
                logger.debug(f"Failed responding to message {message.get('card_id')}: {respond_exc}")
                executed.append({
                    "card_id": message.get("card_id"),
                    "status": "failed",
                    "reason": str(respond_exc),
                })

        msg = f"completed in answering ebay messages: {len([e for e in executed if e.get('status') == 'sent'])} messages answered."
        tool_result = TextContent(type="text", text=msg)
        tool_result.meta = {"executed": executed}
        return [tool_result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorEBAYRespoondToMessage")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]


def _resolve_conversation_url(driver, message):
    conversation_url = message.get("conversation_url") or ""
    if conversation_url:
        if conversation_url.startswith("http"):
            return conversation_url
        return urljoin(driver.current_url, conversation_url)

    # fallback: attempt to locate card by id and click to extract href
    card_id = message.get("card_id") or message.get("id")
    if not card_id:
        return ""

    try:
        card_element = driver.find_element(By.CSS_SELECTOR, f"#{card_id}")
        try:
            wrapper = card_element.find_element(By.CSS_SELECTOR, '.card__message-content-wrapper')
            href = wrapper.get_attribute("data-href") or wrapper.get_attribute("href") or ""
            if href:
                if href.startswith("http"):
                    return href
                return urljoin(driver.current_url, href)
        except NoSuchElementException:
            pass
    except NoSuchElementException:
        return ""

    return ""


def _send_response_to_message(driver, detail_url, text_body, attachment_paths):
    original_window = driver.current_window_handle
    existing_handles = set(driver.window_handles)

    driver.execute_script("window.open(arguments[0], '_blank');", detail_url)

    try:
        WebDriverWait(driver, 15).until(lambda d: len(d.window_handles) > len(existing_handles))
    except TimeoutException:
        raise RuntimeError("detail-window-open-timeout")

    new_handle = None
    for handle in driver.window_handles:
        if handle not in existing_handles:
            new_handle = handle
            break

    if not new_handle:
        raise RuntimeError("detail-window-handle-missing")

    driver.switch_to.window(new_handle)

    try:
        _wait_for_reply_composer(driver)
        if text_body:
            _enter_reply_text(driver, text_body)

        if attachment_paths:
            _upload_reply_attachments(driver, attachment_paths)

        _submit_reply(driver)

        # Wait for confirmation or thread update to ensure send completed
        _wait_for_send_confirmation(driver)
    finally:
        driver.close()
        driver.switch_to.window(original_window)
        time.sleep(0.2)


def _wait_for_reply_composer(driver):
    composer_selectors = [
        '.msg-compose',
        '[data-test-id="reply-compose"]',
        'form[action*="Send" i]',
    ]

    for selector in composer_selectors:
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, selector))
            )
            return
        except TimeoutException:
            continue


def _enter_reply_text(driver, text_body):
    input_selectors = [
        'textarea[name="reply"]',
        'textarea[name="message"]',
        'textarea[id*="reply" i]',
        'div[contenteditable="true"][role="textbox"]',
        'div[contenteditable="true"][data-placeholder*="Reply" i]',
    ]

    for selector in input_selectors:
        try:
            element = driver.find_element(By.CSS_SELECTOR, selector)
            element.clear()
            element.send_keys(text_body)
            return
        except (NoSuchElementException, StaleElementReferenceException):
            continue

    # Fallback: attempt to focus active element
    active = driver.switch_to.active_element
    try:
        active.clear()
    except Exception:
        pass
    active.send_keys(text_body)


def _upload_reply_attachments(driver, attachment_paths):
    file_input_selectors = [
        'input[type="file"][name*="attachment" i]',
        'input[type="file"][data-test-id*="attachment" i]',
        'input[type="file"][multiple]',
        'input[type="file"]',
    ]

    file_input = None
    for selector in file_input_selectors:
        try:
            file_input = driver.find_element(By.CSS_SELECTOR, selector)
            if file_input:
                break
        except NoSuchElementException:
            continue

    if not file_input:
        raise RuntimeError("attachment-input-not-found")

    existing_value = file_input.get_attribute("value") or ""
    if existing_value:
        file_input.clear()

    valid_paths = []
    for path in attachment_paths:
        if not path:
            continue
        normalized = os.path.abspath(path)
        if os.path.isfile(normalized):
            valid_paths.append(normalized)
        else:
            logger.debug(f"Attachment path not found: {path}")

    if not valid_paths:
        return

    combined = "\n".join(valid_paths)
    file_input.send_keys(combined)

    # Wait for attachment previews to render
    try:
        WebDriverWait(driver, 10).until(
            lambda d: len(d.find_elements(By.CSS_SELECTOR, '[data-test-id="attachment-preview"], .attachment-preview, .msg-attachment__item')) >= len(valid_paths)
        )
    except TimeoutException:
        logger.debug("Attachment upload confirmation timeout")


def _submit_reply(driver):
    send_selectors = [
        (By.CSS_SELECTOR, 'button[data-test-id="send"], button[data-test-id="send-button"]'),
        (By.CSS_SELECTOR, 'button[type="submit"][aria-label*="Send" i]'),
        (By.XPATH, "//button[contains(translate(., 'SEND', 'send'), 'send')]")
    ]

    for by, value in send_selectors:
        try:
            button = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((by, value)))
            button.click()
            return
        except TimeoutException:
            continue
        except ElementClickInterceptedException:
            driver.execute_script("arguments[0].click();", button)
            return

    raise RuntimeError("send-button-not-found")


def _wait_for_send_confirmation(driver):
    confirmation_selectors = [
        '[data-test-id="toast-message"]',
        '.toast__message',
        '.notification--success',
    ]

    end_time = time.time() + 10
    while time.time() < end_time:
        for selector in confirmation_selectors:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            if any(el.is_displayed() for el in elements):
                return
        time.sleep(0.5)

    # fallback: consider send successful if new reply bubble appears
    try:
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '.msg-thread__message--outbound, .message--outbound'))
        )
    except TimeoutException:
        logger.debug("No explicit confirmation detected after send")



def add_ebay_read_all_messages_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="ebay_read_all_messages",
        description="read ebay newly received messages list.",
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


def add_ebay_respond_to_message_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="ebay_respond_to_message",
        description="Answer ebay messages with text, attachments, and related actions if any (for example, handle return, cancel, refund/partial refund, send replacement items, etc",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["messages_todos"],
                    "properties": {
                        "type": "array",
                        "description": "list of json objects with basic attributes of original_label(full path file name), product_name_short, quantity, and customer_name.",
                        "items": {
                            "type": "object",
                            "required": ["message_id", "reply_text", "reply_attachments", "actions"],
                            "properties": {
                                "message_id": {"type": "string"},
                                "reply_text": {"type": "string"},
                                "reply_attachments": {"type": "array"},
                                "actions": {"type": "array"}
                            }
                        }
                    }
                }
            }
        },
    )

    tool_schemas.append(tool_schema)


def add_ebay_read_next_message_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="ebay_read_next_message",
        description="in ebay seller hub messages page, read next unread message by clicking on the message, read it, summerarize it, reaspond to it, and return the handling details info in json format including ones that require human intervention.",
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
                            "description": "some options in json format including policies, etc. will use default if these info are missing anyways.",
                        }
                    },
                }
            }
        },
    )

    tool_schemas.append(tool_schema)