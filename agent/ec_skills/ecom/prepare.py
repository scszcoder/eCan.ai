"""Turn stored report rows into the facts a ruleset reads. Arithmetic only, no judgment:
the rulesets in ``rulesets/`` decide what the facts mean.

  gads_tables       search_terms / products / campaigns aggregates for gads_v1
  gads_context      target ROAS / CPA, break-even ROAS, learning windows
  tracking_facts    one row for tracking_v1 (conversion actions + order reconciliation)
  feed_tables       items + account rows for feed_v1 (Merchant Center + Shopify products)
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from agent.ec_skills.ecom import kb, metrics
from agent.ec_skills.ecom.store import Store


def _d(s: Any) -> Optional[date]:
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _window(rows: List[Dict[str, Any]], today: date, days: int) -> List[Dict[str, Any]]:
    start = today - timedelta(days=days)
    return [r for r in rows if (_d(r.get("date")) or today) > start and (_d(r.get("date")) or today) <= today]


def _days_below_breakeven(daily: List[Dict[str, Any]], breakeven: Optional[float], today: date) -> Optional[int]:
    """The longest trailing run of days whose pooled ROAS is under break-even (spend > 0)."""
    if not breakeven:
        return None
    by_day: Dict[date, Dict[str, float]] = {}
    for r in daily:
        d = _d(r.get("date"))
        if d:
            b = by_day.setdefault(d, {"cost": 0.0, "value": 0.0})
            b["cost"] += r.get("cost") or 0
            b["value"] += r.get("conv_value") or 0
    if not by_day:
        return None
    cost = value = 0.0
    longest = 0
    for d in sorted(by_day, reverse=True):
        cost += by_day[d]["cost"]
        value += by_day[d]["value"]
        if cost > 0 and value / cost < breakeven:
            longest = (today - d).days + 1
    return longest


def _last_change(changes: List[Dict[str, Any]], campaign: str, kinds: tuple) -> Optional[date]:
    ds = [_d(c.get("date")) for c in changes
          if c.get("campaign") == campaign and any(k in str(c.get("change_type") or "").lower() for k in kinds)]
    ds = [d for d in ds if d]
    return max(ds) if ds else None


def gads_context(store: Store, store_id: str, *, scope: Optional[Dict[str, Any]] = None,
                 breakeven_roas: Optional[float] = None, target_roas: Optional[float] = None,
                 target_cpa: Optional[float] = None, aov: Optional[float] = None) -> Dict[str, Any]:
    """Targets for the rules. Order: explicit argument -> store profile targets -> break-even x margin
    of safety. A missing break-even is reported, never invented."""
    scope = {"store_id": store_id, "platform": "google_ads", **(scope or {})}
    t = {k: v["value"] for k, v in kb.thresholds("thresholds.gads", scope, store).items()}
    profile = (store.kb_get("store_profile", store_id) or {}).get("value") or {}
    targets = profile.get("targets") or {}
    breakeven_roas = breakeven_roas or targets.get("breakeven_roas")
    target_roas = target_roas or targets.get("target_roas") or (
        round(breakeven_roas * t["target_roas_over_breakeven"], 2) if breakeven_roas else None)
    if target_cpa is None and aov and target_roas:
        target_cpa = round(aov / target_roas, 2)
    gaps = [n for n, v in (("breakeven_roas", breakeven_roas), ("target_roas", target_roas),
                           ("target_cpa", target_cpa)) if v is None]
    return {"breakeven_roas": breakeven_roas, "target_roas": target_roas, "target_cpa": target_cpa, "aov": aov,
            "shared_negatives": kb.value("gads.shared_negatives", scope, store) or [], "missing": gaps}


def gads_tables(store: Store, store_id: str, *, window_days: int = 14, today: Optional[date] = None,
                breakeven_roas: Optional[float] = None) -> Dict[str, Any]:
    today = today or date.today()
    t = {k: v["value"] for k, v in kb.thresholds("thresholds.gads", {"store_id": store_id}, store).items()}
    st = _window(store.rows("gads_search_term_rows", store_id), today, window_days)
    pr_all = store.rows("gads_product_rows", store_id)
    pr = _window(pr_all, today, window_days)
    camp_all = store.rows("gads_campaign_rows", store_id)
    changes = store.rows("gads_change_rows", store_id)

    search_terms = metrics.group([r for r in st if (r.get("added_excluded") or "").lower() != "excluded"],
                                 ["campaign", "ad_group", "search_term", "match_type"])
    first_seen: Dict[str, date] = {}
    for r in pr_all:
        d = _d(r.get("date"))
        if d and (r["item_id"] not in first_seen or d < first_seen[r["item_id"]]):
            first_seen[r["item_id"]] = d
    products = metrics.group(pr, ["item_id"])
    titles = {r["item_id"]: r for r in pr}
    for p in products:
        src = titles.get(p["item_id"]) or {}
        p.update({k: src.get(k) for k in ("title", "product_type", "custom_label_0", "campaign")})
        p["days_live"] = (today - first_seen[p["item_id"]]).days if p["item_id"] in first_seen else None

    campaigns = []
    names = list(dict.fromkeys(r["campaign"] for r in camp_all if r.get("campaign")))
    learning: Dict[str, bool] = {}
    for name in names:
        rows = [r for r in camp_all if r.get("campaign") == name]
        latest = max(rows, key=lambda r: r.get("date") or "")
        win = metrics.totals(_window(rows, today, window_days))
        d7 = metrics.totals(_window(rows, today, 7))
        d30 = metrics.totals(_window(rows, today, 30))
        lost = [r.get("lost_is_budget") for r in _window(rows, today, window_days) if r.get("lost_is_budget") is not None]
        structural = _last_change(changes, name, ("create", "bid strategy", "bidding", "structure", "status"))
        budget_change = _last_change(changes, name, ("budget",))
        target_change = _last_change(changes, name, ("target",))
        dated = [_d(r.get("date")) for r in rows if _d(r.get("date"))]
        started = min(dated) if dated else None
        anchor = max([d for d in (structural, started) if d], default=None)
        learning[name] = bool(anchor and (today - anchor).days < t["learning_days"])
        campaigns.append({
            "campaign": name, "type": latest.get("type"), "status": latest.get("status"),
            "budget": latest.get("budget"), "bidding": latest.get("bidding"),
            "target_roas": (latest.get("target_roas") or None), "cost": win.get("cost", 0),
            "conversions": win.get("conversions", 0), "conv_value": win.get("conv_value", 0), "roas": win.get("roas"),
            "lost_is_budget": (sum(lost) / len(lost)) if lost else None,
            "cost_7d": d7.get("cost", 0), "conv_7d": d7.get("conversions", 0),
            "conv_30d": d30.get("conversions", 0), "roas_30d": d30.get("roas"),
            "days_since_budget_change": (today - budget_change).days if budget_change else None,
            "days_since_target_change": (today - target_change).days if target_change else None,
            "days_below_breakeven": _days_below_breakeven(rows, breakeven_roas, today),
            "in_learning": learning[name],
        })
    return {"search_terms": search_terms, "products": products, "campaigns": campaigns,
            "in_learning": learning, "window_days": window_days, "today": today.isoformat()}


_PURCHASE = re.compile(r"purchase|order|checkout complete|sale", re.I)


def tracking_facts(conversion_actions: List[Dict[str, Any]], *, shopify_orders: Optional[float] = None,
                   gads_conversions: Optional[float] = None, ga4_purchases: Optional[float] = None,
                   eu_uk_traffic: bool = False, consent_mode: Optional[bool] = None) -> Dict[str, Any]:
    """``conversion_actions`` rows: {name, category, primary (bool), source, counting ("every"|"one"),
    value_tracking (bool), status ("active"|"inactive"|"no_recent_conversions"|...)} as the
    Google Ads Conversions page shows them."""
    purchase = [c for c in conversion_actions
                if str(c.get("category") or "").lower() == "purchase" or _PURCHASE.search(str(c.get("name") or ""))]
    primary = [c for c in purchase if c.get("primary")]
    p0 = primary[0] if len(primary) == 1 else {}
    counts = [v for v in (shopify_orders, gads_conversions, ga4_purchases) if v is not None]
    gap = None
    if shopify_orders and len(counts) >= 2:
        gap = round(max(abs(v - shopify_orders) for v in counts) / shopify_orders, 3)
    return {"check": "tracking", "purchase_actions": len(purchase), "primary_purchase_count": len(primary),
            "primary_name": p0.get("name"), "primary_source": p0.get("source"),
            "primary_counting": (str(p0.get("counting") or "").lower() or None),
            "primary_value_tracking": p0.get("value_tracking"),
            "primary_status": (str(p0.get("status") or "").lower().replace(" ", "_") or None),
            "shopify_orders": shopify_orders, "gads_conversions": gads_conversions, "ga4_purchases": ga4_purchases,
            "gap_pct": gap, "eu_uk_traffic": eu_uk_traffic, "consent_mode": consent_mode}


_PROMO = re.compile(r"\b(free shipping|sale|% off|discount|best price|cheap|buy now|limited time|"
                    r"clearance|deal|coupon)\b|!", re.I)


def _caps_share(title: str) -> float:
    letters = [c for c in title if c.isalpha()]
    return sum(c.isupper() for c in letters) / len(letters) if letters else 0.0


def feed_tables(store: Store, store_id: str, policy_pages: Optional[Dict[str, bool]] = None,
                account_issues: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Items from Merchant Center (status/issues) joined to the Shopify export by SKU/handle,
    plus one account row (policy pages present, account-level issues)."""
    scope = {"store_id": store_id}
    title_max = kb.value("gads.title_max", scope, store)
    gmc = store.rows("gmc_product_rows", store_id)
    shop = store.rows("shopify_product_rows", store_id)
    items: Dict[str, Dict[str, Any]] = {}
    for r in gmc:
        it = items.setdefault(r["item_id"], {"item_id": r["item_id"], "issues": []})
        it.update({k: r.get(k) for k in ("title", "status", "price", "availability", "gtin", "brand", "mpn",
                                         "image_link", "google_product_category") if r.get(k) is not None})
        if r.get("issue"):
            it["issues"].append(r["issue"])
    if not items:  # no Merchant Center export yet: audit the Shopify catalog on its own
        for p in shop:
            if (p.get("status") or "active") == "active":
                items[p["handle"]] = {"item_id": p["handle"], "title": p.get("title"), "issues": [],
                                      "gtin": (p.get("barcodes") or [None])[0], "brand": p.get("vendor"),
                                      "mpn": p.get("gs_mpn"), "google_product_category": p.get("product_category"),
                                      "image_link": "yes" if p.get("image_count") else None}
    for it in items.values():
        title = it.get("title") or ""
        it.update({"title_len": len(title), "title_max": title_max, "title_promo": bool(_PROMO.search(title)),
                   "title_caps_share": round(_caps_share(title), 2),
                   "has_identifier": bool(it.get("gtin") or (it.get("brand") and it.get("mpn"))),
                   "has_image": bool(it.get("image_link")), "issue_text": "; ".join(it["issues"])})
    pages = policy_pages or {}
    required = kb.value("shopify.policy_pages", scope, store) or []
    account = [{"scope": "account", "missing_policy_pages": [p for p in required if pages.get(p) is False],
                "unknown_policy_pages": [p for p in required if p not in pages],
                "account_issues": [a.get("issue") for a in (account_issues or [])],
                "account_issue_count": len(account_issues or [])}]
    total = len(items)
    approved = sum(1 for i in items.values() if (i.get("status") or "") in ("approved", "active"))
    return {"items": list(items.values()), "account": account, "item_count": total,
            "approval_rate": round(approved / total, 3) if total and gmc else None}
