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
from .tools import RECORD_ID, TOOLS, foreign_record, tool_docs

MAX_CALLS_PER_TURN = 8
COMPACT_AT_CHARS = 200_000       # above this the older turns are compacted into a progress summary
KEEP_RECENT_TURNS = 4            # turns (reply + results) kept whole after a compaction
SUMMARY_SOURCE_CHARS = 160_000   # the transcript a summary is written from (its tail)
HISTORY_CHARS = 360_000          # last resort if a compaction fails: older tool results are elided
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
- 所有工具的结果都会原样回到对话里，你能一直看到之前做过的实验，不要重复已经做过、结果已知的实验。对话太长时，较早的轮次会被压缩成一份进展摘要，放在任务后面：摘要里的事实就是你之前亲眼确认过的。
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


SUMMARY_SYSTEM = "你在为一次网页技术探索写交接摘要。只写纯文本，不要 JSON，不要寒暄。"
SUMMARY_PROMPT = """下面是这次探索到目前为止的记录（你的每一轮回答和工具结果）。对话太长了，之后你只能看到：原始任务、这份摘要、最近几轮。所以把后面还用得上的都写进去，宁可具体，不要概括：

1. 目标与进度：任务要什么，做到哪一步了。
2. 已确认的事实（原样保留，不要改写）：页面结构、CSS 路径/选择器、表单数据键、接口网址与返回字段、关键数值与读回结果。
3. 试过但不行的做法，以及为什么不行（之后不要再试）。
4. 当前的假设和支持/反对它的证据。
5. 下一步打算做的几个实验。
{previous}
【记录】
{transcript}"""


def _transcript(messages: List[Any]) -> str:
    from langchain_core.messages import AIMessage
    lines = []
    for m in messages:
        if isinstance(m, AIMessage):
            lines.append("【你】" + _text(m.content)[:4000])
        elif isinstance(m.content, list):
            body = "\n".join("[截图]" if isinstance(p, dict) and p.get("type") == "image_url" else
                             str(p.get("text", "") if isinstance(p, dict) else p)[:6000] for p in m.content)
            lines.append("【工具结果】" + body)
        else:
            lines.append("【消息】" + str(m.content)[:6000])
    return "\n\n".join(lines)[-SUMMARY_SOURCE_CHARS:]


async def _compact(llm: Any, messages: List[Any], task: str, state: Dict[str, Any]) -> bool:
    """Above COMPACT_AT_CHARS, the turns before the last KEEP_RECENT_TURNS become one
    progress summary the model writes itself (facts kept verbatim, dead ends, current
    hypothesis, next steps), placed under the task: dropping old results lost what
    they had shown. False when it could not compact (the caller then elides)."""
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
    if sum(_size(m.content) for m in messages) <= COMPACT_AT_CHARS:
        return True
    cut = len(messages) - 2 * KEEP_RECENT_TURNS
    while cut > 2 and not isinstance(messages[cut], AIMessage):
        cut -= 1
    if cut <= 2:
        return False
    previous = f"\n【上一份摘要（把它并进新摘要）】\n{state['summary']}\n" if state.get("summary") else ""
    ask = [SystemMessage(content=SUMMARY_SYSTEM),
           HumanMessage(content=SUMMARY_PROMPT.format(previous=previous, transcript=_transcript(messages[2:cut])))]
    try:
        reply = await asyncio.wait_for(llm.ainvoke(ask), LLM_TIMEOUT_SEC)
        summary = _text(reply.content).strip()
    except Exception as exc:
        logger.warning(f"[explorer] compaction failed ({type(exc).__name__}: {exc}); eliding instead")
        return False
    if len(summary) < 40:
        logger.warning(f"[explorer] compaction gave no usable summary ({len(summary)} chars); eliding instead")
        return False
    state["summary"], state["n"] = summary, state.get("n", 0) + 1
    before = sum(_size(m.content) for m in messages)
    messages[1] = HumanMessage(content=f"{task}\n\n【之前的进展摘要（第 {state['n']} 次压缩，你自己写的）】\n{summary}")
    del messages[2:cut]
    logger.info(f"[explorer] compacted: {before} -> {sum(_size(m.content) for m in messages)} chars, "
                f"summary {len(summary)} chars ({_meta(reply)})")
    return True


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
    ids = RECORD_ID.findall(here)
    created = set(ctx.get("created") or [])
    mine = [i for i in ids if i in created] or [i for i in ids if await _created_here(page, i)]
    if mine:
        # 拼多多's 下一步 makes a new goods draft and opens it (KEN 11-01): that record
        # is this exploration's own. Its address names it twice -- the draft id and a
        # goods_id given later (…&id=205104378132&goods_id=1023830508893) -- and the
        # second one alone sent the explorer back: every id in the address of a record
        # it created is its own. Kept for the caller to delete when it ends.
        new = [i for i in ids if i not in created]
        ctx.setdefault("own_ids", []).extend(new)
        ctx.setdefault("created", []).extend(new)
        logger.info(f"[explorer] record {'/'.join(ids)} was created by this exploration's own tab; allowed")
        return f"{out}\n（这一步打开的记录 {'/'.join(ids)} 是这次探索自己新建的，可以在上面实验；探索结束后会删掉。）"
    try:
        await page.evaluate("history.back()", 5)
        await asyncio.sleep(2)
        back = await page.url()
    except Exception as exc:
        back = f"?（{type(exc).__name__}）"
    logger.warning(f"[explorer] left foreign record {rid} ({here[:120]}) -> {back[:120]}")
    return f"{out}\n拒绝：这一步打开了别的商品/记录（{rid}），已经退回到 {back}。只在这次任务自己的页面上实验。"


CREATE_URL = re.compile(r"create|add|new", re.I)


async def _created_here(page: Any, rid: str) -> bool:
    """Did a request our own tab sent (one that creates something) answer with *rid*?"""
    for r in reversed(list(getattr(page, "network", []))[-80:]):
        if not CREATE_URL.search(str(r.get("url") or "").split("?")[0]):
            continue
        try:
            if rid in str(await page.response_body(r["id"])):
                return True
        except Exception:
            continue
    return False


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
    if not getattr(page, "owned", True):
        # The tab the failed run left is that run's own page (its new draft): the
        # explorer was sent away from it five times (拼多多 KEN 11-01, …&id=205104513862).
        ctx["own_ids"] += [i for i in RECORD_ID.findall(here) if i not in ctx["own_ids"]]
    logger.info(f"[explorer] start model={model} port={port} reused_tab={not getattr(page, 'owned', True)} url={here[:160]} "
                f"task_chars={len(task)} own_ids={ctx['own_ids']}")
    first = task + "\n\n（你现在在 " + here + "）"
    messages: List[Any] = [SystemMessage(content=SYSTEM.format(tools=tool_docs(), max_calls=MAX_CALLS_PER_TURN)),
                           HumanMessage(content=first)]
    compaction: Dict[str, Any] = {}
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
                        "turns": turn, "calls": calls, "error": "", "created": ctx.get("created", [])}
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
            if not await _compact(llm, messages, first, compaction):
                _elide(messages)
        logger.warning(f"[explorer] used all {max_turns} turns without done ({calls} calls)")
        return {"final": "", "turns": max_turns, "calls": calls, "error": "used all turns without done",
                "created": ctx.get("created", [])}
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
