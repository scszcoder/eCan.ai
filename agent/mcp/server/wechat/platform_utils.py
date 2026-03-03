"""
Cross-platform window management and clipboard utilities for WeChat automation.

Supports Windows, macOS, and Linux. Each platform has its own implementation
for window finding, activation, clipboard text/file operations.
"""

import os
import sys
import time
import subprocess
import struct

from utils.logger_helper import logger_helper as logger

PLATFORM = sys.platform  # 'win32', 'darwin', 'linux'


# ---------------------------------------------------------------------------
# Window info dataclass (platform-neutral)
# ---------------------------------------------------------------------------

class WindowInfo:
    """Lightweight cross-platform window descriptor."""
    __slots__ = ("title", "hwnd", "left", "top", "width", "height", "is_minimized")

    def __init__(self, title="", hwnd=None, left=0, top=0, width=0, height=0, is_minimized=False):
        self.title = title
        self.hwnd = hwnd
        self.left = left
        self.top = top
        self.width = width
        self.height = height
        self.is_minimized = is_minimized


# ═══════════════════════════════════════════════════════════════════════════
# FIND WINDOWS BY TITLE
# ═══════════════════════════════════════════════════════════════════════════

def find_windows_by_title(title_keywords: list[str]) -> list[WindowInfo]:
    """Return a list of WindowInfo objects whose titles contain any of the keywords."""
    if PLATFORM == "win32":
        return _find_windows_win32(title_keywords)
    elif PLATFORM == "darwin":
        return _find_windows_macos(title_keywords)
    else:
        return _find_windows_linux(title_keywords)


# --- Windows ---
def _find_windows_win32(title_keywords: list[str]) -> list[WindowInfo]:
    try:
        import pygetwindow as gw
        results = []
        kw_lower = {k.lower() for k in title_keywords}
        for title_kw in title_keywords:
            try:
                wins = gw.getWindowsWithTitle(title_kw)
                for w in wins:
                    wt = w.title.strip().lower()
                    # Prefer exact matches first
                    if wt in kw_lower:
                        results.insert(0, WindowInfo(
                            title=w.title, hwnd=getattr(w, "_hWnd", None),
                            left=w.left, top=w.top, width=w.width, height=w.height,
                            is_minimized=w.isMinimized,
                        ))
                    else:
                        results.append(WindowInfo(
                            title=w.title, hwnd=getattr(w, "_hWnd", None),
                            left=w.left, top=w.top, width=w.width, height=w.height,
                            is_minimized=w.isMinimized,
                        ))
            except Exception:
                pass
        return results
    except ImportError:
        logger.warning("[platform_utils] pygetwindow not available on this system")
        return []


# --- macOS ---
def _find_windows_macos(title_keywords: list[str]) -> list[WindowInfo]:
    """Use AppleScript to list visible windows and match by title."""
    results = []
    try:
        # AppleScript: get names of all visible application processes
        script = '''
        tell application "System Events"
            set windowList to {}
            repeat with proc in (every process whose visible is true)
                repeat with w in (every window of proc)
                    set end of windowList to {name of proc, name of w, position of w, size of w}
                end repeat
            end repeat
            return windowList
        end tell
        '''
        out = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=10,
        )
        if out.returncode != 0:
            return results

        # Parse output — AppleScript returns comma-separated nested lists
        # Fallback: simpler approach per keyword
        for kw in title_keywords:
            script2 = f'''
            tell application "System Events"
                set matchedWindows to {{}}
                repeat with proc in (every process whose visible is true)
                    repeat with w in (every window of proc)
                        if name of w contains "{kw}" then
                            set winPos to position of w
                            set winSize to size of w
                            set end of matchedWindows to (name of w & "|" & (item 1 of winPos as text) & "|" & (item 2 of winPos as text) & "|" & (item 1 of winSize as text) & "|" & (item 2 of winSize as text))
                        end if
                    end repeat
                end repeat
                set AppleScript's text item delimiters to "\\n"
                return matchedWindows as text
            end tell
            '''
            out2 = subprocess.run(
                ["osascript", "-e", script2],
                capture_output=True, text=True, timeout=10,
            )
            if out2.returncode == 0 and out2.stdout.strip():
                for line in out2.stdout.strip().split("\n"):
                    parts = line.strip().split("|")
                    if len(parts) >= 5:
                        results.append(WindowInfo(
                            title=parts[0],
                            left=int(parts[1]), top=int(parts[2]),
                            width=int(parts[3]), height=int(parts[4]),
                        ))
    except Exception as e:
        logger.warning(f"[platform_utils] macOS window search failed: {e}")
    return results


# --- Linux ---
def _find_windows_linux(title_keywords: list[str]) -> list[WindowInfo]:
    """Use wmctrl -l to list windows and match by title."""
    results = []
    try:
        out = subprocess.run(
            ["wmctrl", "-l", "-G"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode != 0:
            # Fallback: try xdotool
            return _find_windows_linux_xdotool(title_keywords)

        kw_lower = [k.lower() for k in title_keywords]
        for line in out.stdout.strip().split("\n"):
            # Format: 0x... desktop x y w h hostname title...
            parts = line.split(None, 7)
            if len(parts) < 8:
                continue
            hwnd_str, _, x, y, w, h, _host, title = parts
            title_lower = title.strip().lower()
            for kw in kw_lower:
                if kw in title_lower:
                    results.append(WindowInfo(
                        title=title.strip(), hwnd=hwnd_str,
                        left=int(x), top=int(y), width=int(w), height=int(h),
                    ))
                    break
    except FileNotFoundError:
        return _find_windows_linux_xdotool(title_keywords)
    except Exception as e:
        logger.warning(f"[platform_utils] Linux window search failed: {e}")
    return results


def _find_windows_linux_xdotool(title_keywords: list[str]) -> list[WindowInfo]:
    results = []
    try:
        for kw in title_keywords:
            out = subprocess.run(
                ["xdotool", "search", "--name", kw],
                capture_output=True, text=True, timeout=5,
            )
            if out.returncode == 0:
                for wid in out.stdout.strip().split("\n"):
                    wid = wid.strip()
                    if not wid:
                        continue
                    # Get window name
                    name_out = subprocess.run(
                        ["xdotool", "getwindowname", wid],
                        capture_output=True, text=True, timeout=3,
                    )
                    # Get geometry
                    geo_out = subprocess.run(
                        ["xdotool", "getwindowgeometry", "--shell", wid],
                        capture_output=True, text=True, timeout=3,
                    )
                    title = name_out.stdout.strip() if name_out.returncode == 0 else kw
                    x, y, w, h = 0, 0, 0, 0
                    if geo_out.returncode == 0:
                        for gl in geo_out.stdout.strip().split("\n"):
                            if gl.startswith("X="):
                                x = int(gl.split("=")[1])
                            elif gl.startswith("Y="):
                                y = int(gl.split("=")[1])
                            elif gl.startswith("WIDTH="):
                                w = int(gl.split("=")[1])
                            elif gl.startswith("HEIGHT="):
                                h = int(gl.split("=")[1])
                    results.append(WindowInfo(
                        title=title, hwnd=wid,
                        left=x, top=y, width=w, height=h,
                    ))
    except FileNotFoundError:
        logger.warning("[platform_utils] Neither wmctrl nor xdotool found on Linux")
    except Exception as e:
        logger.warning(f"[platform_utils] Linux xdotool search failed: {e}")
    return results


# ═══════════════════════════════════════════════════════════════════════════
# BRING WINDOW TO FRONT
# ═══════════════════════════════════════════════════════════════════════════

def bring_window_to_front(win: WindowInfo) -> bool:
    """Activate / bring a window to the foreground. Returns True on success."""
    if PLATFORM == "win32":
        return _activate_win32(win)
    elif PLATFORM == "darwin":
        return _activate_macos(win)
    else:
        return _activate_linux(win)


def _activate_win32(win: WindowInfo) -> bool:
    try:
        import win32gui, win32con
        hwnd = win.hwnd
        if not hwnd:
            return False
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            time.sleep(0.3)
        win32gui.SetForegroundWindow(hwnd)
        return True
    except Exception:
        # Fallback via pygetwindow
        try:
            import pygetwindow as gw
            wins = gw.getWindowsWithTitle(win.title)
            if wins:
                w = wins[0]
                if w.isMinimized:
                    w.restore()
                    time.sleep(0.3)
                w.activate()
                return True
        except Exception:
            pass
    return False


def _activate_macos(win: WindowInfo) -> bool:
    try:
        # Activate by window title via AppleScript
        script = f'''
        tell application "System Events"
            repeat with proc in (every process whose visible is true)
                repeat with w in (every window of proc)
                    if name of w contains "{win.title}" then
                        set frontmost of proc to true
                        perform action "AXRaise" of w
                        return true
                    end if
                end repeat
            end repeat
        end tell
        return false
        '''
        out = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=5,
        )
        return out.returncode == 0 and "true" in out.stdout.lower()
    except Exception as e:
        logger.warning(f"[platform_utils] macOS activate failed: {e}")
        return False


def _activate_linux(win: WindowInfo) -> bool:
    hwnd = win.hwnd
    if not hwnd:
        return False
    try:
        # Try wmctrl first
        out = subprocess.run(
            ["wmctrl", "-i", "-a", str(hwnd)],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0:
            return True
    except FileNotFoundError:
        pass
    try:
        # Fallback: xdotool
        subprocess.run(
            ["xdotool", "windowactivate", "--sync", str(hwnd)],
            capture_output=True, text=True, timeout=5,
        )
        return True
    except Exception as e:
        logger.warning(f"[platform_utils] Linux activate failed: {e}")
    return False


# ═══════════════════════════════════════════════════════════════════════════
# CLIPBOARD — TEXT
# ═══════════════════════════════════════════════════════════════════════════

def clipboard_set_text(text: str):
    """Copy text to the system clipboard (cross-platform)."""
    if PLATFORM == "win32":
        _clipboard_set_text_win32(text)
    elif PLATFORM == "darwin":
        _clipboard_set_text_macos(text)
    else:
        _clipboard_set_text_linux(text)


def _clipboard_set_text_win32(text: str):
    try:
        import pyperclip
        pyperclip.copy(text)
        return
    except ImportError:
        pass
    try:
        import win32clipboard
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardText(text)
        win32clipboard.CloseClipboard()
    except Exception as e:
        logger.warning(f"[platform_utils] Win32 clipboard failed: {e}")
        raise


def _clipboard_set_text_macos(text: str):
    try:
        import pyperclip
        pyperclip.copy(text)
        return
    except ImportError:
        pass
    # Fallback: pbcopy
    proc = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
    proc.communicate(text.encode("utf-8"))


def _clipboard_set_text_linux(text: str):
    try:
        import pyperclip
        pyperclip.copy(text)
        return
    except ImportError:
        pass
    # Try xclip, then xsel
    for cmd in [["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]]:
        try:
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
            proc.communicate(text.encode("utf-8"))
            return
        except FileNotFoundError:
            continue
    raise RuntimeError("No clipboard tool available (install xclip or xsel)")


# ═══════════════════════════════════════════════════════════════════════════
# CLIPBOARD — FILE
# ═══════════════════════════════════════════════════════════════════════════

def clipboard_set_file(file_path: str):
    """Copy a file to the system clipboard so Ctrl+V / Cmd+V pastes it."""
    file_path = os.path.abspath(file_path)
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    if PLATFORM == "win32":
        _clipboard_set_file_win32(file_path)
    elif PLATFORM == "darwin":
        _clipboard_set_file_macos(file_path)
    else:
        _clipboard_set_file_linux(file_path)


def _clipboard_set_file_win32(file_path: str):
    import win32clipboard
    import win32con

    # DROPFILES structure
    offset = 20  # sizeof(DROPFILES)
    # fWide = 1 means Unicode
    dropfiles = struct.pack("IIIii", offset, 0, 0, 0, 1)
    # File list: null-terminated UTF-16LE string, double-null terminated
    file_bytes = file_path.encode("utf-16-le") + b"\x00\x00" + b"\x00\x00"
    data = dropfiles + file_bytes

    win32clipboard.OpenClipboard()
    win32clipboard.EmptyClipboard()
    win32clipboard.SetClipboardData(win32con.CF_HDROP, data)
    win32clipboard.CloseClipboard()
    logger.info(f"[platform_utils] Copied file to clipboard (Win): {file_path}")


def _clipboard_set_file_macos(file_path: str):
    # Use osascript to set clipboard to a file reference
    script = f'''
    set the clipboard to (POSIX file "{file_path}")
    '''
    out = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True, timeout=5,
    )
    if out.returncode != 0:
        raise RuntimeError(f"macOS clipboard file copy failed: {out.stderr}")
    logger.info(f"[platform_utils] Copied file to clipboard (macOS): {file_path}")


def _clipboard_set_file_linux(file_path: str):
    # xclip with target for file URIs
    file_uri = f"file://{file_path}"
    try:
        proc = subprocess.Popen(
            ["xclip", "-selection", "clipboard", "-t", "text/uri-list"],
            stdin=subprocess.PIPE,
        )
        proc.communicate(file_uri.encode("utf-8"))
        logger.info(f"[platform_utils] Copied file to clipboard (Linux): {file_path}")
    except FileNotFoundError:
        raise RuntimeError("xclip not found — install it to copy files to clipboard on Linux")


# ═══════════════════════════════════════════════════════════════════════════
# PASTE HOTKEY (platform-aware)
# ═══════════════════════════════════════════════════════════════════════════

def paste_hotkey():
    """Press the platform-appropriate paste shortcut."""
    import pyautogui
    if PLATFORM == "darwin":
        pyautogui.hotkey("command", "v")
    else:
        pyautogui.hotkey("ctrl", "v")
