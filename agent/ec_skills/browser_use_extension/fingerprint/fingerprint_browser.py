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


def _norm_dir(path) -> str:
    """Compare two user-data-dir strings without tripping on case or a
    trailing separator — Windows hands us both spellings."""
    return str(path).rstrip("\\/").lower()


def _data_dirs_on_port(port: int) -> list:
    """The ``--user-data-dir`` of every process listening on *port*.

    A debugging port is not proof of identity. Another Chromium -- the user's
    own browser, a leftover from other tooling -- can already be listening on
    it, and ``/json/version`` will answer happily from THAT browser. Driving it
    would mean the user's personal profile, with no proxy and their real IP.
    So we ask the operating system who owns the socket and what profile they
    opened, instead of trusting the port.
    """
    dirs = []
    try:
        import psutil
    except Exception:
        return dirs

    pids = set()
    try:
        for conn in psutil.net_connections(kind="inet"):
            if conn.laddr and conn.laddr.port == int(port) and conn.pid:
                pids.add(conn.pid)
    except (psutil.AccessDenied, OSError) as exc:
        logger.debug(f"[fp-browser] cannot enumerate sockets ({exc})")
        return dirs

    for pid in pids:
        try:
            for arg in (psutil.Process(pid).cmdline() or []):
                if arg.startswith("--user-data-dir="):
                    dirs.append((pid, arg.split("=", 1)[1]))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return dirs


def _ask_browser_to_quit(pid: int, user_data_dir: Path,
                         grace: float = 20.0) -> bool:
    """Ask the browser at *pid* to close itself, and wait for it to finish.

    For when the browser is ours but unreachable over CDP -- it lost its
    debugging port to another Chromium -- so the polite CDP close is not
    available, yet it still holds the profile directory and nothing can start
    until it lets go.

    This is a REQUEST, not a kill: on Windows ``taskkill`` without ``/F``
    posts WM_CLOSE to the window, and elsewhere SIGTERM does the same job.
    Chromium treats both as "the user closed me" and flushes cookies and
    localStorage on the way out -- the session being preserved is the entire
    point of the profile, so a forced kill is never attempted, not even as a
    fallback. If it will not go, we say so and let the user decide.

    Guarded twice over: the pid must still be a live process whose command
    line names THIS profile directory. A pid can be recycled between the scan
    and the call, and closing someone else's browser -- or worse, some other
    program entirely -- would be far worse than failing here.
    """
    try:
        import psutil
    except Exception:
        return False

    try:
        proc = psutil.Process(pid)
        argv = proc.cmdline() or []
    except Exception as exc:
        logger.debug(f"[fp-browser] pid {pid} is gone already ({exc})")
        return True

    owns_profile = any(
        a.startswith("--user-data-dir=")
        and _norm_dir(a.split("=", 1)[1]) == _norm_dir(user_data_dir)
        for a in argv
    )
    if not owns_profile:
        logger.warning(
            f"[fp-browser] refusing to close pid {pid}: it is not running "
            f"{user_data_dir} (the pid was probably recycled)"
        )
        return False

    logger.info(f"[fp-browser] asking pid {pid} to close (it holds "
                f"{user_data_dir} and cannot be reached over CDP)")
    try:
        if os.name == "nt":
            # No /F: this posts WM_CLOSE, which Chromium handles as a normal
            # window close and flushes its session. /F would be TerminateProcess.
            subprocess.run(["taskkill", "/PID", str(pid)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=10)
        else:
            proc.terminate()            # SIGTERM — Chromium exits cleanly
    except Exception as exc:
        logger.warning(f"[fp-browser] could not ask pid {pid} to close: {exc}")
        return False

    try:
        proc.wait(timeout=grace)
        logger.info(f"[fp-browser] pid {pid} closed; {user_data_dir} is free")
        return True
    except Exception:
        logger.warning(
            f"[fp-browser] pid {pid} did not close within {grace:.0f}s; "
            f"leaving it alone rather than forcing it"
        )
        return False


def _running_browser_for(user_data_dir: Path) -> Optional[dict]:
    """A Chromium already running *user_data_dir*, if one is.

    Asks the OS which process opened this profile rather than trusting the
    port file we wrote: that file records what we INTENDED, and it has been
    wrong every way it can be -- stale after a crash, pointing at a port a
    different browser won, left behind by a previous install.

    Returns ``{"pid", "port", "healthy"}``. ``healthy`` means the browser can
    actually be driven: its debugging port answers CDP and serves only this
    profile. An unhealthy one still matters, because it holds the profile
    directory and nothing else can start until it lets go.
    """
    try:
        import psutil
    except Exception:
        return None

    want = _norm_dir(user_data_dir)
    candidates = []
    for proc in psutil.process_iter(["cmdline"]):
        try:
            argv = proc.info.get("cmdline") or []
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

        dir_arg = next((a for a in argv if a.startswith("--user-data-dir=")), None)
        if not dir_arg or _norm_dir(dir_arg.split("=", 1)[1]) != want:
            continue

        # Chromium's renderers, GPU and utility processes all inherit
        # --user-data-dir, so most matches are NOT the browser. Only the
        # browser process has no --type=, and only it owns the window and the
        # debugging port -- asking a renderer to close does nothing at all,
        # which is exactly how a close request appeared to be ignored.
        if any(a.startswith("--type=") for a in argv):
            continue

        port_arg = next((a for a in argv
                         if a.startswith("--remote-debugging-port=")), None)
        try:
            port = int(port_arg.split("=", 1)[1]) if port_arg else 0
        except ValueError:
            port = 0

        healthy = bool(
            port
            and _cdp_version(port, timeout=1.0)
            and _port_serves_profile(port, user_data_dir) is not False
        )
        candidates.append({"pid": proc.pid, "port": port, "healthy": healthy})

    if not candidates:
        return None
    # A usable one wins; otherwise report the first, which is the one holding
    # the directory and therefore the one that has to go.
    return next((c for c in candidates if c["healthy"]), candidates[0])


def _port_serves_profile(port: int, user_data_dir: Path) -> Optional[bool]:
    """True if the only browser on *port* is running *user_data_dir*.

    None when we cannot tell (no psutil, or the OS refused the socket table) --
    the caller treats that as "cannot verify" rather than as a failure, since
    on a locked-down machine refusing every launch would be worse.
    """
    found = _data_dirs_on_port(port)
    if not found:
        return None
    want = _norm_dir(user_data_dir)
    foreign = [(pid, d) for pid, d in found if _norm_dir(d) != want]
    if foreign:
        for pid, d in foreign:
            logger.error(
                f"[fp-browser] port {port} is also served by pid {pid} running "
                f"{d} -- that is NOT this profile"
            )
        return False
    return True


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

    # Is a browser already running THIS profile? Ask the OS, not the port
    # file -- the file records what we intended, and it can be stale, or name
    # a port another browser won. The profile directory is the identity.
    existing = _running_browser_for(user_data_dir)
    if existing:
        recorded = _read_port_file(user_data_dir) or {}
        relay_port = int(recorded.get("relay_port") or 0)
        relay_dead = bool(relay_port) and not _port_open(relay_port)

        if existing["healthy"] and not relay_dead:
            # Loaded, reachable, and still egressing through its proxy: use it.
            logger.info(
                f"[fp-browser] '{profile_id}' is already running "
                f"(pid {existing['pid']}, port {existing['port']}); reusing it"
            )
            br = LaunchedBrowser(
                profile_id=profile_id,
                user_data_dir=str(user_data_dir),
                debug_port=existing["port"],
                cdp_url=f"http://127.0.0.1:{existing['port']}",
                pid=existing["pid"],
                attached=True,
            )
            _RUNNING[profile_id] = br
            return br

        # Running but not usable. Two reasons, and the response differs:
        why = ("its proxy relay is dead, so it has no proxy"
               if relay_dead else
               "its debugging port does not answer for this profile")
        logger.warning(
            f"[fp-browser] '{profile_id}' is running (pid {existing['pid']}) "
            f"but unusable: {why}. It also holds the profile directory, so it "
            f"has to go before a fresh one can start."
        )

        if existing["healthy"]:
            # We can still reach it, so close it the polite way -- which is
            # also what flushes the session the profile exists to keep.
            close_profile(profile_id)
        _clear_port_file(user_data_dir)

        still_there = _running_browser_for(user_data_dir)
        if still_there:
            # Unreachable over CDP, so ask the window to close instead. Not a
            # forced kill: Chromium flushes its session on a close request,
            # and that session is what the profile is for.
            _ask_browser_to_quit(still_there["pid"], user_data_dir)
            still_there = _running_browser_for(user_data_dir)

        if still_there:
            raise RuntimeError(
                f"'{profile_id}' is still open (pid {still_there['pid']}) and "
                f"would not close on request: {why}. Close that browser window "
                f"and run again -- the next launch picks a free port of its "
                f"own and will not collide."
            )

    port = int(debug_port) or _free_port()
    if _port_open(port, timeout=0.5):
        # Something already answers here. Launching anyway is how we ended up
        # driving the user's own Chrome: both processes bind, and /json/version
        # replies from whichever one wins.
        #
        # Step aside rather than fail, even when the port was asked for
        # explicitly. This browser's debugging port is an internal detail --
        # nothing outside this module ever connects to it, so a requested port
        # is a hint, not a contract. The user's own Chrome on 9228 is a real
        # setup that other skills drive; colliding with it is our problem to
        # avoid, not theirs to work around.
        taken = port
        port = _free_port()
        logger.warning(
            f"[fp-browser] port {taken} is already in use "
            f"({', '.join(d for _pid, d in _data_dirs_on_port(taken)) or 'unknown'}); "
            f"starting '{profile_id}' on {port} instead"
        )

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
            # Answering is not the same as being ours. Confirm the browser on
            # this port opened THIS profile before handing the endpoint out.
            serves = _port_serves_profile(port, user_data_dir)
            if serves is False:
                try:
                    proc.terminate()
                except Exception:
                    pass
                if stop_relay:
                    stop_relay()
                raise RuntimeError(
                    f"port {port} is served by a different browser than "
                    f"'{profile_id}'. Refusing to drive it: it would be "
                    f"someone else's profile, without this profile's proxy or "
                    f"fingerprint. Close whatever else is using {port} (often "
                    f"a Chrome started with --remote-debugging-port), or leave "
                    f"the node's CDP port on auto."
                )
            if serves is None:
                logger.warning(
                    f"[fp-browser] could not verify who owns port {port}; "
                    f"proceeding on the assumption it is ours"
                )
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
