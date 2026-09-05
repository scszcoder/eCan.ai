"""Run-scope log tagging (utils/log_scope.py): suffix rendering, stamping in the
emitting thread, thread handoff, and the live logger_helper pipeline."""

import asyncio
import concurrent.futures
import logging
import os
import time

from utils import log_scope as ls


def test_suffix_and_scope_restore():
    assert ls.suffix() == ""
    with ls.scope(agent_name="前台小张", task_name="飞鸽客服前台001", skill_name="飞鸽客服前台", run_id=None):
        assert ls.suffix() == " [agent=前台小张 task=飞鸽客服前台001 skill=飞鸽客服前台]"
        ls.update_scope(run_id="r1")
        assert ls.suffix().endswith("run=r1]")
    assert ls.suffix() == ""  # restored


def test_filter_stamps_record_and_formatter_tolerates_missing():
    f = ls.ScopeFilter()
    rec = logging.LogRecord("x", logging.INFO, __file__, 1, "hello", None, None)
    with ls.scope(agent_name="A"):
        assert f.filter(rec) is True
    assert rec.ecan_scope == " [agent=A]"
    # an existing stamp is kept even if the filter runs again out of scope
    assert f.filter(rec) is True and rec.ecan_scope == " [agent=A]"
    fmt = ls.ScopedFormatter("%(message)s%(ecan_scope)s")
    bare = logging.LogRecord("x", logging.INFO, __file__, 1, "bare", None, None)
    assert fmt.format(bare) == "bare"
    assert fmt.format(rec) == "hello [agent=A]"


def test_context_flows_into_asyncio_but_needs_wrap_for_executor():
    async def inner():
        return ls.suffix()

    async def main():
        with ls.scope(agent_name="B"):
            t = asyncio.create_task(inner())
            return await t
    assert asyncio.run(main()) == " [agent=B]"

    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    with ls.scope(agent_name="C"):
        assert pool.submit(ls.suffix).result() == ""              # plain submit: lost
        assert pool.submit(ls.wrap_context(ls.suffix)).result() == " [agent=C]"
    assert pool.submit(ls.suffix).result() == ""                  # pooled thread not polluted
    pool.shutdown()


def test_live_logger_pipeline_writes_suffix_to_file():
    """End-to-end through logger_helper's QueueHandler -> listener -> file."""
    from utils.logger_helper import logger_helper, get_log_path
    marker = f"scope-e2e-{time.time_ns()}"
    with ls.scope(agent_name="前台小张", task_name="T1"):
        logger_helper.info(marker)
    path = get_log_path()
    line = ""
    for _ in range(50):  # async listener — poll briefly
        with open(path, encoding="utf-8", errors="replace") as fh:
            for l in fh:
                if marker in l:
                    line = l
        if line:
            break
        time.sleep(0.05)
    assert line, "marker never reached the log file"
    assert line.rstrip().endswith("[agent=前台小张 task=T1]")
