"""违禁词巡检: every live product title and spec name of a store checked against banned words.

Words come from three places, merged:
  1. WORDS below (广告法 极限词, 虚假/权威, 医疗功效, 迷信, 诱导): built in;
  2. <ks>/违禁词/违禁词库.txt -- a shared list that a refresh can replace (refresh(url));
  3. <folder>/违禁词.txt -- the merchant's own: one word per line, "分类:词" to file it,
     "-词" to drop a built-in word for this store, "#" starts a comment.

"禁用" words are against the 广告法 everywhere; "慎用" words depend on the category or need
papers (e.g. 美白 needs 特证 for cosmetics, 抗菌 needs a test report). The result says which
product, where (title / spec), the word, its class and what to do. Read only: no change
is made to the store; titles are fixed by the person or through 新品标题.
"""
from __future__ import annotations

import os
import re
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple

from utils.logger_helper import logger_helper as logger

BAN, CARE = "禁用", "慎用"
# (class, severity, words). Longer words win over the shorter ones they contain.
WORDS: List[Tuple[str, str, str]] = [
    ("极限词", BAN, "最 最佳 最具 最爱 最赚 最优 最优秀 最好 最大 最高 最高级 最高档 最奢侈 最低 最低价 最便宜 最流行 "
                   "最受欢迎 最时尚 最新 最先进 最先 最后一波 第一 中国第一 全网第一 销量第一 排名第一 全国第一 第一品牌 "
                   "NO.1 NO1 TOP1 TOP.1 唯一 独一无二 一流 仅此一次 顶级 顶尖 尖端 极品 极佳 绝佳 绝对 终极 极致 "
                   "首个 首选 首家 首发 全网首发 全国首家 独家 国家级 世界级 全球级 宇宙级 王牌 冠军 领袖品牌 领导品牌 "
                   "领先 领导者 缔造者 至尊 巅峰 史无前例 前无古人 万能 无敌 全网 史上 100% 百分百 永久 祖传 "
                   "遥遥领先 全球首发 全国销量冠军 销冠"),
    ("虚假权威", BAN, "国家免检 质量免检 免检 特供 专供 国宾 国家领导人 驰名商标 中国驰名商标 指定产品 央视推荐 "
                     "央视上榜 权威认证 专家推荐 医生推荐 院士推荐 老字号"),
    ("诱导时限", BAN, "万人疯抢 全民疯抢 抢疯了 抢爆 再不抢就没了 错过就没机会了 不会再便宜了 随时涨价 马上涨价 "
                     "史上最低价 仅限今日 今日截止 秒杀全网 点击领奖 恭喜获奖 免单"),
    ("医疗功效", BAN, "治疗 治愈 根治 药到病除 特效 抗癌 防癌 消炎 降血压 降血糖 降血脂 壮阳 增高 丰胸 排毒 "
                     "祛病 包治 无副作用 零副作用 疗效 处方 复方 药用 医用级"),
    ("医疗功效", CARE, "美白 祛斑 淡斑 祛痘 抗皱 防脱 生发 脱毛 防晒 杀菌 抗菌 除菌 抑菌 除螨 消毒 减肥 瘦身 燃脂 "
                      "助眠 改善睡眠 提高免疫力 增强免疫力 补肾 养生 调理 安神 修复 抗过敏 敏感肌 孕妇可用 婴儿可用 "
                      "母婴级 婴幼儿级 医美 械字号 药妆"),
    ("迷信", BAN, "招财进宝 旺夫 旺财 辟邪 转运 改运 风水 化煞 化解小人 镇宅 开光 保平安 带来好运 增加财运 事业运 桃花运"),
    ("材质夸大", CARE, "纯天然 100%纯棉 原单 原厂 尾单 大牌同款 明星同款 专柜品质 官方正品"),
]
REMEDY = {"极限词": "删掉，或换成具体的事实（材质、尺寸、数量）", "虚假权威": "删掉，除非有对应的证明文件",
          "诱导时限": "删掉；活动时间写在活动设置里", "医疗功效": "非药品/器械不能写；有特证/报告的要能拿得出来",
          "迷信": "删掉", "材质夸大": "要和商品属性、吊牌一致；说不清的别写", "商家": "按商家自己的规定改"}
SHARED = "违禁词库.txt"
OWN = "违禁词.txt"


def parse(lines: Iterable[str], default_class: str = "商家") -> Tuple[Dict[str, Tuple[str, str]], set]:
    """({word: (class, severity)}, {words to drop}) from text lines."""
    add: Dict[str, Tuple[str, str]] = {}
    drop = set()
    for raw in lines:
        s = raw.split("#", 1)[0].strip()
        if not s:
            continue
        if s.startswith("-"):
            drop.add(s[1:].strip())
            continue
        cls, sev = default_class, BAN
        if re.match(r"^[^:：]{1,8}[:：]", s):
            cls, s = re.split(r"[:：]", s, 1)
            cls = cls.strip()
            sev = CARE if "慎" in cls else BAN
        for w in re.split(r"[\s,，、]+", s):
            if w.strip():
                add[w.strip()] = (cls, sev)
    return add, drop


def _read(path: str) -> List[str]:
    try:
        with open(path, encoding="utf-8-sig") as f:
            return f.read().splitlines()
    except UnicodeDecodeError:
        with open(path, encoding="gb18030") as f:
            return f.read().splitlines()
    except OSError:
        return []


def word_list(folder: str = "", shared_dir: str = "") -> Dict[str, Tuple[str, str]]:
    words: Dict[str, Tuple[str, str]] = {}
    for cls, sev, text in WORDS:
        for w in text.split():
            words.setdefault(w, (cls, sev))
    drop: set = set()
    for path, cls in ((os.path.join(shared_dir, SHARED), "词库"), (os.path.join(folder, OWN), "商家")):
        if (shared_dir if cls == "词库" else folder) and os.path.isfile(path):
            add, d = parse(_read(path), cls)
            words.update(add)
            drop |= d
    for w in drop:
        words.pop(w, None)
    return words


def find(text: str, words: Dict[str, Tuple[str, str]]) -> List[Tuple[str, str, str]]:
    """[(word, class, severity)] in *text*; a word inside a longer hit is not repeated."""
    low = str(text or "").lower()
    taken: List[Tuple[int, int]] = []
    out = []
    for w in sorted(words, key=len, reverse=True):
        start = 0
        wl = w.lower()
        while True:
            i = low.find(wl, start)
            if i < 0:
                break
            span = (i, i + len(wl))
            if not any(a <= span[0] and span[1] <= b for a, b in taken):
                taken.append(span)
                if not any(o[0] == w for o in out):
                    out.append((w, *words[w]))
            start = i + 1
    return out


def check(skus: List[Dict[str, Any]], words: Dict[str, Tuple[str, str]]) -> List[Dict[str, Any]]:
    """One row per (product, place, word)."""
    rows, seen = [], set()
    for s in skus:
        pid = str(s.get("product_id") or "")
        places = [("标题", s.get("title") or "")] + [("规格", f"{k}:{v}") for k, v in (s.get("spec") or {}).items()]
        for where, text in places:
            for w, cls, sev in find(text, words):
                key = (pid, where, text if where == "规格" else "", w)
                if key in seen:
                    continue
                seen.add(key)
                rows.append({"级别": sev, "商品ID": pid, "商品": str(s.get("title") or "")[:60], "位置": where,
                             "原文": text[:80], "词": w, "分类": cls, "怎么改": REMEDY.get(cls, REMEDY["商家"])})
    rows.sort(key=lambda r: (r["级别"] != BAN, r["商品ID"]))
    return rows


def summary(rows: List[Dict[str, Any]], products: int, store: str = "") -> str:
    ban = [r for r in rows if r["级别"] == BAN]
    care = [r for r in rows if r["级别"] == CARE]
    hit = {r["商品ID"] for r in rows}
    if not rows:
        return f"违禁词巡检（{store}）：查了 {products} 个在售商品的标题和规格名，没发现违禁词。"
    text = (f"违禁词巡检（{store}）：查了 {products} 个在售商品的标题和规格名，{len(hit)} 个有问题："
            f"禁用词 {len(ban)} 处，慎用词 {len(care)} 处。")
    for r in ban[:6]:
        text += f"\n- 禁用「{r['词']}」：{r['商品'][:20]}（{r['位置']}）"
    for r in care[:3]:
        text += f"\n- 慎用「{r['词']}」：{r['商品'][:20]}（{r['位置']}，{r['分类']}）"
    text += "\n不会改店铺：标题请自己改，或用「新品标题」重写后再改。"
    return text


def refresh(url: str, shared_dir: str, timeout_s: float = 20.0) -> Dict[str, Any]:
    """Replace the shared list with the plain-text list at *url* (one word or "分类:词" per line).
    A list that comes back empty or tiny keeps the old one."""
    import requests
    resp = requests.get(url, timeout=timeout_s)
    resp.raise_for_status()
    text = resp.content.decode("utf-8-sig", errors="replace")
    add, drop = parse(text.splitlines(), "词库")
    if len(add) < 20:
        raise RuntimeError(f"违禁词库只有 {len(add)} 个词，没有替换旧的")
    os.makedirs(shared_dir, exist_ok=True)
    tmp = os.path.join(shared_dir, SHARED + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, os.path.join(shared_dir, SHARED))
    return {"words": len(add), "dropped": len(drop)}


def _xlsx(rows: List[Dict[str, Any]], path: str, quality: Optional[List[Dict[str, Any]]] = None) -> str:
    from agent.ec_skills.store_reports import write_xlsx
    sheets = {"违禁词": rows or [{"结果": "没发现违禁词"}]}
    if quality:
        sheets["质量分"] = quality
    return write_xlsx(sheets, path)


def run_for_store(store_id: str, platform: str, folder: str, shared_dir: str = "",
                  words_url: str = "", skus: Optional[List[Dict[str, Any]]] = None,
                  with_quality: bool = True) -> Dict[str, Any]:
    """Check *store_id*'s live titles (and, on 抖店, the platform's quality score and missing
    pictures: store_quality); Excel to <folder>/结果/违禁词巡检_<time>.xlsx."""
    errors = []
    if words_url and shared_dir:
        try:
            refresh(words_url, shared_dir)
        except Exception as exc:
            errors.append(f"词库没更新（用旧的）：{str(exc)[:80]}")
    if skus is None:
        from agent.ec_skills.store_prices import read_store_skus
        skus = [s for s in read_store_skus(platform, store_id=store_id)[0]
                if not store_id or not s.get("store_id") or s.get("store_id") == store_id]
    if not skus:
        raise RuntimeError("违禁词巡检：没有读到店铺商品（店铺页没有打开，或未登录）")
    words = word_list(folder, shared_dir)
    rows = check(skus, words)
    products = len({str(s.get("product_id") or "") for s in skus})
    quality: List[Dict[str, Any]] = []
    if platform == "douyin" and with_quality:
        try:
            from agent.ec_skills.store_quality import read_quality
            q = read_quality(store_id)
            quality = q["rows"]
            errors += [f"质量分：{e}" for e in q["errors"][:2]]
        except Exception as exc:
            errors.append(f"质量分没读到：{str(exc)[:80]}")
    path = _xlsx(rows, os.path.join(folder, "结果", time.strftime("违禁词巡检_%Y%m%d_%H%M.xlsx")), quality)
    text = summary(rows, products, store_id or platform)
    if quality:
        from agent.ec_skills.store_quality import summary as quality_summary
        text += "\n" + quality_summary(quality)
    if errors:
        text += "\n" + "；".join(errors)
    logger.info(f"[word-patrol] {store_id} products={products} hits={len(rows)} words={len(words)}")
    return {"summary": text, "path": path, "hits": len(rows), "products": products, "errors": errors}
