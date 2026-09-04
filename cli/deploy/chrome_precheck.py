r"""Chrome environment pre-check for 快速生成 → 抖店客服 (Fast Deploy, douyin_cs).

Runs BEFORE any resource is created. The customer runs (2026-09-04/05) that
produced "no response at all" both failed before detection ever started:
eCan attached to a Chrome that had no Feige page — either its own
auto-started blank Chrome, or a Chrome launched without the debug flag
because a hidden instance swallowed it. This check removes the setup
guesswork:

  1. Chrome installed?  If not: fail with a clickable download link.
  2. Chrome's directory on PATH (user Path via HKCU, no admin needed).
  3. Desktop Chrome shortcut(s) retargeted to launch with the debug flags
     eCan attaches to, so a double-click on the icon is a correct launch:
       chrome.exe --remote-debugging-port=9228 --user-data-dir="C:\chrome_data"
                  --disable-features=SharedStorage,InterestCohort

Steps 2 and 3 are best-effort (logged, never fatal). Only a missing Chrome
fails the deploy. Windows-only for step 3; other platforms run 1 and 2.
"""

import glob
import os
import platform
from typing import Any, Dict, List, Optional, Tuple

CHROME_DOWNLOAD_URL = "https://www.google.cn/chrome/"
DEBUG_PORT = 9228
USER_DATA_DIR = r"C:\chrome_data"
CHROME_DEBUG_ARGS = (
    f'--remote-debugging-port={DEBUG_PORT} --user-data-dir="{USER_DATA_DIR}" '
    "--disable-features=SharedStorage,InterestCohort"
)


def _desktop_dirs() -> List[str]:
    """User desktop (honours OneDrive redirection via User Shell Folders) +
    the public desktop."""
    dirs: List[str] = []
    try:
        import winreg
        with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as k:
            val, _ = winreg.QueryValueEx(k, "Desktop")
            if val:
                dirs.append(os.path.expandvars(str(val)))
    except Exception:
        pass
    dirs.append(os.path.join(os.path.expanduser("~"), "Desktop"))
    pub = os.environ.get("PUBLIC")
    if pub:
        dirs.append(os.path.join(pub, "Desktop"))
    seen: List[str] = []
    for d in dirs:
        if d and os.path.isdir(d) and d.lower() not in [s.lower() for s in seen]:
            seen.append(d)
    return seen


def update_chrome_shortcuts(chrome_path: str, desktop_dirs: Optional[List[str]] = None) -> Dict[str, Any]:
    """Retarget every desktop .lnk whose target is chrome.exe to launch with
    CHROME_DEBUG_ARGS. Returns {updated: [...], skipped: [...], detail}."""
    result: Dict[str, Any] = {"updated": [], "skipped": [], "detail": ""}
    if platform.system() != "Windows":
        result["detail"] = "not Windows"
        return result
    try:
        import win32com.client  # pywin32 — in requirements-windows.txt
    except Exception as e:
        result["detail"] = f"pywin32 unavailable: {e}"
        return result
    try:
        shell = win32com.client.Dispatch("WScript.Shell")
    except Exception as e:
        result["detail"] = f"WScript.Shell unavailable: {e}"
        return result
    chrome_exe = os.path.basename(chrome_path).lower() or "chrome.exe"
    for d in (desktop_dirs if desktop_dirs is not None else _desktop_dirs()):
        for lnk in glob.glob(os.path.join(d, "*.lnk")):
            try:
                sc = shell.CreateShortcut(lnk)
                target = str(sc.TargetPath or "")
                if os.path.basename(target).lower() != chrome_exe:
                    continue
                if str(sc.Arguments or "").strip() == CHROME_DEBUG_ARGS:
                    result["skipped"].append(lnk)
                    continue
                sc.Arguments = CHROME_DEBUG_ARGS
                sc.Save()
                result["updated"].append(lnk)
            except Exception as e:  # public desktop may be read-only for non-admins
                result["skipped"].append(f"{lnk} ({e})")
    return result


def run_chrome_precheck() -> Tuple[bool, List[str], str]:
    """Returns (ok, log_lines, failure_message). ok=False only when Chrome is
    not installed; the message + log carry the download link for the panel."""
    from agent.mcp.server.chrome_launcher import add_chrome_to_path, find_chrome

    log: List[str] = ["Chrome pre-check / Chrome 环境检查:"]
    info = find_chrome()
    if not info.get("found"):
        log += [
            "  ✗ Google Chrome not installed on this computer. / 未检测到 Google Chrome。",
            f"  → Download and install Chrome, then click Create again: {CHROME_DOWNLOAD_URL}",
            f"  → 请下载并安装 Chrome 后再点击“创建”: {CHROME_DOWNLOAD_URL}",
        ]
        return False, log, f"Google Chrome is not installed / 未安装 Chrome — download: {CHROME_DOWNLOAD_URL}"

    chrome_path = str(info["path"])
    log.append(f"  ✓ Chrome found: {chrome_path}")

    if info.get("in_path"):
        log.append("  ✓ Chrome directory already on PATH")
    else:
        r = add_chrome_to_path(chrome_path)
        if r.get("added"):
            log.append(f"  ✓ Added Chrome directory to PATH ({r.get('detail')})")
        else:
            log.append(f"  • PATH unchanged: {r.get('detail') or r.get('method')}")

    if platform.system() == "Windows":
        s = update_chrome_shortcuts(chrome_path)
        for lnk in s["updated"]:
            log.append(f"  ✓ Desktop shortcut now launches Chrome with debug flags: {lnk}")
        if s["updated"]:
            log.append(f"    args: {CHROME_DEBUG_ARGS}")
        if not s["updated"] and not s["skipped"]:
            log.append("  • No desktop Chrome shortcut found — launch Chrome manually with: "
                       f"chrome.exe {CHROME_DEBUG_ARGS}")
        if s["skipped"] and not s["updated"]:
            log.append(f"  • Desktop shortcut already configured / skipped: {len(s['skipped'])}")
        if s.get("detail"):
            log.append(f"  • Shortcut update note: {s['detail']}")
    return True, log, ""
