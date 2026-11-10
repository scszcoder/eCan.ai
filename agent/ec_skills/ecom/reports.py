"""``ec_report_detect`` / ``ec_report_normalize``: a downloaded report file -> canonical rows.

Handles the files the platforms' own download buttons produce:
  * Google Ads report downloads (CSV, or UTF-16 tab-separated "CSV for Excel"), which open
    with a title line and a date-range line, end with "Total: ..." rows, and write
    "--", "< 10%", "> 90%", "1,234.56" and "12.3%".
  * Shopify Products export (one row per variant/image; product fields only on the first).
  * Merchant Center product lists (status + issues per item).

Headers are matched loosely (case, spacing, punctuation, a few known aliases), so an export
with extra or reordered columns still works. A file that matches no known report returns
``report_type: None`` rather than a guess.
"""
from __future__ import annotations

import csv
import io
import re
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# canonical table -> {canonical column: [header aliases]}; the first group lists the columns
# that must be present for the file to be that report.
REPORTS: Dict[str, Dict[str, Any]] = {
    "gads_search_term_rows": {
        "platform": "google_ads",
        "required": ["search_term", "clicks", "cost"],
        "columns": {
            "date": ["day", "date"], "search_term": ["search term"], "match_type": ["match type",
                                                                                     "search term match type"],
            "campaign": ["campaign"], "ad_group": ["ad group"], "added_excluded": ["added/excluded"],
            "impressions": ["impr.", "impressions"], "clicks": ["clicks"], "cost": ["cost"],
            "conversions": ["conversions", "conv."], "conv_value": ["conv. value", "conversion value",
                                                                     "total conv. value"],
            "currency": ["currency code", "currency"],
        },
    },
    "gads_product_rows": {
        "platform": "google_ads",
        "required": ["item_id", "clicks", "cost"],
        "columns": {
            "date": ["day", "date"], "item_id": ["item id", "product item id", "offer id"],
            "title": ["title", "product title"], "campaign": ["campaign"],
            "product_type": ["product type (1st level)", "product type (first level)", "product type"],
            "brand": ["brand"], "custom_label_0": ["custom label 0"], "custom_label_1": ["custom label 1"],
            "custom_label_2": ["custom label 2"], "custom_label_3": ["custom label 3"],
            "custom_label_4": ["custom label 4"],
            "impressions": ["impr.", "impressions"], "clicks": ["clicks"], "cost": ["cost"],
            "conversions": ["conversions", "conv."], "conv_value": ["conv. value", "conversion value"],
            "currency": ["currency code", "currency"],
        },
    },
    "gads_campaign_rows": {
        "platform": "google_ads",
        "required": ["campaign", "clicks", "cost"],
        "columns": {
            "date": ["day", "date"], "campaign": ["campaign"], "type": ["campaign type", "advertising channel"],
            "status": ["campaign status", "status"], "budget": ["budget", "daily budget"],
            "bidding": ["bid strategy type", "bid strategy", "bidding strategy type"],
            "target_roas": ["target roas", "target roas (%)"], "target_cpa": ["target cpa"],
            "impressions": ["impr.", "impressions"], "clicks": ["clicks"], "cost": ["cost"],
            "conversions": ["conversions", "conv."], "conv_value": ["conv. value", "conversion value"],
            "search_is": ["search impr. share", "search impression share"],
            "lost_is_budget": ["search lost is (budget)", "search lost impression share (budget)"],
            "lost_is_rank": ["search lost is (rank)", "search lost impression share (rank)"],
            "currency": ["currency code", "currency"],
        },
    },
    "shopify_product_rows": {
        "platform": "shopify",
        "required": ["handle", "title", "variant_price"],
        "columns": {
            "handle": ["handle"], "title": ["title"], "body_html": ["body (html)", "body html", "description"],
            "vendor": ["vendor"], "product_category": ["product category",
                                                       "google shopping / google product category"],
            "product_type": ["type", "product type"], "tags": ["tags"], "published": ["published"],
            "status": ["status"], "variant_sku": ["variant sku", "sku"], "variant_price": ["variant price", "price"],
            "compare_at": ["variant compare at price", "compare at price"],
            "inventory": ["variant inventory qty", "inventory quantity"],
            "variant_barcode": ["variant barcode", "barcode"], "cost_per_item": ["cost per item"],
            "image_src": ["image src"], "image_alt": ["image alt text"], "seo_title": ["seo title"],
            "seo_description": ["seo description"],
            "gs_mpn": ["google shopping / mpn"], "gs_condition": ["google shopping / condition"],
            "gs_custom_product": ["google shopping / custom product"],
            "gs_custom_label_0": ["google shopping / custom label 0"],
        },
    },
    "gmc_product_rows": {
        "platform": "google_merchant_center",
        "required": ["item_id", "status"],
        "columns": {
            "item_id": ["item id", "offer id", "id", "product id"], "title": ["title", "product title"],
            "status": ["status", "approval status", "overall status"],
            "issue": ["issue", "issues", "item issues", "disapproval reasons", "issue title"],
            "severity": ["severity", "issue severity"], "detail": ["detail", "issue detail", "description"],
            "destinations": ["destinations", "marketing methods", "destination"],
            "price": ["price"], "availability": ["availability"], "gtin": ["gtin"], "brand": ["brand"],
            "mpn": ["mpn"], "image_link": ["image link"], "link": ["link"],
            "google_product_category": ["google product category"],
        },
    },
}

_NUMERIC = {"impressions", "clicks", "cost", "conversions", "conv_value", "budget", "target_roas", "target_cpa",
            "search_is", "lost_is_budget", "lost_is_rank", "variant_price", "compare_at", "inventory",
            "cost_per_item", "price"}
_PERCENT_AS_FRACTION = {"search_is", "lost_is_budget", "lost_is_rank", "target_roas"}
_EMPTY = {"", "--", "-", "n/a", "na", "none", "null", " --"}

_BIDDING = {
    "maximize clicks": "max_clicks", "maximise clicks": "max_clicks", "manual cpc": "manual_cpc",
    "enhanced cpc": "manual_cpc", "maximize conversions": "max_conversions", "maximise conversions": "max_conversions",
    "maximize conversion value": "max_conv_value", "maximise conversion value": "max_conv_value",
    "target roas": "troas", "target cpa": "tcpa", "target impression share": "target_is",
}
_CAMPAIGN_TYPES = {"performance max": "pmax", "shopping": "shopping", "search": "search",
                   "display": "display", "video": "video", "demand gen": "demand_gen"}


def _key(header: str) -> str:
    return re.sub(r"\s+", " ", str(header or "").replace("﻿", "").strip().lower())


def read_table(path: Path) -> Tuple[List[str], List[List[str]], List[str]]:
    """(header, rows, preamble lines) from a CSV/TSV/XLSX export. The header is the first row
    with at least 3 non-empty cells; lines above it (report title, date range) are the preamble."""
    path = Path(path)
    if path.suffix.lower() in (".xlsx", ".xlsm"):
        from openpyxl import load_workbook
        wb = load_workbook(path, read_only=True, data_only=True)
        raw = [["" if c is None else str(c) for c in r] for r in wb.worksheets[0].iter_rows(values_only=True)]
        wb.close()
    else:
        data = path.read_bytes()
        if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
            text = data.decode("utf-16")
        else:
            text = data.decode("utf-8-sig", errors="replace")
        sample = "\n".join(text.splitlines()[:10])
        delim = "\t" if sample.count("\t") > sample.count(",") else ","
        raw = list(csv.reader(io.StringIO(text), delimiter=delim))
    start = next((i for i, r in enumerate(raw) if sum(1 for c in r if str(c).strip()) >= 3), 0)
    preamble = [" ".join(c for c in r if c).strip() for r in raw[:start] if any(str(c).strip() for c in r)]
    header = [str(c) for c in (raw[start] if raw else [])]
    return header, raw[start + 1:], preamble


def _header_map(header: List[str], spec: Dict[str, List[str]]) -> Dict[str, int]:
    keys = [_key(h) for h in header]
    found: Dict[str, int] = {}
    for col, aliases in spec.items():
        for alias in aliases:
            if alias in keys:
                found[col] = keys.index(alias)
                break
    return found


def detect(path: Path) -> Dict[str, Any]:
    header, _rows, preamble = read_table(path)
    best: Optional[Tuple[str, Dict[str, int]]] = None
    for name, spec in REPORTS.items():
        hmap = _header_map(header, spec["columns"])
        if all(c in hmap for c in spec["required"]):
            if best is None or len(hmap) > len(best[1]):
                best = (name, hmap)
    if not best:
        return {"report_type": None, "platform": None, "confidence": 0.0, "header": header, "preamble": preamble}
    name, hmap = best
    unmatched = [h for i, h in enumerate(header) if i not in hmap.values() and str(h).strip()]
    return {"report_type": name, "platform": REPORTS[name]["platform"],
            "confidence": round(len(hmap) / max(1, len([h for h in header if str(h).strip()])), 2),
            "header_map": {c: header[i] for c, i in hmap.items()}, "unmatched_headers": unmatched,
            "preamble": preamble, "date_range": _date_range(preamble)}


def _date_range(preamble: List[str]) -> Optional[List[str]]:
    from datetime import datetime
    for line in preamble:
        parts = re.split(r"\s+[-–]\s+", line)
        if len(parts) == 2:
            out = []
            for p in parts:
                for fmt in ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d", "%d %B %Y", "%m/%d/%Y"):
                    try:
                        out.append(datetime.strptime(p.strip(), fmt).strftime("%Y-%m-%d"))
                        break
                    except ValueError:
                        continue
            if len(out) == 2:
                return out
    return None


def number(value: Any, as_fraction: bool = False) -> Optional[float]:
    """'1,234.56' -> 1234.56; '12.5%' -> 12.5 (or 0.125 with ``as_fraction``); '< 10%' -> 0.1
    (Google's floor); '> 90%' -> 0.9; '--' -> None."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().lower()
    if s in _EMPTY:
        return None
    pct = "%" in s
    s = re.sub(r"[<>\s,$€£¥%]|us\$|ca\$|au\$|a\$|c\$", "", s)
    try:
        n = float(s)
    except ValueError:
        return None
    return n / 100 if (pct and as_fraction) else n


def _date(value: Any) -> Optional[str]:
    from datetime import datetime
    s = str(value or "").strip()
    if not s or s.lower() in _EMPTY:
        return None
    for fmt in ("%Y-%m-%d", "%b %d, %Y", "%B %d, %Y", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return s


def normalize(path: Path, report_type: Optional[str] = None) -> Dict[str, Any]:
    """Rows in the canonical columns of ``report_type`` (detected when not given)."""
    det = detect(path)
    report_type = report_type or det["report_type"]
    if not report_type:
        return {"table": None, "rows": [], "warnings": ["no known report matches these headers"], "detect": det}
    spec = REPORTS[report_type]
    header, raw, _pre = read_table(path)
    hmap = _header_map(header, spec["columns"])
    missing = [c for c in spec["required"] if c not in hmap]
    if missing:
        return {"table": report_type, "rows": [], "warnings": [f"missing required columns: {missing}"],
                "detect": det}
    rows, warnings, skipped_totals = [], [], 0
    first_col = min(hmap.values())
    for r in raw:
        if not any(str(c).strip() for c in r):
            continue
        lead = str(r[first_col] if first_col < len(r) else "").strip().lower()
        if lead.startswith("total") or any(str(c).strip().lower().startswith("total:") for c in r[:3]):
            skipped_totals += 1
            continue
        row: Dict[str, Any] = {}
        for col, idx in hmap.items():
            cell = r[idx] if idx < len(r) else ""
            if col in _NUMERIC:
                row[col] = number(cell, as_fraction=col in _PERCENT_AS_FRACTION)
            elif col == "date":
                row[col] = _date(cell)
            else:
                s = str(cell).strip()
                row[col] = None if s.lower() in _EMPTY else s
        rows.append(row)
    rows = _post(report_type, rows)
    if skipped_totals:
        warnings.append(f"skipped {skipped_totals} total row(s)")
    return {"table": report_type, "rows": rows, "warnings": warnings, "detect": det}


def _post(report_type: str, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if report_type == "gads_campaign_rows":
        for r in rows:
            r["bidding"] = _BIDDING.get(_key(r.get("bidding")), r.get("bidding"))
            r["type"] = _CAMPAIGN_TYPES.get(_key(r.get("type")), r.get("type"))
            if r.get("status"):
                r["status"] = _key(r["status"])
            # Google writes target ROAS as a percentage ("400%"): keep it as the ratio 4.0.
    if report_type in ("gads_search_term_rows",):
        for r in rows:
            mt = _key(r.get("match_type"))
            r["match_type"] = ("exact" if "exact" in mt else "phrase" if "phrase" in mt
                               else "broad" if "broad" in mt else mt or None)
    if report_type == "gmc_product_rows":
        for r in rows:
            r["status"] = _key(r.get("status")).replace("not approved", "disapproved") or None
    if report_type == "shopify_product_rows":
        return _shopify_products(rows)
    return rows


def _shopify_products(variant_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One row per product (handle): product fields from its first row, variant/image counts
    from the rest."""
    by_handle: "OrderedDict[str, List[Dict[str, Any]]]" = OrderedDict()
    for r in variant_rows:
        if r.get("handle"):
            by_handle.setdefault(r["handle"], []).append(r)
    out = []
    for handle, rs in by_handle.items():
        head = next((r for r in rs if r.get("title")), rs[0])
        variants = [r for r in rs if r.get("variant_price") is not None or r.get("variant_sku")]
        images = [r for r in rs if r.get("image_src")]
        prices = [r["variant_price"] for r in variants if r.get("variant_price") is not None]
        costs = [r["cost_per_item"] for r in variants if r.get("cost_per_item") is not None]
        inv = [r["inventory"] for r in variants if r.get("inventory") is not None]
        out.append({
            "product_id": handle, "handle": handle, "title": head.get("title"), "body_html": head.get("body_html"),
            "vendor": head.get("vendor"), "product_type": head.get("product_type"),
            "product_category": head.get("product_category"), "tags": head.get("tags"),
            "status": (head.get("status") or "").lower() or None, "published": head.get("published"),
            "price": min(prices) if prices else None, "price_max": max(prices) if prices else None,
            "compare_at": head.get("compare_at"),
            "inventory": sum(inv) if inv else None, "variant_count": len(variants),
            "skus": [r["variant_sku"] for r in variants if r.get("variant_sku")],
            "barcodes": [r["variant_barcode"] for r in variants if r.get("variant_barcode")],
            "cost_per_item": (sum(costs) / len(costs)) if costs else None,
            "cost_coverage": round(len(costs) / len(variants), 2) if variants else 0.0,
            "image_count": len(images), "images_missing_alt": sum(1 for r in images if not r.get("image_alt")),
            "seo_title": head.get("seo_title"), "seo_description": head.get("seo_description"),
            "gs_mpn": head.get("gs_mpn"), "gs_custom_product": head.get("gs_custom_product"),
            "custom_label_0": head.get("gs_custom_label_0"),
        })
    return out
