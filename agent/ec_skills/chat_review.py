"""客服质检 + 客户之声 from our own 客服 replies (the qa_history table: every reply the
front desk sent, with the buyer's question). Read only.

  quality  客服质检  every turn of the last N days (default 7) checked: by rules (empty or
                     stalling replies, banned words in a reply, the same reply sent twice in a
                     row) and by the model in batches (答非所问 / 没答 / 乱承诺 / 信息可能不对 /
                     态度 / 太长); the worst turns listed with the reason
  voice    客户之声  every buyer question given a topic (尺码, 物流发货, ...) by the model,
                     counted here; per topic the products asked about most and examples; then
                     the model's suggestions (what to add to 商品知识 / 详情页 / FAQ)

Buyer names are never written out; long digit runs (phones, order numbers) are masked.
Result Excel in <folder>/结果/<名称>_<time>.xlsx.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
from collections import Counter, defaultdict
from typing import Any, Callable, Dict, List, Optional

from utils.logger_helper import logger_helper as logger

MODEL = os.environ.get("ECAN_CHAT_REVIEW_MODEL", "qwen3-vl-plus")
NAMES = {"quality": "客服质检", "voice": "客户之声"}
BATCH = 25
TOPICS = ["尺码", "物流发货", "价格优惠", "质量材质", "颜色款式", "使用方法", "售后退换", "库存现货", "发票", "催单投诉", "其他"]
STALL = ("稍后回复", "稍等", "正在为您查询", "正在查询", "请稍候", "马上为您", "帮您问一下")
ISSUES = ["答非所问", "没答", "乱承诺", "信息可能不对", "态度", "太长"]


def mask(text: Any, n: int = 200) -> str:
    s = re.sub(r"\d{6,}", lambda m: m.group(0)[:2] + "****" + m.group(0)[-2:], str(text or ""))
    return re.sub(r"\s+", " ", s).strip()[:n]


def read_turns(store_id: str, days: int, now: Optional[dt.datetime] = None) -> List[Dict[str, Any]]:
    """qa_history rows of the last *days* days for *store_id*, from the running app's DB."""
    from app_context import AppContext
    mgr = getattr(AppContext.get_main_window(), "ec_db_mgr", None)
    svc = getattr(mgr, "qa_history_service", None) if mgr else None
    if svc is None:
        raise RuntimeError("聊天记录库没打开（这个功能要在桌面版里运行）")
    since = (now or dt.datetime.now(dt.timezone.utc)) - dt.timedelta(days=days)
    return svc.list_recent(since, store_id=store_id or None)


def _when(v: Any) -> str:
    if isinstance(v, dt.datetime):
        t = v if v.tzinfo else v.replace(tzinfo=dt.timezone.utc)
        return t.astimezone(dt.timezone(dt.timedelta(hours=8))).strftime("%m-%d %H:%M")
    return str(v or "")[5:16]


def _ask(prompt: str) -> str:
    from langchain_core.messages import HumanMessage
    from agent.ec_skills.llm_utils.llm_utils import create_ecanai_chat_llm
    from utils.log_scope import scope
    llm = create_ecanai_chat_llm(MODEL, temperature=0.1)
    with scope(modality="text"):
        reply = llm.invoke([HumanMessage(content=prompt)]).content
    return reply if isinstance(reply, str) else json.dumps(reply, ensure_ascii=False)


def _json(raw: str) -> Dict[str, Any]:
    m = re.search(r"\{.*\}", raw or "", re.S)
    try:
        return json.loads(m.group(0)) if m else {}
    except ValueError:
        return {}


# ---------------------------------------------------------------- 客服质检

def rule_issues(turns: List[Dict[str, Any]]) -> Dict[int, List[str]]:
    from agent.ec_skills.word_patrol import BAN, find, word_list
    words = {w: v for w, v in word_list().items() if v[1] == BAN and len(w) > 1}
    out: Dict[int, List[str]] = defaultdict(list)
    last: Dict[str, str] = {}
    for i, t in enumerate(turns):
        a = str(t.get("answer") or "").strip()
        if not a:
            out[i].append("没答")
        elif len(a) <= 20 and any(s in a for s in STALL):
            out[i].append("只说稍等")
        hits = [w for w, _, _ in find(a, words)]
        if hits:
            out[i].append("回复里有违禁词：" + "、".join(hits[:3]))
        cust = str(t.get("customer_id") or t.get("chat_id") or "")
        if a and cust and last.get(cust) == a:
            out[i].append("重复回复")
        last[cust] = a
    return out


_QUALITY_PROMPT = """你是电商客服主管，检查下面这些客服回复（每条是买家问题 Q 和客服回复 A）。
只列出有问题的条目，问题类型只能用：{issues}。
- 答非所问：回复和问题对不上；没答：没有回答问题本身；乱承诺：答应了店铺规则里不一定有的东西（赔偿、赠品、包退、指定时间到货）；
- 信息可能不对：回复里的尺码/材质/价格/发货时间像是编的或前后矛盾；态度：生硬、推脱、不礼貌；太长：买家一句话，回了一大段。
每条给 1-5 分（5 最好）和一句话说明。只输出 JSON：{{"items":[{{"no":序号,"score":分,"issues":["..."],"note":"..."}}]}}

{turns}"""


def grade(turns: List[Dict[str, Any]], ask: Callable[[str], str]) -> Dict[int, Dict[str, Any]]:
    out: Dict[int, Dict[str, Any]] = {}
    for b in range(0, len(turns), BATCH):
        part = turns[b:b + BATCH]
        body = "\n".join(f"{b + i + 1}. Q：{mask(t.get('question'), 150)}\n   A：{mask(t.get('answer'), 300)}"
                         for i, t in enumerate(part))
        try:
            got = _json(ask(_QUALITY_PROMPT.format(issues="、".join(ISSUES), turns=body)))
        except Exception as exc:
            logger.warning(f"[chat-review] grade batch {b}: {exc}")
            continue
        for it in got.get("items") or []:
            try:
                n = int(it.get("no")) - 1
            except (TypeError, ValueError):
                continue
            if b <= n < b + len(part):
                out[n] = {"score": it.get("score"), "issues": [x for x in it.get("issues") or [] if x in ISSUES],
                          "note": str(it.get("note") or "")[:120]}
    return out


def quality(turns: List[Dict[str, Any]], ask: Callable[[str], str], opts: Dict[str, Any]):
    rules = rule_issues(turns)
    model = grade(turns, ask)
    rows = []
    for i, t in enumerate(turns):
        issues = rules.get(i, []) + (model.get(i, {}).get("issues") or [])
        if not issues:
            continue
        rows.append({"时间": _when(t.get("created_at")), "商品ID": t.get("product_id") or "",
                     "买家问": mask(t.get("question")), "客服答": mask(t.get("answer"), 400),
                     "问题": "、".join(dict.fromkeys(issues)), "评分": model.get(i, {}).get("score", ""),
                     "说明": model.get(i, {}).get("note", "")})
    rows.sort(key=lambda r: (r["评分"] if isinstance(r["评分"], (int, float)) else 3))
    c = Counter(x.split("：")[0] for r in rows for x in r["问题"].split("、"))
    text = (f"{opts['days']} 天客服回复 {len(turns)} 条，有问题的 {len(rows)} 条（{len(rows) * 100 // max(1, len(turns))}%）："
            + "，".join(f"{k} {v}" for k, v in c.most_common()) + "。")
    for r in rows[:5]:
        text += f"\n- {r['问题']}：问「{r['买家问'][:24]}」答「{r['客服答'][:30]}」"
    if rows:
        text += "\n改法：答错的补进商品知识；乱承诺/违禁词的改客服提示词里的店铺规则。"
    return text, {"有问题的回复": rows, "统计": [{"问题": k, "条数": v} for k, v in c.most_common()]}


# ---------------------------------------------------------------- 客户之声

_TOPIC_PROMPT = """给下面每个买家问题标一个主题，主题只能从这些里选：{topics}。
只输出 JSON：{{"labels":[[序号,"主题"],...]}}

{questions}"""

_ADVICE_PROMPT = """你是电商运营。下面是本店最近 {days} 天买家咨询的主题统计和例子。
给 3-5 条具体建议：哪些信息该补进详情页/商品知识/自动回复，哪些问题说明商品或服务有毛病。
只根据这些数据，不要编造。只输出 JSON：{{"suggestions":["..."]}}

{stats}"""


def label(questions: List[str], ask: Callable[[str], str]) -> List[str]:
    out = ["其他"] * len(questions)
    for b in range(0, len(questions), 50):
        part = questions[b:b + 50]
        body = "\n".join(f"{b + i + 1}. {mask(q, 100)}" for i, q in enumerate(part))
        try:
            got = _json(ask(_TOPIC_PROMPT.format(topics="、".join(TOPICS), questions=body)))
        except Exception as exc:
            logger.warning(f"[chat-review] label batch {b}: {exc}")
            continue
        for pair in got.get("labels") or []:
            try:
                n, topic = int(pair[0]) - 1, str(pair[1])
            except (TypeError, ValueError, IndexError):
                continue
            if b <= n < b + len(part) and topic in TOPICS:
                out[n] = topic
    return out


def voice(turns: List[Dict[str, Any]], ask: Callable[[str], str], opts: Dict[str, Any]):
    turns = [t for t in turns if str(t.get("question") or "").strip()]
    labels = label([t["question"] for t in turns], ask)
    by: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for t, lb in zip(turns, labels):
        by[lb].append(t)
    rows = []
    for topic, ts in sorted(by.items(), key=lambda kv: -len(kv[1])):
        prods = Counter(str(t.get("product_id") or "") for t in ts if t.get("product_id"))
        rows.append({"主题": topic, "咨询数": len(ts), "占比": f"{len(ts) * 100 // max(1, len(turns))}%",
                     "问得多的商品ID": "、".join(p for p, _ in prods.most_common(3)),
                     "例子": " | ".join(mask(t["question"], 40) for t in ts[:4])})
    stats = "\n".join(f"{r['主题']} {r['咨询数']} 条（{r['占比']}），例：{r['例子']}" for r in rows)
    sugg: List[str] = []
    if rows:
        try:
            sugg = [str(s) for s in _json(ask(_ADVICE_PROMPT.format(days=opts["days"], stats=stats))).get("suggestions") or []][:5]
        except Exception as exc:
            logger.warning(f"[chat-review] advice: {exc}")
    text = f"{opts['days']} 天买家咨询 {len(turns)} 条，最多的：" + "，".join(f"{r['主题']} {r['咨询数']}" for r in rows[:5]) + "。"
    if sugg:
        text += "\n建议：" + "".join(f"\n{i}. {s}" for i, s in enumerate(sugg, 1))
    detail = [{"时间": _when(t.get("created_at")), "主题": lb, "商品ID": t.get("product_id") or "", "买家问": mask(t["question"]),
               "客服答": mask(t.get("answer"), 300)} for t, lb in zip(turns, labels)]
    return text, {"主题": rows, "明细": detail, "建议": [{"建议": s} for s in sugg]}


def run_for_store(kind: str, store_id: str, folder: str, opts: Optional[Dict[str, Any]] = None,
                  turns: Optional[List[Dict[str, Any]]] = None, ask: Optional[Callable[[str], str]] = None,
                  now: Optional[dt.datetime] = None) -> Dict[str, Any]:
    if kind not in NAMES:
        raise ValueError(f"unknown kind {kind!r}; one of {', '.join(NAMES)}")
    opts = dict(opts or {})
    opts["days"] = int(opts.get("days") or 7)
    name = NAMES[kind]
    turns = read_turns(store_id, opts["days"]) if turns is None else turns
    turns = turns[-int(opts.get("max_turns") or 600):]
    if not turns:
        return {"summary": f"{name}（{store_id}）：{opts['days']} 天内没有客服回复记录。", "path": "", "turns": 0}
    text, sheets = (quality if kind == "quality" else voice)(turns, ask or _ask, opts)
    from agent.ec_skills.store_reports import write_xlsx
    stamp = (now or dt.datetime.now()).strftime("%Y%m%d_%H%M")
    path = write_xlsx(sheets, os.path.join(folder, "结果", f"{name}_{stamp}.xlsx")) if any(sheets.values()) else ""
    logger.info(f"[chat-review] {kind} {store_id} turns={len(turns)} path={bool(path)}")
    return {"summary": f"{name}（{store_id}）：" + text, "path": path, "turns": len(turns)}
