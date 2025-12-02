#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import colorlog
from logging.handlers import RotatingFileHandler
import os
import sys
import signal
import io
from config.constants import APP_NAME
from config.app_info import app_info
import traceback

# ====== 集成 TRACE 日志等级 ======
TRACE_LEVEL_NUM = 5
logging.addLevelName(TRACE_LEVEL_NUM, "TRACE")

def trace(self, message, *args, **kws):
    if self.isEnabledFor(TRACE_LEVEL_NUM):
        self._log(TRACE_LEVEL_NUM, message, args, **kws)
logging.Logger.trace = trace
# ====== END ======


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

        self.setup(APP_NAME, appdata_path + "/runlogs/" + APP_NAME + ".log", logging.DEBUG)

        # 初始化崩溃日志功能
        self._setup_crash_logging()

    def setup(self, log_name, log_file, level):
        self.logger = logging.getLogger(log_name)
        self.logger.setLevel(level)
        self.logger.propagate = False

        if not any(isinstance(h, logging.StreamHandler) for h in self.logger.handlers):
            console_formatter = colorlog.ColoredFormatter(
                "%(log_color)s%(asctime)s - %(name)s - %(levelname)s - %(message)s",
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

            # 创建支持 UTF-8 的控制台处理器
            # 在 PyInstaller 环境中，sys.stdout 可能为 None
            if sys.stdout is not None:
                if sys.platform == "win32" and hasattr(sys.stdout, 'buffer'):
                    # Windows 系统需要特殊处理 UTF-8 编码
                    try:
                        console_handler = logging.StreamHandler(
                            io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
                        )
                    except (AttributeError, OSError):
                        # 如果失败，使用标准处理器
                        console_handler = logging.StreamHandler()
                else:
                    console_handler = logging.StreamHandler()

                console_handler.setFormatter(console_formatter)
                self.logger.addHandler(console_handler)
            # 如果 sys.stdout 为 None（PyInstaller windowed 模式），跳过控制台处理器

        if not any(isinstance(h, RotatingFileHandler) for h in self.logger.handlers):
            file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            # 确保文件处理器使用 UTF-8 编码
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=1024 * 1024 * 10,
                backupCount=5,
                encoding='utf-8',
                errors='replace'
            )
            file_handler.setFormatter(file_formatter)
            self.logger.addHandler(file_handler)

    def _safe_encode_message(self, message):
        """Safely encode message, handle emoji and special characters"""
        if not isinstance(message, str):
            message = str(message)

        # On Windows systems, if encoding issues occur, replace problematic characters
        # Only check encoding if we're on Windows and message might have issues
        if sys.platform == "win32":
            # Quick check: if message is pure ASCII, skip encoding check
            try:
                message.encode('ascii')
                return message  # Pure ASCII, no encoding issues
            except UnicodeEncodeError:
                pass  # Contains non-ASCII, need to check GBK
            
            try:
                # Try encoding to GBK, if it fails then replace characters
                message.encode('gbk')
            except UnicodeEncodeError:
                # Replace characters that cannot be encoded
                message = message.encode('gbk', errors='replace').decode('gbk', errors='replace')

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

        # Get log file path
        log_path = getattr(self, 'logger', None)
        if log_path and hasattr(log_path, 'handlers'):
            for handler in log_path.handlers:
                if isinstance(handler, RotatingFileHandler):
                    log_file = handler.baseFilename
                    break
            else:
                log_file = "Unknown"
        else:
            log_file = "Unknown"

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


logger_helper = LoggerHelper()

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