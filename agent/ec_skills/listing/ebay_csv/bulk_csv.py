"""eBay Seller Hub bulk-listing CSV: inspect a template, fill it, read the results file.

The template is the one the seller downloads from Seller Hub (Reports ->
Uploads -> Download template). Its header row starts with the Action column,
e.g. ``*Action(SiteID=US|Country=US|Currency=USD|Version=1193)``; a leading
``*`` marks a required column and ``C:<Name>`` columns are item specifics.
Lines above the header (``#INFO`` ...) are kept verbatim. Columns are matched
by name, never by position, so a changed template still fills correctly.
"""
import csv
import io
import os
import re
from typing import Dict, List, Optional, Tuple

# friendly spec key -> template column (bare name, without * or (...))
FRIENDLY = {
    "sku": "CustomLabel", "category_id": "Category", "category": "Category", "title": "Title",
    "subtitle": "Subtitle", "description": "Description", "condition_id": "ConditionID",
    "condition_description": "ConditionDescription", "price": "StartPrice",
    "quantity": "Quantity", "format": "Format", "duration": "Duration", "location": "Location",
    "postal_code": "PostalCode", "upc": "Product:UPC", "ean": "Product:EAN", "epid": "Product:EPID",
    "shipping_profile": "ShippingProfileName", "return_profile": "ReturnProfileName",
    "payment_profile": "PaymentProfileName", "best_offer": "BestOfferEnabled",
    "store_category": "StoreCategory", "item_id": "ItemID",
}
DEFAULTS = {"Format": "FixedPrice", "Duration": "GTC"}


def _bare(col: str) -> str:
    """'*Action(SiteID=US|...)' -> 'Action'; '*C:Brand' -> 'C:Brand'."""
    return re.sub(r"\(.*\)$", "", col.strip().lstrip("*")).strip()


def _read(path: str) -> Tuple[List[List[str]], int]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    for i, r in enumerate(rows):
        if r and _bare(r[0]).lower() == "action":
            return rows, i
    raise ValueError(f"{os.path.basename(path)}: no header row starting with the Action column "
                     "-- is this an eBay bulk-listing template?")


def inspect_template(path: str) -> dict:
    rows, h = _read(path)
    header = rows[h]
    action = header[0]
    site = dict(kv.split("=", 1) for kv in re.findall(r"[A-Za-z]+=[^|)]+", action))
    return {
        "template": path,
        "action_column": action,
        "site": site,
        "columns": [_bare(c) for c in header if c.strip()],
        "required": [_bare(c) for c in header if c.strip().startswith("*")],
        "item_specifics": [_bare(c)[2:] for c in header if _bare(c).startswith("C:")],
        "info_lines": [r for r in rows[:h] if any(x.strip() for x in r)][:5],
        "example_rows": len([r for r in rows[h + 1:] if any(x.strip() for x in r)]),
    }


def _row_cells(spec_row: dict, index: Dict[str, int], header: List[str],
               warnings: List[str], label: str) -> List[str]:
    cells = [""] * len(header)

    def put(col: str, value):
        if value is None or value == "":
            return
        i = index.get(col.lower())
        if i is None:
            header.append(col)
            index[col.lower()] = i = len(header) - 1
            cells.append("")
            warnings.append(f"{label}: column {col!r} is not in the template; added it")
        if isinstance(value, bool):
            value = "1" if value else "0"
        if isinstance(value, (list, tuple)):
            value = "|".join(str(v) for v in value)
        cells[i] = str(value)

    for k, v in spec_row.items():
        if k in ("aspects", "variations", "fields", "pic_urls", "image_urls", "specifics"):
            continue
        put(FRIENDLY.get(k, k), v)
    for name, v in (spec_row.get("aspects") or {}).items():
        put(f"C:{name}", v if not isinstance(v, list) else "|".join(map(str, v)))
    pics = spec_row.get("pic_urls") or spec_row.get("image_urls")
    if pics:
        put("PicURL", "|".join(pics))
    for k, v in (spec_row.get("fields") or {}).items():
        put(_bare(k), v)
    return cells


def fill_template(template: str, spec: dict, out: Optional[str] = None) -> dict:
    """spec = {"action": "Add", "listings": [row, ...]}; a row with "variations" is a family.

    Row keys: friendly keys (see FRIENDLY), "aspects" {Name: value} -> C:Name,
    "pic_urls" [urls], "fields" {exact column: value}. A family row carries the
    shared data; each variation {"sku", "specifics": {"Color": "Red"}, "price",
    "quantity", "pic_url"?} becomes a child row.
    """
    rows, h = _read(template)
    header = list(rows[h])
    index = {_bare(c).lower(): i for i, c in enumerate(header) if c.strip()}
    warnings: List[str] = []
    out_rows: List[List[str]] = []
    action = spec.get("action") or "Add"
    listings = spec.get("listings") or []
    if not listings:
        raise ValueError("spec.listings is empty")

    required = [_bare(c) for c in header if c.strip().startswith("*") and _bare(c) != "Action"]
    for n, lst in enumerate(listings):
        label = lst.get("sku") or f"listings[{n}]"
        row = {**{k: v for k, v in DEFAULTS.items()}, **lst}
        variations = row.pop("variations", None) or []
        if variations:
            names: List[str] = []
            values: Dict[str, List[str]] = {}
            for var in variations:
                for k, v in (var.get("specifics") or {}).items():
                    if k not in values:
                        names.append(k)
                        values[k] = []
                    if str(v) not in values[k]:
                        values[k].append(str(v))
            row["RelationshipDetails"] = "|".join(f"{k}={';'.join(values[k])}" for k in names)
            row.pop("price", None)
            row.pop("quantity", None)
        cells = _row_cells(row, index, header, warnings, label)
        cells[0] = action
        out_rows.append(cells)
        if not variations:
            missing = [c for c in required if not cells[index[c.lower()]]]
            if missing:
                warnings.append(f"{label}: required column(s) empty: {', '.join(missing)}")
        for var in variations:
            vlabel = var.get("sku") or label
            vrow = {"sku": var.get("sku"), "price": var.get("price"), "quantity": var.get("quantity"),
                    "Relationship": "Variation",
                    "RelationshipDetails": "|".join(f"{k}={v}" for k, v in (var.get("specifics") or {}).items())}
            if var.get("pic_url"):
                vrow["PicURL"] = var["pic_url"]
            vcells = _row_cells(vrow, index, header, warnings, vlabel)
            vcells[0] = ""
            out_rows.append(vcells)
            for col in ("StartPrice", "Quantity", "CustomLabel"):
                i = index.get(col.lower())
                if i is not None and not vcells[i]:
                    warnings.append(f"{vlabel}: variation needs {col}")

    width = len(header)
    out_rows = [r + [""] * (width - len(r)) for r in out_rows]
    out = out or os.path.splitext(template)[0] + "_filled.csv"
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    for r in rows[:h]:
        w.writerow(r)
    w.writerow(header)
    w.writerows(out_rows)
    with open(out, "w", encoding="utf-8", newline="") as f:
        f.write(buf.getvalue())
    return {"upload_file": out, "rows": len(out_rows), "listings": len(listings), "warnings": warnings}


_STATUS_COLS = ("status", "result")
_ERR_COLS = ("errorcode", "error code", "errorid", "error id")
_MSG_COLS = ("errormessage", "error message", "message", "errors", "error")
_ID_COLS = ("itemid", "item id", "item number", "itemnumber")
_SKU_COLS = ("customlabel", "custom label", "sku", "custom label (sku)")


def parse_results(path: str) -> dict:
    """The upload results file eBay produces for a bulk upload -> per-row outcome."""
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    h = next((i for i, r in enumerate(rows)
              if any(_bare(c).lower() in _STATUS_COLS for c in r)), None)
    if h is None:
        raise ValueError("no Status column found -- is this the upload results file?")
    header = [_bare(c).lower() for c in rows[h]]

    def col(names):
        return next((i for i, c in enumerate(header) if c in names), None)

    si, ei, mi, ii, ki = col(_STATUS_COLS), col(_ERR_COLS), col(_MSG_COLS), col(_ID_COLS), col(_SKU_COLS)
    items, errors, warnings, listed = [], 0, 0, []
    for r in rows[h + 1:]:
        if not any(x.strip() for x in r):
            continue
        g = lambda i: r[i].strip() if i is not None and i < len(r) else ""
        status = g(si)
        sev = ("error" if re.search(r"fail|error", status, re.I)
               else "warning" if re.search(r"warn", status, re.I) or (g(mi) and not re.search(r"fail", status, re.I) and g(ei))
               else "ok")
        item = {"status": status, "sku": g(ki) or None, "item_id": g(ii) or None,
                "error_code": g(ei) or None, "message": g(mi) or None, "severity": sev}
        items.append(item)
        errors += sev == "error"
        warnings += sev == "warning"
        if item["item_id"] and sev != "error":
            listed.append(item["item_id"])
    return {"rows": len(items), "errors": errors, "warnings": warnings, "listed_item_ids": listed,
            "items": items, "done": errors == 0 and bool(items)}
