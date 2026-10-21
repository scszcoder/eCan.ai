"""One task assigned to several agents: the first agent runs the pooled task
object, every other agent a runtime copy with its own queue and run state, so
a message addressed to an agent is run by that agent (2026-10-18: a message to
做图专家小王 ran as tester00 because three agents drained one shared queue).
Scheduled tasks stay one shared object (each occurrence runs once)."""
from types import SimpleNamespace

from agent.agent_converter import _resolve_from_compiled_pool
from agent.ec_tasks.models import ManagedTask

WANG, TESTER, EBAY = "agent_wang", "agent_tester", "agent_ebay"


def _pooled(trigger=("message",), **kw):
    return ManagedTask(id="task_img", contextId="ctx", name="电商做图00", trigger=list(trigger),
                       metadata={"task_vars": {"store": "A"}}, state={"k": 1}, **kw)


def _resolve(pool, agent_id):
    stub = SimpleNamespace(id="task_img", name="电商做图00", skill=None)
    return _resolve_from_compiled_pool([stub], pool, "task", agent_id, agent_id)[0]


def test_each_further_agent_gets_its_own_queue_and_run_state():
    pooled = _pooled(skill=SimpleNamespace(name="亚马逊电商做图00"))
    t_tester = _resolve([pooled], TESTER)
    t_wang = _resolve([pooled], WANG)
    t_ebay = _resolve([pooled], EBAY)

    assert t_tester is pooled                          # the first agent runs the pooled object
    for c, aid in ((t_wang, WANG), (t_ebay, EBAY)):
        assert c is not pooled and c.id == pooled.id and c.name == pooled.name
        assert c.agent_id == aid
        assert c.skill is pooled.skill                 # same compiled skill
        assert c.queue is not pooled.queue
        assert c.run_id != pooled.run_id
        assert c.pause_event is not pooled.pause_event and c.pause_event.is_set()
        assert c.cancellation_event is not pooled.cancellation_event
        assert c.trigger == ["message"] and c.trigger is not pooled.trigger
        assert c.metadata == pooled.metadata and c.metadata is not pooled.metadata
    assert t_wang.queue is not t_ebay.queue and t_wang.run_id != t_ebay.run_id

    # A message put on 小王's queue is only on 小王's queue.
    t_wang.queue.put_nowait({"to": WANG})
    assert pooled.queue.empty() and t_ebay.queue.empty() and t_wang.queue.qsize() == 1

    # Per-agent changes stay per agent.
    t_wang.metadata["task_vars"]["store"] = "B"
    t_wang.state["k"] = 2
    t_wang.trigger.append("x")
    t_wang.skill = SimpleNamespace(name="other")
    assert pooled.metadata["task_vars"]["store"] == "A" and pooled.state["k"] == 1
    assert pooled.trigger == ["message"] and pooled.skill.name == "亚马逊电商做图00"


def test_reloading_the_first_agent_gets_the_same_pooled_object_again():
    pooled = _pooled()
    assert _resolve([pooled], TESTER) is pooled
    assert _resolve([pooled], WANG) is not pooled
    assert _resolve([pooled], TESTER) is pooled        # e.g. agent refresh / edit


def test_a_task_with_one_agent_is_unchanged():
    pooled = _pooled()
    assert _resolve([pooled], WANG) is pooled
    assert pooled.agent_id == ""                       # not rewritten


def test_a_scheduled_shared_task_stays_one_object():
    for trig in (["schedule"], ["schedule", "message"], ["after"]):
        pooled = _pooled(trigger=trig)
        assert _resolve([pooled], TESTER) is pooled
        assert _resolve([pooled], WANG) is pooled      # one owner, one run per occurrence


def test_legacy_message_trigger_names_count_as_message():
    pooled = _pooled(trigger=["interaction", "a2a_queue"])
    _resolve([pooled], TESTER)
    assert _resolve([pooled], WANG) is not pooled
