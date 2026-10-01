"""media-gen async mode: submit once, park the task, resume when the job watcher
records the outcome. Runs the real node in a real LangGraph graph with a
checkpointer against the fake llm-proxy from test_media_proxy."""

import time
import types
from typing import Any, TypedDict

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from agent.ec_skills.media import media_gen_node, media_job_watcher as watcher
from tests.unit.test_media_proxy import FakeProxy, _client


class _Ctx(TypedDict, total=False):
    task_id: str
    run_id: str


class _Runner:
    def __init__(self):
        self.delivered, self.held, self.restored = [], [], []

    def hold_pending_timeout(self, task_id, seconds):
        self.held.append((task_id, seconds))
        return 600.0

    def restore_pending_timeout(self, task_id, prev):
        self.restored.append((task_id, prev))

    def deliver_to_task(self, task_id, event_type, request):
        self.delivered.append((task_id, event_type, request))
        return True


@pytest.fixture
def env(tmp_path, monkeypatch):
    proxy = FakeProxy()
    runner = _Runner()
    monkeypatch.setattr(media_gen_node, "_make_client", lambda: _client(proxy))
    monkeypatch.setattr(media_gen_node, "generated_medias_root", lambda: str(tmp_path / "generated_medias"))
    from agent.ec_skills.media import proxy_media_client
    monkeypatch.setattr(proxy_media_client.ProxyMediaClient, "from_ecanai", classmethod(lambda cls: _client(proxy)))
    monkeypatch.setattr(watcher, "_store_path", lambda: str(tmp_path / "pending_media_jobs.json"))
    monkeypatch.setattr(watcher, "_runner_for", lambda task_id: runner)
    monkeypatch.setattr(watcher, "POLL_INITIAL_S", 0.05)
    monkeypatch.setattr(watcher, "POLL_MAX_S", 0.1)
    watcher._jobs.clear()
    monkeypatch.setattr(watcher, "_loaded", True)
    yield types.SimpleNamespace(proxy=proxy, runner=runner, tmp=tmp_path)
    watcher._jobs.clear()


def _graph(**cfg):
    inputs = {k: {"type": "constant", "content": v} for k, v in cfg.items()}
    node = media_gen_node.build_media_gen_node({"title": "MediaGen_1", "inputsValues": inputs},
                                               "media-gen_x", "sk", "owner", None)
    g = StateGraph(dict, context_schema=_Ctx)
    g.add_node("media", node)
    g.add_edge(START, "media")
    g.add_edge("media", END)
    return g.compile(checkpointer=InMemorySaver())


CFG = {"configurable": {"thread_id": "th1"}}
CTX = {"task_id": "task-1", "run_id": "run-1"}


def _start(graph):
    return graph.invoke({"messages": [], "attributes": {}, "result": {}}, CFG, context=CTX)


def _wait(pred, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.05)
    return False


def test_async_video_parks_resumes_and_publishes(env):
    graph = _graph(mediaType="video", modelName="seedance-1.0-pro", prompt="a dog", runMode="async")
    out = _start(graph)
    assert "__interrupt__" in out
    assert len(env.proxy.jobs) == 1 and env.runner.held[0][0] == "task-1"

    # An unrelated wake-up before the job is done: re-park, never re-submit.
    out = graph.invoke(Command(resume={"noise": True}), CFG, context=CTX)
    assert "__interrupt__" in out and len(env.proxy.jobs) == 1

    assert _wait(lambda: env.runner.delivered), "watcher never delivered"
    task_id, event_type, request = env.runner.delivered[0]
    assert (task_id, event_type) == ("task-1", "media_gen")
    assert request["metadata"]["i_tag"] == "vid1"

    out = graph.invoke(Command(resume={"notification_to_agent": {}}), CFG, context=CTX)
    assert "__interrupt__" not in out
    assert out["result"]["media_job"]["status"] == "succeeded"
    assert out["tool_result"]["MediaGen_1"]["media_paths"] == out["result"]["media"][0]["path"]
    assert len(env.proxy.jobs) == 1 and watcher.lookup("task-1:th1:media-gen_x") is None
    assert env.runner.restored == [("task-1", 600.0)]


def test_async_timeout_cancels_and_resumes_with_error(env):
    graph = _graph(mediaType="music", modelName="suno-v5.5", prompt="slow", runMode="async", timeoutSeconds=0.3)
    assert "__interrupt__" in _start(graph)
    assert _wait(lambda: env.runner.delivered)
    assert env.proxy.calls("DELETE", "/v1/music/mus1")
    out = graph.invoke(Command(resume={}), CFG, context=CTX)
    assert out["result"]["media_error"]["code"] == "client_timeout"
    assert out["tool_result"]["MediaGen_1"]["media_error"]["code"] == "client_timeout"


def test_push_collects_the_job_at_once(env, monkeypatch):
    monkeypatch.setattr(watcher, "POLL_INITIAL_S", 3600.0)   # the regular schedule would wait an hour
    graph = _graph(mediaType="video", modelName="seedance-1.0-pro", prompt="a dog", runMode="async")
    assert "__interrupt__" in _start(graph)
    # Exactly what the proxy publishes: results is a JSON string and carries NO output URL.
    assert watcher.on_push({"id": "vid1", "acctSiteID": "site", "agentID": None, "workType": "media_gen",
                            "taskID": "vid1", "status": "succeeded", "timestamp": "2026-09-30T00:00:00Z",
                            "results": '{"id": "vid1", "object": "video", "status": "succeeded", '
                                       '"model": "seedance-1.0-pro", "error": null, "usage": {"video_seconds": 5}}'})
    assert _wait(lambda: env.runner.delivered), "push did not trigger collection"
    out = graph.invoke(Command(resume={}), CFG, context=CTX)
    assert open(out["result"]["media"][0]["path"], "rb").read().startswith(b"\x00\x00")
    assert not watcher.on_push({"workType": "rerank_search_results", "taskID": "x"})


def test_sync_mode_and_image_never_park(env):
    out = _start(_graph(mediaType="video", modelName="seedance-1.0-pro", prompt="a dog"))
    assert "__interrupt__" not in out and out["result"]["media_job"]["status"] == "succeeded"
    out = _start(_graph(mediaType="image", modelName="seedream-4.0", prompt="a cat", runMode="async"))
    assert "__interrupt__" not in out and out["result"]["media"]


def test_runner_delivers_and_holds_timeout():
    from agent.ec_tasks.runner import TaskRunner, DEFAULT_RUNTIME_EVENT_TIMEOUT_SEC
    from queue import Queue
    task = types.SimpleNamespace(id="t1", name="T", queue=Queue())
    woke = []
    fake = types.SimpleNamespace(agent=types.SimpleNamespace(tasks=[task], card=types.SimpleNamespace(name="A")),
                                 _task_states={}, _ensure_task_execution_alive=lambda t, e: woke.append(e))
    fake._find_task = lambda tid: TaskRunner._find_task(fake, tid)
    assert TaskRunner.deliver_to_task(fake, "t1", "media_gen", {"id": "j"})
    assert task.queue.get_nowait()["id"] == "j" and woke == ["media_gen"]
    assert not TaskRunner.deliver_to_task(fake, "nope", "media_gen", {})
    prev = TaskRunner.hold_pending_timeout(fake, "t1", DEFAULT_RUNTIME_EVENT_TIMEOUT_SEC + 500)
    assert prev is None and fake._task_states["t1"]["_runtime_event_timeout"] == DEFAULT_RUNTIME_EVENT_TIMEOUT_SEC + 500
    TaskRunner.restore_pending_timeout(fake, "t1", prev)
    assert "_runtime_event_timeout" not in fake._task_states["t1"]
