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

from agent.ec_tasks.progress import note_task_progress
from utils.logger_helper import logger_helper as logger

from .page import PageSession, browser_port
from .tools import TOOLS, foreign_record, tool_docs

MAX_CALLS_PER_TURN = 8
HISTORY_CHARS = 360_000          # older tool results are elided above this (Opus keeps ~200K tokens)
KEEP_RECENT_RESULTS = 8
IMAGE_CHARS = 6_000              # a screenshot as the model sees it
GIST_CHARS = 200                 # what an elided tool result keeps of each call
MAX_BAD_REPLIES = 3              # replies in a row outside the protocol end the run (KEN 10-31: 60 paid turns, 0 calls)
MAX_OUTPUT_TOKENS = 16_000
LLM_TIMEOUT_SEC = 240            # one model reply; a call that never came back froze run 72 (KEN 11-01)

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
    """The first JSON object in *text* that is a turn ({"thinking"/"calls"/"done"}).
    Text before or after it (a code fence, a note, a second object) is ignored:
    one greedy {...} match spanning two objects failed every turn."""
    decoder = json.JSONDecoder(strict=False)
    text = text or ""
    for m in re.finditer(r"\{", text):
        try:
            out, _ = decoder.raw_decode(text, m.start())
        except ValueError:
            continue
        if isinstance(out, dict) and ({"thinking", "calls", "done"} & set(out)):
            return out
    return None


def _text(content: Any) -> str:
    """A reply's text; content blocks (a list) are joined, non-text blocks dropped."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(p if isinstance(p, str) else str(p.get("text") or "") for p in content
                       if isinstance(p, str) or (isinstance(p, dict) and p.get("type") in (None, "text")))
    return str(content or "")


def _meta(reply: Any) -> str:
    md = getattr(reply, "response_metadata", None) or {}
    use = md.get("token_usage") or {}
    return (f"model={md.get('model_name') or md.get('model') or '?'} finish={md.get('finish_reason') or '?'} "
            f"in={use.get('prompt_tokens', '?')} out={use.get('completion_tokens', '?')}")


def _elide(messages: List[Any]) -> None:
    """Keep the conversation under HISTORY_CHARS: older tool results become a stub
    (the model's own reasoning about them stays)."""
    from langchain_core.messages import HumanMessage
    total = sum(_size(m.content) for m in messages)
    results = [i for i, m in enumerate(messages) if isinstance(m, HumanMessage) and i > 1]
    for i in results[:-KEEP_RECENT_RESULTS]:
        if total <= HISTORY_CHARS:
            break
        total -= _size(messages[i].content)
        messages[i] = HumanMessage(content="（较早的工具结果已省略，开头是：）\n" + _gist(messages[i].content)
                                   + "\n（你当时的结论在上一轮 thinking 里）")
        total += _size(messages[i].content)


def _size(content: Any) -> int:
    """What a message costs the model, in characters: a screenshot counts as what
    the model pays for it (~1.6K tokens), not its base64 length (two screenshots
    used to push out every older result)."""
    if isinstance(content, list):
        return sum(IMAGE_CHARS if isinstance(p, dict) and p.get("type") == "image_url" else _size(p.get("text", "") if isinstance(p, dict) else p)
                   for p in content)
    return len(str(content or ""))


def _gist(content: Any) -> str:
    texts = [p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"] if isinstance(content, list) else [str(content or "")]
    return "\n".join(t[:GIST_CHARS] for t in texts if t)[:GIST_CHARS * 4]


async def _leave_foreign_record(page: Any, ctx: Dict[str, Any], out: Any) -> Any:
    """A click (or anything else) that landed on another record's page goes straight
    back: its edit page may autosave whatever happens next."""
    try:
        here = await page.url()
    except Exception:
        return out
    rid = foreign_record(here, ctx)
    if not rid:
        return out
    try:
        await page.evaluate("history.back()", 5)
        await asyncio.sleep(2)
        back = await page.url()
    except Exception as exc:
        back = f"?（{type(exc).__name__}）"
    logger.warning(f"[explorer] left foreign record {rid} ({here[:120]}) -> {back[:120]}")
    return f"{out}\n拒绝：这一步打开了别的商品/记录（{rid}），已经退回到 {back}。只在这次任务自己的页面上实验。"


async def explore(task: str, *, store_id: str = "", profile_id: str = "", start_url: str, reuse_tab: str = "",
                  domains: List[str], model: str = "claude-opus-5-5", max_turns: int = 60,
                  llm: Any = None, own_ids: Optional[List[str]] = None,
                  files: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Run one exploration. Returns {"final": str, "turns": n, "calls": n, "error": str}.

    *own_ids*: records (product ids...) this run made; no other record page is opened.
    *files*: name -> local path of the files the ``upload`` tool may use."""
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
    port = browser_port(store_id, profile_id)
    if not port:
        return {"final": "", "turns": 0, "calls": 0, "error": f"no running browser for store {store_id or profile_id}"}
    if llm is None:
        from agent.ec_skills.llm_utils.llm_utils import create_ecanai_chat_llm
        llm = create_ecanai_chat_llm(model, temperature=0.0, media=True)
        llm.max_tokens = MAX_OUTPUT_TOKENS
    page = await PageSession.open(port, start_url, reuse_tab)
    ctx = {"domains": domains, "own_ids": [str(x) for x in own_ids or []], "files": dict(files or {})}
    here = await page.url()
    logger.info(f"[explorer] start model={model} port={port} reused_tab={not getattr(page, 'owned', True)} url={here[:160]} task_chars={len(task)}")
    messages: List[Any] = [SystemMessage(content=SYSTEM.format(tools=tool_docs(), max_calls=MAX_CALLS_PER_TURN)),
                           HumanMessage(content=task + "\n\n（你现在在 " + here + "）")]
    calls = bad = 0
    try:
        for turn in range(1, max_turns + 1):
            # A turn is a sign of life: without it the runner cleared a busy exploration
            # as hung at 300 s (拼多多 run 73, KEN 11-01).
            note_task_progress()
            try:
                reply = await asyncio.wait_for(llm.ainvoke(messages), LLM_TIMEOUT_SEC)
            except asyncio.TimeoutError:
                bad += 1
                logger.warning(f"[explorer] turn {turn}: no reply in {LLM_TIMEOUT_SEC} s ({bad}/{MAX_BAD_REPLIES})")
                if bad >= MAX_BAD_REPLIES:
                    return {"final": "", "turns": turn, "calls": calls, "error": f"the model did not reply {bad} times in a row"}
                continue
            text = _text(reply.content)
            messages.append(AIMessage(content=text))
            step = _parse(text)
            if step is None:
                bad += 1
                logger.warning(f"[explorer] turn {turn}: reply outside the protocol ({bad}/{MAX_BAD_REPLIES}) {_meta(reply)} "
                               f"chars={len(text)} head={text[:400]!r} tail={text[-200:]!r}")
                if bad >= MAX_BAD_REPLIES:
                    return {"final": "", "turns": turn, "calls": calls,
                            "error": f"{bad} replies in a row were not a JSON turn; last began {text[:200]!r}"}
                messages.append(HumanMessage(content=(
                    "你的回答里没有找到一个合法的 JSON 对象（要有 thinking、calls、done 三个键）。只回答一个 JSON 对象，"
                    "不要代码块标记，不要在它后面写别的内容，也不要替工具写结果——结果由我执行后发给你。")))
                continue
            bad = 0
            logger.info(f"[explorer] turn {turn} ({_meta(reply)}): {str(step.get('thinking') or '')[:300]}")
            if step.get("done") and not step.get("calls"):
                done = step["done"]
                logger.info(f"[explorer] done after {turn} turns, {calls} calls")
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
                out = await _leave_foreign_record(page, ctx, out)
                calls += 1
                logger.info(f"[explorer] turn {turn} call {k}: {name} {json.dumps(args, ensure_ascii=False)[:160]} -> {str(out)[:160]}")
                parts.append({"type": "text", "text": f"[{k}] {name}({json.dumps(args, ensure_ascii=False)[:300]})\n{out}"})
                if image:
                    parts.append({"type": "image_url", "image_url": {"url": "data:image/png;base64," + image}})
            if not parts:
                parts = [{"type": "text", "text": "这一轮没有工具调用也没有 done。继续，或者用 done 交付。"}]
            try:
                here = await page.url()
            except Exception as exc:          # a wedged page is news for the model, not the end of the run
                here = f"（页面没有响应：{type(exc).__name__}）"
            parts.append({"type": "text", "text": f"（第 {turn}/{max_turns} 轮；现在在 {here}）"})
            messages.append(HumanMessage(content=parts))
            _elide(messages)
        logger.warning(f"[explorer] used all {max_turns} turns without done ({calls} calls)")
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
