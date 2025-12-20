"""
Inventory handlers: Warehouses and Products
Provides simple in-memory CRUD over IPC for demo/testing.
"""
from typing import Any, Optional, Dict, List
from gui.ipc.types import IPCRequest, IPCResponse, create_success_response, create_error_response
from gui.ipc.registry import IPCHandlerRegistry
from utils.logger_helper import logger_helper as logger

# In-memory stores (process lifetime only)
WAREHOUSES: List[Dict[str, Any]] = [
    {
        "id": "wh-1001",
        "name": "West Coast Hub",
        "city": "San Francisco",
        "state": "CA",
        "contactFirstName": "Alex",
        "contactLastName": "Chen",
        "phone": "415-555-1234",
        "email": "alex@example.com",
        "messagingPlatform": "Slack",
        "messagingId": "@alex",
        "address1": "1 Market St",
        "address2": "Suite 300",
        "addressCity": "San Francisco",
        "addressState": "CA",
        "addressZip": "94105",
        "costDescription": "Inbound: $0.15/unit\nStorage: $12/pallet/month\nOutbound: $0.25/unit",
    },
    {
        "id": "wh-2002",
        "name": "East Fulfillment",
        "city": "New York",
        "state": "NY",
        "contactFirstName": "Riley",
        "contactLastName": "Park",
        "phone": "212-555-8899",
        "email": "riley@example.com",
        "messagingPlatform": "Teams",
        "messagingId": "riley.park",
        "address1": "200 Madison Ave",
        "address2": "",
        "addressCity": "New York",
        "addressState": "NY",
        "addressZip": "10016",
        "costDescription": "Storage tiered by volume. Handling fee per order.",
    },
]

PRODUCTS: List[Dict[str, Any]] = [
    {
        "id": "p-1001",
        "nickName": "Travel Mug",
        "title": "Insulated Stainless Steel Mug 12oz",
        "features": "Double wall insulation\nLeak-proof lid",
        "sizeL": "3",
        "sizeW": "3",
        "sizeH": "5",
        "weightOz": "9",
        "fragile": False,
        "batteryInside": False,
        "chemical": False,
        "flammable": False,
        "city": "San Francisco",
        "state": "CA",
        "inventories": [{"location": "west", "quantity": "120"}],
        "dropShippers": [{"name": "ShipBob", "quantity": "50"}],
        "media": [],
        "suppliers": [{"name": "Acme Factory", "link": "", "factoryUnitPrice": "4.20"}],
        "platforms": [{"name": "Amazon", "link": "", "id": "B0-123"}],
    },
    {
        "id": "p-1002",
        "nickName": "LED Desk Lamp",
        "title": "Adjustable LED Desk Lamp",
        "features": "3 brightness levels\nUSB power",
        "sizeL": "10",
        "sizeW": "6",
        "sizeH": "18",
        "weightOz": "23",
        "fragile": True,
        "batteryInside": False,
        "chemical": False,
        "flammable": False,
        "city": "New York",
        "state": "NY",
        "inventories": [{"location": "east", "quantity": "80"}],
        "dropShippers": [],
        "media": [],
        "suppliers": [],
        "platforms": [],
    },
]

# ===== Warehouses =====
@IPCHandlerRegistry.handler('get_warehouses')
def handle_get_warehouses(request: IPCRequest, params: Optional[dict]) -> IPCResponse:
    try:
        return create_success_response(request, {"warehouses": WAREHOUSES})
    except Exception as e:
        logger.error(f"[inventory] get_warehouses error: {e}")
        return create_error_response(request, 'GET_WAREHOUSES_ERROR', str(e))

@IPCHandlerRegistry.handler('save_warehouse')
def handle_save_warehouse(request: IPCRequest, params: Optional[dict]) -> IPCResponse:
    try:
        warehouse = (params or {}).get('warehouse')
        if not warehouse or not isinstance(warehouse, dict) or not warehouse.get('id'):
            return create_error_response(request, 'INVALID_PARAMS', 'warehouse with id is required')
        wid = warehouse['id']
        idx = next((i for i, w in enumerate(WAREHOUSES) if w.get('id') == wid), None)
        if idx is None:
            WAREHOUSES.insert(0, warehouse)
        else:
            WAREHOUSES[idx] = warehouse
        return create_success_response(request, {"warehouse": warehouse})
    except Exception as e:
        logger.error(f"[inventory] save_warehouse error: {e}")
        return create_error_response(request, 'SAVE_WAREHOUSE_ERROR', str(e))

@IPCHandlerRegistry.handler('delete_warehouse')
def handle_delete_warehouse(request: IPCRequest, params: Optional[dict]) -> IPCResponse:
    try:
        wid = (params or {}).get('id')
        if not wid:
            return create_error_response(request, 'INVALID_PARAMS', 'id is required')
        before = len(WAREHOUSES)
        WAREHOUSES[:] = [w for w in WAREHOUSES if w.get('id') != wid]
        deleted = len(WAREHOUSES) != before
        return create_success_response(request, {"deleted": deleted})
    except Exception as e:
        logger.error(f"[inventory] delete_warehouse error: {e}")
        return create_error_response(request, 'DELETE_WAREHOUSE_ERROR', str(e))

# ===== Products =====
@IPCHandlerRegistry.handler('get_products')
def handle_get_products(request: IPCRequest, params: Optional[dict]) -> IPCResponse:
    try:
        return create_success_response(request, {"products": PRODUCTS})
    except Exception as e:
        logger.error(f"[inventory] get_products error: {e}")
        return create_error_response(request, 'GET_PRODUCTS_ERROR', str(e))

@IPCHandlerRegistry.handler('save_product')
def handle_save_product(request: IPCRequest, params: Optional[dict]) -> IPCResponse:
    try:
        product = (params or {}).get('product')
        if not product or not isinstance(product, dict) or not product.get('id'):
            return create_error_response(request, 'INVALID_PARAMS', 'product with id is required')
        pid = product['id']
        idx = next((i for i, p in enumerate(PRODUCTS) if p.get('id') == pid), None)
        if idx is None:
            PRODUCTS.insert(0, product)
        else:
            PRODUCTS[idx] = product
        return create_success_response(request, {"product": product})
    except Exception as e:
        logger.error(f"[inventory] save_product error: {e}")
        return create_error_response(request, 'SAVE_PRODUCT_ERROR', str(e))

@IPCHandlerRegistry.handler('delete_product')
def handle_delete_product(request: IPCRequest, params: Optional[dict]) -> IPCResponse:
    try:
        pid = (params or {}).get('id')
        if not pid:
            return create_error_response(request, 'INVALID_PARAMS', 'id is required')
        before = len(PRODUCTS)
        PRODUCTS[:] = [p for p in PRODUCTS if p.get('id') != pid]
        deleted = len(PRODUCTS) != before
        return create_success_response(request, {"deleted": deleted})
    except Exception as e:
        logger.error(f"[inventory] delete_product error: {e}")
        return create_error_response(request, 'DELETE_PRODUCT_ERROR', str(e))
