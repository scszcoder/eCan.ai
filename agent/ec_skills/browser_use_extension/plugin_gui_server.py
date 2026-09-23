"""
Plugin GUI Server — tiny localhost-only HTTP server for plugin iframe assets.

Why a separate origin
---------------------
The Plugins page mounts each plugin's GUI in a sandboxed ``<iframe>``.
Sandboxed iframes are most secure when their content lives on a
*different origin* from the host app, so postMessage is the only cross-
boundary channel.  Plugin authors get a stable URL
(``http://127.0.0.1:<port>/p/<bundle>/<slot.html>``) without us having
to bundle their HTML into the React app.

Security
--------
- Binds to ``127.0.0.1`` only.  Random port picked at boot.
- Strict CSP header sent on every response.
- Path-traversal hardened: requests must match ``/p/<bundle>/<file>``
  where bundle is a known plugin and file resolves under that bundle's
  ``gui/`` directory.  Symlinks and ``..`` are rejected.
- File types served: ``html, js, mjs, css, json, png, jpg, jpeg, gif,
  svg, ico, woff, woff2``.  Everything else is 415.

API
---
- ``start(port: int = 0)`` — launch the server in a background thread.
  ``port=0`` lets the OS pick.  Returns the bound port.
- ``stop()`` — graceful shutdown.
- ``get_gui_url(bundle, slot)`` — returns
  ``http://127.0.0.1:<port>/p/<bundle>/<slot_entry>`` when the bundle's
  manifest declares ``gui.slots[slot]``, else ``None``.
"""

from __future__ import annotations

import http.server
import logging
import mimetypes
import os
import socketserver
import threading
from pathlib import Path
from typing import Optional

from . import plugin_registry
from .hook_loader import _read_manifest_file  # type: ignore[attr-defined]

from utils.logger_helper import logger_helper as logger  # CN app logger is "eCan.cn"


_ALLOWED_EXTS = {
    ".html", ".htm", ".js", ".mjs", ".css", ".json",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",
    ".woff", ".woff2",
}

# The host mounts us with ``sandbox="allow-scripts"`` and deliberately WITHOUT
# ``allow-same-origin``, so the document gets an **opaque origin**. CSP's
# ``'self'`` resolves to the document's origin, and an opaque origin matches
# nothing — so a policy written with ``'self'`` blocks every script the page
# loads, including bridge.js, and the panel is inert with no error we log.
# Source expressions match the RESOURCE URL rather than the document origin, so
# naming our own origin explicitly works under the sandbox and keeps the policy
# just as tight. ``{origin}`` is substituted per request in ``_send_common``.
_DEFAULT_CSP = (
    "default-src 'none'; "
    "script-src {origin}; "
    "style-src {origin} 'unsafe-inline'; "
    "img-src {origin} data:; "
    "font-src {origin} data:; "
    "connect-src 'none'; "
    # The packaged app loads its UI from a LOCAL FILE
    # (web_engine_view.load_local_file -> file:///.../gui_v2/dist/index.html),
    # so our ancestor's scheme is `file:`. A bare `*` does NOT cover that:
    # per CSP3 it matches only network schemes (http/https/ws/wss) or a scheme
    # equal to the protected resource's own. The customer's console said so
    # outright:
    #
    #   Refused to frame 'http://127.0.0.1:52348/' because an ancestor violates
    #   the following Content Security Policy directive: "frame-ancestors *".
    #   Note that '*' matches only URLs with network schemes ... The scheme
    #   'http:' must be added explicitly.
    #
    # That is the entire "works in dev, blank after install" difference: under
    # `pnpm dev` the ancestor is http://localhost:3000, a network scheme, so `*`
    # matches and the panel loads. Schemes are therefore listed explicitly.
    "frame-ancestors * file: http: https:; "
    "form-action 'none'; "
    "base-uri 'none'"
)


# ---------------------------------------------------------------------------
# Manifest helpers
# ---------------------------------------------------------------------------
def _read_gui_slots(bundle: str) -> dict[str, dict]:
    """Return ``manifest.gui.slots`` as a dict, or {} when absent/malformed."""
    entry = plugin_registry.get(bundle)
    if entry is None or not entry.install_path:
        return {}
    try:
        manifest = _read_manifest_file(Path(entry.install_path))
    except Exception:
        return {}
    gui = manifest.get("gui") if isinstance(manifest.get("gui"), dict) else None
    if not gui:
        return {}
    slots = gui.get("slots")
    if not isinstance(slots, dict):
        return {}
    out: dict[str, dict] = {}
    for name, cfg in slots.items():
        if isinstance(cfg, dict) and isinstance(cfg.get("entrypoint"), str):
            out[str(name)] = cfg
    return out


def _bundle_gui_dir(bundle: str) -> Optional[Path]:
    """Return ``<install_path>/gui/`` if it exists, else None."""
    entry = plugin_registry.get(bundle)
    if entry is None or not entry.install_path:
        return None
    gui_dir = Path(entry.install_path) / "gui"
    if not gui_dir.is_dir():
        return None
    return gui_dir.resolve()


# ---------------------------------------------------------------------------
# Request handler
# ---------------------------------------------------------------------------
class _Handler(http.server.BaseHTTPRequestHandler):
    """Serve plugin GUI assets with path-traversal hardening."""

    def log_message(self, format, *args):  # noqa: A002 (BaseHTTPRequestHandler signature)
        # Access lines stay at DEBUG so the eCan log stream doesn't get spammed.
        # Failures are surfaced by send_error() below instead of by sniffing a
        # status code out of this formatted string.
        logger.debug(f"[PluginGuiServer] {self.address_string()} - " + (format % args))

    def send_error(self, code, message=None, explain=None):  # noqa: D102
        # BaseHTTPRequestHandler logs the code but not WHY; the reason string
        # is the whole diagnostic value here (missing gui/, traversal, symlink,
        # unsupported type).
        logger.warning(
            f"[PluginGuiServer] {code} for {self.path!r}: {message!r}"
        )
        super().send_error(code, message, explain)

    def _csp(self) -> str:
        """CSP naming our own origin, because 'self' cannot work under the
        host's ``sandbox="allow-scripts"`` opaque origin (see _DEFAULT_CSP)."""
        return _DEFAULT_CSP.format(origin=f"http://127.0.0.1:{_PORT}")

    def end_headers(self):
        # Common headers applied to every response.
        self.send_header("Content-Security-Policy", self._csp())
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self):  # noqa: N802 (BaseHTTPRequestHandler)
        path = self.path.split("?", 1)[0].split("#", 1)[0]
        if not path.startswith("/p/"):
            self.send_error(404, "not a plugin asset URL")
            return
        try:
            _, _p, bundle, *rest = path.split("/")
        except Exception:
            self.send_error(400, "bad URL")
            return
        if not bundle or not rest:
            self.send_error(404, "missing bundle or asset")
            return
        # Reject obvious traversal patterns early.
        rel = "/".join(rest)
        if ".." in rel.split("/") or rel.startswith("/"):
            self.send_error(403, "path traversal denied")
            return

        gui_dir = _bundle_gui_dir(bundle)
        if gui_dir is None:
            self.send_error(404, "plugin not found or has no gui/")
            return

        target = (gui_dir / rel).resolve()
        # Ensure resolved path is still under gui_dir.
        try:
            target.relative_to(gui_dir)
        except ValueError:
            self.send_error(403, "path traversal denied")
            return

        if target.is_symlink():
            self.send_error(403, "symlinks not allowed")
            return
        if not target.is_file():
            self.send_error(404, "not found")
            return

        ext = target.suffix.lower()
        if ext not in _ALLOWED_EXTS:
            self.send_error(415, f"unsupported file type: {ext}")
            return

        ctype, _ = mimetypes.guess_type(str(target))
        if ctype is None:
            ctype = "application/octet-stream"
        try:
            data = target.read_bytes()
        except Exception as e:
            self.send_error(500, f"read failed: {e}")
            return

        # The DOCUMENT fetch is logged at INFO — one line per panel open, and
        # the only way to tell "the page loaded and its scripts did nothing"
        # from "the frame never requested anything at all". Those two have
        # completely different causes and the previous diagnostic pass could
        # not separate them: only failures were raised above DEBUG, so a
        # healthy 200 looked exactly like silence. Sub-resources (js/css) stay
        # at DEBUG to keep the stream quiet.
        if ext in (".html", ".htm"):
            logger.info(
                f"[PluginGuiServer] SERVED document {self.path!r} "
                f"({len(data)} bytes) — the frame did fetch the page"
            )
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class _ThreadingServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
_LOCK = threading.Lock()
_SERVER: Optional[_ThreadingServer] = None
_THREAD: Optional[threading.Thread] = None
_PORT: int = 0


def start(port: int = 0) -> int:
    """Start the GUI asset server. Idempotent — returns the live port either way."""
    global _SERVER, _THREAD, _PORT
    with _LOCK:
        if _SERVER is not None:
            return _PORT
        try:
            srv = _ThreadingServer(("127.0.0.1", port), _Handler)
        except Exception as e:
            logger.error(f"[PluginGuiServer] bind failed on port={port}: {e}")
            raise
        _SERVER = srv
        _PORT = srv.server_address[1]
        _THREAD = threading.Thread(
            target=srv.serve_forever,
            name="PluginGuiServer",
            daemon=True,
        )
        _THREAD.start()
    logger.info(f"[PluginGuiServer] listening on http://127.0.0.1:{_PORT}/")
    return _PORT


def stop() -> None:
    """Graceful shutdown. Idempotent."""
    global _SERVER, _THREAD, _PORT
    with _LOCK:
        srv = _SERVER
        _SERVER = None
        _PORT = 0
    if srv is not None:
        try:
            srv.shutdown()
            srv.server_close()
        except Exception as e:
            logger.warning(f"[PluginGuiServer] shutdown error: {e}")
    if _THREAD is not None:
        try:
            _THREAD.join(timeout=2.0)
        except Exception:
            pass


def port() -> int:
    """Return the listening port, or 0 if not started."""
    return _PORT


def get_gui_url(bundle: str, slot: str) -> Optional[str]:
    """Return the iframe URL for ``bundle``'s ``slot``, or None if not declared."""
    if _PORT == 0:
        return None
    slots = _read_gui_slots(bundle)
    cfg = slots.get(slot)
    if not cfg:
        return None
    entry = cfg.get("entrypoint")
    if not isinstance(entry, str) or not entry:
        return None
    # Author writes "gui/config.html" or "config.html" — strip leading
    # "gui/" since the URL bakes it in.
    if entry.startswith("gui/"):
        entry = entry[len("gui/") :]
    # Reject anything that already contains traversal.
    if ".." in entry.split("/") or entry.startswith("/"):
        return None

    # Pre-flight, logged at INFO because customers run at INFO and a panel that
    # fails to load is otherwise completely silent: the host gets a URL, the
    # iframe shows a broken-document icon, and nothing reaches eCan.log. We
    # still return the URL (the 404 is the honest answer if the file is gone) —
    # this only makes the cause visible on the machine where it happens, which
    # is the difference between diagnosing it and guessing at it.
    gui_dir = _bundle_gui_dir(bundle)
    if gui_dir is None:
        logger.warning(
            f"[PluginGuiServer] {bundle!r} slot={slot!r} declares "
            f"entrypoint={entry!r} but the bundle has no readable gui/ "
            f"directory — the panel will 404 and render blank"
        )
    else:
        target = gui_dir / entry
        logger.info(
            f"[PluginGuiServer] {bundle!r} slot={slot!r} -> {target} "
            f"(exists={target.is_file()})"
        )
        if not target.is_file():
            logger.warning(
                f"[PluginGuiServer] {bundle!r} slot={slot!r} entrypoint is "
                f"MISSING on disk: {target} — the panel will 404 and render "
                f"blank. In a packaged build this means the bundle's gui/ "
                f"files were not shipped."
            )
    return f"http://127.0.0.1:{_PORT}/p/{bundle}/{entry}"


def gui_slots(bundle: str) -> dict[str, dict]:
    """Public wrapper around the manifest reader; used by IPC handlers."""
    return dict(_read_gui_slots(bundle))


__all__ = ["start", "stop", "port", "get_gui_url", "gui_slots"]
