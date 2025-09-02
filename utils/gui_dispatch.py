from __future__ import annotations

from PySide6 import QtCore
import concurrent.futures as cf
from typing import Any, Callable, Optional
from utils.logger_helper import logger_helper as logger


class _Invoker(QtCore.QObject):
    """A tiny bridge to run callables on the Qt main thread.

    Usage (from any worker thread):
        result = run_on_main_thread(lambda: some_qt_call())
    or fire-and-forget:
        post_to_main_thread(lambda: some_qt_call())
    """

    _call = QtCore.Signal(object, object)  # (fn: Callable[[], Any], future: Future)

    def __init__(self) -> None:
        super().__init__()
        # Ensure slot runs in the GUI thread
        self._call.connect(self._on_call, QtCore.Qt.QueuedConnection)

    @QtCore.Slot(object, object)
    def _on_call(self, fn: Callable[[], Any], fut: Optional[cf.Future]) -> None:
        try:
            res = fn()
            if fut is not None and not fut.done():
                fut.set_result(res)
        except Exception as e:
            logger.error(f"Error in dispatched function '{fn.__name__}': {e}", exc_info=True)
            if fut is not None and not fut.done():
                fut.set_exception(e)


# Singleton invoker instance
_invoker: Optional[_Invoker] = None


def _get_invoker() -> _Invoker:
    global _invoker
    if _invoker is None:
        _invoker = _Invoker()
    return _invoker


def run_on_main_thread(fn: Callable[[], Any], timeout: Optional[float] = None) -> Any:
    """Execute fn on the Qt main thread and wait for the result.

    - fn: a no-arg callable to execute on the GUI thread
    - timeout: optional seconds to wait; None = wait indefinitely
    """
    fut: cf.Future = cf.Future()
    _get_invoker()._call.emit(fn, fut)
    return fut.result(timeout)


def post_to_main_thread(fn: Callable[[], Any]) -> None:
    """Schedule fn to run on the Qt main thread (fire-and-forget)."""
    _get_invoker()._call.emit(fn, None)



def init_gui_dispatch() -> None:
    """Initialize the invoker on the main thread."""
    _get_invoker()
