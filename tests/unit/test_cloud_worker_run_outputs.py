"""Cloud worker: task_vars reach runSkill runs, and $RUN_OUTPUT_DIR binds to
the per-run output folder that is uploaded to S3 afterwards (2026-10-09)."""
from pathlib import Path

from agent.cloud_worker.worker_main import _bind_run_output_dir, _task_vars_from_run_message


def test_task_vars_from_top_level_or_meta_data():
    assert _task_vars_from_run_message({"task_vars": {"a": "1"}}) == {"a": "1"}
    assert _task_vars_from_run_message({"meta_data": {"task_vars": {"b": "2"}}}) == {"b": "2"}
    assert _task_vars_from_run_message({"meta_data": '{"task_vars": {"c": "3"}}'}) == {"c": "3"}
    assert _task_vars_from_run_message({"skill": {}}) is None


def test_run_output_dir_placeholder_is_bound():
    out = Path("/tmp/run_out")
    tv = _bind_run_output_dir({"docs_root": "$RUN_OUTPUT_DIR", "n": 3, "x": "keep"}, out)
    assert tv == {"docs_root": out.as_posix(), "n": 3, "x": "keep"}
    assert _bind_run_output_dir(None, out) is None
