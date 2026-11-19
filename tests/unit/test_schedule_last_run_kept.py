"""A daily task that already ran this cycle does not run again when the app restarts:
its last scheduled run is kept on disk (in memory only, every start re-ran it)."""
import types
from datetime import datetime, timedelta

import pytest

from agent.ec_tasks import scheduler as S
from agent.ec_tasks.models import RepeatType, TaskSchedule


@pytest.fixture(autouse=True)
def last_runs_file(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "_last_runs_path", lambda: str(tmp_path / "schedule_last_runs.json"))


def _daily_task(task_id="task_1"):
    start = (datetime.now() - timedelta(days=3, hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    schedule = TaskSchedule(repeat_type=RepeatType.BY_DAYS, repeat_number=1, repeat_unit="day",
                            start_date_time=start, end_date_time="2099-12-31 00:00:00", time_out=60)
    # As loaded: no last run in memory.
    return types.SimpleNamespace(id=task_id, schedule=schedule, trigger=["schedule"],
                                 last_run_datetime=None, already_run_flag=False)


def test_a_task_run_this_cycle_is_not_run_again_after_a_restart():
    assert S.find_tasks_ready_to_run([_daily_task()]) is not None     # first start: due, runs
    assert S.find_tasks_ready_to_run([_daily_task()]) is None         # restart: already ran today


def test_a_task_whose_last_run_was_before_this_cycle_runs_once():
    S.save_last_run("task_1", datetime.now() - timedelta(days=2))
    task = _daily_task()
    assert S.find_tasks_ready_to_run([task]) is task
    assert S.find_tasks_ready_to_run([_daily_task()]) is None


def test_runs_are_kept_per_task():
    S.find_tasks_ready_to_run([_daily_task("task_a")])
    assert S.find_tasks_ready_to_run([_daily_task("task_b")]) is not None
    assert S.load_last_run("task_a") and S.load_last_run("missing") is None
