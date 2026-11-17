"""Draft guard: fixes and checks listing-draft proposals in code before a report is saved.

An LLM drafting step drops or reshuffles facts from run to run; this pass makes the
facts deterministic. It reads the product folder's ``products.json``
(``{"models": [{"model", "upc", "owner_confirmed": {key: value}, "features": [...]}]}``)
and, for each proposal in the report:

- every ``owner_confirmed`` value becomes an item specific under one canonical name
  and must be stated in the description (missing ones are appended);
- ``features``, when given, become the selling points, in order;
- buyer copy loses any sentence that names a source or hedges;
- the condition description is one plain sentence about the condition;
- ``title_length`` is measured and a title over the limit is cut at a word;
- flags, gaps and conflicts about values the owner settled, or stale
  selling-point counts, are dropped.

Every change is listed in the proposal's ``guard_fixes``.

Use as a skill code node (``main(state)``) placed after the node whose
``result.llm_result.next_tool_input`` carries ``{"report": {...}, "report_md": "..."}``,
with the product folder at ``prompt_refs.run_context.product_folder``.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from utils.logger_helper import logger_helper as logger

# owner_confirmed keys whose item-specific name is not just the key title-cased.
SPEC_NAMES = {
    "wattage": "Power",
    "plate_surface": "Plate Surface",
    "cooking_surface": "Cooking Surface",
}
# Other names a drafter uses for the same item specific; replaced by the canonical one.
ALIASES = {
    "Power": ["wattage", "watts", "power"],
    "Plate Surface": ["plate surface", "surface coating", "plate coating", "coating", "plate material"],
    "Servings": ["servings", "serving size", "serves", "capacity"],
    "Weight": ["weight", "product weight", "item weight"],
    "Dimensions": ["dimensions", "product dimensions", "item dimensions", "size"],
    "Cooking Surface": ["cooking surface", "cooking area", "cooking surface area"],
    "Warranty": ["warranty", "manufacturer warranty"],
    "Color": ["color", "colour"],
}
BANNED = ["owner-confirmed", "owner confirmed", "box indicates", "box states", "per the box",
          "box claim", "not verified", "not confirmed", "not provided", "not specified",
          "is described for", "suited to", "intended for"]
CONDITION_NOISE = ["photo", "packag", "included", "box"]
MAX_TITLE = 80  # eBay's title limit
SELLING_POINTS = 7


def spec_name(key: str) -> str:
    return SPEC_NAMES.get(key, key.replace("_", " ").title())


def _norm(s) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def _numbers(s) -> List[str]:
    return re.findall(r"\d+(?:\.\d+)?", str(s))


def _sentences(text) -> List[str]:
    return [p for p in re.split(r"(?<=[.!?])\s+", (text or "").strip()) if p]


def _has_banned(text) -> bool:
    low = str(text).lower()
    return any(b in low for b in BANNED)


def _words(s) -> set:
    return set(re.findall(r"[a-z]{3,}", str(s).lower()))


def _in_text(value, text) -> bool:
    """True when *value* is stated in *text*: every number of it, or else every word of
    it in any order ('three-year limited manufacturer warranty' matches 'the
    manufacturer warranty is three-year limited')."""
    nums = _numbers(value)
    if nums:
        have = set(_numbers(text))
        return all(n in have for n in nums)
    words = _words(value)
    return bool(words) and words <= _words(text)


def load_models(folder) -> List[dict]:
    try:
        data = json.loads((Path(folder) / "products.json").read_text(encoding="utf-8"))
        return data.get("models") or []
    except Exception:
        return []


def model_for(proposal: dict, models: List[dict]) -> Optional[dict]:
    name = _norm(proposal.get("model", ""))
    for m in models:
        if m.get("model") and _norm(m["model"]) in name:
            return m
    return None


def guard_proposal(p: dict, entry: Optional[dict]) -> dict:
    fixes: List[str] = []
    entry = entry or {}
    confirmed = entry.get("owner_confirmed") or {}
    features = [f for f in (entry.get("features") or []) if f]

    # Item specifics: confirmed values, under one canonical name each.
    specs = dict(p.get("item_specifics") or {})
    for key, value in confirmed.items():
        name = spec_name(key)
        for alias in ALIASES.get(name, [name.lower()]):
            for k in [k for k in specs if k.lower() == alias and k != name]:
                specs.pop(k)
                fixes.append(f"item specific '{k}' replaced by '{name}'")
        if specs.get(name) != value:
            fixes.append(f"item specific {name} set to '{value}'")
            specs[name] = value
    if entry.get("upc") and not specs.get("UPC"):
        specs["UPC"] = entry["upc"]
        fixes.append("item specific UPC added")
    for k in [k for k, v in specs.items() if _has_banned(v) or str(v).strip().lower() in ("", "n/a", "unknown")]:
        specs.pop(k)
        fixes.append(f"item specific '{k}' dropped (no plain value)")
    p["item_specifics"] = specs

    # Condition description: one plain sentence about the condition only.
    cond = _sentences(p.get("condition_description", ""))
    kept = [s for s in cond if not _has_banned(s) and not any(w in s.lower() for w in CONDITION_NOISE)][:1]
    if kept != cond:
        fixes.append("condition description cut to one plain sentence")
    p["condition_description"] = kept[0] if kept else (cond[0] if cond else "")

    # Description: no banned sentences; every confirmed value stated, before the closing condition line.
    desc = _sentences(p.get("description", ""))
    clean = [s for s in desc if not _has_banned(s)]
    if len(clean) != len(desc):
        fixes.append(f"description: {len(desc) - len(clean)} sentence(s) naming a source or hedging removed")
    tail = []
    if clean and p["condition_description"] and _norm(clean[-1]) == _norm(p["condition_description"]):
        tail = [clean.pop()]
    missing = [(spec_name(k), v) for k, v in confirmed.items() if not _in_text(v, " ".join(clean))]
    if missing:
        clean.append("; ".join(f"{n}: {v}" for n, v in missing) + ".")
        fixes.append("description: added " + ", ".join(n for n, _ in missing))
    if p["condition_description"] and not tail and not _in_text(p["condition_description"], " ".join(clean)):
        tail = [p["condition_description"]]
    p["description"] = " ".join(clean + tail)

    # Selling points: the model's features when given, else the drafter's without repeats or banned ones.
    if features:
        points = features[:SELLING_POINTS]
    else:
        points, seen = [], set()
        for s in p.get("selling_points") or []:
            if _has_banned(s) or _norm(s) in seen:
                continue
            seen.add(_norm(s))
            points.append(s)
        points = points[:SELLING_POINTS]
    if points != (p.get("selling_points") or []):
        fixes.append(f"selling points set to {len(points)} ({'products.json features' if features else 'deduplicated'})")
    p["selling_points"] = points

    title = (p.get("title") or "").strip()
    if len(title) > MAX_TITLE:
        title = title[:MAX_TITLE].rsplit(" ", 1)[0]
        fixes.append(f"title cut to {MAX_TITLE} characters")
    p["title"] = title
    if p.get("title_length") != len(title):
        fixes.append(f"title_length corrected to {len(title)}")
    p["title_length"] = len(title)

    flags = [f for f in (p.get("flags") or []) if not _stale(f)]
    if len(points) < SELLING_POINTS:
        flags.append(f"{len(points)} selling points; add sourced features to reach {SELLING_POINTS}.")
    p["flags"] = flags

    p["guard_fixes"] = fixes
    return p


def _stale(s) -> bool:
    low = str(s).lower()
    return ("owner-confirmed" in low or "owner confirmed" in low or "supersed" in low
            or "selling point" in low)


def guard_report(report: dict, models: List[dict]) -> dict:
    for i, p in enumerate(report.get("proposals") or []):
        report["proposals"][i] = guard_proposal(p, model_for(p, models))

    settled = [v for m in models for v in (m.get("owner_confirmed") or {}).values() if _numbers(v)]

    def stale_conflict(s) -> bool:
        # A conflict over a value the owner settled is no longer a conflict.
        return _stale(s) or any(all(n in _numbers(s) for n in _numbers(v)) for v in settled)
    report["conflicts"] = [c for c in (report.get("conflicts") or []) if not stale_conflict(c)]
    report["gaps"] = [g for g in (report.get("gaps") or []) if "selling point" not in str(g).lower()]
    return report


def main(state: Dict[str, Any], *, runtime=None, store=None, **kwargs) -> Dict[str, Any]:
    """Skill code-node entry: guards the report in ``result.llm_result.next_tool_input``."""
    try:
        llm = ((state.get("result") or {}).get("llm_result")) or {}
        nti = llm.get("next_tool_input") or {}
        call = nti.get("input") if isinstance(nti.get("input"), dict) else nti
        report = call.get("report") if isinstance(call, dict) else None
        if not isinstance(report, dict) or not report.get("proposals"):
            logger.info("[draft_guard] no proposals, nothing to check")
            return state
        run_context = (state.get("prompt_refs") or {}).get("run_context") or {}
        models = load_models(run_context.get("product_folder", ""))
        old_titles = [p.get("title") for p in report["proposals"]]
        guard_report(report, models)
        md = call.get("report_md")
        brief = (llm.get("chat_brief") or {}).get("per_model") or []
        for old, p in zip(old_titles, report["proposals"]):
            new = p.get("title")
            if old and new and old != new:
                if isinstance(md, str):
                    md = md.replace(old, new)
                for b in brief:
                    if b.get("title") == old:
                        b["title"] = new
            logger.info(f"[draft_guard] {p.get('model')}: {len(p['guard_fixes'])} fix(es): {p['guard_fixes']}")
        if isinstance(md, str):
            call["report_md"] = md
    except Exception as e:
        logger.warning(f"[draft_guard] error, report saved unchanged: {e!r}")
    return state
