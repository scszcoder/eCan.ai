"""run_async_in_worker_thread must hand back the result even when a task the
coroutine left behind never finishes its cancellation. browser-use did this
after stopping on consecutive failures, and the node thread froze in join()."""
import asyncio
import time

from agent.ec_skills.llm_utils import llm_utils
from agent.ec_skills.llm_utils.llm_utils import run_async_in_worker_thread


def _stubborn_leftover():
    async def _ignore_cancel():
        while True:
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                continue
    asyncio.get_running_loop().create_task(_ignore_cancel())


def test_result_returns_despite_stuck_cleanup(monkeypatch):
    monkeypatch.setattr(llm_utils, "_WORKER_CLEANUP_GRACE_S", 0.5)

    async def run():
        _stubborn_leftover()
        await asyncio.sleep(0)
        return {"final": "ok"}

    t0 = time.monotonic()
    assert run_async_in_worker_thread(run) == {"final": "ok"}
    assert time.monotonic() - t0 < 5


def test_error_still_raises_despite_stuck_cleanup(monkeypatch):
    monkeypatch.setattr(llm_utils, "_WORKER_CLEANUP_GRACE_S", 0.5)

    async def run():
        _stubborn_leftover()
        await asyncio.sleep(0)
        raise ValueError("boom")

    try:
        run_async_in_worker_thread(run)
    except ValueError as e:
        assert str(e) == "boom"
    else:
        raise AssertionError("expected ValueError")


def test_plain_run_returns_result():
    async def run():
        return 42

    assert run_async_in_worker_thread(run) == 42
