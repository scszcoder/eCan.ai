"""Launch and shut down a registered browser profile.

One call takes a profile id and gives back a CDP endpoint:

    br = launch_profile("etsy")
    ...  # drive br.cdp_url
    close_profile("etsy")

What this owns that a bare ``subprocess.Popen`` does not:

* **The proxy.** An authenticated SOCKS5 upstream needs a local relay in front
  of it (Chromium cannot do SOCKS auth — see ``socks_relay``). The relay's
  lifetime is the browser's lifetime, so it is started and stopped here.
* **One browser per user-data-dir.** Chromium refuses a second process on a
  directory already in use, and the failure mode is a browser that exits a
  second after launch with nothing useful on stderr. We record the debug port
  inside the profile directory, so a *different process* — the next skill run —
  finds the running browser and attaches instead of racing it.
* **A graceful close.** Killing Chromium loses whatever it had not yet flushed:
  cookies, localStorage, and the session state that is the entire point of
  keeping a profile. We close the tabs and let it exit on its own.
"""

import json
import os
import socket
import subprocess
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from utils.logger_helper import logger_helper as logger

from . import profile_registry as registry

# Written inside the user-data-dir so any process can find a running browser
# for this profile. Chromium ignores unknown dotfiles there.
_PORT_FILE = ".ecan_cdp.json"

# Flags we pass on every launch. Most are noise suppression; the ones that
# matter for fingerprinting are noted.
_BASE_FLAGS = (
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-background-mode",
    "--force-color-profile=srgb",       # else the color profile varies by display
    "--metrics-recording-only",
    "--password-store=basic",           # no OS keyring prompt on Linux
    "--use-mock-keychain",
    "--disable-features=FlashDeprecationWarning,EnablePasswordsAccountStorage",
    "--remote-allow-origins=*",         # CDP clients send an Origin header
)


@dataclass
class LaunchedBrowser:
    """A running browser for one profile."""
    profile_id: str
    user_data_dir: str
    debug_port: int
    cdp_url: str
    pid: int = 0
    attached: bool = False              # True if we found it already running
    stop_relay: Optional[Callable[[], None]] = field(default=None, repr=False)


# Browsers this process launched, by profile id.
_RUNNING: dict = {}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _port_open(port: int, timeout: float = 1.0) -> bool:
    """Is anything listening on 127.0.0.1:*port*?"""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def _cdp_version(port: int, timeout: float = 1.0) -> Optional[dict]:
    """Return /json/version if a browser is listening on *port*, else None."""
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/json/version", timeout=timeout
        ) as r:
            return json.load(r)
    except Exception:
        return None


def _read_port_file(user_data_dir: Path) -> Optional[dict]:
    try:
        return json.loads((user_data_dir / _PORT_FILE).read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_port_file(user_data_dir: Path, data: dict) -> None:
    try:
        (user_data_dir / _PORT_FILE).write_text(json.dumps(data), encoding="utf-8")
    except Exception as exc:
        logger.warning(f"[fp-browser] could not record the debug port: {exc}")


def _clear_port_file(user_data_dir: Path) -> None:
    try:
        (user_data_dir / _PORT_FILE).unlink()
    except Exception:
        pass


def resolve_browser_path(profile: dict) -> str:
    """Which binary to run.

    The profile records the binary that wrote it, because a profile written by
    a newer Chromium can make an older one refuse to start ("profile appears to
    be from a newer version"). That recorded path wins; the fallbacks are for
    profiles created before we started recording it.
    """
    recorded = ((profile.get("browser") or {}).get("path") or "").strip()
    if recorded and Path(recorded).exists():
        return recorded
    env = (os.getenv("ECAN_CHROMIUM_PATH") or "").strip()
    if env and Path(env).exists():
        return env
    # Playwright's bundled Chromium, newest install first.
    pw = Path.home() / "AppData/Local/ms-playwright"
    if not pw.exists():
        pw = Path.home() / ".cache/ms-playwright"
    if pw.exists():
        builds = sorted((d for d in pw.glob("chromium-*") if d.is_dir()),
                        key=lambda d: d.name, reverse=True)
        for d in builds:
            for rel in ("chrome-win/chrome.exe", "chrome-linux/chrome",
                        "chrome-mac/Chromium.app/Contents/MacOS/Chromium"):
                if (d / rel).exists():
                    return str(d / rel)
    raise FileNotFoundError(
        "no Chromium binary found; record one on the profile or set "
        "ECAN_CHROMIUM_PATH"
    )


def _proxy_flags(profile: dict):
    """Build the --proxy-server flags, starting a relay if auth is needed.

    Returns ``(flags, stop_relay_or_None, relay_port)``; ``relay_port`` is 0
    when no relay was needed.
    """
    proxy = profile.get("proxy") or {}
    host, port = (proxy.get("host") or "").strip(), proxy.get("port")
    if not host or not port:
        return [], None, 0

    scheme = (proxy.get("scheme") or "socks5").strip().lower()
    user = (proxy.get("username") or "").strip()
    password = registry.get_proxy_password(profile)

    if user and password and scheme.startswith("socks"):
        # Chromium cannot authenticate to SOCKS at all; front it with a relay.
        from .socks_relay import start_relay
        local_port, stop = start_relay(host, int(port), user, password)
        server = f"socks5://127.0.0.1:{local_port}"
    else:
        # HTTP proxies can carry credentials in the URL; SOCKS without auth is
        # passed through directly.
        cred = f"{user}:{password}@" if (user and password) else ""
        server = f"{scheme}://{cred}{host}:{int(port)}"
        stop, local_port = None, 0

    flags = [f"--proxy-server={server}"]
    bypass = profile.get("proxy_bypass") or []
    if bypass:
        flags.append("--proxy-bypass-list=" + ",".join(bypass))
    return flags, stop, local_port


def launch_profile(
    profile_id: str,
    debug_port: int = 0,
    headless: bool = False,
    start_url: str = "about:blank",
    timeout: float = 30.0,
) -> LaunchedBrowser:
    """Start (or attach to) the browser for *profile_id*.

    ``debug_port=0`` picks a free port. If a browser is already running on this
    profile — started by us or by an earlier process — its endpoint is returned
    and nothing new is launched.
    """
    profile = registry.get_profile(profile_id)
    if not profile:
        raise KeyError(f"no browser profile registered as '{profile_id}'")

    user_data_dir = Path(profile["user_data_dir"])
    user_data_dir.mkdir(parents=True, exist_ok=True)

    # Already ours?
    existing = _RUNNING.get(profile_id)
    if existing and _cdp_version(existing.debug_port):
        logger.info(f"[fp-browser] '{profile_id}' is already running on port "
                    f"{existing.debug_port}; reusing it")
        return existing

    # Already someone else's? (a previous run of the app, or a manual launch)
    recorded = _read_port_file(user_data_dir)
    if recorded:
        ver = _cdp_version(int(recorded.get("port") or 0))
        if ver:
            logger.info(f"[fp-browser] attaching to the browser already on port "
                        f"{recorded['port']} for '{profile_id}' "
                        f"({ver.get('Browser')})")
            # The relay belongs to whichever process launched the browser. If
            # that process is gone the relay is gone with it, and the browser
            # is now reaching the site from OUR address instead of the proxy
            # exit — the one thing an anti-detect profile must never do.
            relay_port = int(recorded.get("relay_port") or 0)
            if relay_port and not _port_open(relay_port):
                # An orphan: the launcher died (crash, kill, or an exit that
                # skipped close_all) and took the relay with it. The browser
                # is left with NO proxy, so nothing can legitimately still be
                # using it, and attaching would egress from this machine's own
                # address. Close it properly — which also flushes the session
                # the profile exists to keep — and start a clean one below
                # rather than making the user hunt down a stray window.
                logger.warning(
                    f"[fp-browser] '{profile_id}' is orphaned on port "
                    f"{recorded['port']}: its relay (127.0.0.1:{relay_port}) "
                    f"is dead, so it has no proxy. Closing it and relaunching."
                )
                if not close_profile(profile_id):
                    raise RuntimeError(
                        f"'{profile_id}' is running on port {recorded['port']} "
                        f"with a dead proxy relay and could not be closed "
                        f"automatically. Close that browser window, then run "
                        f"again; attaching to it would send traffic from this "
                        f"machine's own IP."
                    )
                _clear_port_file(user_data_dir)
                recorded = None          # fall through to a fresh launch

            if recorded:
                br = LaunchedBrowser(
                    profile_id=profile_id,
                    user_data_dir=str(user_data_dir),
                    debug_port=int(recorded["port"]),
                    cdp_url=f"http://127.0.0.1:{recorded['port']}",
                    pid=int(recorded.get("pid") or 0),
                    attached=True,
                )
                _RUNNING[profile_id] = br
                return br
        elif recorded:
            _clear_port_file(user_data_dir)  # stale

    port = int(debug_port) or _free_port()
    binary = resolve_browser_path(profile)
    proxy_flags, stop_relay, relay_port = _proxy_flags(profile)

    argv = [
        binary,
        f"--user-data-dir={user_data_dir}",
        f"--remote-debugging-port={port}",
        f"--lang={profile.get('locale') or 'en-US'}",
        *_BASE_FLAGS,
        *proxy_flags,
    ]
    if headless:
        argv.append("--headless=new")
        # Chromium in a container has no user namespace to sandbox into. Only
        # done headless: a sandboxed browser is the safer default on a desktop
        # where the user may browse with it themselves.
        argv.append("--no-sandbox")
    argv.append(start_url)

    logger.info(f"[fp-browser] launching '{profile_id}' on port {port} "
                f"({Path(binary).name}, proxy={'yes' if proxy_flags else 'no'}, "
                f"headless={headless})")
    proc = subprocess.Popen(argv, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)

    deadline = time.time() + timeout
    ver = None
    while time.time() < deadline:
        ver = _cdp_version(port)
        if ver:
            break
        if proc.poll() is not None:
            if stop_relay:
                stop_relay()
            raise RuntimeError(
                f"Chromium exited immediately (code {proc.returncode}) for "
                f"'{profile_id}'. The usual cause is another browser already "
                f"holding {user_data_dir}."
            )
        time.sleep(0.5)

    if not ver:
        if stop_relay:
            stop_relay()
        proc.terminate()
        raise TimeoutError(
            f"'{profile_id}' did not open a debug port within {timeout:.0f}s")

    br = LaunchedBrowser(
        profile_id=profile_id,
        user_data_dir=str(user_data_dir),
        debug_port=port,
        cdp_url=f"http://127.0.0.1:{port}",
        pid=proc.pid,
        stop_relay=stop_relay,
    )
    _RUNNING[profile_id] = br
    _write_port_file(user_data_dir, {"port": port, "pid": proc.pid,
                                     "relay_port": relay_port,
                                     "started": int(time.time())})
    logger.info(f"[fp-browser] '{profile_id}' ready: {ver.get('Browser')} on {br.cdp_url}")
    return br


def profile_status(profile_id: str) -> dict:
    """Whether *profile_id*'s browser is up, and where to reach it.

    Reads the port file inside the user-data-dir, so this answers for a browser
    ANY process launched — the GUI asking about one a skill run started, or the
    CLI asking about one the app started. ``owned`` distinguishes the two,
    because only the launching process holds the proxy relay.
    """
    blank = {
        "profile_id": profile_id, "running": False, "port": 0, "cdp_url": "",
        "pid": 0, "relay_port": 0, "relay_alive": False, "started": 0,
        "owned": False,
    }
    profile = registry.get_profile(profile_id)
    if not profile:
        return blank

    user_data_dir = Path(profile.get("user_data_dir") or "")
    recorded = _read_port_file(user_data_dir) if str(user_data_dir) else None
    port = int((recorded or {}).get("port") or 0)
    if not port or not _cdp_version(port, timeout=0.5):
        return blank

    relay_port = int(recorded.get("relay_port") or 0)
    return {
        "profile_id": profile_id,
        "running": True,
        "port": port,
        "cdp_url": f"http://127.0.0.1:{port}",
        "pid": int(recorded.get("pid") or 0),
        "relay_port": relay_port,
        # No relay recorded means the profile has no proxy, which is healthy.
        "relay_alive": (not relay_port) or _port_open(relay_port, timeout=0.5),
        "started": int(recorded.get("started") or 0),
        "owned": profile_id in _RUNNING,
    }


def close_profile(profile_id: str, grace: float = 15.0) -> bool:
    """Close the browser for *profile_id*, letting it flush its session.

    Closing every tab is what makes Chromium exit on its own and write out
    cookies and localStorage. Killing the process instead is how a profile
    silently loses the login it just made.
    """
    br = _RUNNING.get(profile_id)
    if not br:
        # Not ours. It may still be up from an earlier app run or another
        # process; closing tabs over CDP flushes the session just the same.
        # We do NOT fall through to killing it below — the relay belongs to
        # whoever launched it, and killing another process's browser is worse
        # than reporting that it is still open.
        st = profile_status(profile_id)
        if not st["running"]:
            return False
        br = LaunchedBrowser(
            profile_id=profile_id,
            user_data_dir=str((registry.get_profile(profile_id) or {})
                              .get("user_data_dir") or ""),
            debug_port=st["port"],
            cdp_url=st["cdp_url"],
            pid=0,                      # withhold the pid: no kill fallback
            attached=True,
        )

    targets = []
    try:
        with urllib.request.urlopen(f"{br.cdp_url}/json/list", timeout=2) as r:
            targets = [t for t in json.load(r) if t.get("type") == "page"]
    except Exception as exc:
        logger.warning(f"[fp-browser] could not list tabs of '{profile_id}': {exc}")

    for t in targets:
        try:
            urllib.request.urlopen(f"{br.cdp_url}/json/close/{t['id']}",
                                   timeout=2).read()
        except Exception:
            pass

    exited = False
    deadline = time.time() + grace
    while time.time() < deadline:
        if not _cdp_version(br.debug_port, timeout=0.5):
            exited = True
            break
        time.sleep(0.5)

    if not exited:
        logger.warning(f"[fp-browser] '{profile_id}' did not exit within "
                       f"{grace:.0f}s; terminating (session state may be stale)")
        if br.pid:
            try:
                os.kill(br.pid, 15)
            except Exception:
                pass

    if br.stop_relay:
        br.stop_relay()
    _clear_port_file(Path(br.user_data_dir))
    _RUNNING.pop(profile_id, None)
    logger.info(f"[fp-browser] closed '{profile_id}'")
    return True


def close_all(grace: float = 15.0) -> None:
    """Close every browser this process launched. Call on app shutdown."""
    for pid in list(_RUNNING):
        try:
            close_profile(pid, grace=grace)
        except Exception as exc:
            logger.warning(f"[fp-browser] closing '{pid}' failed: {exc}")


def running_profiles() -> dict:
    """Profiles this process currently has open, by id."""
    return dict(_RUNNING)
