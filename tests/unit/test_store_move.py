import os

import openpyxl

from agent.ec_skills import listing_sheet
from agent.ec_skills import store_move as sm

P = {"source_id": "38521", "title": "儿童运动套装 ECAN测试款", "category": "服装/童装/运动套装", "attrs": {"品牌": "无", "面料": "棉100%"},
     "main": ["https://x/a.png", "https://x/b.png"], "main34": [], "detail": ["https://x/d1.png"], "colour": {"樱花粉": "https://x/c.png"},
     "skus": [{"spec": {"颜色分类": "樱花粉", "尺码大小": "110cm"}, "price": 229.0, "stock": 10, "code": "ECK-11"},
              {"spec": {"颜色分类": "樱花粉", "尺码大小": "120cm"}, "price": 239.0, "stock": 5, "code": "ECK-12"}],
     "code": "ECK3102"}


def fake_download(url, path):
    open(path + ".png", "wb").write(b"png")
    return path + ".png"


def test_products_become_a_listing_sheet_the_listing_skill_reads(tmp_path):
    out = sm.run("douyin", "douyin-x", str(tmp_path), {"target_platform": "pdd"}, products=[dict(P)], download=fake_download)
    assert out["products"] == 1 and out["pictures"] == 4 and "还没有发布" in out["summary"]
    assert "类目「服装/童装/运动套装」是来源平台的" in out["summary"] and "主图只有 2 张" in out["summary"]
    wb = openpyxl.load_workbook(out["path"])
    goods = list(wb["商品"].iter_rows(values_only=True))
    assert goods[1][:6] == ("ECK3102", "儿童运动套装 ECAN测试款", "服装/童装/运动套装", "无", 229.0, 15) and goods[1][6] == "面料=棉100%"
    skus = list(wb["规格"].iter_rows(values_only=True))
    assert skus[0] == ("商品编码", "颜色分类", "尺码大小", "价格", "库存", "规格编码") and skus[2][2] == "120cm"
    pics = {r[1]: (r[2], r[3]) for r in list(wb["图片"].iter_rows(values_only=True))[1:]}
    assert pics["ECK3102_颜色图4.png"] == ("颜色图", "樱花粉") and pics["ECK3102_主图1.png"] == ("主图", None)
    # the listing skill's own reader takes it
    done = listing_sheet.convert(out["path"], str(tmp_path / "inbox"))
    code, folder, problems = done[0]
    assert code == "ECK3102" and os.path.isfile(os.path.join(folder, "listing.json")) and not problems


def test_nothing_read_says_so(tmp_path):
    assert "没有从" in sm.run("pdd", "p", str(tmp_path), products=[])["summary"]
