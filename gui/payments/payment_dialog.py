"""In-app payment dialog for the CN desktop app (Alipay / WeChat Pay).

Reuses the *proven* web payment flow verbatim (the same approach as
``gui/auth/wechat_login_dialog.py``): the dialog hosts an embedded
browser pointed at the payment entry page (``payment_config.entry_url``,
e.g. ``…/cn/payment-test/index.php``). That page already offers both
Alipay and WeChat Pay, creates a real order server-side (merchant secret
stays on the server), redirects to the Alipay cashier or renders a WeChat
NATIVE QR, and polls ``payment-status.php`` — showing a ``#state`` element
that becomes ``success`` / ``failed`` on the server-verified result.

This dialog watches that ``#state`` element (works on both the WeChat QR
page and the index status page) and resolves when the payment reaches a
terminal state, so the app can refresh the account afterward.

Threading: everything runs on the Qt GUI (qasync main loop). IPC handlers
run off that thread and invoke ``open_payment`` via
``asyncio.run_coroutine_threadsafe(..., AppContext.main_loop)``.
"""
from __future__ import annotations

import asyncio
from typing import Optional
from urllib.parse import urlsplit, parse_qs

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtWidgets import QDialog, QVBoxLayout, QWidget
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage

from utils.logger_helper import logger_helper as logger

# Reads the payment page's own status element. Both wechat-start.php's QR
# page and index.php's status section render `<p id="state">` and set its
# className to 'success'/'failed' from the server-verified poll.
_READ_STATE_JS = (
    "(function(){var e=document.getElementById('state');"
    "if(!e)return '';var c=(e.className||'').toLowerCase();"
    "if(c.indexOf('success')>=0)return 'SUCCESS';"
    "if(c.indexOf('failed')>=0)return 'FAILED';return 'PENDING';})()"
)

_POLL_INTERVAL_MS = 1500
_DEFAULT_TIMEOUT_S = 600  # payments can take a few minutes (order expires 30m)


def _order_id_from_url(url: str) -> str:
    try:
        qs = parse_qs(urlsplit(url).query)
        val = qs.get("order_id", [""])[0]
        return str(val or "")
    except Exception:
        return ""


class PaymentDialog(QDialog):
    """Modal dialog hosting the payment entry page in an embedded view.

    Resolves the asyncio future with ``{"status": "SUCCESS"|"FAILED",
    "order_id": <str>}`` on a terminal payment state, or ``None`` on
    cancel/timeout.
    """

    def __init__(self, entry_url: str, future: "asyncio.Future",
                 timeout_s: int = _DEFAULT_TIMEOUT_S, parent=None):
        super().__init__(parent)
        self._future = future
        self._resolved = False
        self._order_id = ""

        self.setWindowTitle("充值支付")
        self.setWindowModality(Qt.ApplicationModal)
        self.resize(560, 720)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Off-the-record profile so each top-up starts with clean cookies/
        # storage and nothing persists to disk after the dialog closes.
        self._profile = QWebEngineProfile(self)
        self._view = QWebEngineView(self)
        self._page = QWebEnginePage(self._profile, self._view)
        self._view.setPage(self._page)
        layout.addWidget(self._view)

        self._view.urlChanged.connect(self._on_url_changed)

        self._poll = QTimer(self)
        self._poll.setInterval(_POLL_INTERVAL_MS)
        self._poll.timeout.connect(self._check_state)

        self._timeout = QTimer(self)
        self._timeout.setSingleShot(True)
        self._timeout.setInterval(max(30, int(timeout_s)) * 1000)
        self._timeout.timeout.connect(self._on_timeout)

        self._view.load(QUrl(entry_url))
        self._poll.start()
        self._timeout.start()

    def _on_url_changed(self, url: QUrl) -> None:
        # Capture the order id when the page carries it (e.g. the Alipay
        # return → index.php?order_id=…). Best-effort; not required.
        oid = _order_id_from_url(url.toString())
        if oid:
            self._order_id = oid

    def _check_state(self) -> None:
        if self._resolved:
            return
        self._page.runJavaScript(_READ_STATE_JS, self._on_state_read)

    def _on_state_read(self, state) -> None:
        if self._resolved:
            return
        s = str(state or "").upper()
        if s == "SUCCESS":
            logger.info(f"[Payment] order {self._order_id!r} reported SUCCESS")
            self._resolve({"status": "SUCCESS", "order_id": self._order_id})
        elif s == "FAILED":
            logger.info(f"[Payment] order {self._order_id!r} reported FAILED")
            self._resolve({"status": "FAILED", "order_id": self._order_id})

    def _on_timeout(self) -> None:
        logger.warning("[Payment] dialog timed out; closing")
        self._resolve(None)

    def _resolve(self, result: Optional[dict]) -> None:
        if self._resolved:
            return
        self._resolved = True
        try:
            self._poll.stop()
            self._timeout.stop()
        except Exception:
            pass
        if not self._future.done():
            self._future.set_result(result)
        self.accept() if result else self.reject()

    def closeEvent(self, event) -> None:  # user closed the window
        if not self._resolved:
            logger.info("[Payment] dialog closed by user before completion")
            self._resolve(None)
        super().closeEvent(event)


async def open_payment(entry_url: str,
                       timeout_s: int = _DEFAULT_TIMEOUT_S) -> Optional[dict]:
    """Open the payment dialog and await its result.

    MUST be awaited on the Qt GUI (qasync) loop. Returns
    ``{"status": "SUCCESS"|"FAILED", "order_id": <str>}`` on a terminal
    state, ``None`` on cancel/timeout.
    """
    loop = asyncio.get_running_loop()
    future: "asyncio.Future" = loop.create_future()

    # AppContext.get_main_window() returns the MainWindow *controller* (a plain
    # class, not a QWidget), so it can't be a QDialog parent. Only use it if
    # it's actually a QWidget; otherwise a top-level ApplicationModal dialog.
    parent = None
    try:
        from app_context import AppContext
        candidate = AppContext.get_main_window()
        if isinstance(candidate, QWidget):
            parent = candidate
    except Exception:
        parent = None

    dialog = PaymentDialog(entry_url, future, timeout_s=timeout_s, parent=parent)
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
