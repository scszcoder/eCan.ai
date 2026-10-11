"""agent/ec_tasks/run_state.py: what the task list shows (multi-task Phase 4)."""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.ec_tasks import resource_gate as rg
from agent.ec_tasks.run_state import task_run_states
from agent.ec_tasks.task_deps import AfterTracker


def test_waiting_held_and_missed(monkeypatch):
    g = rg.ResourceGate(spawn=lambda fn: fn())
    monkeypatch.setattr(rg, "_gate", g)
    key = "agent:ag1/browser:store3"
    g.acquire_or_wait("A", (key,), rg.SCHEDULED, 0, on_grant=lambda: None)
    g.acquire_or_wait("B", (key, "user:printer"), rg.REACTIVE, 1, on_grant=lambda: None)

    a = SimpleNamespace(id="A", name="抓取", metadata={})
    b = SimpleNamespace(id="B", name="回复", metadata={"last_missed": {"at": "x", "due": "10:30", "why": "late"}})
    c = SimpleNamespace(id="C", name="日报", metadata={"after": {"tasks": ["A", "B"]}}, trigger=["schedule", "after"])
    tracker = AfterTracker()
    tracker.record("A", True)
    runner = SimpleNamespace(_after_held={"C": {}}, _after_tracker_obj=tracker)
    states = task_run_states([SimpleNamespace(tasks=[a, b, c], runner=runner)])

    assert states["B"]["waiting_resource"]["resources"] == ["browser:store3", "printer"]
    assert states["B"]["waiting_resource"]["behind"] == ["抓取"]
    assert states["B"]["last_missed"]["due"] == "10:30"
    assert states["C"]["waiting_after"] == ["回复"]
    assert "A" not in states
