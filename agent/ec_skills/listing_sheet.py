"""商品上架 spreadsheet -> listing.json folders, for the 商品上架 skills.

A store owner fills one spreadsheet (one row per product, per SKU, per picture,
per size) and drops it with the pictures into the store's 上架 folder; each
product becomes ``<out>/<商品编码>/listing.json`` plus its files, which is what
the 上架 skills publish. Customers keep spreadsheets, not JSON.

Sheets (``write_template`` writes an empty one with instructions):
  商品   商品编码*  商品标题*  类目*  品牌  价格*  库存  属性  描述
  规格   商品编码*  <one column per spec: 颜色, 尺码, 适用机型 …>  价格  库存  规格编码
  图片   商品编码*  文件名*  用途*（主图/详情图/尺码表图/颜色图/视频）  颜色
  尺码表 商品编码*  尺码*  then any measurement columns (身高cm, 体重斤, 衣长cm …)
"""
from __future__ import annotations

import json
import os
import re
import shutil
from typing import Any

SHEETS = {
    "商品": ["商品编码", "商品标题", "类目", "品牌", "价格", "库存", "属性", "描述"],
    "规格": ["商品编码", "颜色", "尺码", "价格", "库存", "规格编码"],
    "图片": ["商品编码", "文件名", "用途", "颜色"],
    "尺码表": ["商品编码", "尺码", "身高cm", "体重斤", "衣长cm", "胸围cm"],
}
HELP = [
    ("商品编码", "必填。同一商品在各表里用同一个编码；也是这个商品的文件夹名。"),
    ("商品标题", "必填。按平台要求的标题原样填写。"),
    ("类目", "必填。从大到小用 / 分隔，例如：童装/婴儿装/亲子装/T恤。"),
    ("价格 / 库存", "商品表里填默认值；规格表里某个 SKU 的价格或库存不同才填。"),
    ("属性", "多条用分号分隔，每条“名称=值”，例如：面料=棉;领型=圆领;适用季节=夏季。"),
    ("规格", "每个 SKU 一行。颜色、尺码两列可以改名或增删：每种规格一列，列名就是平台上的规格名（例如 适用机型、款式）。价格、库存、规格编码三列名字不要改。"),
    ("图片", "文件名是和表格放在同一个文件夹里的图片/视频文件。用途：主图（按顺序，第一张是首图）、详情图、尺码表图、颜色图（同时填颜色）、视频。"),
    ("尺码表", "每个尺码一行；尺寸列可以增删（列名写清单位，如 身高cm、体重斤）。没有尺码表就不填，平台要求时会报告缺少。"),
]
_SKU_FIELDS = {"商品编码", "价格", "库存", "规格编码"}
ROLE = {"主图": "main", "详情图": "detail", "尺码表图": "size_chart", "颜色图": "color", "视频": "video"}


def write_template(path: str) -> str:
    import openpyxl
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, cols in SHEETS.items():
        wb.create_sheet(name).append(cols)
    ws = wb.create_sheet("填写说明")
    ws.append(["项目", "说明"])
    for row in HELP:
        ws.append(list(row))
    wb.save(path)
    return path


def _num(v: Any) -> Any:
    if v is None or str(v).strip() == "":
        return None
    try:
        f = float(str(v).strip())
        return int(f) if f.is_integer() else f
    except ValueError:
        return str(v).strip()


def _rows(wb, name: str) -> list[dict]:
    if name not in wb.sheetnames:
        return []
    it = wb[name].iter_rows(values_only=True)
    head = [str(h).strip() if h is not None else "" for h in next(it, [])]
    out = []
    for r in it:
        d = {h: (str(v).strip() if isinstance(v, str) else v) for h, v in zip(head, r) if h}
        if any(v not in (None, "") for v in d.values()):
            out.append(d)
    return out


def _attrs(text: Any) -> dict:
    out = {}
    for part in re.split(r"[;；\n]", str(text or "")):
        if "=" in part or "＝" in part:
            k, v = re.split(r"[=＝]", part, maxsplit=1)
            if k.strip():
                out[k.strip()] = v.strip()
    return out


def read_sheet(xlsx: str, media_dir: str = "") -> dict[str, dict]:
    """The listings in a 商品上架 spreadsheet, by 商品编码 (file names not resolved).
    A spreadsheet without our 商品 sheet is read loosely (``_read_loose``)."""
    import io
    import openpyxl
    # From bytes: openpyxl keeps a file it opened locked on Windows, and the
    # owner could not save or replace their spreadsheet while the app ran.
    with open(xlsx, "rb") as f:
        wb = openpyxl.load_workbook(io.BytesIO(f.read()), data_only=True)
    if "商品" not in wb.sheetnames:
        return _read_loose(wb, media_dir or os.path.dirname(os.path.abspath(xlsx)))
    out: dict[str, dict] = {}
    for r in _rows(wb, "商品"):
        code = str(r.get("商品编码") or "").strip()
        if not code:
            continue
        cat = [c.strip() for c in re.split(r"[/>／＞]", str(r.get("类目") or "")) if c.strip()]
        attrs = _attrs(r.get("属性"))
        if r.get("品牌"):
            attrs.setdefault("品牌", str(r["品牌"]))
        out[code] = {"code": code, "title": str(r.get("商品标题") or ""), "category": cat, "attributes": attrs,
                     "price": _num(r.get("价格")), "stock": _num(r.get("库存")),
                     "description": str(r.get("描述") or ""), "skus": [], "files": {}}
    for r in _rows(wb, "规格"):
        L = out.get(str(r.get("商品编码") or "").strip())
        if L is None:
            continue
        # Every other column is a spec (颜色, 尺码, 适用机型 ...): a phone case
        # varies by model, not by size.
        sku = {k: str(_num(v)) for k, v in r.items() if k not in _SKU_FIELDS and v not in (None, "")}
        sku["价格"] = _num(r.get("价格")) if r.get("价格") not in (None, "") else L["price"]
        sku["库存"] = _num(r.get("库存")) if r.get("库存") not in (None, "") else L["stock"]
        if r.get("规格编码"):
            sku["商家编码"] = str(r["规格编码"])
        L["skus"].append(sku)
    for r in _rows(wb, "图片"):
        L = out.get(str(r.get("商品编码") or "").strip())
        role = ROLE.get(str(r.get("用途") or "").strip())
        name = str(r.get("文件名") or "").strip()
        if L is None or not role or not name:
            continue
        if role == "color":
            L["files"].setdefault("color", {})[str(r.get("颜色") or "")] = name
        elif role in ("main", "detail"):
            L["files"].setdefault(role, []).append(name)
        else:
            L["files"][role] = name
    for r in _rows(wb, "尺码表"):
        L = out.get(str(r.get("商品编码") or "").strip())
        if L is None or r.get("尺码") in (None, ""):
            continue
        row = {k: str(_num(v)) for k, v in r.items() if k != "商品编码" and v not in (None, "")}
        chart = L.setdefault("size_chart", {"columns": [], "rows": []})
        for k in row:
            if k not in chart["columns"]:
                chart["columns"].append(k)
        chart["rows"].append(row)
    for L in out.values():
        specs: dict[str, list] = {}
        for sku in L["skus"]:
            for k, v in sku.items():
                if k not in ("价格", "库存", "商家编码") and v not in specs.setdefault(k, []):
                    specs[k].append(v)
        if specs:
            L["specs"] = specs
        for spec, key in (("颜色", "colors"), ("尺码", "sizes")):
            if specs.get(spec):
                L[key] = specs[spec]
    return out


# --- loose spreadsheets (e.g. 生意管家 商品批量发布: 货号 / 宝贝标题 / 当前类目 "男装>>衬衫" /
# 一口价 / 库存, one column per attribute, one row per SKU or a separate sku sheet, and the
# pictures in one folder per 货号 named 主图1, 详情图1, SKU_米色 ...)
ALIAS = {
    "code": ("货号", "商品编码", "款号", "商家编码", "商品货号", "商家货号"),
    "title": ("宝贝标题", "商品标题", "标题", "商品名称"),
    "category": ("当前类目", "类目", "商品类目"),
    "price": ("一口价", "价格", "售价", "销售价"),
    "stock": ("库存", "数量", "件数", "总库存", "库存数量"),
    "brand": ("品牌",),
    "description": ("描述", "宝贝描述", "商品描述"),
    "sku_code": ("sku编码", "规格编码", "sku货号", "sku商家编码"),
}
# Columns the fills can't set yet: kept in listing["ignored"] so nothing vanishes silently.
UNSUPPORTED = ("导购标题", "宝贝类型", "库存扣减方式", "库存类型", "上架时间", "发货时间", "发货地",
               "提取方式", "运费模板", "主图", "吊牌图", "透明图", "图文详情", "白底图")
SPEC_NAMES = ("颜色", "颜色分类", "尺码", "尺寸", "规格", "型号", "款式", "适用机型")
_MEASURE = re.compile(r"身高|体重|胸围|腰围|臀围|衣长|裤长|肩宽|脚长|头围")
_MEDIA = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".mp4", ".mov"}


def _clean(h: Any) -> str:
    return re.sub(r"[*＊\s]|[（(]必填[)）]", "", str(h or "")).lower()


def _field(header: str) -> str:
    h = _clean(header)
    return next((f for f, names in ALIAS.items() if h in names), "")


def _table(ws) -> list[dict]:
    """Rows of *ws* under the first of its top 5 rows that has a 货号-like column."""
    rows = list(ws.iter_rows(values_only=True))
    for i, r in enumerate(rows[:5]):
        head = [str(h).strip() if h is not None else "" for h in r]
        if any(_field(h) == "code" for h in head):
            out = []
            for r2 in rows[i + 1:]:
                d = {h: (v.strip() if isinstance(v, str) else v) for h, v in zip(head, r2) if h and v not in (None, "")}
                if d:
                    out.append(d)
            return out
    return []


def _get(row: dict, field: str) -> Any:
    return next((v for h, v in row.items() if _field(h) == field), None)


def _is_measure(h: str, v: Any) -> bool:
    return bool(_MEASURE.search(h)) and bool(re.search(r"\d", str(v)))


def _read_loose(wb, media_dir: str) -> dict[str, dict]:
    tables = [t for t in (_table(ws) for ws in wb.worksheets) if t]
    if not tables:
        return {}
    main, sku_rows = tables[0], [r for t in tables[1:] for r in t]
    groups: dict[str, list] = {}
    for r in main:
        code = str(_num(_get(r, "code")) or "").strip()
        if code:
            groups.setdefault(code, []).append(r)
    sku_groups: dict[str, list] = {}
    for r in sku_rows:
        code = str(_num(_get(r, "code")) or "").strip()
        if code in groups:
            sku_groups.setdefault(code, []).append(r)
    out = {}
    for code, rows in groups.items():
        first = rows[0]
        skus_from = sku_groups.get(code) or rows
        # Spec columns: the usual names, plus any column whose value differs between this product's SKU rows.
        cols = {h for r in skus_from for h in r if not _field(h) and not _is_measure(h, r[h])
                and _clean(h) not in UNSUPPORTED}
        specs_cols = [h for h in cols if _clean(h) in SPEC_NAMES
                      or len({str(r.get(h)) for r in skus_from}) > 1]
        specs_cols.sort(key=lambda h: [str(k) for k in skus_from[0]].index(h) if h in skus_from[0] else 99)
        cat = [c.strip() for c in re.split(r">>|[/>／＞]", str(_get(first, "category") or "")) if c.strip()]
        L = {"code": code, "title": str(_get(first, "title") or ""), "category": cat, "attributes": {},
             "price": _num(_get(first, "price")), "stock": _num(_get(first, "stock")),
             "description": str(_get(first, "description") or ""), "skus": [], "files": {}, "ignored": []}
        for h, v in first.items():
            if _clean(h) in UNSUPPORTED:
                L["ignored"].append(f"{h}={v}")
            elif not _field(h) and h not in specs_cols and not _is_measure(h, v):
                L["attributes"][h] = str(_num(v))
        if _get(first, "brand"):
            L["attributes"].setdefault("品牌", str(_get(first, "brand")))
        size_col = next((h for h in specs_cols if _clean(h) in ("尺码", "尺寸")), "")
        chart_rows: dict[str, dict] = {}
        for r in skus_from if specs_cols else []:
            sku = {h: str(_num(r[h])) for h in specs_cols if r.get(h) not in (None, "")}
            sku["价格"] = _num(_get(r, "price")) if _get(r, "price") not in (None, "") else L["price"]
            sku["库存"] = _num(_get(r, "stock")) if _get(r, "stock") not in (None, "") else L["stock"]
            if _get(r, "sku_code"):
                sku["商家编码"] = str(_get(r, "sku_code"))
            L["skus"].append(sku)
            measures = {h: str(_num(v)) for h, v in r.items() if _is_measure(h, v)}
            if size_col and measures and sku.get(size_col):
                chart_rows.setdefault(sku[size_col], {"尺码": sku[size_col], **measures})
        if chart_rows:
            columns = ["尺码"] + [k for k in next(iter(chart_rows.values())) if k != "尺码"]
            L["size_chart"] = {"columns": columns, "rows": list(chart_rows.values())}
        specs: dict[str, list] = {}
        for sku in L["skus"]:
            for k, v in sku.items():
                if k not in ("价格", "库存", "商家编码") and v not in specs.setdefault(k, []):
                    specs[k].append(v)
        if specs:
            L["specs"] = specs
            colors = next((specs[h] for h in specs if _clean(h) in ("颜色", "颜色分类")), None)
            if colors:
                L["colors"] = colors
            if size_col in specs:
                L["sizes"] = specs[size_col]
        _find_pictures(L, media_dir)
        if not L["ignored"]:
            del L["ignored"]
        out[code] = L
    return out


def _find_pictures(L: dict, media_dir: str) -> None:
    """Pictures in <media_dir>/<货号>/ by name: 主图1.. 详情图1.. SKU_<颜色> 尺码表 视频;
    others (吊牌, 白底, 透明, 3:4 主图) go to L["ignored"]."""
    sub = re.sub(r'[\\/:*?"<>|]', "-", L["code"])
    folder = os.path.join(media_dir, sub)
    if not os.path.isdir(folder):
        return
    colors = L.get("colors") or []
    main, detail = [], []
    for name in sorted(os.listdir(folder)):
        stem, ext = os.path.splitext(name)
        if ext.lower() not in _MEDIA:
            continue
        rel, s = f"{sub}/{name}", stem.strip()
        n = int((re.search(r"(\d+)\s*$", s) or [0, 0])[1] or 0)
        if ext.lower() in (".mp4", ".mov"):
            L["files"].setdefault("video", rel)
        elif re.match(r"^主图", s) and not re.search(r"3\s*[:：比x×]\s*4|竖", s):
            main.append((n, rel))
        elif re.match(r"^详情", s):
            detail.append((n, rel))
        elif s.startswith("尺码表"):
            L["files"]["size_chart"] = rel
        elif re.match(r"^sku", s, re.I):
            spec = re.sub(r"^sku[\s_\-]*", "", s, flags=re.I)
            color = next((c for c in colors if spec == c), "") or next((c for c in colors if spec.startswith(c)), "")
            if color and color not in L["files"].get("color", {}):
                L["files"].setdefault("color", {})[color] = rel
            elif not color:
                L["ignored"].append(f"图片 {name}")
        else:
            L["ignored"].append(f"图片 {name}")
    if main:
        L["files"]["main"] = [r for _, r in sorted(main)]
    if detail:
        L["files"]["detail"] = [r for _, r in sorted(detail)]


def problems(listing: dict, folder: str = "") -> list[str]:
    """What stops this listing from being published, in words for the store owner."""
    out = []
    for key, what in (("title", "商品标题"), ("category", "类目"), ("price", "价格")):
        if not listing.get(key):
            out.append(f"缺少{what}")
    if not (listing.get("files") or {}).get("main"):
        out.append("没有主图（图片表里用途填“主图”）")
    for s in listing.get("skus") or []:
        if s.get("价格") in (None, "") or s.get("库存") in (None, ""):
            name = " ".join(str(v) for k, v in s.items() if k not in ("价格", "库存", "商家编码"))
            out.append(f"规格 {name} 缺少价格或库存")
    if folder:
        for v in (listing.get("files") or {}).values():
            for name in (v.values() if isinstance(v, dict) else v if isinstance(v, list) else [v]):
                if name and not os.path.isfile(os.path.join(folder, name)):
                    out.append(f"找不到文件 {name}")
    return out


def convert(xlsx: str, out_root: str, media_dir: str = "") -> list[tuple[str, str, list[str]]]:
    """Write ``<out_root>/<商品编码>/listing.json`` (+ its files, copied from
    ``media_dir``, default: the spreadsheet's folder) for every product.
    Returns ``(code, folder, problems)``; a product with problems is still
    written, so the owner can see and fix it, but the skill skips it."""
    media_dir = media_dir or os.path.dirname(os.path.abspath(xlsx))
    done = []
    for code, L in read_sheet(xlsx, media_dir).items():
        folder = os.path.join(out_root, re.sub(r'[\\/:*?"<>|]', "-", code))
        os.makedirs(folder, exist_ok=True)
        for v in L["files"].values():
            for name in (v.values() if isinstance(v, dict) else v if isinstance(v, list) else [v]):
                src, dst = os.path.join(media_dir, name), os.path.join(folder, os.path.basename(name))
                if name and os.path.isfile(src) and not os.path.isfile(dst):
                    shutil.copyfile(src, dst)
        # Pictures found in a per-货号 subfolder ("A1/主图1.jpg") now sit in the product folder itself.
        for role, v in L["files"].items():
            if isinstance(v, dict):
                L["files"][role] = {k: os.path.basename(n) for k, n in v.items()}
            elif isinstance(v, list):
                L["files"][role] = [os.path.basename(n) for n in v]
            else:
                L["files"][role] = os.path.basename(v)
        found = problems(L, folder)
        if found:
            L["problems"] = found
        with open(os.path.join(folder, "listing.json"), "w", encoding="utf-8") as f:
            json.dump(L, f, ensure_ascii=False, indent=1)
        done.append((code, folder, found))
    return done
