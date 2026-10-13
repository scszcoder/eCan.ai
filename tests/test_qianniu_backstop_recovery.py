"""The 千牛 backstop accelerates — bounded — while 接待中心 is off the chat list.

alpha yx 2026-10-13: a computed 千牛 reply stalled ~5.5 min because the window
was parked on 商品管理; neither the send nor the backstop could act, and the
backstop only retried every 90 s. When the 正在接待 list is unreachable the loop
now re-checks on a short cadence for a bounded burst, so the reply leaves within
~_BACKSTOP_RECOVER_S of 接待中心 returning — without spinning OCR when it stays
closed.
"""

from agent.ec_skills.browser_use_extension.hooks.external.qianniu_chat.observer import (
    _backstop_recovery_state as step,
)

TRIES = 3


def test_reachable_keeps_base_cadence_and_stays_armed():
    # on_tab True → no fast passes, armed for the next outage.
    assert step(True, 0, True, TRIES) == (0, True)
    assert step(True, 2, False, TRIES) == (0, True)  # recovered mid-burst → base + re-armed


def test_first_off_list_pass_starts_a_bounded_burst():
    fast_left, ready = step(False, 0, True, TRIES)
    assert fast_left == TRIES and ready is False


def test_burst_counts_down_then_falls_back_without_re_arming():
    fast_left, ready = TRIES, False
    counts = []
    for _ in range(TRIES + 2):                       # keep failing past the burst
        fast_left, ready = step(False, fast_left, ready, TRIES)
        counts.append(fast_left)
    assert counts == [TRIES - 1, TRIES - 2, 0, 0, 0]  # TRIES=3: 2,1,0 then clamped at 0
    assert ready is False                            # never re-arms while still off-list


def test_recovery_re_arms_for_the_next_outage():
    # burst spent, still off-list → base cadence
    assert step(False, 0, False, TRIES) == (0, False)
    # 接待中心 came back
    assert step(True, 0, False, TRIES) == (0, True)
    # next outage gets a fresh burst
    assert step(False, 0, True, TRIES) == (TRIES, False)
