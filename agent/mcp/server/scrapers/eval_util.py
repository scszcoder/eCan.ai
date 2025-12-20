from __future__ import annotations
import ast
import math
from typing import Any, Dict, List, Tuple, Optional
from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback
# -----------------------------
# Safe expression evaluation
# -----------------------------
_ALLOWED_FUNCS = {
    "abs": abs, "min": min, "max": max, "round": round,
    "floor": math.floor, "ceil": math.ceil, "sqrt": math.sqrt, "log": math.log,
    "log10": math.log10, "exp": math.exp, "pow": pow, "sin": math.sin,
    "cos": math.cos, "tan": math.tan, "pi": math.pi, "e": math.e
}
_ALLOWED_NODES = {
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.Num, ast.Name, ast.Load, ast.Call,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod, ast.FloorDiv,
    ast.USub, ast.UAdd, ast.Constant, ast.Tuple
}


def _safe_eval(expr: str, names: Dict[str, float]) -> float:
    """
    Evaluate a simple arithmetic expression safely with a restricted AST.
    Names come from the search item and a few convenience entries (like 'value').
    """
    if not expr or not expr.strip():
        raise ValueError("Empty expression")
    node = ast.parse(expr, mode="eval")

    def _check(n: ast.AST):
        if type(n) not in _ALLOWED_NODES:
            raise ValueError(f"Disallowed expression node: {type(n).__name__}")
        for child in ast.iter_child_nodes(n):
            _check(child)

    _check(node)

    def _eval(n: ast.AST) -> float:
        if isinstance(n, ast.Expression):
            return _eval(n.body)
        if isinstance(n, ast.Constant):  # py>=3.8
            if isinstance(n.value, (int, float)):
                return float(n.value)
            raise ValueError("Only numeric constants allowed")
        if isinstance(n, ast.Num):  # py<3.8
            return float(n.n)
        if isinstance(n, ast.Name):
            if n.id in names:
                return float(names[n.id])
            if n.id in _ALLOWED_FUNCS:
                return _ALLOWED_FUNCS[n.id]
            raise ValueError(f"Unknown variable: {n.id}")
        if isinstance(n, ast.UnaryOp):
            val = _eval(n.operand)
            if isinstance(n.op, ast.UAdd):  return +val
            if isinstance(n.op, ast.USub):  return -val
            raise ValueError("Unsupported unary operator")
        if isinstance(n, ast.BinOp):
            left, right = _eval(n.left), _eval(n.right)
            if isinstance(n.op, ast.Add):      return left + right
            if isinstance(n.op, ast.Sub):      return left - right
            if isinstance(n.op, ast.Mult):     return left * right
            if isinstance(n.op, ast.Div):      return left / right
            if isinstance(n.op, ast.FloorDiv): return left // right
            if isinstance(n.op, ast.Mod):      return left % right
            if isinstance(n.op, ast.Pow):      return left ** right
            raise ValueError("Unsupported binary operator")
        if isinstance(n, ast.Call):
            func = _eval(n.func)
            if func not in _ALLOWED_FUNCS.values():
                raise ValueError("Function not allowed")
            args = [_eval(a) for a in n.args]
            return float(func(*args))
        raise ValueError(f"Unsupported expression element: {type(n).__name__}")

    return float(_eval(node))


# -----------------------------
# Helpers
# -----------------------------
def _to_float_or_none(x: Any) -> Optional[float]:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _linear_interp_extrapolate(x: float, lut: Dict[str, Any]) -> float:
    """
    Piecewise-linear interpolation/extrapolation on a LUT mapping x->y.
    Keys in lut can be str or numeric; we coerce to floats.
    """
    points: List[Tuple[float, float]] = []
    for k, v in lut.items():
        xk = _to_float_or_none(k)
        yk = _to_float_or_none(v)
        if xk is None or yk is None:
            continue
        points.append((xk, yk))
    if not points:
        raise ValueError("Empty or invalid score_lut")

    points.sort(key=lambda t: t[0])
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]

    if len(points) == 1:
        return ys[0]

    # Left extrapolation
    if x <= xs[0]:
        x0, y0 = xs[0], ys[0]
        x1, y1 = xs[1], ys[1]
        return y0 + (y1 - y0) * ((x - x0) / (x1 - x0))
    # Right extrapolation
    if x >= xs[-1]:
        x0, y0 = xs[-2], ys[-2]
        x1, y1 = xs[-1], ys[-1]
        return y0 + (y1 - y0) * ((x - x0) / (x1 - x0))

    # Interpolation in between
    # Find segment [i, i+1] with xs[i] <= x <= xs[i+1]
    lo, hi = 0, len(xs) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if xs[mid] == x:
            return ys[mid]
        if xs[mid] < x:
            lo = mid + 1
        else:
            hi = mid - 1
    i = max(0, hi)
    x0, x1 = xs[i], xs[i + 1]
    y0, y1 = ys[i], ys[i + 1]
    if x1 == x0:
        return y0
    t = (x - x0) / (x1 - x0)
    return y0 + t * (y1 - y0)


def _collect_context_from_item(item: Dict[str, Any]) -> Dict[str, float]:
    """
    Create a flat variable context from the item for formula evaluation.
    - Pull top-level numeric fields.
    - If the item contains a nested FOM-like structure (components), also flatten those names -> raw_value.
    """
    ctx: Dict[str, float] = {}

    def add_num_dict(d: Dict[str, Any]):
        for k, v in d.items():
            if isinstance(v, (int, float)):
                ctx[k] = float(v)

    # Top-level
    add_num_dict(item)

    # Nested common patterns
    # 1) item['fom']['components'] style
    def add_components(comps: Any):
        if isinstance(comps, list):
            for comp in comps:
                name = comp.get("name")
                rv = comp.get("raw_value")
                if name and isinstance(rv, (int, float)):
                    ctx[name] = float(rv)
                elif isinstance(rv, dict):
                    # subcomponents
                    for sub_name, sub in rv.items():
                        sub_rv = (sub or {}).get("raw_value")
                        if isinstance(sub_rv, (int, float)):
                            # add by sub_name
                            ctx[sub_name] = float(sub_rv)

    if isinstance(item.get("fom"), dict):
        add_components(item["fom"].get("components", []))
    if isinstance(item.get("components"), list):
        add_components(item["components"])

    logger.debug("[eval_util] _collect_context_from_item", ctx)
    return ctx


def _find_item_value_for_component(item: Dict[str, Any], comp: Dict[str, Any]) -> Optional[float]:
    """
    Heuristics to get the item's numeric value for a component:
    1) item[comp['name']]
    2) item['fom']['components'][name].raw_value
    3) item['components'][name].raw_value
    4) fallback: comp['raw_value'] (from the template)
    """
    name = comp.get("name")
    if name in item and isinstance(item[name], (int, float)):
        return float(item[name])

    # Scan item['fom']['components']
    def find_in_components(comps):
        if not isinstance(comps, list): return None
        for c in comps:
            if c.get("name") == name:
                rv = c.get("raw_value")
                if isinstance(rv, (int, float)):
                    return float(rv)
        return None

    if isinstance(item.get("fom"), dict):
        v = find_in_components(item["fom"].get("components"))
        if v is not None:
            return v

    if isinstance(item.get("components"), list):
        v = find_in_components(item["components"])
        if v is not None:
            return v

    # Fallback to template's raw_value
    rv = comp.get("raw_value")
    if isinstance(rv, (int, float)):
        return float(rv)

    return None


def _score_leaf_component(
        item: Dict[str, Any],
        comp: Dict[str, Any],
        global_ctx: Dict[str, float],
) -> Optional[float]:
    """
    Score a leaf component using formula OR LUT.
    - If formula present (non-empty), use it.
    - Else if LUT non-empty, use piecewise-linear interpolation/extrapolation on 'value'.
    - 'value' is determined by _find_item_value_for_component().
    Returns None if cannot score.
    """
    formula = (comp.get("score_formula") or "").strip()
    lut = comp.get("score_lut") or {}
    value = _find_item_value_for_component(item, comp)

    if formula:
        if value is not None:
            # Offer both the component's name and a generic 'value' to formulas
            ctx = dict(global_ctx)
            if comp.get("name"):
                ctx[comp["name"]] = value
            ctx["value"] = value
        else:
            # No specific value; formulas may rely purely on global_ctx constants/other fields
            ctx = dict(global_ctx)

        try:
            return _safe_eval(formula, ctx)
        except Exception:
            return None

    # LUT path
    if lut and value is not None:
        try:
            return _linear_interp_extrapolate(value, lut)
        except Exception:
            return None

    return None


def _normalize_weights(weights: List[float]) -> List[float]:
    if not weights:
        return []
    s = sum(w for w in weights if w is not None)
    if s <= 0:
        # equal weights
        n = len(weights)
        return [1.0 / n] * n
    return [(w if w is not None else 0.0) / s for w in weights]


def _score_component(
        item: Dict[str, Any],
        comp: Dict[str, Any],
        global_ctx: Dict[str, float],
) -> Optional[float]:
    """
    Score a component, handling nested subcomponents if comp['raw_value'] is a dict.
    If nested, compute weighted combination of sub-scores.
    """
    rv = comp.get("raw_value")
    # Nested subcomponents?
    if isinstance(rv, dict):
        sub_names = list(rv.keys())
        sub_scores: List[Optional[float]] = []
        sub_weights: List[float] = []
        for sub_name in sub_names:
            print("sub_name", sub_name)
            sub_comp = dict(rv[sub_name] or {})
            sub_comp.setdefault("name", sub_name)
            sc = _score_leaf_component(item, sub_comp, global_ctx)
            sub_scores.append(sc)
            sub_weights.append(_to_float_or_none(sub_comp.get("weight")) or 0.0)

        # Normalize weights (if all zero, fall back to equal weighting on available subs)
        non_null_scores = [s for s in sub_scores if s is not None]
        if not non_null_scores:
            return None

        # If all provided weights are zero/missing, use equal weights among non-null subs
        if sum(sub_weights) == 0:
            # distribute equally across scored subs
            cnt = sum(1 for s in sub_scores if s is not None)
            norm = [(1.0 / cnt if sub_scores[i] is not None else 0.0) for i in range(len(sub_scores))]
        else:
            # normalize over all, but zeros remain zero (unscored will be zero weight)
            norm = _normalize_weights(sub_weights)

        total = 0.0
        for i, s in enumerate(sub_scores):
            if s is None:
                continue
            total += norm[i] * s
        return total

    # Leaf component:
    return _score_leaf_component(item, comp, global_ctx)


def calculate_score(fom: Dict[str, Any], items: List[Dict[str, Any]], clamp: bool = False) -> List[Dict[str, Any]]:
    """
    Mutates and returns the items list, adding 'score' to each item.

    Assumptions / behavior:
    - Each item may hold raw fields referenced by score formulas (e.g., 'price', 'speed', 'current').
    - If an item doesn't provide a needed field, we fall back to the FOM template's 'raw_value'.
    - For nested components, subcomponent weights are respected; same at top-level.
    - If clamp=True, final score is clamped to [0, 100].
    """
    try:
        logger.debug("[eval_util] calculate_score", fom, items)
        components = fom.get("components", []) or []

        for item in items:
            # Build a variable context once per item for formula evaluation
            ctx = _collect_context_from_item(item)

            comp_scores: List[Optional[float]] = []
            comp_weights: List[float] = []

            print("Item:", item)
            for comp in components:
                print("comp", comp)
                s = _score_component(item, comp, ctx)
                print("score:", s)
                comp_scores.append(s)
                comp_weights.append(_to_float_or_none(comp.get("weight")) or 0.0)

            # Combine top-level
            # If no scores at all, skip
            if not any(s is not None for s in comp_scores):
                item["score"] = None
                continue

            if sum(comp_weights) == 0:
                # equal weighting among components that produced a score
                cnt = sum(1 for s in comp_scores if s is not None)
                print("cnt", cnt)

    except Exception as e:
        err_trace = get_traceback(e, "ErrorCalculateScores")
        logger.debug(err_trace)


def get_default_fom_form():
    return {
        "id": "eval_system_form",
        "type": "score",
        "title": "score system",
        "components": [
            {
                "name": "price",
                "type": "integer",
                "raw_value": 125,
                "target_value": 125,
                "max_value": 150,
                "min_value": 0,
                "unit": "cents",
                "tooltip": "unit price in cents, 1.25 is the target max price",
                "score_formula": "80 + (125-price)",
                "score_lut": {},
                "weight": 0.3
            },
            {
                "name": "availability",
                "type": "integer",
                "raw_value": 0,
                "target_value": 0,
                "max_value": 150,
                "min_value": 0,
                "unit": "days",
                "tooltip": "nuber of days before the part is available",
                "score_formula": "",
                "score_lut": {
                    "20": 100,
                    "10": 80,
                    "8": 60
                },
                "weight": 0.3
            },
            {
                "name": "performance",
                "type": "integer",
                "raw_value": {
                    "power": {
                        "raw_value": 3,
                        "target_value": 125,
                        "type": "integer",
                        "unit": "mA",
                        "tooltip": "power consumption in mA",
                        "score_formula": "80 + (5-current)",
                        "score_lut": {},
                        "weight": 0.7
                    },
                    "clock_rate": {
                        "raw_value": 10,
                        "target_value": 125,
                        "max_value": 120,
                        "min_value": 0,
                        "type": "integer",
                        "unit": "MHz",
                        "tooltip": "max clock speed in MHz",
                        "score_formula": "80 + (speed - 10)",
                        "score_lut": {},
                        "weight": 0.3
                    }
                },
                "unit": "",
                "tooltip": "technical performance",
                "score_formula": "100 - 5*performance",
                "score_lut": {},
                "weight": 0.4
            }
        ]
    }

def get_default_rerank_req():
    return {
        # "agent_id": "agent-001",
        # "work_type": "rerank_search_results",
        # "setup": {
            "fom_form": {
                "id": "eval_system_form",
                "type": "score",
                "title": "LDO under search",
                "components": [
                    {
                        "name": "Price",
                        "type": "integer",
                        "raw_value": 125,
                        "target_value": 125,
                        "max_value": 150,
                        "min_value": 0,
                        "unit": "cents",
                        "tooltip": "unit price in cents, 1.25 is the target max price",
                        "score_formula": "80 + (125-price)",
                        "score_lut": {},
                        "weight": 0.3,
                        "_lutRowIds": {}
                    },
                    {
                        "name": "Quantity Available",
                        "type": "integer",
                        "raw_value": 0,
                        "target_value": 0,
                        "max_value": 150,
                        "min_value": 0,
                        "unit": "days",
                        "tooltip": "lead time/availablility of the component",
                        "score_formula": "",
                        "score_lut": {
                            "8": 60,
                            "10": 80,
                            "20": 100
                        },
                        "weight": 0.3,
                        "_lutRowIds": {
                            "8": "8g7zjodrk451758232319331",
                            "10": "mcfhb1odoyk1758232319331",
                            "20": "03te3shcn4o41758232319331"
                        }
                    },
                    {
                        "name": "performance",
                        "type": "integer",
                        "raw_value": {
                            "Voltage - Output (Min/Fixed)": {
                                "name": "Voltage - Output (Min/Fixed)",
                                "type": "integer",
                                "raw_value": 0,
                                "target_value": 0,
                                "max_value": 100,
                                "min_value": 0,
                                "unit": "",
                                "tooltip": "",
                                "score_formula": "min(max((Voltage_Output_Min - 2.5) / (3.0 - 2.5) * 100, 0), 100)",
                                "score_lut": {},
                                "weight": 0.4,
                                "_lutRowIds": {}
                            },
                            "Voltage - Output (Max)": {
                                "name": "Voltage - Output (Max)",
                                "type": "integer",
                                "raw_value": 0,
                                "target_value": 0,
                                "max_value": 100,
                                "min_value": 0,
                                "unit": "",
                                "tooltip": "",
                                "score_formula": "min(max((Voltage_Output_Max - 3.5) / (3.0 - 3.5) * 100, 0),100)",
                                "score_lut": {},
                                "weight": 0.3,
                                "_lutRowIds": {}
                            },
                            "Current - Output": {
                                "name": "Current - Output",
                                "type": "integer",
                                "raw_value": 0,
                                "target_value": 0,
                                "max_value": 100,
                                "min_value": 0,
                                "unit": "",
                                "tooltip": "",
                                "score_formula": "min(max((Current_Output - 500) / (1000 - 500) * 100,0),100)",
                                "score_lut": {},
                                "weight": 0.3,
                                "_lutRowIds": {}
                            }
                        },
                        "weight": 0.4
                    }
                ],
                "text": "Here is a figure of merit (FOM) form to aid searching the parts you're looking for, please try your best to fill it out and send back to me. if you're not sure about certain parameters, just leave them blank. Also feel free to ask any questions about the meaning and implications of any parameters you're not sure about."
            },
            "rows": [
                {
                    "Price": "Obsolete",
                    "Quantity Available": "0 In Stock",
                    "Voltage - Output (Min/Fixed)": "2.5V",
                    "Voltage - Output (Max)": "12V",
                    "Current - Output": "50mA"
                },
                {
                    "Price": "1,000 : $1.43750 Tape & Reel (TR)",
                    "Quantity Available": "0 In Stock",
                    "Voltage - Output (Min/Fixed)": "1.223V",
                    "Voltage - Output (Max)": "12V",
                    "Current - Output": "150mA"
                },
                {
                    "Price": "Obsolete",
                    "Quantity Available": "0 In Stock",
                    "Voltage - Output (Min/Fixed)": "1.223V",
                    "Voltage - Output (Max)": "12V",
                    "Current - Output": "50mA"
                },
                {
                    "Price": "Obsolete",
                    "Quantity Available": "0 In Stock",
                    "Voltage - Output (Min/Fixed)": "0.8V",
                    "Voltage - Output (Max)": "5V",
                    "Current - Output": "1A"
                }
            ],
            "component_info": [
                {
                    "part name": "LDO",
                    "oems": [
                        "NA"
                    ],
                    "model_part_numbers": [
                        "NA"
                    ],
                    "applications_usage": "12V to 3V usb hand warmer",
                    "usage_grade": "NA"
                }
            ]
        # }
    }