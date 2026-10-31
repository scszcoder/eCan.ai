"""The explorer's tools: look, probe, act, read the page's own data and traffic.

Guard rails are code, not prompt: the explorer may never publish, submit, save,
sign up or pay, and never leaves the store's own site.
"""
from __future__ import annotations

import json
import re
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple

from .page import PageSession

# Buttons an exploration must never press, whatever the model decides.
FORBIDDEN = re.compile(r"发布|提交|保存|存草稿|草稿|报名|推广|充值|开通|支付|购买|上架|下架|删除|确认订单")
RESULT_CHARS = 9000

# A compact view of the page (or one section): visible elements with their own
# text -- one-character labels included -- form state, and a CSS path to act on.
SNAPSHOT_JS = r"""((sel, maxChars) => {
  const root = sel ? document.querySelector(sel) : document.body;
  if (!root) return 'no element matches ' + sel;
  const out = []; let size = 0;
  const visible = e => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const pathOf = e => { const parts = []; for (let n = e, k = 0; n && n.nodeType === 1 && k < 5; n = n.parentElement, k++) {
      if (n.id && /^[A-Za-z][\w-]*$/.test(n.id)) { parts.unshift('#' + n.id); break; }
      const p = n.parentElement; const same = p ? [...p.children].filter(c => c.tagName === n.tagName) : [];
      parts.unshift(n.tagName.toLowerCase() + (same.length > 1 ? ':nth-of-type(' + (same.indexOf(n) + 1) + ')' : '')); }
    return parts.join('>'); };
  const own = e => [...e.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent.trim()).filter(Boolean).join(' ');
  const walk = (e, d) => {
    if (size > maxChars || !e || e.nodeType !== 1) return;
    if (['SCRIPT', 'STYLE', 'NOSCRIPT', 'SVG', 'PATH'].includes(e.tagName)) return;
    if (!visible(e)) return;
    const tag = e.tagName.toLowerCase(), t = own(e).slice(0, 120);
    const act = /^(a|button|input|select|textarea|label|option|li)$/.test(tag) || e.getAttribute('role') || e.onclick || e.tabIndex >= 0;
    const bits = [];
    if (t) bits.push(JSON.stringify(t));
    if ('value' in e && e.value !== undefined && e.value !== '' && tag !== 'li' && tag !== 'button') bits.push('value=' + JSON.stringify(String(e.value).slice(0, 80)));
    if (e.checked) bits.push('checked');
    if (e.disabled) bits.push('disabled');
    if (e.placeholder) bits.push('placeholder=' + JSON.stringify(e.placeholder));
    if (e.getAttribute('role')) bits.push('role=' + e.getAttribute('role'));
    if (e.className && typeof e.className === 'string' && /error|active|checked|selected|disabled/i.test(e.className)) bits.push('class~' + (e.className.match(/[\w-]*(error|active|checked|selected|disabled)[\w-]*/i) || [''])[0]);
    if (bits.length || act) { const line = '  '.repeat(Math.min(d, 12)) + tag + (act ? ' [' + pathOf(e) + ']' : '') + ' ' + bits.join(' ');
      out.push(line); size += line.length; }
    for (const c of e.children) walk(c, bits.length ? d + 1 : d);
    if (e.shadowRoot) for (const c of e.shadowRoot.children) walk(c, d + 1);
  };
  walk(root, 0);
  return out.join('\n') + (size > maxChars ? '\n…（截断：用 selector 只看一块）' : '');
})(%s, %d)"""

CLICK_JS = r"""((text, sel, nth) => {
  let els;
  if (sel) els = [...document.querySelectorAll(sel)];
  else { const all = [...document.querySelectorAll('body *')].filter(e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; });
    els = all.filter(e => [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim() === text));
    if (!els.length) els = all.filter(e => (e.innerText || '').trim() === text);
    if (!els.length) els = all.filter(e => e.children.length < 3 && (e.innerText || '').includes(text)); }
  const e = els[nth || 0];
  if (!e) return { error: 'no visible element ' + (sel ? 'matches ' + sel : 'shows ' + JSON.stringify(text)), candidates: els.length };
  e.scrollIntoView({ block: 'center' });
  const r = e.getBoundingClientRect();
  const label = ((e.closest('button,a,label,[role=button]') || e).innerText || e.value || '').trim().slice(0, 60);
  return { x: r.x + r.width / 2, y: r.y + r.height / 2, label, tag: e.tagName.toLowerCase(), matches: els.length };
})(%s, %s, %d)"""

FOCUS_JS = r"""((sel) => { const e = sel ? document.querySelector(sel) : document.activeElement;
  if (!e) return { error: 'no element ' + sel }; e.scrollIntoView({ block: 'center' }); e.focus();
  if ('select' in e) { try { e.select() } catch (x) {} }
  return { tag: e.tagName.toLowerCase(), value: e.value }; })(%s)"""

ToolFn = Callable[[PageSession, dict, dict], Awaitable[Tuple[str, Optional[str]]]]
TOOLS: Dict[str, Tuple[str, ToolFn]] = {}


def tool(name: str, doc: str):
    def deco(fn: ToolFn):
        TOOLS[name] = (doc, fn)
        return fn
    return deco


def _clip(x: Any) -> str:
    s = x if isinstance(x, str) else json.dumps(x, ensure_ascii=False, default=str)
    return s if len(s) <= RESULT_CHARS else s[:RESULT_CHARS] + f"\n…（还有 {len(s) - RESULT_CHARS} 字，缩小范围再看）"


@tool("snapshot", "snapshot(selector?, max_chars=12000)：页面（或 selector 那一块）可见元素的文字、值、勾选状态，和可以拿来点的 [CSS 路径]。单字标签（S、M、L）也在。")
async def _snapshot(page, a, ctx):
    return _clip(await page.evaluate(SNAPSHOT_JS % (json.dumps(a.get("selector") or ""), int(a.get("max_chars") or 12000)))), None


@tool("screenshot", "screenshot(selector?)：截图（整屏或某个元素），你能直接看到。")
async def _screenshot(page, a, ctx):
    data = await page.screenshot(a.get("selector") or "")
    return ("截图如下" if data else "截图失败"), (data or None)


@tool("run_js", "run_js(code)：在页面里运行一段 JavaScript（表达式，或带 return 的函数体，可以 await），返回结果。用来读页面状态、组件数据、DOM。不要用它点发布/提交/保存类按钮。")
async def _run_js(page, a, ctx):
    code = str(a.get("code") or "")
    if re.search(r"\.click\(|\.submit\(|dispatchEvent\(|requestSubmit", code) and FORBIDDEN.search(code):
        return "拒绝：这段脚本会点发布/提交/保存一类的按钮。探索只做实验。", None
    body = code if re.search(r"(^|[;{}\s])return\b", code) else "return (" + code + "\n);"
    return _clip(await page.evaluate("(async()=>{ " + body + " })()")), None


@tool("network", "network(filter?, body=false, limit=15)：页面最近发出的请求（网址、状态）；body=true 时附上响应内容。页面自己的接口往往直接告诉你数据怎么存。")
async def _network(page, a, ctx):
    rx = re.compile(str(a.get("filter") or "."), re.I)
    rows = [r for r in page.network if rx.search(r.get("url", ""))][-int(a.get("limit") or 15):]
    if a.get("body"):
        return _clip([dict(r, body=(await page.response_body(r["id"]))[:3000]) for r in rows[-5:]]), None
    return _clip(rows), None


@tool("click", "click(text? | selector?, nth=0)：像人一样点一下：按可见文字（完全相同的优先）或 snapshot 给的 CSS 路径。返回点到的是什么。")
async def _click(page, a, ctx):
    found = await page.evaluate(CLICK_JS % (json.dumps(a.get("text") or ""), json.dumps(a.get("selector") or ""),
                                            int(a.get("nth") or 0)))
    if not isinstance(found, dict) or found.get("error"):
        return _clip(found), None
    if FORBIDDEN.search(str(found.get("label") or "")):
        return f"拒绝：“{found.get('label')}”是发布/提交/保存一类的按钮，探索不能点。", None
    await page.mouse_click(found["x"], found["y"])
    return _clip({"clicked": found.get("label") or found.get("tag"), "matches": found.get("matches")}), None


@tool("type", "type(text, selector?)：把整段文字一次输入到 selector 那个输入框（不给就是当前焦点），先选中原内容，输入后读回。")
async def _type(page, a, ctx):
    focus = await page.evaluate(FOCUS_JS % json.dumps(a.get("selector") or ""))
    if not isinstance(focus, dict) or focus.get("error"):
        return _clip(focus), None
    await page.insert_text(str(a.get("text") or ""))
    after = await page.evaluate(FOCUS_JS % json.dumps(a.get("selector") or ""))
    return _clip({"value_now": (after or {}).get("value")}), None


@tool("press", "press(key)：按一个键：Enter、Escape、Tab、Backspace、ArrowDown、ArrowUp。")
async def _press(page, a, ctx):
    await page.press(str(a.get("key") or "Enter"))
    return "ok", None


@tool("navigate", "navigate(url)：打开同一个店铺后台里的网址（只能是本平台的网址）。")
async def _navigate(page, a, ctx):
    url = str(a.get("url") or "")
    if not re.match(r"https://", url) or not any(d in url.split("/")[2] for d in ctx.get("domains") or []):
        return "拒绝：只能打开本平台店铺后台的网址。", None
    return "现在在 " + await page.navigate(url), None


@tool("wait", "wait(seconds)：等页面加载或渲染（最多 10 秒）。")
async def _wait(page, a, ctx):
    import asyncio
    await asyncio.sleep(min(10.0, float(a.get("seconds") or 2)))
    return "ok", None


def _form_tool(name: str, doc: str, build):
    async def run(page, a, ctx):
        try:
            js = build(a)
        except Exception as exc:
            return f"参数不对：{exc}", None
        return _clip(await page.evaluate(js, timeout=40)), None
    TOOLS[name] = (doc, run)


def _register_form_tools():
    from agent.ec_skills.browser_use_extension import form_store_tools as f
    _form_tool("probe_page_data", "probe_page_data(text)：找出显示 text 的那部分背后页面自己的表单数据，列出它的键。", lambda a: f._probe_js(str(a["text"])))
    _form_tool("read_form_field", "read_form_field(key)：读一个键的整段值（a/b 表示 a 里的 b）。", lambda a: f._read_js(str(a["key"])))
    _form_tool("write_form_field", "write_form_field(key, value)：把整段新值写进去（不对的类型、undefined 会被拒绝；没写进去会自动改回），报告 same_as_written。", lambda a: f._write_js(str(a["key"]), f._as_value(a.get("value"))))
    _form_tool("revert_form_field", "revert_form_field(key)：改回 write_form_field 之前的值。", lambda a: f._revert_js(str(a["key"])))
    _form_tool("try_recipe", "try_recipe(key, build, data)：把配方按发布时的样子完整跑一遍（data 是商品资料原样），读回后改回旧值。", lambda a: f._try_recipe_js(str(a["key"]), str(a["build"]), a.get("data")))


_register_form_tools()


def tool_docs() -> str:
    return "\n".join(f"- {doc}" for _, (doc, _) in sorted(TOOLS.items()))
