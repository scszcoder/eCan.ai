"""``ec_rules_eval``: run a ruleset (JSON data in ``rulesets/``) over rows.

A rule is data, not code:

    {"id": "gads.neg.no_conv_cost", "entity": "search_term", "id_field": "search_term",
     "when": "conversions == 0 and cost >= t.neg_cost_mult_cpa * ctx.target_cpa",
     "guard": "clicks >= 1",                       # optional sample guard: fails -> "observe"
     "unless": "ctx.in_learning(campaign)",        # optional: true -> skipped (recorded)
     "action": {"type": "negate_keyword", "after": {"term": "{search_term}", "match": "exact"},
                "risk": "low", "required_level": 2},
     "judgment": "'{search_term}' spent {cost} with no conversion (>= {t.neg_cost_mult_cpa}x target CPA)",
     "evidence": ["cost", "clicks", "conversions"]}

Expressions are a small, safe subset of Python: names, numbers, strings, comparisons,
and/or/not, + - * /, ``in``, ``t.<threshold>``, ``ctx.<value>``, ``row.<field>``, and calls to the
functions in ``ctx`` (e.g. ``ctx.in_learning(campaign)``) plus ``lower``, ``len``, ``round``,
``min``/``max``/``abs``, ``contains_any`` and ``first_match``.
Nothing else parses. A missing field is ``None``; ``<``, ``<=``, ``>``, ``>=`` with ``None`` are false (no data is
not "below the threshold"), while ``== None`` / ``!= None`` test for it.
"""
from __future__ import annotations

import ast
import json
import operator
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

RULESET_DIR = Path(__file__).parent / "rulesets"

_BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}
_CMP = {ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt, ast.LtE: operator.le,
        ast.Gt: operator.gt, ast.GtE: operator.ge}


class Namespace:
    def __init__(self, values: Dict[str, Any]):
        self._values = values

    def get(self, name: str) -> Any:
        return self._values.get(name)


def _contains_any(text: Any, words: Any) -> bool:
    s = f" {str(text or '').lower()} "
    return any(re.search(rf"(?<![a-z0-9]){re.escape(str(w).lower())}(?![a-z0-9])", s) for w in words or [])


def _first_match(text: Any, words: Any) -> Optional[str]:
    return next((str(w) for w in words or [] if _contains_any(text, [w])), None)


_BUILTINS: Dict[str, Callable[..., Any]] = {
    "lower": lambda s: str(s or "").lower(),
    "contains_any": _contains_any,
    "first_match": _first_match,
    "round": round,
    "len": lambda v: len(v or []),
    "abs": abs, "min": min, "max": max,
}


@lru_cache(maxsize=512)
def _parse(expr: str) -> ast.Expression:
    tree = ast.parse(expr, mode="eval")
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.UnaryOp, ast.Not, ast.USub,
                                 ast.BinOp, ast.Compare, ast.Name, ast.Load, ast.Constant, ast.Attribute,
                                 ast.Call, ast.List, ast.Tuple, ast.In, ast.NotIn, *_BIN, *_CMP)):
            raise ValueError(f"not allowed in a rule: {type(node).__name__} in {expr!r}")
        if isinstance(node, ast.Attribute) and not (isinstance(node.value, ast.Name)
                                                    and node.value.id in ("t", "ctx", "row")):
            raise ValueError(f"only t./ctx./row. attributes are allowed: {expr!r}")
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            raise ValueError(f"private names are not allowed: {expr!r}")
    return tree


def evaluate(expr: str, row: Dict[str, Any], t: Dict[str, Any], ctx: Dict[str, Any]) -> Any:
    scopes = {"t": Namespace(t), "ctx": Namespace(ctx), "row": Namespace(row)}

    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, (ast.List, ast.Tuple)):
            return [ev(e) for e in node.elts]
        if isinstance(node, ast.Name):
            if node.id in scopes:
                return scopes[node.id]
            if node.id in _BUILTINS:
                return _BUILTINS[node.id]
            if node.id in ("True", "False", "None"):
                return {"True": True, "False": False, "None": None}[node.id]
            return row.get(node.id)
        if isinstance(node, ast.Attribute):
            return ev(node.value).get(node.attr)
        if isinstance(node, ast.BoolOp):
            vals = (ev(v) for v in node.values)
            return all(vals) if isinstance(node.op, ast.And) else any(vals)
        if isinstance(node, ast.UnaryOp):
            v = ev(node.operand)
            if isinstance(node.op, ast.Not):
                return not v
            return None if v is None else -v
        if isinstance(node, ast.BinOp):
            a, b = ev(node.left), ev(node.right)
            if a is None or b is None:
                return None
            if isinstance(node.op, ast.Div) and not b:
                return None
            return _BIN[type(node.op)](a, b)
        if isinstance(node, ast.Compare):
            left = ev(node.left)
            for op, comp in zip(node.ops, node.comparators):
                right = ev(comp)
                if isinstance(op, (ast.In, ast.NotIn)):
                    ok = right is not None and left in right
                    ok = ok if isinstance(op, ast.In) else not ok
                elif isinstance(op, (ast.Eq, ast.NotEq)):
                    ok = _CMP[type(op)](left, right)
                else:
                    if left is None or right is None:
                        return False
                    ok = _CMP[type(op)](left, right)
                if not ok:
                    return False
                left = right
            return True
        if isinstance(node, ast.Call):
            fn = ev(node.func)
            if not callable(fn):
                raise ValueError(f"not a function in a rule: {ast.dump(node.func)}")
            return fn(*[ev(a) for a in node.args])
        raise ValueError(f"unsupported: {type(node).__name__}")

    return ev(_parse(expr))


def _fmt(template: str, row: Dict[str, Any], t: Dict[str, Any], ctx: Dict[str, Any]) -> str:
    def sub(m):
        path = m.group(1)
        if path.startswith("t."):
            v = t.get(path[2:])
        elif path.startswith("ctx."):
            v = ctx.get(path[4:])
        else:
            v = row.get(path)
        if isinstance(v, float):
            return f"{v:.2f}".rstrip("0").rstrip(".")
        return "" if v is None else str(v)
    return re.sub(r"\{([A-Za-z_][A-Za-z0-9_.]*)\}", sub, template or "")


def _fill(obj: Any, row, t, ctx) -> Any:
    """Fill templates inside an action's ``after``. A value that is exactly "{field}" keeps its type."""
    if isinstance(obj, str):
        m = re.fullmatch(r"\{([A-Za-z_][A-Za-z0-9_.]*)\}", obj)
        if m and not m.group(1).startswith(("t.", "ctx.")):
            return row.get(m.group(1))
        return _fmt(obj, row, t, ctx)
    if isinstance(obj, dict):
        if set(obj) == {"expr"}:
            return evaluate(obj["expr"], row, t, ctx)
        return {k: _fill(v, row, t, ctx) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_fill(v, row, t, ctx) for v in obj]
    return obj


@lru_cache(maxsize=None)
def load_ruleset(ruleset_id: str) -> Dict[str, Any]:
    path = RULESET_DIR / f"{ruleset_id}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    for rule in data.get("rules") or []:      # parse every expression now, so a bad ruleset fails loudly
        for key in ("when", "guard", "unless"):
            if rule.get(key):
                _parse(rule[key])
    return data


def run(ruleset: Dict[str, Any], tables: Dict[str, List[Dict[str, Any]]], t: Dict[str, Any],
        ctx: Optional[Dict[str, Any]] = None, rule_ids: Optional[List[str]] = None,
        mode: Optional[str] = None) -> Dict[str, Any]:
    """Evaluate every rule over the rows of its ``table``.

    Returns {"matches": [...], "observe": [...], "skipped": [...]}: a match passed ``when`` and
    its sample guard; ``observe`` passed ``when`` but not the guard (too little data to act);
    ``skipped`` matched but an ``unless`` held (e.g. the campaign is still learning). With
    ``mode``, only rules listing that mode in ``modes`` run.
    """
    ctx = ctx or {}
    out: Dict[str, List[Dict[str, Any]]] = {"matches": [], "observe": [], "skipped": []}
    for rule in ruleset.get("rules") or []:
        if rule_ids and rule["id"] not in rule_ids:
            continue
        if mode and rule.get("modes") and mode not in rule["modes"]:
            continue
        for row in tables.get(rule["table"]) or []:
            if not evaluate(rule["when"], row, t, ctx):
                continue
            entity_id = row.get(rule.get("id_field") or "id")
            item = {"rule_id": rule["id"], "entity": {"type": rule["entity"], "id": str(entity_id),
                                                       **({"name": str(row[rule["name_field"]])}
                                                          if rule.get("name_field") and row.get(rule["name_field"])
                                                          else {})},
                    "judgment": _fmt(rule.get("judgment", ""), row, t, ctx),
                    "evidence": {f: row.get(f) for f in rule.get("evidence") or []},
                    "row": row}
            if rule.get("unless") and evaluate(rule["unless"], row, t, ctx):
                out["skipped"].append({**item, "reason": rule.get("unless_reason") or rule["unless"]})
                continue
            if rule.get("guard") and not evaluate(rule["guard"], row, t, ctx):
                out["observe"].append({**item, "reason": "below the minimum sample: " + rule["guard"]})
                continue
            if rule.get("action"):
                item["action"] = _fill(rule["action"], row, t, ctx)
            out["matches"].append(item)
    return out
