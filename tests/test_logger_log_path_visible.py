"""Help > 查看日志 regression: the log-file path must resolve even though the
RotatingFileHandler sits behind the async QueueListener (2026-09-04: the
viewer showed 未找到日志文件 because only self.logger.handlers were inspected)."""

import os

from utils.logger_helper import logger_helper, get_log_path, get_crash_log_info


def test_environment_info_finds_file_behind_queue_listener():
    info = logger_helper._get_environment_info()
    assert info["log_path"] != "Unknown"
    assert os.path.basename(info["log_path"]).endswith(".log")
    assert os.path.exists(info["log_path"])


def test_public_helpers_agree():
    assert get_log_path() == logger_helper._get_environment_info()["log_path"]
    info = get_crash_log_info()  # what gui/log_viewer.py reads
    assert info["log_file"] == get_log_path()
    assert info["log_exists"] is True
