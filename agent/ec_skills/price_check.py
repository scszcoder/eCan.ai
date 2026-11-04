"""价格核验: the merchant's own price table against the store's live SKU prices.

The merchant keeps a price table (any .xlsx/.csv: one row per product or per SKU,
with a code and the price it should sell at, optionally a floor price). Each
store SKU is matched to a row -- by SKU code (商家编码), else by product code /
商品ID plus the SKU's spec values, else by the product alone -- and checked:

  标价       the SKU's price on the store
  券后价     标价 minus the best coupon one item can use (store or this product's
             coupons whose threshold the price reaches)
  偏差       券后价 against the table's price; outside the tolerance (default ±10%)
             is 偏高 / 偏低, under the floor is 低于底价 (the loss-prevention case)

Read only: nothing here changes the store. Platform readers supply the SKUs and
coupons (see ``store_images``); the result goes to an Excel file and a summary.
"""
from __future__ import annotations

import csv
import io
import os
import re
from typing import Any, Dict, Iterable, List, Optional

# Header words, loosely matched (a merchant's own sheet): the first column whose
# header contains one of these words, in this order of preference.
HEADERS = {
    "sku_code": ["规格编码", "SKU编码", "sku编码", "商家编码", "外部编码", "条码"],
    "code": ["货号", "款号", "商品编码", "商品编号", "型号"],
    "product_id": ["商品ID", "商品id", "宝贝ID", "宝贝id", "产品ID"],
    "spec": ["规格", "SKU", "sku", "销售属性"],
    "title": ["商品名称", "商品标题", "宝贝标题", "标题", "名称"],
    "floor": ["底价", "最低价", "红线价", "控价", "保底价"],
    "target": ["目标价", "标准价", "指导价", "建议价", "零售价", "售价", "一口价", "价格"],
}
TOLERANCE = 0.10


def _norm(s: Any) -> str:
    return re.sub(r"\s+", "", str(s if s is not None else "")).lower()


def _num(v: Any) -> Optional[float]:
    if v is None or str(v).strip() == "":
        return None
    try:
        return float(str(v).replace("¥", "").replace("￥", "").replace(",", "").replace("元", "").strip())
    except ValueError:
        return None


def _columns(head: List[str]) -> Dict[str, int]:
    """field -> column index; each column is used once, more specific fields first."""
    out: Dict[str, int] = {}
    used = set()
    for field, words in HEADERS.items():
        for w in words:
            hit = next((i for i, h in enumerate(head) if i not in used and w.lower() in h.lower()), None)
            if hit is not None:
                out[field] = hit
                used.add(hit)
                break
    return out


def _sheets(path: str) -> Iterable[List[List[Any]]]:
    if path.lower().endswith(".csv"):
        raw = open(path, "rb").read()
        for enc in ("utf-8-sig", "gb18030"):
            try:
                yield list(csv.reader(io.StringIO(raw.decode(enc))))
                return
            except UnicodeDecodeError:
                continue
        return
    import openpyxl
    with open(path, "rb") as f:                     # from bytes: no lock on the owner's file
        wb = openpyxl.load_workbook(io.BytesIO(f.read()), data_only=True, read_only=True)
    for ws in wb.worksheets:
        yield [list(r) for r in ws.iter_rows(values_only=True)]


def read_table(path: str) -> List[Dict[str, Any]]:
    """The price table's rows: {sku_code, code, product_id, spec, title, target, floor}.
    The header row is the first of the first 10 rows that names a code and a price."""
    rows: List[Dict[str, Any]] = []
    for grid in _sheets(path):
        for h, head in enumerate(grid[:10]):
            cols = _columns([str(x or "").strip() for x in head])
            if ({"sku_code", "code", "product_id"} & set(cols)) and ({"target", "floor"} & set(cols)):
                break
        else:
            continue
        for r in grid[h + 1:]:
            get = lambda f: r[cols[f]] if f in cols and cols[f] < len(r) else None
            row = {f: str(get(f)).strip() for f in ("sku_code", "code", "product_id", "spec", "title")
                   if get(f) not in (None, "")}
            row["target"], row["floor"] = _num(get("target")), _num(get("floor"))
            if (row.get("sku_code") or row.get("code") or row.get("product_id")) and \
                    (row["target"] is not None or row["floor"] is not None):
                rows.append(row)
    return rows


def best_coupon(price: float, product_id: str, coupons: List[Dict[str, Any]]) -> float:
    """The largest amount one item at *price* can take off: store coupons and this
    product's coupons whose threshold it reaches (coupons do not stack here)."""
    best = 0.0
    for c in coupons:
        if c.get("product_id") and str(c["product_id"]) != str(product_id):
            continue
        if price >= float(c.get("threshold") or 0):
            best = max(best, float(c.get("amount") or 0))
    return min(best, price)


def _spec_match(row_spec: str, sku_spec: Dict[str, str]) -> bool:
    want = [_norm(p) for p in re.split(r"[/;；,，\s]+", str(row_spec)) if p.strip()]
    have = [_norm(v) for v in sku_spec.values()]
    return bool(want) and all(any(w == h for h in have) for w in want)


def match(row: Dict[str, Any], skus: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The store SKUs one price-table row covers."""
    if row.get("sku_code"):
        hit = [s for s in skus if _norm(s.get("sku_code")) == _norm(row["sku_code"])]
        if hit:
            return hit
    keys = {_norm(row.get(k)) for k in ("code", "product_id", "sku_code") if row.get(k)}
    prod = [s for s in skus if _norm(s.get("product_id")) in keys or _norm(s.get("code")) in keys]
    if row.get("spec"):
        return [s for s in prod if _spec_match(row["spec"], s.get("spec") or {})]
    return prod


def check(table: List[Dict[str, Any]], skus: List[Dict[str, Any]], coupons: List[Dict[str, Any]],
          tolerance: float = TOLERANCE) -> List[Dict[str, Any]]:
    """One result per (table row, matched SKU), plus rows that matched nothing.
    A SKU covered by a SKU-level row is not checked again by its product's row."""
    out: List[Dict[str, Any]] = []
    done = set()
    ordered = sorted(table, key=lambda r: 0 if (r.get("sku_code") or r.get("spec")) else 1)
    for row in ordered:
        hits = [s for s in match(row, skus) if id(s) not in done]
        if not hits:
            if not match(row, skus):
                out.append({**_row_keys(row), "结果": "店铺里没找到"})
            continue
        for s in hits:
            done.add(id(s))
            price = float(s.get("price") or 0)
            after = round(price - best_coupon(price, s.get("product_id", ""), coupons), 2)
            res = {**_row_keys(row), "商品ID": s.get("product_id", ""), "店铺商品": s.get("title", ""),
                   "店铺规格": "/".join(str(v) for v in (s.get("spec") or {}).values()),
                   "SKU编码": s.get("sku_code", ""), "标价": price, "券后价": after,
                   "表格价": row.get("target"), "底价": row.get("floor")}
            flags = []
            if row.get("floor") is not None and after < row["floor"]:
                flags.append("低于底价")
            if row.get("target"):
                gap = (after - row["target"]) / row["target"]
                res["偏差"] = f"{gap:+.1%}"
                if gap > tolerance:
                    flags.append("偏高")
                elif gap < -tolerance:
                    flags.append("偏低")
            res["结果"] = "、".join(flags) or "正常"
            out.append(res)
    return out


def _row_keys(row: Dict[str, Any]) -> Dict[str, Any]:
    return {"表格编码": row.get("sku_code") or row.get("code") or row.get("product_id") or "",
            "表格规格": row.get("spec", ""), "表格商品": row.get("title", "")}


COLUMNS = ["结果", "表格编码", "表格商品", "表格规格", "商品ID", "店铺商品", "店铺规格", "SKU编码",
           "标价", "券后价", "表格价", "偏差", "底价"]


def summary(results: List[Dict[str, Any]], store: str = "") -> str:
    """A few lines for the merchant: counts, then the SKUs that need a look."""
    bad = [r for r in results if r["结果"] != "正常"]
    lines = [f"{store}价格核验：核对 {len(results)} 条，正常 {len(results) - len(bad)} 条，需要看的 {len(bad)} 条。"]
    order = {"低于底价": 0, "偏低": 1, "偏高": 2}
    for r in sorted(bad, key=lambda r: min([order.get(f, 3) for f in r["结果"].split("、")]))[:20]:
        what = r.get("店铺商品") or r.get("表格商品") or r["表格编码"]
        spec = f"（{r['店铺规格']}）" if r.get("店铺规格") else ""
        if "券后价" in r:
            lines.append(f"- {r['结果']}：{what}{spec} 券后 {r['券后价']:g} 元，表格 {r.get('表格价') or '-'}，底价 {r.get('底价') or '-'}")
        else:
            lines.append(f"- {r['结果']}：表格里的 {r['表格编码']} {r.get('表格商品', '')}")
    if len(bad) > 20:
        lines.append(f"……其余 {len(bad) - 20} 条见表格。")
    return "\n".join(lines)


def write_xlsx(results: List[Dict[str, Any]], path: str) -> str:
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "价格核验"
    ws.append(COLUMNS)
    for r in results:
        ws.append([r.get(c, "") if r.get(c) is not None else "" for c in COLUMNS])
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    wb.save(path)
    return path


def run_for_store(store_id: str, platform: str, folder: str, tolerance: float = TOLERANCE) -> Dict[str, Any]:
    """The newest price table in *folder* against *store_id*'s live SKUs; the result
    Excel goes to ``<folder>/结果/价格核验_<time>.xlsx``. {summary, path, counts}; no
    table yet = a summary saying so; raises (words for the merchant) when the table
    or the store cannot be read."""
    import time
    from agent.ec_skills.store_prices import read_store_skus
    tables = sorted((os.path.join(folder, n) for n in (os.listdir(folder) if os.path.isdir(folder) else [])
                     if n.lower().endswith((".xlsx", ".csv")) and not n.startswith("~$")),
                    key=os.path.getmtime)
    if not tables:
        # the daily run on a store whose merchant has not given a table yet: nothing to check
        return {"summary": f"价格核验：还没有价格表。把价格表（.xlsx 或 .csv，含 编码 和 价格 两列）放进 {folder}",
                "path": "", "table": "", "skus": 0, "counts": {}}
    table = read_table(tables[-1])
    if not table:
        raise RuntimeError(f"价格核验：{os.path.basename(tables[-1])} 里没找到 编码 和 价格 两列（如 货号/商家编码 + 售价/控价）")
    skus, coupons = read_store_skus(platform, store_id=store_id)
    skus = [s for s in skus if not store_id or s.get("store_id") == store_id]
    if not skus:
        raise RuntimeError("价格核验：没有读到店铺商品（店铺客服聊天页没有打开，或未登录）")
    coupons = [c for c in coupons if not store_id or c.get("store_id") == store_id]
    results = check(table, skus, coupons, tolerance)
    path = write_xlsx(results, os.path.join(folder, "结果", time.strftime("价格核验_%Y%m%d_%H%M.xlsx")))
    counts: Dict[str, int] = {}
    for r in results:
        for f in r["结果"].split("、"):
            counts[f] = counts.get(f, 0) + 1
    return {"summary": summary(results), "path": path, "table": os.path.basename(tables[-1]),
            "skus": len(skus), "counts": counts}
