"""Enqueueing a turn — the desktop's half of unified execution (C4).

Today a cloud task leaves this machine by HMAC-POSTing a launcher, which starts
a one-shot Job. Under unified execution everything becomes a turn on one queue
and the launcher becomes a scaler: the desktop stops dispatching and starts
*producing*.

**One path per task, never two.** A task that is both launcher-dispatched and
queued executes twice, from two processes, answering the same customer from two
places. Nothing upstream prevents that, so this module is built so it cannot
happen from here:

* the choice is a single per-task field (``metadata.execution_path``), not a
  pair of booleans that can both be true;
* a failed enqueue returns an error and **never falls back to the launcher** —
  a fallback is exactly the window where both paths are live;
* if the queue path is switched off on this client while a task is marked for
  the queue, that task refuses to run rather than quietly taking the old path,
  because the server-side scheduler may already have been flipped for it.

Placement travels with the turn: ``requires[]`` is matched against a pod's
capabilities as a WHERE clause, and ``lifetime`` tells the scheduler whether a
cold pod will do. This is what makes the Phase 0.3 declarations load-bearing.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit

from utils.logger_helper import logger_helper as logger

ENV_ENABLED = "ECAN_UNIFIED_TURN_QUEUE"
ENV_TOKEN = "ECAN_FLEET_INTERNAL_TOKEN"
ENV_ENDPOINT = "ECAN_FLEET_ENDPOINT"

EXECUTION_PATH_KEY = "execution_path"
PATH_QUEUE = "queue"
PATH_LAUNCHER = "launcher"

_TRUTHY = ("1", "true", "yes", "on")


class TurnQueueError(RuntimeError):
    """An enqueue failed. Never retried down the other path."""


class TurnQueueNotConfigured(TurnQueueError):
    """This client cannot reach the queue at all."""


def queue_enabled() -> bool:
    """Whether this client may use the queue path.

    Default OFF: the flip is per task and coordinated with the server-side
    scheduler, so a client that has merely been updated must not start
    enqueuing on its own.
    """
    return (os.environ.get(ENV_ENABLED) or "").strip().lower() in _TRUTHY


def task_execution_path(task: Any) -> str:
    """Which path this task is on. One field, so it cannot be on both."""
    try:
        metadata = getattr(task, "metadata", None)
        if isinstance(metadata, dict):
            value = str(metadata.get(EXECUTION_PATH_KEY) or "").strip().lower()
            if value in (PATH_QUEUE, PATH_LAUNCHER):
                return value
    except Exception:
        pass
    return PATH_LAUNCHER


def task_uses_queue(task: Any) -> bool:
    return task_execution_path(task) == PATH_QUEUE


def _account_manager_url() -> str:
    endpoint = (os.environ.get(ENV_ENDPOINT) or "").strip()
    if endpoint:
        return endpoint
    try:
        from agent.cloud_api.endpoints import get_endpoint_config

        gql = (get_endpoint_config().graphql_endpoint or "").strip()
    except Exception as exc:
        raise TurnQueueNotConfigured(f"No GraphQL endpoint configured: {exc}")
    if not gql:
        raise TurnQueueNotConfigured("No GraphQL endpoint configured")
    parts = urlsplit(gql)
    if not parts.scheme or not parts.netloc:
        raise TurnQueueNotConfigured(f"GraphQL endpoint is not a URL: {gql}")
    return f"{parts.scheme}://{parts.netloc}/ecbAccountManager"


def _credential() -> str:
    """The credential ``turn_enqueue`` accepts today.

    It is the internal shared token, which a desktop install does not have and
    should not be given — whoever holds it can mint an end-user session for any
    owner. Until the server accepts an owner-authenticated enqueue (server S7),
    this path only works where that token is deliberately present, and says so
    plainly rather than failing with a 401 nobody can interpret.
    """
    token = (os.environ.get(ENV_TOKEN) or "").strip()
    if not token:
        raise TurnQueueNotConfigured(
            f"turn_enqueue needs a credential the desktop does not hold. Set "
            f"{ENV_TOKEN} for a trusted client, or wait for the server to accept "
            f"an owner-authenticated enqueue."
        )
    return token


def turn_requires(task: Any, agent: Any = None) -> List[str]:
    """What a pod must advertise to run this task.

    The task's own ``requires``, plus the dedication capability when the agent
    has one: dedication is expressed as a requirement on the work, never as a
    binding on the agent, so it stays a scheduling decision.
    """
    from agent.placement import dedicated_capability, normalize_requires

    requires = list(normalize_requires(getattr(task, "requires", None)))

    dedicated_to = ""
    try:
        if agent is not None:
            dedicated_to = str(getattr(agent, "dedicated_vehicle_id", "") or "")
    except Exception:
        dedicated_to = ""

    if dedicated_to:
        agent_id = str(getattr(agent, "id", "") or getattr(agent, "agent_id", "") or "")
        if agent_id:
            cap = dedicated_capability(agent_id)
            if cap not in requires:
                requires.append(cap)

    return requires


def build_enqueue_payload(
    task: Any,
    *,
    owner: str,
    trigger_type: str = "",
    conversation_id: str = "",
    agent: Any = None,
    input_text: str = "",
) -> Dict[str, Any]:
    """The turn this task becomes.

    ``input`` carries the task id as structured JSON because a turn row names an
    owner, a conversation and an agent but never a task — the worker resolves
    its work from this until the server carries the task itself (server S0).
    """
    from agent.placement import placement_of

    task_id = str(getattr(task, "id", "") or "")
    if not task_id:
        raise TurnQueueError("cannot enqueue a task with no id")
    if not owner:
        raise TurnQueueError(f"cannot enqueue task {task_id} with no owner")

    place = placement_of(task)
    agent_id = str(getattr(task, "agent_id", "") or "")

    payload: Dict[str, Any] = {
        "owner": owner,
        "agent_id": agent_id,
        "requires": turn_requires(task, agent),
        "lifetime": place["lifetime"],
        "residency": place["residency"],
        "input": json.dumps({
            "task_id": task_id,
            "text": input_text or "",
            "trigger": trigger_type or "",
        }, ensure_ascii=False),
    }
    if conversation_id:
        payload["conversation_id"] = conversation_id
    return payload


def enqueue_task_turn(
    task: Any,
    *,
    owner: str,
    trigger_type: str = "",
    conversation_id: str = "",
    agent: Any = None,
    input_text: str = "",
    timeout: float = 30.0,
) -> Dict[str, Any]:
    """Enqueue this task as a turn. Raises rather than returning a half-answer.

    The caller must NOT fall back to the launcher on failure: the server may
    already consider this task queued, and running it both ways answers one
    customer twice.
    """
    import requests

    url = _account_manager_url()
    token = _credential()
    payload = build_enqueue_payload(
        task, owner=owner, trigger_type=trigger_type,
        conversation_id=conversation_id, agent=agent, input_text=input_text,
    )

    try:
        resp = requests.post(
            url,
            json={"action": "turn_enqueue", "input": payload},
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {token}"},
            timeout=timeout,
        )
        status = resp.status_code
        text = resp.text
    except Exception as exc:
        raise TurnQueueError(f"turn_enqueue transport error: {exc}") from exc

    try:
        data = json.loads(text or "{}")
    except Exception:
        raise TurnQueueError(f"turn_enqueue returned non-JSON (HTTP {status}): {text[:200]}")

    if status == 401:
        raise TurnQueueNotConfigured(
            "turn_enqueue rejected this client's credential (HTTP 401). The "
            "desktop cannot authenticate to the queue until the server accepts "
            "an owner-authenticated enqueue."
        )
    if status >= 400 or not data.get("success"):
        raise TurnQueueError(
            f"turn_enqueue failed (HTTP {status}): "
            f"{data.get('error') or data.get('message') or text[:200]}"
        )

    turn = data.get("turn") or {}
    created = data.get("created")
    logger.info(
        f"[TurnQueue] task={getattr(task, 'id', '?')} enqueued as turn={turn.get('id')} "
        f"created={created} requires={payload['requires']} lifetime={payload['lifetime']}"
    )
    return {"turn_id": turn.get("id"), "created": created, "turn": turn}
