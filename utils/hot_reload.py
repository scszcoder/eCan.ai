import asyncio
import importlib
import os
import sys
import threading
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from utils.logger_helper import logger_helper as logger

def _is_module_loaded(module_name):
    """Check if module is already loaded"""
    return module_name in sys.modules

def _reload_module(module_name):
    """Reload specified module"""
    if not _is_module_loaded(module_name):
        logger.info(f"Module {module_name} is not loaded, skipping reload.")
        return

    try:
        logger.info(f"Reloading module: {module_name}")
        module = sys.modules[module_name]
        importlib.reload(module)
        logger.info(f"Successfully reloaded module: {module_name}")
    except Exception as e:
        logger.error(f"Error reloading module {module_name}: {e}")

class PythonFileEventHandler(FileSystemEventHandler):
    """Handle .py file modification events"""

    def __init__(self, base_path):
        super().__init__()
        self.base_path = Path(base_path).resolve()

    def on_modified(self, event):
        if event.is_directory or not event.src_path.endswith(".py"):
            return

        file_path = Path(event.src_path).resolve()
        logger.debug(f"File modified: {file_path}")

        # Convert file path to module name
        # Example: /path/to/project/utils/hot_reload.py -> utils.hot_reload
        try:
            # Get path relative to project root directory
            relative_path = file_path.relative_to(self.base_path)
            # Remove .py suffix
            module_path = relative_path.with_suffix('')
            # Replace path separator with .
            module_name = str(module_path).replace(os.path.sep, '.')
            _reload_module(module_name)
        except ValueError:
            logger.warning(f"Modified file {file_path} is not inside the project base path {self.base_path}.")
        except Exception as e:
            logger.error(f"Error processing file modification: {e}")


def start_watching(watch_paths, loop):
    """
    Start file monitoring in a separate thread.

    :param watch_paths: List of directories to monitor.
    :param loop: asyncio event loop, used to schedule reload tasks in the loop (if needed).
                   Current implementation reloads directly, loop is not used.
    """
    project_root = Path(__file__).resolve().parent.parent  # Project root directory (ecan.ai)

    event_handler = PythonFileEventHandler(base_path=project_root)
    observer = Observer()

    for path in watch_paths:
        full_path = os.path.join(project_root, path)
        if os.path.isdir(full_path):
            observer.schedule(event_handler, full_path, recursive=True)
            logger.info(f"Start watching directory for hot-reload: {full_path}")
        else:
            logger.warning(f"Directory not found for hot-reloading: {full_path}")

    def run_observer():
        observer.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()

    thread = threading.Thread(target=run_observer, daemon=True)
    thread.start()
    logger.info("Hot-reload file watcher thread started.") 