"""Unexpected dialogs in a desktop app the agent drives (千牛 first), resolved by
an LLM instead of hard-coded RPA rules that break when the app rewords or
restyles a dialog.

    resolve(platform, lines, screenshot_path, doing, act, reread, builtin=())

1. A learned rule (a dialog handled before: its distinctive texts -> action)
   is applied instantly, no model call.
2. Otherwise the OCR lines (text + position) go to a fast text model through the
   eCan llm-proxy. It answers in JSON: is something blocking, what is it, which
   action -- and whether it needs to SEE the screen; only then is the
   screenshot sent to a vision model.
3. The action is checked in code before it runs: a click only on text OCR
   actually sees, never on a forbidden button (send / pay / refund / delete ...,
   or the composer's own 发送/关闭), at most one action per call.
4. A dialog that is gone after the action becomes a learned rule.

Never escalates to a human: an unresolved dialog is logged loudly and the
caller carries on (Esc was tried, the next failure asks again).
Models: ECAN_UI_OBSTACLE_MODEL (text), ECAN_UI_OBSTACLE_VISION_MODEL.
"""
from __future__ import annotations

import base64
import json
import os
import re
import threading
import time
from typing import Callable, Dict, List, Optional

from utils.logger_helper import logger_helper as logger

# qwen-flash: 3 s and right on a reworded 千牛 refusal; qwen3.8-flash was as right
# but took 37 s (it reasons first), deepseek-v4-flash missed the refusal (2026-10-19).
TEXT_MODEL = os.environ.get("ECAN_UI_OBSTACLE_MODEL", "qwen-flash")
VISION_MODEL = os.environ.get("ECAN_UI_OBSTACLE_VISION_MODEL", "qwen3-vl-plus")
# Buttons the agent must never press to get rid of a dialog, whatever a model says.
FORBIDDEN = ("发送", "付款", "支付", "确认收货", "删除", "退款", "同意退款", "举报", "拉黑", "投诉",
             "注销", "退出登录", "解绑", "结束会话")
_RULES_LOCK = threading.Lock()


def _rules_path() -> str:
    from config.app_info import app_info
    d = os.path.join(app_info.appdata_path, "ui_obstacles")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "rules.json")


def _load_rules() -> List[dict]:
    try:
        with open(_rules_path(), encoding="utf-8") as f:
            return json.load(f) or []
    except Exception:
        return []


def _save_rule(rule: dict) -> None:
    with _RULES_LOCK:
        rules = [r for r in _load_rules()
                 if not (r.get("platform") == rule["platform"] and r.get("match") == rule["match"])]
        rules.append(rule)
        try:
            with open(_rules_path(), "w", encoding="utf-8") as f:
                json.dump(rules[-200:], f, ensure_ascii=False, indent=1)
        except Exception as e:
            logger.warning(f"[ui-obstacle] could not save the learned rule: {e}")


def _texts(lines: List[dict]) -> List[str]:
    return [str(it.get("text") or "").strip() for it in lines or [] if str(it.get("text") or "").strip()]


def match_rule(platform: str, lines: List[dict], builtin=()) -> Optional[dict]:
    """A learned (or *builtin*, shipped) rule whose every distinctive text is on screen."""
    texts = _texts(lines)
    for rule in list(builtin) + list(reversed(_load_rules())):
        if rule.get("platform") == platform and rule.get("match") and \
                all(any(m in t for t in texts) for m in rule["match"]):
            return rule
    return None


_PROMPT = """You watch a desktop app ({platform}) that an automation agent operates for an online store.
The agent was trying to: {doing}
That step failed. Below is everything OCR read on the app window, one line per text: text @(x,y), window size {w}x{h}.

Decide if a dialog, popup, banner or overlay is in the way of the chat, and how to get rid of it.
Answer ONLY a JSON object:
{{"blocking": true|false,
  "kind": "reply_refused" | "notice" | "confirm" | "login_or_verify" | "ad" | "other" | "none",
  "summary": "<what it says, short, in Chinese>",
  "action": "click" | "esc" | "none",
  "button": "<the exact visible text of the button to click, if action=click>",
  "clear_reply_box": true|false,
  "refused_reason": "<if the app refused the agent's message: why, in Chinese>",
  "match": ["<2-3 short distinctive texts that identify THIS dialog>"],
  "need_vision": true|false,
  "close_xy": [x, y],
  "popup_box": [x1, y1, x2, y2]}}
close_xy / popup_box: ONLY if you can see the image and the popup has no text button, just an
icon (×): action="click_xy", close_xy = the center of that × in IMAGE pixels, popup_box = the
popup's outline in IMAGE pixels. Never the app window's own ×/minimize in its top-right corner.
Rules: prefer the button that closes / goes back / acknowledges (返回修改, 我知道了, 关闭 on the dialog, 取消, 确定 for a notice).
Never pick a button that sends, pays, refunds, deletes, reports or logs out. If a text button closes it,
use action="click" with that text, not click_xy. If the app refused the agent's
message, set clear_reply_box=true. Set need_vision=true ONLY if the text alone is not enough to tell
(e.g. an icon-only button). If nothing is blocking, blocking=false, action="none".

OCR lines:
{lines}"""


def _format_lines(lines: List[dict]) -> tuple:
    out, w, h = [], 0, 0
    for it in lines or []:
        lc, t = it.get("loc"), str(it.get("text") or "").strip()
        if not lc or not t:
            continue
        y1, x1, y2, x2 = lc
        w, h = max(w, x2), max(h, y2)
        out.append((int((y1 + y2) / 2), int((x1 + x2) / 2), t))
    out.sort()
    return "\n".join(f"{t} @({x},{y})" for y, x, t in out[:220]), w, h


def _ask(model: str, prompt: str, image_path: str = "") -> dict:
    from langchain_core.messages import HumanMessage
    from agent.ec_skills.llm_utils.llm_utils import create_ecanai_chat_llm
    llm = create_ecanai_chat_llm(model, temperature=0.0)
    if image_path:
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        ext = "png" if image_path.lower().endswith(".png") else "jpeg"
        content = [{"type": "text", "text": prompt},
                   {"type": "image_url", "image_url": {"url": f"data:image/{ext};base64,{b64}"}}]
    else:
        content = prompt
    reply = llm.invoke([HumanMessage(content=content)]).content
    text = reply if isinstance(reply, str) else json.dumps(reply, ensure_ascii=False)
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0)) if m else {}


def _vet(decision: dict, lines: List[dict], h: int) -> Optional[str]:
    """Why this action must not run, or None when it may."""
    action = decision.get("action")
    if action not in ("click", "esc", "none", "click_xy"):
        return f"unknown action {action!r}"
    if action == "click_xy":
        return None if decision.get("_via") == "vision" else "a position needs the vision model (it saw the image)"
    if action != "click":
        return None
    button = str(decision.get("button") or "").strip()
    if not button:
        return "click without a button text"
    if any(f in button for f in FORBIDDEN):
        return f"button {button!r} is on the never-press list"
    hits = [it for it in lines or [] if button in str(it.get("text") or "") and it.get("loc")]
    if not hits:
        return f"button {button!r} is not on screen"
    if button in ("关闭",) and all((it["loc"][0] + it["loc"][2]) / 2 > 0.85 * h for it in hits):
        return "'关闭' at the bottom is the reply box's own button (it closes the chat)"
    return None


def resolve(platform: str, lines: List[dict], screenshot_path: str, doing: str,
            act: Dict[str, Callable], reread: Callable[[], List[dict]], builtin=(),
            use_model: bool = True, allow_esc: bool = True) -> dict:
    """Try to clear what is blocking *platform*'s window. *act* has 'click'(x, y),
    'esc'(), 'clear_reply_box'(); *reread*() returns fresh OCR lines.
    use_model=False: rules only (cheap enough for every screen read).
    allow_esc=False: the app treats Esc as an action (千牛: closes the chat), so
    Esc is never pressed and a refused / unavailable decision does nothing.
    Returns {"resolved": bool, "kind", "summary", "refused_reason", "via": rule|llm|vision|none}."""
    t0 = time.monotonic()
    rule = match_rule(platform, lines, builtin)
    if rule:
        decision, via = dict(rule["action"]), "rule"
    elif not use_model:
        return {"resolved": False, "kind": None, "summary": None, "refused_reason": "", "via": "none"}
    else:
        text, w, h = _format_lines(lines)
        try:
            decision, via = _ask(TEXT_MODEL, _PROMPT.format(platform=platform, doing=doing, w=w, h=h,
                                                             lines=text)), "llm"
            if decision.get("need_vision") and screenshot_path and os.path.exists(screenshot_path):
                logger.info(f"[ui-obstacle] {platform}: text model asked to see the screen; using {VISION_MODEL}")
                decision, via = _ask(VISION_MODEL, _PROMPT.format(platform=platform, doing=doing, w=w, h=h,
                                                                  lines=text), screenshot_path), "vision"
        except Exception as e:
            logger.warning(f"[ui-obstacle] {platform}: model call failed ({e}); "
                           f"{'pressing Esc' if allow_esc else 'leaving the screen as it is'}")
            decision, via = {"blocking": True, "action": "esc" if allow_esc else "none",
                             "summary": "model unavailable"}, "none"
    out = {"resolved": False, "kind": decision.get("kind"), "summary": decision.get("summary"),
           "refused_reason": decision.get("refused_reason") or "", "via": via}
    if not decision.get("blocking") and via != "rule":
        logger.info(f"[ui-obstacle] {platform}: nothing blocking per {via} ({doing})")
        return out
    _, _w, h = _format_lines(lines)
    decision["_via"] = via
    why_not = _vet(decision, lines, h)
    if not why_not and decision.get("action") == "click_xy":
        vet_xy = act.get("vet_xy")
        why_not = ("this app takes no positions" if vet_xy is None
                   else vet_xy(decision.get("close_xy"), decision.get("popup_box"), lines))
    if why_not:
        logger.warning(f"[ui-obstacle] {platform}: refused the {via} action {decision} ({why_not}); "
                       f"{'pressing Esc' if allow_esc else 'leaving the screen as it is'}")
        decision = {"action": "esc" if allow_esc else "none"}
    if decision.get("action") == "esc" and not allow_esc:
        logger.warning(f"[ui-obstacle] {platform}: the model chose Esc, which this app treats as an action; "
                       f"not pressing it")
        decision = dict(decision, action="none")
    if decision.get("action") == "none":
        return out
    if decision.get("action") == "click":
        hit = next(it for it in lines if str(decision["button"]).strip() in str(it.get("text") or "")
                   and it.get("loc"))
        y1, x1, y2, x2 = hit["loc"]
        act["click"](int((x1 + x2) / 2), int((y1 + y2) / 2))
    elif decision.get("action") == "click_xy":
        act["click_xy"](*decision["close_xy"][:2])
    elif decision.get("action") == "esc":
        act["esc"]()
    time.sleep(0.6)
    if decision.get("clear_reply_box"):
        try:
            act["clear_reply_box"]()
        except Exception as e:
            logger.warning(f"[ui-obstacle] {platform}: could not clear the reply box: {e}")
    after = _texts(reread())
    match = [m for m in (decision.get("match") or (rule or {}).get("match") or []) if m][:3]
    gone = bool(match) and not all(any(m in t for t in after) for m in match)
    out["resolved"] = gone or (not match and decision.get("action") != "none")
    level = logger.info if out["resolved"] else logger.error
    level(f"[ui-obstacle] {platform}: {decision.get('kind')} '{decision.get('summary')}' -> "
          f"{decision.get('action')} {decision.get('button') or ''} via {via}: "
          f"{'cleared' if out['resolved'] else 'STILL THERE (carrying on; the next failure asks again)'}"
          f"{(' -- refused: ' + out['refused_reason']) if out['refused_reason'] else ''} "
          f"[{int((time.monotonic() - t0) * 1000)}ms]")
    if gone and via in ("llm", "vision") and decision.get("action") != "click_xy":   # positions move
        _save_rule({"platform": platform, "match": match, "learned": time.strftime("%Y-%m-%d %H:%M"),
                    "summary": decision.get("summary"),
                    "action": {k: decision.get(k) for k in ("blocking", "kind", "summary", "action", "button",
                                                            "clear_reply_box", "refused_reason")}})
    return out


_REWRITE_PROMPT = """你是网店客服。你刚发给买家的回复被平台拦截了。
买家的消息：{question}
被拦截的回复：{reply}
平台给出的原因：{reason}

请重写这条回复，避开拦截原因：直接回应买家的消息，不要用"有什么可以帮您"之类的开场白；
不知道的信息不要编造，可以请买家补充具体信息（如商品、尺码、订单）。语气礼貌简洁，不超过60个字。
只输出重写后的回复本身。"""


def rewrite_refused(question: str, reply: str, reason: str) -> str:
    """One rewrite of a reply the platform refused, for the stated reason, via
    the llm-proxy text model. "" when it fails or comes back unchanged."""
    try:
        from langchain_core.messages import HumanMessage
        from agent.ec_skills.llm_utils.llm_utils import create_ecanai_chat_llm
        llm = create_ecanai_chat_llm(TEXT_MODEL, temperature=0.3)
        text = llm.invoke([HumanMessage(content=_REWRITE_PROMPT.format(
            question=question or "（未知）", reply=reply, reason=reason or "（未说明）"))]).content
        text = (text if isinstance(text, str) else "").strip().strip('"“”')
    except Exception as e:
        logger.warning(f"[ui-obstacle] rewrite of a refused reply failed: {e}")
        return ""
    return "" if not text or text == reply.strip() else text[:300]
