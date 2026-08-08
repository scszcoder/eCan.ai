import asyncio
import base64
import json
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Optional
from uuid import uuid4

import aiohttp
import certifi
import httpx

from utils.logger_helper import logger_helper as logger


@dataclass(frozen=True)
class AppSyncApiKeyConfig:
    http_endpoint: str
    api_key: str
    auth_token: Optional[str] = None
    ws_endpoint: Optional[str] = None
    host: Optional[str] = None

    def resolved_ws_endpoint(self) -> str:
        ws = (self.ws_endpoint or "").strip()
        if ws:
            return ws
        http = (self.http_endpoint or "").strip()
        if http.startswith("https://") and "appsync-api" in http:
            rest = http[len("https://") :]
            rest = rest.replace("appsync-api", "appsync-realtime-api", 1)
            return "wss://" + rest
        return http

    def resolved_host(self) -> str:
        if self.host:
            return self.host
        endpoint = (self.http_endpoint or "").strip() or (self.ws_endpoint or "").strip()
        if not endpoint:
            return ""
        from urllib.parse import urlparse

        parsed = urlparse(endpoint)
        host = parsed.netloc
        if "appsync-realtime-api" in host:
            host = host.replace("appsync-realtime-api", "appsync-api")
        return host


def _mk_http_headers(api_key: str) -> Dict[str, str]:
    return {
        "Content-Type": "application/json",
        "cache-control": "no-cache",
        "x-api-key": api_key,
    }


def _build_auth_headers(auth_token: Optional[str], api_key: str) -> Dict[str, str]:
    tok = (auth_token or "").strip()
    if tok:
        if tok.lower().startswith("bearer "):
            return {"Authorization": tok}
        if tok.count(".") >= 2:
            return {"Authorization": tok}
    return {"x-api-key": api_key}


def _mk_ws_headers(host: str, api_key: str, auth_token: Optional[str]) -> Dict[str, str]:
    headers = _build_auth_headers(auth_token, api_key)
    headers["host"] = host
    return headers


def _mk_ws_url(ws_endpoint: str, *, host: str, api_key: str, auth_token: Optional[str]) -> str:
    headers = _mk_ws_headers(host, api_key, auth_token)
    header_b64 = base64.b64encode(json.dumps(headers).encode("utf-8")).decode("utf-8")
    return f"{ws_endpoint}?header={header_b64}&payload=e30="


def _graphql_publish_task_status() -> str:
    return """
    mutation PublishTaskStatus($input: TaskStatusInput!) {
      publishTaskStatus(input: $input) {
        id
        runID
        runner
        error
        success
        status
        timestamp
      }
    }
    """


def _graphql_on_task_status() -> str:
    return """
    subscription OnTaskStatus($runner: String!) {
      onTaskStatus(runner: $runner) {
        id
        runID
        runner
        error
        success
        status
        timestamp
      }
    }
    """


def _graphql_run_cloud_tasks_direct() -> str:
    return """
    mutation RunCloudTasks($input: [CloudTaskInput]!) {
      runCloudTasks(input: $input)
    }
    """


def _graphql_run_cloud_tasks_cloudtaskinput() -> str:
        return """
        mutation RunCloudTasks($input: [CloudTaskInput]!) {
            runCloudTasks(input: $input)
        }
        """


def _graphql_run_cloud_tasks_input() -> str:
    return """
    mutation RunCloudTasks($input: [CloudTaskInput]!) {
      runCloudTasks(input: $input)
    }
    """


def _graphql_publish_skill_editor_stream_event() -> str:
    return """
    mutation PublishSkillEditorStreamEvent($input: SkillEditorStreamEventInput!) {
      publishSkillEditorStreamEvent(input: $input) {
        eventId
        owner
        sessionId
        flowgramId
        eventType
        payload
        timestamp
      }
    }
    """


def _maybe_parse_awsjson(v: Any) -> Any:
    if isinstance(v, str):
        try:
            return json.loads(v)
        except Exception:
            return v
    return v


async def _post_graphql(
    http_endpoint: str,
    *,
    api_key: str,
    query: str,
    variables: Dict[str, Any],
    auth_token: Optional[str] = None,
) -> Dict[str, Any]:
    headers = {"Content-Type": "application/json", "cache-control": "no-cache"}
    headers.update(_build_auth_headers(auth_token, api_key))
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            http_endpoint,
            json={"query": query, "variables": variables},
            headers=headers,
            timeout=30.0,
        )
        resp.raise_for_status()
        payload = resp.json()
        if isinstance(payload, dict) and payload.get("errors"):
            raise RuntimeError(payload.get("errors"))
        return payload


async def publish_task_status(
    *,
    config: AppSyncApiKeyConfig,
    runner: str,
    success: bool,
    run_id: Optional[str] = None,
    status: Any = None,
    error: Optional[str] = None,
) -> Dict[str, Any]:
    return await _post_graphql(
        config.http_endpoint,
        api_key=config.api_key,
        auth_token=config.auth_token,
        query=_graphql_publish_task_status(),
        variables={
            "input": {
                "runID": run_id,
                "runner": runner,
                "error": error,
                "success": bool(success),
                "status": status,
            }
        },
    )


async def publish_skill_editor_stream_event(
    *,
    config: AppSyncApiKeyConfig,
    owner: str,
    session_id: str,
    event_type: str,
    payload: Any = None,
    flowgram_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Publish a Skill Editor realtime event.

    Event types are intended to mirror the existing desktop IPC push methods:
      - skill_editor.chat.stream_chunk
      - skill_editor.chat.stream_end
      - skill_editor.chat.error
      - skill_editor.event

    Note: AppSync's AWSJSON scalar is typically represented as a JSON-encoded string.
    This helper JSON-encodes dict/list payloads for maximal compatibility.
    """

    safe_payload = payload
    if isinstance(payload, (dict, list)):
        safe_payload = json.dumps(payload, ensure_ascii=False)

    return await _post_graphql(
        config.http_endpoint,
        api_key=config.api_key,
        auth_token=config.auth_token,
        query=_graphql_publish_skill_editor_stream_event(),
        variables={
            "input": {
                "owner": owner,
                "sessionId": session_id,
                "flowgramId": flowgram_id,
                "eventType": event_type,
                "payload": safe_payload,
            }
        },
    )


async def run_cloud_tasks(
    *,
    config: AppSyncApiKeyConfig,
    task_ids: list[str],
    agent_id: str = None,
    task_name: str = None,
    options: dict = None,
) -> Dict[str, str]:
    """Run tasks in cloud and return mapping task_id -> run_id.

    Schema:
        input CloudTaskInput { agent_id: String, task_id: String, task_name: String, options: AWSJSON! }
        runCloudTasks(input: [CloudTaskInput]!): AWSJSON!
    """
    if not task_ids:
        return {}

    # Build CloudTaskInput list
    cloud_task_inputs = []
    for tid in task_ids:
        entry: dict = {"task_id": tid, "options": json.dumps(options or {})}
        if agent_id:
            entry["agent_id"] = agent_id
        if task_name:
            entry["task_name"] = task_name
        cloud_task_inputs.append(entry)

    last_exc: Optional[Exception] = None

    cloudtask_input = [{"task_id": str(tid), "options": {}} for tid in task_ids]

    for query, variables in (
        (_graphql_run_cloud_tasks_cloudtaskinput(), {"input": cloudtask_input}),
        (_graphql_run_cloud_tasks_direct(), {"taskIds": task_ids}),
        (_graphql_run_cloud_tasks_input(), {"input": {"taskIds": task_ids}}),
    ):
        try:
            resp = await _post_graphql(config.http_endpoint, api_key=config.api_key, query=query, variables=variables)
            data = (resp or {}).get("data") or {}
            raw = data.get("runCloudTasks")
            payload = _maybe_parse_awsjson(raw)

            if isinstance(payload, dict) and "items" in payload:
                payload = payload.get("items")

            mapping: Dict[str, str] = {}
            if isinstance(payload, list):
                for item in payload:
                    if not isinstance(item, dict):
                        continue
                    task_id = item.get("taskId") or item.get("taskID") or item.get("id")
                    run_id = item.get("runId") or item.get("runID") or item.get("run_id")
                    if task_id and run_id:
                        mapping[str(task_id)] = str(run_id)
            elif isinstance(payload, dict):
                # Sometimes backend returns {taskId: runId, ...}
                for k, v in payload.items():
                    if k and v:
                        mapping[str(k)] = str(v)

            if mapping:
                return mapping

            raise RuntimeError(f"runCloudTasks returned unexpected payload: {type(payload).__name__}")
        except Exception as e:
            last_exc = e
            continue

    raise RuntimeError(f"runCloudTasks failed: {last_exc}")


async def _subscribe(
    *,
    config: AppSyncApiKeyConfig,
    query: str,
    variables: Dict[str, Any],
    operation_name: str,
    field_name: str,
    on_envelope: Callable[[Dict[str, Any]], Awaitable[None]],
    max_retries: int,
    max_idle_sec: int = 300,
) -> None:
    """Subscribe to an AppSync GraphQL subscription with graceful cancellation support.
    
    Args:
        max_idle_sec: Max seconds to stay connected without receiving messages.
                      Set to 300 (5 min) to prevent orphaned connections.
                      The outer caller (runner) manages subscription lifetime via
                      asyncio cancellation; this limit acts as a hard safety net.
    """
    ws_endpoint = config.resolved_ws_endpoint()
    host = config.resolved_host()
    ws_url = _mk_ws_url(ws_endpoint, host=host, api_key=config.api_key, auth_token=config.auth_token)

    retry = 0
    base_backoff = 3
    last_msg_time = time.time()

    while True:
        # Check for cancellation on every loop iteration — enables fast shutdown
        current_task = asyncio.current_task()
        if current_task is not None and current_task.done():
            logger.debug(f"[AppSync] _subscribe cancelled (task done), operation={operation_name}")
            return

        try:
            import ssl

            ssl_context = ssl.create_default_context(cafile=certifi.where())

            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(
                    ws_url,
                    protocols=["graphql-ws"],
                    ssl=ssl_context,
                    timeout=aiohttp.ClientTimeout(total=60, connect=30),
                ) as websocket:
                    await websocket.send_str(json.dumps({"type": "connection_init"}))
                    conn_start = time.time()

                    # Wait for connection_ack with periodic cancellation checks
                    ack_timeout = 30
                    while True:
                        current_task = asyncio.current_task()
                        if current_task is not None and current_task.done():
                            logger.debug(f"[AppSync] _subscribe cancelled during ack, operation={operation_name}")
                            return
                        try:
                            msg = await asyncio.wait_for(websocket.receive(), timeout=5.0)
                        except asyncio.TimeoutError:
                            continue  # check cancellation and retry ack
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            response_data = json.loads(msg.data)
                            msg_type = response_data.get('type')
                            if msg_type == "connection_ack":
                                last_msg_time = time.time()
                                break
                            elif msg_type == "connection_error":
                                error_payload = response_data.get('payload', {})
                                logger.warning(f"[AppSync] Connection error: {error_payload}")
                        elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                            raise RuntimeError("connection closed during ack")

                    api_headers = _mk_ws_headers(host, config.api_key, config.auth_token)
                    sub_data = {
                        "query": query,
                        "operationName": operation_name,
                        "variables": variables,
                    }

                    sub_request = {
                        "id": f"sub-{uuid4().hex}",
                        "payload": {
                            "data": json.dumps(sub_data),
                            "extensions": {
                                "authorization": {k: v for k, v in api_headers.items() if k != "content-type"}
                            },
                        },
                        "type": "start",
                    }

                    await websocket.send_str(json.dumps(sub_request))

                    # Wait for start_ack with periodic cancellation checks
                    while True:
                        current_task = asyncio.current_task()
                        if current_task is not None and current_task.done():
                            logger.debug(f"[AppSync] _subscribe cancelled during start_ack, operation={operation_name}")
                            return
                        try:
                            msg = await asyncio.wait_for(websocket.receive(), timeout=5.0)
                        except asyncio.TimeoutError:
                            continue
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            response_data = json.loads(msg.data)
                            if response_data.get("type") == "start_ack":
                                last_msg_time = time.time()
                                break
                            elif response_data.get("type") == "error":
                                logger.error(f"[AppSync] Subscription error: {response_data}")
                        elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                            raise RuntimeError("connection closed during start_ack")

                    # Main message loop with idle timeout and cancellation checks
                    while True:
                        current_task = asyncio.current_task()
                        if current_task is not None and current_task.done():
                            logger.debug(f"[AppSync] _subscribe cancelled, operation={operation_name}")
                            return

                        idle_elapsed = time.time() - last_msg_time
                        if idle_elapsed > max_idle_sec:
                            logger.warning(f"[AppSync] Idle timeout ({idle_elapsed:.0f}s > {max_idle_sec}s), operation={operation_name}")
                            return

                        receive_timeout = min(15.0, max(5.0, max_idle_sec - idle_elapsed))
                        try:
                            msg = await asyncio.wait_for(websocket.receive(), timeout=receive_timeout)
                        except asyncio.TimeoutError:
                            # check cancellation and idle timeout on timeout
                            current_task = asyncio.current_task()
                            if current_task is not None and current_task.done():
                                return
                            idle_elapsed = time.time() - last_msg_time
                            if idle_elapsed > max_idle_sec:
                                return
                            continue

                        if msg.type == aiohttp.WSMsgType.TEXT:
                            last_msg_time = time.time()
                            data = json.loads(msg.data)
                            if data.get("type") == "data":
                                payload_data = (data.get("payload") or {}).get("data")
                                if not isinstance(payload_data, dict):
                                    continue
                                envelope = payload_data.get(field_name)
                                if not isinstance(envelope, dict):
                                    continue
                                if "status" in envelope:
                                    envelope["status"] = _maybe_parse_awsjson(envelope.get("status"))

                                await on_envelope(envelope)

                            elif data.get("type") in ("ka", "keepalive"):
                                continue
                        elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                            raise RuntimeError("websocket closed")

        except asyncio.CancelledError:
            logger.debug(f"[AppSync] _subscribe CancelledError, operation={operation_name}")
            raise
        except Exception as e:
            retry += 1
            backoff = min(base_backoff * (2 ** (retry - 1)), 30)
            # Check cancellation before sleeping
            current_task = asyncio.current_task()
            if current_task is not None and current_task.done():
                logger.debug(f"[AppSync] _subscribe cancelled before backoff, operation={operation_name}")
                return
            logger.warning(f"[ec_tasks.appsync_pubsub] subscribe error (attempt {retry}/{max_retries}): {e}")
            if retry >= max_retries:
                raise
            await asyncio.sleep(backoff)


def start_task_status_streams_for_runs(
    *,
    config: AppSyncApiKeyConfig,
    run_ids: list[str],
    on_envelope: Callable[[Dict[str, Any]], Awaitable[None]],
    max_retries: int = 20,
    runner_from_run_id: Callable[[str], str] | None = None,
) -> list[asyncio.Task]:
    """Start multiple TaskStatus subscriptions (one per run_id).

    Returns the created asyncio tasks (caller owns cancellation).
    Default mapping is runner == run_id.
    """
    if runner_from_run_id is None:
        runner_from_run_id = lambda rid: rid

    tasks: list[asyncio.Task] = []
    for idx, rid in enumerate(run_ids or []):
        rid = (rid or "").strip()
        if not rid:
            continue
        runner = runner_from_run_id(rid)
        
        # Add staggered delay to avoid AppSync rate limiting
        # First subscription starts immediately, subsequent ones delayed
        delay = idx * 1.5  # 1.5s between each subscription (increased from 500ms)
        
        async def delayed_subscribe(runner_val, delay_val):
            if delay_val > 0:
                await asyncio.sleep(delay_val)
            return await subscribe_task_status(
                config=config,
                runner=runner_val,
                on_envelope=on_envelope,
                max_retries=max_retries,
            )
        
        tasks.append(
            asyncio.create_task(delayed_subscribe(runner, delay))
        )
    return tasks


async def subscribe_task_status(
    *,
    config: AppSyncApiKeyConfig,
    runner: str,
    on_envelope: Callable[[Dict[str, Any]], Awaitable[None]],
    max_retries: int = 20,
) -> None:
    await _subscribe(
        config=config,
        query=_graphql_on_task_status(),
        variables={"runner": runner},
        operation_name="OnTaskStatus",
        field_name="onTaskStatus",
        on_envelope=on_envelope,
        max_retries=max_retries,
        max_idle_sec=600,  # 10 min idle timeout as safety net; caller manages lifetime via cancellation
    )
