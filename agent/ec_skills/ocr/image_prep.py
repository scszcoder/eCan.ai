
from agent.cloud_api.cloud_api import send_query_chat_request_to_cloud8, upload_file, req_cloud_read_screen, \
    upload_file8, req_cloud_read_screen8, send_query_chat_request_to_cloud, download_file, send_reg_steps_to_cloud
from agent.cloud_api.lan_api import req_lan_read_screen8
from datetime import datetime
import platform
import os
import subprocess
import io
import sys
import json
from utils.lazy_import import lazy
from utils.path_manager import path_manager
from agent.ec_skills.sys_utils.sys_utils import symTab

from utils.logger_helper import logger_helper as logger

_mac_screen_perm_prompted = False
screen_loc = (0, 0)

# ---- Minimal stubs for missing helpers (to be replaced with real implementations) ----
def get_top_visible_window(win_title_keyword: str):
    """
    Return (window_title, [x, y, w, h]) for the top visible window matching the keyword.
    Cross-platform with macOS/Windows specific implementations; fallback to full screen.
    """
    try:
        min_w, min_h = 300, 200
        if sys.platform == 'win32':
            try:
                import win32gui  # type: ignore
            except Exception:
                size = lazy.pyautogui.size()
                return (win_title_keyword or "", [0, 0, size[0], size[1]])

            candidates = []
            def _enum_handler(hwnd, _):
                if win32gui.IsWindowVisible(hwnd):
                    t = win32gui.GetWindowText(hwnd)
                    if t:
                        try:
                            l, tpy, r, b = win32gui.GetWindowRect(hwnd)
                            w = max(0, r - l)
                            h = max(0, b - tpy)
                            candidates.append((t, hwnd, w * h, [l, tpy, w, h]))
                        except Exception:
                            pass

            win32gui.EnumWindows(_enum_handler, None)

            # If keyword provided, pick first match; else pick the largest window above threshold
            if win_title_keyword:
                low = win_title_keyword.lower()
                for t, hwnd, area, rect in candidates:
                    if low in t.lower():
                        return (t, rect)
            # filter out tiny windows and pick largest by area
            large = [c for c in candidates if c[2] >= min_w * min_h]
            chosen = max(large, key=lambda x: x[2]) if large else (candidates[0] if candidates else None)
            if chosen:
                return (chosen[0], chosen[3])

            size = lazy.pyautogui.size()
            return (win_title_keyword or "", [0, 0, size[0], size[1]])

        elif sys.platform == 'darwin':
            try:
                from Quartz import CGWindowListCopyWindowInfo, kCGWindowListOptionOnScreenOnly, kCGNullWindowID  # type: ignore
            except Exception:
                size = lazy.pyautogui.size()
                return (win_title_keyword or "", [0, 0, size[0], size[1]])

            windows = CGWindowListCopyWindowInfo(kCGWindowListOptionOnScreenOnly, kCGNullWindowID)
            candidates = []
            for w in windows or []:
                title = w.get('kCGWindowName') or ''
                bounds = w.get('kCGWindowBounds') or {}
                x = int(bounds.get('X', 0))
                y = int(bounds.get('Y', 0))
                width = int(bounds.get('Width', 0))
                height = int(bounds.get('Height', 0))
                area = max(0, width) * max(0, height)
                owner = w.get('kCGWindowOwnerName') or ''
                # Filter out likely utility/system windows by tiny size
                candidates.append((title, owner, area, [x, y, width, height]))

            if win_title_keyword:
                kw = win_title_keyword.lower()
                for t, owner, area, rect in candidates:
                    if isinstance(t, str) and kw in t.lower():
                        return (t, rect)

            # pick the largest window above threshold
            large = [c for c in candidates if c[2] >= min_w * min_h]
            chosen = max(large, key=lambda x: x[2]) if large else (candidates[0] if candidates else None)
            if chosen:
                return (chosen[0], chosen[3])

            size = lazy.pyautogui.size()
            return (win_title_keyword or "", [0, 0, size[0], size[1]])

        else:
            size = lazy.pyautogui.size()
            return (win_title_keyword or "", [0, 0, size[0], size[1]])
    except Exception:
        try:
            size = lazy.pyautogui.size()
            return (win_title_keyword or "", [0, 0, size[0], size[1]])
        except Exception:
            return (win_title_keyword or "", [0, 0, 0, 0])


def findRef(ref_name, img_mark_up):
    """
    Find entries in img_mark_up whose name matches ref_name (or prefix match before '!').
    Expected return: list of dicts. Stub: simple filter on 'name'.
    """
    if not img_mark_up:
        return []
    results = []
    for item in img_mark_up:
        try:
            name = item.get("name", "")
            base = name.split("!")[0]
            if name == ref_name or base == ref_name:
                results.append(item)
        except Exception:
            continue
    return results


def findBoundBox(boxes):
    """
    Merge multiple boxes into a bounding box.
    Input boxes expected as [top, left, bottom, right] or [left, top, right, bottom].
    Stub: tries to handle both by inferring min/max.
    Returns [left, top, right, bottom].
    """
    if not boxes:
        return [0, 0, 0, 0]
    # Normalize and merge
    lefts, tops, rights, bottoms = [], [], [], []
    for b in boxes:
        if not isinstance(b, (list, tuple)) or len(b) < 4:
            continue
        # Heuristic: if b[0] < b[2] and b[1] < b[3] it's [top,left,bottom,right], else try [left,top,right,bottom]
        if b[0] <= b[2] and b[1] <= b[3]:
            top, left, bottom, right = b[0], b[1], b[2], b[3]
        else:
            left, top, right, bottom = b[0], b[1], b[2], b[3]
        lefts.append(int(left))
        tops.append(int(top))
        rights.append(int(right))
        bottoms.append(int(bottom))
    if not lefts:
        return [0, 0, 0, 0]
    return [min(lefts), min(tops), max(rights), max(bottoms)]


def check_macos_screen_recording_permission():
    """
    Check macOS screen recording permission.
    Returns: (has_permission: bool, app_name: Optional[str], python_path: str)
    """
    if platform.system() != "Darwin":
        return True, None, sys.executable

    python_path = sys.executable

    # Method 1: Native API if available
    try:
        from Quartz import CGPreflightScreenCaptureAccess  # type: ignore
        ok = CGPreflightScreenCaptureAccess()
        if ok:
            logger.info("macOS screen recording permission granted (native API)")
            return True, None, python_path
    except Exception as e:
        logger.debug(f"Native permission check unavailable: {e}")

    # Method 2: screencapture tiny region
    try:
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
            tmp_path = tmp.name
        try:
            result = subprocess.run(
                ['screencapture', '-x', '-R', '0,0,1,1', tmp_path],
                capture_output=True,
                timeout=2
            )
            if result.returncode == 0 and os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
                logger.info("macOS screen recording permission granted (screencapture)")
                os.unlink(tmp_path)
                return True, None, python_path
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
    except Exception as e:
        logger.debug(f"screencapture test failed: {e}")

    # Method 3: pyautogui tiny screenshot
    try:
        test_img = lazy.pyautogui.screenshot(region=(0, 0, 1, 1))
        if test_img and test_img.size[0] > 0 and test_img.size[1] > 0:
            logger.info("macOS screen recording permission granted (pyautogui)")
            return True, None, python_path
    except Exception as e:
        logger.debug(f"pyautogui permission test failed: {e}")

    # Determine app name for guidance
    app_name = "Python"
    try:
        if getattr(sys, 'frozen', False):
            app_name = "eCan"
        else:
            if 'TERM_PROGRAM' in os.environ:
                term_program = os.environ['TERM_PROGRAM']
                tl = term_program.lower()
                if 'cursor' in tl:
                    app_name = "Cursor"
                elif 'vscode' in tl:
                    app_name = "Visual Studio Code"
                elif 'pycharm' in tl:
                    app_name = "PyCharm"
            if 'Cursor' in python_path:
                app_name = "Cursor"
            elif 'Visual Studio Code' in python_path or 'VSCode' in python_path:
                app_name = "Visual Studio Code"
            elif 'PyCharm' in python_path:
                app_name = "PyCharm"
            elif '/Library/Frameworks/Python.framework' in python_path:
                app_name = "Python (Official)"
            else:
                app_name = f"Python ({os.path.basename(python_path)})"
    except Exception as e:
        logger.debug(f"Failed to detect app name: {e}")

    return False, app_name, python_path


def show_macos_permission_guide(app_name: str, python_path: str):
    """Show macOS screen recording permission setup guide."""
    try:
        logger.error("=" * 80)
        logger.error("macOS Screen Recording Permission Not Granted!")
        logger.error("=" * 80)
        logger.error("")
        logger.error("IMPORTANT: You need to authorize THIS executable:")
        logger.error(f"   {python_path}")
        logger.error("")
        logger.error("Steps:")
        logger.error("1) System Settings → Privacy & Security → Screen Recording")
        logger.error(f"2) Find '{app_name}' and check the box")
        logger.error("3) If not listed, click '+' and add the app or the Python executable above")
        logger.error("4) Restart this process after granting permission")
        logger.error("")
        logger.error("which python3  # Should match the path above")
        logger.error("")
        try:
            subprocess.run(['open', 'x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture'],
                           check=False, timeout=2)
            logger.info("System Settings opened")
        except Exception:
            pass
    except Exception:
        # Best-effort logging only
        pass

# given a list anchor info in img_mark_up, and given area_spec which is list of anchors
# carve out a subimage of the original "img" which is the boundbox formed the
# list of area_spec anchors.
# area_spec will be the same as defined in CSK
# assumes: the boundbox defining anchors are unique on the image
def carveOutImage(img0, area_spec, img_mark_up):
    subimage = img0
    if area_spec:
        if "sub_refs" in area_spec:
            ref_names = [ref["ref"] for ref in area_spec["sub_refs"]]
            refs = []
            for ref_name in ref_names:
                ref = findRef(ref_name, img_mark_up)
                if ref:
                    refs.append(ref[0])
            ref_boxes = [r["loc"] for r in refs]
            print(f"ref boxes: {ref_boxes}")

            if len(ref_boxes) >=2:
                subArea = findBoundBox(ref_boxes)
                if subArea[0] < subArea[2] and subArea[1] < subArea[3]:
                    print(f"Carve out {subArea}")
                    subimage = img0.crop(subArea)

    return subimage

# given a list anchor info in img_mark_up, and given area_spec which is list of anchors
# mask out (smear with all black or all white) a sub-section of the original "img" which
# is the boundbox formed the  list of area_spec anchors.
# area_spec will be the same as defined in CSK
# loc in T, L, B, R
def maskOutImage(img, area_spec, img_mark_up):
    for mask in area_spec["masks"]:
        ref = findRef(mask["ref"], img_mark_up)
        if ref:
            ref = ref[0]
            box_height = ref["loc"][2] - ref["loc"][0]
            box_width = ref["loc"][3] - ref["loc"][1]
            if ref["side"] == "bottom":
                top = ref["loc"][2] + ref["voffset"]*box_height
                bottom = top + ref["height"]*box_height
                left = ref["loc"][0] + ref["hoffset"]*box_width
                right = left + ref["width"] * box_width
            elif ref["side"] == "top":
                bottom = ref["loc"][0] - ref["voffset"] * box_height
                top = bottom - ref["height"] * box_height
                left = ref["loc"][0] + ref["hoffset"] * box_width
                right = left + ref["width"] * box_width
            elif ref["side"] == "left":
                top = ref["loc"][0] + ref["voffset"] * box_height
                bottom = top + ref["height"] * box_height
                right = ref["loc"][1] - ref["hoffset"] * box_width
                left = right - ref["width"] * box_width
            elif ref["side"] == "right":
                top = ref["loc"][0] + ref["voffset"] * box_height
                bottom = top + ref["height"] * box_height
                left = ref["loc"][3] + ref["hoffset"] * box_width
                right = left + ref["width"] * box_width

            print(f"mask left, top, right, bottom: {[left, top, right, bottom]}")
            # Define the area to black out (x1, y1) -> (x2, y2)
            # x1, y1 = 50, 50  # Top-left corner
            # x2, y2 = 200, 200  # Bottom-right corner

            # Make the region black
            img[left:top, right:bottom] = (0, 0, 0)


def _captureScreenWithCommand(win_title_keyword, subArea=None):
    """
    Capture screen using macOS screencapture command (inherits Terminal/IDE permission)
    Returns: (image, image_bytes, window_rect)
    """
    import tempfile
    from PIL import Image
    import io

    # Get window info
    if win_title_keyword:
        window_name, window_rect = get_top_visible_window(win_title_keyword)
    else:
        logger.info("capture default top window")
        window_name, window_rect = get_top_visible_window("")

    # Validate window_rect
    if not window_rect or len(window_rect) < 4:
        logger.error(f"Invalid window_rect: {window_rect}, using full screen")
        screen_size = lazy.pyautogui.size()
        window_rect = [0, 0, screen_size[0], screen_size[1]]

    # Create temp file for screenshot
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
        tmp_path = tmp.name

    try:
        # Capture with region if specified
        x, y, w, h = window_rect[0], window_rect[1], window_rect[2], window_rect[3]

        # screencapture -R x,y,w,h captures a region
        cmd = ['screencapture', '-x', '-R', f'{x},{y},{w},{h}', tmp_path]
        result = subprocess.run(cmd, capture_output=True, timeout=3)

        logger.debug(f"screencapture region cmd: {' '.join(cmd)}")
        logger.debug(f"screencapture returncode: {result.returncode}")
        logger.debug(f"screencapture stderr: {result.stderr.decode('utf-8') if result.stderr else 'none'}")
        logger.debug(
            f"File exists: {os.path.exists(tmp_path)}, Size: {os.path.getsize(tmp_path) if os.path.exists(tmp_path) else 0}")

        if result.returncode != 0 or not os.path.exists(tmp_path) or os.path.getsize(tmp_path) == 0:
            # Fallback to full screen
            logger.warning(f"Region capture failed (rc={result.returncode}), trying full screen...")
            cmd = ['screencapture', '-x', tmp_path]
            result = subprocess.run(cmd, capture_output=True, timeout=3)

            logger.debug(f"screencapture fullscreen returncode: {result.returncode}")
            logger.debug(
                f"screencapture fullscreen stderr: {result.stderr.decode('utf-8') if result.stderr else 'none'}")
            logger.debug(
                f"File exists: {os.path.exists(tmp_path)}, Size: {os.path.getsize(tmp_path) if os.path.exists(tmp_path) else 0}")

            if result.returncode == 0 and os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
                # Update window_rect to full screen
                im = Image.open(tmp_path)
                window_rect = [0, 0, im.size[0], im.size[1]]
            else:
                logger.error(
                    f"screencapture command failed: returncode={result.returncode}, stderr={result.stderr.decode('utf-8') if result.stderr else 'none'}")

        # Load and return image
        if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
            im = Image.open(tmp_path)

            # Convert to bytes
            img_byte_arr = io.BytesIO()
            im.save(img_byte_arr, format='PNG')
            image_bytes = img_byte_arr.getvalue()

            logger.info(f"✅ screencapture command succeeded: {im.size}")

            # Apply subArea if specified
            if subArea and len(subArea) == 4:
                x1, y1, x2, y2 = subArea
                im = im.crop((x1, y1, x2, y2))
                img_byte_arr = io.BytesIO()
                im.save(img_byte_arr, format='PNG')
                image_bytes = img_byte_arr.getvalue()

            return im, image_bytes, window_rect
        else:
            raise RuntimeError("screencapture produced empty file")
    finally:
        # Clean up temp file
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def captureScreen(win_title_keyword, subArea=None):
    global screen_loc
    logger.info(
        ">>>>>>>>>>>>>>>>>>>>>screen read time stamp1BX: " + datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3])

    # Check macOS screen recording permission first
    has_permission, app_name, python_path = check_macos_screen_recording_permission()
    if not has_permission:
        # Show guide only once per process
        global _mac_screen_perm_prompted
        if not _mac_screen_perm_prompted:
            show_macos_permission_guide(app_name, python_path)
            _mac_screen_perm_prompted = True

        # Try screencapture command first on macOS (inherits parent process permission)
        if platform.system() == "Darwin":
            logger.info("⚡ Trying screencapture command (uses Terminal/IDE permission)...")
            try:
                return _captureScreenWithCommand(win_title_keyword, subArea)
            except Exception as e:
                logger.warning(f"screencapture fallback failed: {e}, trying pyautogui...")
        else:
            logger.warning("⚠️  Screenshot may fail without permission")

    if win_title_keyword:
        window_name, window_rect = get_top_visible_window(win_title_keyword)
    else:
        logger.info("capture default top window")
        window_name, window_rect = get_top_visible_window("")

    # Validate window_rect before using it
    if not window_rect or len(window_rect) < 4:
        logger.error(f"ERROR: Invalid window_rect: {window_rect}, using full screen as fallback")
        screen_size = lazy.pyautogui.size()
        window_rect = [0, 0, screen_size[0], screen_size[1]]

    # Validate window_rect values are positive and reasonable
    if window_rect[2] <= 0 or window_rect[3] <= 0:
        logger.error(f"ERROR: Invalid window dimensions (w={window_rect[2]}, h={window_rect[3]}), using full screen")
        screen_size = lazy.pyautogui.size()
        window_rect = [0, 0, screen_size[0], screen_size[1]]

    # now we have obtained the top window, take a screen shot , region is a 4-tuple of  left, top, width, and height.
    im0 = None
    max_retries = 3

    for attempt in range(max_retries):
        try:
            # Try to capture with the specified region
            im0 = lazy.pyautogui.screenshot(region=(window_rect[0], window_rect[1], window_rect[2], window_rect[3]))

            # Validate the captured image
            if im0 is None or im0.size[0] == 0 or im0.size[1] == 0:
                raise ValueError(f"Captured image has invalid size: {im0.size if im0 else 'None'}")

            # Successfully captured
            logger.info(f"Successfully captured screenshot: {im0.size}")
            break

        except Exception as e:
            logger.warning(f"Screenshot attempt {attempt + 1}/{max_retries} failed: {e}")

            if attempt < max_retries - 1:
                # Try with full screen on next attempt
                screen_size = lazy.pyautogui.size()
                window_rect = [0, 0, screen_size[0], screen_size[1]]
                logger.info(f"Retrying with full screen: {window_rect}")
            else:
                # Last attempt failed, try alternative methods
                logger.error("All pyautogui attempts failed, trying alternative methods")

                # Alternative 1: Try pyautogui full screen
                try:
                    im0 = lazy.pyautogui.screenshot()
                    if im0 and im0.size[0] > 0 and im0.size[1] > 0:
                        logger.info(f"✅ Alternative pyautogui succeeded: {im0.size}")
                        window_rect = [0, 0, im0.size[0], im0.size[1]]
                        break
                except Exception as e2:
                    logger.debug(f"Alternative pyautogui failed: {e2}")

                # Alternative 2: Try macOS screencapture command (most reliable on macOS)
                if platform.system() == "Darwin":
                    try:
                        import tempfile
                        from PIL import Image
                        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                            tmp_path = tmp.name
                        try:
                            # Use screencapture with full screen
                            result = subprocess.run(
                                ['screencapture', '-x', tmp_path],
                                capture_output=True,
                                timeout=3
                            )
                            if result.returncode == 0 and os.path.exists(tmp_path):
                                im0 = Image.open(tmp_path)
                                if im0 and im0.size[0] > 0 and im0.size[1] > 0:
                                    logger.info(f"✅ screencapture command succeeded: {im0.size}")
                                    window_rect = [0, 0, im0.size[0], im0.size[1]]
                                    os.unlink(tmp_path)
                                    break
                            if os.path.exists(tmp_path):
                                os.unlink(tmp_path)
                        except Exception:
                            if os.path.exists(tmp_path):
                                os.unlink(tmp_path)
                            raise
                    except Exception as e3:
                        logger.debug(f"screencapture command failed: {e3}")

                # All methods failed
                logger.error(f"All screenshot methods failed")
                raise RuntimeError(f"Failed to capture screenshot after {max_retries} attempts: {e}") from e

    if im0 is None:
        raise RuntimeError("Failed to capture screenshot: image is None")

    if subArea:
        subimage = im0.crop(subArea)
    else:
        subimage = im0

    # Convert the PIL Image to bytes (in memory, no disk write)
    image_io = io.BytesIO()
    subimage.save(image_io, format="PNG")  # Convert image to PNG format
    image_bytes = image_io.getvalue()

    screen_loc = (window_rect[0], window_rect[1])
    return subimage, image_bytes, screen_loc


def saveImageToFile(img, sfile, fformat):
    if sfile:
        if not os.path.exists(os.path.dirname(sfile)):
            os.makedirs(os.path.dirname(sfile))

        img.save(sfile)
    else:
        logger.warning("File name not specified; skipping image save.")


# win_title_keyword == "" means capture the entire screen
def captureScreenToFile(win_title_keyword, sfile, subarea=None, fformat='png'):
    subimage, image_bytes, window_rect = captureScreen(win_title_keyword, subarea)
    saveImageToFile(subimage, sfile, fformat)

    return subimage, image_bytes, window_rect


def takeScreenShot(win_title_keyword, subArea=None):
    global screen_loc
    logger.info(
        ">>>>>>>>>>>>>>>>>>>>>screen read time stamp1BBX: " + datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3])
    if win_title_keyword:
        window_name, window_rect = get_top_visible_window(win_title_keyword)
    else:
        logger.info("capture default top window")
        window_name, window_rect = get_top_visible_window("")

    # Validate window_rect before using it
    if not window_rect or len(window_rect) < 4:
        logger.error(f"ERROR: Invalid window_rect: {window_rect}, using full screen as fallback")
        screen_size = lazy.pyautogui.size()
        window_rect = [0, 0, screen_size[0], screen_size[1]]

    # now we have obtained the top window, take a screen shot , region is a 4-tuple of  left, top, width, and height.
    im0 = lazy.pyautogui.screenshot(region=(window_rect[0], window_rect[1], window_rect[2], window_rect[3]))

    return im0, window_rect


# win_title_keyword == "" means capture the entire screen
async def readRandomWindow8(mission, win_title_keyword, log_user, session, token):
    dtnow = datetime.now()
    date_word = dtnow.strftime("%Y%m%d")
    dt_string = str(int(dtnow.timestamp()))
    logger.info("date string:" + dt_string)

    fdir = path_manager.get_log_path(log_user, date_word, "b0m0/any_any_any_any/skills/any/images")
    image_file = os.path.join(fdir, f"scrn_{dt_string}.png")

    # Ensure directory exists
    path_manager.ensure_directory_exists(image_file)

    screen_img, img_bytes, window_rect = captureScreenToFile(win_title_keyword, image_file)
    # "imageFile": "C:/Users/***/PycharmProjects/ecbot/resource/runlogs/20240328/b0m0/any_any_any_any/skills/any/images/*.png"
    # shutil.copy(source_file, image_file)
    return await cloudAnalyzeRandomImage8(mission, screen_img, image_file, screen_img, session, token)


async def readScreen8(win_title_keyword, site_page, page_sect, page_theme, layout, mission, sk_settings, sfile, options,
                      factors):
    settings = mission.main_win_settings
    mainwin = mission.get_main_win()
    screen_img, img_bytes, window_rect = captureScreenToFile(win_title_keyword, sfile)

    session = settings["session"]
    token = settings["token"]
    mid = mission.getMid()
    bid = mission.getBid()
    image_file = sfile

    result = await cloudAnalyzeImage8(image_file, screen_img, img_bytes, site_page, page_sect, page_theme, layout, mid,
                                      bid, sk_settings, options, factors, session, token, mission)
    return result


# image_file *.png must be put in the following diretory
# "imageFile": "C:/Users/***/PycharmProjects/ecbot/resource/runlogs/20240328/b0m0/any_any_any_any/skills/any/images/*.png"
async def cloudAnalyzeRandomImage8(mission, screen_image, image_file, image_bytes, session, token):
    settings = mission.main_win_settings
    mainwin = mission.get_main_win()
    sk_settings = {
        "platform": "any",
        "app": "any",
        "site": "any",
        "skname": "any",
        "skfname": "resource/skills/public/any_any_any_any/any.psk",
        "display_resolution": mainwin.config_manager.general_settings.display_resolution,
        "wan_api_key": mainwin.config_manager.general_settings.ocr_api_key
    }
    logger.debug("Skill settings prepared for random image analysis: %s", sk_settings)
    return await cloudAnalyzeImage8(image_file, screen_image, image_bytes, "any", "any", "", "", 0, 0, sk_settings, "",
                                    "{}", session, token, mission)


async def cloudAnalyzeImage8(img_file, screen_image, image_bytes, site_page, page_sect, page_theme, layout, mid, bid,
                             sk_settings, options, factors, session, token, mission):
    logger.info(
        ">>>>>>>>>>>>>>>>>>>>>screen read time stamp1BXXX: " + datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3])
    mwin = mission.get_main_win()
    network_api_engine = mwin.getNetworkApiEngine()
    if network_api_engine == "lan":
        img_endpoint = mwin.getLanOCREndpoint()
        logger.info("Using LAN OCR endpoint: %s", img_endpoint)
    else:
        img_endpoint = mwin.getWanApiEndpoint()

    # upload screen to S3
    if network_api_engine == "wan":
        await upload_file8(session, img_file, token, mwin.getWanApiEndpoint(), "screen")

    full_width, full_height = screen_image.size

    m_skill_names = [sk_settings["skname"]]
    m_psk_names = [sk_settings["skfname"]]
    csk_name = sk_settings["skfname"].replace("psk", "csk")
    m_csk_names = [csk_name]

    logger.info(
        ">>>>>>>>>>>>>>>>>>>>>screen read time stamp1C: " + datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3])

    # request an analysis of the uploaded screen
    # some example options usage:
    # Note: options is a global variable name that actually contains the options json string as shown below:
    # "options": "{\"info\": [{\"info_name\": \"label_row\", \"info_type\": \"lines 1\", \"template\": \"2\", \"ref_method\": \"1\", \"refs\": [{\"dir\": \"right inline\", \"ref\": \"entries\", \"offset\": 0, \"offset_unit\": \"box\"}]}]}",
    # basically let a user to modify csk file by appending some user defined way to extract certain information element.

    request = [{
        "mid": mid,
        "bid": bid,
        "os": sk_settings["platform"],
        "app": sk_settings["app"],
        "domain": sk_settings["site"],
        "page": site_page,
        "layout": layout,
        "skill": m_skill_names[0],
        "psk": m_psk_names[0].replace("\\", "\\\\"),
        "csk": m_csk_names[0].replace("\\", "\\\\"),
        "lastMove": page_sect,
        "options": "",
        "theme": page_theme,
        "imageFile": img_file.replace("\\", "\\\\"),
        "factor": factors
    }]

    if options != "":
        if isinstance(symTab[options], str):
            request[0]["options"] = symTab[options]
        elif isinstance(symTab[options], dict):
            if "txt_attention_area" in symTab[options]:
                symTab[options]["txt_attention_area"] = [int(symTab[options]["txt_attention_area"][0] * full_width),
                                                         int(symTab[options]["txt_attention_area"][1] * full_height),
                                                         int(symTab[options]["txt_attention_area"][2] * full_width),
                                                         int(symTab[options]["txt_attention_area"][3] * full_height)]

            if "icon_attention_area" in symTab[options]:
                symTab[options]["icon_attention_area"] = [int(symTab[options]["icon_attention_area"][0] * full_width),
                                                          int(symTab[options]["icon_attention_area"][1] * full_height),
                                                          int(symTab[options]["icon_attention_area"][2] * full_width),
                                                          int(symTab[options]["icon_attention_area"][3] * full_height)]

            if "display_resolution" not in symTab[options]:
                symTab[options]["display_resolution"] = sk_settings["display_resolution"]

            request[0]["options"] = json.dumps(symTab[options]).replace('"', '\\"')
    else:
        # txt_attention_area is a list of 4 numbers: left, top, right, bottom which defines the area to pay extra attention on the cloud side.
        # attention_targets is a list of text strings to find in the attention area. this whole attention scheme is about using more
        # robust image to text algorithms on the cloud side to get a better reading of the results. The downside is the image process time
        # is long, so limiting only certain area of the image helps keep speed in tact. Usually we home in on right half of the screen.
        # or center half of the screen.
        half_width = int(full_width / 2)
        half_height = int((full_height) / 2)
        request[0]["options"] = json.dumps({"display_resolution": sk_settings["display_resolution"],
                                            "txt_attention_area": [half_width, 0, full_width, full_height],
                                            "attention_targets": ["OK"]}).replace('"', '\\"')

    logger.info(
        ">>>>>>>>>>>>>>>>>>>>>screen read time stamp1D: " + datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3])

    local_info = {
        "user": mwin.getUser(),
        "host_name": mwin.getHostName(),
        "ip": mwin.getIP()
    }

    imgs = [
        {
            "file_name": img_file,
            "bytes": image_bytes
        }
    ]
    api_key = sk_settings["wan_api_key"]
    if api_key:
        logger.debug("OCR API key detected (length=%d).", len(api_key))
    else:
        logger.warning("OCR API key missing or empty.")
    result = await req_read_screen8(session, request, token, api_key, local_info, imgs, network_api_engine,
                                    img_endpoint)

    # Check if result contains an error from network failure
    if isinstance(result, dict) and 'error' in result:
        logger.error(f"Network error in OCR request: {result.get('message', 'Unknown error')}")
        logger.error(f"Error details: {result.get('details', 'No details available')}")
        return []

    if network_api_engine == "wan":
        jresult = json.loads(result['body'])
    else:
        jresult = result['body']
    # logger.info("cloud result data: "+json.dumps(jresult["data"]))
    logger.info(
        ">>>>>>>>>>>>>>>>>>>>>screen read time stamp1E: " + datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3])

    if "errors" in jresult:
        logger.error("ERROR Type: " + json.dumps(jresult["errors"][0]["errorType"]) + "ERROR Info: " + json.dumps(
            jresult["errors"][0]["errorInfo"]))
        return []
    else:
        # logger.info("cloud result data body: "+json.dumps(result["body"]))
        if network_api_engine == "wan":
            jbody = json.loads(result['body'])
        else:
            jbody = json.loads(result['body']['data']['body'])
            logger.debug("OCR response body: %s", jbody)

        # global var "last_screen" always contains information extracted from the last screen shot.
        if len(jbody["data"]) > 0:
            symTab["last_screen"] = jbody["data"]
            return jbody["data"]
        else:
            symTab["last_screen"] = []
            return []


async def req_read_screen8(session, request, token, api_key, local_info, imgs, engine, api_endpoint):
    if engine == "aws":
        return await req_cloud_read_screen8(session, request, token, api_endpoint)
    elif engine == "lan":
        return await req_lan_read_screen8(session, request, token, api_key, local_info, imgs, api_endpoint)