"""publish_step_result must not block the event loop.

It used a sync httpx client (needed: an AsyncClient trips sniffio in
run_async_in_sync contexts) directly inside ``async def`` plus ``time.sleep``
retries, so one publish could freeze the loop for up to 30s per attempt. The
POST now runs in a worker thread and the backoff uses asyncio.sleep.
"""
import asyncio
import threading

import httpx

from agent.ec_skills.browser_use_extension import passive_utils as pu


class _Result:
    run_id = "run-1"
    step_id = "step-1"

    def model_dump(self):
        return {"run_id": self.run_id, "step_id": self.step_id, "browser": {}}


def _fake_client_factory(record, fail_first=True):
    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": {"ok": True}}

    class _FakeClient:
        def __init__(self, **kwargs):
            record["kwargs"] = kwargs

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def post(self, *a, **k):
            record.setdefault("threads", []).append(threading.get_ident())
            if fail_first and len(record["threads"]) == 1:
                raise httpx.ConnectError("transient")
            return _Resp()

    return _FakeClient


def test_post_runs_off_loop_and_retries_with_async_sleep(monkeypatch):
    record = {}
    monkeypatch.setattr(httpx, "Client", _fake_client_factory(record))
    slept = []

    async def _fast_sleep(d):
        slept.append(d)

    monkeypatch.setattr(asyncio, "sleep", _fast_sleep)

    loop_thread = {}

    async def _main():
        loop_thread["id"] = threading.get_ident()
        await pu.publish_step_result(_Result(), "https://example.invalid/graphql", "tok", "cid")

    asyncio.run(_main())

    assert len(record["threads"]) == 2                      # failed once, then succeeded
    assert loop_thread["id"] not in record["threads"]       # never on the loop thread
    assert slept == [1.0]                                   # backoff via asyncio.sleep
    assert "verify" in record["kwargs"]                     # shared TLS context passed
