"""The local server must stay up: no self-shutdown after N requests, and when its thread
does die the health monitor must actually bring it back (with nest_asyncio applied app-wide,
asyncio.run in a fresh thread used to fail with "There is no current event loop")."""
import socket
import time
import urllib.request

import nest_asyncio
import pytest

from gui import LocalServer as ls


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _up(port):
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=2)
        return True
    except urllib.error.HTTPError:
        return True  # any HTTP answer means it is serving
    except Exception:
        return False


def _wait(cond, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cond():
            return True
        time.sleep(0.2)
    return False


@pytest.fixture
def manager():
    import asyncio
    old_policy = asyncio.get_event_loop_policy()
    nest_asyncio.apply()
    # main.py's order: nest_asyncio patches the default policy, then the app switches.
    if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    port = _free_port()
    m = ls.ServerManager(ls._EarlyMainWin(port))
    m.start_in_thread()
    yield m, port
    m.stop()
    asyncio.set_event_loop_policy(old_policy)


def test_server_does_not_retire_itself_after_n_requests(manager):
    m, _port = manager
    assert m.uvicorn_server.config.limit_max_requests is None


def test_a_dead_server_thread_is_restarted(manager):
    m, port = manager
    assert _wait(lambda: _up(port))
    first = m.server_thread
    m.uvicorn_server.should_exit = True  # dies without stop(): like the 1000-request exit
    assert _wait(lambda: m.server_thread is not first and m.server_ready.is_set() and _up(port))
