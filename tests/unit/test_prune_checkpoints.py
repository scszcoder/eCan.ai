"""prune_thread_to_latest: a task parked on an interrupt keeps only its latest checkpoint.

2026-10-21: chip-doc crawler workers wait for their next batch on an interrupt
forever; InMemorySaver kept every checkpoint of every round, each a copy of a
state that grows by one batch message per round, and the app hit its 7.5 GB guard.
"""
import operator
from typing import Annotated, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from agent.checkpointing import prune_thread_to_latest


class State(TypedDict):
    history: Annotated[list, operator.add]
    batch: str


def _graph(saver):
    g = StateGraph(State)
    g.add_node("wait", lambda s: {"batch": interrupt("next batch")})
    g.add_node("work", lambda s: {"history": [s["batch"]]})
    g.add_edge(START, "wait")
    g.add_edge("wait", "work")
    g.add_edge("work", "wait")
    return g.compile(checkpointer=saver)


def _rounds(prune, n=30):
    saver = InMemorySaver()
    graph, cfg = _graph(saver), {"configurable": {"thread_id": "worker-1"}}
    graph.invoke({"history": [], "batch": ""}, cfg)
    sizes = []
    for i in range(n):
        graph.invoke(Command(resume=f"batch {i} " + "x" * 2000), cfg)
        if prune:
            prune_thread_to_latest(saver, "worker-1")
        sizes.append(sum(len(v[1]) for v in saver.blobs.values()))
    return graph, saver, cfg, sizes


def test_unpruned_saver_grows_quadratically():
    _, _, _, sizes = _rounds(prune=False)
    assert sizes[-1] > 5 * sizes[len(sizes) // 3]  # 3x the rounds, ~9x the bytes


def test_pruned_saver_holds_only_the_latest_state():
    graph, saver, cfg, sizes = _rounds(prune=True)
    assert len(saver.storage["worker-1"][""]) == 1
    # the state still grows by one message per round, but only one copy of it is kept
    assert sizes[-1] < 30 * 2100 * 1.5


def test_resume_after_pruning_continues_the_same_state():
    graph, saver, cfg, _ = _rounds(prune=True, n=5)
    graph.invoke(Command(resume="batch 5"), cfg)
    history = graph.get_state(cfg).values["history"]
    assert [h.split(" x")[0].strip() for h in history] == [f"batch {i}" for i in range(6)]


def test_other_threads_are_untouched():
    saver = InMemorySaver()
    graph = _graph(saver)
    for t in ("a", "b"):
        cfg = {"configurable": {"thread_id": t}}
        graph.invoke({"history": [], "batch": ""}, cfg)
        for i in range(3):
            graph.invoke(Command(resume=f"{t}{i}"), cfg)
    before = {k for k in saver.blobs if k[0] == "b"}
    prune_thread_to_latest(saver, "a")
    assert {k for k in saver.blobs if k[0] == "b"} == before
    assert len(saver.storage["b"][""]) > 1
