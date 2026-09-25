"""Fleet transfers: the client half of the cloud control plane.

The cloud only records who asked for what and hands out short-lived storage
links; see docs/FLEET_TRANSFER_SERVER_CONTRACT.md. What travels is an opaque
blob sealed end to end by ``agent.fleet.seal`` -- this module never opens,
builds or names its contents, and must not learn to: it lives in a cloud-bound
directory (tests/unit/test_browser_profile_stays_local.py).

Same route, bearer and error types as ``store_api``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import requests

from agent.cloud_api.store_api import StoreApiError, StoreApiUnavailable, _call

KINDS = ("logs", "profile")
FINISHED = ("done", "failed", "expired")

__all__ = ["StoreApiError", "StoreApiUnavailable", "create", "list_for", "get", "update",
           "upload_url", "download_url", "finish", "normalize", "put_blob", "get_blob"]

_FIELDS = {
    "transferId": "transfer_id", "sourceVehicleId": "source_vehicle_id",
    "receiverVehicleId": "receiver_vehicle_id", "requesterVehicleId": "requester_vehicle_id",
    "objectKey": "object_key", "createdAt": "created_at", "updatedAt": "updated_at",
    "expiresAt": "expires_at",
}


def normalize(row: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """One transfer row, snake_case whatever spelling the server used."""
    out: Dict[str, Any] = {}
    for k, v in (row or {}).items():
        out[_FIELDS.get(k, k)] = v
    for k in ("params", "receiver"):
        if not isinstance(out.get(k), dict):
            out[k] = {}
    return out


def create(kind: str, source_vehicle_id: str, receiver_vehicle_id: str,
           requester_vehicle_id: str, params: Dict[str, Any],
           receiver: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    if not source_vehicle_id or not receiver_vehicle_id or source_vehicle_id == receiver_vehicle_id:
        raise ValueError("a transfer needs two different machines")
    payload: Dict[str, Any] = {"kind": kind, "source_vehicle_id": source_vehicle_id,
                               "receiver_vehicle_id": receiver_vehicle_id,
                               "requester_vehicle_id": requester_vehicle_id, "params": params}
    if receiver:
        payload["receiver"] = receiver
    return normalize(_call("transfer_create", payload).get("transfer"))


def list_for(vehicle_id: str, include_finished: bool = False) -> List[Dict[str, Any]]:
    data = _call("transfer_list", {"vehicle_id": vehicle_id, "include_finished": include_finished})
    return [normalize(r) for r in (data.get("transfers") or [])]


def get(transfer_id: str) -> Dict[str, Any]:
    return normalize(_call("transfer_get", {"transfer_id": transfer_id}).get("transfer"))


def update(transfer_id: str, **fields: Any) -> Dict[str, Any]:
    allowed = {k: v for k, v in fields.items()
               if k in ("status", "receiver", "route", "size", "sha256", "error") and v is not None}
    return normalize(_call("transfer_update", {"transfer_id": transfer_id, **allowed}).get("transfer"))


def upload_url(transfer_id: str) -> str:
    return str(_call("transfer_upload_url", {"transfer_id": transfer_id}).get("url") or "")


def download_url(transfer_id: str) -> str:
    return str(_call("transfer_download_url", {"transfer_id": transfer_id}).get("url") or "")


def finish(transfer_id: str, status: str, error: str = "") -> Dict[str, Any]:
    payload: Dict[str, Any] = {"transfer_id": transfer_id, "status": status}
    if error:
        payload["error"] = error[:1000]
    return normalize(_call("transfer_finish", payload).get("transfer"))


def put_blob(url: str, path: str, timeout: float = 600.0) -> None:
    """Upload a sealed file to a presigned PUT link."""
    with open(path, "rb") as f:
        resp = requests.put(url, data=f, timeout=timeout,
                            headers={"Content-Type": "application/octet-stream"})
    if resp.status_code >= 300:
        raise StoreApiError(f"upload failed (HTTP {resp.status_code}): {resp.text[:200]}")


def get_blob(url: str, path: str, timeout: float = 600.0) -> None:
    """Download a sealed file from a presigned GET link."""
    with requests.get(url, stream=True, timeout=timeout) as resp:
        if resp.status_code >= 300:
            raise StoreApiError(f"download failed (HTTP {resp.status_code})")
        with open(path, "wb") as f:
            for chunk in resp.iter_content(1024 * 1024):
                f.write(chunk)
