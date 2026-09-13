"""A serving turn must not be reported done while parked on its first node.

`build_pend_event_node` calls `interrupt()` unconditionally on entry — there is
no path that consumes an event already sitting in the state. So a skill whose
loop begins with `pend_event` interrupts on its FIRST node, and the turn was
reported done having asked the model nothing:

    ENTERING node=pend_event_sVz3K
    Interrupt(value={'i_tag': 'pend_event_sVz3K'})
    reported done: 0in/0out $0.0000

The desktop never showed this because its executor auto-resumes — runner.py:
"the message is already in the state but pend_event always interrupts on first
visit; auto-resume feeds the message as a resume payload so the graph advances
to the LLM node". The worker calls execute_task_hybrid directly and skipped it.

One turn stays one complete request/response: the resume happens inside the
same call, on the checkpoint just parked at. Nothing is carried between turns,
so any pod can serve any turn without conversation-keyed threads or a shared
checkpoint.
"""

import pytest


PARKED = {'success': False, 'step': {'__interrupt__': [{'value': {'i_tag': 'pend_event_x'}}]}}
DONE = {'success': True, 'step': {'answer': 'hello'}}


class _Msg:
    def __init__(self, prompt, chat_id='chat-1'):
        self.prompt = prompt
        self.chat_id = chat_id


@pytest.fixture
def wm():
    import agent.cloud_worker.worker_main as module
    return module


@pytest.fixture(autouse=True)
def _executor():
    """execute_task_hybrid is imported lazily from its own module inside the
    function under test, so patching worker_main would miss it."""
    import agent.ec_tasks.executor as executor
    return executor


def test_a_parked_run_is_recognised(wm):
    assert wm._interrupted_at_pend_event(PARKED)


@pytest.mark.parametrize('response', [
    DONE,
    {'success': False, 'step': {'error': 'boom'}},   # a real failure, not a park
    {'success': False},
    None,
    'not-a-dict',
])
def test_anything_else_is_not_a_park(wm, response):
    assert not wm._interrupted_at_pend_event(response)


def test_a_finished_run_is_returned_untouched(wm, monkeypatch, _executor):
    """No interrupt, no second invocation."""
    calls = []
    monkeypatch.setattr(_executor, 'execute_task_hybrid',
                        lambda *a, **k: calls.append(a) or DONE)

    out = wm._auto_resume_pend_event(object(), DONE, _Msg('hi'))

    assert out is DONE
    assert calls == [], 'a completed run must not be resumed'


def test_a_parked_run_is_resumed_with_the_turns_message(wm, monkeypatch, _executor):
    seen = {}

    def _exec(task, command, **kwargs):
        seen['command'] = command
        return DONE

    monkeypatch.setattr(_executor, 'execute_task_hybrid', _exec)

    out = wm._auto_resume_pend_event(object(), PARKED, _Msg('有货吗？'))

    assert out is DONE, 'the resumed result should be returned, not the park'
    payload = seen['command'].resume
    assert payload['human_text'] == '有货吗？'
    assert payload['data']['human_text'] == '有货吗？'


def test_the_resume_event_type_is_one_pend_event_accepts(wm, monkeypatch, _executor):
    """`human_chat` skills accept `chat_message`; `send_chat` would hit the
    agent-self-echo guard and be treated as the agent's own outbound message."""
    seen = {}
    monkeypatch.setattr(_executor, 'execute_task_hybrid',
                        lambda task, command, **k: seen.update(command=command) or DONE)

    wm._auto_resume_pend_event(object(), PARKED, _Msg('hi'))

    assert seen['command'].resume['event_type'] == 'chat_message'


def test_the_resume_is_marked_as_coming_from_a_human(wm, monkeypatch, _executor):
    """The echo guard reads senderType/human_text to tell a visitor from the
    agent's own send_chat completing."""
    seen = {}
    monkeypatch.setattr(_executor, 'execute_task_hybrid',
                        lambda task, command, **k: seen.update(command=command) or DONE)

    wm._auto_resume_pend_event(object(), PARKED, _Msg('hi', chat_id='c-9'))

    ctx = seen['command'].resume['context']
    assert ctx['senderType'] == 'human'
    assert ctx['chatId'] == 'c-9'


@pytest.mark.parametrize('empty', ['', '   ', None])
def test_an_empty_message_parks_rather_than_asking_the_model_nothing(wm, monkeypatch, _executor, empty):
    calls = []
    monkeypatch.setattr(_executor, 'execute_task_hybrid',
                        lambda *a, **k: calls.append(a) or DONE)

    out = wm._auto_resume_pend_event(object(), PARKED, _Msg(empty))

    assert out is PARKED
    assert calls == [], 'resuming with nothing would ask the model to answer nothing'


def test_still_parked_after_resume_is_returned_as_parked(wm, monkeypatch, _executor):
    """A skill wanting a SECOND event this turn cannot be satisfied by a
    request/response turn — report the park, not a silent success."""
    monkeypatch.setattr(_executor, 'execute_task_hybrid', lambda *a, **k: PARKED)

    out = wm._auto_resume_pend_event(object(), PARKED, _Msg('hi'))

    assert wm._interrupted_at_pend_event(out)


def test_the_core_calls_auto_resume(wm):
    """_run_skill_once must route its result through this, or the fix is inert."""
    import inspect

    src = inspect.getsource(wm._run_skill_once)
    assert '_auto_resume_pend_event' in src
