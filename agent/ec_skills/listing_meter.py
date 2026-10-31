"""Per-listing billing: one new product, confirmed by the platform, as outcome events.

Price (owner decision 2026-10-30, CN): a new product with its first SKU is one
``main_sku_listed``; each further SKU is one ``variant_sku_added``. A 5-SKU
product is 1 + 4 events. The rules (eCan_lambda PRODUCT_LISTING_BILLING_FOR_CLIENT.md):

* only after the platform returns the new product's id -- the caller passes what
  the platform itself answered, never what an agent said;
* never for a product that existed before this run (an edit, an old product);
* never on a test run (the task's ``billing_test`` setting, on the run scope);
* the platform's own ids make the keys, the first SKU in the platform's order is
  the base SKU, so a retry repeats the same keys and is never charged twice.

Site-free: a site bundle reads the product from its platform and calls
``record_listing``. Like ``metering.emit``, this is platform code, never callable
from a skill's code node -- a skill cannot add or drop billable listings.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from utils.logger_helper import logger_helper as logger

SCENARIO = "product_listing"
MAIN = "main_sku_listed"
VARIANT = "variant_sku_added"
LOG_TAG = "[LISTING-METER]"

# A product created a little before the run's recorded start is still this run's
# (clocks differ between the PC and the platform).
CLOCK_SLACK_S = 600


def _scope() -> Dict[str, Any]:
    try:
        from utils.log_scope import get_scope
        return get_scope() or {}
    except Exception:
        return {}


def listing_events(platform: str, shop_id: str, product_id: str, sku_ids: Sequence[str],
                   occurred_at: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """The events for one new product: ``[(meter, key, evidence), ...]`` as dicts."""
    p, shop, pid = str(platform), str(shop_id), str(product_id)
    skus = [str(s) for s in sku_ids if str(s or "").strip()]
    if not (p and shop and pid and skus):
        return []
    events = [{"meter_code": MAIN, "idempotency_key": f"listing:{p}:{shop}:{pid}",
               "evidence": {"platform": p, "shop_id": shop, "product_id": pid, "base_sku_id": skus[0]}}]
    for sku in dict.fromkeys(skus[1:]):
        if sku != skus[0]:
            events.append({"meter_code": VARIANT, "idempotency_key": f"listing_sku:{p}:{shop}:{sku}",
                           "evidence": {"platform": p, "shop_id": shop, "product_id": pid, "sku_id": sku}})
    return events


def record_listing(platform: str, shop_id: str, product_id: str, sku_ids: Sequence[str], *,
                   created_at: Optional[float] = None) -> Dict[str, Any]:
    """Record one new product the platform confirmed. Never raises.

    *created_at*: the product's creation time (epoch seconds) as the platform
    reports it; a product older than this run is not new and is not recorded.
    Returns ``{"recorded": n, "would_charge": n, "test": bool, "skipped": reason}``.
    """
    out: Dict[str, Any] = {"recorded": 0, "would_charge": 0, "test": False, "skipped": ""}
    try:
        sc = _scope()
        started = float(sc.get("run_started_at") or 0)
        if created_at and started and float(created_at) < started - CLOCK_SLACK_S:
            out["skipped"] = "product existed before this run"
            logger.info(f"{LOG_TAG} {platform} {product_id}: {out['skipped']}; nothing recorded")
            return out
        events = listing_events(platform, shop_id, product_id, sku_ids)
        if not events:
            out["skipped"] = "no shop, product or SKU id from the platform"
            logger.warning(f"{LOG_TAG} {platform} {product_id!r}: {out['skipped']}; nothing recorded")
            return out
        out["would_charge"] = len(events)
        if sc.get("billing_test"):
            out["test"] = True
            logger.info(f"{LOG_TAG} test run: {platform} {product_id} would be {len(events)} event(s) "
                        f"(1 product + {len(events) - 1} SKU); nothing recorded")
            return out
        from agent.ec_skills import metering
        when = datetime.fromtimestamp(float(created_at), tz=timezone.utc).replace(tzinfo=None) if created_at else None
        for ev in events:
            if metering.emit(SCENARIO, ev["meter_code"], idempotency_key=ev["idempotency_key"],
                             evidence=ev["evidence"], occurred_at=when):
                out["recorded"] += 1
        logger.info(f"{LOG_TAG} {platform} {product_id}: {out['recorded']} new of {len(events)} event(s)")
        return out
    except Exception as exc:
        logger.warning(f"{LOG_TAG} record failed (non-fatal): {exc}")
        out["skipped"] = f"error: {exc}"
        return out
