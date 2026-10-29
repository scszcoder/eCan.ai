"""Recipes, per-part failure counts and the exploration trigger (see package doc)."""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Dict, List, Optional

FAILS_TO_EXPLORE = 2          # consecutive failed checks of one part
EXPLORE_COOLDOWN_S = 12 * 3600  # per part
EXPLORES_PER_DAY = 2          # per store folder
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
    def grade(self, results: Dict[str, bool]) -> None:
        """*results*: part -> whether the check found it right this run."""
        parts, recipes, now = self.parts(), self.recipes(), _now()
        for part, ok in results.items():
            p = parts.setdefault(part, {"consecutive_fails": 0})
            p["consecutive_fails"] = 0 if ok else int(p.get("consecutive_fails", 0)) + 1
            p["last_checked_at"] = now
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

    def explore_target(self, results: Dict[str, bool], weights: Optional[Dict[str, int]] = None) -> Optional[str]:
        """The part to explore now, if any: failed ``FAILS_TO_EXPLORE`` checks in a row,
        not explored in the cooldown, and the folder's daily cap not reached; among
        several, the one with the most failures, then the most mismatches (*weights*).
        Marks it explored (call once per run, after ``grade``)."""
        parts, now = self.parts(), _now()
        today = [t for p in parts.values() for t in p.get("explored", []) if now - t < 86400]
        if len(today) >= EXPLORES_PER_DAY:
            return None
        failing = [(n, p) for n, p in parts.items()
                   if n in results and not results[n]
                   and int(p.get("consecutive_fails", 0)) >= FAILS_TO_EXPLORE
                   and now - max(p.get("explored", [0]) or [0]) > EXPLORE_COOLDOWN_S]
        if not failing:
            return None
        weights = weights or {}
        name, p = max(failing, key=lambda x: (int(x[1].get("consecutive_fails", 0)), weights.get(x[0], 0)))
        p.setdefault("explored", []).append(now)
        self._save("parts.json", parts)
        return name


def explore_prompt(part: str, mismatches: List[str], context: str, start_url: str, data_note: str) -> str:
    """The explore node's task: find a reliable method for *part* and return it as a recipe."""
    bad = "\n".join("- " + m for m in mismatches[:20]) or "（无）"
    return f"""任务：探索。最近两次运行里“{part}”这一部分都没做对（店铺接口核对的结果如下）。找出一个可靠的做法，写成脚本配方返回。

核对出错的地方：
{bad}

背景（之前的做法和经验）：
{context}

规则：
1. 在当前标签页打开 {start_url} 。这是新建页，用来做实验：只做出能重现问题的最小例子（例如少量规格值），绝不点“发布”“提交”“保存”“存草稿”，不点任何报名/推广/充值按钮。做完离开页面即可，不要保存。
2. 先弄清这部分数据实际存在哪里：页面上显示的元素（可能是滚动表格、只渲染一部分的行、合并的单元格），还是页面自己的数据（表单状态、框架组件的数据、它发出的接口请求）。用 evaluate 读；只读不改，先摸清结构。
3. 想出做法后，用 evaluate 测：写入一个测试值 → 读回确认页面显示和数据都变了 → 改回原值。三步都要做并记下结果。
4. 配方脚本要求：一段 JavaScript，形如 (async(DATA)=>{{ ... }})(__DATA__)；DATA 是这次商品的资料（{data_note}），脚本从 DATA 里取要填的值，按每一项自己的标识（例如规格值）对应，绝不按位置。脚本必须返回一段 JSON，说明改了几项、哪些对不上。脚本里不要出现两个连着的左花括号或两个连着的右花括号（中间加空格）。不超过 {MAX_SCRIPT_CHARS} 个字符。
5. 最后用 done 只返回一段 JSON：{{"part": "{part}", "when": "什么时候、在哪一步运行它（一句话）", "script": "脚本", "test": "写入/读回/改回的结果", "why": "原来的做法为什么错（一句话）"}}。找不到可靠做法就返回 {{"part": "{part}", "script": "", "why": "原因"}}。"""


def parse_recipe(final: str, part: str) -> Optional[dict]:
    """The recipe in the explore node's final answer, or None if unusable."""
    m = re.search(r"\{.*\}", str(final or ""), re.S)
    try:
        r = json.loads(m.group(0), strict=False) if m else {}
    except Exception:
        return None
    script = str(r.get("script") or "").strip()
    if not script or len(script) > MAX_SCRIPT_CHARS or DATA_SLOT not in script:
        return None
    # the prompt template renderer reads {{ }} as variables
    script = re.sub(r"\{\{", "{ {", script)
    script = re.sub(r"\}\}", "} }", script)
    return {"part": part or str(r.get("part") or ""), "when": str(r.get("when") or "")[:300],
            "script": script, "test": str(r.get("test") or "")[:600], "why": str(r.get("why") or "")[:300]}
