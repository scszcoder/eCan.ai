"""
微信扫码登录组件 (PySide6 WebView 方案)

适用于桌面 App，无需配置回调 URL，回调在本地 WebView 截获。

架构：
1. WebView 加载微信授权页面
2. 用户扫码授权后，微信回调到 redirect_uri
3. WebView 截获 redirect_uri，提取 code 参数
4. 用 code 调用后端完成登录

无需：
- ngrok
- 公网回调地址
- 微信开放平台配置 localhost

注意：Qt UI 操作必须在主线程中执行。``run_wechat_webview`` 会自动检测当前
线程，非主线程时通过 ``QMetaObject.invokeMethod`` 把 dialog 创建和显示
投递到主线程，并在当前线程阻塞等待结果。
"""

import threading
import traceback
from typing import Optional
from urllib.parse import parse_qs, urlparse

from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout
from PySide6.QtCore import Qt, Signal, Slot, QTimer, QMetaObject, QCoreApplication
from PySide6.QtGui import QFont

from gui.core.web_engine_view import WebEngineView
from utils.logger_helper import logger_helper as logger


class WeChatWebViewAuth(QDialog):
    """
    微信 WebView 扫码登录对话框

    使用 QWebEngineView 加载微信授权页面，截获回调 URL 获取 code。

    Signals:
        auth_completed(code: str, state: str): 授权成功，获取到 code
        auth_cancelled(): 用户取消登录
        auth_error(error: str): 授权失败
    """

    auth_completed = Signal(str, str)
    auth_cancelled = Signal()
    auth_error = Signal(str)

    def __init__(self, parent=None, *,
                 app_id: str,
                 redirect_uri: str,
                 state: str = "",
                 scope: str = "snsapi_login"):
        super().__init__(parent)
        self.app_id = app_id
        self.redirect_uri = redirect_uri
        self.state = state or f"wechat_desktop_{id(self)}"
        self.scope = scope

        self._setup_ui()

    def _setup_ui(self):
        """Setup UI components"""
        self.setWindowTitle("微信扫码登录")
        self.setMinimumSize(400, 500)
        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        title = QLabel("请使用微信扫码登录")
        title.setFont(QFont("", 14, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        self.web_view = WebEngineView(self)
        self.web_view.setMinimumSize(360, 400)
        layout.addWidget(self.web_view)

        self.status_label = QLabel("正在加载...")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: #666;")
        layout.addWidget(self.status_label)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.refresh_btn = QPushButton("刷新二维码")
        self.refresh_btn.clicked.connect(self._refresh)
        btn_layout.addWidget(self.refresh_btn)

        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)

        layout.addLayout(btn_layout)

        self.web_view.url_changed.connect(self._on_url_changed)
        self.web_view.load_error.connect(self._on_load_error)

    def _build_auth_url(self) -> str:
        """Build WeChat authorization URL"""
        base_url = "https://open.weixin.qq.com/connect/qrconnect"
        params = {
            "appid": self.app_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": self.scope,
            "state": self.state,
        }
        query = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{base_url}?{query}"

    def load_auth_url(self):
        """Load the WeChat authorization URL (must be called on Qt main thread)."""
        auth_url = self._build_auth_url()
        logger.info("[WeChatAuth] Loading authorization URL")
        self.status_label.setText("请使用微信扫码...")
        self.web_view.load_url(auth_url)

    @Slot(str)
    def _on_url_changed(self, url: str):
        """Handle URL changes, intercept callback with code"""
        logger.debug(f"[WeChatAuth] URL changed: {url}")

        parsed = urlparse(url)
        if parsed.scheme not in ('http', 'https'):
            return

        query_params = parse_qs(parsed.query)

        if 'code' in query_params:
            code = query_params['code'][0]
            state = query_params.get('state', [''])[0]

            if state == self.state:
                logger.info("[WeChatAuth] Authorization code received")
                self.status_label.setText("授权成功，正在登录...")
                self.auth_completed.emit(code, state)
                QTimer.singleShot(500, self.accept)
            else:
                logger.warning(f"[WeChatAuth] State mismatch: expected={self.state}, got={state}")
                self.auth_error.emit("State verification failed")
                self.status_label.setText("验证失败，请重试")

        elif 'error' in query_params:
            error = query_params.get('error_description', ['Unknown error'])[0]
            logger.error(f"[WeChatAuth] Authorization error: {error}")
            self.auth_error.emit(error)
            self.status_label.setText(f"授权失败: {error}")

    @Slot(str)
    def _on_load_error(self, error: str):
        """Handle load errors"""
        logger.error(f"[WeChatAuth] Load error: {error}")
        self.status_label.setText(f"加载失败: {error}")
        self.auth_error.emit(error)

    @Slot()
    def _refresh(self):
        """Refresh the QR code"""
        logger.info("[WeChatAuth] Refreshing QR code")
        self.status_label.setText("正在刷新...")
        self.web_view.reload_page()

    def closeEvent(self, event):
        """Handle dialog close"""
        logger.info("[WeChatAuth] Dialog closed by user")
        self.auth_cancelled.emit()
        super().closeEvent(event)


def _run_on_main_thread_sync(func) -> object:
    """Invoke ``func`` on the Qt main thread and block until it returns.

    Falls back to a direct call if already on the main thread, or if there is
    no Qt application instance (e.g. in headless tests).
    """
    app = QCoreApplication.instance()
    if app is None:
        return func()

    main_thread = app.thread()
    if threading.current_thread() is main_thread:
        return func()

    # Post to main thread via a QObject helper using BlockingQueuedConnection.
    from PySide6.QtCore import QObject

    class _Helper(QObject):
        def __init__(self):
            super().__init__()
            self.result = None

        @Slot()
        def run(self):
            try:
                self.result = func()
            except Exception as e:
                logger.error(f"[WeChatLogin] Main-thread runner error: {e}")
                logger.error(traceback.format_exc())
                self.result = e

    helper = _Helper()
    helper.moveToThread(main_thread)
    QMetaObject.invokeMethod(helper, "run", Qt.BlockingQueuedConnection)
    return helper.result


def run_wechat_webview(*,
                       app_id: str,
                       redirect_uri: str,
                       state: str = "",
                       scope: str = "snsapi_login") -> Optional[dict]:
    """Show the WeChat WebView login dialog and block until done.

    Safe to call from any thread — UI work is dispatched to the Qt main thread.

    Returns:
        ``{"code": "...", "state": "..."}`` on success, else ``None``.
    """
    def _show():
        dialog = WeChatWebViewAuth(
            app_id=app_id,
            redirect_uri=redirect_uri,
            state=state,
            scope=scope,
        )

        holder: dict = {}

        def on_completed(code: str, st: str):
            holder["code"] = code
            holder["state"] = st

        def on_error(error: str):
            logger.error(f"[WeChatLogin] Auth error: {error}")
            holder["error"] = error

        dialog.auth_completed.connect(on_completed)
        dialog.auth_error.connect(on_error)

        dialog.load_auth_url()
        dialog.exec()  # Modal; blocks main thread's event loop until closed.

        return holder.get("code")

    code = _run_on_main_thread_sync(_show)
    if isinstance(code, Exception):
        return None
    if not code:
        return None
    return {"code": code, "state": state or ""}
