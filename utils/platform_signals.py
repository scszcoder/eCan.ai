"""Cross-platform exit-signal handling for the shutdown lease.

The watchdog needs to know that the app is going away. ``atexit`` covers the
normal interpreter shutdown, but not:

* ``kill <pid>`` / SIGTERM on macOS and Linux;
* Ctrl+C in a terminal (SIGINT);
* Windows ``CTRL_BREAK_EVENT`` (SIGBREAK) and console Ctrl+C
  (``CTRL_C_EVENT``), which only a console-mode process can receive.

Windows has **no SIGTERM at all** — ``signal.signal(SIGTERM, ...)`` raises
``ValueError`` there. Every platform must therefore be probed individually,
and a refusal to install one handler must never prevent the others.

The handlers record the intent and then let the signal do what it would
have done anyway.

Installing a Python handler **replaces** the signal's previous disposition
(usually ``SIG_DFL``, i.e. "terminate the process"). A handler that merely
records the intent and returns therefore *swallows* the signal: the process
keeps running, ``SIGTERM`` no longer stops anything and Ctrl+C raises no
``KeyboardInterrupt``. So the handler restores the previous disposition and
re-delivers the signal to itself, and the process dies exactly as it would
have without a handler.
"""
from __future__ import annotations

import os as _os
import signal as _signal
import sys as _sys
from typing import Callable, Optional

from utils.logger_helper import logger_helper as logger

#: Signals we try, in order, on every platform. Entries that the platform
#: refuses are skipped individually.
_POSIX_SIGNALS = (("SIGTERM", "SIGTERM"), ("SIGINT", "SIGINT"))
_WINDOWS_SIGNALS = (("SIGBREAK", "SIGBREAK"),)


def _truthy(value: Optional[str]) -> bool:
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def install_exit_handlers(mark_fn: Callable[[str], None],
                           platform: Optional[str] = None,
                           respect_pytest: bool = True) -> list[str]:
    """Install the exit-signal handlers for *mark_fn*.

    ``mark_fn(name)`` is called with a signal name (``"SIGTERM"``,
    ``"SIGINT"``, ``"SIGBREAK"``) when the platform delivers one. It is
    expected not to raise; if it does, the error is swallowed — a signal
    handler that raises would replace the intended termination with a
    traceback.

    Returns the list of signal names that were actually installed.
    """
    plat = platform or _sys.platform

    if _truthy(_os.environ.get("ECAN_NO_EXIT_SIGNALS")):
        return []
    # Under pytest, replacing the real handlers would break Ctrl+C and the
    # test runner's own signal handling. ``respect_pytest=False`` is used by
    # the tests that exercise the installation itself.
    if respect_pytest and _os.environ.get("PYTEST_CURRENT_TEST"):
        return []

    targets = list(_POSIX_SIGNALS)
    if plat == "win32":
        targets += list(_WINDOWS_SIGNALS)

    installed: list[str] = []
    for name, attr in targets:
        sig = getattr(_signal, attr, None)
        if sig is None:
            # The signal does not exist on this host (e.g. SIGBREAK outside
            # Windows). The target platform still asked for it, but there is
            # nothing to register against.
            logger.debug(f"[ExitIntent] signal {name} not available on this platform")
            continue
        # Remember what the signal did *before* we replaced it. Restoring this
        # (rather than hard-coding SIG_DFL) keeps SIGINT's KeyboardInterrupt
        # behaviour and respects an app that had chosen SIG_IGN.
        try:
            previous = _signal.getsignal(sig)
        except Exception:
            previous = _signal.SIG_DFL
        try:
            _signal.signal(sig, _make_handler(name, mark_fn, previous))
            installed.append(name)
        except (ValueError, AttributeError, OSError, RuntimeError) as exc:
            # ValueError: the signal does not exist here (Windows SIGTERM) or
            #             we are not on the main thread.
            # RuntimeError: signal handlers can only be set from the main thread.
            logger.debug(f"[ExitIntent] signal {name} not installed: {exc}")
    return installed


def _restore_and_redeliver(signum, previous) -> None:
    """Put the signal's old disposition back and re-deliver the signal.

    This is the whole point of the handler: without it the signal is
    *consumed* by the Python handler and the process survives it.
    """
    try:
        _signal.signal(signum, previous if previous is not None else _signal.SIG_DFL)
    except Exception as exc:
        logger.debug(f"[ExitIntent] could not restore handler for {signum}: {exc}")
    try:
        _os.kill(_os.getpid(), signum)
    except Exception as exc:
        logger.debug(f"[ExitIntent] could not re-deliver {signum}: {exc}")


def _make_handler(name: str, mark_fn: Callable[[str], None], previous=None):
    def _handler(signum, frame=None):  # noqa: ARG001 - signal handler signature
        try:
            mark_fn(name)
        except Exception as exc:
            logger.debug(f"[ExitIntent] could not record {name}: {exc}")
        # Recording the intent is not enough: the handler replaced the
        # signal's default disposition, so the process would outlive the
        # signal. Restore the previous disposition and let the signal do
        # what it would have done anyway.
        _restore_and_redeliver(signum, previous)
    return _handler
