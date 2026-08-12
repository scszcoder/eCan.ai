"""In-app WeChat QR login dialog for the CN desktop app.

Reuses the *proven* web login chain unchanged: the dialog hosts an
embedded browser pointed at the已备案域名 PHP entry
(``wechat_login.php``).  The user scans the QR with WeChat; WeChat
redirects to the registered PHP callback, which does the code→token
exchange (APP_SECRET stays on the server) and provisions a CloudBase user
via ``CLOUDBASE_WECHAT_PROVISION_URL``, then writes ``token`` /
``username`` into the page's ``localStorage`` and redirects to
``hello_world.php``.

This dialog watches the embedded page and, once it lands back on the
site's origin with an authenticated ``localStorage``, reads ``token`` /
``username`` and hands them to the caller.  The caller finalizes the
session through the SAME backend path as email/AWS login
(``cloudbase_finalize_session`` → ``_build_login_response``), so the
desktop obtains an access token used for API authentication exactly like
the AWS/Cognito login does.

Threading: everything here MUST run on the Qt GUI thread (the qasync main
loop).  IPC handlers run off that thread, so they call
``open_wechat_login`` via ``asyncio.run_coroutine_threadsafe(...,
AppContext.main_loop)`` and block on the returned future.
"""
from __future__ import annotations

import asyncio
import json
from typing import Optional
from urllib.parse import urlsplit

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtWidgets import QDialog, QVBoxLayout, QWidget
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage

from utils.logger_helper import logger_helper as logger

# JS that snapshots the three keys the PHP callback writes on success.
_READ_STORAGE_JS = (
    "(function(){try{return JSON.stringify({"
    "token:localStorage.getItem('token')||'',"
    "username:localStorage.getItem('username')||'',"
    "auth:localStorage.getItem('isAuthenticated')||''"
    "});}catch(e){return '{}';}})()"
)

_POLL_INTERVAL_MS = 600
_DEFAULT_TIMEOUT_S = 300


def _host_of(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower()
    except Exception:
        return ""


class WechatLoginDialog(QDialog):
    """Modal dialog hosting the WeChat QR login page in an embedded view.

    Emits its result through ``self.result_data`` (a dict with ``token`` /
    ``username``) or ``None`` on cancel/timeout, and resolves the asyncio
    future handed to :func:`open_wechat_login`.
    """

    def __init__(self, entry_url: str, future: "asyncio.Future",
                 timeout_s: int = _DEFAULT_TIMEOUT_S, parent=None):
        super().__init__(parent)
        self._entry_url = entry_url
        self._entry_host = _host_of(entry_url)
        self._future = future
        self._resolved = False
        self.result_data: Optional[dict] = None

        self.setWindowTitle("微信扫码登录")
        self.setWindowModality(Qt.ApplicationModal)
        self.resize(480, 640)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Off-the-record profile: fresh localStorage/cookies each time, so a
        # token we read is from THIS login (never a stale prior session), and
        # nothing is persisted to disk after the dialog closes.
        self._profile = QWebEngineProfile(self)  # no storage name => OTR
        self._view = QWebEngineView(self)
        self._page = QWebEnginePage(self._profile, self._view)
        self._view.setPage(self._page)
        layout.addWidget(self._view)

        self._view.loadFinished.connect(self._on_load_finished)

        # Poll timer: the PHP callback writes localStorage then redirects, so
        # we re-check on a short interval as well as on each loadFinished.
        self._poll = QTimer(self)
        self._poll.setInterval(_POLL_INTERVAL_MS)
        self._poll.timeout.connect(self._check_storage)

        # Hard timeout so a stuck/abandoned scan doesn't hang the caller.
        self._timeout = QTimer(self)
        self._timeout.setSingleShot(True)
        self._timeout.setInterval(max(10, int(timeout_s)) * 1000)
        self._timeout.timeout.connect(self._on_timeout)

        self._view.load(QUrl(self._entry_url))
        self._poll.start()
        self._timeout.start()

    # ── page events ─────────────────────────────────────────────────────
    def _on_load_finished(self, ok: bool) -> None:
        if not ok:
            logger.debug("[WechatLogin] page load reported failure (continuing)")
        self._check_storage()

    def _check_storage(self) -> None:
        if self._resolved:
            return
        # localStorage is per-origin — only read when we're back on the
        # site's origin (not while on open.weixin.qq.com scanning).
        cur_host = _host_of(self._view.url().toString())
        if not cur_host or self._entry_host not in cur_host:
            return
        self._page.runJavaScript(_READ_STORAGE_JS, self._on_storage_read)

    def _on_storage_read(self, raw) -> None:
        if self._resolved:
            return
        try:
            data = json.loads(raw) if isinstance(raw, str) and raw else {}
        except Exception:
            data = {}
        token = str(data.get("token") or "").strip()
        auth = str(data.get("auth") or "").strip().lower()
        if token and auth in ("true", "1", "yes"):
            username = str(data.get("username") or "").strip()
            logger.info(
                f"[WechatLogin] captured session token (len={len(token)}) "
                f"for username={username!r}"
            )
            self._resolve({"token": token, "username": username})

    def _on_timeout(self) -> None:
        logger.warning("[WechatLogin] login timed out; closing dialog")
        self._resolve(None)

    # ── resolution ──────────────────────────────────────────────────────
    def _resolve(self, result: Optional[dict]) -> None:
        if self._resolved:
            return
        self._resolved = True
        self.result_data = result
        try:
            self._poll.stop()
            self._timeout.stop()
        except Exception:
            pass
        if not self._future.done():
            # We're on the GUI/qasync loop thread already; set directly.
            self._future.set_result(result)
        self.accept() if result else self.reject()

    def closeEvent(self, event) -> None:  # user clicked the window ✕
        if not self._resolved:
            logger.info("[WechatLogin] dialog closed by user before completion")
            self._resolve(None)
        super().closeEvent(event)


async def open_wechat_login(entry_url: str,
                            timeout_s: int = _DEFAULT_TIMEOUT_S) -> Optional[dict]:
    """Open the WeChat login dialog and await its result.

    MUST be awaited on the Qt GUI (qasync) loop.  Returns
    ``{"token": ..., "username": ...}`` on success, ``None`` on
    cancel/timeout.
    """
    loop = asyncio.get_running_loop()
    future: "asyncio.Future" = loop.create_future()

    # get_main_window() is None during login, but returns the MainWindow
    # *controller* (a plain class, not a QWidget) if called post-login — which
    # can't be a QDialog parent. Only use it when it's actually a QWidget.
    parent = None
    try:
        from app_context import AppContext
        candidate = AppContext.get_main_window()
        if isinstance(candidate, QWidget):
            parent = candidate
    except Exception:
        parent = None

    dialog = WechatLoginDialog(entry_url, future, timeout_s=timeout_s, parent=parent)
    dialog.show()
    dialog.raise_()
    dialog.activateWindow()
    try:
        return await future
    finally:
        try:
            dialog.deleteLater()
        except Exception:
            pass
