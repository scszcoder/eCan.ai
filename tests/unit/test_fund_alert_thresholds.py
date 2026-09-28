"""Balance-alarm levels: defaults come from the settings template (low ¥10,
critical ¥5) and every change the user makes on the Account page is logged."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from gui.config.general_settings import GeneralSettings


def test_template_defaults():
    t = json.loads(Path("resource/data/settings_template.json").read_text(encoding="utf-8"))
    assert t["low_fund_threshold"] == 10
    assert t["critical_fund_threshold"] == 5


def test_a_change_is_logged_and_kept():
    gs = GeneralSettings.__new__(GeneralSettings)       # no config manager / hardware scan
    gs._data = {"low_fund_threshold": 10, "critical_fund_threshold": 5}
    with mock.patch("gui.config.general_settings.logger") as log:
        gs.update_data({"username": "u", "low_fund_threshold": 20, "critical_fund_threshold": 5})
    assert gs._data["low_fund_threshold"] == 20 and "username" not in gs._data
    lines = [c.args[0] for c in log.info.call_args_list]
    assert any("low_fund_threshold: 10 -> 20" in s for s in lines)
    assert not any("critical_fund_threshold" in s for s in lines)   # unchanged: not logged
