import sys
import os
import logging

def get_log_path():
    if sys.platform == 'win32':
        base = os.environ.get('APPDATA', os.path.expanduser('~'))
        log_dir = os.path.join(base, 'ecbot')
    else:
        base = os.path.expanduser('~')
        log_dir = os.path.join(base, 'Library', 'Application Support', 'ecbot')
    os.makedirs(log_dir, exist_ok=True)
    return os.path.join(log_dir, 'ecbot_crash.log')

log_file = get_log_path()
logging.basicConfig(
    filename=log_file,
    level=logging.ERROR,
    format='%(asctime)s %(levelname)s %(message)s'
)

def log_uncaught_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logging.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

def install_crash_logger():
    sys.excepthook = log_uncaught_exception