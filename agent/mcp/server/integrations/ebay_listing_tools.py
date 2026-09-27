"""eBay listing tools -- the API path (Sell Inventory API) and the bulk-CSV path.

API path (needs an eBay developer app + the seller's one-time consent, done by
the ``ebay_connect_account`` browser action):

* ``ebay_api_status``        -- is the app configured / the seller connected.
* ``ebay_category_suggest``  -- product keywords -> candidate category ids.
* ``ebay_category_aspects``  -- a category's item specifics (required ones with valid values).
* ``ebay_account_setup``     -- business policies + inventory locations (optionally create one).
* ``ebay_upload_media``      -- local images/videos -> eBay-hosted image URLs / video ids.
* ``ebay_publish_listing``   -- one listing or variation family: items -> group -> offers -> publish.

CSV path (no API; a browser uploads the file in Seller Hub):

* ``ebay_csv_inspect`` / ``ebay_csv_fill`` / ``ebay_csv_parse_result``.

All take their arguments under ``input`` and return JSON text + meta. No
credential or token ever appears in a result.
"""

import json
import os
from typing import Any, Dict, List

from mcp.types import TextContent

from utils.logger_helper import logger_helper as logger

_MAX_ITEMS = 200


def _reply(payload: Dict[str, Any]) -> List[TextContent]:
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, default=str),
                        meta=payload)]


def _input(args) -> Dict[str, Any]:
    return (args or {}).get("input") or {}


def _need_file(path: str, what: str) -> str:
    p = str(path or "").strip()
    if not p:
        raise ValueError(f"{what} is required")
    if not os.path.isfile(p):
        raise ValueError(f"{what} not found: {p}")
    return p


def _err(tool: str, e: Exception) -> List[TextContent]:
    from agent.ec_skills.listing.ebay_api.auth import EbayAuthError
    from agent.ec_skills.listing.ebay_api.client import EbayApiError
    if isinstance(e, EbayApiError):
        return _reply({"ok": False, "error": str(e), "errors": e.errors})
    if isinstance(e, EbayAuthError):
        return _reply({"ok": False, "error": str(e), "needs": "connect"})
    logger.warning(f"[{tool}] {e}")
    return _reply({"ok": False, "error": f"{type(e).__name__}: {e}"})


# --------------------------------------------------------------------- API path

async def ebay_api_status(mainwin, args):
    try:
        from agent.ec_skills.listing.ebay_api import auth
        st = auth.status()
        if not st["app_configured"]:
            st["next"] = ("the eBay developer app is not configured on this machine: a human must "
                          "store its App ID / Cert ID / RuName (python -m "
                          "agent.ec_skills.listing.ebay_api.config set)")
        elif not st["connected"]:
            st["next"] = "connect the seller account (browser step ebay_connect_account)"
        return _reply({"ok": True, **st})
    except Exception as e:
        return _err("ebay_api_status", e)


async def ebay_category_suggest(mainwin, args):
    try:
        from agent.ec_skills.listing.ebay_api.listing import suggest_categories
        inp = _input(args)
        q = str(inp.get("query") or "").strip()
        if not q:
            raise ValueError("query is required")
        return _reply({"ok": True, **await suggest_categories(q, inp.get("marketplace") or "EBAY_US")})
    except Exception as e:
        return _err("ebay_category_suggest", e)


async def ebay_category_aspects(mainwin, args):
    try:
        from agent.ec_skills.listing.ebay_api.listing import category_aspects
        inp = _input(args)
        cid = str(inp.get("category_id") or "").strip()
        if not cid:
            raise ValueError("category_id is required")
        return _reply({"ok": True, **await category_aspects(
            cid, inp.get("marketplace") or "EBAY_US", int(inp.get("max_values") or 30))})
    except Exception as e:
        return _err("ebay_category_aspects", e)


async def ebay_account_setup(mainwin, args):
    try:
        from agent.ec_skills.listing.ebay_api.listing import account_setup, create_location
        inp = _input(args)
        created = None
        loc = inp.get("create_location")
        if loc:
            if not loc.get("key") or not loc.get("address"):
                raise ValueError("create_location needs key and address")
            created = await create_location(loc["key"], loc["address"], loc.get("name") or "")
        res = await account_setup(inp.get("marketplace") or "EBAY_US")
        if created:
            res["created_location"] = created
        if not all(res.get(f"{k}_policies") for k in ("fulfillment", "payment", "return")):
            res["next"] = ("a business policy type is missing: the seller must create shipping, payment "
                           "and return policies in eBay (Account -> Business policies), or opt in to "
                           "business policies first")
        if not res.get("locations"):
            res.setdefault("next", "no inventory location: create one with create_location")
        return _reply({"ok": True, **res})
    except Exception as e:
        return _err("ebay_account_setup", e)


async def ebay_upload_media(mainwin, args):
    try:
        from agent.ec_skills.listing.ebay_api.listing import upload_media
        inp = _input(args)
        paths = inp.get("paths") or []
        if isinstance(paths, str):
            paths = [paths]
        if not paths:
            raise ValueError("paths is required (local image/video files)")
        res = await upload_media(paths, video_wait_s=float(inp.get("video_wait_s") or 60))
        res["ok"] = not any("error" in m for m in res["media"])
        return _reply(res)
    except Exception as e:
        return _err("ebay_upload_media", e)


async def ebay_publish_listing(mainwin, args):
    try:
        from agent.ec_skills.listing.ebay_api.listing import listing_url, publish_listing
        inp = _input(args)
        spec = inp.get("spec")
        if isinstance(spec, str):
            spec = json.loads(spec)
        if not isinstance(spec, dict):
            raise ValueError("spec must be an object")
        res = await publish_listing(spec)
        res["urls"] = {k: listing_url(v, res.get("marketplace") or "EBAY_US")
                       for k, v in (res.get("listing_ids") or {}).items() if v}
        res["next"] = ("verify the listing page" if res["ok"] else
                       "fix exactly what the errors name, then call ebay_publish_listing again "
                       "with the same SKUs (it updates in place)")
        return _reply(res)
    except Exception as e:
        return _err("ebay_publish_listing", e)


# --------------------------------------------------------------------- CSV path

async def ebay_csv_inspect(mainwin, args):
    try:
        from agent.ec_skills.listing.ebay_csv.bulk_csv import inspect_template
        return _reply({"ok": True, **inspect_template(_need_file(_input(args).get("template_path"),
                                                                 "template_path"))})
    except Exception as e:
        return _err("ebay_csv_inspect", e)


async def ebay_csv_fill(mainwin, args):
    try:
        from agent.ec_skills.listing.ebay_csv.bulk_csv import fill_template
        inp = _input(args)
        template = _need_file(inp.get("template_path"), "template_path")
        spec = inp.get("spec")
        if isinstance(spec, str):
            spec = json.loads(spec)
        res = fill_template(template, spec or {}, inp.get("out_path") or None)
        return _reply({"ok": True, **res, "next": "upload the file in 'upload_file' in Seller Hub"})
    except Exception as e:
        return _err("ebay_csv_fill", e)


async def ebay_csv_parse_result(mainwin, args):
    try:
        from agent.ec_skills.listing.ebay_csv.bulk_csv import parse_results
        res = parse_results(_need_file(_input(args).get("result_path"), "result_path"))
        if len(res["items"]) > _MAX_ITEMS:
            res["items_truncated"] = len(res["items"]) - _MAX_ITEMS
            res["items"] = res["items"][:_MAX_ITEMS]
        res["next"] = ("done -- verify the listings" if res["done"] else
                       "fix the rows with errors, fill again with only those listings, re-upload")
        return _reply({"ok": True, **res})
    except Exception as e:
        return _err("ebay_csv_parse_result", e)


# --------------------------------------------------------------------- schemas

_CAT = "<category>E-Commerce</category><sub-category>eBay Listing</sub-category>"


def _tool(types, name, desc, props, required=()):
    return types.Tool(
        _meta={"run_in_cloud": False}, name=name, description=_CAT + desc,
        inputSchema={"type": "object", "required": ["input"], "properties": {"input": {
            "type": "object", "required": list(required), "properties": props}}})


def add_ebay_listing_tool_schemas(tool_schemas):
    import mcp.types as types
    mkt = {"type": "string", "description": "eBay marketplace id, e.g. EBAY_US, EBAY_GB, EBAY_DE (default EBAY_US)."}
    tool_schemas += [
        _tool(types, "ebay_api_status",
              "Whether the eBay developer app is configured on this machine and the seller account is "
              "connected (API listing path). Call first.", {}),
        _tool(types, "ebay_category_suggest",
              "Suggest eBay leaf categories for product keywords; returns category ids with their paths.",
              {"query": {"type": "string"}, "marketplace": mkt}, ["query"]),
        _tool(types, "ebay_category_aspects",
              "A category's item specifics (aspects): REQUIRED ones with valid values, recommended ones, "
              "whether each may vary across variations, and free-text vs selection-only.",
              {"category_id": {"type": "string"}, "marketplace": mkt,
               "max_values": {"type": "integer", "description": "Values listed per aspect (default 30)."}},
              ["category_id"]),
        _tool(types, "ebay_account_setup",
              "The seller's business policies (shipping/fulfillment, payment, return) and inventory "
              "locations, whose ids a listing needs. Optionally create a location first: "
              "create_location={key, name, address:{addressLine1, city, stateOrProvince, postalCode, country}}.",
              {"marketplace": mkt, "create_location": {"type": "object"}}),
        _tool(types, "ebay_upload_media",
              "Upload LOCAL image and video files to eBay; returns eBay-hosted image URLs (for image_urls) "
              "and video ids (for video_ids).",
              {"paths": {"type": "array", "items": {"type": "string"}},
               "video_wait_s": {"type": "number", "description": "Seconds to wait for a video to go LIVE (default 60)."}},
              ["paths"]),
        _tool(types, "ebay_publish_listing",
              "Create or update and PUBLISH one eBay listing (single item or a variation family). Spec: "
              "{marketplace, category_id, condition (NEW, USED_EXCELLENT, ...), merchant_location_key, "
              "listing_policies:{fulfillment_policy_id, payment_policy_id, return_policy_id}, format "
              "(FIXED_PRICE), items:[{sku, title, description, aspects:{Name:[values]}, image_urls, video_ids, "
              "brand, mpn, upc, ean, price, quantity}], group (only for variations): {key, title, description, "
              "aspects (shared), image_urls, varies_by:{Color:[...], Size:[...]}, image_varies_by:[\"Color\"]}}. "
              "Idempotent by SKU/group key: on errors fix the named fields and call again.",
              {"spec": {"type": "object"}}, ["spec"]),
        _tool(types, "ebay_csv_inspect",
              "Read an eBay Seller Hub bulk-listing CSV template: site, columns, required columns, item "
              "specifics (C:) columns.",
              {"template_path": {"type": "string"}}, ["template_path"]),
        _tool(types, "ebay_csv_fill",
              "Fill an eBay bulk-listing CSV template. Spec: {action: Add|Revise|End, listings:[{sku, "
              "category_id, title, description, condition_id, price, quantity, pic_urls:[public URLs], "
              "aspects:{Brand: ...}, shipping_profile, return_profile, payment_profile, location, "
              "fields:{<exact column>: value}, variations:[{sku, specifics:{Color: Red}, price, quantity, "
              "pic_url}]}]}. Returns upload_file + warnings.",
              {"template_path": {"type": "string"}, "spec": {"type": "object"},
               "out_path": {"type": "string"}}, ["template_path", "spec"]),
        _tool(types, "ebay_csv_parse_result",
              "Read the results file of a Seller Hub bulk upload: per-row status, error codes/messages, "
              "listed item ids, and a done verdict.",
              {"result_path": {"type": "string"}}, ["result_path"]),
    ]
