"""Amazon listing via the category flat file -- the deterministic half.

A skill lists on Amazon through Seller Central's "Add Products via Upload":
a browser node downloads the category template, these tools turn a JSON
listing spec into the upload file and read Amazon's processing report back,
and the LLM fixes exactly the fields the report names until it is clean.
What an LLM cannot do reliably -- edit a 200-column macro workbook, route
per-marketplace offer columns, read field errors out of cell comments -- is
done here (agent/ec_skills/listing/amazon_flatfile, ported from vibe-seller).

Tools (all take their arguments under ``input``, return JSON text + meta):

* ``amazon_template_inspect`` -- what this template needs: dialect,
  marketplaces it is stamped for, the columns friendly spec keys map to,
  required fields and their valid values.
* ``amazon_template_fill``    -- spec in -> the tab-delimited file to upload.
* ``amazon_parse_feedback``   -- processing report in -> per-field errors and
  a ``done`` verdict (only 18320 "missing main image" may remain).
"""

import json
import os
from typing import Any, Dict, List

from mcp.types import TextContent

from utils.logger_helper import logger_helper as logger

_MAX_VALUES_DEFAULT = 40      # valid values listed per field (enums can run to 1000s)
_MAX_ITEMS = 200              # report findings returned


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


def _cap(values, n):
    if not values:
        return values
    return values if len(values) <= n else values[:n] + [f"... ({len(values) - n} more)"]


async def amazon_template_inspect(mainwin, args):
    try:
        from agent.ec_skills.listing.amazon_flatfile.listing_bulk import inspect_template
        inp = _input(args)
        path = _need_file(inp.get("template_path"), "template_path")
        n = int(inp.get("max_values") or _MAX_VALUES_DEFAULT)
        info = inspect_template(path, inp.get("field") or None)
        if "values" in info:
            info["values"] = _cap(info["values"], max(n, 200))
        else:
            info["required"] = {f: _cap(v, n) for f, v in info["required"].items()}
            for r in info["roles"].values():
                r["values"] = _cap(r["values"], n)
        return _reply({"ok": True, **info})
    except SystemExit as e:
        return _reply({"ok": False, "error": str(e)})
    except Exception as e:
        logger.warning(f"[amazon_template_inspect] {e}")
        return _reply({"ok": False, "error": str(e)})


async def amazon_template_fill(mainwin, args):
    try:
        from agent.ec_skills.listing.amazon_flatfile.listing_bulk import fill_template
        inp = _input(args)
        template = _need_file(inp.get("template_path"), "template_path")
        spec = inp.get("spec")
        if isinstance(spec, str):
            spec = json.loads(spec)
        if not isinstance(spec, dict) or not spec.get("rows"):
            raise ValueError("spec must be an object with a non-empty 'rows' list")
        out = str(inp.get("out_path") or "").strip()
        if not out:
            base, ext = os.path.splitext(template)
            out = f"{base}_filled{ext or '.xlsm'}"
        res = fill_template(template, spec, out, inp.get("marketplace") or None)
        return _reply({"ok": True, **res,
                       "next": "upload the file in 'upload_file' (the .txt), not the Excel file"})
    except SystemExit as e:
        return _reply({"ok": False, "error": str(e)})
    except Exception as e:
        logger.warning(f"[amazon_template_fill] {e}")
        return _reply({"ok": False, "error": str(e)})


async def amazon_parse_feedback(mainwin, args):
    try:
        from agent.ec_skills.listing.amazon_flatfile.listing_bulk import parse_feedback_report
        inp = _input(args)
        path = _need_file(inp.get("report_path"), "report_path")
        res = parse_feedback_report(path, inp.get("batch_id") or None)
        for k in ("items", "field_errors", "loose_rows"):
            if isinstance(res.get(k), list) and len(res[k]) > _MAX_ITEMS:
                res[k + "_truncated"] = len(res[k]) - _MAX_ITEMS
                res[k] = res[k][:_MAX_ITEMS]
        res["next"] = ("done -- verify the listing is live on the target marketplace"
                       if res["done"] else
                       "fix exactly the fields named (parent SKU first), refill, re-upload, re-check")
        return _reply({"ok": True, **res})
    except SystemExit as e:
        return _reply({"ok": False, "error": str(e)})
    except Exception as e:
        logger.warning(f"[amazon_parse_feedback] {e}")
        return _reply({"ok": False, "error": str(e)})


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

_CAT = "<category>E-Commerce</category><sub-category>Amazon Listing</sub-category>"


def add_amazon_listing_tool_schemas(tool_schemas):
    import mcp.types as types

    tool_schemas.append(types.Tool(
        _meta={"run_in_cloud": False},
        name="amazon_template_inspect",
        description=(
            _CAT + "Read an Amazon category flat-file template (.xlsm/.xlsx downloaded from "
            "Seller Central 'Add Products via Upload') and report what it needs: dialect "
            "(legacy/unified), the marketplaces it is stamped for, the column each friendly "
            "spec key (sku, parentage, parent_sku, variation_theme, brand, product_type, "
            "product_id...) fills, and every REQUIRED field with its valid values. Call it "
            "before writing a listing spec; pass `field` to see one field's detail."
        ),
        inputSchema={
            "type": "object", "required": ["input"],
            "properties": {"input": {
                "type": "object", "required": ["template_path"],
                "properties": {
                    "template_path": {"type": "string", "description": "Local path of the downloaded template."},
                    "field": {"type": "string", "description": "Optional: one field API name to detail."},
                    "max_values": {"type": "integer", "description": "Valid values listed per field (default 40)."},
                },
            }},
        },
    ))

    tool_schemas.append(types.Tool(
        _meta={"run_in_cloud": False},
        name="amazon_template_fill",
        description=(
            _CAT + "Fill an Amazon category template from a listing spec and write the "
            "tab-delimited upload file. Spec: {\"product_type\", \"brand\", \"marketplace\" "
            "(e.g. \"US\"), \"rows\": [{\"sku\", \"operation\" (create|update|partialupdate|delete), "
            "\"parentage\" (Parent|Child), \"parent_sku\", \"variation_theme\", \"asin\" (to match "
            "an existing ASIN), \"our_price\", \"quantity\", \"fields\": {<field API name>: value}}]}. "
            "A variation family is one Parent row plus Child rows. Price/stock are routed to the "
            "marketplace's own columns. Returns `upload_file` (upload THAT .txt, never the Excel "
            "file) plus warnings (missing required fields, values outside the template's lists)."
        ),
        inputSchema={
            "type": "object", "required": ["input"],
            "properties": {"input": {
                "type": "object", "required": ["template_path", "spec"],
                "properties": {
                    "template_path": {"type": "string", "description": "Local path of the downloaded template."},
                    "spec": {"type": "object", "description": "The listing spec (see description)."},
                    "marketplace": {"type": "string", "description": "Country code or marketplace id being listed on; overrides spec.marketplace."},
                    "out_path": {"type": "string", "description": "Optional output .xlsm path (default: <template>_filled.xlsm)."},
                },
            }},
        },
    ))

    tool_schemas.append(types.Tool(
        _meta={"run_in_cloud": False},
        name="amazon_parse_feedback",
        description=(
            _CAT + "Read the processing report Amazon returns for an uploaded template and list "
            "every error/warning by SKU and FIELD (Amazon writes the exact field fix as a cell "
            "comment on the report's Template tab). `done` is true only when no error remains "
            "except 18320 (missing main image). If not done: fix exactly the named fields, parent "
            "SKU first, refill and re-upload."
        ),
        inputSchema={
            "type": "object", "required": ["input"],
            "properties": {"input": {
                "type": "object", "required": ["report_path"],
                "properties": {
                    "report_path": {"type": "string", "description": "Local path of the downloaded processing report (.xlsm/.xlsx/.txt/.csv)."},
                    "batch_id": {"type": "string", "description": "Optional upload batch id (reference_id), echoed in the verdict."},
                },
            }},
        },
    ))
