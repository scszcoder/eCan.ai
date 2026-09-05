"""Help > 查看日志 Agent dropdown helpers (pure functions in gui/log_viewer.py)."""
import pytest
pytest.importorskip("PySide6")
from gui.log_viewer import _scope_agents, _filter_lines

LOG = "\n".join([
    "2026-09-04 22:47:20,175 - eCan.cn - INFO - [BrowserManager] Connecting to existing chrome [agent=前台小张 task=飞鸽客服前台001]",
    "2026-09-04 22:47:21,400 - eCan.cn - WARNING - [EventMonitor][HB] status=page_mismatch [agent=前台小张 task=飞鸽客服前台001]",
    "2026-09-04 22:47:22,000 - eCan.cn - INFO - [RUN] something [agent=客服小王 task=飞鸽客服应答001]",
    "2026-09-04 22:47:23,000 - eCan.cn - INFO - unscoped line",
])

def test_scope_agents_extracted():
    assert sorted(set(_scope_agents(LOG))) == ["前台小张", "客服小王"]

def test_filter_by_agent_and_level():
    assert len(_filter_lines(LOG, "", "前台小张")) == 2
    assert len(_filter_lines(LOG, "WARNING", "前台小张")) == 1
    assert len(_filter_lines(LOG, "WARNING", "")) == 1
    assert len(_filter_lines(LOG, "", "")) == 4
    assert _filter_lines(LOG, "", "nobody") == []
