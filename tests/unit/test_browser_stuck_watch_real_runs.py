"""The stuck watch on two real runs (KEN 2026-10-31, step verdicts and goals as logged).

抖店 run 68 spent 35 steps on the same attributes, writing "I've been stuck"
between "the page has loaded" steps; nothing fired and the run died. 拼多多
run 69 wrote "upload attempts have been failing" while the error moved row by
row, then published: it may be nudged, never stopped.
"""
import json
from pathlib import Path

from agent.ec_skills.browser_node.runner import StuckWatch, goals_repeating

RUNS = json.loads((Path(__file__).parent / "data" / "browser_step_verdicts_ken_2026_10_31.json")
                  .read_text(encoding="utf-8"))


def _replay(steps):
    watch, out = StuckWatch(), []
    for s in steps:
        verdict = watch.step(s["eval"])
        if verdict:
            out.append((s["step"], verdict))
    return out


def test_an_agent_stuck_between_other_steps_is_nudged_soon():
    fired = _replay(RUNS["douyin_run68_stuck_on_attributes"])
    assert fired and fired[0][1] == "nudge" and fired[0][0] <= 36
    assert len([v for _, v in fired if v == "nudge"]) >= 2      # the second nudge is where the model steps up


def test_a_progressing_agent_that_says_failing_is_never_stopped():
    fired = _replay(RUNS["pdd_run69_progressing_then_published"])
    assert all(v == "nudge" for _, v in fired)


def test_near_identical_goals_count_as_repeating():
    g = "Fill remaining required attributes: 风格(运动风), 服饰工艺(印花), 适用年龄(儿童), 功能(亲肤). "
    assert goals_repeating([g + "Then fix sizes.", g + "Then upload detail images and fix sizes.", g + "Then fix sizes."])
    assert not goals_repeating(["Upload main_1.png", "Fill the title", "Pick the category"])
