"""The explorer loop: a strong model works a page problem the way an engineer
works a bug -- it keeps its whole history, reasons between actions, calls several
tools a turn, looks at screenshots, and stops only with a verified recipe or a
precise findings note.

Each turn the model answers one JSON object::

    {"thinking": "...", "calls": [{"tool": "snapshot", "args": {...}}, ...], "done": null}

The calls run in order and every result (screenshots as images) goes back into
the conversation. ``done`` (an object) ends the run; it is the explore node's
final answer (see experience.explore_prompt for its shape).
"""
from __future__ import annotations

import asyncio
import contextvars
import json
import re
import threading
from typing import Any, Dict, List, Optional

from utils.logger_helper import logger_helper as logger

from .page import PageSession, browser_port
from .tools import TOOLS, tool_docs

MAX_CALLS_PER_TURN = 8
HISTORY_CHARS = 360_000          # older tool results are elided above this (Opus keeps ~200K tokens)
KEEP_RECENT_RESULTS = 8

SYSTEM = """你是一位资深前端工程师，正在用浏览器调试工具排查一个电商商家后台页面上的问题。你通过下面的工具操作一个已经登录的真实页面。

工具：
{tools}

工作方式（和你平时调试代码一样）：
- 先看清楚再动手：snapshot / screenshot / run_js / network 都是只读的，多用。
- 每一轮先在 thinking 里写下你现在知道什么、怀疑什么、下一步要验证什么；然后一次给出这一轮要做的几个工具调用（最多 {max_calls} 个，按顺序执行）。会改变页面的调用（click、type、write_form_field）放在这一轮的最后，下一轮看了结果再继续。
- 所有工具的结果都会原样回到对话里，你能一直看到之前做过的所有实验，不要重复已经做过、结果已知的实验。
- 只做实验：不能发布、提交、保存、存草稿，不能报名、推广、充值、开通（这些按钮会被拒绝）。写进页面数据的测试值做完要改回。

每一轮只回答一个 JSON 对象，不要别的文字：
{{"thinking": "推理", "calls": [{{"tool": "工具名", "args": {{...}}}}], "done": null}}
任务完成时 calls 为空，done 填任务要求的那个 JSON 对象。"""


def _parse(text: str) -> Optional[dict]:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        out = json.loads(m.group(0), strict=False)
    except Exception:
        return None
    return out if isinstance(out, dict) else None


def _elide(messages: List[Any]) -> None:
    """Keep the conversation under HISTORY_CHARS: older tool results become a stub
    (the model's own reasoning about them stays)."""
    from langchain_core.messages import HumanMessage
    size = lambda m: len(json.dumps(m.content, ensure_ascii=False, default=str))
    results = [i for i, m in enumerate(messages) if isinstance(m, HumanMessage) and i > 1]
    total = sum(size(m) for m in messages)
    for i in results[:-KEEP_RECENT_RESULTS]:
        if total <= HISTORY_CHARS:
            break
        total -= size(messages[i])
        messages[i] = HumanMessage(content="（较早的工具结果已省略；你当时的结论在上一轮 thinking 里）")
        total += size(messages[i])


async def explore(task: str, *, store_id: str = "", profile_id: str = "", start_url: str, reuse_tab: str = "",
                  domains: List[str], model: str = "claude-opus-5-5", max_turns: int = 60,
                  llm: Any = None) -> Dict[str, Any]:
    """Run one exploration. Returns {"final": str, "turns": n, "calls": n, "error": str}."""
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
    port = browser_port(store_id, profile_id)
    if not port:
        return {"final": "", "turns": 0, "calls": 0, "error": f"no running browser for store {store_id or profile_id}"}
    if llm is None:
        from agent.ec_skills.llm_utils.llm_utils import create_ecanai_chat_llm
        llm = create_ecanai_chat_llm(model, temperature=0.0, media=True)
    page = await PageSession.open(port, start_url, reuse_tab)
    ctx = {"domains": domains}
    messages: List[Any] = [SystemMessage(content=SYSTEM.format(tools=tool_docs(), max_calls=MAX_CALLS_PER_TURN)),
                           HumanMessage(content=task + "\n\n（你现在在 " + await page.url() + "）")]
    calls = 0
    try:
        for turn in range(1, max_turns + 1):
            reply = await llm.ainvoke(messages)
            text = reply.content if isinstance(reply.content, str) else json.dumps(reply.content, ensure_ascii=False)
            messages.append(AIMessage(content=text))
            step = _parse(text)
            if step is None:
                messages.append(HumanMessage(content="你的回答不是一个 JSON 对象。按约定格式重新回答这一轮。"))
                continue
            logger.info(f"[explorer] turn {turn}: {str(step.get('thinking') or '')[:300]}")
            if step.get("done") and not step.get("calls"):
                done = step["done"]
                return {"final": done if isinstance(done, str) else json.dumps(done, ensure_ascii=False),
                        "turns": turn, "calls": calls, "error": ""}
            parts: List[Dict[str, Any]] = []
            for k, call in enumerate((step.get("calls") or [])[:MAX_CALLS_PER_TURN], 1):
                name = str((call or {}).get("tool") or "")
                args = (call or {}).get("args") or {}
                entry = TOOLS.get(name)
                if entry is None:
                    parts.append({"type": "text", "text": f"[{k}] {name}: 没有这个工具"})
                    continue
                try:
                    out, image = await entry[1](page, args if isinstance(args, dict) else {}, ctx)
                except Exception as exc:
                    out, image = f"出错：{type(exc).__name__}: {exc}", None
                calls += 1
                logger.info(f"[explorer] turn {turn} call {k}: {name} {json.dumps(args, ensure_ascii=False)[:160]} -> {str(out)[:160]}")
                parts.append({"type": "text", "text": f"[{k}] {name}({json.dumps(args, ensure_ascii=False)[:300]})\n{out}"})
                if image:
                    parts.append({"type": "image_url", "image_url": {"url": "data:image/png;base64," + image}})
            if not parts:
                parts = [{"type": "text", "text": "这一轮没有工具调用也没有 done。继续，或者用 done 交付。"}]
            parts.append({"type": "text", "text": f"（第 {turn}/{max_turns} 轮；现在在 {await page.url()}）"})
            messages.append(HumanMessage(content=parts))
            _elide(messages)
        return {"final": "", "turns": max_turns, "calls": calls, "error": "used all turns without done"}
    finally:
        await page.close()


def explore_sync(task: str, **kwargs) -> Dict[str, Any]:
    """Run ``explore`` from synchronous code (a skill's code node), in its own event
    loop and thread, keeping the caller's run scope (attribution, billing flags)."""
    ctx = contextvars.copy_context()
    box: Dict[str, Any] = {}

    def run():
        try:
            box["out"] = ctx.run(lambda: asyncio.run(explore(task, **kwargs)))
        except Exception as exc:
            logger.warning(f"[explorer] failed: {type(exc).__name__}: {exc}")
            box["out"] = {"final": "", "turns": 0, "calls": 0, "error": f"{type(exc).__name__}: {exc}"}
    th = threading.Thread(target=run, name="explorer", daemon=True)
    th.start()
    th.join()
    return box["out"]
