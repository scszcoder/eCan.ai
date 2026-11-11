"""Agent status for the cloud Manager: providers, the get_agent_status / status_diagnose
gateway intents, the agent list in the heartbeat, anomaly events, and the product research
provider (docs/AGENT_STATUS_PROBING_DESIGN.md)."""
import asyncio
import json
import time
import types
from pathlib import Path

import pytest

from agent.a2a import gateway as G
from agent.status import diagnose as D
from agent.status import providers as P


class FakeServer:
    def __init__(self, reject_caps=False):
        self.calls, self.n, self.reject_caps = [], 0, reject_caps

    async def post(self, query, variables):
        if self.reject_caps and "capabilities" in variables.get("input", {}):
            raise RuntimeError("Validation error: field 'capabilities' is not defined for AgentEndpointInput")
        self.calls.append((query.split("(")[0].split()[-1], variables))
        if "SendA2AMessage" in query:
            self.n += 1
            return {"data": {"sendA2AMessage": {"id": f"out{self.n}"}}}
        return {"data": {}}

    def sent(self):
        return [json.loads(v["input"]["payload"]) | {"_to": v["input"]["toAgentId"]}
                for q, v in self.calls if q == "SendA2AMessage"]


def agent(aid, name, skills, running=True):
    return types.SimpleNamespace(card=types.SimpleNamespace(id=aid, name=name), _running=running, status="active",
                                 skills=[types.SimpleNamespace(name=s) for s in skills], tasks=[])


@pytest.fixture
def team(monkeypatch):
    """A 'crawl' team provider for skills crawl_*, with a switchable answer."""
    state = {"anomalies": [], "sleep": 0}

    def crawl_status(ctx):
        time.sleep(state["sleep"])
        return {"health": "ok", "headline": f"{len(ctx.members)} members", "anomalies": list(state["anomalies"]),
                "progress": {"unit": "items", "done": 3, "total": 10, "percent": 30.0}}
    monkeypatch.setattr(P, "_providers", {})
    monkeypatch.setattr(P, "_loaded", True)
    P.register("crawl", crawl_status, skills=("crawl_worker", "crawl_boss"), team="crawl", team_name="The crawl",
               roots=lambda inputs: [Path(inputs.get("root", "."))])
    return state


def mainwin():
    return types.SimpleNamespace(agents=[agent("a1", "Boss", ["crawl_boss_00"]), agent("a2", "Worker1", ["crawl_worker_00"]),
                                         agent("a3", "Helper", ["chat"], running=False)])


def gw(server, tmp_path, mw=None):
    return G.Gateway(mainwin=mw or mainwin(), machine_id="m1", org="org1", post=server.post, tools={},
                     state_dir=tmp_path)


def stored(env, mid="in1"):
    return {"id": mid, "toAgentId": "machine_m1", "toMachineId": "machine_m1", "fromAgentId": "mgr_org1",
            "payload": json.dumps(env), "createdAt": "2026-11-11T10:00:00+00:00"}


def request(intent, task):
    return G.new_request(intent, task, reply_to="mgr_org1")


def run(coro):
    return asyncio.run(coro)


def test_agents_are_grouped_into_teams_by_their_skills(team):
    agents = P.local_agents(mainwin())
    assert [(a["name"], a["team"]) for a in agents] == [("Boss", "crawl"), ("Worker1", "crawl"), ("Helper", None)]
    subjects = [(s["kind"], s["id"], [m["name"] for m in ms]) for s, ms in P.resolve(None, agents)]
    assert subjects == [("team", "crawl", ["Boss", "Worker1"]), ("agent", "a3", ["Helper"])]
    (s, ms), = P.resolve([{"name": "worker1"}], agents)          # by name, any case
    assert s["id"] == "a2" and len(ms) == 1


def test_a_team_report_comes_from_its_provider_and_others_from_presence(team, monkeypatch):
    from utils import agent_status
    agents = P.local_agents(mainwin())
    reports = [P.report_for(s, ms, machine={"id": "machine_m1"}) for s, ms in P.resolve(None, agents)]
    assert reports[0]["health"] == "ok" and reports[0]["progress"]["percent"] == 30.0
    assert reports[0]["subject"]["members"] == ["Boss", "Worker1"] and len(reports[0]["presence"]) == 2
    assert reports[1]["health"] == "down" and reports[1]["headline"] == "not running"
    agent_status.report("a3", chrome="attached_existing")
    try:
        rep = P.report_for(*P.resolve([{"id": "a3"}], P.local_agents(mainwin()))[0], machine={})
        assert rep["metrics"]["readiness"]["Helper"]["chrome"] == "attached_existing"      # the ledger fallback
    finally:
        agent_status.clear("a3")


def test_a_slow_or_failing_provider_gives_presence_with_health_unknown(team):
    team["sleep"] = 0.5
    (s, ms), = P.resolve([{"kind": "team", "id": "crawl"}], P.local_agents(mainwin()))
    rep = P.report_for(s, ms, machine={}, budget_s=0.05)
    assert rep["health"] == "unknown" and rep["anomalies"][0]["id"] == "status-provider-timeout"
    assert [p["name"] for p in rep["presence"]] == ["Boss", "Worker1"]

    def broken(ctx):
        raise KeyError("x")
    P.register("crawl", broken, skills=("crawl_worker", "crawl_boss"), team="crawl")
    rep = P.report_for(s, ms, machine={})
    assert rep["health"] == "unknown" and rep["anomalies"][0]["id"] == "status-provider-error"


def test_a_report_is_kept_under_its_size_limit(team):
    rep = {"subject": {}, "recent": [{"what": "x" * 500}] * 100, "detail": "y" * 5000}
    small = P.clamp(rep, limit=4000)
    assert P._size(small) <= 4000 and small["recent_truncated"] > 0


def test_get_agent_status_sends_one_progress_per_subject_then_one_response(team, tmp_path):
    s = FakeServer()
    req = request("get_agent_status", {"subjects": [{"kind": "team", "id": "crawl"}, {"name": "Ghost"}]})
    assert run(gw(s, tmp_path).handle(stored(req))) == "done"
    kinds = [m["kind"] for m in s.sent()]
    assert kinds == ["ack", "progress", "progress", "response"]
    progress = {m["progress"]["subject"]["id"]: m["result"]["report"] for m in s.sent() if m["kind"] == "progress"}
    assert progress["crawl"]["health"] == "ok"
    assert progress["Ghost"]["health"] == "down" and progress["Ghost"]["headline"] == "not on this machine"
    resp = s.sent()[-1]
    assert resp["status"] == "done" and resp["result"]["count"] == 2 and resp["result"]["complete"]
    assert [m["msg_id"] for m in s.sent()][1:3] == [f"{req['correlation_id']}:progress:1",
                                                    f"{req['correlation_id']}:progress:2"]


def test_status_sent_as_a_tool_call_works_the_same(team, tmp_path):
    s = FakeServer()
    for i, args in enumerate(({"subjects": [{"kind": "team", "id": "crawl"}]},
                              {"input": {"subjects": [{"kind": "team", "id": "crawl"}]}})):   # with the MCP wrapper
        req = request("tool_call", {"tool": "get_agent_status", "input": args})
        assert run(gw(s, tmp_path).handle(stored(req, mid=f"in{i}"))) == "done"
        assert s.sent()[-1]["result"]["reports"][0]["subject"]["id"] == "crawl"


def test_the_owner_can_turn_status_off_in_the_allowlist(team, tmp_path, monkeypatch):
    monkeypatch.setattr(G, "allowlist", lambda: {"tools": ["ping"], "skills": []})
    s = FakeServer()
    for i, req in enumerate((request("get_agent_status", {}), request("status_diagnose", {"subject": "Boss"}),
                             request("tool_call", {"tool": "get_agent_status", "input": {}}))):
        assert run(gw(s, tmp_path).handle(stored(req, mid=f"in{i}"))) == "rejected"
        assert s.sent()[-1]["error"]["code"] == "NOT_ALLOWED"
    assert {"get_agent_status", "status_diagnose"} <= set(G.DEFAULT_TOOLS)


def test_no_subjects_means_everything_on_this_machine(team, tmp_path):
    s = FakeServer()
    run(gw(s, tmp_path).handle(stored(request("get_agent_status", {}))))
    assert [r["subject"]["id"] for r in s.sent()[-1]["result"]["reports"]] in (["crawl", "a3"], ["a3", "crawl"])


def test_the_heartbeat_lists_the_agents_and_an_older_server_still_gets_one(team, tmp_path):
    s = FakeServer()
    run(gw(s, tmp_path).heartbeat())
    caps = json.loads(s.calls[0][1]["input"]["capabilities"])
    assert caps["teams"] == [{"id": "crawl", "name": "The crawl", "description": "", "members": ["a1", "a2"]}]
    assert {a["name"]: a["has_provider"] for a in caps["agents"]} == {"Boss": True, "Worker1": True, "Helper": False}
    assert caps["status"]["intents"] == ["get_agent_status", "status_diagnose"]

    old = FakeServer(reject_caps=True)
    g = gw(old, tmp_path)
    run(g.heartbeat())
    run(g.heartbeat())
    assert len(old.calls) == 2 and all("capabilities" not in v["input"] for _, v in old.calls)


def test_capabilities_stay_under_their_size_limit(team, monkeypatch):
    many = types.SimpleNamespace(agents=[agent(f"id{i}", f"Agent number {i}", [f"skill_{j}" for j in range(5)])
                                         for i in range(200)])
    caps = P.capabilities(many)
    assert P._size(caps) <= P.CAPABILITIES_MAX_BYTES and caps["agents_truncated"] > 0


def test_a_needs_human_anomaly_is_announced_once_until_it_clears(team, tmp_path):
    s = FakeServer()
    g = gw(s, tmp_path)
    run(g.handle(stored(request("get_agent_status", {}))))       # the Manager that asks gets the events
    team["anomalies"] = [{"id": "blocked", "severity": "error", "needs_human": True, "what": "captcha"},
                         {"id": "slow", "severity": "info", "needs_human": False, "what": "slow"}]
    assert run(g.anomaly_tick()) == 1
    ev = s.sent()[-1]
    assert ev["kind"] == "event" and ev["event"] == "status_anomaly" and ev["anomaly"]["id"] == "blocked"
    assert ev["_to"] == "mgr_org1" and ev["msg_id"].startswith("anomaly:machine_m1:team:crawl:blocked:")
    assert run(gw(s, tmp_path).anomaly_tick()) == 0               # still there, also after a restart
    team["anomalies"] = []
    assert run(g.anomaly_tick()) == 0
    team["anomalies"] = [{"id": "blocked", "severity": "error", "needs_human": True, "what": "captcha again"}]
    assert run(g.anomaly_tick()) == 1


def test_diagnose_scrubs_secrets_and_stays_in_the_subjects_folders(team, tmp_path):
    log = tmp_path / "eCan.log"
    log.write_text("other line\nWorker1 token=abc123 user songc@example.com\n"
                   "Worker1 Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.c2lnbmF0dXJlMTIz\n",
                   encoding="utf-8")
    members = [m for m in P.local_agents(mainwin()) if m["name"] == "Worker1"]
    out = D.diagnose({"what": "log_tail"}, members, [], log_path=log)
    assert "other line" not in out["text"] and "abc123" not in out["text"] and "songc@" not in out["text"]
    assert "eyJ" not in out["text"] and out["scrubbed"] >= 3

    (tmp_path / "work").mkdir()
    (tmp_path / "work" / "notes.md").write_text("password: hunter2\nok\n", encoding="utf-8")
    (tmp_path / "work" / ".env").write_text("X=1", encoding="utf-8")
    (tmp_path / "nas.txt").write_text("pw", encoding="utf-8")
    roots = [tmp_path / "work"]
    out = D.diagnose({"what": "file", "path": str(tmp_path / "work" / "notes.md")}, members, roots)
    assert "hunter2" not in out["text"] and "ok" in out["text"]
    for bad in (tmp_path / "work" / ".env", tmp_path / "nas.txt", tmp_path / "eCan.log"):
        with pytest.raises(PermissionError):
            D.diagnose({"what": "file", "path": str(bad)}, members, roots)


def test_status_diagnose_through_the_gateway(team, tmp_path, monkeypatch):
    s = FakeServer()
    (tmp_path / "f.txt").write_text("hello", encoding="utf-8")
    monkeypatch.setattr(P, "roots_for", lambda members, inputs=None: [tmp_path])
    req = request("status_diagnose", {"subject": {"name": "Boss"}, "what": "file", "path": str(tmp_path / "f.txt")})
    assert run(gw(s, tmp_path).handle(stored(req))) == "done"
    assert s.sent()[-1]["result"]["text"] == "hello"
    req = request("status_diagnose", {"subject": {"name": "Boss"}, "what": "file", "path": "C:/Windows/win.ini"})
    assert run(gw(s, tmp_path).handle(stored(req, mid="in2"))) == "refused"
    req = request("status_diagnose", {"subject": {"name": "Ghost"}, "what": "log_tail"})
    assert run(gw(s, tmp_path).handle(stored(req, mid="in3"))) == "not_found"


def test_the_local_tool_returns_the_same_report(team):
    from agent.mcp.server.api.ecan_ai.ecan_ai_api import ecan_ai_api_get_agent_status
    rep = ecan_ai_api_get_agent_status(mainwin(), {"team": "crawl"})
    assert rep["health"] == "ok" and rep["subject"]["id"] == "crawl"
    assert ecan_ai_api_get_agent_status(mainwin(), {"agent_id": "nobody"})["health"] == "down"


# ── the product research provider ─────────────────────────────────────────────────

def _research(tmp_path, *, blocked=False, limited=0, dup=0, reused_dup=0):
    from agent.ec_skills.product_research import store
    root = tmp_path / "research"
    (root / "_queue").mkdir(parents=True)
    (root / "_queue" / "phrases.txt").write_text("garden hose\nfire pit\nhammock\n", encoding="utf-8")
    t = store.now()
    store.write_table(store.queue_status_path(root), store.QUEUE_COLS, [
        {"phrase": "garden hose", "slug": "garden_hose", "state": "done", "products": "20/20", "attempts": "0",
         "updated": t, "note": "20/20 products", "bytes": ""},
        {"phrase": "fire pit", "slug": "fire_pit", "state": "crawling", "products": "20", "attempts": "0",
         "updated": t, "note": "", "bytes": ""}], "queue")
    rows, pdir = [], root / "fire_pit"
    (pdir / "raw").mkdir(parents=True)
    for i in range(1, 8):
        asin = f"B{i}"
        note = ("reviews limited (8 top), 5 img, 1 vid" if i <= limited else
                "20 neg, 8 pos, 5 img, 1 vid" + (", reused from x" if limited < i <= limited + reused_dup else ""))
        same = limited < i <= limited + reused_dup + dup
        neg = [{"id": f"r{i}"}]
        rec = {"asin": asin, "neg_reviews": neg, "pos_reviews": neg if same else [{"id": f"p{i}"}]}
        (pdir / "raw" / f"{asin}.json").write_text(json.dumps(rec), encoding="utf-8")
        rows.append({"rank": str(i), "asin": asin, "state": "done", "worker": "crawler1", "attempts": "0",
                     "updated": t, "note": note})
    rows.append({"rank": "8", "asin": "B8", "state": "failed", "worker": "crawler2", "attempts": "3",
                 "updated": t, "note": "no result within 15 min"})
    store.write_table(store.status_path(pdir), store.PRODUCT_COLS, rows, "fire pit")
    if blocked:
        store.set_blocked(root, "captcha", "crawler1", "https://www.amazon.com/")
    return root


def _pr_report(root, since=None):
    from agent.ec_skills.product_research import status as S
    return S.status(P.StatusContext({"kind": "team", "id": "product_research"}, [], since=since,
                                    inputs={"research_root": str(root)}))


def test_product_research_reports_progress_rate_and_current_work(tmp_path):
    rep = _pr_report(_research(tmp_path))
    assert rep["health"] == "ok"
    assert rep["progress"]["done"] == 1 and rep["progress"]["total"] == 3 and rep["progress"]["percent"] == 33.3
    assert rep["progress"]["total_is_moving"] and rep["progress"]["secondary"][0]["label"] == "seeds"
    assert rep["metrics"]["products_since"] == 7 and rep["metrics"]["failed_since"] == 1
    assert rep["current"] == [{"what": "fire pit", "detail": "7/20 products, 1 failed"}]
    assert [a["id"] for a in rep["anomalies"]] == ["product-failures"]
    assert rep["recent"][0] == {"ts": rep["recent"][0]["ts"], "kind": "finished", "what": "garden hose",
                                "detail": "20/20 products"}


def test_product_research_flags_a_block_the_review_limit_and_duplicate_reviews(tmp_path):
    rep = _pr_report(_research(tmp_path, blocked=True, limited=2, dup=2, reused_dup=1))
    by_id = {a["id"]: a for a in rep["anomalies"]}
    assert rep["health"] == "blocked"
    assert by_id["blocked"]["needs_human"] and by_id["amazon-review-limit"]["needs_human"]
    assert by_id["duplicate-reviews"]["severity"] == "error" and "2 of the 5" in by_id["duplicate-reviews"]["evidence"]
    assert not by_id["reused-duplicate-reviews"]["needs_human"]


def test_product_research_counts_only_what_happened_since_the_last_report(tmp_path):
    rep = _pr_report(_research(tmp_path), since="2999-01-01T00:00:00+00:00")
    assert rep["metrics"]["products_since"] == 0 and rep["recent"] == []
    assert rep["progress"]["done"] == 1                     # totals don't depend on the window


def test_product_research_registers_as_a_team_for_its_skills():
    P.providers()
    p = P.provider_for(["product_crawler_00"])
    assert p is not None and p.team == "product_research" and P.provider_for(["product_research_manager_00"]) is p
