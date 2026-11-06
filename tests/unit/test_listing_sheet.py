"""商品上架 spreadsheet -> listing.json: store owners fill a spreadsheet, the
上架 skills publish listing.json folders."""
import json
import os

import openpyxl

from agent.ec_skills import listing_sheet


def _sheet(tmp_path, with_main=True):
    p = str(tmp_path / "商品上架.xlsx")
    listing_sheet.write_template(p)
    wb = openpyxl.load_workbook(p)
    wb["商品"].append(["ECT2610B", "珊瑚绒睡衣套装 星月刺绣", "家居服/睡衣/家居服套装", "TONAR", 399, 5,
                     "面料=珊瑚绒；图案=星月\n适用季节=冬季", "加厚保暖"])
    for c, color in enumerate(["燕麦色", "雾霾蓝"], 1):
        for s in ["M", "L", "XL", "XXL"]:
            wb["规格"].append(["ECT2610B", color, s, None, 8 if s == "XXL" else None, f"ECT2610B-{c}{s}"])
    rows = [["ECT2610B", "main_1.png", "主图", None], ["ECT2610B", "detail_1.png", "详情图", None],
            ["ECT2610B", "blue.png", "颜色图", "雾霾蓝"], ["ECT2610B", "chart.png", "尺码表图", None]]
    for r in rows if with_main else rows[1:]:
        wb["图片"].append(r)
    wb["尺码表"].append(["ECT2610B", "M", "160-165", "100-115", 66, 108])
    wb["尺码表"].append(["ECT2610B", "L", "165-170", "115-130", 68, 112])
    wb.save(p)
    for name in ("main_1.png", "detail_1.png", "blue.png", "chart.png"):
        (tmp_path / name).write_bytes(b"x")
    return p


def test_template_has_the_sheets_and_instructions(tmp_path):
    wb = openpyxl.load_workbook(listing_sheet.write_template(str(tmp_path / "t.xlsx")))
    assert wb.sheetnames == ["商品", "规格", "图片", "尺码表", "填写说明"]


def test_a_product_becomes_a_listing_folder(tmp_path):
    out = tmp_path / "inbox"
    [(code, folder, found)] = listing_sheet.convert(_sheet(tmp_path), str(out))
    assert code == "ECT2610B" and found == []
    L = json.load(open(os.path.join(folder, "listing.json"), encoding="utf-8"))
    assert L["category"] == ["家居服", "睡衣", "家居服套装"]
    assert L["attributes"] == {"面料": "珊瑚绒", "图案": "星月", "适用季节": "冬季", "品牌": "TONAR"}
    assert L["colors"] == ["燕麦色", "雾霾蓝"] and L["sizes"] == ["M", "L", "XL", "XXL"]
    assert len(L["skus"]) == 8 and L["skus"][0] == {"颜色": "燕麦色", "尺码": "M", "价格": 399, "库存": 5,
                                                    "商家编码": "ECT2610B-1M"}
    assert L["skus"][3]["库存"] == 8
    assert L["files"] == {"main": ["main_1.png"], "detail": ["detail_1.png"], "color": {"雾霾蓝": "blue.png"},
                          "size_chart": "chart.png"}
    assert L["size_chart"]["columns"] == ["尺码", "身高cm", "体重斤", "衣长cm", "胸围cm"]
    assert L["size_chart"]["rows"][0] == {"尺码": "M", "身高cm": "160-165", "体重斤": "100-115",
                                          "衣长cm": "66", "胸围cm": "108"}
    assert all(os.path.isfile(os.path.join(folder, n)) for n in ("main_1.png", "blue.png", "chart.png"))


def test_problems_are_written_down_for_the_owner(tmp_path):
    [(_, folder, found)] = listing_sheet.convert(_sheet(tmp_path, with_main=False), str(tmp_path / "inbox"))
    assert any("主图" in p for p in found)
    assert json.load(open(os.path.join(folder, "listing.json"), encoding="utf-8"))["problems"] == found


def test_the_spreadsheet_is_not_left_locked(tmp_path):
    # The owner must be able to save or replace it while the app runs (Windows locks open files).
    import shutil
    p = str(tmp_path / "copy.xlsx")
    shutil.copyfile(_sheet(tmp_path), p)        # the helper's own openpyxl handle stays on the original
    listing_sheet.read_sheet(p)
    os.replace(p, p + ".moved")


def test_any_column_can_be_a_spec(tmp_path):
    # A phone case varies by model (适用机型) and design, not by size.
    p = str(tmp_path / "case.xlsx")
    listing_sheet.write_template(p)
    wb = openpyxl.load_workbook(p)
    ws = wb["规格"]
    ws.delete_rows(1)
    ws.append(["商品编码", "适用机型", "颜色", "价格", "库存", "规格编码"])
    wb["商品"].append(["CASE1", "手机壳", "手机配件/手机壳", None, 199, 10, "材质=TPU", None])
    for m in ["iPhone 16", "iPhone 16 Pro"]:
        for c in ["透明", "磨砂黑"]:
            ws.append(["CASE1", m, c, None, None, f"CASE1-{m[-3:]}-{c}"])
    wb["图片"].append(["CASE1", "m.png", "主图", None])
    wb.save(p)
    (tmp_path / "m.png").write_bytes(b"x")
    L = listing_sheet.read_sheet(p)["CASE1"]
    assert L["specs"] == {"适用机型": ["iPhone 16", "iPhone 16 Pro"], "颜色": ["透明", "磨砂黑"]}
    assert L["colors"] == ["透明", "磨砂黑"] and "sizes" not in L
    assert L["skus"][0] == {"适用机型": "iPhone 16", "颜色": "透明", "价格": 199, "库存": 10, "商家编码": "CASE1- 16-透明"}


def _pics(tmp_path, code, names):
    d = tmp_path / code
    d.mkdir()
    for n in names:
        (d / n).write_bytes(b"x")


def test_a_shengyi_guanjia_sheet_one_row_per_sku(tmp_path):
    # 生意管家 商品批量发布: a title row, starred headers, 当前类目 with >>, one column per
    # attribute, product columns repeated on every SKU row, pictures in a folder per 货号.
    p = str(tmp_path / "批量发布.xlsx")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["商品批量发布模板"])
    ws.append(["货号*", "宝贝标题", "当前类目", "导购标题", "一口价*", "颜色", "尺码", "库存*", "面料", "风格", "身高"])
    for color in ("米色", "黑色"):
        for size, h in (("S", "155-160"), ("M", "160-165")):
            ws.append(["A1", "男士衬衫 长袖", "男装>>衬衫", "好穿", 129, color, size, 5, "棉", "商务", h])
    wb.save(p)
    _pics(tmp_path, "A1", ["主图2.jpg", "主图1.jpg", "主图3比4.jpg", "详情图1.png", "SKU_黑色.jpg", "吊牌.jpg", "notes.txt"])
    out = tmp_path / "inbox"
    [(code, folder, found)] = listing_sheet.convert(p, str(out))
    L = json.load(open(os.path.join(folder, "listing.json"), encoding="utf-8"))
    assert (code, found, L["title"], L["category"], L["price"]) == ("A1", [], "男士衬衫 长袖", ["男装", "衬衫"], 129)
    assert L["attributes"] == {"面料": "棉", "风格": "商务"}
    assert L["colors"] == ["米色", "黑色"] and L["sizes"] == ["S", "M"] and len(L["skus"]) == 4
    assert L["skus"][0] == {"颜色": "米色", "尺码": "S", "价格": 129, "库存": 5}
    assert L["size_chart"] == {"columns": ["尺码", "身高"], "rows": [{"尺码": "S", "身高": "155-160"},
                                                                    {"尺码": "M", "身高": "160-165"}]}
    assert L["files"] == {"main": ["主图1.jpg", "主图2.jpg"], "detail": ["详情图1.png"], "color": {"黑色": "SKU_黑色.jpg"}}
    assert L["ignored"] == ["导购标题=好穿", "图片 主图3比4.jpg", "图片 吊牌.jpg"]
    assert all(os.path.isfile(os.path.join(folder, n)) for n in ("主图1.jpg", "SKU_黑色.jpg"))


def test_a_shengyi_guanjia_sheet_with_a_separate_sku_sheet(tmp_path):
    p = str(tmp_path / "批量发布.xlsx")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["商品编码", "宝贝标题", "类目", "价格", "总库存", "材质成分"])
    ws.append(["B2", "连衣裙", "女装/连衣裙", 199, 20, "聚酯纤维100%"])
    sku = wb.create_sheet("sku")
    sku.append(["货号", "颜色", "尺码", "价格", "数量"])
    sku.append(["B2", "红色", "S", 199, 10])
    sku.append(["B2", "红色", "M", 209, 10])
    wb.save(p)
    L = listing_sheet.read_sheet(p)["B2"]
    assert L["attributes"] == {"材质成分": "聚酯纤维100%"} and L["stock"] == 20
    assert L["skus"] == [{"颜色": "红色", "尺码": "S", "价格": 199, "库存": 10},
                         {"颜色": "红色", "尺码": "M", "价格": 209, "库存": 10}]
    assert listing_sheet.problems(L) == ["没有主图（图片表里用途填“主图”）"]
