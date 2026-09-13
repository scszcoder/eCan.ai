"""Fleet turn-queue client (Path 1.5 — the counterpart of the Phase 5 seam).

The server side shipped the queue (``ecbAccountManager`` internal actions) and
said plainly that *no worker calls* ``turn_claim``. This module is the worker's
half: register the pod as a vehicle, claim turns it can satisfy, heartbeat what
it holds, and report the outcome with cost.

Four actions, one POST shape (``{action, input}``) against
``<graphql host>/ecbAccountManager``:

===================  =====================================================
``vehicle_register`` upsert this pod into the fleet roster; doubles as the
                     vehicle liveness signal (the server reads
                     ``last_heartbeat``, which only this action refreshes)
``turn_claim``       take one queued turn this pod's capabilities satisfy
``turn_heartbeat``   keep claimed turns from being reaped mid-run
``turn_done``        report ``done`` | ``failed`` | ``dropped`` with cost
===================  =====================================================

Two properties of the server contract that shape this client:

* **Placement is a WHERE clause.** A turn's ``requires[]`` must be a subset of
  the claiming vehicle's ``capabilities[]``. That is the same vocabulary as the
  Phase 0.3 ``requires`` field — the two halves already speak one language, so
  this client does not translate, it forwards.
* **The turn id is the idempotency key, and it belongs to the server.** A
  redelivered turn must not answer a customer twice, so this client never
  invents or regenerates a turn id: it reports against the id it was handed.

Auth is the internal shared credential (``paymentCreditAuthorized``), not a
user token — these actions are worker-to-control-plane, not user-facing.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit

from utils.logger_helper import logger_helper as logger

ENV_ENDPOINT = "ECAN_FLEET_ENDPOINT"
ENV_TOKEN = "ECAN_FLEET_INTERNAL_TOKEN"
ENV_OWNER = "ECAN_TASK_OWNER"
ENV_CAPABILITIES = "ECAN_VEHICLE_CAPABILITIES"
ENV_CAPACITY = "ECAN_VEHICLE_CAPACITY"
ENV_ENVIRONMENT = "ECAN_VEHICLE_ENVIRONMENT"

DEFAULT_TIMEOUT = 30.0


class FleetError(RuntimeError):
    """A fleet action failed."""


class FleetNotConfigured(FleetError):
    """The pod has no fleet endpoint/credential — it cannot join a fleet."""


def account_manager_url(graphql_endpoint: str) -> str:
    """``ecbAccountManager`` sits beside the GraphQL endpoint on the same host.

    Same derivation the desktop uses for its account-manager calls, so one
    configured endpoint keeps serving both.
    """
    gql = (graphql_endpoint or "").strip()
    if not gql:
        return ""
    parts = urlsplit(gql)
    if not parts.scheme or not parts.netloc:
        return ""
    return f"{parts.scheme}://{parts.netloc}/ecbAccountManager"


def _split_capabilities(raw: str) -> List[str]:
    return [c.strip() for c in str(raw or "").replace(";", ",").split(",") if c.strip()]


class FleetClient:
    """Worker-side client for the turn queue and the vehicle roster."""

    def __init__(
        self,
        *,
        endpoint: str,
        token: str,
        owner: str,
        vehicle_id: str,
        capabilities: Optional[List[str]] = None,
        capacity: int = 1,
        environment: str = "production",
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        if not endpoint:
            raise FleetNotConfigured(
                f"No fleet endpoint: set {ENV_ENDPOINT} or a CN GraphQL endpoint"
            )
        if not token:
            raise FleetNotConfigured(
                f"No fleet credential: set {ENV_TOKEN} (the internal shared token)"
            )
        if not vehicle_id:
            raise FleetNotConfigured(
                "No vehicle id: set ECAN_VEHICLE_ID so the scheduler can address this pod"
            )
        self.endpoint = endpoint
        self.token = token
        self.owner = owner
        self.vehicle_id = vehicle_id
        self.capabilities = list(capabilities or [])
        self.capacity = max(1, int(capacity or 1))
        self.environment = environment or "production"
        self.timeout = timeout

    # ------------------------------------------------------------- config

    @classmethod
    def from_env(cls, vehicle_id: str = "", owner: str = "") -> "FleetClient":
        endpoint = (os.getenv(ENV_ENDPOINT) or "").strip()
        if not endpoint:
            gql = (os.getenv("ECAN_CN_GRAPHQL_ENDPOINT") or "").strip()
            if not gql:
                try:
                    from agent.cloud_api.endpoints import get_endpoint_config

                    gql = get_endpoint_config().graphql_endpoint or ""
                except Exception as exc:  # no config on this image — say so plainly
                    raise FleetNotConfigured(f"No GraphQL endpoint configured: {exc}")
            endpoint = account_manager_url(gql)

        if not vehicle_id:
            from agent.ec_agents.vehicle_affinity import resolve_local_vehicle_id

            vehicle_id = resolve_local_vehicle_id()

        try:
            capacity = int(os.getenv(ENV_CAPACITY) or "1")
        except ValueError:
            capacity = 1

        return cls(
            endpoint=endpoint,
            token=(os.getenv(ENV_TOKEN) or "").strip(),
            owner=owner or (os.getenv(ENV_OWNER) or "").strip(),
            vehicle_id=vehicle_id,
            capabilities=_split_capabilities(os.getenv(ENV_CAPABILITIES) or ""),
            capacity=capacity,
            environment=(os.getenv(ENV_ENVIRONMENT) or "production").strip(),
        )

    # ------------------------------------------------------------ transport

    async def _post(self, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        import httpx

        body = {"action": action, "input": payload}
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
        }
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    self.endpoint, json=body, headers=headers, timeout=self.timeout
                )
                text = resp.text
                status = resp.status_code
        except Exception as exc:
            raise FleetError(f"{action} transport error: {exc}") from exc

        try:
            data = json.loads(text or "{}")
        except Exception:
            raise FleetError(f"{action} returned non-JSON (HTTP {status}): {text[:200]}")

        if status == 401:
            # The credential is wrong, not expired: these actions authenticate
            # with a fixed internal token, so retrying cannot help.
            raise FleetNotConfigured(
                f"{action} rejected: the internal fleet credential ({ENV_TOKEN}) is not accepted"
            )
        if status >= 400 or not data.get("success"):
            raise FleetError(
                f"{action} failed (HTTP {status}): "
                f"{data.get('error') or data.get('message') or text[:200]}"
            )
        return data

    # -------------------------------------------------------------- actions

    async def register_vehicle(self, **overrides: Any) -> Dict[str, Any]:
        """Upsert this pod into the fleet roster.

        Also the vehicle liveness signal: the server offlines a cloud vehicle
        whose ``last_heartbeat`` goes stale, and this action is what refreshes
        it — hence ``heartbeat_vehicle`` below is the same call.
        """
        payload: Dict[str, Any] = {
            "vehicle_id": self.vehicle_id,
            "owner": self.owner,
            "name": overrides.pop("name", None) or self.vehicle_id,
            "capabilities": self.capabilities,
            "max_concurrent_tasks": self.capacity,
            "environment": self.environment,
        }
        payload.update({k: v for k, v in overrides.items() if v is not None})
        data = await self._post("vehicle_register", payload)
        return data.get("vehicle") or {}

    async def heartbeat_vehicle(self) -> Dict[str, Any]:
        """Refresh this vehicle's liveness (a re-register; see above)."""
        return await self.register_vehicle()

    async def offline_vehicle(self) -> Dict[str, Any]:
        """Leave the roster on purpose.

        A pod that just dies is discovered by the server's reaper ~6 minutes
        later; until then the placement side still counts it as online capacity.
        Saying so on the way out costs one call and keeps the roster honest.
        """
        data = await self._post("vehicle_offline", {"vehicle_id": self.vehicle_id})
        return data.get("vehicle") or {}

    async def claim_turn(self) -> Optional[Dict[str, Any]]:
        """Claim one turn, or None when the queue has nothing for this pod.

        Nothing to claim is the normal steady state, not an error — the server
        answers ``{turn: null}`` and so does this.
        """
        data = await self._post(
            "turn_claim",
            {"vehicle_id": self.vehicle_id, "capabilities": self.capabilities},
        )
        turn = data.get("turn")
        return turn if isinstance(turn, dict) else None

    async def heartbeat_turns(self, turn_ids: List[str]) -> List[str]:
        """Keep claimed turns alive; returns the ids the server still counts as ours."""
        ids = [str(t) for t in (turn_ids or []) if t]
        if not ids:
            return []
        data = await self._post(
            "turn_heartbeat", {"turn_ids": ids, "vehicle_id": self.vehicle_id}
        )
        alive = data.get("alive")
        return [str(x) for x in alive] if isinstance(alive, list) else []

    async def finish_turn(
        self,
        turn_id: str,
        *,
        status: str = "done",
        result: Optional[Dict[str, Any]] = None,
        error: str = "",
        cost_usd: float = 0.0,
        input_tokens: int = 0,
        output_tokens: int = 0,
        usage_stages: Optional[Dict[str, Any]] = None,
        retry: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Report the outcome, carrying what the turn cost.

        ``retry=False`` on a failure means *do not requeue*: use it for errors a
        second attempt cannot fix (a turn this pod cannot even map to a task),
        so a permanent problem does not burn every attempt and look transient.
        """
        payload: Dict[str, Any] = {
            "turn_id": turn_id,
            "status": status,
            "cost_usd": float(cost_usd or 0.0),
            "input_tokens": int(input_tokens or 0),
            "output_tokens": int(output_tokens or 0),
        }
        if result is not None:
            payload["result"] = result
        if error:
            payload["error"] = str(error)[:2000]
        if usage_stages:
            payload["usage_stages"] = usage_stages
        if retry is not None:
            payload["retry"] = bool(retry)
        data = await self._post("turn_done", payload)
        return data.get("turn") or {}


def fleet_client_or_none(vehicle_id: str = "", owner: str = "") -> Optional[FleetClient]:
    """A configured client, or None with a reason logged.

    Fleet membership is optional: a pod fed by stdin is still a valid pod, so a
    missing endpoint or credential must not be fatal here. It IS fatal in the
    fleet intake, which cannot work without one.
    """
    try:
        return FleetClient.from_env(vehicle_id=vehicle_id, owner=owner)
    except FleetNotConfigured as exc:
        logger.info(f"[fleet] not joining a fleet: {exc}")
        return None
    except Exception as exc:
        logger.warning(f"[fleet] client construction failed (non-fatal): {exc}")
        return None
