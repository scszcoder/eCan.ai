"""Cross-platform Chrome detection / PATH registration / debug-mode launch.

Backs the ``os_launch_chrome_debug`` and ``os_install_chrome`` MCP tools
(and the matching browser-use actions), so an agent can get a CDP-ready
Chrome running without the user firing one up manually:

    chrome --remote-debugging-port=<port> --user-data-dir=<dir>
           --disable-features=SharedStorage,InterestCohort

Consent model: ``launch_chrome_debug`` NEVER installs anything — when
Chrome is missing it returns ``status='not_installed'`` with a message the
LLM should relay to ask the user's permission; only then should
``install_chrome`` be called. Keep that split — installing software
without an explicit yes is not acceptable agent behavior.

Pure stdlib; safe for cloud workers (no Qt / GUI imports).
"""

import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from typing import Any, Dict, List, Optional

from utils.logger_helper import logger_helper as logger

DEFAULT_DEBUG_PORT = 9228
_DISABLE_FEATURES_FLAG = "--disable-features=SharedStorage,InterestCohort"

_WINDOWS_CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
]
_MAC_CHROME_PATHS = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    os.path.expanduser("~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
]
_LINUX_CHROME_NAMES = ["google-chrome", "google-chrome-stable", "chromium-browser", "chromium"]


def _which_chrome() -> Optional[str]:
    """Chrome resolved from PATH, or None."""
    names = (["chrome", "chrome.exe", "google-chrome"] if platform.system() == "Windows"
             else _LINUX_CHROME_NAMES + ["Google Chrome"])
    for name in names:
        hit = shutil.which(name)
        if hit:
            return hit
    return None


def find_chrome() -> Dict[str, Any]:
    """Locate the Chrome executable.

    Returns {found, path, in_path} — ``in_path`` True when the executable is
    reachable through the PATH env var (vs only at a well-known location).
    """
    from_path = _which_chrome()
    if from_path:
        return {"found": True, "path": from_path, "in_path": True}

    system = platform.system()
    candidates: List[str] = []
    if system == "Windows":
        candidates = list(_WINDOWS_CHROME_PATHS)
        # Registry App Paths is the authoritative install record.
        try:
            import winreg
            for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    with winreg.OpenKey(
                            root,
                            r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe") as k:
                        val, _ = winreg.QueryValueEx(k, None)
                        if val:
                            candidates.insert(0, val)
                except OSError:
                    pass
        except Exception:
            pass
    elif system == "Darwin":
        candidates = list(_MAC_CHROME_PATHS)
    else:
        candidates = [f"/usr/bin/{n}" for n in _LINUX_CHROME_NAMES] + \
                     [f"/opt/google/chrome/{n}" for n in ("google-chrome", "chrome")]

    for cand in candidates:
        if cand and os.path.isfile(cand):
            return {"found": True, "path": cand, "in_path": False}
    return {"found": False, "path": "", "in_path": False}


def add_chrome_to_path(chrome_path: str) -> Dict[str, Any]:
    """Best-effort: make Chrome's directory reachable via PATH.

    Windows: appends to the USER Path (HKCU\\Environment — no admin needed)
    and broadcasts WM_SETTINGCHANGE so new shells see it. macOS/Linux: shell
    rc files are not edited (too invasive) — a /usr/local/bin symlink is
    attempted when writable; otherwise callers just use the absolute path.
    Always updates this process's PATH so subsequent lookups succeed.
    """
    chrome_dir = os.path.dirname(chrome_path)
    result: Dict[str, Any] = {"added": False, "method": "", "detail": ""}
    try:
        # Current process first — cheap and always allowed.
        if chrome_dir not in (os.environ.get("PATH") or "").split(os.pathsep):
            os.environ["PATH"] = (os.environ.get("PATH", "") + os.pathsep + chrome_dir)

        if platform.system() == "Windows":
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0,
                                winreg.KEY_READ | winreg.KEY_WRITE) as key:
                try:
                    current, value_type = winreg.QueryValueEx(key, "Path")
                except OSError:
                    current, value_type = "", winreg.REG_EXPAND_SZ
                parts = [p for p in current.split(os.pathsep) if p]
                if chrome_dir.lower() not in [p.lower() for p in parts]:
                    winreg.SetValueEx(key, "Path", 0, value_type,
                                      os.pathsep.join(parts + [chrome_dir]))
                    result.update(added=True, method="user_path_registry",
                                  detail=f"appended {chrome_dir} to HKCU Environment Path")
                    try:
                        import ctypes
                        ctypes.windll.user32.SendMessageTimeoutW(
                            0xFFFF, 0x001A, 0, "Environment", 0x0002, 5000, None)
                    except Exception:
                        pass
                else:
                    result.update(method="user_path_registry", detail="already present")
        else:
            link = "/usr/local/bin/google-chrome"
            if not os.path.exists(link) and os.access("/usr/local/bin", os.W_OK):
                os.symlink(chrome_path, link)
                result.update(added=True, method="symlink", detail=link)
            else:
                result.update(method="process_env_only",
                              detail="using absolute path; shell rc not modified")
    except Exception as e:
        result["detail"] = f"PATH update failed: {e}"
        logger.warning(f"[chrome_launcher] {result['detail']}")
    return result


def is_debug_chrome_running(port: int = DEFAULT_DEBUG_PORT) -> Dict[str, Any]:
    """Probe the CDP endpoint on *port*."""
    try:
        with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/json/version", timeout=2) as resp:
            info = json.loads(resp.read().decode("utf-8", "replace"))
        return {"running": True,
                "browser": info.get("Browser", ""),
                "ws_url": info.get("webSocketDebuggerUrl", "")}
    except Exception:
        return {"running": False}


def _default_user_data_dir() -> str:
    if platform.system() == "Windows":
        return r"C:\chrome_data"
    return os.path.expanduser("~/chrome_data")


def launch_chrome_debug(port: int = DEFAULT_DEBUG_PORT,
                        user_data_dir: str = "",
                        extra_flags: Optional[List[str]] = None,
                        wait_timeout_s: float = 12.0) -> Dict[str, Any]:
    """Detect Chrome and launch it with remote debugging enabled.

    Returns a status dict:
      already_running — a debug Chrome is already listening on *port*
      launched        — started and the CDP endpoint answered
      launch_timeout  — process started but endpoint didn't answer in time
      not_installed   — Chrome not found; ASK THE USER before calling
                        install_chrome
    """
    probe = is_debug_chrome_running(port)
    if probe.get("running"):
        return {"status": "already_running", "port": port, **probe}

    found = find_chrome()
    if not found["found"]:
        return {
            "status": "not_installed",
            "message": ("Google Chrome was not found on this computer. "
                        "Ask the user for permission to download and install "
                        "it (the install_chrome tool), or ask them to install "
                        "it from https://www.google.com/chrome/ and retry."),
        }

    path_result: Dict[str, Any] = {}
    if not found["in_path"]:
        path_result = add_chrome_to_path(found["path"])

    data_dir = (user_data_dir or "").strip() or _default_user_data_dir()
    try:
        os.makedirs(data_dir, exist_ok=True)
    except Exception as e:
        return {"status": "error", "message": f"cannot create user-data-dir {data_dir}: {e}"}

    cmd = [found["path"],
           f"--remote-debugging-port={port}",
           f"--user-data-dir={data_dir}",
           _DISABLE_FEATURES_FLAG,
           "--no-first-run", "--no-default-browser-check"]
    if extra_flags:
        cmd.extend(str(f) for f in extra_flags)

    try:
        try:
            from utils.subprocess_helper import popen_no_window
            proc = popen_no_window(cmd)
        except Exception:
            kwargs: Dict[str, Any] = {}
            if platform.system() == "Windows":
                kwargs["creationflags"] = 0x00000008 | 0x00000200  # DETACHED | NEW_PROCESS_GROUP
            else:
                kwargs["start_new_session"] = True
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL, **kwargs)
    except Exception as e:
        return {"status": "error", "message": f"failed to launch Chrome: {e}",
                "chrome_path": found["path"]}

    deadline = time.time() + wait_timeout_s
    while time.time() < deadline:
        probe = is_debug_chrome_running(port)
        if probe.get("running"):
            return {"status": "launched", "port": port, "pid": proc.pid,
                    "chrome_path": found["path"], "user_data_dir": data_dir,
                    "path_registration": path_result, **probe}
        time.sleep(0.4)
    return {"status": "launch_timeout", "port": port, "pid": proc.pid,
            "chrome_path": found["path"], "user_data_dir": data_dir,
            "message": f"Chrome started (pid {proc.pid}) but the CDP endpoint "
                       f"on port {port} did not answer within {wait_timeout_s}s. "
                       f"An existing non-debug Chrome using the same profile "
                       f"directory can cause this."}


def install_chrome() -> Dict[str, Any]:
    """Download and silently install Google Chrome.

    ONLY call after the user has explicitly agreed. Takes minutes.
    """
    already = find_chrome()
    if already["found"]:
        return {"status": "already_installed", "path": already["path"]}

    system = platform.system()
    try:
        if system == "Windows":
            url = "https://dl.google.com/chrome/install/latest/chrome_installer.exe"
            dest = os.path.join(tempfile.gettempdir(), "chrome_installer.exe")
            logger.info(f"[chrome_launcher] downloading {url}")
            urllib.request.urlretrieve(url, dest)
            # Silent per-machine install falls back to per-user automatically
            # when not elevated.
            r = subprocess.run([dest, "/silent", "/install"], timeout=900)
            if r.returncode not in (0, None):
                return {"status": "error",
                        "message": f"installer exited with code {r.returncode}"}
        elif system == "Darwin":
            if shutil.which("brew"):
                r = subprocess.run(["brew", "install", "--cask", "google-chrome"],
                                   capture_output=True, text=True, timeout=1800)
                if r.returncode != 0:
                    return {"status": "error", "message": (r.stderr or r.stdout)[-500:]}
            else:
                url = "https://dl.google.com/chrome/mac/universal/stable/GGRO/googlechrome.dmg"
                dmg = os.path.join(tempfile.gettempdir(), "googlechrome.dmg")
                urllib.request.urlretrieve(url, dmg)
                mount = subprocess.run(["hdiutil", "attach", "-nobrowse", dmg],
                                       capture_output=True, text=True, timeout=300)
                if mount.returncode != 0:
                    return {"status": "error", "message": mount.stderr[-500:]}
                try:
                    subprocess.run(["cp", "-R", "/Volumes/Google Chrome/Google Chrome.app",
                                    "/Applications/"], check=True, timeout=600)
                finally:
                    subprocess.run(["hdiutil", "detach", "/Volumes/Google Chrome"],
                                   capture_output=True, timeout=120)
        else:  # Linux
            url = "https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb"
            deb = os.path.join(tempfile.gettempdir(), "google-chrome.deb")
            urllib.request.urlretrieve(url, deb)
            # Needs root; try non-interactive sudo, otherwise hand back guidance.
            r = subprocess.run(["sudo", "-n", "dpkg", "-i", deb],
                               capture_output=True, text=True, timeout=600)
            if r.returncode != 0:
                return {"status": "needs_manual_step",
                        "message": ("Downloaded to " + deb + " but installing "
                                    "requires root. Ask the user to run: "
                                    f"sudo dpkg -i {deb} && sudo apt-get -f install")}
    except Exception as e:
        return {"status": "error", "message": f"install failed: {e}"}

    found = find_chrome()
    if found["found"]:
        return {"status": "installed", "path": found["path"]}
    return {"status": "error",
            "message": "installer ran but Chrome still not found — it may "
                       "need a moment or a manual finish"}
