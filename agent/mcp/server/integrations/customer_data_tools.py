"""Customer-data MCP tools: ``query_price`` / ``query_inventories`` / ``query_order``.

These are thin wrappers around vendor-supplied integration code. The actual
data may live in Shopify, WooCommerce, a customer's own ERP read-replica,
a SaaS like Cin7, etc. — the integrator plugs their handler in and the
agent's chatbot calls one canonical MCP tool regardless of backend.

Wiring a vendor
---------------
Two ways:

1. **At import time (preferred for production)** — the integrator's
   bootstrap module calls ``register_vendor_handler``::

       from agent.mcp.server.integrations.customer_data_tools import (
           register_vendor_handler,
       )

       async def _shopify_price(args):
           ...
           return {"sku": "...", "price": 199.0, "currency": "CNY"}

       register_vendor_handler("shopify", "price", _shopify_price)

   The chatbot picks the active vendor via the ``ECAN_CUSTOMER_DATA_VENDOR``
   env var (default: ``"mock"``).

2. **Per call** — the LLM passes ``vendor_id`` in ``input``. Useful for
   multi-tenant deployments where a single agent serves stores running on
   different platforms.

Mock vendor
-----------
A built-in ``mock`` vendor returns deterministic stub data so the chatbot
flow can be exercised end-to-end before a real integration is wired up.
It reads from ``data/customer_data_mock.json`` if present, otherwise
synthesizes a small response. Real deployments should set
``ECAN_CUSTOMER_DATA_VENDOR`` away from ``mock``.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import os
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple

from mcp.types import TextContent

from utils.logger_helper import get_traceback
from utils.logger_helper import logger_helper as logger


# ---------------------------------------------------------------------------
# Vendor registry
# ---------------------------------------------------------------------------

# Tool kinds the registry knows about. Each kind is a separate slot so a
# vendor can implement only what they support (e.g. read-only price/stock
# but no order lookups).
_TOOL_KINDS: Tuple[str, ...] = ("price", "inventory", "order")

VendorHandler = Callable[[Dict[str, Any]], Any]  # may be sync OR async

_VENDOR_HANDLERS: Dict[Tuple[str, str], VendorHandler] = {}


def register_vendor_handler(vendor_id: str, kind: str, fn: VendorHandler) -> None:
    """Register ``fn`` as the handler for ``(vendor_id, kind)``.

    ``fn`` is called with the LLM-supplied ``input`` dict (already validated
    to be a dict). It may be sync or async; if sync it is executed in a
    thread to avoid blocking the event loop. The return value should be a
    JSON-serializable dict matching the contract documented in the tool
    description (price → ``{sku, price, currency, ...}``,
    inventory → ``{sku, on_hand, ...}``, order → ``{order_id, status, ...}``).
    """
    if kind not in _TOOL_KINDS:
        raise ValueError(f"unknown tool kind {kind!r}; expected one of {_TOOL_KINDS}")
    _VENDOR_HANDLERS[(vendor_id, kind)] = fn


def _active_vendor(input_data: Dict[str, Any]) -> str:
    return (
        (input_data.get("vendor_id") or "").strip()
        or os.environ.get("ECAN_CUSTOMER_DATA_VENDOR", "").strip()
        or "mock"
    )


async def _invoke_handler(fn: VendorHandler, input_data: Dict[str, Any]) -> Any:
    if inspect.iscoroutinefunction(fn):
        return await fn(input_data)
    return await asyncio.to_thread(fn, input_data)


# ---------------------------------------------------------------------------
# Built-in "mock" vendor — deterministic stub data for development
# ---------------------------------------------------------------------------

_MOCK_PATH_ENV = "ECAN_CUSTOMER_DATA_MOCK_PATH"


def _load_mock_db() -> Dict[str, Any]:
    p = os.environ.get(_MOCK_PATH_ENV) or str(
        Path(__file__).resolve().parents[4] / "data" / "customer_data_mock.json"
    )
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except FileNotFoundError:
        return {}
    except Exception as e:
        logger.warning(f"[customer_data][mock] failed to load {p!r}: {e}")
        return {}


def _mock_price(input_data: Dict[str, Any]) -> Dict[str, Any]:
    sku = (input_data.get("sku") or "").strip()
    db = _load_mock_db().get("prices", {})
    row = db.get(sku)
    if not row:
        return {"sku": sku, "found": False, "note": "mock vendor: no price for this SKU"}
    return {"sku": sku, "found": True, **row}


def _mock_inventory(input_data: Dict[str, Any]) -> Dict[str, Any]:
    sku = (input_data.get("sku") or "").strip()
    db = _load_mock_db().get("inventory", {})
    row = db.get(sku)
    if not row:
        return {"sku": sku, "found": False, "note": "mock vendor: no stock record for this SKU"}
    return {"sku": sku, "found": True, **row}


def _mock_order(input_data: Dict[str, Any]) -> Dict[str, Any]:
    order_id = (input_data.get("order_id") or "").strip()
    db = _load_mock_db().get("orders", {})
    row = db.get(order_id)
    if not row:
        return {
            "order_id": order_id,
            "found": False,
            "note": "mock vendor: order not found",
        }
    return {"order_id": order_id, "found": True, **row}


register_vendor_handler("mock", "price", _mock_price)
register_vendor_handler("mock", "inventory", _mock_inventory)
register_vendor_handler("mock", "order", _mock_order)


# ---------------------------------------------------------------------------
# Shared MCP tool body
# ---------------------------------------------------------------------------

async def _dispatch(kind: str, args: Dict[str, Any], required: Tuple[str, ...]) -> list[TextContent]:
    try:
        input_data = (args or {}).get("input", {}) or {}
        if not isinstance(input_data, dict):
            return [TextContent(type="text", text="Error: input must be an object")]

        missing = [k for k in required if not (input_data.get(k) or "").strip()] if required else []
        if missing:
            msg = f"Missing required field(s): {', '.join(missing)}"
            result = TextContent(type="text", text=f"Error: {msg}")
            result.meta = {"status": "error", "message": msg}
            return [result]

        vendor = _active_vendor(input_data)
        fn = _VENDOR_HANDLERS.get((vendor, kind))
        if fn is None:
            msg = (
                f"No customer-data integration registered for vendor={vendor!r} "
                f"kind={kind!r}. Set ECAN_CUSTOMER_DATA_VENDOR or call "
                f"register_vendor_handler() during integrator bootstrap."
            )
            logger.warning(f"[customer_data][{kind}] {msg}")
            result = TextContent(type="text", text=msg)
            result.meta = {"status": "not_configured", "vendor_id": vendor, "kind": kind}
            return [result]

        logger.info(f"[customer_data][{kind}] vendor={vendor!r} input_keys={list(input_data.keys())}")
        payload = await _invoke_handler(fn, input_data)
        if not isinstance(payload, dict):
            payload = {"value": payload}

        text_answer = json.dumps(payload, ensure_ascii=False, default=str)
        result = TextContent(type="text", text=text_answer)
        result.meta = {"status": "success", "vendor_id": vendor, "kind": kind, **payload}
        return [result]
    except Exception as e:
        err_trace = get_traceback(e, f"ErrorCustomerData_{kind}")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def query_price(mainwin, args):
    return await _dispatch("price", args, required=("sku",))


async def query_inventories(mainwin, args):
    return await _dispatch("inventory", args, required=("sku",))


async def query_order(mainwin, args):
    return await _dispatch("order", args, required=("order_id",))


# ---------------------------------------------------------------------------
# Schema registration
# ---------------------------------------------------------------------------

def _common_vendor_field() -> Dict[str, Any]:
    return {
        "type": "string",
        "description": (
            "Optional vendor / integration identifier (e.g. 'shopify', "
            "'woocommerce', 'erp_v2'). Leave empty to use the deployment "
            "default from the ECAN_CUSTOMER_DATA_VENDOR env var."
        ),
    }


def add_query_price_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schemas.append(types.Tool(
        _meta={"run_in_cloud": False},
        name="query_price",
        description=(
            "<category>Customer Service</category><sub-category>Lookup</sub-category>"
            "Look up the current selling price (and optional discount / promo "
            "metadata) for a SKU by delegating to the customer's commerce "
            "platform integration. Use this — NOT rag_query — whenever the "
            "customer asks 'how much', '多少钱', 'price', 'discount', 'sale "
            "price'. Returns structured JSON: "
            "{sku, found, price, currency, original_price?, promo?, ...}."
        ),
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": ["sku"],
                    "properties": {
                        "sku": {
                            "type": "string",
                            "minLength": 1,
                            "description": "Product SKU / item ID to price.",
                        },
                        "customer_id": {
                            "type": "string",
                            "description": (
                                "Optional customer ID — lets the integration "
                                "apply tier-specific or coupon prices."
                            ),
                        },
                        "currency": {
                            "type": "string",
                            "description": "Optional currency override (ISO 4217).",
                        },
                        "vendor_id": _common_vendor_field(),
                    },
                }
            },
        },
    ))


def add_query_inventories_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schemas.append(types.Tool(
        _meta={"run_in_cloud": False},
        name="query_inventories",
        description=(
            "<category>Customer Service</category><sub-category>Lookup</sub-category>"
            "Look up real-time inventory / stock-on-hand for a SKU by "
            "delegating to the customer's commerce platform integration. Use "
            "this — NOT rag_query — whenever the customer asks 'in stock', "
            "'有货吗', '现货', 'available', 'restock'. Returns structured "
            "JSON: {sku, found, on_hand, reserved?, warehouses?, ...}."
        ),
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": ["sku"],
                    "properties": {
                        "sku": {
                            "type": "string",
                            "minLength": 1,
                            "description": "Product SKU / item ID.",
                        },
                        "warehouse_id": {
                            "type": "string",
                            "description": (
                                "Optional warehouse / location filter. Leave "
                                "empty for an aggregated total across all "
                                "warehouses."
                            ),
                        },
                        "vendor_id": _common_vendor_field(),
                    },
                }
            },
        },
    ))


def add_query_order_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schemas.append(types.Tool(
        _meta={"run_in_cloud": False},
        name="query_order",
        description=(
            "<category>Customer Service</category><sub-category>Lookup</sub-category>"
            "Look up an order by its ID and return status / shipping / "
            "tracking metadata by delegating to the customer's commerce "
            "platform integration. Use this — NOT rag_query — whenever the "
            "customer asks about 'my order', '订单', 'tracking number', "
            "'shipping status', 'delivery date', 'refund status'. Returns "
            "structured JSON: {order_id, found, status, total, items, "
            "tracking_number?, carrier?, eta?, ...}."
        ),
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": ["order_id"],
                    "properties": {
                        "order_id": {
                            "type": "string",
                            "minLength": 1,
                            "description": "Order ID provided by the customer.",
                        },
                        "customer_id": {
                            "type": "string",
                            "description": (
                                "Optional customer ID — some integrations "
                                "require it to authorize the lookup."
                            ),
                        },
                        "vendor_id": _common_vendor_field(),
                    },
                }
            },
        },
    ))
