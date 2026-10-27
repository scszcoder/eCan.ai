"""An agent that keeps judging its own steps as failed is nudged, then stopped,
even when it varies its attempts (browser-use's loop detector only sees repeated
actions; 拼多多 publish on KEN 2026-10-28 spent ~50 steps like that)."""
from agent.ec_skills.browser_node.runner import StuckWatch

FAIL = "Previous upload to element {} failed; the error panel still shows 请上传预览图. Verdict: Failure"


def test_the_same_failure_three_times_nudges_and_progress_resets():
    w = StuckWatch()
    assert [w.step(FAIL.format(i * 1000)) for i in range(2)] == ["", ""]
    assert w.step("Uploaded the image; the control is gone. Verdict: Success") == ""
    assert [w.step(FAIL.format(i * 1000)) for i in range(3)] == ["", "", "nudge"]


def test_five_different_failures_in_a_row_nudge():
    w = StuckWatch()
    fails = ["Could not find the size box. Verdict: Failure", "The 确定 button is disabled. Verdict: Failure",
             "Title field rejected the input. Verdict: Failure", "Dropdown closed without a value. Verdict: Failure",
             "Upload went to the wrong row. Verdict: Failure"]
    assert [w.step(v) for v in fails] == ["", "", "", "", "nudge"]


def test_same_verdict_three_times_nudges_even_without_failure_words():
    w = StuckWatch()
    same = "Scrolled to the SKU table; the 柠檬黄 header still has no rows. Verdict: Uncertain"
    assert [w.step(same) for _ in range(3)] == ["", "", "nudge"]


def test_stops_after_the_last_nudge_is_used():
    w = StuckWatch(max_nudges=2)
    out = [w.step(FAIL.format(i)) for i in range(15)]
    assert out.count("nudge") == 2 and out[-1] == "stop"


def test_a_varied_productive_run_is_left_alone():
    w = StuckWatch()
    verdicts = [f"Filled field {k} with the listing value. Verdict: Success" for k in range(30)]
    assert not any(w.step(v) for v in verdicts)
