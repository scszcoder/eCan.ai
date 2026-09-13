"""Unified execution C4 — the desktop enqueues a turn instead of dispatching.

The property worth more than the feature: **one path per task, never two.** A
task that is both launcher-dispatched and queued executes twice, from two
processes, answering one customer from two places — and nothing upstream
prevents it. So the tests below spend most of their time on what happens when
things go wrong, because every one of those cases is a chance to silently take
the other path:

  * a failed enqueue must NOT fall back to the launcher;
  * a client with the queue switched off must refuse a queue-marked task rather
    than dispatching it, because the server-side scheduler may already have been
    flipped for that task;
  * the per-task choice is one field, so it cannot say both.
"""

import json

import pytest

from agent.cloud_api import turn_queue


class _Task:
    """Enough of a ManagedTask for the enqueue path."""

    def __init__(self, **kw):
        self.id = kw.get("id", "task_1")
        self.name = kw.get("name", "t")
        self.agent_id = kw.get("agent_id", "agent_1")
        self.metadata = kw.get("metadata", {})
        self.residency = kw.get("residency", "any")
        self.lifetime = kw.get("lifetime", "conversation")
        self.requires = kw.get("requires", [])
        self.owner = kw.get("owner", "")
        self.state = {}


# ===========================================================================
# Which path a task is on
# ===========================================================================

def test_tasks_default_to_the_launcher():
    """Nothing changes until a task is deliberately flipped."""
    assert turn_queue.task_execution_path(_Task()) == turn_queue.PATH_LAUNCHER
    assert not turn_queue.task_uses_queue(_Task())


def test_a_task_can_be_marked_for_the_queue():
    task = _Task(metadata={"execution_path": "queue"})
    assert turn_queue.task_uses_queue(task)


def test_the_choice_is_one_field():
    """Two booleans could both be true; one field cannot say both."""
    task = _Task(metadata={"execution_path": "queue"})
    assert turn_queue.task_execution_path(task) == turn_queue.PATH_QUEUE
    task.metadata["execution_path"] = "launcher"
    assert turn_queue.task_execution_path(task) == turn_queue.PATH_LAUNCHER


def test_an_unknown_path_reads_as_the_launcher():
    """An unrecognised value must not enable the new path by accident."""
    assert turn_queue.task_execution_path(_Task(metadata={"execution_path": "quene"})) \
        == turn_queue.PATH_LAUNCHER


def test_queue_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv(turn_queue.ENV_ENABLED, raising=False)
    assert not turn_queue.queue_enabled()
    monkeypatch.setenv(turn_queue.ENV_ENABLED, "1")
    assert turn_queue.queue_enabled()


def test_execution_path_survives_the_db_conversion():
    """A scalar needs its own line in the metadata carry list.

    task_vars and browser_identity are copied as dicts; a string key not named
    there is dropped, which is how a flip ends up doing nothing at all.
    """
    from agent.agent_converter import _convert_dict_to_task

    task = _convert_dict_to_task({
        "id": "task_1", "name": "t",
        "metadata": {"execution_path": "queue", "task_vars": {"a": 1}},
    })
    assert task.metadata.get("execution_path") == "queue"
    assert turn_queue.task_uses_queue(task)


# ===========================================================================
# What the turn carries
# ===========================================================================

def test_payload_carries_the_task_and_its_placement():
    """A turn row names an owner/conversation/agent but never a task."""
    task = _Task(requires=["browser_local"], lifetime="turn", residency="cloud")
    payload = turn_queue.build_enqueue_payload(
        task, owner="o@example.com", trigger_type="message")

    assert payload["owner"] == "o@example.com"
    assert payload["agent_id"] == "agent_1"
    assert payload["requires"] == ["browser_local"]
    assert payload["lifetime"] == "turn"
    assert payload["residency"] == "cloud"
    assert json.loads(payload["input"])["task_id"] == "task_1"


def test_payload_refuses_a_task_with_no_owner():
    with pytest.raises(turn_queue.TurnQueueError):
        turn_queue.build_enqueue_payload(_Task(), owner="")


def test_dedication_travels_as_a_requirement_not_a_binding():
    """Isolation is a scheduling decision, so it rides on the work."""
    class _Agent:
        id = "agent_1"
        dedicated_vehicle_id = "pod_7"

    requires = turn_queue.turn_requires(_Task(requires=["gpu"]), _Agent())
    assert requires == ["gpu", "dedicated:agent_1"]


def test_no_dedication_adds_nothing():
    class _Agent:
        id = "agent_1"
        dedicated_vehicle_id = ""

    assert turn_queue.turn_requires(_Task(requires=["gpu"]), _Agent()) == ["gpu"]


# ===========================================================================
# The runner seam — where double execution would happen
# ===========================================================================

class _Runner:
    """Just the method under test, bound to a stand-in."""

    def __init__(self):
        self.agent = None

    _enqueue_cloud_task_turn = None      # filled in below


@pytest.fixture
def runner():
    from agent.ec_tasks.runner import TaskRunner

    obj = _Runner()
    obj._enqueue_cloud_task_turn = TaskRunner._enqueue_cloud_task_turn.__get__(obj, _Runner)
    return obj


def test_a_launcher_task_is_not_handled_here(runner):
    """handled=False means "carry on down the old path", which is correct here."""
    result, handled = runner._enqueue_cloud_task_turn(_Task(), "message")
    assert handled is False
    assert result is None


def test_a_queue_task_refuses_when_the_client_has_the_queue_off(runner, monkeypatch):
    """The dangerous case: this task may already be served from the queue.

    Falling through to the launcher would make this machine the second copy.
    """
    monkeypatch.delenv(turn_queue.ENV_ENABLED, raising=False)
    task = _Task(metadata={"execution_path": "queue"})

    result, handled = runner._enqueue_cloud_task_turn(task, "message")
    assert handled is True                       # NOT passed to the launcher
    assert result["success"] is False
    assert turn_queue.ENV_ENABLED in result["error"]


def test_a_failed_enqueue_does_not_fall_back(runner, monkeypatch):
    monkeypatch.setenv(turn_queue.ENV_ENABLED, "1")

    def _boom(*a, **kw):
        raise turn_queue.TurnQueueError("control plane down")

    monkeypatch.setattr(turn_queue, "enqueue_task_turn", _boom)
    task = _Task(metadata={"execution_path": "queue"}, owner="o@example.com")

    result, handled = runner._enqueue_cloud_task_turn(task, "message")
    assert handled is True                       # the launcher is never reached
    assert result["success"] is False
    assert "control plane down" in result["error"]


def test_an_unexpected_error_does_not_fall_back_either(runner, monkeypatch):
    """Any exception, not just ours — the fallback is what must not happen."""
    monkeypatch.setenv(turn_queue.ENV_ENABLED, "1")

    def _boom(*a, **kw):
        raise ValueError("something else entirely")

    monkeypatch.setattr(turn_queue, "enqueue_task_turn", _boom)
    task = _Task(metadata={"execution_path": "queue"}, owner="o@example.com")

    result, handled = runner._enqueue_cloud_task_turn(task, "message")
    assert handled is True
    assert result["success"] is False


def test_a_successful_enqueue_keeps_the_server_turn_id(runner, monkeypatch):
    """The turn id is the server's idempotency key; the client never mints one."""
    monkeypatch.setenv(turn_queue.ENV_ENABLED, "1")
    monkeypatch.setattr(
        turn_queue, "enqueue_task_turn",
        lambda *a, **kw: {"turn_id": "turn_abc", "created": True, "turn": {}},
    )
    task = _Task(metadata={"execution_path": "queue"}, owner="o@example.com")

    result, handled = runner._enqueue_cloud_task_turn(task, "message")
    assert handled is True
    assert result == {"success": True, "turn_id": "turn_abc"}
    assert task.state["turn_id"] == "turn_abc"


# ===========================================================================
# Configuration failures say what to do about them
# ===========================================================================

def test_missing_credential_names_the_real_blocker(monkeypatch):
    """A 401 nobody can interpret is worse than a refusal that explains itself."""
    monkeypatch.delenv(turn_queue.ENV_TOKEN, raising=False)
    with pytest.raises(turn_queue.TurnQueueNotConfigured) as exc:
        turn_queue._credential()
    assert turn_queue.ENV_TOKEN in str(exc.value)


def test_endpoint_is_derived_from_the_graphql_host(monkeypatch):
    monkeypatch.setenv(turn_queue.ENV_ENDPOINT, "https://x/ecbAccountManager")
    assert turn_queue._account_manager_url() == "https://x/ecbAccountManager"
