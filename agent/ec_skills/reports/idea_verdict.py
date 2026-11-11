"""Product-idea verdict: will this marketplace product make or lose money?

The interviewer collects the customer's numbers and the market check reads
competitor prices and reviews; this module does the arithmetic, so the verdict
is the same for the same inputs and never depends on how the model felt.

Three scenarios, all over ``months`` (default 12):
  claimed       the customer's own price and sales;
  base          the customer's price, 60% of the sales they expect;
  conservative  10% lower price (coupons, price war), 35% of the sales,
                ads 1.5x and returns 1.5x.
The verdict is DROP unless the conservative case at least breaks even, the base
case keeps a 15% margin and the peak cash fits the money the customer has.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

# Assumptions when the customer does not know a number (Amazon US, mid-size item).
DEFAULTS = {
    "referral_pct": 0.15,          # Amazon referral fee, most categories
    "fulfillment_fee": 5.50,       # FBA fee per unit for a small standard item
    "storage_per_unit_month": 0.30,
    "return_rate": 0.06,
    "ad_pct_of_price": 0.25,       # ad spend per unit sold, as a share of price, at launch
    "duty_pct": 0.0,
    "freight_per_unit": 0.0,
    "launch_budget": 1500.0,       # samples, photos, trademark, listing
    "months": 12,
    "months_in_stock": 2.0,        # average months a unit sits in storage before it sells
}
RAMP = (0.3, 0.6)                  # share of the monthly rate in the first two months
MIN_BASE_MARGIN = 0.15

SCENARIOS = {
    "claimed": {"price": 1.0, "units": 1.0, "ads": 1.0, "returns": 1.0},
    "base": {"price": 1.0, "units": 0.6, "ads": 1.0, "returns": 1.0},
    "conservative": {"price": 0.9, "units": 0.35, "ads": 1.5, "returns": 1.5},
}


def _num(v: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if v is None or v == "":
            return default
        return float(str(v).replace("$", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return default


def _inputs(idea: Dict[str, Any]) -> Dict[str, float]:
    """The numbers the model uses: the customer's answers, else the defaults."""
    out = {k: _num(idea.get(k), d) for k, d in DEFAULTS.items()}
    for k in ("sale_price", "unit_cost", "monthly_units", "first_order_units", "cash_available"):
        out[k] = _num(idea.get(k))
    if out["first_order_units"] is None and out["monthly_units"]:
        out["first_order_units"] = round(out["monthly_units"] * 3)
    return out


def _months_of_sales(months: float) -> float:
    """Selling months after the launch ramp."""
    m = int(months)
    return sum(RAMP[:m]) + max(m - len(RAMP), 0)


def scenario(x: Dict[str, float], factors: Dict[str, float]) -> Dict[str, float]:
    price = x["sale_price"] * factors["price"]
    landed = x["unit_cost"] * (1 + x["duty_pct"]) + x["freight_per_unit"]
    fees = price * x["referral_pct"] + x["fulfillment_fee"]
    ads = price * x["ad_pct_of_price"] * factors["ads"]
    storage = x["storage_per_unit_month"] * x["months_in_stock"]
    returns = x["return_rate"] * factors["returns"] * (landed + x["fulfillment_fee"])
    per_unit = price - landed - fees - ads - storage - returns
    units = x["monthly_units"] * factors["units"] * _months_of_sales(x["months"])
    unsold = max((x["first_order_units"] or 0) - units, 0)
    writeoff = unsold * landed          # stock left over from the first order, assumed unsellable
    profit = per_unit * units - x["launch_budget"] - writeoff
    peak_cash = x["launch_budget"] + (x["first_order_units"] or 0) * landed + 2 * x["monthly_units"] * factors["units"] * ads
    return {"price": round(price, 2), "landed_cost": round(landed, 2), "fees": round(fees, 2),
            "ads": round(ads, 2), "returns": round(returns, 2), "storage": round(storage, 2),
            "profit_per_unit": round(per_unit, 2), "margin": round(per_unit / price, 3) if price else 0.0,
            "units": round(units), "unsold_first_order": round(unsold), "writeoff": round(writeoff, 2),
            "profit": round(profit, 2), "peak_cash": round(peak_cash, 2)}


def _break_even_price(x: Dict[str, float]) -> float:
    """Conservative-case price at which the horizon's profit is zero (bisection)."""
    lo, hi = 0.0, max(x["sale_price"] * 10, 1.0)
    for _ in range(60):
        mid = (lo + hi) / 2
        y = dict(x, sale_price=mid / SCENARIOS["conservative"]["price"])
        if scenario(y, SCENARIOS["conservative"])["profit"] < 0:
            lo = mid
        else:
            hi = mid
    return round(hi, 2)


def _market_reasons(x: Dict[str, float], idea: Dict[str, Any], market: Dict[str, Any]) -> List[str]:
    """What the competitor listings say against the customer's plan."""
    reasons: List[str] = []
    median = _num(market.get("price_median"))
    if median and x["sale_price"] > median * 1.25 and not str(idea.get("differentiation") or "").strip():
        reasons.append(f"You plan ${x['sale_price']:,.2f}, {x['sale_price'] / median - 1:.0%} above the median "
                       f"competitor (${median:,.2f}), with nothing that sets your product apart.")
    if median and median < x["sale_price"] * 0.8:
        reasons.append(f"Competitors sell at a median ${median:,.2f}; at that price your conservative case is worse still.")
    ratings = _num(market.get("ratings_count_median"))
    if str(market.get("competition") or "").lower() == "high" and ratings and ratings >= 1000:
        reasons.append(f"The leaders have a median of {ratings:,.0f} ratings; a new listing starts at zero "
                       "and needs months of ad spend to be seen next to them.")
    return reasons


def evaluate(idea: Dict[str, Any], market: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The verdict for one idea: ``{"verdict", "reasons", "scenarios", ...}``.
    ``market`` is the review-mining step's market summary, when there is one."""
    x = _inputs(idea)
    missing = [k for k in ("sale_price", "unit_cost", "monthly_units") if not x.get(k)]
    if missing:
        return {"verdict": "INCOMPLETE", "missing": missing,
                "reasons": [f"Cannot judge the idea without: {', '.join(missing)}."]}
    runs = {name: scenario(x, f) for name, f in SCENARIOS.items()}
    cons, base = runs["conservative"], runs["base"]
    reasons: List[str] = []
    if cons["profit"] < 0:
        reasons.append(f"In the conservative case you lose ${-cons['profit']:,.0f} over {int(x['months'])} months.")
    if base["margin"] < MIN_BASE_MARGIN:
        reasons.append(f"Even the base case keeps only {base['margin']:.0%} of the price per unit "
                       f"(needs {MIN_BASE_MARGIN:.0%}): one fee rise or price cut wipes it out.")
    if base["profit_per_unit"] <= 0:
        reasons.append(f"Every unit sold loses ${-base['profit_per_unit']:.2f} before launch costs.")
    if x.get("cash_available") is not None and cons["peak_cash"] > x["cash_available"]:
        reasons.append(f"It needs about ${cons['peak_cash']:,.0f} in cash before sales pay back; "
                       f"you said you have ${x['cash_available']:,.0f}.")
    reasons += _market_reasons(x, idea, market or {})
    if cons["unsold_first_order"]:
        reasons.append(f"At conservative sales, {cons['unsold_first_order']} units of the first order "
                       f"are still unsold after {int(x['months'])} months.")
    # The base case is the expected outcome; when it still makes money, the
    # conservative case is the loss to warn about.
    if base["profit"] < 0:
        loss, loss_kind = -base["profit"], "expected"
    elif cons["profit"] < 0:
        loss, loss_kind = -cons["profit"], "possible"
    else:
        loss, loss_kind = 0.0, ""
    losses = [-r["profit"] for r in runs.values() if r["profit"] < 0]
    return {
        "verdict": "DROP" if reasons else "WORKS ON PAPER",
        "expected_loss": round(loss, 2),
        "loss_kind": loss_kind,
        "loss_range": [round(min(losses), 2), round(max(losses), 2)] if losses else [],
        "reasons": reasons,
        "scenarios": runs,
        "break_even_price": _break_even_price(x),
        "assumptions": {k: x[k] for k in DEFAULTS if _num(idea.get(k)) is None},
        "inputs": {k: v for k, v in x.items() if v is not None},
    }


def _money(v: float) -> str:
    return f"-${-v:,.0f}" if v < 0 else f"${v:,.0f}"


def render_markdown(idea: Dict[str, Any], result: Dict[str, Any], market: Optional[Dict[str, Any]] = None) -> str:
    name = idea.get("idea") or "Product idea"
    if result["verdict"] == "INCOMPLETE":
        return f"# {name}: no verdict\n\n" + "\n".join(f"- {r}" for r in result["reasons"]) + "\n"
    if result["verdict"] != "DROP":
        head = "# Works on paper, even in the conservative case"
    elif result["expected_loss"]:
        verb = "expect to lose" if result["loss_kind"] == "expected" else "you could lose"
        lo, hi = result["loss_range"]
        span = f" (between ${lo:,.0f} and ${hi:,.0f} across the scenarios)" if hi > lo else ""
        head = f"# DROP IT: {verb} ${result['expected_loss']:,.0f}{span}"
    else:
        head = "# DROP IT"
    lines = [head, "", f"Idea: {name}", ""]
    if result["reasons"]:
        lines += ["## Why", ""] + [f"- {r}" for r in result["reasons"]] + [""]
    lines += ["## The numbers", "",
              "| | claimed | base | conservative |", "|---|---|---|---|"]
    rows = [("Price", "price", "$"), ("Landed cost / unit", "landed_cost", "$"), ("Fees / unit", "fees", "$"),
            ("Ads / unit", "ads", "$"), ("Returns / unit", "returns", "$"), ("Profit / unit", "profit_per_unit", "$"),
            ("Margin", "margin", "%"), ("Units sold", "units", ""), ("Unsold first order", "unsold_first_order", ""),
            ("Profit over the period", "profit", "M"), ("Peak cash needed", "peak_cash", "M")]
    sc = result["scenarios"]
    for label, key, kind in rows:
        vals = [sc[s][key] for s in ("claimed", "base", "conservative")]
        fmt = {"$": lambda v: f"${v:,.2f}", "%": lambda v: f"{v:.0%}", "M": _money}.get(kind, lambda v: f"{v:,}")
        lines.append(f"| {label} | " + " | ".join(fmt(v) for v in vals) + " |")
    lines += ["", "## What would have to change", "",
              f"- Price that only breaks even in the conservative case: ${result['break_even_price']:,.2f} "
              f"(you planned ${result['inputs']['sale_price']:,.2f})."]
    if market:
        lines += ["", "## What the market shows", ""]
        for k, v in market.items():
            if v not in (None, "", [], {}):
                lines.append(f"- {k.replace('_', ' ')}: {v if not isinstance(v, list) else '; '.join(map(str, v))}")
    if result["assumptions"]:
        lines += ["", "## Assumed (you did not give these)", ""]
        lines += [f"- {k.replace('_', ' ')}: {v}" for k, v in result["assumptions"].items()]
    lines += ["", "Scenarios: base = 60% of the sales you expect; conservative = 35% of them, a 10% lower "
              "price, ads and returns 1.5x. Not financial advice; check your real fees before you order."]
    return "\n".join(lines) + "\n"


# ── skill steps ───────────────────────────────────────────────────────────────

INTERVIEW_HOLD_S = 3600   # a customer may take a while to answer each question


def hold_interview_open(runtime: Any, seconds: float = INTERVIEW_HOLD_S) -> None:
    """Keep the task parked on the customer's reply longer than the runner's
    default (10 min) before it gives up on the wait."""
    try:
        from agent.ec_skills.media.media_job_watcher import _runner_for
        ctx = getattr(runtime, "context", None)
        task_id = str((ctx.get("task_id") if isinstance(ctx, dict) else getattr(ctx, "task_id", "")) or "")
        runner = _runner_for(task_id) if task_id else None
        if runner is not None:
            runner.hold_pending_timeout(task_id, seconds)
    except Exception:
        pass


def interview_answers(state: Dict[str, Any]) -> Dict[str, Any]:
    llm = (state.get("result") or {}).get("llm_result") or {}
    answers = llm.get("answers") if isinstance(llm, dict) else None
    return answers if isinstance(answers, dict) else {}


def run_idea_check(state: Dict[str, Any], node: str = "", date: Optional[str] = None) -> Dict[str, Any]:
    """The verdict step: answers + the market check -> report files and the chat message."""
    from agent.ec_skills.reports.report_store import save_and_upload
    from agent.ec_skills.reports.review_report import parse_mining
    from agent.ec_skills.reports.store_report import browser_final

    idea = dict((state.get("attributes") or {}).get("idea_answers") or interview_answers(state))
    mining = parse_mining(browser_final(state, node)) if node or state.get("tool_result") else None
    market = dict((mining or {}).get("market") or {})
    if mining and mining.get("themes"):
        market["top_buyer_complaints"] = [t.get("theme") for t in mining["themes"] if t.get("kind") != "praise"][:5]
    result = evaluate(idea, market)
    md = render_markdown(idea, result, market)
    who = idea.get("customer_name") or idea.get("idea") or "idea"
    out = save_and_upload("idea_check", str(who), {"report.md": md, "report.json":
                          {"idea": idea, "result": result, "market_check": mining}}, date)
    if result["verdict"] == "INCOMPLETE":
        message = "I could not finish the numbers: " + " ".join(result["reasons"])
    else:
        title = md.splitlines()[0].lstrip("# ").strip()
        why = "\n".join(f"- {r}" for r in result["reasons"][:5])
        sc = result["scenarios"]
        message = (f"{title}\n\n" + (f"Why:\n{why}\n\n" if why else "")
                   + f"Over {int(result['inputs']['months'])} months: claimed {_money(sc['claimed']['profit'])}, "
                   f"base {_money(sc['base']['profit'])}, conservative {_money(sc['conservative']['profit'])}. "
                   f"Break-even price (conservative): ${result['break_even_price']:,.2f}.\n"
                   f"Full report: {Path(out['folder']) / 'report.md'}")
    out.update(verdict=result["verdict"], message=message)
    return out
