"""Path 1.5 — the worker wired to the server-side turn queue.

The queue shipped on the server with no worker calling it. This is the other
half: claim a turn, heartbeat it while it runs, report what it cost. Four
properties are worth protecting, and each has tests below:

  * **The turn id belongs to the server.** The client never mints one, never
    regenerates one on retry, and reports against the id it was handed —
    otherwise at-least-once delivery answers a customer twice.
  * **A turn that cannot be mapped to work is a permanent failure.** Reporting
    it as retryable burns every attempt on the same impossibility and reads as
    a flaky worker instead of a missing contract field.
  * **Cost is reported per turn.** TokenTracker computes it and then drops it
    when there is no DB service — which is exactly a pod's situation.
  * **Nothing in this path may kill the pod.** Claim errors back off, report
    errors log; only the work item itself fails.
"""

import asyncio
import json

import pytest

from agent.cloud_worker import cn_serve, fleet_client
from agent.ec_skills import usage_window


def _run(coro):
    return asyncio.run(coro)


# ===========================================================================
# Client configuration
# ===========================================================================

def test_account_manager_url_sits_beside_the_graphql_endpoint():
    url = fleet_client.account_manager_url(
        "https://sccb0-x.service.tcloudbase.com/api/graphql")
    assert url == "https://sccb0-x.service.tcloudbase.com/ecbAccountManager"


def test_account_manager_url_is_empty_when_unconfigured():
    assert fleet_client.account_manager_url("") == ""
    assert fleet_client.account_manager_url("not-a-url") == ""


def test_client_refuses_to_build_without_a_credential():
    with pytest.raises(fleet_client.FleetNotConfigured):
        fleet_client.FleetClient(
            endpoint="https://x/ecbAccountManager", token="", owner="o", vehicle_id="v")


def test_client_refuses_to_build_without_a_vehicle_id():
    """A pod with no id cannot be addressed by the scheduler or heartbeat."""
    with pytest.raises(fleet_client.FleetNotConfigured):
        fleet_client.FleetClient(
            endpoint="https://x/ecbAccountManager", token="t", owner="o", vehicle_id="")


def test_capabilities_parse_from_the_env_list(monkeypatch):
    monkeypatch.setenv(fleet_client.ENV_ENDPOINT, "https://x/ecbAccountManager")
    monkeypatch.setenv(fleet_client.ENV_TOKEN, "internal-token")
    monkeypatch.setenv(fleet_client.ENV_CAPABILITIES, "browser_local, cn_llm ;gpu")
    monkeypatch.setenv(fleet_client.ENV_CAPACITY, "8")
    client = fleet_client.FleetClient.from_env(vehicle_id="pod-1", owner="o@example.com")
    assert client.capabilities == ["browser_local", "cn_llm", "gpu"]
    assert client.capacity == 8


def test_fleet_client_or_none_is_quiet_when_not_configured(monkeypatch):
    """Fleet membership is optional — a stdin-fed pod is still a valid pod."""
    monkeypatch.delenv(fleet_client.ENV_ENDPOINT, raising=False)
    monkeypatch.delenv(fleet_client.ENV_TOKEN, raising=False)
    monkeypatch.setenv("ECAN_CN_GRAPHQL_ENDPOINT", "https://x/api/graphql")
    assert fleet_client.fleet_client_or_none(vehicle_id="pod-1") is None


# ===========================================================================
# Transport
# ===========================================================================

class _FakeResponse:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self.text = json.dumps(body) if not isinstance(body, str) else body


class _FakeAsyncClient:
    """Stands in for httpx.AsyncClient; records what was posted."""

    posted = []
    reply = _FakeResponse(200, {"success": True})

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, json=None, headers=None, timeout=None):
        type(self).posted.append({"url": url, "body": json, "headers": headers})
        return type(self).reply


@pytest.fixture
def fake_http(monkeypatch):
    import httpx

    _FakeAsyncClient.posted = []
    _FakeAsyncClient.reply = _FakeResponse(200, {"success": True})
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    return _FakeAsyncClient


def _client():
    return fleet_client.FleetClient(
        endpoint="https://x/ecbAccountManager", token="internal-token",
        owner="o@example.com", vehicle_id="pod-1", capabilities=["cn_llm"], capacity=4)


def test_post_carries_the_internal_credential_and_action_shape(fake_http):
    fake_http.reply = _FakeResponse(200, {"success": True, "turn": None})
    _run(_client().claim_turn())
    sent = fake_http.posted[-1]
    assert sent["headers"]["Authorization"] == "Bearer internal-token"
    assert sent["body"]["action"] == "turn_claim"
    assert sent["body"]["input"] == {"vehicle_id": "pod-1", "capabilities": ["cn_llm"]}


def test_empty_queue_is_not_an_error(fake_http):
    """Nothing to claim is the steady state, not a failure."""
    fake_http.reply = _FakeResponse(200, {"success": True, "turn": None})
    assert _run(_client().claim_turn()) is None


def test_claim_returns_the_turn(fake_http):
    fake_http.reply = _FakeResponse(200, {"success": True, "turn": {"id": "turn_1"}})
    assert _run(_client().claim_turn())["id"] == "turn_1"


def test_a_401_is_a_configuration_problem_not_a_retry(fake_http):
    """These actions use a fixed internal token; retrying cannot fix a wrong one."""
    fake_http.reply = _FakeResponse(401, {"success": False, "error": "unauthorized_internal"})
    with pytest.raises(fleet_client.FleetNotConfigured):
        _run(_client().claim_turn())


def test_server_error_surfaces_the_server_message(fake_http):
    fake_http.reply = _FakeResponse(400, {"success": False, "error": "turn not found"})
    with pytest.raises(fleet_client.FleetError) as exc:
        _run(_client().finish_turn("turn_1"))
    assert "turn not found" in str(exc.value)


def test_non_json_reply_is_reported_as_such(fake_http):
    fake_http.reply = _FakeResponse(502, "<html>gateway</html>")
    with pytest.raises(fleet_client.FleetError) as exc:
        _run(_client().claim_turn())
    assert "non-JSON" in str(exc.value)


def test_vehicle_heartbeat_is_a_re_registration(fake_http):
    """The server refreshes last_heartbeat on vehicle_register and nowhere else."""
    fake_http.reply = _FakeResponse(200, {"success": True, "vehicle": {"id": "pod-1"}})
    _run(_client().heartbeat_vehicle())
    sent = fake_http.posted[-1]
    assert sent["body"]["action"] == "vehicle_register"
    assert sent["body"]["input"]["max_concurrent_tasks"] == 4
    assert sent["body"]["input"]["capabilities"] == ["cn_llm"]


def test_finish_turn_carries_cost_and_tokens(fake_http):
    fake_http.reply = _FakeResponse(200, {"success": True, "turn": {"id": "turn_1"}})
    _run(_client().finish_turn(
        "turn_1", status="done", result={"ok": True},
        cost_usd=0.0123, input_tokens=1200, output_tokens=340))
    body = fake_http.posted[-1]["body"]["input"]
    assert body["turn_id"] == "turn_1"
    assert body["status"] == "done"
    assert body["cost_usd"] == 0.0123
    assert body["input_tokens"] == 1200 and body["output_tokens"] == 340
    assert body["result"] == {"ok": True}


def test_heartbeat_with_no_ids_does_not_call_the_server(fake_http):
    assert _run(_client().heartbeat_turns([])) == []
    assert fake_http.posted == []


# ===========================================================================
# turn -> work item
# ===========================================================================

def test_task_id_comes_from_the_turn_input_json(monkeypatch):
    monkeypatch.delenv("ECAN_TASK_ID", raising=False)
    msg = json.loads(cn_serve.turn_to_worker_message({
        "id": "turn_1", "owner": "o@example.com", "conversationId": "conv_9",
        "agentId": "agent_3",
        "input": json.dumps({"task_id": "task_7", "text": "在吗"}),
    }))
    assert msg["owner_id"] == "o@example.com"
    assert msg["task_id"] == "task_7"
    assert msg["options"]["testInputs"]["text"] == "在吗"


def test_task_id_falls_back_to_a_pinned_pod(monkeypatch):
    """Single-tenant serving: the pod is pinned to one task."""
    monkeypatch.setenv("ECAN_TASK_ID", "task_pinned")
    msg = json.loads(cn_serve.turn_to_worker_message({
        "id": "turn_1", "owner": "o@example.com", "input": "plain question",
    }))
    assert msg["task_id"] == "task_pinned"
    assert msg["options"]["testInputs"]["text"] == "plain question"


def test_a_turn_naming_no_task_is_a_mapping_error(monkeypatch):
    monkeypatch.delenv("ECAN_TASK_ID", raising=False)
    with pytest.raises(cn_serve.TurnMappingError) as exc:
        cn_serve.turn_to_worker_message({"id": "turn_1", "owner": "o", "input": "hi"})
    assert "ECAN_TASK_ID" in str(exc.value)


def test_a_turn_with_no_owner_is_a_mapping_error(monkeypatch):
    monkeypatch.delenv("ECAN_TASK_OWNER", raising=False)
    monkeypatch.setenv("ECAN_TASK_ID", "task_pinned")
    with pytest.raises(cn_serve.TurnMappingError):
        cn_serve.turn_to_worker_message({"id": "turn_1", "input": "hi"})


def test_run_id_is_the_turn_id(monkeypatch):
    """A redelivered turn overwrites its own run state instead of opening a second."""
    monkeypatch.setenv("ECAN_TASK_ID", "task_pinned")
    msg = json.loads(cn_serve.turn_to_worker_message({
        "id": "turn_abc", "owner": "o", "input": "hi"}))
    assert msg["options"]["run_id"] == "turn_abc"
    assert msg["options"]["turn_id"] == "turn_abc"


def test_conversation_thread_only_when_the_flag_is_on(monkeypatch):
    """Phase 2.2 stays opt-in; off, a turn is its own thread exactly as before."""
    monkeypatch.setenv("ECAN_TASK_ID", "task_pinned")
    turn = {"id": "turn_1", "owner": "o", "conversationId": "conv_9",
            "agentId": "agent_3", "input": "hi"}

    monkeypatch.delenv("ECAN_CONVERSATION_THREADS", raising=False)
    assert "thread_id" not in json.loads(cn_serve.turn_to_worker_message(turn))["options"]

    monkeypatch.setenv("ECAN_CONVERSATION_THREADS", "1")
    options = json.loads(cn_serve.turn_to_worker_message(turn))["options"]

    from agent.conversation_threads import thread_id_for
    assert options["thread_id"] == thread_id_for("agent_3", "conv_9")


def test_conversation_thread_is_namespaced_by_agent(monkeypatch):
    """Two agents serving one customer must not share a thread."""
    monkeypatch.setenv("ECAN_TASK_ID", "task_pinned")
    monkeypatch.setenv("ECAN_CONVERSATION_THREADS", "1")

    def thread_of(agent_id):
        return json.loads(cn_serve.turn_to_worker_message({
            "id": "t", "owner": "o", "conversationId": "conv_9",
            "agentId": agent_id, "input": "hi"}))["options"]["thread_id"]

    assert thread_of("agent_a") != thread_of("agent_b")


# ===========================================================================
# usage accounting
# ===========================================================================

def test_usage_delta_measures_one_window():
    usage_window.reset()
    before = usage_window.snapshot()
    usage_window.record_usage_sample(100, 20, 0.001)
    usage_window.record_usage_sample(50, 10, 0.0005)
    delta = usage_window.snapshot() - before
    assert delta.input_tokens == 150
    assert delta.output_tokens == 30
    assert round(delta.cost_usd, 6) == 0.0015
    assert delta.calls == 2


def test_usage_sampling_never_raises():
    """Accounting must not be able to break a run."""
    usage_window.reset()
    usage_window.record_usage_sample("not-a-number", None, "nope")  # no raise
    assert usage_window.snapshot().input_tokens == 0


# ===========================================================================
# the turn handler
# ===========================================================================

class _FakeFleet:
    def __init__(self, turns=None):
        self.turns = list(turns or [])
        self.reports = []
        self.turn_beats = []
        self.vehicle_beats = 0
        self.claim_error = None

    async def claim_turn(self):
        if self.claim_error:
            err, self.claim_error = self.claim_error, None
            raise err
        return self.turns.pop(0) if self.turns else None

    async def heartbeat_vehicle(self):
        self.vehicle_beats += 1
        return {}

    async def heartbeat_turns(self, ids):
        self.turn_beats.append(list(ids))
        return list(ids)

    async def finish_turn(self, turn_id, **kw):
        self.reports.append({"turn_id": turn_id, **kw})
        return {}


def test_completed_turn_is_reported_with_its_usage(monkeypatch):
    monkeypatch.setenv("ECAN_TASK_ID", "task_pinned")
    usage_window.reset()
    fleet = _FakeFleet()

    async def core(message):
        usage_window.record_usage_sample(1000, 200, 0.02)
        return {"reply": "好的"}

    handler = cn_serve.make_turn_handler(fleet, core=core)
    _run(handler(json.dumps({"id": "turn_1", "owner": "o", "input": "hi"})))

    report = fleet.reports[-1]
    assert report["turn_id"] == "turn_1"
    assert report["status"] == "done"
    assert report["result"] == {"reply": "好的"}
    assert report["input_tokens"] == 1000 and report["output_tokens"] == 200
    assert report["cost_usd"] == pytest.approx(0.02)


def test_usage_is_charged_to_the_turn_that_spent_it(monkeypatch):
    """The second turn must not inherit the first turn's tokens."""
    monkeypatch.setenv("ECAN_TASK_ID", "task_pinned")
    usage_window.reset()
    fleet = _FakeFleet()
    amounts = iter([(1000, 200, 0.02), (10, 2, 0.0002)])

    async def core(message):
        i, o, c = next(amounts)
        usage_window.record_usage_sample(i, o, c)
        return {}

    handler = cn_serve.make_turn_handler(fleet, core=core)
    for tid in ("turn_1", "turn_2"):
        _run(handler(json.dumps({"id": tid, "owner": "o", "input": "hi"})))

    assert fleet.reports[0]["input_tokens"] == 1000
    assert fleet.reports[1]["input_tokens"] == 10


def test_failed_turn_is_reported_and_still_raises(monkeypatch):
    """serve()'s per-item isolation counts the failure; the queue hears about it."""
    monkeypatch.setenv("ECAN_TASK_ID", "task_pinned")
    fleet = _FakeFleet()

    async def core(message):
        raise RuntimeError("skill blew up")

    handler = cn_serve.make_turn_handler(fleet, core=core)
    with pytest.raises(RuntimeError):
        _run(handler(json.dumps({"id": "turn_1", "owner": "o", "input": "hi"})))

    report = fleet.reports[-1]
    assert report["status"] == "failed"
    assert "skill blew up" in report["error"]
    assert report.get("retry") is None       # retryable by default


def test_unmappable_turn_is_reported_as_permanent(monkeypatch):
    """Retrying a turn that names no task maps to the same nothing three times."""
    monkeypatch.delenv("ECAN_TASK_ID", raising=False)
    fleet = _FakeFleet()

    async def core(message):                 # pragma: no cover - must not run
        raise AssertionError("core must not run for an unmappable turn")

    handler = cn_serve.make_turn_handler(fleet, core=core)
    with pytest.raises(cn_serve.TurnMappingError):
        _run(handler(json.dumps({"id": "turn_1", "owner": "o", "input": "hi"})))

    assert fleet.reports[-1]["status"] == "failed"
    assert fleet.reports[-1]["retry"] is False


def test_a_failed_report_does_not_kill_the_pod(monkeypatch):
    """The run already happened; raising here would trade one loss for a dead pod."""
    monkeypatch.setenv("ECAN_TASK_ID", "task_pinned")
    fleet = _FakeFleet()

    async def boom(turn_id, **kw):
        raise fleet_client.FleetError("control plane down")

    fleet.finish_turn = boom

    async def core(message):
        return {"ok": True}

    handler = cn_serve.make_turn_handler(fleet, core=core)
    _run(handler(json.dumps({"id": "turn_1", "owner": "o", "input": "hi"})))  # no raise


def test_turn_is_heartbeated_while_it_runs(monkeypatch):
    """A turn slower than the stale window must beat during the run, not after."""
    monkeypatch.setenv("ECAN_TASK_ID", "task_pinned")
    fleet = _FakeFleet()

    async def slow_core(message):
        await asyncio.sleep(0.12)
        return {}

    handler = cn_serve.make_turn_handler(fleet, core=slow_core, heartbeat_interval=0.02)
    _run(handler(json.dumps({"id": "turn_1", "owner": "o", "input": "hi"})))

    assert fleet.turn_beats and fleet.turn_beats[0] == ["turn_1"]


def test_unserialisable_result_is_reported_as_text(monkeypatch):
    monkeypatch.setenv("ECAN_TASK_ID", "task_pinned")
    fleet = _FakeFleet()

    class _Opaque:
        def __repr__(self):
            return "opaque-result"

    async def core(message):
        return {"obj": _Opaque()}

    handler = cn_serve.make_turn_handler(fleet, core=core)
    _run(handler(json.dumps({"id": "turn_1", "owner": "o", "input": "hi"})))
    assert "opaque-result" in json.dumps(fleet.reports[-1]["result"], ensure_ascii=False)


# ===========================================================================
# the fleet intake
# ===========================================================================

async def _drain(agen, limit):
    out = []
    async for item in agen:
        out.append(json.loads(item))
        if len(out) >= limit:
            break
    return out


def test_intake_yields_claimed_turns():
    fleet = _FakeFleet(turns=[{"id": "turn_1"}, {"id": "turn_2"}])
    got = _run(_drain(cn_serve.fleet_intake(fleet, poll_interval=0.01), 2))
    assert [t["id"] for t in got] == ["turn_1", "turn_2"]


def test_intake_backs_off_on_an_empty_queue_and_recovers():
    fleet = _FakeFleet(turns=[])

    async def go():
        agen = cn_serve.fleet_intake(fleet, poll_interval=0.01, idle_backoff_max=0.02)
        task = asyncio.create_task(_drain(agen, 1))
        await asyncio.sleep(0.08)
        fleet.turns.append({"id": "turn_late"})
        return await asyncio.wait_for(task, timeout=2)

    assert _run(go())[0]["id"] == "turn_late"


def test_a_claim_error_backs_off_instead_of_killing_the_pod():
    """A control-plane blip must not take this pod out of the fleet."""
    fleet = _FakeFleet(turns=[{"id": "turn_1"}])
    fleet.claim_error = RuntimeError("502 bad gateway")
    got = _run(_drain(cn_serve.fleet_intake(fleet, poll_interval=0.01), 1))
    assert got[0]["id"] == "turn_1"


def test_intake_heartbeats_the_vehicle():
    fleet = _FakeFleet(turns=[{"id": "turn_1"}])
    _run(_drain(cn_serve.fleet_intake(fleet, poll_interval=0.01), 1))
    assert fleet.vehicle_beats >= 1


def test_intake_stops_at_max_turns():
    fleet = _FakeFleet(turns=[{"id": "turn_1"}, {"id": "turn_2"}])

    async def go():
        out = []
        async for item in cn_serve.fleet_intake(fleet, poll_interval=0.01, max_turns=1):
            out.append(item)
        return out

    assert len(_run(go())) == 1


# ===========================================================================
# the loop, unchanged
# ===========================================================================

def test_serve_runs_the_turn_handler_over_the_fleet_intake(monkeypatch):
    """The whole point of the Phase 5 seam: a new transport, no loop changes."""
    monkeypatch.setenv("ECAN_SERVE_ALLOW_EPHEMERAL", "1")
    monkeypatch.setenv("ECAN_TASK_ID", "task_pinned")
    fleet = _FakeFleet(turns=[
        {"id": "turn_1", "owner": "o", "input": "hi"},
        {"id": "turn_2", "owner": "o", "input": "hi again"},
    ])
    ran = []

    async def core(message):
        ran.append(json.loads(message)["options"]["turn_id"])
        return {}

    stats = _run(cn_serve.serve(
        cn_serve.fleet_intake(fleet, poll_interval=0.01, max_turns=2),
        handler=cn_serve.make_turn_handler(fleet, core=core),
        install_context=False,
    ))
    assert ran == ["turn_1", "turn_2"]
    assert stats.completed == 2 and stats.failed == 0
    assert [r["status"] for r in fleet.reports] == ["done", "done"]


def test_one_bad_turn_does_not_stop_the_pod(monkeypatch):
    monkeypatch.setenv("ECAN_SERVE_ALLOW_EPHEMERAL", "1")
    monkeypatch.setenv("ECAN_TASK_ID", "task_pinned")
    fleet = _FakeFleet(turns=[
        {"id": "turn_bad", "owner": "o", "input": "hi"},
        {"id": "turn_ok", "owner": "o", "input": "hi"},
    ])

    async def core(message):
        if json.loads(message)["options"]["turn_id"] == "turn_bad":
            raise RuntimeError("nope")
        return {}

    stats = _run(cn_serve.serve(
        cn_serve.fleet_intake(fleet, poll_interval=0.01, max_turns=2),
        handler=cn_serve.make_turn_handler(fleet, core=core),
        install_context=False,
    ))
    assert stats.failed == 1 and stats.completed == 1
    assert [r["status"] for r in fleet.reports] == ["failed", "done"]


# ===========================================================================
# Phase 2.2 on the serving path — the thread id reaches the run
# ===========================================================================

class _FakeCNClient:
    endpoint = "https://x/api/graphql"
    access_token = "t"

    async def get_task(self, task_id):
        return {"id": task_id, "name": "t", "metadata": {}}

    async def get_task_skills(self, task_id):
        return [{"id": "skill_1", "name": "qa",
                 "diagram": {"nodes": [{"id": "n1"}]}}]

    async def upload_json(self, *a, **kw):
        return None


@pytest.fixture
def captured_worker_message(monkeypatch):
    """Run run_single_cn against fakes and capture the WorkerMessage it builds."""
    from agent.cloud_worker import cn_worker_main, worker_main

    monkeypatch.setattr(cn_worker_main.CNBackendClient, "from_env",
                        classmethod(lambda cls: _FakeCNClient()))
    monkeypatch.setattr(cn_worker_main, "configure_cloud_logger", lambda **kw: None)
    monkeypatch.setattr(cn_worker_main, "stop_cloud_logger", lambda: None)

    async def _noop(*a, **kw):
        return None

    monkeypatch.setattr(cn_worker_main, "_publish_event", _noop)
    monkeypatch.setattr(cn_worker_main, "_save_run_state", _noop)

    captured = {}

    def _fake_run(*, msg, skill_root):
        captured["msg"] = msg
        return {"reply": "ok"}

    monkeypatch.setattr(worker_main, "_run_skill_once", _fake_run)
    return captured


def test_conversation_thread_reaches_the_run(monkeypatch, captured_worker_message):
    """Turn -> options.thread_id -> WorkerMessage.thread_id, end to end."""
    monkeypatch.setenv("ECAN_TASK_ID", "task_pinned")
    monkeypatch.setenv("ECAN_CONVERSATION_THREADS", "1")
    from agent.cloud_worker.cn_worker_main import run_single_cn
    from agent.conversation_threads import thread_id_for

    message = cn_serve.turn_to_worker_message({
        "id": "turn_1", "owner": "o@example.com", "conversationId": "conv_9",
        "agentId": "agent_3", "input": "在吗",
    })
    result = _run(run_single_cn(message))

    assert captured_worker_message["msg"].thread_id == thread_id_for("agent_3", "conv_9")
    # And the result comes back, which is what turn_done reports to the customer.
    assert result == {"reply": "ok"}


def test_without_the_flag_each_run_keeps_its_own_thread(monkeypatch, captured_worker_message):
    monkeypatch.setenv("ECAN_TASK_ID", "task_pinned")
    monkeypatch.delenv("ECAN_CONVERSATION_THREADS", raising=False)
    from agent.cloud_worker.cn_worker_main import run_single_cn

    message = cn_serve.turn_to_worker_message({
        "id": "turn_1", "owner": "o@example.com", "conversationId": "conv_9",
        "agentId": "agent_3", "input": "在吗",
    })
    _run(run_single_cn(message))
    assert captured_worker_message["msg"].thread_id is None


# ===========================================================================
# Concurrency correctness (after Capacity landed — tests/test_serve_concurrency.py)
#
# Two things that were silently wrong the moment a pod could hold more than one
# turn at a time, both reproduced before being fixed.
# ===========================================================================

def test_each_turn_is_charged_only_its_own_usage(monkeypatch):
    """Overlapping turns must not bill each other.

    With a shared counter read before/after, turns spending 1000 and 10 tokens
    in the same window were each reported as 1010 — every conversation charged
    for its neighbours.
    """
    monkeypatch.setenv("ECAN_TASK_ID", "task_pinned")
    usage_window.reset()
    fleet = _FakeFleet()

    async def core(message):
        turn_id = json.loads(message)["options"]["turn_id"]
        await asyncio.sleep(0.02)                      # ensure the turns overlap
        usage_window.record_usage_sample(1000 if turn_id == "turn_a" else 10, 0, 0.0)
        await asyncio.sleep(0.02)
        return {}

    handler = cn_serve.make_turn_handler(fleet, core=core)

    async def go():
        await asyncio.gather(*[
            handler(json.dumps({"id": t, "owner": "o", "input": "x"}))
            for t in ("turn_a", "turn_b")
        ])

    _run(go())
    charged = {r["turn_id"]: r["input_tokens"] for r in fleet.reports}
    assert charged == {"turn_a": 1000, "turn_b": 10}


def test_usage_outside_a_turn_still_counts_process_wide():
    """A sample with no window open is not lost, just unattributed."""
    usage_window.reset()
    usage_window.record_usage_sample(5, 1, 0.001)
    assert usage_window.snapshot().input_tokens == 5


def test_execution_core_runs_off_the_event_loop(monkeypatch, captured_worker_message):
    """The core is synchronous and builds its own loop; it must not run on ours.

    Called inline it raised "Cannot run the event loop while another loop is
    running", silently fell back to sync execution, and blocked the serve loop
    for the whole turn — so heartbeats could not fire (a turn past
    TURN_STALE_SECONDS is reaped and answered twice) and turns serialised no
    matter what capacity the pod advertised.
    """
    import threading
    import time

    from agent.cloud_worker import cn_worker_main, worker_main

    monkeypatch.setenv("ECAN_TASK_ID", "task_pinned")
    seen = {}

    def blocking_run(*, msg, skill_root):
        seen["thread"] = threading.current_thread().name
        time.sleep(0.15)                               # a real turn blocks like this
        return {"ok": True}

    monkeypatch.setattr(worker_main, "_run_skill_once", blocking_run)

    async def go():
        ticks = 0

        async def ticker():
            nonlocal ticks
            while True:
                await asyncio.sleep(0.01)
                ticks += 1

        beat = asyncio.create_task(ticker())
        try:
            await cn_worker_main.run_single_cn(cn_serve.turn_to_worker_message(
                {"id": "turn_1", "owner": "o@example.com", "input": "hi"}))
        finally:
            beat.cancel()
        return ticks

    ticks = _run(go())
    assert seen["thread"] != threading.main_thread().name
    # The loop kept running while the turn did: this is what lets a long turn
    # keep heartbeating.
    assert ticks >= 5, f"event loop was blocked during the turn (ticks={ticks})"
