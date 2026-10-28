"""Size charts are not only clothing: a shoe chart (鞋码/脚长) or a hat chart
(规格/头围) in a product document is the product's size chart, and a size
question about them is a size question (2026-10-28 self-test: both were missed)."""
from knowledge.ks.doc_extract import _is_size_table
from knowledge.ks.text import attribute_family


def _rows(head, *rows):
    return [list(head)] + [list(r) for r in rows]


def test_clothing_shoe_and_hat_charts_are_size_charts():
    assert _is_size_table(_rows(["尺码", "身高(cm)", "胸围(cm)"], ["120", "110-120", "68"]))
    assert _is_size_table(_rows(["鞋码", "脚长(cm)", "脚宽(cm)"], ["39", "24.5", "9.2"]))
    assert _is_size_table(_rows(["规格", "头围(cm)", "帽深(cm)"], ["L", "56-58", "12"]))


def test_a_price_table_is_not_a_size_chart():
    assert not _is_size_table(_rows(["颜色", "价格", "库存"], ["红", "99", "10"]))
    assert not _is_size_table(_rows(["规格", "价格", "库存"], ["红色", "99", "10"]))


def test_shoe_and_hat_questions_are_size_questions():
    for q in ("脚长24.5穿几码", "平时穿39这款要大一码吗", "头围57戴哪个", "我头大能戴吗"):
        assert attribute_family(q) == "size", q
