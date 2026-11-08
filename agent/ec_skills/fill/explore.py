"""Repairing a fill flow: the explorer's tools for it and its task.

The explorer edits a working copy of the flow (``fill_edit``), runs it up to the
submit on the live page (``fill_dry_run``: the platform's submit and autosave
requests are blocked) and repeats until the dry run reaches the submit with the
form matching the listing. ``finish(...)`` then proposes that copy; the next real
listing runs it and its read-back check keeps or retires it (store.FillStore).
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Dict, Optional, Tuple

from .store import FillStore, _all_steps

RESULT_CHARS = 9000


def _clip(x: Any) -> str:
    s = x if isinstance(x, str) else json.dumps(x, ensure_ascii=False, default=str, indent=1)
    return s if len(s) <= RESULT_CHARS else s[:RESULT_CHARS] + f"\n…（还有 {len(s) - RESULT_CHARS} 字）"


def _outline(steps, depth: int = 0) -> list:
    lines = []
    for s in steps or []:
        refs = " ".join(f"{k}={s[k]}" for k in ("js", "target", "items", "if", "until", "input", "frame", "save")
                        if isinstance(s.get(k), str) and len(s[k]) <= 60)
        lines.append("  " * depth + f"- {s.get('id')} [{s.get('op') or 'js'}] {s.get('stage') or ''} {refs}".rstrip())
        if s.get("op") == "foreach":
            lines += _outline(s.get("steps"), depth + 1)
    return lines


def view(store: FillStore, what: str) -> str:
    w = store.working()
    what = str(what or "steps")
    if what == "steps":
        return "\n".join(_outline(w.get("steps"))) + "\n\n片段：" + "、".join(sorted((w.get("snippets") or {}).keys()))
    if what.startswith("snippet:"):
        name = what.split(":", 1)[1]
        return (w.get("snippets") or {}).get(name, f"没有片段 {name}")
    if what.startswith("step:"):
        sid = what.split(":", 1)[1]
        hit = next((s for s in _all_steps(w.get("steps")) if s.get("id") == sid), None)
        return _clip(hit) if hit else f"没有步骤 {sid}"
    if what in ("report", "diag", "start_url"):
        return _clip(w.get(what))
    if what == "notes":
        return store.notes() or "（还没有）"
    if what == "last_failure":
        return _clip(store._load("last_failure.json", {}) or "（没有记录）")
    if what == "versions":
        return _clip(store.meta().get("versions"))
    return "what 可以是：steps、snippet:<名字>、step:<id>、report、diag、start_url、notes、last_failure、versions"


def _find(steps, sid) -> Optional[Tuple[list, int]]:
    for k, s in enumerate(steps or []):
        if s.get("id") == sid:
            return steps, k
        if s.get("op") == "foreach":
            hit = _find(s.get("steps"), sid)
            if hit:
                return hit
    return None


def edit(store: FillStore, a: Dict[str, Any]) -> str:
    """One edit of the working copy; returns what happened."""
    w = store.working()
    snippets = w.setdefault("snippets", {})
    if a.get("set_snippet"):
        name = str(a["set_snippet"])
        if a.get("code") is None:
            return "set_snippet 要给 code"
        snippets[name] = str(a["code"])
        done = f"片段 {name} 已更新（{len(snippets[name])} 字）"
    elif a.get("delete_snippet"):
        snippets.pop(str(a["delete_snippet"]), None)
        done = f"片段 {a['delete_snippet']} 已删除"
    elif a.get("set_step") or a.get("delete_step") or a.get("insert_after") or a.get("insert_before"):
        sid = a.get("set_step") or a.get("delete_step") or a.get("insert_after") or a.get("insert_before")
        hit = _find(w.get("steps"), sid)
        if not hit:
            return f"没有步骤 {sid}"
        lst, k = hit
        step = a.get("step")
        if not a.get("delete_step") and not isinstance(step, dict):
            return "要给 step（一个步骤对象）"
        if a.get("set_step"):
            lst[k] = step
        elif a.get("delete_step"):
            lst.pop(k)
        elif a.get("insert_after"):
            lst.insert(k + 1, step)
        else:
            lst.insert(k, step)
        done = f"步骤 {sid} 已{'替换' if a.get('set_step') else '删除' if a.get('delete_step') else '插入新步骤'}"
    elif a.get("set") in ("report", "diag", "start_url"):
        w[a["set"]] = a.get("value")
        done = f"{a['set']} 已更新"
    else:
        return "不认识的修改；见工具说明"
    bad = store.save_working(w)
    return f"拒绝：{bad}（工作副本没变）" if bad else done + "。改完用 fill_dry_run 试。"


async def dry_run_tool(ctx: Dict[str, Any], a: Dict[str, Any]) -> str:
    from .node import dry_run
    f = ctx["fill"]
    out = await asyncio.to_thread(dry_run, f["store_id"], f["experience"], f["listing"], f["file_map"])
    keep = {k: out.get(k) for k in ("ok", "stage", "step", "error", "diag", "check", "blocked") if out.get(k) not in (None, "", [])}
    keep["steps_run"] = out.get("log")[-20:] if out.get("log") else []
    keep["verdict"] = ("通过：走到了提交前，表单和资料一致" if out.get("ok") and (out.get("check") or {}).get("ok") else
                       "没通过：" + (str(out.get("error")) if not out.get("ok") else "表单和资料不一致（见 check）"))
    return _clip(keep)


TOOL_DOCS = {
    "fill_view": "fill_view(what)：看填表流程（工作副本）。what：steps（步骤大纲）、snippet:<名字>、step:<id>、report、diag、start_url、notes（平台笔记）、last_failure（上次真实发布失败在哪一步、页面什么样）、versions。",
    "fill_edit": "fill_edit(...)：改填表流程的工作副本，一次一处：{set_snippet: 名字, code: 脚本} | {delete_snippet: 名字} | {set_step: id, step: {...}} | {insert_after: id, step: {...}} | {insert_before: id, step: {...}} | {delete_step: id} | {set: report|diag|start_url, value: ...}。步骤格式见任务说明。",
    "fill_dry_run": "fill_dry_run()：在新标签页里把工作副本从头跑到“提交”之前（真正的提交和自动存草稿都被拦截），读回表单和资料比对。返回停在哪一步、错误、页面状态、比对结果。",
    "fill_note": "fill_note(text)：把一条查清的平台事实记进平台笔记（下一次排查会先读到）。",
}


def register(TOOLS: dict) -> None:
    """Adds the fill tools to the explorer's tool table; they work only in a fill repair."""
    def need(ctx):
        return None if ctx.get("fill") else "这次探索不是修填表流程，没有这个工具。"

    async def _view(page, a, ctx):
        return need(ctx) or view(FillStore(ctx["fill"]["experience"]), a.get("what") or "steps"), None

    async def _edit(page, a, ctx):
        return need(ctx) or edit(FillStore(ctx["fill"]["experience"]), a), None

    async def _dry(page, a, ctx):
        return need(ctx) or await dry_run_tool(ctx, a), None

    async def _note(page, a, ctx):
        if need(ctx):
            return need(ctx), None
        FillStore(ctx["fill"]["experience"]).add_note(a.get("text") or "")
        return "已记下", None
    for name, fn in (("fill_view", _view), ("fill_edit", _edit), ("fill_dry_run", _dry), ("fill_note", _note)):
        TOOLS[name] = (TOOL_DOCS[name], fn)


def repair_prompt(store: FillStore, listing_note: str) -> str:
    """The explorer's task when the platform's fill flow failed on a real listing."""
    fail = store._load("last_failure.json", {})
    return f"""任务：修好这个平台的“填表流程”。它是一份数据（步骤列表 + 页面脚本片段），由一个固定的引擎在店铺后台的发布页上一步步执行，把商品资料填进表单并提交。最近一次真实发布在下面这一步失败了——多半是平台改了页面。你要像资深工程师修线上问题那样找到根本原因，改好流程，并用试运行证明改好了。

【上次失败】
{_clip(fail) if fail else "（没有记录：先用 fill_dry_run 复现）"}

【平台笔记】（之前查清的事实）
{store.notes() or "（还没有）"}

【商品资料】{listing_note}

【流程格式】每个步骤：{{"id": 唯一名, "stage": 阶段名, "op": 操作, ...}}。脚本（js/target/items/text/if/until/input）写片段名或直接写脚本，执行时是 (async (A) => {{...}})(参数)，A = {{listing, files, vars, item, index, mode}}；以 return/const/let/if 等语句开头的要自己 return，否则当表达式。脚本返回 null/false、带 error 的对象或抛错 = 这一步失败。
- js：运行脚本（save 把结果存进 A.vars.<名字>）。wait：反复运行直到为真（seconds）。
- click：target 返回要点的元素；until 点完后等它为真；retries 重试（最后一次用元素自己的 click()）；js_click 直接用元素的 click()；frame 在地址含这个字的框架里做。
- type：点 target 元素后输入 text 脚本的值；commit 输入后按的键（如 Tab）；until 输入后等它为真。
- press（key）、sleep（seconds）、foreach（items 返回列表，steps 对每一项执行，A.item 是当前项）。
- upload：roles 是资料里的文件用途（main、detail、size_chart…），input 返回 <input type=file>（可配 frame），answers {{url: 上传接口地址的正则, path: 返回里对象的位置, name_key: 文件名字段}} 收集上传后的地址存进 save。
- submit：真正的提交按钮（只有它能点“提交/发布”类按钮）；试运行时它不会点，而是运行 report 读回表单。
- report：一段脚本，返回 {{title, category, attributes{{名:值}}, pictures{{main, detail}}, skus[{{商家编码, 价格, 库存, 颜色, 尺码}}]}}，用来和资料比对。

【方法】
1. 复现：fill_view last_failure 看失败的步骤和当时的页面；fill_dry_run 跑一遍，确认在同一处失败。
2. 观察：用 snapshot / screenshot / run_js / network / probe_page_data 看那一步的页面现在是什么样，和片段期待的对比（元素文字、结构、表单数据的位置、接口变了没有）。
3. 至少写两个假设，逐个用证据证实或排除。
4. 改：fill_edit 一次改一处，只改出问题的片段或步骤，保持其他部分不动。优先读写页面自己的表单数据，不要依赖元素序号或位置。
5. 验证：fill_dry_run，直到 verdict 是“通过”。没通过就回到第 2 步。查清的平台事实用 fill_note 记下。
6. 别动不该动的：失败原因是我们的引擎或工具本身（不是页面变了）时，不要绕过去，写进 engine_issues 交给开发者。

【规则】你自己在页面上做实验时，绝不点“发布”“提交”“保存”“存草稿”，不点报名/推广/充值/开通；fill_dry_run 里的提交和自动存草稿已被拦截。

【交付】最后用 done 只返回一段 JSON：
{{"fill_fixed": true 或 false, "root_cause": "根本原因和证据", "change": "改了哪些步骤/片段、为什么", "dry_run": "最后一次 fill_dry_run 的 verdict 原文", "findings": "给下一次排查的事实", "engine_issues": ["引擎/工具本身的问题（没有就空）"]}}
fill_fixed 只能在最后一次 fill_dry_run 通过之后写 true。"""


def finish(experience: str, final: str) -> Tuple[int, str]:
    """After a repair: propose the working copy if the explorer says it is fixed and its
    last dry run passed. (version, "") or (0, why not)."""
    m = re.search(r"\{.*\}", str(final or ""), re.S)
    try:
        r = json.loads(m.group(0), strict=False) if m else {}
    except Exception:
        r = {}
    store = FillStore(experience)
    if r.get("findings"):
        store.add_note(str(r["findings"]))
    if not r.get("fill_fixed"):
        return 0, "the explorer did not fix it: " + str(r.get("root_cause") or final)[:300]
    return store.propose(str(r.get("change") or r.get("root_cause") or "")[:600])
