import datetime as dt
import json

import openpyxl

from agent.ec_skills import chat_review as cr

T = dt.datetime(2026, 11, 4, 2, 0, tzinfo=dt.timezone.utc)


def _t(q, a, cust="c1", pid="9"):
    return {"question": q, "answer": a, "customer_id": cust, "product_id": pid, "created_at": T}


def test_rules_catch_stalls_banned_words_and_repeats_and_digits_are_masked():
    turns = [_t("有M码吗", "稍等"), _t("质量好吗", "全网第一好"), _t("在吗", "在的亲"), _t("在吗", "在的亲"),
             _t("电话13800138000", "")]
    got = cr.rule_issues(turns)
    assert got[0] == ["只说稍等"] and "违禁词：全网第一" in got[1][0] and got[3] == ["重复回复"] and got[4] == ["没答"]
    assert 2 not in got and cr.mask("电话13800138000") == "电话13****00"


def test_quality_merges_model_grades_and_writes_the_excel(tmp_path):
    turns = [_t("多久发货", "今天发"), _t("能退吗", "随便退，还送您礼品")]
    asked = []

    def ask(p):
        asked.append(p)
        return json.dumps({"items": [{"no": 2, "score": 2, "issues": ["乱承诺", "不存在的类型"], "note": "送礼品没依据"}]},
                          ensure_ascii=False)
    out = cr.run_for_store("quality", "douyin-x", str(tmp_path), turns=turns, ask=ask, now=dt.datetime(2026, 11, 4, 10))
    assert "Q：能退吗" in asked[0] and "有问题的 1 条" in out["summary"] and "乱承诺 1" in out["summary"]
    rows = list(openpyxl.load_workbook(out["path"])["有问题的回复"].iter_rows(values_only=True))
    assert rows[1][4] == "乱承诺" and rows[1][0] == "11-04 10:00"


def test_voice_counts_topics_here_not_in_the_model():
    turns = [_t("M码多大", "x", pid="1"), _t("L码呢", "x", pid="1"), _t("几天到", "x", pid="2")]

    def ask(p):
        if "主题只能从" in p:
            return json.dumps({"labels": [[1, "尺码"], [2, "尺码"], [3, "物流发货"]]}, ensure_ascii=False)
        assert "尺码 2 条" in p
        return json.dumps({"suggestions": ["详情页加尺码表"]}, ensure_ascii=False)
    text, sheets = cr.voice(turns, ask, {"days": 7})
    assert sheets["主题"][0]["主题"] == "尺码" and sheets["主题"][0]["问得多的商品ID"] == "1"
    assert "详情页加尺码表" in text and "尺码 2" in text


def test_no_turns_says_so(tmp_path):
    assert "没有客服回复记录" in cr.run_for_store("voice", "s", str(tmp_path), turns=[])["summary"]
