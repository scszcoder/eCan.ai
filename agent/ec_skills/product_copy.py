"""商品运营 writing chores on the llm-proxy models, from the merchant's own files (works on all 3 platforms).

Input: <folder>/输入/<商品>/ -- one folder per product -- holding pictures (jpg/png/webp, in name order)
and optionally 说明.txt (category, material, selling points, 规格, who it is for) and 竞品标题.txt (titles of
competing items the merchant copied, one per line; we don't read competitor pages ourselves).

  titles   新品标题     3 long titles + 1 short title + one title per 规格, each checked for length and for
                        absolute words (最/第一/顶级... banned by the 广告法 and the platforms)
  detail   详情页分析   a detail page (its pictures, top to bottom) read screen by screen: what each screen
                        does, its text, the order of selling points, what is missing, what to change

Results: <folder>/结果/<kind>_<time>.xlsx plus a summary. Nothing is written to a store.
"""
from __future__ import annotations

import datetime as dt
import io
import json
import os
import re
from typing import Any, Callable, Dict, List, Optional

from utils.logger_helper import logger_helper as logger

PICS = (".jpg", ".jpeg", ".png", ".webp")
VISION_MODEL = os.environ.get("ECAN_PRODUCT_IMAGE_MODEL", "qwen3-vl-plus")
NAMES = {"titles": "新品标题", "detail": "详情页分析"}
TITLE_MAX = 60          # 抖店 / 拼多多 / 淘宝: 30 汉字 = 60 characters (a 汉字 counts 2)
SHORT_MAX = 24
# absolute / unprovable claims the 广告法 bans and the platforms reject in titles
BANNED = ("最", "第一", "唯一", "顶级", "顶尖", "极品", "极致", "绝对", "首个", "首选", "国家级", "世界级",
          "全网", "史上", "万能", "100%", "百分百", "独一无二", "无敌", "冠军", "王牌", "永久", "特效", "根治")
REPAIRS = 2
PIECES_PER_CALL = 6
MAX_PIECES = 24


def width(text: str) -> int:
    """Title length the way the platforms count it: a 汉字 / full-width character = 2, ASCII = 1."""
    return sum(1 if ord(ch) < 128 else 2 for ch in text)


def banned_in(text: str) -> List[str]:
    return [w for w in BANNED if w in text]


def products(folder: str) -> List[Dict[str, Any]]:
    """[{name, pictures, notes, rivals}] for each product folder under <folder>/输入/."""
    root = os.path.join(folder, "输入")
    out = []
    for name in sorted(os.listdir(root)) if os.path.isdir(root) else []:
        d = os.path.join(root, name)
        if not os.path.isdir(d):
            continue

        def text(*names, limit=1500):
            for fn in names:
                try:
                    with open(os.path.join(d, fn), encoding="utf-8-sig") as fh:
                        return fh.read().strip()[:limit]
                except OSError:
                    continue
            return ""
        pics = sorted(os.path.join(d, f) for f in os.listdir(d) if f.lower().endswith(PICS))
        notes, rivals = text("说明.txt", "notes.txt"), text("竞品标题.txt", limit=3000)
        if pics or notes:
            out.append({"name": name, "pictures": pics, "notes": notes,
                        "rivals": [x.strip() for x in rivals.splitlines() if x.strip()][:20]})
    return out


def _jpeg(src, long_side: int = 1024) -> bytes:
    from PIL import Image
    im = src if hasattr(src, "convert") else Image.open(src)
    im = im.convert("RGB")
    im.thumbnail((long_side, long_side))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return buf.getvalue()


def pieces(path: str) -> List[bytes]:
    """A tall detail picture cut into screens about 1.3x as high as wide, so its text stays readable after
    the model's downscale; a normal picture is one piece."""
    from PIL import Image
    with Image.open(path) as im:
        w, h = im.size
        step = max(1, int(w * 1.3))
        if h <= step * 1.2:
            return [_jpeg(im)]
        return [_jpeg(im.crop((0, top, w, min(h, top + step)))) for top in range(0, h, step)]


def ask_model(prompt: str, images: List[bytes]) -> str:
    """One call on the llm-proxy (the vision model when pictures go along)."""
    import base64
    from langchain_core.messages import HumanMessage
    from agent.ec_skills.llm_utils.llm_utils import create_ecanai_chat_llm
    from utils.log_scope import scope
    parts = [{"type": "text", "text": prompt}]
    for b in images:
        parts.append({"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(b).decode()}})
    llm = create_ecanai_chat_llm(VISION_MODEL, temperature=0.3, media=bool(images))
    with scope(modality="multimodal" if images else "text"):
        reply = llm.invoke([HumanMessage(content=parts)]).content
    return reply if isinstance(reply, str) else json.dumps(reply, ensure_ascii=False)


def _json(raw: str) -> Dict[str, Any]:
    m = re.search(r"\{.*\}", raw or "", re.S)
    return json.loads(m.group(0)) if m else {}


# ---------------------------------------------------------------- 新品标题

_TITLE_PROMPT = """你是电商运营，给一件新品写{platform}商品标题。
商品说明：{notes}
{rivals}
规则：
- 长标题 3 个，每个不超过 {tmax} 字符（汉字算 2，字母数字算 1），尽量写满；结构：核心品类词 + 属性词（材质/款式/功能）+ 人群/场景词 + 卖点词；
  3 个标题侧重不同的搜索词，不要只是换顺序。
- 短标题 1 个，不超过 {smax} 字符，一眼看懂是什么、最大卖点。
- 说明里列了规格（颜色/尺码/型号）时，每个规格一个规格标题（不超过 {tmax} 字符），规格名照说明原样写、不加单位；没列就不写。
- 只写图片和说明里看得出来的东西，不编造材质、功效、销量、认证；不用 最/第一/唯一/顶级/极品/绝对/全网/100% 这类极限词；不用别的品牌名。
只输出 JSON：{{"long": ["..",".." ,".."], "short": "..", "sku": [{{"spec": "..", "title": ".."}}],
"words": {{"core": [".."], "attr": [".."], "scene": [".."], "selling": [".."]}}, "why": "一两句：为什么这样组词"}}"""


def check_titles(got: Dict[str, Any], tmax: int, smax: int) -> List[str]:
    probs = []
    titles = [("长标题", t, tmax) for t in got.get("long") or []] + [("短标题", got.get("short") or "", smax)]
    titles += [(f"规格标题 {s.get('spec', '')}", s.get("title") or "", tmax) for s in got.get("sku") or []]
    for label, t, cap in titles:
        if not t:
            probs.append(f"{label} 是空的")
        elif width(t) > cap:
            probs.append(f"{label}「{t}」{width(t)} 字符，超过 {cap}，要删掉至少 {width(t) - cap} 字符")
        if banned_in(t):
            probs.append(f"{label}「{t}」用了极限词 {'、'.join(banned_in(t))}")
    if len(got.get("long") or []) < 3:
        probs.append("长标题不到 3 个")
    return probs


def design_titles(p: Dict[str, Any], platform: str = "", tmax: int = TITLE_MAX, smax: int = SHORT_MAX,
                  ask: Optional[Callable[[str, List[bytes]], str]] = None) -> Dict[str, Any]:
    """Titles for one product; one repair round when a title breaks the length / word rules."""
    ask = ask or ask_model
    rivals = ("同类商品的标题（参考它们的搜索词，不要照抄）：\n" + "\n".join(p["rivals"])) if p.get("rivals") else ""
    prompt = _TITLE_PROMPT.format(platform=platform or "", notes=p.get("notes") or "（没有说明，只看图片）",
                                  rivals=rivals, tmax=tmax, smax=smax)
    images = [_jpeg(x) for x in p.get("pictures", [])[:3]]
    got = _json(ask(prompt, images))
    probs = check_titles(got, tmax, smax)
    # the model can't count characters (KEN 11-05: a 31-char short title it called 23), so each repair round
    # tells it the counted length and how much to cut
    for _ in range(REPAIRS):
        if not probs:
            break
        fixed = _json(ask(prompt + "\n\n上一次的结果有问题（字符数是程序数的，汉字算 2，空格和字母数字算 1，以此为准），"
                          "只改有问题的标题，其余照抄，重新输出完整 JSON：\n" + "\n".join(probs)
                          + "\n上一次的结果：" + json.dumps(got, ensure_ascii=False), images))
        if fixed:
            got = fixed
        probs = check_titles(got, tmax, smax)
    got["problems"] = probs
    return got


# ---------------------------------------------------------------- 详情页分析

_SCREEN_PROMPT = """下面是一个电商商品详情页从上往下的第 {first} 到第 {last} 屏（截图按顺序）。
商品说明：{notes}
逐屏说明，只输出 JSON：{{"screens": [{{"no": 屏序号, "role": "首屏/卖点/细节/参数/尺码/场景/对比/资质/售后/品牌/其他 之一",
"text": "屏上的主要文字（原样，最多60字）", "point": "这一屏想让买家相信什么（一句话）", "issue": "看不清、字太小、信息重复等问题，没有就空"}}]}}"""

_REVIEW_PROMPT = """你是电商视觉运营。这是一个商品详情页逐屏的内容（从上往下）：
{screens}
商品说明：{notes}
分析这个详情页为什么能（或不能）让买家下单，只输出 JSON：
{{"structure": "整体结构一句话（例如 痛点→卖点→细节→参数→售后）",
"selling_points": ["按出现顺序列出卖点"],
"strengths": ["做得好的地方，指明第几屏"],
"missing": ["缺少的买家关心的信息（如尺码、材质成分、洗护、售后、使用场景）"],
"suggestions": ["具体改法，指明第几屏，最多 6 条"]}}
建议里不要编造商品事实：尺寸、成分比例、认证等级的含义、售后承诺等，详情页和说明里没有的，写成【商家填写：xx】让商家补，不要替商家写数字或承诺。"""


def analyse_detail(p: Dict[str, Any], ask: Optional[Callable[[str, List[bytes]], str]] = None) -> Dict[str, Any]:
    ask = ask or ask_model
    shots: List[bytes] = []
    for path in p.get("pictures", []):
        shots.extend(pieces(path))
    cut = len(shots) > MAX_PIECES
    shots = shots[:MAX_PIECES]
    notes = p.get("notes") or "（没有说明）"
    screens: List[Dict[str, Any]] = []
    for i in range(0, len(shots), PIECES_PER_CALL):
        batch = shots[i:i + PIECES_PER_CALL]
        got = _json(ask(_SCREEN_PROMPT.format(first=i + 1, last=i + len(batch), notes=notes), batch))
        for k, s in enumerate((got.get("screens") or [])[:len(batch)]):
            screens.append(dict(s, no=i + k + 1))
    lines = "\n".join(f"第{s['no']}屏 [{s.get('role', '')}] {s.get('text', '')} → {s.get('point', '')}" for s in screens)
    review = _json(ask(_REVIEW_PROMPT.format(screens=lines or "（没读到）", notes=notes), [])) if screens else {}
    return {"screens": screens, "review": review, "cut": cut}


# ---------------------------------------------------------------- run

def _xlsx(kind: str, results: List[Dict[str, Any]], path: str) -> str:
    import openpyxl
    os.makedirs(os.path.dirname(path), exist_ok=True)
    wb = openpyxl.Workbook()
    ws = wb.active
    if kind == "titles":
        ws.title = "新品标题"
        ws.append(["商品", "类型", "规格", "标题", "字符数", "问题"])
        for r in results:
            g = r["result"]
            rows = [("长标题", "", t) for t in g.get("long") or []] + [("短标题", "", g.get("short") or "")]
            rows += [("规格标题", s.get("spec", ""), s.get("title", "")) for s in g.get("sku") or []]
            for label, spec, t in rows:
                bad = "；".join(x for x in g.get("problems", []) if t and t in x)
                ws.append([r["name"], label, spec, t, width(t), bad])
        w2 = wb.create_sheet("组词")
        w2.append(["商品", "核心词", "属性词", "人群/场景词", "卖点词", "思路"])
        for r in results:
            w = r["result"].get("words") or {}
            w2.append([r["name"]] + ["、".join(w.get(k) or []) for k in ("core", "attr", "scene", "selling")]
                      + [r["result"].get("why", "")])
    else:
        ws.title = "逐屏"
        ws.append(["商品", "第几屏", "作用", "文字", "想说明", "问题"])
        for r in results:
            for s in r["result"]["screens"]:
                ws.append([r["name"], s.get("no"), s.get("role", ""), s.get("text", ""), s.get("point", ""), s.get("issue", "")])
        w2 = wb.create_sheet("结论")
        w2.append(["商品", "项目", "内容"])
        for r in results:
            rv = r["result"]["review"]
            w2.append([r["name"], "结构", rv.get("structure", "")])
            for key, label in (("selling_points", "卖点顺序"), ("strengths", "做得好"), ("missing", "缺少"), ("suggestions", "建议")):
                for x in rv.get(key) or []:
                    w2.append([r["name"], label, x])
    wb.save(path)
    return path


def _summary(kind: str, results: List[Dict[str, Any]], errors: List[str], path: str) -> str:
    name = NAMES[kind]
    out = [f"{name}：{len(results)} 个商品，结果在 {path}。" if results else f"{name}：没有结果。"]
    for r in results[:3]:
        g = r["result"]
        if kind == "titles":
            out.append(f"「{r['name']}」长标题：" + " ｜ ".join(g.get("long") or []) + f"；短标题：{g.get('short', '')}")
            if g.get("problems"):
                out.append("  还要人改：" + "；".join(g["problems"][:3]))
        else:
            rv = g["review"]
            out.append(f"「{r['name']}」{len(g['screens'])} 屏，结构：{rv.get('structure', '')}")
            if rv.get("missing"):
                out.append("  缺少：" + "；".join(rv["missing"][:3]))
            if rv.get("suggestions"):
                out.append("  建议：" + "；".join(rv["suggestions"][:3]))
            if g.get("cut"):
                out.append(f"  图片太长，只看了前 {MAX_PIECES} 屏")
    if errors:
        out.append("没做成：" + "；".join(errors[:3]))
    out.append("只是建议，不会改店铺；用之前请人工看一遍。" if kind == "detail" else
               "只是草稿，不会改店铺；发布前请人工核对，标题里的属性要和商品一致。")
    return "\n".join(out)


def run(kind: str, folder: str, opts: Optional[Dict[str, Any]] = None, ask=None, now=None) -> Dict[str, Any]:
    """*kind* for every product folder under <folder>/输入/. Returns {summary, path, errors}."""
    opts = opts or {}
    if kind not in NAMES:
        raise ValueError(f"unknown kind {kind!r}; one of {', '.join(NAMES)}")
    items = products(folder)
    only = str(opts.get("product") or "").strip()
    if only:
        items = [p for p in items if p["name"] == only]
    if kind == "detail":
        items = [p for p in items if p["pictures"]]
    name = NAMES[kind]
    if not items:
        need = "详情页的图片（从上往下，按文件名排序）" if kind == "detail" else "1-3 张商品图和/或 说明.txt"
        return {"summary": f"{name}：{os.path.join(folder, '输入')} 下面没有商品文件夹（每个商品一个文件夹，放{need}）。",
                "path": "", "errors": []}
    results, errors = [], []
    for p in items[: int(opts.get("max_products") or 5)]:
        try:
            if kind == "titles":
                res = design_titles(p, str(opts.get("platform") or ""), int(opts.get("title_max") or TITLE_MAX),
                                    int(opts.get("short_max") or SHORT_MAX), ask=ask)
            else:
                res = analyse_detail(p, ask=ask)
            results.append({"name": p["name"], "result": res})
        except Exception as exc:
            errors.append(f"{p['name']}：{type(exc).__name__}: {str(exc)[:120]}")
    stamp = (now or dt.datetime.now()).strftime("%Y%m%d_%H%M")
    path = _xlsx(kind, results, os.path.join(folder, "结果", f"{name}_{stamp}.xlsx")) if results else ""
    logger.info(f"[product-copy] {kind} products={len(items)} done={len(results)} errors={len(errors)}")
    return {"summary": _summary(kind, results, errors, path), "path": path, "errors": errors}
