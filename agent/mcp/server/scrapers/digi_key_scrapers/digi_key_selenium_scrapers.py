import re, json, time, random, unicodedata, traceback
from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException, ElementClickInterceptedException, ElementNotInteractableException, WebDriverException
from agent.agent_service import get_agent_by_id
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from typing import Any, Dict, Tuple, Union, Optional, List, Iterable, Callable
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.common.keys import Keys
from contextlib import contextmanager
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities

caps = DesiredCapabilities.CHROME.copy()
caps["goog:loggingPrefs"] = {"performance": "ALL"}  # enable Network.* in get_log('performance')


PX_STATE = ("PX_NONE", "PX_PRESENT", "PX_SILENT", "PX_CHALLENGE_SHOWN", "PX_BLOCK_PAGE")

Locator = Tuple[str, str]
_ITEMS_TRAIL = re.compile(r"\s*\d[\d,]*\s*Items\s*$", re.I)


class PXGuardTrip(RuntimeError):
    def __init__(self, msg, details=None):
        super().__init__(msg)
        self.details = details or {}

def _try_js(driver, script, args=None, default=None):
    try:
        return driver.execute_script(script, *(args or []))
    except Exception:
        return default

def _label_of(a):
    """Visible label of the anchor without the trailing '#### Items' text."""
    return _ITEMS_TRAIL.sub("", (a.text or "").strip())

def _try_js(driver, script, args=None, default=None):
    try:
        return driver.execute_script(script, *(args or []))
    except Exception:
        return default

def _has_px_dom(driver) -> Dict[str, Any]:
    # Quick DOM probes (fast; avoid full page_source when possible)
    challenge_node = _try_js(
        driver,
        "return document.querySelector('#px-captcha-wrapper, iframe[title*=\"Human verification\" i]) || null;"
    )
    block_title = (_try_js(driver, "return document.title || '';", default="") or "").strip()
    meta_desc = _try_js(driver, "let m=document.querySelector('meta[name=description]'); return m?m.content:'';", default="") or ""
    # Digi-Key block page fingerprints you pasted
    digikey_logo = _try_js(driver, "return !!document.querySelector('img.px-captcha-logo[src*=\"mobile-robot-2.png\"]');", default=False)
    human_css = _try_js(driver, "return !!document.querySelector('link[href*=\"humanSecurity\"]');", default=False)
    header_text = _try_js(driver, "let el=document.querySelector('.px-captcha-header'); return el?el.textContent.trim():'';", default="") or ""
    app_id = _try_js(driver, "return window._pxAppId || window._pxAppId2 || null;", default=None)

    return {
        "challenge_dom": bool(challenge_node),
        "block_title": block_title,
        "meta_desc": meta_desc,
        "has_human_css": bool(human_css),
        "has_digikey_block_logo": bool(digikey_logo),
        "captcha_header_text": header_text,
        "app_id": app_id,
    }

def _px_cookies(driver) -> List[str]:
    names = []
    try:
        for c in driver.get_cookies():
            n = c.get("name") or ""
            if n.startswith("_px"):
                names.append(n)
    except Exception:
        pass
    return names

def _px_net_in_logs(driver) -> Dict[str, Any]:
    """
    Optional: requires Chrome perf logging enabled.
    Look for calls to first-party /lO2Z... endpoints or px-cloud.
    """
    hits, blocks = 0, 0
    urls = []
    try:
        logs = driver.get_log("performance")  # needs caps set at driver init
        for row in logs:
            try:
                msg = json.loads(row.get("message", "{}")).get("message", {})
            except Exception:
                continue
            if msg.get("method") not in ("Network.requestWillBeSent", "Network.responseReceived"):
                continue
            params = msg.get("params", {})
            url = (params.get("request", {}) or {}).get("url") or params.get("response", {}).get("url") or ""
            if not url:
                continue
            if any(k in url for k in ("/captcha", "/xhr", "px-cloud.net", "/lO2Z")):
                urls.append(url)
                if msg.get("method") == "Network.responseReceived":
                    status = (params.get("response", {}) or {}).get("status", 0)
                    if status in (403, 429):
                        blocks += 1
                hits += 1
    except Exception:
        pass
    return {"requests": hits, "blocklike": blocks, "sample_urls": urls[-5:]}

def detect_px_state(driver) -> Dict[str, Any]:
    """
    Classify current PerimeterX/Human Security state on the page.
    Returns { state, evidence:{...} }
    """
    dom = _has_px_dom(driver)
    cookies = _px_cookies(driver)
    net = _px_net_in_logs(driver)

    # Determine state
    title = dom["block_title"]
    if (
        "access to this page has been denied" in title.casefold()
        or "px-captcha" in (dom["meta_desc"] or "").casefold()
        or dom["has_human_css"]
        or dom["has_digikey_block_logo"]
        or "big fans of robots" in (dom["captcha_header_text"] or "").casefold()
    ):
        state = "PX_BLOCK_PAGE"
    elif dom["challenge_dom"]:
        state = "PX_CHALLENGE_SHOWN"
    elif dom["app_id"] or cookies:
        # Library present; if we also see network calls to px endpoints, mark "silent"
        state = "PX_SILENT" if net["requests"] > 0 else "PX_PRESENT"
    else:
        state = "PX_NONE"

    return {
        "state": state,
        "evidence": {
            "title": title,
            "meta_desc": dom["meta_desc"],
            "app_id": dom["app_id"],
            "cookies": cookies,
            "net": net,
        },
    }

def _after_any_action_px_guard(driver, *, tag: str = "", settle_ms: int = 250) -> dict:
    """
    Post-action guard:
      - allow a short settle so overlays/redirects can render
      - inspect PX state; on challenge/block -> raise PXGuardTrip
    """
    if settle_ms > 0:
        time.sleep(settle_ms / 1000.0)

    px = detect_px_state(driver)  # your richer state machine
    state = px["state"]

    if state in ("PX_CHALLENGE_SHOWN", "PX_BLOCK_PAGE"):
        raise PXGuardTrip(
            f"PX guard tripped after action '{tag}': {state}",
            details=px
        )
    return px

# tiny helper
def slug(s: str) -> str:
    return "".join(c.lower() if c.isalnum() else "-" for c in s).strip("-")


def detect_px_block(driver: WebDriver) -> Dict[str, Any]:
    """
    Detects PerimeterX/Human Security 'Access to this page has been denied' pages.
    Returns a dict with detection details.

    Example return:
    {
        "blocked": True,
        "provider": "PerimeterX / Human Security",
        "signals": ["access-denied-title", "#px-captcha-wrapper present", "pxns script"],
        "reference_id": "d77fbfd0-8a91-11f0-bc45-af3974abeccf",
        "app_id": "PXlO2Z493J",
    }
    """
    signals: list[str] = []
    app_id = None
    ref_id = None

    # Grab page source early (works even if some JS fails)
    try:
        html = driver.page_source or ""
    except Exception:
        html = ""

    logger.debug(f"got page html: {html}")
    # 1) Title / text cues
    try:
        title = (driver.title or "").strip()
    except Exception:
        title = ""

    if "Access to this page has been denied" in title or "Access to this page has been denied" in html:
        signals.append("access-denied-title")

    if 'meta name="description" content="px-captcha"' in html or "px-captcha" in html:
        signals.append("meta-px-captcha")

    # 2) DOM markers specific to this challenge
    if re.search(r'id=["\']px-captcha-wrapper["\']', html):
        signals.append("#px-captcha-wrapper present")

    if re.search(r'<iframe[^>]+title=["\']Human verification challenge["\']', html, re.I):
        signals.append("captcha-iframe")

    if re.search(r'humanSecurity2\.css', html):
        signals.append("humanSecurity2.css")

    # 3) Known script URLs
    if re.search(r'/pxns/(?:d\.js|c\.\d+\.js)', html):
        signals.append("pxns script")

    if re.search(r'captcha\.px-cloud\.net|/captcha\.js\?a=c', html):
        signals.append("captcha script")

    logger.debug(f"signals found: {signals}")
    # 4) PerimeterX globals in window (if accessible)
    try:
        px = driver.execute_script(
            "return {appId: window._pxAppId || null, uuid: window._pxUuid || null, vid: window._pxVid || null};"
        ) or {}
        logger.debug(f"px: {px}")
        if px.get("appId"):
            app_id = px.get("appId")
            signals.append(f"_pxAppId={app_id}")
        if px.get("uuid"):
            ref_id = px.get("uuid")
    except Exception:
        pass
    logger.debug(f"ref_id: {ref_id}")
    # 5) Extract Reference ID from HTML fallback
    if not ref_id:
        m = re.search(r'Reference ID\s+([a-f0-9-]{20,})', html, re.I)
        if m:
            ref_id = m.group(1)

    logger.debug(f"final signals: {ref_id} {signals}")
    blocked = bool(signals)
    if blocked:
        driver.save_screenshot("digikey_blocked.png")

    return {
        "blocked": blocked,
        "provider": "PerimeterX / Human Security" if blocked else None,
        "signals": signals,
        "reference_id": ref_id,
        "app_id": app_id,
    }


class PXBlockDetected(RuntimeError):
    def __init__(self, info: dict):
        super().__init__(f"PerimeterX/HumanSecurity block detected: {info}")
        self.info = info

def _screenshot(driver, prefix="blocked", folder="snapshots"):
    Path(folder).mkdir(parents=True, exist_ok=True)
    path = Path(folder) / f"{prefix}-{int(time.time())}.png"
    try:
        driver.save_screenshot(str(path))
    except Exception:
        pass
    return path

def assert_not_blocked(driver):
    info = detect_px_block(driver)  # <-- your function
    if info.get("blocked"):
        shot = _screenshot(driver)
        logger.error("PX blocked; ref=%s app=%s shot=%s signals=%s",
                     info.get("reference_id"), info.get("app_id"), shot, info.get("signals"))
        raise PXBlockDetected(info)

@contextmanager
def step(driver, name: str, *, settle_ms: int = 250, screenshot_cb=None):
    """
    Wrap any interaction in `with step(driver, "desc"):` so we always run the PX post-action guard.
    On exceptions, we still run the guard to decide whether PX caused the failure.
    """
    try:
        yield
        # Normal success → check if PX popped right after the action
        _after_any_action_px_guard(driver, tag=name, settle_ms=settle_ms)

    except TimeoutException:
        # A wait failed. Was it actually PX showing up?
        try:
            _after_any_action_px_guard(driver, tag=f"{name} [after Timeout]", settle_ms=0)
        except PXGuardTrip as px:
            if screenshot_cb:
                screenshot_cb(f"px-trip__timeout__{name}")
            raise
        raise  # not PX-related, bubble up the original timeout

    except (ElementClickInterceptedException, WebDriverException):
        # Click got intercepted / generic Selenium err → check PX first
        try:
            _after_any_action_px_guard(driver, tag=f"{name} [after Selenium error]", settle_ms=0)
        except PXGuardTrip:
            if screenshot_cb:
                screenshot_cb(f"px-trip__selenium__{name}")
            raise
        raise  # not PX, re-raise

    except Exception:
        # Any other error → still see if PX just landed
        try:
            _after_any_action_px_guard(driver, tag=f"{name} [after Exception]", settle_ms=0)
        except PXGuardTrip:
            if screenshot_cb:
                screenshot_cb(f"px-trip__exception__{name}")
            raise
        raise

# ---- Convenience wrappers for common actions ----
def safe_get(driver, url: str, *, settle_ms: int = 250):
    with step(driver, f"GET {url}", settle_ms=settle_ms):
        driver.get(url)

def safe_click(driver, el: WebElement, desc: str = "click", *, settle_ms: int = 250):
    with step(driver, desc, settle_ms=settle_ms):
        el.click()

def safe_click_robust(driver,
                      el: WebElement,
                      desc: str = "click",
                      *,
                      settle_ms: int = 250):
    """
    Minimal-risk robust click:
      1) normal click
      2) scrollIntoView(center) and retry
      3) JS el.click()
      4) Dispatch MouseEvents via JS (mousedown/mouseup/click)
    Wrapped with PX guard via step().
    """
    with step(driver, desc, settle_ms=settle_ms):
        try:
            el.click()
            return
        except Exception:
            pass
        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center', inline:'center'});", el)
            time.sleep(0.05)
            el.click()
            return
        except Exception:
            pass
        try:
            driver.execute_script("arguments[0].click();", el)
            return
        except Exception:
            pass
        # Last resort: synthesize mouse events
        driver.execute_script(
            """
            (function(el){
              try{
                const ev = (t)=>new MouseEvent(t,{bubbles:true,cancelable:true,view:window});
                el.dispatchEvent(ev('mousedown'));
                el.dispatchEvent(ev('mouseup'));
                el.dispatchEvent(ev('click'));
                return true;
              }catch(e){ return false; }
            })(arguments[0]);
            """,
            el
        )

def _px_tick(driver, tag: str, *, settle_ms: int = 0):
    """Lightweight mid-action PX check (optional)."""
    _after_any_action_px_guard(driver, tag=tag, settle_ms=settle_ms)

def safe_send_keys(driver,
                   webelement: WebElement,
                   keys,
                   desc: str = "type",
                   *,
                   settle_ms: int = 200,
                   guard_mid: bool = False):
    with step(driver, desc, settle_ms=settle_ms):
        webelement.send_keys(keys)
        if guard_mid:
            _px_tick(driver, f"{desc} [after send_keys]")

def _resolve_element(driver,
                     target: Union[WebElement, Locator],
                     timeout: int = 10,
                     clickable: bool = False) -> WebElement:
    """Accepts a WebElement or a (By, locator) tuple and returns a visible element."""
    if isinstance(target, tuple):
        cond = EC.element_to_be_clickable(target) if clickable else EC.visibility_of_element_located(target)
        return WebDriverWait(driver, timeout).until(cond)
    return target


def _smooth_scroll_by(driver, total_dy: float, steps: int = 20, delay: float = 0.03):
    if steps < 1:
        steps = 1
    step_dy = total_dy / float(steps)
    for _ in range(steps):
        driver.execute_script("window.scrollBy(0, arguments[0]);", step_dy)
        # allow layout to settle a frame
        driver.execute_script("return window.requestAnimationFrame(() => {});")
        time.sleep(delay)

def safe_scroll(driver,
                to: str = "element",
                element: Optional[Union[WebElement, Locator]] = None,
                by: Optional[int] = None,
                block: str = "center",
                behavior: str = "smooth",
                desc: str = "scroll",
                *,
                settle_ms: int = 150,
                guard_mid: bool = False):
    """
    Scroll safely:
      - to="element" with element=...
      - to="top"/"bottom"
      - or by=<pixels> (positive=down, negative=up)
    """
    with step(driver, desc, settle_ms=settle_ms):
        # Helper to perform incremental scrolls for smooth visual motion


        # Smooth scrolling logic for different targets
        if by is not None:
            # Scroll by a specific offset in small increments
            total = int(by)
            steps = max(10, min(60, abs(total) // 100))  # more steps for larger distances
            _smooth_scroll_by(driver, total, steps=steps, delay=0.02)

        elif to == "top":
            current_y = driver.execute_script("return window.pageYOffset || document.documentElement.scrollTop || 0;") or 0
            total = -float(current_y)
            steps = max(20, min(80, int(abs(total) // 150)))
            _smooth_scroll_by(driver, total, steps=steps, delay=0.02)

        elif to == "bottom":
            current_y = driver.execute_script("return window.pageYOffset || document.documentElement.scrollTop || 0;") or 0
            max_y = driver.execute_script(
                "return Math.max(document.body.scrollHeight, document.documentElement.scrollHeight) - window.innerHeight;") or 0
            total = float(max_y) - float(current_y)
            steps = max(20, min(100, int(abs(total) // 150)))
            _smooth_scroll_by(driver, total, steps=steps, delay=0.02)

        else:
            # Scroll to the element's Y position smoothly
            el = _resolve_element(driver, element or (By.TAG_NAME, "body"), timeout=10)
            # Compute absolute Y we want to land at
            target_top = driver.execute_script("return arguments[0].getBoundingClientRect().top;", el)
            viewport_y = driver.execute_script("return window.pageYOffset || document.documentElement.scrollTop || 0;") or 0
            inner_h = driver.execute_script("return window.innerHeight;") or 0

            if block == "start":
                target_y = viewport_y + float(target_top)
            elif block == "end":
                target_y = viewport_y + float(target_top) - (inner_h - 1)
            else:  # center
                target_y = viewport_y + float(target_top) - (inner_h / 2.0)

            current_y = viewport_y
            total = float(target_y) - float(current_y)
            steps = max(20, min(80, int(abs(total) // 120)))
            _smooth_scroll_by(driver, total, steps=steps, delay=0.02)

        # Final settle
        driver.execute_script("return window.requestAnimationFrame(() => {});")
        time.sleep(0.05)
        if guard_mid:
            _px_tick(driver, f"{desc} [after scroll]")

def safe_input_text(driver,
                    target: Union[WebElement, Locator],
                    text: str,
                    *,
                    click_first: bool = True,
                    clear: str = "auto",   # "auto" | "keys" | "js" | "none"
                    method: str = "send_keys",  # "send_keys" | "js"
                    per_char_delay: Optional[Tuple[float, float]] = None,  # (min,max) seconds
                    desc: str = "type text",
                    settle_ms: int = 250,
                    guard_mid: bool = True) -> WebElement:
    """
    Types into inputs/contentEditable robustly.
    - clear="auto": try .clear(), fall back to Ctrl+A+Del, then JS if needed.
    - method="send_keys": normal typing (optionally human-like with per_char_delay).
    - method="js": set value via JS + dispatch input/change events.
    """
    with step(driver, desc, settle_ms=settle_ms):
        el = _resolve_element(driver, target, timeout=10, clickable=True)
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)

        if click_first:
            try:
                el.click()
            except Exception:
                driver.execute_script("arguments[0].click();", el)
            if guard_mid:
                _px_tick(driver, f"{desc} [after click]")

        # Clear
        if clear != "none":
            cleared = False
            if clear in ("auto", "keys"):
                try:
                    el.clear()
                    cleared = True
                except Exception:
                    pass
                if not cleared:
                    try:
                        el.send_keys(Keys.CONTROL + "a", Keys.DELETE)
                        cleared = True
                    except Exception:
                        pass
            if not cleared and clear in ("auto", "js"):
                try:
                    driver.execute_script("""
                        const el = arguments[0];
                        if ('value' in el) el.value = '';
                        if (el.isContentEditable) el.innerHTML = '';
                        el.dispatchEvent(new Event('input', {bubbles: true}));
                        el.dispatchEvent(new Event('change', {bubbles: true}));
                    """, el)
                except Exception:
                    pass

        # Input text
        if method == "js":
            driver.execute_script("""
                const el = arguments[0], val = arguments[1];
                if ('value' in el) el.value = val;
                else if (el.isContentEditable) el.textContent = val;
                el.dispatchEvent(new Event('input', {bubbles: true}));
                el.dispatchEvent(new Event('change', {bubbles: true}));
            """, el, text)
        else:
            if per_char_delay:
                lo, hi = per_char_delay
                for ch in text:
                    el.send_keys(ch)
                    time.sleep(random.uniform(lo, hi))
            else:
                el.send_keys(text)

        if guard_mid:
            _px_tick(driver, f"{desc} [after input]")
        return el  # chaining

def safe_exec_js(driver,
                 script: str,
                 *args,
                 desc: str = "exec js",
                 settle_ms: int = 0,
                 guard_mid: bool = True):
    """
    Execute a small JS snippet with arguments, wrapped with PX guard.
    Use this for simple execute_script calls. For injecting scripts, use safe_inject_js.
    """
    with step(driver, desc, settle_ms=settle_ms):
        res = driver.execute_script(script, *args)
        if guard_mid:
            _px_tick(driver, f"{desc} [after exec]", settle_ms=0)
        return res

def safe_inject_js(driver,
                   *,
                   src: Optional[str] = None,
                   inline: Optional[str] = None,
                   script_id: Optional[str] = None,
                   module: bool = False,
                   timeout: int = 10,
                   desc: str = "inject js",
                   settle_ms: int = 0,
                   guard_mid: bool = True):
    """
    Inject external script (src=...) and wait for load, or inject inline JS.
    Idempotent if script_id is provided (skips if element already present).
    """
    if not src and not inline:
        raise ValueError("Provide either src or inline JS to inject.")

    with step(driver, desc, settle_ms=settle_ms):
        # If already injected (by id), skip
        if script_id:
            exists = driver.execute_script("return !!document.getElementById(arguments[0]);", script_id)
            if exists:
                if guard_mid:
                    _px_tick(driver, f"{desc} [already present]")
                return True

        if src:
            ok = driver.execute_async_script("""
                const [src, scriptId, isModule, cb, toMs] = arguments;
                const done = (v) => cb(v);
                if (scriptId && document.getElementById(scriptId)) { done(true); return; }
                const s = document.createElement('script');
                s.src = src;
                if (scriptId) s.id = scriptId;
                if (isModule) s.type = 'module';
                let timer = setTimeout(() => { s.onload = s.onerror = null; done(false); }, toMs);
                s.onload = () => { clearTimeout(timer); done(true); };
                s.onerror = () => { clearTimeout(timer); done(false); };
                (document.head || document.documentElement).appendChild(s);
            """, src, script_id, bool(module), timeout * 1000)
            if guard_mid:
                _px_tick(driver, f"{desc} [after load]")
            return bool(ok)
        else:
            # Inline JS (synchronous)
            if script_id:
                driver.execute_script("""
                    const code = arguments[0], scriptId = arguments[1], isModule = arguments[2];
                    if (scriptId && document.getElementById(scriptId)) return;
                    const s = document.createElement('script');
                    if (scriptId) s.id = scriptId;
                    if (isModule) s.type = 'module';
                    s.textContent = code;
                    (document.head || document.documentElement).appendChild(s);
                """, inline, script_id, bool(module))
            else:
                driver.execute_script(inline)
            if guard_mid:
                _px_tick(driver, f"{desc} [after inline]")
            return True

def safe_wait(driver,
              target: Optional[Union[WebElement, Locator]] = None,
              *,
              condition: str = "visible",
              timeout: int = 10,
              poll: float = 0.2,
              text: Optional[str] = None,        # for condition="text"
              attribute: Optional[str] = None,   # for condition="attr"
              value: Optional[str] = None,       # for condition="attr"
              desc: Optional[str] = None,
              settle_ms: int = 150,
              guard_mid: bool = True):
    """
    General-purpose Selenium wait with PX guard.

    condition:
      - "present"      -> presence_of_element_located
      - "visible"      -> visibility_of_element_located / visibility_of
      - "clickable"    -> element_to_be_clickable (requires a locator OR enabled+displayed element)
      - "invisible"    -> invisibility_of_element_located / visibility_of(el)==False
      - "gone"         -> staleness_of(el) OR invisibility_of_element_located
      - "text"         -> text_to_be_present_in_element(_located)  (requires 'text')
      - "attr"         -> element attribute equals 'value'          (requires 'attribute' and 'value')

    Returns:
      - WebElement (for element-based conditions)
      - True/False for boolean conditions ("invisible", "gone", "text", "attr")
    """
    d = desc or f"wait {condition}"
    with step(driver, d, settle_ms=settle_ms):
        wait = WebDriverWait(driver, timeout, poll_frequency=poll)

        def resolve():
            # Build an ExpectedCondition based on what we got
            if condition == "present":
                if isinstance(target, tuple):
                    return wait.until(EC.presence_of_element_located(target))
                # If given a WebElement, assume it's already present
                return target

            if condition == "visible":
                if isinstance(target, tuple):
                    return wait.until(EC.visibility_of_element_located(target))
                return wait.until(EC.visibility_of(target))  # element

            if condition == "clickable":
                if isinstance(target, tuple):
                    return wait.until(EC.element_to_be_clickable(target))
                # For a WebElement, emulate: visible + enabled
                return wait.until(lambda drv: (target.is_displayed() and target.is_enabled()) and target or False)

            if condition == "invisible":
                if isinstance(target, tuple):
                    return wait.until(EC.invisibility_of_element_located(target))
                # For a WebElement, invisible means not displayed
                return wait.until(lambda drv: not target.is_displayed())

            if condition == "gone":
                if isinstance(target, tuple):
                    return wait.until(EC.invisibility_of_element_located(target))
                # For a WebElement, staleness is the safest "gone"
                return wait.until(EC.staleness_of(target))

            if condition == "text":
                if text is None:
                    raise ValueError("safe_wait(condition='text') requires 'text='.")
                if isinstance(target, tuple):
                    return wait.until(EC.text_to_be_present_in_element(target, text))
                return wait.until(lambda drv: text in (target.text or ""))

            if condition == "attr":
                if attribute is None or value is None:
                    raise ValueError("safe_wait(condition='attr') requires 'attribute=' and 'value='.")
                if isinstance(target, tuple):
                    return wait.until(lambda drv: (drv.find_element(*target).get_attribute(attribute) == value))
                return wait.until(lambda drv: target.get_attribute(attribute) == value)

            raise ValueError(f"Unknown condition: {condition!r}")

        result = resolve()
        if guard_mid:
            _px_tick(driver, f"{d} [resolved]", settle_ms=0)
        return result


def safe_wait_js(driver,
                 js_predicate: str,
                 *args,
                 timeout: int = 10,
                 poll: float = 0.25,
                 desc: str = "wait js",
                 settle_ms: int = 150,
                 guard_mid: bool = True):
    """
    Wait until a JS predicate returns truthy.
    `js_predicate` should be an expression or function body that returns a value.

    Example:
      safe_wait_js(driver, "return document.readyState === 'complete'")
      safe_wait_js(driver, "return window._done === true")
      safe_wait_js(driver, "return (arguments[0] > 3)", 5)
    """
    with step(driver, desc, settle_ms=settle_ms):
        wait = WebDriverWait(driver, timeout, poll_frequency=poll)
        # Normalize to an IIFE that returns a value
        code = js_predicate.strip()
        if not code.lower().startswith("return"):
            code = "return (" + code + ")"
        result = wait.until(lambda drv: drv.execute_script(code, *args))
        if guard_mid:
            _px_tick(driver, f"{desc} [resolved]", settle_ms=0)
        return result


# example usage:
# # 1) Scroll patterns
# safe_scroll(driver, to="top")
# safe_scroll(driver, to="bottom")
# safe_scroll(driver, by=800)  # down 800px
# safe_scroll(driver, element=(By.LINK_TEXT, "Wire Ducts, Raceways"))
#
# # 2) Type into a search box, with human-like typing
# safe_input_text(driver, (By.CSS_SELECTOR, "input[name='keywords']"),
#                 "barrel connector", per_char_delay=(0.03, 0.08))
#
# # 3) Set text via JS (for stubborn React inputs)
# safe_input_text(driver, (By.CSS_SELECTOR, "#qty"), "12", method="js")
#
# # 4) Inject a helper library once
# safe_inject_js(driver, src="https://example.com/helper.js", script_id="helper-js")
#
# # 5) Inject inline utility (idempotent)
# safe_inject_js(driver, inline="""
#   window._dbgLog = (...a) => console.log('[DBG]', ...a);
# """, script_id="dbg-inline")
# ====================== above all ai generated ======================

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


def _best_match(anchors, phrase: str):
    """Pick the best <a> whose visible label matches `phrase` (case-insensitive)."""
    want = phrase.strip().casefold()
    scored = []
    for a in anchors:
        try:
            lbl = _label_of(a)  # uses (a.text or "").strip()
        except StaleElementReferenceException:
            continue  # skip stale nodes
        low = lbl.casefold()
        score = (
            3 if low == want else
            2 if low.startswith(want) else
            1 if want in low else
            0
        )
        if score:
            scored.append((score, len(lbl), a, lbl))
    if not scored:
        return None, None
    scored.sort(key=lambda t: (-t[0], t[1]))  # higher score, then shorter label
    return scored[0][2], scored[0][3]         # (element, label)


def describe_element(el, max_html=3000):
    try:
        label = _label_of(el)  # your helper strips trailing “Items”
    except Exception:
        label = (el.text or "").strip()
    try:
        href = el.get_attribute("href") or ""
    except Exception:
        href = ""
    try:
        cls = el.get_attribute("class") or ""
    except Exception:
        cls = ""
    try:
        outer = el.get_attribute("outerHTML") or ""
        outer_short = (outer[:max_html] + "…") if len(outer) > max_html else outer
    except Exception:
        outer_short = ""
    return f"label='{label}' href='{href}' class='{cls}' outerHTML='{outer_short}'"


def format_elements(elems, max_items=10):
    lines = []
    # for i, el in enumerate(elems[:max_items]):
    for i, el in enumerate(elems):
        lines.append(f"[{i}] {describe_element(el)}")
    # if len(elems) > max_items:
    #     lines.append(f"... and {len(elems) - max_items} more")
    #     for i, el in enumerate(elems[-max_items:]):
    #         lines.append(f"[{i}] {describe_element(el)}")
    return "\n".join(lines)

def safe_big_scroll_down(driver, n_screen=10, guard_mid=False):
    viewport_height = driver.execute_script("return window.innerHeight;")
    n_screen = n_screen
    scroll_per_screen = 5
    _smooth_scroll_by(driver, viewport_height * n_screen, steps=n_screen*scroll_per_screen, delay=0.3)
    safe_scroll(driver, by=viewport_height * 30)

    driver.execute_script("return window.requestAnimationFrame(() => {});")
    time.sleep(0.05)
    if guard_mid:
        _px_tick(driver, f"big scroll [after scroll]")


def click_category_link_safe(driver, phrase: str, timeout: int = 20) -> bool:
    """
    Find and click a category/sub-category link by visible label using safe_* wrappers.
    Returns True if navigation succeeded (click or direct href).
    """
    # Wait for any category container first
    logger.debug(f"waiting for category container......")
    locator = (By.CSS_SELECTOR, "div[class*='categoryContainer']")
    safe_wait(driver, locator, condition="present", timeout=timeout, desc="wait category containers")

    logger.debug(f"Found category container......")

    viewport_height = driver.execute_script("return window.innerHeight;")

    safe_scroll(driver, by=viewport_height*30)

    # Scroll to the email input field at the bottom of the page.
    # email_input_locator = (By.CSS_SELECTOR, 'input.footer-email-input[placeholder="Enter your email"]')
    # safe_scroll(
    #     driver,
    #     to="element",
    #     element=email_input_locator,
    #     desc="scroll to footer email input"
    # )

    logger.debug(f"Scoll to bottom.....")

    # Locate target anchor
    with step(driver, f"locate link '{phrase}'"):
        anchors = driver.find_elements(
            By.XPATH,
            "//div[contains(@class,'categoryContainer')]"
            "//a[contains(@href,'/en/products/')]"
        )
        logger.debug(f"matching target {phrase}.{len(anchors)}.....{format_elements(anchors)}")
        for anchor in anchors:
            if "Regulator" in _label_of(anchor):
                print("Regulator found!!!:", _label_of(anchor))

        target, label = _best_match(anchors, phrase)

        # Fallback: search across the whole page if not inside the containers
        if not target:
            logger.debug("target not found!!!")
            anchors = driver.find_elements(By.XPATH, "//a[contains(@href,'/en/products/')]")
            target, label = _best_match(anchors, phrase)

        if not target:
            logger.debug("2nd target not found!!!")
            return False

    logger.debug(f"Target found!!! {target} {label}")
    # Bring into view
    logger.debug("scrolling to target ......")
    safe_scroll(driver, element=target, block="center", desc=f"scroll to '{label}'")

    # Click (with JS & href fallbacks)
    try:
        logger.debug("clicking on target ......")
        safe_click(driver, target, desc=f"click '{label}'")
        return True
    except Exception:
        pass

    # JS-click fallback
    try:
        with step(driver, f"JS click '{label}' fallback"):
            logger.debug("JS clicking on target ......")
            driver.execute_script("arguments[0].click();", target)
        return True
    except Exception:
        pass

    # Direct navigation as last resort
    href = target.get_attribute("href")
    if href:
        logger.debug(f"directly go to target href......{href}")
        safe_get(driver, href)
        return True

    return False

def _norm(s: str) -> str:
    """Loose, case/space-insensitive comparison key."""
    if s is None:
        return ""
    s = unicodedata.normalize("NFKC", s)
    s = s.casefold()
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _value_present_in_options(selected_value: str, options: List[Dict]) -> bool:
    want = _norm(selected_value)
    for opt in options or []:
        # tolerate dicts that may lack 'value' and only have 'label'
        val = opt.get("value") or opt.get("label")
        if _norm(str(val)) == want:
            return True
    return False

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


# -----------------------------
# DOM finders (robust to class churn)
# -----------------------------

def _find_filter_card(driver, header_text: str):
    """
    Return the root <div class='div-card'> for the filter with the given header text.
    Tries exact match first, then contains().
    """
    want = header_text.strip()
    # Quick wait for any filter grid/cards to exist
    locator = (By.CSS_SELECTOR, "div.div-card")
    safe_wait(driver, locator, condition="present", timeout=20, desc="wait filter cards")


    # 1) Exact header match
    xpath_exact = (
        ".//div[contains(@class,'div-card')][.//div[contains(@class,'cardHeader') and normalize-space() = %s]]"
    )
    cards = driver.find_elements(By.XPATH, xpath_exact % repr(want))
    if cards:
        return cards[0]

    # 2) Contains() fallback (case-insensitive via translate is messy; do two passes)
    xpath_contains = (
        ".//div[contains(@class,'div-card')][.//div[contains(@class,'cardHeader') and contains(normalize-space(), %s)]]"
    )
    cards = driver.find_elements(By.XPATH, xpath_contains % repr(want))
    if cards:
        return cards[0]

    # 3) Last resort: scan all headers and compare normalized text in Python
    for card in driver.find_elements(By.CSS_SELECTOR, "div.div-card"):
        try:
            header = card.find_element(By.XPATH, ".//div[contains(@class,'cardHeader')]").text
            if _norm(header) == _norm(want):
                return card
        except Exception:
            continue
    return None

def _get_search_input(card):
    """Return the 'Search Filter' input inside this card, if present."""
    inputs = card.find_elements(By.XPATH, ".//input[@placeholder='Search Filter']")
    return inputs[0] if inputs else None

def _get_scroll_outers(card):
    """
    Return (outer_scroll, inner_canvas) for the virtualized list.
    outer_scroll has overflow:auto; inner_canvas has huge height.
    """
    outer = None
    inner = None
    # Prefer data-testid markers when present
    try:
        outer = card.find_element(By.XPATH, ".//div[@data-testid='filter-box-outer-ref']//div[contains(@style,'overflow: auto')]")
    except Exception:
        pass
    if not outer:
        # Generic fallback: the first descendant div with overflow: auto
        outs = card.find_elements(By.XPATH, ".//div[contains(@style,'overflow: auto')]")
        outer = outs[0] if outs else None
    if outer:
        try:
            inner = outer.find_element(By.XPATH, ".//div[@data-testid='filter-box-inner-ref']")
        except Exception:
            # fallback: tallest child
            nodes = outer.find_elements(By.XPATH, ".//div")
            inner = max(nodes, key=lambda n: int(re.search(r"(\d+)", (n.value_of_css_property("height") or "0")).group(1)) if n else 0) if nodes else None
    return outer, inner

def _visible_option_nodes(card):
    """Return the current visible option <span> elements (the inner text node)."""
    # The clickable element is the outer span with data-testid ending in '-label-<id>'
    return card.find_elements(By.CSS_SELECTOR, "span[data-testid^='filter-'][data-testid*='-label-']")
    # return card.find_elements(By.CSS_SELECTOR, "span.tss-css-1w97wf3-options > span")

def _find_visible_option_by_text(card, target_text: str):
    want = _norm(target_text)
    # Elements in virtualized lists can go stale as the DOM re-renders during scroll/filtering.
    # Guard against StaleElementReferenceException and fall back to textContent when needed.
    for node in _visible_option_nodes(card):
        txt = ""
        try:
            txt = node.text or ""
        except StaleElementReferenceException:
            # Node detached between enumeration and text read; skip and continue
            continue
        except Exception:
            try:
                # Fallback to attribute read which can be more permissive in some cases
                txt = node.get_attribute("textContent") or ""
            except Exception:
                txt = ""
        if _norm(txt) == want:
            return node
    return None

def _scroll_and_probe_for_option(driver, card, target_text: str, max_jumps: int = 80) -> Optional[object]:
    """
    Virtual-scroll the list to find an option by text. Uses safe_inject_js to scroll outer.
    """
    outer, inner = _get_scroll_outers(card)
    if not outer:
        # No virtual scroller? Just try visible options again.
        return _find_visible_option_by_text(card, target_text)

    # Try from the top first
    safe_exec_js(driver, "arguments[0].scrollTop = 0;", outer, desc="scroll list top")
    time.sleep(0.05)
    found = _find_visible_option_by_text(card, target_text)
    if found:
        return found

    # Compute scroll metrics via JS
    scroll_h = safe_exec_js(driver, "return arguments[0].scrollHeight;", outer, desc="get scrollHeight")
    client_h = safe_exec_js(driver, "return arguments[0].clientHeight;", outer, desc="get clientHeight")
    if not scroll_h or not client_h:
        # fallback brute check
        for _ in range(12):
            safe_exec_js(driver, "arguments[0].scrollTop += 200;", outer, desc="scroll step")
            time.sleep(0.05)
            hit = _find_visible_option_by_text(card, target_text)
            if hit:
                return hit
        return None

    # Step proportionally (adaptive)
    step = max(int(client_h * 0.8), 120)
    pos = 0
    for _ in range(max_jumps):
        pos = min(pos + step, int(scroll_h) - int(client_h))
        safe_exec_js(driver, "arguments[0].scrollTop = arguments[1];", outer, pos, desc="scroll step abs")
        time.sleep(0.05)
        hit = _find_visible_option_by_text(card, target_text)
        if hit:
            return hit

    # Try the very bottom once
    safe_exec_js(driver, "arguments[0].scrollTop = arguments[0].scrollHeight;", outer, desc="scroll bottom")
    time.sleep(0.05)
    return _find_visible_option_by_text(card, target_text)

# -----------------------------
# Core setter
# -----------------------------

def _set_single_filter_value(driver, header: str, value: str, timeout: int = 20) -> bool:
    """
    Inside the filter card titled `header`, select option whose text == `value`.
    Returns True if it clicks something (or it detects the option already active); False if not found.
    """
    logger.debug("Setting filter '%s' to '%s'...", header, value)
    with step(driver, f"filter '{header}' = '{value}'"):
        card = _find_filter_card(driver, header)
        if not card:
            logger.warning("Card not found!!!")
            return False
        logger.debug("Card found!!!")
        # Bring card into view
        safe_scroll(driver, element=card, block="center", desc=f"scroll to '{header}' card")

        # Prefer the search box if present: it's fast and avoids virtual scroll
        search = _get_search_input(card)
        if search:
            # Clear & type, then wait for options to refresh
            safe_input_text(driver, search, value, clear="auto", desc=f"type '{value}' in '{header}' search")
            # wait for an option matching the value to be present
            try:
                safe_wait(
                    driver,
                    lambda: _find_visible_option_by_text(card, value) is not None,
                    timeout=10,
                    desc=f"wait option '{value}' visible in '{header}'"
                )
            except Exception:
                # fall through to scroll if search didn't filter it in
                pass

        # If visible now, great; otherwise virtual-scroll
        logger.debug("Checking if option '%s' is visible...", value)
        node = _find_visible_option_by_text(card, value) or _scroll_and_probe_for_option(driver, card, value)
        if not node:
            return False

        # Scroll the option into view (within the card) & click
        try:
            safe_scroll(driver, element=node, block="center", desc=f"scroll option '{value}' into view")
        except Exception:
            pass

        # Re-resolve the node after scrolling to avoid stale references
        try:
            node = _find_visible_option_by_text(card, value) or node
        except Exception:
            pass

        # Guard: do not try to click disabled options (common after a prior filter constrains results)
        def _is_disabled(n: WebElement) -> bool:
            try:
                return bool(safe_exec_js(
                    driver,
                    """
                    const el = arguments[0];
                    if (!el) return false;
                    const disabledAttr = el.getAttribute('data-disabled');
                    const ariaDis = el.getAttribute('aria-disabled');
                    const hasDisabled = el.hasAttribute('disabled');
                    const cls = (el.className || '');
                    const disabledClass = /options-disabled|disabled/i.test(cls);
                    return (disabledAttr === 'true') || hasDisabled || (ariaDis === 'true') || disabledClass;
                    """,
                    n,
                    desc=f"probe disabled '{value}' in '{header}'"
                ))
            except StaleElementReferenceException:
                # Attempt one refresh read
                refreshed = _find_visible_option_by_text(card, value)
                if not refreshed:
                    return False
                try:
                    return bool(safe_exec_js(
                        driver,
                        """
                        const el = arguments[0];
                        if (!el) return false;
                        const disabledAttr = el.getAttribute('data-disabled');
                        const ariaDis = el.getAttribute('aria-disabled');
                        const hasDisabled = el.hasAttribute('disabled');
                        const cls = (el.className || '');
                        const disabledClass = /options-disabled|disabled/i.test(cls);
                        return (disabledAttr === 'true') || hasDisabled || (ariaDis === 'true') || disabledClass;
                        """,
                        refreshed,
                        desc=f"probe disabled '{value}' in '{header}' (retry)"
                    ))
                except Exception:
                    return False
            except Exception:
                return False

        if _is_disabled(node):
            logger.warning("Option '%s' in '%s' appears disabled; skipping click.", value, header)
            return False

        # Click the inner label span (more reliable than the container)
        try:
            safe_click_robust(driver, node, desc=f"select '{value}' in '{header}'")
            return True
        except StaleElementReferenceException:
            # Refresh once and retry
            refreshed = _find_visible_option_by_text(card, value)
            if not refreshed:
                return False
            try:
                safe_click_robust(driver, refreshed, desc=f"select '{value}' in '{header}' (retry)")
                return True
            except Exception:
                return False
        except Exception:
            return False

# -----------------------------
# Public API
# -----------------------------


def apply_parametric_filters_safe(driver, filters: List[Dict], timeout: int = 20) -> List[Tuple[str, bool, str]]:
    """
    Apply a list of parametric filters:
      each item like {
        'label': 'Manufacturer',
        'type': 'select',
        'options': [{'label':'Altera','value':'Altera'}, ...],
        'selectedValue': 'Altera'
      }

    For each filter item:
      - if selectedValue is truthy AND is present in `options`, try to set it
      - otherwise skip (return reason)
    Returns a list of tuples: (label, applied_bool, reason)
    """
    try:
        logger.debug(f"AApplying filters: {filters}")
        results = []
        for f in filters or []:
            label = (f or {}).get("label") or ""
            sel   = (f or {}).get("selectedValue")
            opts  = (f or {}).get("options") or []
            logger.debug(f"label::: {label}, sel {sel}, opts {opts}")
            if not label:
                logger.warning("Missing label in filter: %s", f)
                results.append(("<missing label>", False, "no label"))
                continue

            if not sel:
                logger.warning("Missing selectedValue in filter: %s", f)
                results.append((label, False, "no selectedValue"))
                continue

            if not _value_present_in_options(str(sel), opts):
                logger.warning("Missing options in filter: %s", f)
                results.append((label, False, "selectedValue not in options (skipped)"))
                continue

            applied = _set_single_filter_value(driver, label, str(sel), timeout=timeout)
            results.append((label, bool(applied), "ok" if applied else "option not found / not clickable"))

            # After setting all filters, find and click the 'Apply All' button.
            try:
                logger.debug("Attempting to click 'Apply All' filters button...")
                apply_button_selector = (By.CSS_SELECTOR, "button[data-testid='apply-all-button']")
                apply_button = WebDriverWait(driver, timeout).until(
                    EC.element_to_be_clickable(apply_button_selector)
                )
                apply_button.click()
                logger.debug("'Apply All' button clicked. Waiting for page to update.")
                # Wait for the page to process the filters and reload the results.
                selenium_wait_for_page_load(driver)
                # Lightweight readiness wait (non-invasive)
                try:
                    safe_wait_js(driver, "return document.readyState==='complete'", timeout=min(10, timeout), desc="wait readyState complete")
                except Exception:
                    pass

                # quick hack only
                break
            except TimeoutException:
                logger.warning("'Apply All' button was not found or not clickable within the timeout period.")
                # Depending on the desired behavior, you might want to handle this case differently.
                # For now, we just log a warning and continue.
                pass
            except Exception as e:
                logger.error(f"An error occurred while trying to click 'Apply All': {get_traceback(e)}")
    except Exception as e:
        logger.error(f"An error applying pfs: {get_traceback(e)}")

    return results

import csv
import re
import time
from pathlib import Path
from typing import Dict, List, Tuple

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import sys
import subprocess
from utils.subprocess_helper import get_windows_creation_flags

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


START_URL = "https://www.digikey.com/en/products/filter/programmable-logic-ics/696"  # <-- put your results URL here
OUT_CSV = Path("digikey_results_dynamic_selenium.csv")
MAX_PAGES = 1         # set >1 to paginate
HEADLESS = True
PAGELOAD_TIMEOUT = 25
WAIT_TIMEOUT = 10

ROW_SELECTOR = ".SearchResults-productRow, .ProductResults .ProductRow, .SearchResults .ProductRow"

def _wait(driver, timeout: int = 10):
    return WebDriverWait(driver, timeout, poll_frequency=0.25, ignored_exceptions=(StaleElementReferenceException,))


def _visible(driver, css: str, timeout: int = 10):
    return _wait(driver, timeout).until(EC.visibility_of_element_located((By.CSS_SELECTOR, css)))


def _present(driver, css: str, timeout: int = 10):
    return _wait(driver, timeout).until(EC.presence_of_element_located((By.CSS_SELECTOR, css)))


def _visible_all(driver, css: str, timeout: int = 10):
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
            print("[OK] Accepted cookies (OneTrust)")
            time.sleep(0.2)
            return
    except Exception:
        pass
    # Generic accept button
    try:
        btns = driver.find_elements(By.XPATH, "//button[normalize-space()='Accept']")
        if btns:
            btns[0].click()
            print("[OK] Accepted cookies (generic)")
            time.sleep(0.2)
    except Exception:
        pass

def selenium_wait_for_results_container(driver, timeout_ms: int = 10000):
    logger.debug("selenium_wait_for_results_container.....")
    timeout = max(1, timeout_ms // 1000)
    selectors = [
        "div[data-testid='sb-container']",
        "#productSearchContainer, .SearchResults.ProductResults",
        ".SearchResults.ProductResults",
        ".SearchResults",
        ".ProductResults",
        ".SearchResults-productTable",
    ]
    logger.debug("ding ding ding.....")
    # Strategy 1: try in current context
    for sel in selectors:
        try:
            el = _visible(driver, sel, timeout=3)
            if el:
                logger.debug("Found results using strategy1")
                return el
        except Exception:
            pass
    logger.debug("Try using strategy2")
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
    logger.debug("Try using strategy3")
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
    svc = Service(ChromeDriverManager().install(), log_output=subprocess.DEVNULL)
    if sys.platform == "win32":
        try:
            svc.creationflags = get_windows_creation_flags()
        except Exception:
            pass
    driver = webdriver.Chrome(service=svc, options=chrome_opts)
    driver.set_page_load_timeout(PAGELOAD_TIMEOUT)
    return driver


def selenium_wait_for_page_load(driver):
    try:
        _wait(driver, 60).until(lambda d: d.execute_script("return document.readyState") == "complete")
    except TimeoutException:
        pass
    selenium_accept_cookies(driver)



def get_table_headers(driver) -> List[str]:
    """Extract the column headers in the exact order of TH elements.
    Do NOT skip empty headers to keep alignment with TDs.
    """
    headers: List[str] = []
    try:
        logger.debug("Extracting table headers (aligned with TH count)...")
        header_row = driver.find_element(By.CSS_SELECTOR, "tr[data-testid='Draggable Headers']")
        header_cells = header_row.find_elements(By.TAG_NAME, "th")

        for idx, cell in enumerate(header_cells):
            text_val = ""
            try:
                # Prefer label span text
                el = cell.find_element(By.CSS_SELECTOR, "div[data-testid='custom-header-label'] span")
                text_val = (el.text or "").strip()
            except Exception:
                text_val = ""

            # As a secondary hint, try to infer from data-testid if present (e.g., draggable-header--100)
            if not text_val:
                try:
                    dt = cell.get_attribute("data-testid") or ""
                    if dt:
                        text_val = dt
                except Exception:
                    pass

            headers.append(text_val)

        logger.info(f"Extracted {len(headers)} headers: {headers}")
    except Exception as e:
        logger.error(f"Could not extract table headers: {get_traceback(e)}")
    return headers


def _get_current_page_index(driver) -> Optional[int]:
    """Detect current page number from pagination (disabled numeric button)."""
    try:
        # Preferred: disabled numeric button indicates current page
        cur_btn = driver.find_elements(By.XPATH, "//div[@data-testid='pagination-container']//button[starts-with(@data-testid,'btn-page-') and @disabled]")
        if cur_btn:
            val = cur_btn[0].get_attribute("value") or cur_btn[0].text
            try:
                return int(str(val).strip())
            except Exception:
                return None
        # Fallback: tabindex='-1' often marks current page in MUI
        cur_btn = driver.find_elements(By.XPATH, "//div[@data-testid='pagination-container']//button[starts-with(@data-testid,'btn-page-') and @tabindex='-1']")
        if cur_btn:
            val = cur_btn[0].get_attribute("value") or cur_btn[0].text
            try:
                return int(str(val).strip())
            except Exception:
                return None
    except Exception:
        return None
    return None


def _click_next_page(driver, timeout: int = 15) -> bool:
    """Click the next page button and wait until page index increases. Returns True if page changed."""
    try:
        logger.debug("Clicking next page...")
        prev_idx = _get_current_page_index(driver)
        logger.debug(f"previous page index is...{prev_idx}")
        next_btns = driver.find_elements(By.XPATH, "//div[@data-testid='pagination-container']//button[@data-testid='btn-next-page']")
        if not next_btns:
            logger.debug("next button not found!!!...")
            return False
        next_btn = next_btns[0]
        # Try standard click; fallback to JS click
        try:
            logger.debug("next button found and clicking right now....")
            next_btn.click()
        except Exception:
            try:
                driver.execute_script("arguments[0].click();", next_btn)
            except Exception:
                return False

        # Wait for page index to change or rows to refresh
        def page_changed(drv):
            cur = _get_current_page_index(drv)
            return (prev_idx is None and cur is not None) or (cur is not None and prev_idx is not None and cur > prev_idx)

        try:
            WebDriverWait(driver, timeout).until(lambda d: page_changed(d))
            return True
        except Exception:
            # As a fallback, wait for table rows to go stale/refresh
            try:
                WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, "tr[class*='muwdap-tr'], tbody tr")))
            except Exception:
                pass
            # Check once more
            return page_changed(driver)
    except Exception:
        return False


def selenium_extract_search_results(driver, max_n: Optional[int] = None, max_pages: Optional[int] = None):
    """
    Extract results across multiple pages using pagination controls.
    - max_n: stop after collecting this many rows (if provided)
    - max_pages: limit number of pages to traverse (defaults to MAX_PAGES constant if present)
    Backward compatible with previous single-page behavior when limits are not provided.
    """
    try:
        limit_pages = max_pages if max_pages is not None else MAX_PAGES
        all_rows: List[Dict[str, str]] = []
        pages = 0

        while True:
            logger.debug("Parsing rows on current page...")
            rows, _ = parse_rows_on_page(driver)
            logger.debug(f"Found {len(rows)} rows on page {pages + 1}")

            if max_n is not None:
                need = max(0, max_n - len(all_rows))
                if need > 0:
                    all_rows.extend(rows[:need])
                # Stop early if reached desired count
                if len(all_rows) >= max_n:
                    break
            else:
                all_rows.extend(rows)

            pages += 1
            # Respect page limit if provided (or constant)
            if limit_pages and pages >= limit_pages:
                break

            # Try go to next page; stop if cannot
            if not _click_next_page(driver):
                break
            # Allow the next page to render content a bit before parsing
            try:
                WebDriverWait(driver, WAIT_TIMEOUT).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "tr[class*='muwdap-tr'], tbody tr"))
                )
            except Exception:
                pass
            time.sleep(0.3)

        logger.debug(f"Total rows collected: {len(all_rows)} across {pages} page(s)")
        print(f"extracted # of rows {len(all_rows)}")
        return all_rows
    except Exception as e:
        logger.error(f"Error during selenium_extract_search_results: {get_traceback(e)}")
        return []



def apply_search_results_sort_safe(driver, header_text: str, asc: bool) -> bool:
    """Find the column with given header_text and click its sort button.
    asc=True clicks the ascending button; asc=False clicks the descending button.
    Returns True if a click was performed and we observed a change; otherwise False.
    """
    try:
        logger.debug(f"Sorting search results on header '{header_text}' ascending={asc}")
        # Guard: ensure a real WebDriver instance is passed, not a module like selenium.webdriver
        # We avoid strict isinstance checks to support vendor-specific subclasses.
        if not hasattr(driver, "find_element") or not hasattr(driver, "execute_script"):
            logger.error(
                "apply_search_results_sort_safe: invalid driver passed (expected Selenium WebDriver), got %r",
                type(driver),
            )
            return False
        wait = WebDriverWait(driver, 10)

        # 1) Locate the header TH that contains an element whose normalized text == header_text
        header = wait.until(
            EC.presence_of_element_located(
                (By.XPATH, f"//th[.//*[normalize-space(text())='{header_text}']]")
            )
        )

        # Try to detect prior sort state via aria-sort if present
        try:
            before_sort = (header.get_attribute("aria-sort") or "").lower()
        except Exception as e:
            err_msg = get_traceback(e, "ErrorBeforeSort")
            logger.error(f"{err_msg}")
            before_sort = ""

        logger.debug(f"Header found!!!!!")
        # 2) Within the header, find the appropriate sort button
        # Primary: Digi-Key uses data-testid like sort--<id>-asc / sort--<id>-dsc
        testid_part = "-asc" if asc else "-dsc"
        sort_btn = None
        try:
            sort_btn = header.find_element(By.XPATH, f".//button[contains(@data-testid, '{testid_part}')]")
        except Exception:
            pass
        if sort_btn is None:
            # Fallback: class contains 'asc' / 'desc'
            btn_xpath = ".//button[contains(@class,'asc')]" if asc else ".//button[contains(@class,'desc')]"
            try:
                sort_btn = header.find_element(By.XPATH, btn_xpath)
            except Exception as e:
                err_msg = get_traceback(e, "ErrorSortBtn")
                logger.error(f"{err_msg}")
                # Last resort: any button inside header
                cand = header.find_elements(By.XPATH, ".//button")
                if not cand:
                    logger.warning("No sort button found inside header '%s'", header_text)
                    return False
                sort_btn = cand[0]

        # 3) Click sort
        logger.debug(f"Sort button found!!!!!")
        try:
            sort_btn.click()
        except Exception:
            driver.execute_script("arguments[0].click();", sort_btn)

        # 4) Wait for sort state to update (aria-sort change) or for rows to refresh
        def sort_changed(drv):
            try:
                cur = header.get_attribute("aria-sort")
            except Exception:
                cur = None
            if cur and cur != before_sort:
                return True
            # Fallback heuristic: table rows present (ensures DOM is ready)
            try:
                return bool(drv.find_elements(By.CSS_SELECTOR, "tr[class*='muwdap-tr'], tbody tr"))
            except Exception:
                return False

        try:
            WebDriverWait(driver, 10).until(lambda d: sort_changed(d))
        except Exception:
            pass

        logger.debug("Sort State Changed, sort click completed")
        return True
    except Exception as e:
        logger.error(f"Error during sorting search results: {get_traceback(e)}")
        return False


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
        # Prefer anchor directly if present, otherwise find by data-testid then closest ancestor anchor
        try:
            mpn_a = td.find_element(By.CSS_SELECTOR, "a[data-testid='data-table-product-number']")
        except Exception:
            mpn_label = td.find_element(By.CSS_SELECTOR, "[data-testid='data-table-product-number']")
            mpn_a = mpn_label.find_element(By.XPATH, "./ancestor::a[1]")
        out["MPN"] = clean_text(mpn_a.text)
        href = mpn_a.get_attribute("href")
        if href:
            out["Product URL"] = href if href.startswith("http") else f"https://www.digikey.com{href}"
    except Exception:
        pass

    # Manufacturer + URL
    try:
        try:
            mfr_a = td.find_element(By.CSS_SELECTOR, "a[data-testid='data-table-mfr-link']")
        except Exception:
            mfr_label = td.find_element(By.CSS_SELECTOR, "[data-testid='data-table-mfr-link']")
            mfr_a = mfr_label.find_element(By.XPATH, "./ancestor::a[1]")
        out["Manufacturer"] = clean_text(mfr_a.text)
        href = mfr_a.get_attribute("href")
        if href:
            out["Manufacturer URL"] = href if href.startswith("http") else f"https://www.digikey.com{href}"
    except Exception:
        pass

    # Datasheet URL (PDF icon link)
    try:
        # Avoid :has selector for broad compatibility; directly find the svg then nearest ancestor link
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
        std_src = img.get_attribute("data-standard-url")
        if src:
            out["Image URL"] = src if src.startswith("http") else f"https:{src}"
        if std_src:
            out["Image Standard URL"] = std_src if std_src.startswith("http") else f"https:{std_src}"
    except Exception:
        pass

    return out


def parse_rows_on_page(driver) -> Tuple[List[Dict[str, str]], List[str]]:
    rows_out: List[Dict[str, str]] = []
    dynamic_keys_in_order: List[str] = []

    # First, get the correct headers for all columns.
    headers = get_table_headers(driver)
    if not headers:
        logger.error("Could not retrieve table headers. Aborting parsing.")
        return rows_out, dynamic_keys_in_order
    # wait for row presence
    try:
        WebDriverWait(driver, WAIT_TIMEOUT).until(
            # EC.presence_of_element_located((By.CSS_SELECTOR, "tr[data-testid^='tr-']"))
            EC.presence_of_element_located((By.CSS_SELECTOR, "tr[class*='muwdap-tr'], tbody tr"))
        )
    except Exception as e:
        err_msg = get_traceback(e, "ErrorParseRowsOnPage")
        print("[WARNING] Rows not found; timed out", err_msg)
        return rows_out, dynamic_keys_in_order
    print("rows found...")
    # prefer specific class; fallback to generic
    # rows = driver.find_elements(By.CSS_SELECTOR, "tr[data-testid^='tr-']")
    rows = driver.find_elements(By.CSS_SELECTOR, "tr[class*='muwdap-tr'], tbody tr")
    print("driver found # of rows", len(rows))
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

            # Start with a stable fallback based on data-atag if available
            key = preferred_key(key_raw) if key_raw else f"col{j}"
            if j < len(headers):
                header = headers[j]
                # If header text is non-empty, prefer it; otherwise keep the fallback to avoid misalignment
                if header and header.strip():
                    key = header.strip()

            if key not in dynamic_keys_in_order:
                dynamic_keys_in_order.append(key)

            print("setting key:", key)
            # cell text with stale-safe retrieval
            val = ""
            try:
                # small retry to mitigate transient staleness
                for _ in range(2):
                    try:
                        val = clean_text(td.text)
                        break
                    except StaleElementReferenceException:
                        time.sleep(0.05)
                        continue
            except Exception:
                val = ""
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
            logger.debug(f"Found row: {row}")
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

# apply parametric filter and extract search results
def digi_key_selenium_search_component(driver, pfs, category_phrase, site_url):
    try:
        logger.debug("digi_key_selenium_search_component... accessing driver")
        selenium_wait_for_page_load(driver)
        logger.debug(f"clicking on category phrase... {category_phrase}")
        # click_category_link_safe(driver, category_phrase)
        logger.debug(f"wait for category page to full load...")
        selenium_wait_for_page_load(driver)
        logger.debug(f"applying pfs: {pfs}")
        filters_to_apply = [pfs] if isinstance(pfs, dict) else pfs
        applied_pfs = apply_parametric_filters_safe(driver, filters_to_apply)

        logger.debug(f"waiting for search results to show up completely......")
        # selenium_wait_for_results_container(driver)
        time.sleep(3)
        safe_big_scroll_down(driver)

        logger.debug(f"done big scroll......")

        logger.debug(f"after pfs extracting search results......")
        components_results = selenium_extract_search_results(driver)
        logger.debug(f"after pfs search results collected......{components_results}")
        results = {"status": "success", "components": components_results}

    except Exception as e:
        err_msg = get_traceback(e, "ErrorDigikeySeleniumSearchComponent")
        results = {"status": "failed", "error": err_msg, "components": []}

    return results

# apply column sort and re-extract after-sort table.
def digi_key_selenium_sort_and_extract_results(driver,  header, ascending, max_n):
    try:
        logger.debug("digi_key_selenium_sort_and_extract_results... accessing driver")
        apply_search_results_sort_safe(driver, header, ascending)

        logger.debug(f"waiting for search results to show up completely......")
        # selenium_wait_for_results_container(driver)
        time.sleep(3)
        safe_big_scroll_down(driver)

        logger.debug(f"sort finished, now extracting rows of results")

        logger.debug(f"after sort extracting search results......")
        components_results = selenium_extract_search_results(driver, max_n)
        logger.debug(f"after sort search results collected......{components_results}")
        results = {"status": "success", "components": components_results}

    except Exception as e:
        err_msg = get_traceback(e, "ErrorDigikeySeleniumSortAndExtractResults")
        logger.error(err_msg)
        results = {"status": "failed", "error": err_msg, "components": []}

    return results


if __name__ == "__main__":
    driver = setup_driver()
    extract_search_results_table(driver)
