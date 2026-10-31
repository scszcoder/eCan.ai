"""Recipes, per-part failure counts and the exploration trigger (see package doc)."""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Dict, List, Optional

from .page_data import HELPERS

FAILS_TO_EXPLORE = 2          # consecutive failed checks of one part
EXPLORE_COOLDOWN_S = 12 * 3600  # per part
EXPLORES_PER_DAY = int(os.environ.get("ECAN_EXPLORES_PER_DAY", "10"))   # per store folder (user 2026-10-30: 10 for now)
MAX_SCRIPT_CHARS = 6000
DATA_SLOT = "__DATA__"


def _now() -> float:
    return time.time()


class ExperienceStore:
    """One experience folder: ``recipes.json`` and ``parts.json`` (failure counts)."""

    def __init__(self, folder: str):
        self.folder = folder
        os.makedirs(folder, exist_ok=True)

    # ── files ─────────────────────────────────────────────────────────
    def _path(self, name: str) -> str:
        return os.path.join(self.folder, name)

    def _load(self, name: str, default):
        try:
            with open(self._path(name), encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default

    def _save(self, name: str, value) -> None:
        tmp = self._path(name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self._path(name))

    def recipes(self) -> List[dict]:
        return self._load("recipes.json", [])

    def parts(self) -> Dict[str, dict]:
        return self._load("parts.json", {})

    # ── recipes ───────────────────────────────────────────────────────
    def add_recipe(self, recipe: dict) -> dict:
        """Store a new candidate; it replaces an earlier candidate for the same part."""
        recipe = dict(recipe, status="candidate", added_at=_now(), passes=0, fails=0)
        keep = [r for r in self.recipes() if not (r.get("part") == recipe["part"] and r.get("status") == "candidate")]
        self._save("recipes.json", keep + [recipe])
        return recipe

    def render(self, data: Any = None, max_chars: int = 9000) -> str:
        """Recipes for the agent's prompt, verified first; ``__DATA__`` filled with *data*."""
        live = [r for r in self.recipes() if r.get("status") in ("verified", "candidate")]
        live.sort(key=lambda r: (r.get("status") != "verified", -float(r.get("added_at") or 0)))
        blob = json.dumps(data, ensure_ascii=False) if data is not None else "null"
        out = []
        for r in live:
            tag = "【已验证】" if r["status"] == "verified" else "【待验证：上次探索得出，这次照做，核对会给它定级】"
            out.append(f"- {r['part']}{tag}：{r.get('when', '')}\n  用 evaluate 原样运行（一个字都不要改）：\n"
                       + r["script"].replace(DATA_SLOT, blob))
        text = "\n".join(out)
        return text[:max_chars] if text else "（还没有）"

    # ── scoring ───────────────────────────────────────────────────────
    def grade(self, results: Dict[str, bool], notes: Optional[Dict[str, List[str]]] = None) -> None:
        """*results*: part -> whether the check found it right this run; *notes*:
        part -> what went wrong (kept for an exploration started before a run)."""
        parts, recipes, now = self.parts(), self.recipes(), _now()
        for part, ok in results.items():
            p = parts.setdefault(part, {"consecutive_fails": 0})
            p["consecutive_fails"] = 0 if ok else int(p.get("consecutive_fails", 0)) + 1
            p["last_checked_at"] = now
            if not ok and (notes or {}).get(part):
                p["last_failures"] = [str(n)[:300] for n in notes[part][:10]]
            for r in recipes:
                if r.get("part") != part or r.get("status") not in ("candidate", "verified"):
                    continue
                if ok:
                    r["passes"] = int(r.get("passes", 0)) + 1
                    r["status"] = "verified"
                else:
                    r["fails"] = int(r.get("fails", 0)) + 1
                    # a candidate that failed is retired; a verified one gets one more chance
                    if r["status"] == "candidate" or r["fails"] >= 2:
                        r["status"] = "failed"
        self._save("parts.json", parts)
        self._save("recipes.json", recipes)

    def _may_explore(self, p: dict, now: float, signature: str) -> bool:
        """Cooldown per part -- unless the explorer changed since its last try (a
        different model or instructions: *signature*), which makes a new try fair."""
        last = max(p.get("explored", [0]) or [0])
        return now - last > EXPLORE_COOLDOWN_S or p.get("explored_sig", "") != signature

    def _mark_explored(self, parts: dict, name: str, now: float, signature: str) -> str:
        p = parts[name]
        p.setdefault("explored", []).append(now)
        p["explored_sig"] = signature
        self._save("parts.json", parts)
        return name

    def unmark_explored(self, name: str) -> None:
        """Give back the latest try at *name*: the explorer never got a model answer
        (a run at 03:50 with the account out of balance cost 拼多多 its next try,
        KEN 2026-10-31)."""
        parts = self.parts()
        p = parts.get(name)
        if p and p.get("explored"):
            p["explored"].pop()
            self._save("parts.json", parts)

    def _under_daily_cap(self, parts: dict, now: float) -> bool:
        today = [t for p in parts.values() for t in p.get("explored", []) if now - t < 86400]
        return len(today) < EXPLORES_PER_DAY

    def explore_target(self, results: Dict[str, bool], weights: Optional[Dict[str, int]] = None,
                       signature: str = "") -> Optional[str]:
        """The part to explore now, if any: failed ``FAILS_TO_EXPLORE`` checks in a row,
        allowed by its cooldown (``_may_explore``), and the folder's daily cap not
        reached; among several, the one with the most failures, then the most
        mismatches (*weights*). Marks it explored (call once per run, after ``grade``)."""
        parts, now = self.parts(), _now()
        if not self._under_daily_cap(parts, now):
            return None
        failing = [(n, p) for n, p in parts.items()
                   if n in results and not results[n]
                   and int(p.get("consecutive_fails", 0)) >= FAILS_TO_EXPLORE
                   and self._may_explore(p, now, signature)]
        if not failing:
            return None
        weights = weights or {}
        name, _ = max(failing, key=lambda x: (int(x[1].get("consecutive_fails", 0)), weights.get(x[0], 0)))
        return self._mark_explored(parts, name, now, signature)

    def pending_explore(self, signature: str = "") -> Optional[str]:
        """A part to explore *before* the next run: it failed ``FAILS_TO_EXPLORE``
        checks in a row, has no live recipe, and cooldown and cap allow it -- so the
        run does not fail on it again first. Marks it explored."""
        parts, now = self.parts(), _now()
        if not self._under_daily_cap(parts, now):
            return None
        live = {r.get("part") for r in self.recipes() if r.get("status") in ("candidate", "verified")}
        due = [(n, p) for n, p in parts.items()
               if int(p.get("consecutive_fails", 0)) >= FAILS_TO_EXPLORE and n not in live
               and self._may_explore(p, now, signature)]
        if not due:
            return None
        name, _ = max(due, key=lambda x: int(x[1].get("consecutive_fails", 0)))
        return self._mark_explored(parts, name, now, signature)


# How to find where a page keeps a part's data -- the techniques that worked by hand
# (抖店 2026-10-30: the SKU table and the size chart sit in the page's form store,
# reached in one read from a visible input; an explorer without these spent 59 steps
# guessing window globals and found nothing).
EXPLORE_TOOLBOX = """找数据、改数据用这几个动作（它们是写好、测过的代码，不要自己写遍历组件的脚本）：
1. probe_page_data(text)：text 填这部分旁边看得见的文字（标签、列名、某个值）。返回页面表单数据的所有键（keys），找出和这部分相关的那个键。
2. read_form_field(key)：读这个键的整段值（a/b 表示 a 里面的 b）。读到的结构就是要写的格式。
3. write_form_field(key, value)：value 直接给对象或数组（不是字符串），用同样结构的整段新值写进去，自动读回并报告 same_as_written；旧值会保存。
4. revert_form_field(key)：改回旧值。实验做完一定要改回。
5. try_recipe(key, build, data)：把配方按发布时的样子原样跑一遍（data 填任务给的商品资料原样，作为对象），读回后自动改回旧值。
做法：先 probe → read 看清现在的值 → 按商品资料（DATA）算出新值 → write 测一次 → 看页面和读回都对 → revert → 写好 build 后用 try_recipe 跑一遍，same_as_written 为 true 才算做成。
配方写成 {"key": 键, "build": "一段 JavaScript 函数体：用 DATA（商品资料）算出这个键的整段新值并 return"}，系统会把它包成可以重复运行的脚本；build 里先读 DATA 的真实结构（任务里给了资料的样子），不要猜字段名。
不要：自己写遍历 React/Vue 组件的脚本；逐个输入框模拟打字；在 window 上猜全局变量；反复点同一个按钮等弹窗；页面卡住时从头重建整个页面。"""


def explore_prompt(part: str, mismatches: List[str], context: str, start_url: str, data_note: str) -> str:
    """The explore node's task: find a reliable method for *part* and return it as a recipe."""
    bad = "\n".join("- " + m for m in mismatches[:20]) or "（无）"
    return f"""任务：探索。最近两次运行里“{part}”这一部分都没做对（店铺接口核对的结果如下）。找出一个可靠的做法，写成脚本配方返回。

核对出错的地方：
{bad}

背景（之前的做法和经验）：
{context}

{EXPLORE_TOOLBOX}

规则：
1. 在当前标签页打开 {start_url} 。这是我们自己的测试商品草稿（问题已经在上面重现了，直接去出问题的那部分）或新建页（只做出能重现问题的最小例子）。只做实验：绝不点“发布”“提交”“保存”“存草稿”，不点任何报名/推广/充值按钮；做完离开页面即可，不要保存。
2. 先弄清这部分数据实际存在哪里：页面上显示的元素（可能是滚动表格、只渲染一部分的行、合并的单元格），还是页面自己的数据（表单状态、框架组件的数据、它发出的接口请求）。用 evaluate 读；只读不改，先摸清结构。
3. 想出做法后，用 evaluate 测：写入一个测试值 → 读回确认页面显示和数据都变了 → 改回原值。三步都要做并记下结果。
4. 配方脚本要求：一段 JavaScript，形如 (async(DATA)=>{{ ... }})(__DATA__)；DATA 是这次商品的资料（{data_note}），脚本从 DATA 里取要填的值，按每一项自己的标识（例如规格值）对应，绝不按位置。脚本必须返回一段 JSON，说明改了几项、哪些对不上。脚本里不要出现两个连着的左花括号或两个连着的右花括号（中间加空格）。不超过 {MAX_SCRIPT_CHARS} 个字符。
5. 最后用 done 只返回一段 JSON：{{"part": "{part}", "when": "什么时候、在哪一步运行它（一句话）", "key": "要写的键", "build": "用 DATA 算出新值的函数体", "test": "写入/读回/改回的结果", "replay": try_recipe 返回的原文, "why": "原来的做法为什么错（一句话）"}}（也可以给完整的 "script" 代替 key 和 build）。用 key 和 build 的配方必须带 try_recipe 的 replay，而且 same_as_written 为 true，否则不算配方。找不到可靠做法就返回 {{"part": "{part}", "script": "", "why": "原因"}}。"""


def explore_signature(model: str, escalation: str = "") -> str:
    """Identifies the explorer (model, escalation, instructions): a part may be
    explored again before its cooldown when this changes."""
    import hashlib
    blob = "|".join([model or "", escalation or "", EXPLORE_TOOLBOX, explore_prompt("", [], "", "", "")])
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]


def recipe_script(key: str, build: str) -> str:
    """A recipe that writes one form field with a value built from the run's data
    (DATA): the explorer's ``build`` function body inside the tested helpers."""
    return ("(async(DATA)=>{" + HELPERS + "const key = " + json.dumps(key) + ";"
            "const loc = locate(key); if (!loc) return 'no field ' + key;"
            "const want = (function(DATA){ " + build + " })(DATA);"
            "await loc.set(want); await new Promise(r => setTimeout(r, 600));"
            "return safe({ key, same_as_written: safe(loc.get(), 1e7) === safe(want, 1e7) }, 2000) })(__DATA__)")


def parse_recipe(final: str, part: str) -> Optional[dict]:
    """The recipe in the explore node's final answer, or None if unusable."""
    m = re.search(r"\{.*\}", str(final or ""), re.S)
    try:
        r = json.loads(m.group(0), strict=False) if m else {}
    except Exception:
        return None
    script = str(r.get("script") or "").strip()
    if not script and r.get("key") and r.get("build"):
        # Saved only once replayed as a publish run will run it: run 59's recipe was
        # tested piece by piece, never as a whole, and failed in run 61.
        if not re.search(r'same_as_written\W{1,4}true', json.dumps(r.get("replay"), ensure_ascii=False)):
            return None
        script = recipe_script(str(r["key"]), str(r["build"]))
    if not script or len(script) > MAX_SCRIPT_CHARS + len(HELPERS) or DATA_SLOT not in script:
        return None
    # the prompt template renderer reads {{ }} as variables
    script = re.sub(r"\{\{", "{ {", script)
    script = re.sub(r"\}\}", "} }", script)
    return {"part": part or str(r.get("part") or ""), "when": str(r.get("when") or "")[:300],
            "script": script, "test": str(r.get("test") or "")[:600], "why": str(r.get("why") or "")[:300]}


STORE_LIMIT = "店铺限制"     # a store limit (category/brand not allowed, logged out): never counted


def _default_ask(prompt: str) -> str:
    from langchain_core.messages import HumanMessage
    from agent.ec_skills.llm_utils.llm_utils import create_ecanai_chat_llm
    llm = create_ecanai_chat_llm(os.environ.get("ECAN_PART_NAMER_MODEL", "qwen3.7-flash"), temperature=0.0)
    reply = llm.invoke([HumanMessage(content=prompt)], extra_body={"enable_thinking": False}).content
    return reply if isinstance(reply, str) else json.dumps(reply, ensure_ascii=False)


def name_parts(items: List[str], known: List[str] = (), ask=None) -> List[str]:
    """The part of the work each item (a check mismatch, a passed check, a failure
    note) is about, in order. Reuses *known* names so counts carry over between
    runs, invents a short name for a new kind of problem, and names store limits
    ``STORE_LIMIT``. *ask*: prompt -> reply (default: a small model). [] on failure."""
    items = [str(i) for i in items if str(i).strip()]
    if not items:
        return []
    numbered = "\n".join(f"{k}. {t[:200]}" for k, t in enumerate(items))
    prompt = (
        "下面是一次自动化任务里逐项检查的结果或失败说明。给每一项起一个“部分”名：它说的是这项工作里的哪一部分"
        "（例如 标题、类目、规格编码、价格、库存、主图、尺码表）。\n"
        "规则：1. 已有的部分名（" + ("、".join(known) or "无") + "）合适就用原名，不要造近义词；"
        "2. 都不合适时起一个 2-6 个字的新名字，不要硬套一个相近的已有名字（属性 不是 规格值）；"
        "项目开头已经写明它是哪部分的（例如“属性 风格：…”是 属性），就用那个词；3. 同一类问题用同一个名字；"
        f"4. 店铺本身的限制（类目/品牌不能用、没登录、店铺资质）一律叫“{STORE_LIMIT}”。\n"
        '只返回 JSON：{"parts": ["第0项的部分名", "第1项的部分名", ...]}，个数和项数相同。\n\n' + numbered)
    try:
        reply = (ask or _default_ask)(prompt)
        m = re.search(r"\{.*\}", reply, re.S)
        parts = json.loads(m.group(0), strict=False).get("parts") if m else None
    except Exception:
        return []
    if not isinstance(parts, list) or len(parts) != len(items):
        return []
    return [str(p).strip()[:12] or "其他" for p in parts]


def part_results(failed: List[str], passed: List[str] = (), known: List[str] = (), ask=None):
    """``(results, weights, named)``: part -> passed?, part -> number of failed items,
    and part -> its failed items, from the run's failed and passed items. Store limits
    are left out. ``({}, {}, {})`` when the items cannot be named."""
    failed, passed = list(failed), list(passed)
    names = name_parts(failed + passed, known, ask)
    if not names:
        return {}, {}, {}
    results: Dict[str, bool] = {}
    weights: Dict[str, int] = {}
    named: Dict[str, List[str]] = {}
    for k, part in enumerate(names):
        if part == STORE_LIMIT:
            continue
        if k < len(failed):
            results[part] = False
            weights[part] = weights.get(part, 0) + 1
            named.setdefault(part, []).append(failed[k])
        else:
            results.setdefault(part, True)
    return results, weights, named
