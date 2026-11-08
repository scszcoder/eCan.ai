"""店铺间搬家: the merchant's own products read from one of their stores and written as a
商品上架 spreadsheet (listing_sheet format) with the pictures, for another store. Read only:
nothing is published here. The person checks the sheet (类目 above all: every platform has
its own category tree), then puts it in the target store's 上架 folder and runs 商品上架.

Sources (KEN 11-05):
  抖店   POST fxg /product/tproduct/getSchema {context: {product_id}} in a background fxg tab:
         title, pic (主图), main_image_three_to_four, description (详情 HTML -> pictures),
         goods_category (类目 path), category_properties (属性; names from .items[].label),
         spec_detail (规格 names, colour pictures), sku_detail (price yuan, self_sell_stock, code).
         Which products: the ones given, else 在售 from /product/tproduct/list.
  拼多多 chat-page APIs (uid "0"): getMallChatGoodsList (在售 ids), skuSelectorForMall: goodsName,
         goodsDesc, hdUrl (one main picture), sku[].thumbUrl (colour pictures), specs, normalPrice
         (单买价, fen), quantity, outSkuSn / outGoodsSn. No gallery, detail pictures, attributes or
         category name there: the summary says what to add.
  淘宝   not yet.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import re
import threading
from typing import Any, Dict, List, Optional

from utils.logger_helper import logger_helper as logger

LIST_PAGE = "https://fxg.jinritemai.com/ffa/g/list"
MAX_PRODUCTS = 5
_DOUYIN_JS = r"""(async (ids, max) => {
  const out = [], errors = [];
  if (!ids.length) {
    const j = await (await fetch('/product/tproduct/list?page=0&pageSize=' + max + '&status=0&check_status=3', {credentials: 'include'})).json();
    ids = (Array.isArray(j.data) ? j.data : []).map(p => String(p.product_id)).slice(0, max);
  }
  for (const id of ids) {
    try {
      const s = await (await fetch('/product/tproduct/getSchema?appid=1', {method: 'POST', credentials: 'include',
        headers: {'content-type': 'application/json'}, body: JSON.stringify({context: {product_id: id}})})).json();
      const m = (s.data || {}).model || {};
      if (s.code !== 0 || !m.title) { errors.push(id + ' ' + (s.msg || s.code)); continue; }
      const v = k => (m[k] || {}).value;
      const gc = v('goods_category') || {};
      const cats = [gc.first_cname, gc.second_cname, gc.third_cname, gc.fourth_cname].filter(Boolean);
      const cp = m.category_properties || {}, names = {};
      for (const it of cp.items || []) names[String(it.id)] = it.label || it.name || String(it.id);
      const attrs = {};
      for (const [k, vals] of Object.entries(cp.value || {})) {
        const t = (vals || []).map(x => x.value_name).filter(Boolean).join('/');
        if (t) attrs[names[k] || k] = t;
      }
      const specs = v('spec_detail') || [], valname = {}, colour = {};
      for (const g of specs) for (const sv of g.spec_values || []) { valname[String(sv.id)] = [g.name, sv.name]; if (sv.img_url) colour[sv.name] = sv.img_url; }
      const skus = (v('sku_detail') || []).map(k => {
        const spec = {};
        for (const i of k.spec_detail_ids || []) { const nv = valname[String(i)]; if (nv) spec[nv[0]] = nv[1]; }
        return {spec, price: Number(k.price), stock: Number(k.self_sell_stock ?? (k.stock_info || {}).stock_num ?? 0), code: String(k.code || '')};
      });
      const html = String(v('description') || '');
      out.push({source_id: id, title: String(v('title') || ''), category: cats.join('/'), attrs,
        main: (v('pic') || []).map(p => p.url).filter(Boolean), main34: (v('main_image_three_to_four') || []).map(p => p.url || p).filter(Boolean),
        detail: [...html.matchAll(/<img[^>]+src="([^"]+)"/g)].map(x => x[1]), colour, skus,
        code: String(v('outer_product_id') || v('product_code') || '')});
    } catch (e) { errors.push(id + ' ' + e); }
  }
  return JSON.stringify({products: out, errors});
})(%s, %d)"""
_PDD_JS = r"""(async (ids, max) => {
  const post = async (u, b) => (await fetch(u, {method: 'POST', credentials: 'include',
    headers: {'Content-Type': 'application/json'}, body: JSON.stringify(b)})).json();
  const out = [], errors = [];
  if (!ids.length) {
    const l = await post('/latitude/goods/getMallChatGoodsList', {uid: '0', pageNum: 1, pageSize: max});
    ids = (((l.result || {}).goodsList) || []).map(g => String(g.goodsId)).slice(0, max);
  }
  for (const id of ids) {
    try {
      const r = await post('/latitude/goods/skuSelectorForMall', {goodsId: Number(id), uid: '0'});
      const g = r.result || {};
      if (!r.success || !g.goodsName) { errors.push(id + ' ' + (r.errorMsg || '')); continue; }
      const colour = {};
      const skus = (g.sku || []).filter(k => k.isOnsale !== 0).map(k => {
        const spec = {};
        for (const sp of k.specs || []) if (sp.specKey) spec[sp.specKey] = String(sp.specValue || '').replace(/^\/+|\/+$/g, '').trim();
        const first = (k.specs || [])[0];
        if (k.thumbUrl && first) colour[String(first.specValue || '').replace(/^\/+|\/+$/g, '').trim()] = k.thumbUrl;
        return {spec, price: Number(k.normalPrice || k.groupPrice) / 100, stock: Number(k.quantity || 0), code: String(k.outSkuSn || '')};
      });
      out.push({source_id: id, title: g.goodsName, category: '', attrs: {}, desc: g.goodsDesc || '',
        main: [g.hdUrl || g.hdThumbUrl || g.thumbUrl].filter(Boolean), main34: [], detail: [], colour, skus, code: String(g.outGoodsSn || '')});
    } catch (e) { errors.push(id + ' ' + e); }
  }
  return JSON.stringify({products: out, errors});
})(%s, %d)"""


async def _read(platform: str, store_id: str, ids: List[str], max_n: int) -> Dict[str, Any]:
    from agent.ec_skills.browser_use_extension import store_page
    tabs = [t for t in store_page.store_tabs(platform) if not store_id or t.get("store_id") == store_id]
    if not tabs:
        raise RuntimeError("没有打开来源店铺的页面（店铺浏览器没启动或没登录）")
    if platform == "douyin":
        return await store_page.evaluate_in_background_tab(tabs[0]["ws"], LIST_PAGE, _DOUYIN_JS % (json.dumps(ids), max_n), timeout=240.0)
    return await store_page.evaluate(tabs[0]["ws"], _PDD_JS % (json.dumps(ids), max_n), timeout=240.0)


def read_products(platform: str, store_id: str, ids: List[str], max_n: int = MAX_PRODUCTS, timeout_s: float = 280.0) -> Dict[str, Any]:
    if platform not in ("douyin", "pdd"):
        raise RuntimeError("搬家目前能从抖店、拼多多店铺读商品（淘宝还没接上）")
    box: Dict[str, Any] = {}

    def run():
        try:
            box["out"] = asyncio.run(_read(platform, store_id, ids, max_n))
        except Exception as exc:
            box["error"] = f"{type(exc).__name__}: {exc}"
    t = threading.Thread(target=run, name="store-move", daemon=True)
    t.start()
    t.join(timeout_s)
    if "out" not in box:
        raise RuntimeError(box.get("error") or "timed out")
    raw = box["out"] if isinstance(box["out"], dict) else json.loads(box["out"] or "{}")
    return {"products": raw.get("products") or [], "errors": raw.get("errors") or []}


def _safe(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|\s]+', "_", str(name)).strip("_")[:40] or "x"


def _download(url: str, path: str) -> str:
    import requests
    url = url if url.startswith("http") else "https:" + url
    for attempt in range(2):
        try:
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            break
        except requests.RequestException:
            if attempt:
                raise
    ext = {"image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}.get(r.headers.get("content-type", "").split(";")[0], ".jpg")
    path = os.path.splitext(path)[0] + ext
    with open(path, "wb") as f:
        f.write(r.content)
    return path


def code_of(p: Dict[str, Any]) -> str:
    """The product's own code, else what all its SKU codes start with ("ECK3102-11" -> "ECK3102"), else its ID."""
    heads = {re.split(r"[-_]", s["code"])[0] for s in p.get("skus") or [] if s.get("code")}
    return p.get("code") or (heads.pop() if len(heads) == 1 else "") or p["source_id"]


def sheet_rows(p: Dict[str, Any], files: Dict[str, List[str]]) -> Dict[str, list]:
    """One product -> rows of the 商品上架 sheets (listing_sheet.SHEETS)."""
    code = code_of(p)
    prices = [s["price"] for s in p["skus"] if s.get("price")]
    goods = {"商品编码": code, "商品标题": p["title"], "类目": p["category"], "品牌": p["attrs"].get("品牌", ""),
             "价格": min(prices) if prices else "", "库存": sum(int(s.get("stock") or 0) for s in p["skus"]),
             "属性": ";".join(f"{k}={v}" for k, v in p["attrs"].items() if k != "品牌"), "描述": p.get("desc", "")[:500]}
    skus = [dict({"商品编码": code}, **s["spec"], 价格=s["price"], 库存=s["stock"], 规格编码=s["code"]) for s in p["skus"]]
    pics = [{"商品编码": code, "文件名": f, "用途": role, "颜色": colour} for role, fs in files.items() for f, colour in fs]
    return {"商品": [goods], "规格": skus, "图片": pics}


def check(p: Dict[str, Any], files: Dict[str, list], target: str) -> List[str]:
    todo = []
    if not p["category"]:
        todo.append("类目要填")
    elif target and target != p.get("platform"):
        todo.append(f"类目「{p['category']}」是来源平台的，要换成目标平台的类目")
    if len(files.get("主图", [])) < 3:
        todo.append(f"主图只有 {len(files.get('主图', []))} 张（建议至少 3 张）")
    if not files.get("详情图"):
        todo.append("没有详情图")
    if not p["attrs"]:
        todo.append("属性要补")
    return todo


def run(source_platform: str, source_store: str, folder: str, opts: Optional[Dict[str, Any]] = None,
        products: Optional[List[Dict[str, Any]]] = None, download=None, now: Optional[dt.datetime] = None) -> Dict[str, Any]:
    """Read products from *source_store* and write <folder>/结果/搬家_<time>/商品上架表.xlsx + pictures."""
    opts = opts or {}
    ids = [x for x in re.split(r"[,，\s]+", str(opts.get("product_ids") or "")) if x.strip()]
    errors: List[str] = []
    if products is None:
        got = read_products(source_platform, source_store, ids, int(opts.get("max_products") or MAX_PRODUCTS))
        products, errors = got["products"], got["errors"]
    if not products:
        return {"summary": f"店铺搬家：没有从 {source_store} 读到商品" + (f"（{'；'.join(errors[:2])}）" if errors else "。"),
                "path": "", "products": 0}
    download = download or _download
    out_dir = os.path.join(folder, "结果", (now or dt.datetime.now()).strftime("搬家_%Y%m%d_%H%M"))
    os.makedirs(out_dir, exist_ok=True)
    sheets: Dict[str, list] = {"商品": [], "规格": [], "图片": []}
    lines, pics = [], 0
    target = str(opts.get("target_platform") or "")
    for p in products:
        p["platform"] = source_platform
        code = _safe(code_of(p))
        files: Dict[str, List[tuple]] = {"主图": [], "详情图": [], "颜色图": []}
        jobs = [("主图", u, "") for u in p["main"][:5]] + [("详情图", u, "") for u in p["detail"][:20]] + \
               [("颜色图", u, c) for c, u in p["colour"].items()]
        for n, (role, url, colour) in enumerate(jobs, 1):
            try:
                got = download(url, os.path.join(out_dir, f"{code}_{role}{n}"))
                files[role].append((os.path.basename(got), colour))
            except Exception as exc:
                errors.append(f"{code} 图片没下载下来：{str(exc)[:60]}")
        pics += sum(len(v) for v in files.values())
        for k, rows in sheet_rows(p, files).items():
            sheets[k] += rows
        todo = check(p, files, target)
        lines.append(f"- {p['title'][:24]}（{len(p['skus'])} 个规格，{sum(len(v) for v in files.values())} 张图）"
                     + (f"：{'；'.join(todo)}" if todo else ""))
    import openpyxl
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    from agent.ec_skills.listing_sheet import SHEETS
    for name in ("商品", "规格", "图片"):
        ws = wb.create_sheet(name)
        cols = list(SHEETS[name]) if name != "规格" else ["商品编码"] + list(dict.fromkeys(
            k for r in sheets["规格"] for k in r if k not in ("商品编码", "价格", "库存", "规格编码"))) + ["价格", "库存", "规格编码"]
        ws.append(cols)
        for r in sheets[name]:
            ws.append([r.get(c, "") for c in cols])
    path = os.path.join(out_dir, "商品上架表.xlsx")
    wb.save(path)
    logger.info(f"[store-move] {source_platform} {source_store} products={len(products)} pictures={pics} errors={len(errors)}")
    text = (f"店铺搬家：从 {source_store} 读了 {len(products)} 个商品、{pics} 张图，做成了商品上架表：{out_dir}\n" + "\n".join(lines)
            + "\n还没有发布：先检查表格（类目、标题、价格、属性），改好后把这个文件夹里的表格和图片放进目标店铺的上架文件夹"
              "（listing_inbox/<店铺>），再运行「商品上架」。")
    if errors:
        text += "\n没读全：" + "；".join(errors[:3])
    return {"summary": text, "path": path, "products": len(products), "pictures": pics}
