"""Record a live site's traffic from the Browser Profiles page (no CLI needed).

A thin window over ``agent.ec_skills.browser_use_extension.site_probe``: start
a probe on a login whose browser is open, stop it, and hand back where the
capture is and what it saw. One probe per login at a time.
"""

import os
import subprocess
import sys
import threading
from typing import Any, Dict, Optional

from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response
from utils.logger_helper import logger_helper as logger

_lock = threading.Lock()
_runners: Dict[str, Any] = {}      # profile id -> ProbeRunner


def _brief(summary: Dict[str, Any]) -> Dict[str, Any]:
    """What the page shows: per socket, frame counts and the commonest shapes."""
    socks = summary.get("sockets") or {}
    return {
        "file": summary.get("file", ""),
        "sockets": [{"url": u, "recv": s.get("recv", 0), "sent": s.get("sent", 0),
                     "shapes": [sh for sh, _n in (s.get("shapes") or [])[:5]]}
                    for u, s in socks.items()],
        "apis": len(summary.get("apis") or []),
    }


@IPCHandlerRegistry.handler('site_probe.sites')
def handle_sites(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    from agent.ec_skills.browser_use_extension.site_probe import available_sites
    with _lock:
        running = {pid: {"site": r.probe.preset.name, "file": r.probe.path, "stats": dict(r.probe.stats)}
                   for pid, r in _runners.items() if r.running}
    return create_success_response(request, {"sites": available_sites(), "running": running})


@IPCHandlerRegistry.background_handler('site_probe.start')
def handle_start(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """params: {profile_id, site}"""
    p = params or {}
    pid, site = str(p.get('profile_id') or ''), str(p.get('site') or '')
    try:
        from agent.ec_skills.browser_use_extension.fingerprint import fingerprint_browser
        from agent.ec_skills.browser_use_extension.site_probe import ProbeRunner, load_preset
        st = fingerprint_browser.profile_status(pid)
        if not st.get("running"):
            return create_error_response(request, 'NOT_RUNNING',
                                         'Open this login first, sign in to the store, then record.')
        with _lock:
            if pid in _runners and _runners[pid].running:
                return create_error_response(request, 'ALREADY_RECORDING', 'Already recording this login.')
        runner = ProbeRunner(st["cdp_url"], load_preset(site))
        runner.start()
        with _lock:
            _runners[pid] = runner
        logger.info(f"[site-probe] recording {site} on login {pid!r} -> {runner.probe.path}")
        return create_success_response(request, {"file": runner.probe.path})
    except Exception as e:
        import traceback
        logger.error(f"[site-probe] start failed: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'PROBE_ERROR', str(e))


@IPCHandlerRegistry.background_handler('site_probe.stop')
def handle_stop(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """params: {profile_id}"""
    pid = str((params or {}).get('profile_id') or '')
    with _lock:
        runner = _runners.pop(pid, None)
    if runner is None:
        return create_error_response(request, 'NOT_RECORDING', 'This login is not being recorded.')
    try:
        return create_success_response(request, _brief(runner.stop()))
    except Exception as e:
        logger.error(f"[site-probe] stop failed: {e}")
        return create_error_response(request, 'PROBE_ERROR', str(e))


@IPCHandlerRegistry.handler('site_probe.open_folder')
def handle_open_folder(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    from agent.ec_skills.browser_use_extension.site_probe import default_out_dir
    folder = default_out_dir()
    os.makedirs(folder, exist_ok=True)
    try:
        if sys.platform.startswith('win'):
            os.startfile(folder)  # noqa: S606
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', folder])
        else:
            subprocess.Popen(['xdg-open', folder])
        return create_success_response(request, {'folder': folder})
    except Exception as e:
        return create_error_response(request, 'PROBE_ERROR', f"could not open {folder}: {e}")
