"""Listing on eBay through the Sell Inventory API.

``publish_listing(spec)`` is the one deterministic call: inventory items ->
(item group) -> offers (created or updated) -> publish. It never raises for an
eBay rejection; it returns every error with the step and SKU it belongs to, so
the caller can fix exactly those fields and call it again (it is idempotent by
SKU / group key).
"""
import asyncio
import mimetypes
import os
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urlparse

from . import config
from .client import EbayApiError, EbayClient, body_json

INV = "/sell/inventory/v1"
MEDIA = "/commerce/media/v1_beta"
TAXO = "/commerce/taxonomy/v1"


# ---------------------------------------------------------------- taxonomy

async def _tree_id(c: EbayClient, mkt: str) -> str:
    r = await c.get_json(f"{TAXO}/get_default_category_tree_id", params={"marketplace_id": mkt})
    return r["categoryTreeId"]


async def suggest_categories(query: str, mkt: str = "EBAY_US", env=None, transport=None) -> dict:
    c = EbayClient(env, transport)
    m, _, _ = config.marketplace(mkt)
    tree = await _tree_id(c, m)
    r = await c.get_json(f"{TAXO}/category_tree/{tree}/get_category_suggestions", params={"q": query})
    out = []
    for s in r.get("categorySuggestions") or []:
        cat = s.get("category") or {}
        path = [a.get("categoryName") for a in reversed(s.get("categoryTreeNodeAncestors") or [])]
        out.append({"category_id": cat.get("categoryId"), "name": cat.get("categoryName"),
                    "path": " > ".join([p for p in path if p] + [cat.get("categoryName") or ""])})
    return {"marketplace": m, "category_tree_id": tree, "suggestions": out}


async def category_aspects(category_id: str, mkt: str = "EBAY_US", max_values: int = 30,
                           env=None, transport=None) -> dict:
    """Item specifics for a category: required ones in full, the rest summarised."""
    c = EbayClient(env, transport)
    m, _, _ = config.marketplace(mkt)
    tree = await _tree_id(c, m)
    r = await c.get_json(f"{TAXO}/category_tree/{tree}/get_item_aspects_for_category",
                         params={"category_id": category_id})
    required, recommended, optional = [], [], []
    for a in r.get("aspects") or []:
        con = a.get("aspectConstraint") or {}
        values = [v.get("localizedValue") for v in a.get("aspectValues") or []]
        entry = {
            "name": a.get("localizedAspectName"),
            "mode": con.get("aspectMode"),                   # FREE_TEXT | SELECTION_ONLY
            "multiple": con.get("itemToAspectCardinality") == "MULTI",
            "variation_ok": bool(con.get("aspectEnabledForVariations")),
        }
        if values:
            entry["values"] = values[:max_values] + ([f"... ({len(values) - max_values} more)"]
                                                     if len(values) > max_values else [])
        if con.get("aspectRequired"):
            required.append(entry)
        elif con.get("aspectUsage") == "RECOMMENDED":
            recommended.append(entry)
        else:
            optional.append(entry["name"])
    return {"marketplace": m, "category_id": category_id, "required": required,
            "recommended": recommended, "optional_names": optional}


# ---------------------------------------------------------------- account

async def account_setup(mkt: str = "EBAY_US", env=None, transport=None) -> dict:
    """Business policies and inventory locations an offer can use."""
    c = EbayClient(env, transport)
    m, _, _ = config.marketplace(mkt)
    out: Dict[str, Any] = {"marketplace": m}
    for kind, key, idk in (("fulfillment", "fulfillmentPolicies", "fulfillmentPolicyId"),
                           ("payment", "paymentPolicies", "paymentPolicyId"),
                           ("return", "returnPolicies", "returnPolicyId")):
        try:
            r = await c.get_json(f"/sell/account/v1/{kind}_policy", params={"marketplace_id": m})
            out[f"{kind}_policies"] = [{"id": p.get(idk), "name": p.get("name"),
                                        "description": p.get("description")}
                                       for p in r.get(key) or []]
        except EbayApiError as e:
            out[f"{kind}_policies"] = []
            out.setdefault("problems", []).append({"step": f"{kind}_policy", "errors": e.errors})
    r = await c.get_json(f"{INV}/location", params={"limit": 100})
    out["locations"] = [{"key": l.get("merchantLocationKey"), "name": l.get("name"),
                         "status": l.get("merchantLocationStatus"),
                         "address": (l.get("location") or {}).get("address")}
                        for l in r.get("locations") or []]
    return out


async def create_location(key: str, address: dict, name: str = "", env=None, transport=None) -> dict:
    """A warehouse-type inventory location (address needs at least country + postalCode or city/state)."""
    c = EbayClient(env, transport)
    body = {"location": {"address": address}, "locationTypes": ["WAREHOUSE"],
            "merchantLocationStatus": "ENABLED", "name": name or key}
    await c.request("POST", f"{INV}/location/{quote(key, safe='')}", json_body=body)
    return {"key": key, "created": True}


# ---------------------------------------------------------------- media

async def upload_media(paths: List[str], env=None, transport=None, video_wait_s: float = 60) -> dict:
    """Local images -> eBay-hosted image URLs; local videos -> eBay video ids."""
    c = EbayClient(env, transport)
    results = []
    for p in paths:
        p = os.path.abspath(os.path.expanduser(p))
        mime = mimetypes.guess_type(p)[0] or ""
        try:
            if not os.path.isfile(p):
                raise FileNotFoundError(p)
            if mime.startswith("video/"):
                results.append({"path": p, "kind": "video", **await _upload_video(c, p, video_wait_s)})
            else:
                results.append({"path": p, "kind": "image", **await _upload_image(c, p, mime)})
        except EbayApiError as e:
            results.append({"path": p, "error": e.errors or [{"message": str(e)}]})
        except Exception as e:
            results.append({"path": p, "error": [{"message": f"{type(e).__name__}: {e}"}]})
    return {"media": results}


async def _upload_image(c: EbayClient, path: str, mime: str) -> dict:
    with open(path, "rb") as f:
        data = f.read()
    r = await c.request("POST", f"{MEDIA}/image/create_image_from_file", host="apim",
                        files={"image": (os.path.basename(path), data, mime or "image/jpeg")})
    url = body_json(r).get("imageUrl")
    if not url and r.headers.get("Location"):
        url = (await c.get_json(urlparse(r.headers["Location"]).path, host="apim")).get("imageUrl")
    return {"image_url": url}


async def _upload_video(c: EbayClient, path: str, wait_s: float) -> dict:
    size = os.path.getsize(path)
    title = os.path.splitext(os.path.basename(path))[0][:80]
    r = await c.request("POST", f"{MEDIA}/video", host="apim",
                        json_body={"title": title, "size": size, "classification": ["ITEM"]})
    video_id = (r.headers.get("Location") or "").rstrip("/").rsplit("/", 1)[-1]
    if not video_id:
        raise RuntimeError("eBay did not return a video id")
    with open(path, "rb") as f:
        data = f.read()
    await c.request("POST", f"{MEDIA}/video/{video_id}/upload", host="apim", content=data,
                    headers={"Content-Type": "application/octet-stream"})
    status, waited = "PROCESSING", 0.0
    while waited < wait_s:
        status = (await c.get_json(f"{MEDIA}/video/{video_id}", host="apim")).get("status") or status
        if status in ("LIVE", "BLOCKED", "PROCESSING_FAILED"):
            break
        await asyncio.sleep(5)
        waited += 5
    return {"video_id": video_id, "status": status}


# ---------------------------------------------------------------- publish

def _item_body(item: dict, spec: dict) -> dict:
    product = {k: v for k, v in {
        "title": item.get("title"),
        "description": item.get("description"),
        "aspects": {k: (v if isinstance(v, list) else [v]) for k, v in (item.get("aspects") or {}).items()},
        "imageUrls": item.get("image_urls"),
        "videoIds": item.get("video_ids"),
        "brand": item.get("brand"),
        "mpn": item.get("mpn"),
        "upc": _as_list(item.get("upc")),
        "ean": _as_list(item.get("ean")),
        "isbn": _as_list(item.get("isbn")),
    }.items() if v}
    body = {"product": product,
            "condition": item.get("condition") or spec.get("condition") or "NEW",
            "availability": {"shipToLocationAvailability": {"quantity": int(item.get("quantity") or 0)}}}
    if item.get("condition_description") or spec.get("condition_description"):
        body["conditionDescription"] = item.get("condition_description") or spec["condition_description"]
    if item.get("package"):
        body["packageWeightAndSize"] = item["package"]
    return body


def _as_list(v):
    if not v:
        return None
    return v if isinstance(v, list) else [str(v)]


def _offer_body(item: dict, spec: dict, mkt: str, currency: str) -> dict:
    pol = spec.get("listing_policies") or {}
    body = {
        "sku": item["sku"], "marketplaceId": mkt, "format": spec.get("format") or "FIXED_PRICE",
        "availableQuantity": int(item.get("quantity") or 0),
        "categoryId": str(spec["category_id"]),
        "merchantLocationKey": spec.get("merchant_location_key"),
        "pricingSummary": {"price": {"value": str(item.get("price")), "currency": currency}},
        "listingPolicies": {k: v for k, v in {
            "fulfillmentPolicyId": pol.get("fulfillment_policy_id"),
            "paymentPolicyId": pol.get("payment_policy_id"),
            "returnPolicyId": pol.get("return_policy_id")}.items() if v},
    }
    desc = item.get("listing_description") or spec.get("listing_description")
    if desc:
        body["listingDescription"] = desc
    if item.get("best_offer"):
        body["listingPolicies"]["bestOfferTerms"] = {"bestOfferEnabled": True}
    return body


def check_spec(spec: dict) -> List[str]:
    """Problems that would make eBay reject the call outright."""
    probs = []
    items = spec.get("items") or []
    if not items:
        probs.append("spec.items is empty")
    if not spec.get("category_id"):
        probs.append("spec.category_id is required (use ebay_category_suggest)")
    if not spec.get("merchant_location_key"):
        probs.append("spec.merchant_location_key is required (see ebay_account_setup)")
    pol = spec.get("listing_policies") or {}
    for k in ("fulfillment_policy_id", "payment_policy_id", "return_policy_id"):
        if not pol.get(k):
            probs.append(f"spec.listing_policies.{k} is required (see ebay_account_setup)")
    group = spec.get("group")
    for i, it in enumerate(items):
        if not it.get("sku"):
            probs.append(f"items[{i}].sku is required")
        if it.get("price") in (None, ""):
            probs.append(f"items[{i}].price is required")
        if not group and not it.get("title"):
            probs.append(f"items[{i}].title is required")
        if group:
            for name in (group.get("varies_by") or {}):
                if name not in (it.get("aspects") or {}):
                    probs.append(f"items[{i}].aspects must include the varying aspect {name!r}")
    if group:
        if not group.get("key"):
            probs.append("spec.group.key is required")
        if not group.get("varies_by"):
            probs.append("spec.group.varies_by is required, e.g. {\"Color\": [\"Red\", \"Blue\"]}")
    return probs


async def publish_listing(spec: dict, env=None, transport=None) -> dict:
    """Create/update everything in *spec* and publish it. See module docstring."""
    probs = check_spec(spec)
    if probs:
        return {"ok": False, "stage": "spec", "errors": [{"message": p} for p in probs]}
    c = EbayClient(env, transport)
    mkt, currency, lang = config.marketplace(spec.get("marketplace") or "EBAY_US")
    headers = {"Content-Language": lang}
    errors: List[dict] = []
    warnings: List[dict] = []
    group = spec.get("group")

    def fail(step, e: EbayApiError, sku=None):
        for er in e.errors or [{"message": str(e)}]:
            (warnings if er.get("severity") == "warning" else errors).append(
                {"step": step, "sku": sku, **er})

    # 1. inventory items (a group's shared title/description fill in for its variants)
    for item in spec["items"]:
        if group:
            item = {"title": group.get("title"), "description": group.get("description"), **item}
        try:
            await c.request("PUT", f"{INV}/inventory_item/{quote(item['sku'], safe='')}",
                            json_body=_item_body(item, spec), headers=headers)
        except EbayApiError as e:
            fail("inventory_item", e, item["sku"])

    # 2. the variation group
    if group and not errors:
        gbody = {
            "title": group.get("title"), "description": group.get("description"),
            "aspects": {k: (v if isinstance(v, list) else [v]) for k, v in (group.get("aspects") or {}).items()},
            "imageUrls": group.get("image_urls"),
            "variantSKUs": [it["sku"] for it in spec["items"]],
            "variesBy": {"specifications": [{"name": k, "values": list(v)}
                                            for k, v in group["varies_by"].items()],
                         "aspectsImageVariesBy": group.get("image_varies_by") or []},
        }
        gbody = {k: v for k, v in gbody.items() if v not in (None, {}, [])}
        try:
            await c.request("PUT", f"{INV}/inventory_item_group/{quote(group['key'], safe='')}",
                            json_body=gbody, headers=headers)
        except EbayApiError as e:
            fail("inventory_item_group", e)

    # 3. offers, created or updated in place
    offers: Dict[str, str] = {}
    if not errors:
        for item in spec["items"]:
            body = _offer_body(item, spec, mkt, currency)
            try:
                existing = await c.get_json(f"{INV}/offer", params={"sku": item["sku"], "marketplace_id": mkt},
                                            ok=(200, 404))
                found = [o for o in existing.get("offers") or [] if o.get("format") == body["format"]]
                if found:
                    oid = found[0]["offerId"]
                    await c.request("PUT", f"{INV}/offer/{oid}", json_body=body, headers=headers)
                else:
                    r = await c.request("POST", f"{INV}/offer", json_body=body, headers=headers)
                    oid = body_json(r).get("offerId")
                offers[item["sku"]] = oid
            except EbayApiError as e:
                fail("offer", e, item["sku"])

    # 4. publish
    listing_ids: Dict[str, str] = {}
    if not errors:
        try:
            if group:
                r = await c.request("POST", f"{INV}/offer/publish_by_inventory_item_group",
                                    json_body={"inventoryItemGroupKey": group["key"], "marketplaceId": mkt})
                b = body_json(r)
                listing_ids[group["key"]] = b.get("listingId")
                warnings += [{"step": "publish", **w} for w in _warns(b)]
            else:
                for sku, oid in offers.items():
                    try:
                        r = await c.request("POST", f"{INV}/offer/{oid}/publish")
                        b = body_json(r)
                        listing_ids[sku] = b.get("listingId")
                        warnings += [{"step": "publish", "sku": sku, **w} for w in _warns(b)]
                    except EbayApiError as e:
                        fail("publish", e, sku)
        except EbayApiError as e:
            fail("publish", e)

    ok = not errors and bool(listing_ids)
    return {"ok": ok, "marketplace": mkt, "listing_ids": listing_ids, "offers": offers,
            "errors": errors, "warnings": warnings,
            "stage": "done" if ok else (errors[0]["step"] if errors else "publish")}


def _warns(body: dict) -> List[dict]:
    from .client import normalize_errors
    return [w for w in normalize_errors({"warnings": body.get("warnings") or []})]


def listing_url(listing_id: str, mkt: str = "EBAY_US") -> str:
    domain = {"EBAY_GB": "ebay.co.uk", "EBAY_DE": "ebay.de", "EBAY_AU": "ebay.com.au",
              "EBAY_CA": "ebay.ca", "EBAY_FR": "ebay.fr", "EBAY_IT": "ebay.it",
              "EBAY_ES": "ebay.es"}.get(mkt, "ebay.com")
    return f"https://www.{domain}/itm/{listing_id}"
