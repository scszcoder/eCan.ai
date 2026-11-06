"""抖店 商品质量分: the platform's own quality score and what it says is missing, per live product. Read only.

GET fxg /product/tproduct/list?page&pageSize&status=0&check_status=3 (在售, 审核通过) in a background
fxg tab (the page signs its own requests). Per product (KEN 11-05): quality_score (0-100),
quality_level (lv1-lv3), base_score (基础分), product_material_miss_cnt {miss_pic_11_cnt,
miss_pic_34_cnt, miss_main_video_cnt, miss_white_bg_cnt}, punish_ticket.has_punish_ticket,
exist_category_misplaced + recommend_category, audit_reject_suggestion.
"""
from __future__ import annotations

import asyncio
import json
import threading
from typing import Any, Dict, List

LIST_PAGE = "https://fxg.jinritemai.com/ffa/g/list"
LOW = 80
_JS = r"""(async (query) => {
  const rows = [], errors = [];
  for (let page = 0; page < 20; page++) {
    let j;
    try {
      j = await (await fetch('/product/tproduct/list?pageSize=50' + query + '&page=' + page, {credentials: 'include'})).json();
    } catch (e) { errors.push(String(e)); break; }
    if (j.code !== 0) { errors.push((j.code || '') + ' ' + (j.msg || '')); break; }
    const items = Array.isArray(j.data) ? j.data : [];
    for (const p of items) rows.push({product_id: String(p.product_id), title: p.name || '', score: p.quality_score,
      has_score: !!p.has_quality_score, level: p.quality_level || '', base: p.has_base_score ? p.base_score : null,
      miss: p.product_material_miss_cnt || {}, punished: !!((p.punish_ticket || {}).has_punish_ticket),
      misplaced: !!p.exist_category_misplaced, recommend: JSON.stringify(p.recommend_category || '').slice(0, 80),
      category: p.category_name || '', status: p.status, check_status: p.check_status});
    if (items.length < 50 || rows.length >= Number(j.total || 0)) break;
  }
  return JSON.stringify({rows, errors});
})(%s)"""
ONLINE = "&status=0&check_status=3"
MISS = {"miss_white_bg_cnt": "白底图", "miss_pic_34_cnt": "3:4主图", "miss_pic_11_cnt": "1:1主图", "miss_main_video_cnt": "主图视频"}


def rows_of(raw: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for p in raw:
        miss = {MISS[k]: int(v or 0) for k, v in (p.get("miss") or {}).items() if k in MISS and v}
        todo = []
        if p.get("punished"):
            todo.append("有处罚单，先去处理")
        if p.get("misplaced"):
            todo.append("类目可能放错了")
        if "白底图" in miss:
            todo.append("加白底图（图片小工具·白底图）")
        if "3:4主图" in miss:
            todo.append(f"补 {miss['3:4主图']} 张 3:4 主图（图片小工具·改尺寸）")
        if "1:1主图" in miss:
            todo.append(f"补 {miss['1:1主图']} 张 1:1 主图")
        if "主图视频" in miss:
            todo.append("加主图视频")
        score = p.get("score") if p.get("has_score") else None
        out.append({"商品ID": p["product_id"], "商品": str(p.get("title") or "")[:60], "质量分": "" if score is None else score,
                    "等级": p.get("level", ""), "基础分": "" if p.get("base") is None else p["base"],
                    "缺的素材": "、".join(f"{k}{v}张" if k != "白底图" and k != "主图视频" else k for k, v in miss.items()),
                    "要做的": "；".join(todo), "类目": p.get("category", "")})
    out.sort(key=lambda r: (r["质量分"] if isinstance(r["质量分"], (int, float)) else 101))
    return out


def summary(rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return "质量分：没有读到在售商品。"
    scored = [r["质量分"] for r in rows if isinstance(r["质量分"], (int, float))]
    low = [r for r in rows if isinstance(r["质量分"], (int, float)) and r["质量分"] < LOW]
    text = (f"质量分：{len(rows)} 个在售商品，平均 {sum(scored) / len(scored):.0f} 分" if scored else
            f"质量分：{len(rows)} 个在售商品，平台没给分")
    text += f"，低于 {LOW} 分的 {len(low)} 个。"
    from collections import Counter
    c = Counter(k for r in rows for k in MISS.values() if k in r["缺的素材"])
    if c:
        text += "缺素材：" + "，".join(f"{k} {v} 个商品" for k, v in c.most_common()) + "。"
    for r in [r for r in rows if r["要做的"]][:4]:
        text += f"\n- {r['商品'][:18]}（{r['质量分']}分）：{r['要做的']}"
    return text


async def _read(store_id: str, query: str = ONLINE) -> Dict[str, Any]:
    from agent.ec_skills.browser_use_extension import store_page
    tabs = [t for t in store_page.store_tabs("douyin") if not store_id or t.get("store_id") == store_id]
    if not tabs:
        raise RuntimeError("没有打开这个店铺的后台页（店铺浏览器没启动或没登录）")
    return await store_page.evaluate_in_background_tab(tabs[0]["ws"], LIST_PAGE, _JS % json.dumps(query), timeout=120.0)


def _raw(store_id: str, query: str, timeout_s: float) -> Dict[str, Any]:
    box: Dict[str, Any] = {}

    def run():
        try:
            box["out"] = asyncio.run(_read(store_id, query))
        except Exception as exc:
            box["error"] = f"{type(exc).__name__}: {exc}"
    t = threading.Thread(target=run, name="store-quality", daemon=True)
    t.start()
    t.join(timeout_s)
    if "out" not in box:
        raise RuntimeError(box.get("error") or "timed out")
    return box["out"] if isinstance(box["out"], dict) else json.loads(box["out"] or "{}")


def read_quality(store_id: str = "", timeout_s: float = 150.0) -> Dict[str, Any]:
    """{"rows": [...], "errors": [...]} for a 抖店 store's live products, from any thread."""
    raw = _raw(store_id, ONLINE, timeout_s)
    return {"rows": rows_of(raw.get("rows") or []), "errors": raw.get("errors") or []}


def status_of(p: Dict[str, Any]) -> str:
    if p.get("status") == 0 and p.get("check_status") == 3:
        return "在售"
    if p.get("status") == 1:
        return "已下架"
    return "审核中或其他"


def read_status(store_id: str = "", timeout_s: float = 150.0) -> Dict[str, Dict[str, Any]]:
    """{product_id: {title, status: 在售|已下架|审核中或其他}} of every product of a 抖店 store."""
    raw = _raw(store_id, "", timeout_s)
    return {p["product_id"]: {"title": p.get("title", ""), "status": status_of(p)} for p in raw.get("rows") or []}
