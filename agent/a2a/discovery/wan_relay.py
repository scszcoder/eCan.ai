"""
AppSync-backed A2A message relay.

Used by the router when the recipient agent isn't reachable via LAN-direct
HTTP. Publishes an ``A2AMessage`` mutation; the recipient (subscribed via
``onA2AMessage(toAgentId=<self>)``) receives it on its WebSocket and feeds
it into the same A2A handler chain that LAN-direct HTTP would have hit.

Reuses the proven subscription machinery in ``agent.ec_tasks.appsync_pubsub``.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Awaitable, Callable, Dict, Optional

from agent.ec_tasks.appsync_pubsub import (
    AppSyncApiKeyConfig,
    _post_graphql,
    _subscribe,
)
from utils.logger_helper import logger_helper as logger

SEND_TIMEOUT_SEC = 30.0
SUBSCRIBE_MAX_IDLE_SEC = 600        # 10 min — keep WAN inbox connection warm
SUBSCRIBE_MAX_RETRIES = 5


def _gql_send_a2a() -> str:
    return """
    mutation SendA2AMessage($input: A2AMessageInput!) {
      sendA2AMessage(input: $input) {
        id toAgentId fromAgentId org payload timestamp
      }
    }
    """


def _gql_sub_a2a() -> str:
    return """
    subscription OnA2AMessage($toAgentId: String!) {
      onA2AMessage(toAgentId: $toAgentId) {
        id toAgentId fromAgentId org payload timestamp
      }
    }
    """


async def publish_a2a_message(
    *,
    config: AppSyncApiKeyConfig,
    to_agent_id: str,
    from_agent_id: str,
    org: str,
    payload: dict,
) -> Dict[str, Any]:
    """Publish a single A2A message via AppSync mutation.

    ``payload`` is JSON-encoded into the AWSJSON scalar. Caller may pass any
    JSON-serializable dict (the original A2A JSON-RPC envelope, typically).
    """
    safe_payload = json.dumps(payload, ensure_ascii=False, default=str)
    return await _post_graphql(
        config.http_endpoint,
        api_key=config.api_key,
        query=_gql_send_a2a(),
        variables={
            "input": {
                "toAgentId": to_agent_id,
                "fromAgentId": from_agent_id,
                "org": org,
                "payload": safe_payload,
            }
        },
    )


async def subscribe_a2a_inbox(
    *,
    config: AppSyncApiKeyConfig,
    agent_id: str,
    on_message: Callable[[str, dict], Awaitable[None]],
) -> None:
    """Long-running subscription to one agent's WAN inbox.

    Calls ``on_message(to_agent_id, payload_dict)`` for each delivery.
    Returns only on cancellation or unrecoverable error.
    """

    async def on_envelope(envelope: Dict[str, Any]) -> None:
        try:
            data = (envelope.get("payload") or {}).get("data") or {}
            msg = data.get("onA2AMessage") or {}
            if not msg:
                return
            raw = msg.get("payload")
            if isinstance(raw, str):
                try:
                    payload = json.loads(raw)
                except Exception:
                    payload = {"_raw": raw}
            elif isinstance(raw, dict):
                payload = raw
            else:
                payload = {}
            # Annotate so the downstream handler knows where this came from.
            payload.setdefault("_a2a_from", msg.get("fromAgentId"))
            payload.setdefault("_a2a_via", "wan_relay")
            await on_message(msg.get("toAgentId") or agent_id, payload)
        except Exception as e:
            logger.warning(
                f"[discovery.wan_relay] inbox handler error for {agent_id}: {e}"
            )

    await _subscribe(
        config=config,
        query=_gql_sub_a2a(),
        variables={"toAgentId": agent_id},
        operation_name="OnA2AMessage",
        field_name="onA2AMessage",
        on_envelope=on_envelope,
        max_retries=SUBSCRIBE_MAX_RETRIES,
        max_idle_sec=SUBSCRIBE_MAX_IDLE_SEC,
    )


async def send_via_wan(
    *,
    config: AppSyncApiKeyConfig,
    to_agent_id: str,
    from_agent_id: str,
    org: str,
    payload: dict,
    timeout: float = SEND_TIMEOUT_SEC,
) -> bool:
    """One-shot fire-and-forget send. Returns True on success.

    Doesn't wait for the recipient to actually consume the message — only
    that AppSync accepted the mutation. The recipient's subscription does
    the rest. Use this when you want pure pub/sub semantics.
    """
    try:
        await asyncio.wait_for(
            publish_a2a_message(
                config=config,
                to_agent_id=to_agent_id,
                from_agent_id=from_agent_id,
                org=org,
                payload=payload,
            ),
            timeout=timeout,
        )
        return True
    except asyncio.TimeoutError:
        logger.warning(
            f"[discovery.wan_relay] send to {to_agent_id} timed out after {timeout}s"
        )
        return False
    except Exception as e:
        logger.warning(f"[discovery.wan_relay] send to {to_agent_id} failed: {e}")
        return False
