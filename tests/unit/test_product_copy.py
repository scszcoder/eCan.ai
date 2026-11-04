import datetime as dt
import json
import os

import openpyxl
from PIL import Image

from agent.ec_skills import product_copy as pc


def _product(folder, name, notes="", rivals="", pics=((800, 800),)):
    d = os.path.join(folder, "输入", name)
    os.makedirs(d, exist_ok=True)
    for i, size in enumerate(pics, 1):
        Image.new("RGB", size, "white").save(os.path.join(d, f"{i:02d}.png"))
    if notes:
        open(os.path.join(d, "说明.txt"), "w", encoding="utf-8").write(notes)
    if rivals:
        open(os.path.join(d, "竞品标题.txt"), "w", encoding="utf-8").write(rivals)


def test_width_counts_hanzi_as_two_and_finds_absolute_words():
    assert pc.width("ab衬衫") == 6 and pc.banned_in("全网最低价衬衫") == ["最", "全网"]


GOOD = {"long": ["男士纯棉衬衫长袖商务休闲白衬衣", "长袖白衬衫男纯棉免烫通勤", "纯棉衬衣男士长袖修身正装"],
        "short": "纯棉白衬衫", "sku": [{"spec": "白色 L", "title": "纯棉白衬衫男长袖 白色L码"}],
        "words": {"core": ["衬衫"], "attr": ["纯棉"], "scene": ["通勤"], "selling": ["免烫"]}, "why": "x"}


def test_titles_that_break_the_rules_get_one_repair_round(tmp_path):
    _product(str(tmp_path), "ECK1", notes="男士纯棉长袖衬衫，规格：白色 L", rivals="某某衬衫男\n\n别家衬衫")
    calls = []

    def ask(prompt, images):
        calls.append((prompt, len(images)))
        bad = dict(GOOD, long=GOOD["long"][:2] + ["全网最好的衬衫" * 3])
        return json.dumps(bad if len(calls) == 1 else GOOD, ensure_ascii=False)
    out = pc.run("titles", str(tmp_path), {"platform": "抖店"}, ask=ask, now=dt.datetime(2026, 11, 5, 9, 0))
    assert len(calls) == 2 and calls[0][1] == 1 and "某某衬衫男" in calls[0][0] and "抖店" in calls[0][0]
    assert "极限词" in calls[1][0] and "超过 60" in calls[1][0]
    ws = openpyxl.load_workbook(out["path"]).active
    rows = [[c.value for c in r] for r in ws.iter_rows(min_row=2)]
    assert [r[1] for r in rows] == ["长标题"] * 3 + ["短标题", "规格标题"] and rows[4][2] == "白色 L"
    assert "不会改店铺" in out["summary"] and "还要人改" not in out["summary"]


def test_titles_still_wrong_after_repair_are_flagged(tmp_path):
    _product(str(tmp_path), "ECK1", notes="衬衫", pics=())
    bad = dict(GOOD, short="史上最舒服的衬衫没有之一真的")
    out = pc.run("titles", str(tmp_path), ask=lambda p, i: json.dumps(bad, ensure_ascii=False))
    assert "还要人改" in out["summary"] and "极限词" in out["summary"]


def test_a_tall_detail_picture_is_read_screen_by_screen(tmp_path):
    _product(str(tmp_path), "竞品A", pics=((750, 750 * 13 // 10 * 3), (750, 600)))
    assert len(pc.pieces(os.path.join(str(tmp_path), "输入", "竞品A", "01.png"))) == 3
    seen = []

    def ask(prompt, images):
        seen.append(len(images))
        if images:
            return json.dumps({"screens": [{"no": 9, "role": "卖点", "text": "纯棉", "point": "舒服"}] * len(images)})
        assert "第4屏 [卖点] 纯棉" in prompt
        return json.dumps({"structure": "卖点→参数", "missing": ["尺码表"], "suggestions": ["第1屏加价格锚点"]},
                          ensure_ascii=False)
    out = pc.run("detail", str(tmp_path), ask=ask)
    assert seen == [4, 0] and "缺少：尺码表" in out["summary"] and "第1屏加价格锚点" in out["summary"]
    ws = openpyxl.load_workbook(out["path"])["逐屏"]
    assert [r[1].value for r in ws.iter_rows(min_row=2)] == [1, 2, 3, 4]


def test_empty_inbox_says_what_to_put_where(tmp_path):
    out = pc.run("detail", str(tmp_path))
    assert out["path"] == "" and "输入" in out["summary"] and "详情页的图片" in out["summary"]
