#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import colorlog
from logging.handlers import RotatingFileHandler, QueueHandler, QueueListener
from queue import Queue
import time
import os
import sys
import signal
import io
import atexit
from config.constants import APP_NAME, APP_LOG_FILE
from config.app_info import app_info
import traceback

# ====== 集成 TRACE 日志等级 ======
TRACE_LEVEL_NUM = 5
logging.addLevelName(TRACE_LEVEL_NUM, "TRACE")
logging.TRACE = TRACE_LEVEL_NUM

def trace(self, message, *args, **kws):
    if self.isEnabledFor(TRACE_LEVEL_NUM):
        self._log(TRACE_LEVEL_NUM, message, args, **kws)
logging.Logger.trace = trace
# ====== END ======


def _ws_capture_inline_env() -> str:
    """Read the live-chat WS-capture inline toggle from the environment.

    Canonical knob: ``ECAN_LIVE_CHAT_WS_CAPTURE_INLINE``.  Falls back to any
    legacy site-branded spelling still set by operator run-scripts
    (``ECAN_<SITE>_WS_CAPTURE_INLINE``, single-token site name), so existing
    configs keep working.  utils/ must not import agent.* (cycle risk),
    hence this tiny local scan instead of live_chat_env().
    """
    import re
    val = os.environ.get("ECAN_LIVE_CHAT_WS_CAPTURE_INLINE")
    if val is not None:
        return val
    pat = re.compile(r"^ECAN_[A-Z0-9]+_WS_CAPTURE_INLINE$")
    for key, value in os.environ.items():
        if pat.match(key):
            return value
    return ""


def _snapshot_log_on_version_change(log_file):
    """ws035: when the build tag changes between runs, preserve the PRIOR
    version's log (rename to ``<name>_<prevtag>_<ts>.log``) BEFORE the rotating
    handler opens a fresh file — so cross-version comparison isn't silently lost
    to the 5-slot count rotation. Best-effort; never blocks startup. Returns the
    current build tag (or ``'unknown'``)."""
    tag = "unknown"
    try:
        from config.build_info import get_version_string
        tag = (get_version_string() or "unknown").strip() or "unknown"
    except Exception:
        pass
    try:
        d = os.path.dirname(log_file) or "."
        base, ext = os.path.splitext(os.path.basename(log_file))
        sidecar = os.path.join(d, ".last_build_tag")
        prev = ""
        if os.path.exists(sidecar):
            with open(sidecar, "r", encoding="utf-8", errors="replace") as _fh:
                prev = _fh.read().strip()
        if prev and prev != tag and os.path.exists(log_file):
            _safe = "".join(c if (c.isalnum() or c in "._-") else "_" for c in prev)[:40]
            _dest = os.path.join(
                d, f"{base}_{_safe}_{time.strftime('%Y%m%d-%H%M%S')}{ext}")
            try:
                os.replace(log_file, _dest)
            except Exception:
                pass
        with open(sidecar, "w", encoding="utf-8", errors="replace") as _fh:
            _fh.write(tag)
    except Exception:
        pass
    return tag


class WindowsSafeRotatingFileHandler(RotatingFileHandler):
    """A RotatingFileHandler that handles Windows file locking gracefully."""

    def shouldRollover(self, record):
        retry_after = getattr(self, "_rollover_retry_after", 0)
        if retry_after and time.monotonic() < retry_after:
            return False
        return super().shouldRollover(record)

    def _rollover_to_timestamped_file(self):
        if getattr(self, "stream", None) is not None:
            try:
                self.stream.close()
            finally:
                self.stream = None

        if not os.path.exists(self.baseFilename):
            self.stream = self._open()
            return None

        timestamp = int(time.time() * 1000)
        fallback_path = f"{self.baseFilename}.{timestamp}.rollover"
        suffix = 1
        while os.path.exists(fallback_path):
            fallback_path = f"{self.baseFilename}.{timestamp}.{suffix}.rollover"
            suffix += 1

        self.rotate(self.baseFilename, fallback_path)
        if not self.delay:
            self.stream = self._open()
        return fallback_path
    
    def doRollover(self):
        """Perform rollover with retry logic for Windows file locking issues."""
        if sys.platform != "win32":
            return super().doRollover()
        
        max_retries = 3
        _last_err = None
        for attempt in range(max_retries):
            try:
                super().doRollover()
                self._rollover_retry_after = 0
                return
            except PermissionError as _perm_err:
                _last_err = _perm_err
                if attempt < max_retries - 1:
                    time.sleep(0.1 * (attempt + 1))
            except Exception as _other_err:
                _last_err = _other_err
                # Non-permission errors on Windows usually mean a stuck
                # rotation slot (e.g. `eCan.log.1` left behind by a prior
                # crashed rotation).  Move the blocking backup aside with
                # a timestamped suffix so the next retry proceeds.
                try:
                    import time as _rot_time
                    import os as _rot_os
                    target_1 = f"{self.baseFilename}.1"
                    if _rot_os.path.exists(target_1):
                        stuck_path = f"{target_1}.stuck-{int(_rot_time.time())}"
                        _rot_os.rename(target_1, stuck_path)
                        sys.stderr.write(
                            f"[WindowsSafeRotatingFileHandler] moved stuck "
                            f"{target_1!r} -> {stuck_path!r} to unblock rotation\n"
                        )
                except Exception:
                    pass
        try:
            fallback_path = self._rollover_to_timestamped_file()
            if fallback_path:
                self._rollover_retry_after = 0
                try:
                    sys.stderr.write(
                        f"[WindowsSafeRotatingFileHandler] fallback rollover "
                        f"used {fallback_path!r} for {self.baseFilename!r}\n"
                    )
                except Exception:
                    pass
                return
        except Exception as _fallback_err:
            _last_err = _fallback_err

        # All retries failed.  The stock RotatingFileHandler.doRollover
        # closes `self.stream` BEFORE attempting the rename, so a failed
        # rotation leaves the handler with a closed FD.  Subsequent
        # emit() calls then write to the dead FD and Python's logging
        # framework silently discards the records via handleError --
        # the exact symptom observed 2026-04-22 14:51:10 where eCan.log
        # went dark while the app kept running for several more minutes.
        # Make the failure visible AND guarantee we keep a live stream,
        # even if that means appending to the already-oversized file.
        self._rollover_retry_after = time.monotonic() + 30.0
        try:
            sys.stderr.write(
                f"[WindowsSafeRotatingFileHandler] rollover FAILED for "
                f"{self.baseFilename!r} after {max_retries} attempts: "
                f"{type(_last_err).__name__ if _last_err else 'Unknown'}: "
                f"{_last_err!s}. Continuing to append to current file.\n"
            )
        except Exception:
            pass
        try:
            if getattr(self, "stream", None) is None or getattr(self.stream, "closed", False):
                self.stream = self._open()
        except Exception as _reopen_err:
            try:
                sys.stderr.write(
                    f"[WindowsSafeRotatingFileHandler] could not reopen stream "
                    f"for {self.baseFilename!r}: {_reopen_err!s}\n"
                )
            except Exception:
                pass


class LoggerHelper:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(LoggerHelper, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized') and self._initialized:
            return
        self._initialized = True
        print("init logger helper object")
        appdata_path = app_info.appdata_path
        runlogs_dir = appdata_path + "/runlogs"
        if not os.path.isdir(runlogs_dir):
            os.mkdir(runlogs_dir)
            print("create runlogs directory ", runlogs_dir)
        else:
            print(f"runlogs {runlogs_dir} directory is existed")

        # Default to DEBUG in development, INFO in production; override via ECAN_LOG_LEVEL when needed.
        _env_level = os.environ.get("ECAN_LOG_LEVEL")
        if _env_level is None:
            # No env var set: use DEBUG for development
            import sys
            _is_dev = (
                getattr(sys, 'frozen', False) is False  # not PyInstaller bundle
                and os.environ.get("NODE_ENV") != "production"
                and os.environ.get("ECAN_ENV") != "production"
            )
            _env_level = "DEBUG" if _is_dev else "INFO"
        _env_level = _env_level.upper()
        if _env_level == "TRACE":
            _log_level = TRACE_LEVEL_NUM
        else:
            _log_level = getattr(logging, _env_level, logging.INFO)
        self.setup(APP_NAME, appdata_path + "/runlogs/" + APP_LOG_FILE, _log_level)

        # 初始化崩溃日志功能
        self._setup_crash_logging()

    def setup(self, log_name, log_file, level):
        self.logger = logging.getLogger(log_name)
        self.logger.setLevel(level)
        self.logger.propagate = False

        # Already set up with async queue — don't duplicate
        if any(isinstance(h, QueueHandler) for h in self.logger.handlers):
            return

        target_handlers = []

        console_formatter = colorlog.ColoredFormatter(
            "%(log_color)s%(asctime)s - %(name)s - %(levelname)s - %(message)s%(ecan_scope)s",
            log_colors={
                "DEBUG": "cyan",
                "INFO": "green",
                "WARNING": "yellow",
                "ERROR": "red",
                "CRITICAL": "bold_red",
                "TRACE": "white",
            },
            reset=True,
            secondary_log_colors={},
            style="%"
        )

        # In PyInstaller windowed mode sys.stdout may be None — skip console handler then.
        if sys.stdout is not None:
            if sys.platform == "win32" and hasattr(sys.stdout, 'buffer'):
                try:
                    console_handler = logging.StreamHandler(
                        io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
                    )
                except (AttributeError, OSError):
                    console_handler = logging.StreamHandler()
            else:
                console_handler = logging.StreamHandler()
            console_handler.setFormatter(console_formatter)
            target_handlers.append(console_handler)

        # ws035: preserve the prior build's log before opening the fresh one.
        self._build_tag = _snapshot_log_on_version_change(log_file)

        # Run-scope suffix ("[agent=… task=…]", utils/log_scope.py) — stamped on
        # each record by ScopeFilter in the EMITTING thread (on the QueueHandler),
        # rendered here. ScopedFormatter tolerates records without the stamp.
        from utils.log_scope import ScopeFilter as _ScopeFilter, ScopedFormatter as _ScopedFormatter
        file_formatter = _ScopedFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s%(ecan_scope)s')
        file_handler = WindowsSafeRotatingFileHandler(
            log_file,
            maxBytes=1024 * 1024 * 10,
            backupCount=5,
            encoding='utf-8',
            errors='replace'
        )
        file_handler.setFormatter(file_formatter)
        target_handlers.append(file_handler)
        # The file handler lives behind the QueueListener (not on self.logger),
        # so remember its path for get_crash_log_info() / the Help > 查看日志 viewer.
        self._log_file_path = file_handler.baseFilename

        # Async logging: callers enqueue records in ~μs; a dedicated listener thread
        # drains the queue to the real handlers. Worker threads no longer block
        # on the main thread's log lock / disk I/O.
        self._log_queue = Queue(-1)
        queue_handler = QueueHandler(self._log_queue)
        queue_handler.addFilter(_ScopeFilter())
        for _h in target_handlers:
            _h.addFilter(_ScopeFilter())  # safety net: records that bypass the queue
        self.logger.addHandler(queue_handler)

        self._log_listener = QueueListener(
            self._log_queue, *target_handlers, respect_handler_level=True
        )
        self._log_listener.start()
        atexit.register(self._log_listener.stop)

        # ws035: dedicated async sink for the high-volume live-chat WS frame
        # capture (the bundle-emitted [*-WS-CAP*] records on the "eCan.wscap"
        # logger) so it stops drowning the operational log. Same async
        # queue pattern (non-blocking — the capture runs on the CDP handler loop,
        # which must NOT block on disk I/O). Its own rotating file with a larger
        # budget for forensic retention. Reversible: ECAN_LIVE_CHAT_WS_CAPTURE_INLINE=1
        # (or a legacy site-branded alias) leaves capture unconfigured here so
        # it propagates back into the main log.
        if _ws_capture_inline_env() != "1":
            try:
                cap_logger = logging.getLogger("eCan.wscap")
                cap_logger.setLevel(logging.INFO)
                cap_logger.propagate = False
                if not any(isinstance(h, QueueHandler) for h in cap_logger.handlers):
                    cap_file = os.path.splitext(log_file)[0] + ".wscap.log"
                    cap_handler = WindowsSafeRotatingFileHandler(
                        cap_file,
                        maxBytes=1024 * 1024 * 20,
                        backupCount=5,
                        encoding='utf-8',
                        errors='replace'
                    )
                    cap_handler.setFormatter(file_formatter)
                    cap_handler.addFilter(_ScopeFilter())
                    self._cap_queue = Queue(-1)
                    cap_logger.addHandler(QueueHandler(self._cap_queue))
                    self._cap_listener = QueueListener(
                        self._cap_queue, cap_handler, respect_handler_level=True
                    )
                    self._cap_listener.start()
                    atexit.register(self._cap_listener.stop)
            except Exception:
                pass

        # ws035: stamp every fresh log with the build tag so a line's version is
        # always identifiable (pairs with the version snapshot above).
        try:
            self.logger.info(
                f"[SESSION] build={getattr(self, '_build_tag', 'unknown')} "
                f"log={os.path.basename(log_file)} "
                f"level={logging.getLevelName(level)} pid={os.getpid()}"
            )
        except Exception:
            pass

    def _safe_encode_message(self, message):
        """Coerce non-string messages. Encoding safety is handled by the
        handlers themselves (file handler uses UTF-8 with errors='replace',
        console stream is wrapped in a UTF-8 TextIOWrapper)."""
        if not isinstance(message, str):
            message = str(message)
        return message

    def _join_message_args(self, message, *args):
        """Join message and args into a single string"""
        def safe_str(x):
            try:
                return str(x)
            except Exception:
                return f"<Unprintable {type(x).__name__}>"

        # If message is string and args has one item and contains %, use native formatting
        if isinstance(message, str) and args and "%" in message:
            try:
                result = message % args
                return self._safe_encode_message(result)
            except Exception:
                pass  # If formatting fails, fall back to concatenation

        result = " ".join(safe_str(x) for x in (message,) + args)
        return self._safe_encode_message(result)

    def trace(self, message, *args, **kwargs):
        """Log trace message - only format if trace level is enabled"""
        if hasattr(self, 'logger') and self.logger.isEnabledFor(TRACE_LEVEL_NUM):
            msg = self._join_message_args(message, *args)
            self.logger.trace(msg, **kwargs)

    def debug(self, message, *args, **kwargs):
        """Log debug message - only format if debug level is enabled"""
        if hasattr(self, 'logger') and self.logger.isEnabledFor(logging.DEBUG):
            msg = self._join_message_args(message, *args)
            self.logger.debug(msg, **kwargs)

    def info(self, message, *args, **kwargs):
        """Log info message - only format if info level is enabled"""
        if hasattr(self, 'logger') and self.logger.isEnabledFor(logging.INFO):
            msg = self._join_message_args(message, *args)
            self.logger.info(msg, **kwargs)

    def warning(self, message, *args, **kwargs):
        """Log warning message - only format if warning level is enabled"""
        if hasattr(self, 'logger') and self.logger.isEnabledFor(logging.WARNING):
            msg = self._join_message_args(message, *args)
            self.logger.warning(msg, **kwargs)

    def error(self, message, *args, **kwargs):
        """Log error message - only format if error level is enabled"""
        if hasattr(self, 'logger') and self.logger.isEnabledFor(logging.ERROR):
            msg = self._join_message_args(message, *args)
            self.logger.error(msg, **kwargs)

    def critical(self, message, *args, **kwargs):
        """Log critical message - only format if critical level is enabled"""
        if hasattr(self, 'logger') and self.logger.isEnabledFor(logging.CRITICAL):
            msg = self._join_message_args(message, *args)
            self.logger.critical(msg, **kwargs)

    def exception(self, message, *args, **kwargs):
        """Log an error with the current exception's traceback (stdlib parity —
        modules that used a raw logging.Logger call this)."""
        if hasattr(self, 'logger') and self.logger.isEnabledFor(logging.ERROR):
            msg = self._join_message_args(message, *args)
            kwargs.setdefault('exc_info', True)
            self.logger.error(msg, **kwargs)

    def isEnabledFor(self, level):
        """Check if the underlying logger is enabled for the specified level.
        
        This method is required for compatibility with third-party libraries
        that may call isEnabledFor() directly on the logger instance.
        
        Args:
            level: Logging level to check (e.g., logging.DEBUG, logging.INFO)
            
        Returns:
            bool: True if logging is enabled for the specified level
        """
        if hasattr(self, 'logger') and self.logger:
            return self.logger.isEnabledFor(level)
        return False

    def _setup_crash_logging(self):
        """Setup crash logging functionality"""
        # Record environment information
        env_info = self._get_environment_info()
        self.info(f"Logger initialized - Environment: {env_info['environment']}")
        self.debug(f"Environment details: {env_info}")

    def _get_environment_info(self) -> dict:
        """Get environment information"""
        # Detect runtime environment
        environment = 'production' if getattr(sys, 'frozen', False) else 'development'

        # Get log file path. Since async logging, self.logger only carries a
        # QueueHandler — the RotatingFileHandler is owned by the QueueListener —
        # so look there too (the viewer showed "未找到日志文件" otherwise).
        log_file = "Unknown"
        candidates = list(getattr(getattr(self, 'logger', None), 'handlers', None) or [])
        candidates += list(getattr(getattr(self, '_log_listener', None), 'handlers', None) or [])
        for handler in candidates:
            if isinstance(handler, RotatingFileHandler):
                log_file = handler.baseFilename
                break
        else:
            stored = getattr(self, '_log_file_path', None)
            if stored:
                log_file = stored

        return {
            'environment': environment,
            'log_path': log_file,
            'executable': sys.executable,
            'frozen': getattr(sys, 'frozen', False),
            'platform': sys.platform,
            'app_name': APP_NAME,
        }

    def log_uncaught_exception(self, exc_type, exc_value, exc_traceback):
        """Log uncaught exceptions"""
        # Ignore keyboard interrupts
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return

        # Log exception information
        self.critical("=" * 60)
        self.critical("💥 UNCAUGHT EXCEPTION OCCURRED")
        self.critical("=" * 60)

        # Log environment information
        env_info = self._get_environment_info()
        self.critical(f"Environment: {env_info['environment']}")
        self.critical(f"Platform: {env_info['platform']}")
        self.critical(f"Executable: {env_info['executable']}")
        self.critical(f"Frozen: {env_info['frozen']}")

        # Log exception details
        self.critical(f"Exception Type: {exc_type.__name__}")
        self.critical(f"Exception Message: {str(exc_value)}")

        # Log complete stack trace
        self.critical("Stack Trace:")
        tb_lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
        for line in tb_lines:
            self.critical(line.rstrip())

        self.critical("=" * 60)

        # Call default exception handler (display error)
        sys.__excepthook__(exc_type, exc_value, exc_traceback)

    def install_crash_logger(self):
        """Install crash logger for both Python exceptions and system signals"""
        # Set global exception handler
        sys.excepthook = self.log_uncaught_exception

        # Setup signal handlers for system crashes
        self._setup_signal_handlers()

        self.info("🛡️  Crash logger installed successfully")

    def get_crash_log_info(self) -> dict:
        """Get crash log information"""
        env_info = self._get_environment_info()
        log_file = env_info['log_path']

        info = {
            'log_file': log_file,
            'log_exists': os.path.exists(log_file) if log_file != "Unknown" else False,
            'log_size': os.path.getsize(log_file) if log_file != "Unknown" and os.path.exists(log_file) else 0,
            'environment': env_info['environment'],
            'writable': os.access(os.path.dirname(log_file), os.W_OK) if log_file != "Unknown" else False,
        }

        return info

    def _setup_signal_handlers(self):
        """Setup signal handlers for system crashes"""
        def signal_crash_handler(signum, frame):
            """Handle system signals that indicate crashes"""
            signal_names = {
                signal.SIGSEGV: "SIGSEGV",
                signal.SIGABRT: "SIGABRT",
            }
            if hasattr(signal, 'SIGBUS'):
                signal_names[signal.SIGBUS] = "SIGBUS"

            signal_name = signal_names.get(signum, f"Signal {signum}")

            # Log the crash
            self.critical(f"FATAL CRASH: {signal_name} on {sys.platform}")

            # Force flush all handlers
            for handler in self.logger.handlers:
                handler.flush()

            # Write to crash file as backup
            try:
                crash_file = os.path.join(os.path.expanduser("~"), "eCan_crash.log")
                with open(crash_file, "a", encoding="utf-8") as f:
                    f.write(f"{__import__('datetime').datetime.now()}: FATAL CRASH: {signal_name}\n")
            except:
                pass

            # Restore default handler and re-raise
            signal.signal(signum, signal.SIG_DFL)
            os.kill(os.getpid(), signum)

        # Register signal handlers for common crash signals
        crash_signals = [signal.SIGSEGV, signal.SIGABRT]
        if hasattr(signal, 'SIGBUS'):
            crash_signals.append(signal.SIGBUS)

        for sig in crash_signals:
            try:
                signal.signal(sig, signal_crash_handler)
            except (OSError, ValueError):
                pass


class MCPClientDisconnectFilter(logging.Filter):
    """Filter out benign ClientDisconnect errors from MCP StreamableHTTP transport.
    
    These errors occur when clients cancel/disconnect during HTTP requests,
    which is normal behavior in HTTP/2 streaming scenarios (retries, duplicate requests, etc.).
    The MCP library logs these at ERROR level, but they don't indicate actual problems.
    """
    def filter(self, record):
        # Filter out ClientDisconnect errors from MCP streamable_http
        if record.name == 'mcp.server.streamable_http' and record.levelno == logging.ERROR:
            if 'ClientDisconnect' in record.getMessage():
                return False
        return True


logger_helper = LoggerHelper()

# Add MCP ClientDisconnect filter to suppress benign errors
mcp_disconnect_filter = MCPClientDisconnectFilter()
logger_helper.logger.addFilter(mcp_disconnect_filter)

# ====== Crash logging convenience functions ======
def install_crash_logger():
    """Install crash logger (global convenience function)"""
    return logger_helper.install_crash_logger()

def get_crash_log_info():
    """Get crash log information (global convenience function)"""
    return logger_helper.get_crash_log_info()

def get_environment_info():
    """Get environment information (global convenience function)"""
    return logger_helper._get_environment_info()

def get_log_path():
    """Get log file path (backward compatibility function)"""
    env_info = logger_helper._get_environment_info()
    return env_info['log_path']
# ====== END ======


def get_traceback(e, eType="Error"):
    traceback_info = traceback.extract_tb(e.__traceback__)
    # Extract the file name and line number from the last entry in the traceback
    if traceback_info:
        ex_stat = f"{eType}:" + traceback.format_exc() + " " + str(e)
    else:
        ex_stat = f"{eType}: traceback information not available:" + str(e)
    return ex_stat


def truncate_for_log(data, max_length: int = 500, suffix: str = "...") -> str:
    """
    Truncate data for logging to avoid excessively long log entries.
    
    Args:
        data: Any data to be logged (dict, list, str, etc.)
        max_length: Maximum length of the output string (default 500)
        suffix: Suffix to append when truncated (default "...")
    
    Returns:
        Truncated string representation of the data
    """
    try:
        if data is None:
            return "None"
        
        # Convert to string
        if isinstance(data, (dict, list)):
            import json
            try:
                text = json.dumps(data, ensure_ascii=False, default=str)
            except Exception:
                text = str(data)
        else:
            text = str(data)
        
        # Truncate if needed
        if len(text) > max_length:
            return text[:max_length - len(suffix)] + suffix + f" [truncated, total {len(text)} chars]"
        return text
    except Exception:
        return f"<error converting to string: {type(data).__name__}>"