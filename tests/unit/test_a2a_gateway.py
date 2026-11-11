"""The desktop A2A gateway: cloud requests get an ack, a result and exactly one response;
the allowlist holds; duplicates, deadlines, cancels, catch-up and a missing server contract."""
import asyncio
import json
import types

import pytest

from agent.a2a import gateway as G


class FakeServer:
    """Records every GraphQL call; sendA2AMessage returns a stored id."""

    def __init__(self, stored=None, fail=None):
        self.calls, self.stored, self.fail, self.n = [], stored or [], fail, 0

    async def post(self, query, variables):
        if self.fail:
            raise RuntimeError(self.fail)
        self.calls.append((query.split("(")[0].split()[-1], variables))
        if "GetA2AMessages" in query:
            return {"data": {"getA2AMessages": self.stored}}
        if "SendA2AMessage" in query:
            self.n += 1
            return {"data": {"sendA2AMessage": {"id": f"out{self.n}"}}}
        return {"data": {}}

    def sent(self):
        return [json.loads(v["input"]["payload"]) | {"_to": v["input"]["toAgentId"]}
                for q, v in self.calls if q == "SendA2AMessage"]

    def acks(self):
        return [v["status"] for q, v in self.calls if q == "AckA2AMessage"]


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("ECAN_ECOM_HOME", str(tmp_path / "ecom"))
    return tmp_path


def gw(server, tmp_path, tools=None, bridge=None):
    return G.Gateway(mainwin=object(), machine_id="m1", org="org1", post=server.post, bridge=bridge,
                     tools=tools if tools is not None else {}, state_dir=tmp_path)


def stored(env, mid="in1", to="machine_m1", created="2026-11-10T10:00:00+00:00"):
    return {"id": mid, "toAgentId": to, "toMachineId": "machine_m1", "fromAgentId": "mgr_org1",
            "payload": json.dumps(env), "createdAt": created}


def run(coro):
    return asyncio.run(coro)


def test_a_tool_call_is_acked_run_and_answered_once(tmp_path):
    seen = {}

    async def ec_table_query(mainwin, args):
        seen["args"] = args
        return [types.SimpleNamespace(text="3 rows", meta={"task_result": {"rows": [[1], [2], [3]]}})]
    s = FakeServer()
    g = gw(s, tmp_path, tools={"ec_table_query": ec_table_query})
    req = G.new_request("tool_call", {"tool": "ec_table_query", "input": {"sql": "select 1"}}, reply_to="mgr_org1",
                        thread_id="t1")
    assert run(g.handle(stored(req))) == "done"
    assert seen["args"] == {"sql": "select 1"} and s.acks() == ["accepted"]
    kinds = [(m["kind"], m.get("status")) for m in s.sent()]
    assert kinds == [("ack", "accepted"), ("response", "done")]
    resp = s.sent()[-1]
    assert resp["correlation_id"] == req["correlation_id"] and resp["thread_id"] == "t1" and resp["_to"] == "mgr_org1"
    assert resp["result"]["text"] == "3 rows" and resp["result"]["data"] == {"rows": [[1], [2], [3]]}


def test_the_same_message_delivered_twice_runs_once(tmp_path):
    calls = []

    async def ec_kb(mainwin, args):
        calls.append(1)
        return [types.SimpleNamespace(text="ok", meta={})]
    g = gw(FakeServer(), tmp_path, tools={"ec_kb": ec_kb})
    m = stored(G.new_request("tool_call", {"tool": "ec_kb", "input": {}}, reply_to="mgr_org1"))
    assert run(g.handle(m)) == "done" and run(g.handle(m)) == "duplicate" and calls == [1]


def test_tools_and_skills_off_the_allowlist_are_rejected(tmp_path):
    s = FakeServer()
    g = gw(s, tmp_path, tools={"run_code": lambda *a: 1})
    assert run(g.handle(stored(G.new_request("tool_call", {"tool": "run_code", "input": {}}, reply_to="mgr_org1")))) == "rejected"
    run_other = G.new_request("tool_call", {"tool": "run_skill_for_store", "input": {"input": {"skill_name": "some_writer",
                                                                                            "store_id": "s"}}}, reply_to="mgr_org1")
    assert run(g.handle(stored(run_other, mid="in2"))) == "rejected"
    assert run(g.handle(stored(G.new_request("run_skill", {"skill": "some_writer"}, reply_to="mgr_org1"), mid="in3"))) == "rejected"
    assert s.acks() == ["rejected"] * 3
    assert all(m["kind"] == "ack" and m["error"]["code"] == "NOT_ALLOWED" for m in s.sent())


def test_a_skill_run_is_answered_when_the_run_finishes(tmp_path):
    async def run_skill_for_store(mainwin, args):
        assert args == {"input": {"skill_name": "google_ads_review", "store_id": "s1"}}
        return [types.SimpleNamespace(text="queued on Ops", meta={"task_result": {"success": True, "task_id": "T9",
                                                                                   "task_name": "review·s1"}})]
    s = FakeServer()

    async def go():
        g = gw(s, tmp_path, tools={"run_skill_for_store": run_skill_for_store})
        g._loop = asyncio.get_running_loop()
        req = G.new_request("run_skill", {"skill": "google_ads_review", "store_id": "s1"}, reply_to="mgr_org1")
        assert await g.handle(stored(req)) == "running"
        g.task_finished("other", True, {})                       # not ours: nothing sent
        g.task_finished("T9", True, {"result": {"llm_result": {"message": "Spent $37 on 63 clicks."}}})
        await asyncio.sleep(0.05)
        g.task_finished("T9", True, {})                          # answered once only
        await asyncio.sleep(0.05)
    run(go())
    kinds = [(m["kind"], m.get("status")) for m in s.sent()]
    assert kinds == [("ack", "accepted"), ("progress", "running"), ("response", "done")]
    assert s.sent()[-1]["result"]["message"] == "Spent $37 on 63 clicks."


def test_a_run_that_never_finishes_is_reported_failed_at_its_deadline(tmp_path):
    s = FakeServer()
    g = gw(s, tmp_path)
    g._running["c1"] = {"reply_to": "mgr_org1", "thread_id": None, "task_id": "T1", "started": 0, "last_progress": 0,
                        "deadline": 1, "what": "review"}
    run(g.progress_tick())
    assert s.sent()[-1]["kind"] == "response" and s.sent()[-1]["error"]["code"] == "TIMEOUT" and not g._running


def test_a_request_past_its_deadline_is_not_started(tmp_path):
    s = FakeServer()
    g = gw(s, tmp_path, tools={"ec_kb": lambda *a: pytest.fail("must not run")})
    req = G.new_request("tool_call", {"tool": "ec_kb", "input": {}}, reply_to="mgr_org1", deadline="2020-01-01T00:00:00+00:00")
    assert run(g.handle(stored(req))) == "expired" and s.sent()[-1]["status"] == "expired"


def test_plain_a2a_and_replies_go_to_the_named_local_agent(tmp_path):
    got = []

    async def bridge(agent_id, payload):
        got.append((agent_id, payload))
    g = gw(FakeServer(), tmp_path, bridge=bridge)
    assert run(g.handle(stored({"jsonrpc": "2.0", "method": "message/send"}, to="agent_local"))) == "forwarded"
    reply = G.make("response", correlation_id="c", reply_to="mgr_org1", status="done")
    assert run(g.handle(stored(reply, mid="in2", to="agent_local"))) == "forwarded"
    assert [a for a, _ in got] == ["agent_local", "agent_local"] and got[0][1]["_a2a_via"] == "a2a_gateway"


def test_catch_up_runs_stored_messages_oldest_first_and_remembers_where_it_stopped(tmp_path):
    order = []

    async def ec_kb(mainwin, args):
        order.append(args["n"])
        return [types.SimpleNamespace(text="ok", meta={})]
    msgs = [stored(G.new_request("tool_call", {"tool": "ec_kb", "input": {"n": n}}, reply_to="mgr_org1"), mid=f"m{n}",
                   created=f"2026-11-10T10:0{n}:00+00:00") for n in (2, 1)]
    s = FakeServer(stored=msgs)
    g = gw(s, tmp_path, tools={"ec_kb": ec_kb})
    assert run(g.catch_up()) == 2 and order == [1, 2]
    assert g._load_state()["since"] == "2026-11-10T10:02:00+00:00"
    assert [v for q, v in s.calls if q == "GetA2AMessages"][0]["toMachineId"] == "machine_m1"


def test_without_the_server_contract_nothing_breaks(tmp_path):
    g = gw(FakeServer(fail="Validation error: Cannot query field 'getA2AMessages'"), tmp_path)
    assert run(g.catch_up()) == 0
    run(g.heartbeat())
    assert g._schema_warned


def test_the_machine_announces_itself_with_what_it_can_run(tmp_path):
    s = FakeServer()
    run(gw(s, tmp_path).heartbeat())
    rec = [v for q, v in s.calls if q == "UpsertAgentEndpoint"][0]["input"]
    assert rec["id"] == "machine_m1" and rec["role"] == "machine" and "google_ads_review" in rec["skills"]


def test_a_cancel_stops_the_waiting_run_and_says_so(tmp_path, monkeypatch):
    from agent.ec_tasks import task_mcp_tools
    stopped = []
    monkeypatch.setattr(task_mcp_tools, "stop_agent_task", lambda mw, cfg: stopped.append(cfg) or {"success": True})
    s = FakeServer()
    g = gw(s, tmp_path)
    g._running["c1"] = {"reply_to": "mgr_org1", "thread_id": "t1", "task_id": "T1", "started": 0, "last_progress": 0,
                        "deadline": 9e12, "what": "review"}
    cancel = G.make("cancel", correlation_id="c1", reply_to="mgr_org1")
    assert run(g.handle(stored(cancel))) == "cancelled" and stopped == [{"task_id": "T1"}]
    assert s.sent()[-1]["error"]["code"] == "CANCELLED" and s.sent()[-1]["thread_id"] == "t1"
    assert run(g.handle(stored(cancel, mid="in2"))) == "nothing_to_cancel"


def test_the_old_wan_a2a_path_calls_subscribers_with_their_documented_arguments():
    from agent.chats.wan_a2a_chat import _call_callback
    got = []

    async def cb(message, sender_id, channel_id):
        got.append((message, sender_id, channel_id))
    run(_call_callback(cb, {"message": {"role": "user"}, "senderId": "a1", "channelId": "c1"}))
    assert got == [({"role": "user"}, "a1", "c1")]
