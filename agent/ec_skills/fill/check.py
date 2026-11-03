"""Compare what a form (or a published product) holds with listing.json.

*seen* has the read-back shape the listing skills use::

    {"title", "category", "attributes": {label: text}, "pictures": {"main", "detail", "color": []},
     "skus": [{"商家编码", "价格", "库存", "颜色", "尺码", ...}]}

Only what *seen* carries is checked; an attribute the platform does not have is
not a mismatch (the fill reports it as a data note).
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

SAME_SIZE = {"xxl": "2xl", "xxxl": "3xl", "xxxxl": "4xl", "2xl": "xxl", "3xl": "xxxl", "4xl": "xxxxl"}


def _norm(v: Any) -> str:
    return re.sub(r"\s+", "", str(v if v is not None else ""))


def _num(v: Any):
    m = re.search(r"-?\d+(\.\d+)?", str(v if v is not None else ""))
    return float(m.group(0)) if m else None


def compare(listing: Dict[str, Any], seen: Dict[str, Any]) -> Dict[str, Any]:
    """{"ok", "mismatches", "checked"}."""
    bad: List[str] = []
    checked: List[str] = []
    if not isinstance(seen, dict) or not seen:
        return {"ok": False, "mismatches": ["nothing was read back"], "checked": []}
    if seen.get("title") is not None:
        checked.append("标题")
        if _norm(seen["title"]) != _norm(listing.get("title")):
            bad.append(f"标题：表单「{seen['title']}」，资料「{listing.get('title')}」")
    skus = [x for x in seen.get("skus") or [] if isinstance(x, dict)]
    want = [k for k in listing.get("skus") or [] if isinstance(k, dict)]
    if want and "skus" in seen:
        if len(skus) != len(want):
            bad.append(f"规格数：表单 {len(skus)} 个，资料 {len(want)} 个")
        by_code = {_norm(x.get("商家编码")): x for x in skus if x.get("商家编码")}
        for sku in want:
            code = _norm(sku.get("商家编码"))
            if not code:
                continue
            got = by_code.get(code)
            if got is None:
                bad.append(f"表单里没有规格编码 {sku.get('商家编码')}")
                continue
            checked.append(str(sku.get("商家编码")))
            for k in ("颜色", "尺码"):
                if not (sku.get(k) and got.get(k)):
                    continue
                mine = _norm(sku[k]).lower()
                names = {mine, SAME_SIZE.get(mine, mine)} if k == "尺码" else {mine}
                if not any(n in _norm(got[k]).lower() for n in names):
                    bad.append(f"{sku['商家编码']} 的{k}：表单「{got[k]}」，资料「{sku[k]}」")
            for k in ("价格", "库存"):
                a, b = _num(sku.get(k)), _num(got.get(k))
                if a is not None and b is not None and abs(a - b) > 0.001:
                    bad.append(f"{sku['商家编码']} 的{k}：表单 {got.get(k)}，资料 {sku.get(k)}")
    if seen.get("category") and listing.get("category"):
        cat = listing["category"]
        leaf = re.sub(r"[及与和/、\s]", "", str(cat[-1] if isinstance(cat, list) else cat))
        checked.append("类目")
        if leaf and not any(ch in _norm(seen["category"]) for ch in leaf if ord(ch) > 0x3000 and ch not in "类品其他"):
            bad.append(f"类目：表单「{seen['category']}」，资料「{cat}」")
    shown = seen.get("attributes") if isinstance(seen.get("attributes"), dict) else {}
    for k, v in (listing.get("attributes") or {}).items():
        got = next((gv for gk, gv in shown.items() if _norm(k) in _norm(gk) or _norm(gk) in _norm(k)), None)
        if got is None:
            continue
        checked.append(k)
        parts = [p for p in re.split(r"[+＋;；、,，/／\s]+", str(v or "")) if p]
        missing = [p for p in parts if _norm(p) not in _norm(got) and _norm(got) not in _norm(p)]
        if missing:
            bad.append(f"属性 {k}：表单「{got}」，资料「{v}」")
    pics = seen.get("pictures") if isinstance(seen.get("pictures"), dict) else None
    files = listing.get("files") or {}
    if pics is not None:
        want_main = len(files.get("main") or [])
        want_detail = len(files.get("detail") or []) + (1 if files.get("size_chart") else 0)
        if want_main:
            checked.append("主图")
            if int(pics.get("main") or 0) != want_main:
                bad.append(f"主图：表单 {pics.get('main')} 张，资料 {want_main} 张")
        if want_detail:
            checked.append("详情图")
            if int(pics.get("detail") or 0) < want_detail:
                bad.append(f"详情图：表单 {pics.get('detail')} 张，资料 {want_detail} 张")
    return {"ok": bool(checked) and not bad, "mismatches": bad[:30], "checked": checked}
