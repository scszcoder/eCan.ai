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

Authentication is the user's own session. ``turn_enqueue`` accepts either that
or the internal shared token under one action name, and under a session it takes
``owner`` from the verified identity rather than the body — so a desktop can
only ever enqueue for itself. That matters more than it looks: a desktop
shipping with the internal token would hand every customer the keys to every
other customer, because that token mints end-user sessions for any owner.
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


def _session_bearer_token() -> str:
    """The signed-in user's bearer for ecbAccountManager.

    ecbAccountManager is a sibling route of ``/api/graphql`` on the same
    gateway, so it verifies the same credential — which on CN is the eCan
    30-day session token (HS256, ``sub=openid``). ``_http_auth_header`` already
    makes that choice for every GraphQL call, and delegating keeps the two from
    drifting: intl still sends the Cognito token raw.

    This used to read ``tokens["AccessToken"]`` first. For a WeChat login that
    is the short-lived CloudBase *access* JWT (``sub=uid``), which the HTTP gate
    cannot verify, so `pod_list`, `fleet_status` and `turn_enqueue` all came
    back 401 — "The session was rejected; sign in again" — while the very same
    session made GraphQL calls successfully with the other token. A WeChat
    access JWT also cannot be refreshed, so it only ever got staler.
    """
    try:
        from app_context import AppContext

        mainwin = AppContext.get_main_window()
        if mainwin is None:
            return ""

        from agent.cloud_api.cloud_api import _http_auth_header

        bearer = _http_auth_header(mainwin.get_auth_token() or "")
        token = bearer[7:] if bearer.lower().startswith("bearer ") else bearer
        if token:
            return token

        # No HTTP bearer yet — e.g. an email/CIAM login before its session
        # token is minted. The access token is the only credential there is.
        auth_manager = getattr(mainwin, "auth_manager", None)
        if auth_manager is not None:
            try:
                tokens = auth_manager.get_tokens() or {}
                return str(tokens.get("AccessToken") or tokens.get("access_token") or "").strip()
            except Exception:
                pass
        return ""
    except Exception:
        return ""


def _credential() -> tuple:
    """``(token, kind)`` for ``turn_enqueue``.

    ``turn_enqueue`` takes either credential under one action name, which is the
    right shape: a client should not have to know which one the server wants.

    * ``session`` — the signed-in user. The server derives ``owner`` from the
      verified identity and ignores whatever the body says, so a desktop can
      enqueue only for itself. This is the desktop's path.
    * ``internal`` — the shared token, only when deliberately configured. A
      desktop must never ship with it: whoever holds it can mint an end-user
      session for *any* owner, which would hand every customer the keys to every
      other customer.
    """
    internal = (os.environ.get(ENV_TOKEN) or "").strip()
    if internal:
        return internal, "internal"

    session = _session_bearer_token()
    if session:
        return session, "session"

    raise TurnQueueNotConfigured(
        "turn_enqueue needs a signed-in session. No CloudBase access token or "
        "eCan session token is available on this client."
    )


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
    owner: str = "",
    trigger_type: str = "",
    conversation_id: str = "",
    agent: Any = None,
    input_text: str = "",
) -> Dict[str, Any]:
    """The turn this task becomes.

    ``task_id`` is a field on the turn, not something smuggled inside the input
    text: the server resolves and stores the task at enqueue time, so a retry
    cannot be handed to a different task if the agent's assignment changed in
    between. ``input`` is therefore just what the customer said.

    A turn with no conversation is legal and is what a scheduled task produces —
    but it must name a task or an agent, or the server refuses it rather than
    queueing work nothing can resolve. Naming the task is what this does.

    ``owner`` is carried for the internal-credential path only. Under a user
    session the server takes the owner from the verified identity and ignores
    the body, which is what stops a client enqueuing for somebody else.
    """
    from agent.placement import placement_of

    task_id = str(getattr(task, "id", "") or "")
    if not task_id:
        raise TurnQueueError("cannot enqueue a task with no id")

    place = placement_of(task)
    agent_id = str(getattr(task, "agent_id", "") or "")

    payload: Dict[str, Any] = {
        "task_id": task_id,
        "agent_id": agent_id,
        "requires": turn_requires(task, agent),
        "lifetime": place["lifetime"],
        "residency": place["residency"],
        "input": input_text or "",
        "trigger": trigger_type or "",
    }
    if owner:
        payload["owner"] = owner
    if conversation_id:
        payload["conversation_id"] = conversation_id
    return payload


def enqueue_task_turn(
    task: Any,
    *,
    owner: str = "",
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
    token, kind = _credential()

    if kind == "internal" and not owner:
        # The internal path reads owner from the body, so an unknown owner
        # would enqueue a turn belonging to nobody.
        raise TurnQueueError(
            f"cannot enqueue task {getattr(task, 'id', '?')} with no owner "
            f"(the internal credential takes the owner from the request body)"
        )

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
            f"turn_enqueue rejected this client's {kind} credential (HTTP 401): "
            f"{data.get('message') or 'unauthorized'}. A session credential that "
            f"is merely expired will work again after signing in."
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
        f"created={created} auth={kind} requires={payload['requires']} "
        f"lifetime={payload['lifetime']}"
    )
    return {"turn_id": turn.get("id"), "created": created, "turn": turn}
