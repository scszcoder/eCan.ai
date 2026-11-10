"""The one place metric formulas live (spec P2, P9), and unit economics (X-03).

A ratio whose denominator is zero is ``None``, never 0 or infinity: "no clicks yet" and
"0% conversion" are different statements.
"""
from __future__ import annotations

from collections import OrderedDict
from typing import Any, Dict, Iterable, List, Optional, Sequence

SUM_FIELDS = ("impressions", "clicks", "cost", "conversions", "conv_value", "orders", "sales", "sessions",
              "units", "spend", "add_to_cart", "begin_checkout", "purchase", "view_item")


def ratio(num: Optional[float], den: Optional[float]) -> Optional[float]:
    if num is None or not den:
        return None
    return num / den


def derive(t: Dict[str, Any]) -> Dict[str, Any]:
    """Derived metrics from summed fields. ``cost`` and ``spend`` are the same thing."""
    cost = t.get("cost") if t.get("cost") is not None else t.get("spend")
    conv = t.get("conversions") if t.get("conversions") is not None else t.get("orders")
    value = t.get("conv_value") if t.get("conv_value") is not None else t.get("sales")
    return {
        "ctr": ratio(t.get("clicks"), t.get("impressions")),
        "cpc": ratio(cost, t.get("clicks")),
        "cvr": ratio(conv, t.get("clicks")),
        "cpa": ratio(cost, conv),
        "roas": ratio(value, cost),
        "acos": ratio(cost, value),
        "aov": ratio(value, conv),
    }


def totals(rows: Iterable[Dict[str, Any]], fields: Sequence[str] = SUM_FIELDS) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for r in rows:
        for f in fields:
            v = r.get(f)
            if isinstance(v, (int, float)):
                out[f] = out.get(f, 0) + v
    out.update(derive(out))
    return out


def group(rows: Iterable[Dict[str, Any]], keys: Sequence[str], fields: Sequence[str] = SUM_FIELDS
          ) -> List[Dict[str, Any]]:
    """Sum ``fields`` per distinct ``keys`` and add the derived metrics."""
    buckets: "OrderedDict[tuple, List[Dict[str, Any]]]" = OrderedDict()
    for r in rows:
        buckets.setdefault(tuple(r.get(k) for k in keys), []).append(r)
    return [{**dict(zip(keys, k)), **totals(rs, fields), "_rows": len(rs)} for k, rs in buckets.items()]


def unit_economics(price: float, cogs: float, *, shipping: float = 0.0, payment_fee_pct: float = 0.0,
                   payment_fee_fixed: float = 0.0, platform_fee_pct: float = 0.0, return_pct: float = 0.0,
                   promo_pct: float = 0.0, other: float = 0.0) -> Dict[str, Any]:
    """Per-unit margin before ads, and the ROAS / ACOS at which ads break even.

    ``price`` is what the buyer pays for the item. Returns lose the margin on ``return_pct``
    of units (a simple, conservative model: the item value is not recovered).
    """
    promo = price * promo_pct
    revenue = price - promo
    fees = revenue * (payment_fee_pct + platform_fee_pct) + payment_fee_fixed
    returns = revenue * return_pct
    margin = revenue - cogs - shipping - fees - returns - other
    margin_pct = ratio(margin, revenue)
    return {
        "revenue": round(revenue, 4), "fees": round(fees, 4), "returns_cost": round(returns, 4),
        "margin_before_ads": round(margin, 4), "margin_pct": None if margin_pct is None else round(margin_pct, 4),
        # Ads can spend up to the margin per sale: spend/revenue = margin_pct -> ROAS = 1/margin_pct.
        "breakeven_acos": None if margin_pct is None else round(margin_pct, 4),
        "breakeven_roas": None if not margin_pct or margin_pct <= 0 else round(1 / margin_pct, 4),
        "breakeven_cpa": round(margin, 4) if margin > 0 else None,
        "profitable_before_ads": margin > 0,
    }


def blended_breakeven_roas(products: Iterable[Dict[str, Any]]) -> Optional[float]:
    """Revenue-weighted break-even ROAS over products with ``revenue`` and ``margin_before_ads``
    (both totals for the window). None when the blend loses money before ads."""
    rev = sum(p.get("revenue") or 0 for p in products)
    margin = sum(p.get("margin_before_ads") or 0 for p in products)
    if rev <= 0 or margin <= 0:
        return None
    return round(rev / margin, 4)
