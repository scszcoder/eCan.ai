"""``ec_bulk_file_build``: approved ProposedActions -> the file the platform's own upload takes.

  google_ads        Google Ads Editor / bulk-upload CSV (campaign status, budget, bidding,
                    keywords, campaign negatives). Shared negative lists have no bulk path,
                    so they come back in ``manual`` for the person to paste.
  gmc_supplemental  Merchant Center supplemental feed (TSV): id + the changed attributes.
  shopify_products  Shopify Products CSV import: Handle + only the changed columns, so an
                    import overwrites nothing else. Price, inventory, variants, status and
                    handle are never written.

Only actions with ``status: "approved"`` are written; others are returned in ``skipped``.
The file is a draft for the upload screen's own preview: nothing is applied here.
"""
from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any, Dict, List, Tuple

_MATCH = {"exact": "Exact", "phrase": "Phrase", "broad": "Broad"}
_BIDDING = {"max_clicks": "Maximize clicks", "max_conversions": "Maximize conversions",
            "max_conv_value": "Maximize conversion value", "troas": "Target ROAS", "tcpa": "Target CPA"}

GADS_COLUMNS = ["Action", "Campaign", "Ad group", "Campaign status", "Budget", "Bid strategy type",
                "Target ROAS", "Target CPA", "Keyword", "Criterion Type", "Status"]
SHOPIFY_COLUMNS = {"title": "Title", "body_html": "Body (HTML)", "seo_title": "SEO Title",
                   "seo_description": "SEO Description", "tags": "Tags", "product_type": "Type",
                   "product_category": "Product Category", "image_src": "Image Src", "image_alt": "Image Alt Text"}
SHOPIFY_NEVER = {"price", "variant_price", "compare_at", "inventory", "variants", "status", "handle",
                 "variant_sku", "published"}
GMC_ATTRIBUTES = ("title", "description", "product_type", "google_product_category", "custom_label_0",
                  "custom_label_1", "custom_label_2", "custom_label_3", "custom_label_4", "identifier_exists",
                  "brand", "mpn", "gtin", "product_highlight")


def _approved(actions: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    ok = [a for a in actions if a.get("status") == "approved"]
    return ok, [{"action_id": a.get("action_id"), "reason": f"status is {a.get('status')}"}
                for a in actions if a.get("status") != "approved"]


def _campaign(a: Dict[str, Any]) -> str:
    t = a.get("target") or {}
    after = a.get("after") or {}
    if t.get("type") == "campaign":
        return t.get("id", "")
    return after.get("campaign") or (t.get("parent") or {}).get("id") or t.get("name") or ""


def google_ads_rows(actions: List[Dict[str, Any]]) -> Tuple[List[Dict[str, str]], List[Dict[str, Any]]]:
    rows, manual = [], []
    for a in actions:
        after, kind, camp = a.get("after") or {}, a.get("type"), _campaign(a)
        row = {c: "" for c in GADS_COLUMNS}
        row["Campaign"] = camp
        if kind == "campaign_pause":
            row.update({"Action": "Edit", "Campaign status": "Paused"})
        elif kind == "budget_change":
            row.update({"Action": "Edit", "Budget": f"{float(after['budget']):.2f}"})
        elif kind == "bidding_change":
            row.update({"Action": "Edit", "Bid strategy type": _BIDDING.get(after.get("strategy"), after.get("strategy"))})
            if after.get("strategy") == "troas" and after.get("target") is not None:
                row["Target ROAS"] = f"{float(after['target']) * 100:.0f}%"
            if after.get("strategy") == "tcpa" and after.get("target") is not None:
                row["Target CPA"] = f"{float(after['target']):.2f}"
        elif kind == "negate_keyword":
            if after.get("level") == "shared_list":
                manual.append({"action_id": a.get("action_id"), "what": "add to the shared negative keyword list",
                               "term": after.get("term"), "match": after.get("match")})
                continue
            row.update({"Action": "Add", "Keyword": after["term"],
                        "Criterion Type": f"Campaign negative {after.get('match', 'exact')}"})
        elif kind == "add_keyword":
            row.update({"Action": "Add", "Ad group": after.get("ad_group") or "", "Keyword": after["term"],
                        "Criterion Type": _MATCH.get(after.get("match"), "Exact"), "Status": "Enabled"})
            if not row["Campaign"] and after.get("campaign_series"):
                manual.append({"action_id": a.get("action_id"), "what": "pick the campaign and ad group for "
                               f"the {after['campaign_series']} keyword", "term": after["term"]})
                continue
        else:
            manual.append({"action_id": a.get("action_id"), "what": f"no Google Ads bulk column for {kind}"})
            continue
        rows.append(row)
    return rows, manual


def gmc_supplemental_rows(actions: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    by_id: Dict[str, Dict[str, str]] = {}
    for a in actions:
        item = str((a.get("target") or {}).get("id") or "")
        attrs = {k: v for k, v in (a.get("after") or {}).items() if k in GMC_ATTRIBUTES and v is not None}
        if item and attrs:
            by_id.setdefault(item, {"id": item}).update({k: str(v) for k, v in attrs.items()})
    return list(by_id.values())


def shopify_rows(actions: List[Dict[str, Any]]) -> Tuple[List[Dict[str, str]], List[Dict[str, Any]]]:
    by_handle: Dict[str, Dict[str, str]] = {}
    refused = []
    for a in actions:
        t = a.get("target") or {}
        handle = str(t.get("id") or "")
        after = a.get("after") or {}
        bad = sorted(k for k in after if k in SHOPIFY_NEVER)
        if bad:
            refused.append({"action_id": a.get("action_id"), "reason": f"never written by an import: {bad}"})
            continue
        cols = {SHOPIFY_COLUMNS[k]: str(v) for k, v in after.items() if k in SHOPIFY_COLUMNS and v is not None}
        if handle and cols:
            by_handle.setdefault(handle, {"Handle": handle}).update(cols)
    return list(by_handle.values()), refused


def _csv(rows: List[Dict[str, str]], columns: List[str], delimiter: str = ",") -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=columns, delimiter=delimiter, extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def build(platform: str, actions: List[Dict[str, Any]], out_path: Path) -> Dict[str, Any]:
    approved, skipped = _approved(actions)
    manual: List[Dict[str, Any]] = []
    if platform == "google_ads":
        rows, manual = google_ads_rows(approved)
        used = [c for c in GADS_COLUMNS if any(r.get(c) for r in rows)]
        text = _csv(rows, used or ["Action", "Campaign"])
    elif platform == "gmc_supplemental":
        rows = gmc_supplemental_rows(approved)
        used = ["id"] + [c for c in GMC_ATTRIBUTES if any(c in r for r in rows)]
        text = _csv(rows, used, delimiter="\t")
    elif platform == "shopify_products":
        rows, refused = shopify_rows(approved)
        skipped += refused
        used = ["Handle"] + [c for c in SHOPIFY_COLUMNS.values() if any(c in r for r in rows)]
        text = _csv(rows, used)
    else:
        raise ValueError(f"no bulk file for platform {platform!r}")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")
    return {"path": str(out_path), "rows": len(rows), "columns": used, "manual": manual, "skipped": skipped}
