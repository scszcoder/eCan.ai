import datetime as dt
import os

from agent.ec_skills import campaigns as c

NOW = dt.datetime(2026, 11, 5, 10, 0)
T = lambda y, m, d, h=0: int(dt.datetime(y, m, d, h, tzinfo=c.CN).timestamp())   # noqa: E731


def _item(name, subs, can=False, rule=False):
    # the shape /mmc/activity/seller_activity_feed returns (synthetic values)
    return {"feed_act": {"main_act": {"can_apply": can, "access_rule_check_pass": rule,
                                      "main_act": {"name": name, "act_marketing_type": 2, "main_activity_id": "900"}}},
            "sub_acts": subs}


def _sub(name, a0, a1, can=False, rule=False, done=0):
    return {"name": name, "scene_label": {"name": "秒杀"}, "apply_start_time": a0, "apply_end_time": a1,
            "activity_start_time": T(2026, 11, 10), "activity_end_time": T(2026, 11, 12), "can_apply": can,
            "access_rule_check_pass": rule, "apply_status": 0, "apply_success_item_num": done, "id": "901"}


def test_rows_and_summary_point_at_signups_closing_soon(tmp_path):
    items = [_item("秒杀日A", [_sub("报名1", T(2026, 11, 1), T(2026, 11, 6, 20), can=True, rule=True),
                              _sub("报名2", T(2026, 11, 1), T(2026, 11, 20), can=True, rule=True)]),
             _item("大促B", [_sub("海选", T(2026, 11, 1), T(2026, 12, 1), rule=False)]),
             _item("已结束C", [_sub("旧", T(2026, 10, 1), T(2026, 10, 2), can=True, rule=True)])]
    rows = c.douyin_rows(items)
    assert len(rows) == 4 and rows[0]["type"] == "低价秒杀" and rows[0]["apply_end"] == dt.datetime(2026, 11, 6, 20)
    assert rows[2]["why_not"] == "店铺不满足报名条件"
    text = c.summary(rows, "s1", 3, NOW, [])
    assert "正在报名的平台活动 2 个（3 个报名项）" in text and "能报的 2 项" in text
    assert "「秒杀日A」报名1：11-06 20:00 截止报名" in text and "报名2" not in text
    assert "不会替你报名" in text
    assert os.path.isfile(c.write_xlsx(rows, str(tmp_path / "x.xlsx")))


def test_nothing_joinable_says_why():
    rows = c.douyin_rows([_item("大促B", [_sub("海选", T(2026, 11, 1), T(2026, 12, 1), rule=False)])])
    assert "一个都报不了（店铺不满足报名条件）" in c.summary(rows, "s1", 3, NOW, [])
