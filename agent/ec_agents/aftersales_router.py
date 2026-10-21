"""After-sales routing for a chat front desk (售后前台, chat side).

Pre-sales and after-sales messages arrive in the same platform chat page, which
one front desk watches. Before the front desk picks a Q&A agent for a buyer
turn, it asks this module which part of its pool may take it:

- The pool's 售后 agents are the members with a task whose name carries
  ``ECAN_AFTERSALES_TASK_MARK`` (default "售后", e.g. 「售后应答001」).
  No 售后 member -> nothing changes (the feature is dormant).
- A buyer with an OPEN case goes to the case's owner, and only to it -- one
  售后 agent handles all of one customer's messages until the case closes
  (closes after ``ECAN_AFTERSALES_CASE_IDLE_H`` hours without a message, or by
  ``close_case``).
- Otherwise a turn that reads as after-sales (a problem with an order:
  damaged / wrong / missing item, not working, I want a return / refund ...)
  goes to the 售后 members, and the member picked becomes the case owner
  (``claim``). Every other turn goes to the non-售后 members, as before.

Cases are kept on disk, so a case survives a restart. The platform's own 售后单
stays the status source of truth; this is only who owns the conversation.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from utils.logger_helper import logger_helper as logger

_LOCK = threading.Lock()
_cases: Dict[str, Dict[str, Any]] = {}      # "front_desk|customer" -> {"agent", "opened", "last", "reason"}
_loaded = [False]

# Something went wrong with an order the buyer already has, or they ask to
# undo it. Policy questions BEFORE buying ("可以退货吗" / "支持七天无理由吗") stay
# with 客服: they are answered from the store rules and open no case.
_AFTERSALES = re.compile(
    r"(破损|破了|坏了|损坏|摔坏|压坏|漏液|漏了|发错|错发|少发|漏发|少件|少了|缺件|不能用|用不了|"
    r"开不了机|不工作|没反应|质量问题|有问题|开线|起球了|缩水了|掉色了|褪色了|色差|货不对板|与描述不符|"
    r"假货|没收到|未收到|丢件|快递丢|拒收|退回去了|寄回|已寄回|退货单|售后|投诉|差评|"
    r"(我要|我想|想要|申请|帮我|怎么|如何)(退货|退款|换货|退换|补发|换一个|退了)|"
    r"(退货|退款|换货|补发)(吧|一下|呢|怎么弄|怎么办))")
_PRESALES_POLICY = re.compile(r"(可以|能|能不能|可不可以|支持|有没有|包不包)[^，。？?!！]{0,8}(退|换|七天|无理由|运费险)[^，。]{0,6}[吗嘛么？?]")


def is_aftersales(text: str) -> bool:
    """True if *text* reads as an after-sales turn (see module doc)."""
    t = "".join(str(text or "").split())
    if not t or _PRESALES_POLICY.search(t) and not re.search(r"(破|坏|错|少|漏|不能用|质量|收到)", t):
        return False
    return bool(_AFTERSALES.search(t))


def _mark() -> str:
    return os.environ.get("ECAN_AFTERSALES_TASK_MARK", "售后").strip() or "售后"


def _idle_s() -> float:
    try:
        return float(os.environ.get("ECAN_AFTERSALES_CASE_IDLE_H", "72")) * 3600
    except Exception:
        return 72 * 3600.0


def _path() -> str:
    from config.app_info import app_info
    return os.path.join(app_info.appdata_path, "aftersales_cases.json")


def _load() -> None:
    if _loaded[0]:
        return
    _loaded[0] = True
    try:
        with open(_path(), encoding="utf-8") as f:
            _cases.update(json.load(f) or {})
    except Exception:
        pass


def _save() -> None:
    try:
        with open(_path(), "w", encoding="utf-8") as f:
            json.dump(_cases, f, ensure_ascii=False)
    except Exception as exc:
        logger.warning(f"[aftersales] could not save cases: {exc}")


def _key(front_desk_id: str, customer: str) -> str:
    return f"{front_desk_id}|{customer}"


def _task_names(agent_id: str, lookup: Callable[[str], Any]) -> List[str]:
    agent = lookup(agent_id)
    return [str(getattr(t, "name", "") or "") for t in list(getattr(agent, "tasks", None) or [])]


def _default_lookup(agent_id: str):
    try:
        from agent.agent_service import get_agent_by_id
        return get_agent_by_id(agent_id)
    except Exception:
        return None


def open_case(front_desk_id: str, customer: str) -> Optional[Dict[str, Any]]:
    """The buyer's open case at this front desk, or None."""
    now = time.time()
    with _LOCK:
        _load()
        case = _cases.get(_key(front_desk_id, customer))
        if case and now - float(case.get("last") or 0) > _idle_s():
            _cases.pop(_key(front_desk_id, customer), None)
            _save()
            logger.info(f"[aftersales] case of {customer!r} closed after "
                        f"{_idle_s() / 3600:.0f} h without a message")
            return None
        return dict(case) if case else None


def route(front_desk_id: str, customer: str, text: str, candidate_ids: List[str],
          has_media: bool = False, lookup: Optional[Callable[[str], Any]] = None) -> Tuple[List[str], str]:
    """(the pool members that may take this turn, why). Why is "" when nothing
    changed, "aftersales:case" (the case owner), "aftersales:new" (a 售后 member
    -- call ``claim`` with the one picked), "presales" (the non-售后 members)."""
    ids = [str(c) for c in candidate_ids or [] if c]
    if not ids or not customer:
        return ids, ""
    lookup = lookup or _default_lookup
    mark = _mark()
    try:
        after = [a for a in ids if any(mark in n for n in _task_names(a, lookup))]
    except Exception as exc:
        logger.debug(f"[aftersales] task lookup failed: {exc}")
        return ids, ""
    if not after:
        return ids, ""                               # no 售后 agents: dormant
    others = [a for a in ids if a not in after] or ids
    case = open_case(front_desk_id, customer)
    if case:
        with _LOCK:
            live = _cases.get(_key(front_desk_id, customer))
            if live:
                live["last"] = time.time()
                _save()
        owner = case.get("agent", "")
        if owner in after:
            return [owner], "aftersales:case"
        logger.warning(f"[aftersales] case owner {owner[-8:]!r} of {customer!r} is not in the pool "
                       f"any more; another 售后 agent takes the case")
        return after, "aftersales:new"
    if is_aftersales(text):
        return after, "aftersales:new"
    return others, "presales"


def claim(front_desk_id: str, customer: str, agent_id: str, text: str = "") -> None:
    """*agent_id* now owns *customer*'s case at this front desk."""
    if not (front_desk_id and customer and agent_id):
        return
    now = time.time()
    with _LOCK:
        _load()
        prev = _cases.get(_key(front_desk_id, customer)) or {}
        _cases[_key(front_desk_id, customer)] = {
            "agent": agent_id, "opened": prev.get("opened") or now, "last": now,
            "reason": prev.get("reason") or str(text or "")[:80]}
        _save()
    if not prev:
        logger.info(f"[aftersales] case opened: customer={customer!r} -> agent ...{agent_id[-8:]} "
                    f"({str(text or '')[:40]!r})")


def close_case(front_desk_id: str, customer: str) -> bool:
    with _LOCK:
        _load()
        gone = _cases.pop(_key(front_desk_id, customer), None) is not None
        if gone:
            _save()
    if gone:
        logger.info(f"[aftersales] case closed: customer={customer!r}")
    return gone


def cases() -> Dict[str, Dict[str, Any]]:
    with _LOCK:
        _load()
        return {k: dict(v) for k, v in _cases.items()}
