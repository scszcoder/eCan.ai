"""How any rule value is resolved (spec B9.3): the highest layer that has it wins.

    1 immutable_core       packs/core.json + the owner's own core records (budget caps)
    2 user_instruction     confirmed instructions from chat ("never bid on X", "ROAS 3 for store A")
    3 learning_store       validated learnings for this store (or SKU)
    4 learning_category    validated learnings for this category
    5 learning_platform    validated learnings for this platform
    6/7 pack_prior         the platform packs' shipped defaults ([SRC] corpus / [INF] industry)

``resolve`` returns ``{"value", "layer", "provenance_id"}`` so every decision can say which
learning, instruction or prior produced it. Agents can never write layer 1 (``put_record``
refuses the core collections).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent.ec_skills.ecom.store import Store

PACK_DIR = Path(__file__).parent / "packs"
CORE_COLLECTIONS = ("core", "approval_policy", "delegation_grant")
_MISSING = object()


@lru_cache(maxsize=None)
def load_pack(pack_file: str) -> Dict[str, Any]:
    return json.loads((PACK_DIR / f"{pack_file}.json").read_text(encoding="utf-8"))


def packs() -> List[str]:
    return sorted(p.stem for p in PACK_DIR.glob("*.json"))


def _pack_value(key: str):
    """(value, pack_id, layer) from the shipped packs, core first."""
    for name in ["core", *[p for p in packs() if p != "core"]]:
        pack = load_pack(name)
        values = pack.get("values") or {}
        if key in values:
            return values[key], f"{pack['pack_id']}@{pack['version']}", pack.get("layer", "pack_prior")
    return _MISSING, "", ""


def _scope_matches(rec_scope: Dict[str, Any], scope: Dict[str, Any]) -> bool:
    """Every field the record names must equal the caller's; an empty record scope is global."""
    return all(scope.get(k) == v for k, v in (rec_scope or {}).items() if v not in (None, ""))


def _learning_layer(rec_scope: Dict[str, Any]) -> Optional[str]:
    if rec_scope.get("store_id") or rec_scope.get("sku"):
        return "learning_store"
    if rec_scope.get("category"):
        return "learning_category"
    if rec_scope.get("platform"):
        return "learning_platform"
    return None


_LEARNING_ORDER = ("learning_store", "learning_category", "learning_platform")


def resolve(key: str, scope: Optional[Dict[str, Any]] = None, store: Optional[Store] = None,
            default: Any = None) -> Dict[str, Any]:
    scope = scope or {}
    pack_value, pack_id, pack_layer = _pack_value(key)
    if pack_layer == "immutable_core":
        return {"value": pack_value, "layer": "immutable_core", "provenance_id": pack_id}
    if store is not None:
        for rec in store.kb_list("core"):
            v = rec["value"]
            if v.get("kb_key") == key and _scope_matches(v.get("scope") or {}, scope):
                return {"value": v.get("value"), "layer": "immutable_core", "provenance_id": f"core:{rec['key']}"}
        for rec in store.kb_list("user_instruction"):
            v = rec["value"]
            if (v.get("status") == "confirmed" and v.get("kb_key") == key
                    and _scope_matches(v.get("scope") or {}, scope)):
                return {"value": v.get("value"), "layer": "user_instruction", "provenance_id": rec["key"]}
        found: Dict[str, Dict[str, Any]] = {}
        for rec in store.kb_list("learning"):
            v = rec["value"]
            applies = v.get("applies_to") or {}
            if v.get("status") != "validated" or applies.get("kb_key") != key:
                continue
            rec_scope = v.get("scope") or {}
            layer = _learning_layer(rec_scope)
            if layer and _scope_matches(rec_scope, scope) and layer not in found:
                found[layer] = {"value": applies.get("value"), "layer": layer, "provenance_id": rec["key"]}
        for layer in _LEARNING_ORDER:
            if layer in found:
                return found[layer]
    if pack_value is not _MISSING:
        return {"value": pack_value, "layer": "pack_prior", "provenance_id": pack_id}
    return {"value": default, "layer": "missing", "provenance_id": ""}


def value(key: str, scope: Optional[Dict[str, Any]] = None, store: Optional[Store] = None, default: Any = None):
    return resolve(key, scope, store, default)["value"]


def thresholds(prefix: str, scope: Optional[Dict[str, Any]] = None, store: Optional[Store] = None
               ) -> Dict[str, Dict[str, Any]]:
    """Every key under ``prefix`` (e.g. ``thresholds.gads``), resolved: {short_name: resolve()}."""
    keys = set()
    for name in packs():
        keys.update(k for k in (load_pack(name).get("values") or {}) if k.startswith(prefix + "."))
    return {k[len(prefix) + 1:]: resolve(k, scope, store) for k in sorted(keys)}


def put_record(store: Store, collection: str, key: str, value_: Any, source: str = "agent") -> int:
    """Write a KB record on an agent's behalf. The immutable core is the owner's alone."""
    if collection in CORE_COLLECTIONS and source != "owner":
        raise PermissionError(f"{collection} records are changed only by the owner")
    return store.kb_put(collection, key, value_, source)
