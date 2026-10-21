"""抖店 alpha 2026-10-21 09:26: 肽斯特 sent a product card + "这件衣服面料舒服吗";
the page renders them as ONE bubble, card first, while the turn's text has the
question first. The good answer ("这款是夏季速干面料…") was dropped as stale."""
from agent.ec_skills.browser_use_extension.hooks.external.feige_chat.hot_path import (
    _question_in_bubble, _question_part)

TURN = "这件衣服面料舒服吗 [商品卡片] 男童篮球服套装夏季新款中大童儿童速干运动服 商品ID:3806636856926404910 | 价格:￥55.90"
BUBBLE = ("[商品卡片] 现在付款，明天发货 ￥55.90 (券:立减10元) 现在付款，明天发货 "
          "(服务:7天无理由退货,运费险,极速退款,未发货极速退款)\n这件衣服面料舒服吗")


def test_the_question_is_found_in_the_card_plus_question_bubble():
    assert _question_part(TURN) == "这件衣服面料舒服吗"
    assert _question_in_bubble(TURN, BUBBLE)


def test_a_newer_different_question_is_still_stale():
    assert not _question_in_bubble(TURN, "[商品卡片] 现在付款，明天发货 ￥55.90\n尺码偏大还是偏小")


def test_a_card_alone_or_a_tiny_question_proves_nothing():
    assert not _question_in_bubble("[商品卡片] 男童篮球服套装 ￥55.90", BUBBLE)
    assert not _question_in_bubble("在吗", "在吗")          # under 4 characters: no text-only proof
