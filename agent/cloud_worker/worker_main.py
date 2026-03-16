import argparse
import asyncio
import json
import os
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

# Fix double-import: when run via `python -m agent.cloud_worker.worker_main`,
# __name__ is '__main__' but other modules import us as 'agent.cloud_worker.worker_main'.
# Without this, they get a separate module instance with its own globals (e.g. _global_passive_transport).
if __name__ == '__main__':
    sys.modules.setdefault('agent.cloud_worker.worker_main', sys.modules[__name__])

from utils.logger_helper import logger_helper as logger

# Hardcoded AppSync realtime endpoint for the cloud worker.
EC_APPSYNC_WS_ENDPOINT = "wss://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-realtime-api.us-east-1.amazonaws.com/graphql"
os.environ["EC_APPSYNC_WS_ENDPOINT"] = EC_APPSYNC_WS_ENDPOINT

# Revision marker for tracking deployments
WORKER_REVISION = "20260225a"

# =============================================================================
# L2C Test Mode - Wait for first passive step result before running skill
# Set to True to test L2C WebSocket pub/sub; set to False for production
# =============================================================================
L2C_TEST_MODE = False

from agent.cloud.s3_settings_loader import (
    DEFAULT_ECAN_SKILLS_BUCKET,
    DEFAULT_USER_BASE_PREFIX,
    S3SettingsLoader,
    normalize_user_email_for_s3_prefix,
    build_user_skills_s3_prefix,
    load_appsync_a2a_worker_config_from_s3_for_user,
    build_appsync_a2a_worker_config,
)

from agent.cloud_worker.cloud_logger import (
    configure_cloud_logger,
    stop_cloud_logger,
    get_skill_editor_logger,
)


# =============================================================================
# Global Passive Transport Registry
# Used to share the CloudWorkerPassiveTransport with CloudAgent in build_node.py
# =============================================================================
_global_passive_transport = None

def set_global_passive_transport(transport) -> None:
    """Set the global passive transport for CloudAgent to use."""
    global _global_passive_transport
    _global_passive_transport = transport
    logger.info(f"[cloud_worker] set_global_passive_transport: type={type(transport).__name__}, id={id(transport)}")

def get_global_passive_transport():
    """Get the global passive transport (or None if not set)."""
    result = _global_passive_transport
    logger.info(f"[cloud_worker] get_global_passive_transport: result={type(result).__name__ if result else 'None'}, id={id(result) if result else 'N/A'}")
    return result

def clear_global_passive_transport() -> None:
    """Clear the global passive transport."""
    global _global_passive_transport
    _global_passive_transport = None


def _ecs_task_id_from_arn(task_arn: Optional[str]) -> str:
    if not task_arn or not isinstance(task_arn, str):
        return ""
    return task_arn.split("/")[-1] if "/" in task_arn else task_arn


# =============================================================================
# Run State Management
# =============================================================================

@dataclass
class RunState:
    """Tracks the state of a skill run for coordination with Lambda/frontend."""
    run_id: str
    username: str
    skill_id: str
    skill_name: str
    status: str = "queued"  # queued, running, paused, completed, failed, cancelled
    sqs_message_id: Optional[str] = None
    ecs_task_arn: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None
    current_node: Optional[str] = None
    
    # Control flags (set by subscription listener)
    cancel_requested: bool = False
    pause_requested: bool = False
    step_requested: bool = False


class RunStateManager:
    """Manages run state persistence to S3 and real-time updates via AppSync."""
    
    def __init__(self, bucket: str, key_root: str, region: str):
        self.bucket = bucket
        self.key_root = key_root
        self.region = region
        self._s3_client = None
    
    @property
    def s3_client(self):
        if self._s3_client is None:
            import boto3
            self._s3_client = boto3.client("s3", region_name=self.region)
        return self._s3_client
    
    def _get_run_key(self, username: str, run_id: str) -> str:
        from agent.skill_editor.skill_editor_agent import _safe_user_dir_name
        safe_user = _safe_user_dir_name(username)
        prefix = (self.key_root or "").strip().strip("/")
        parts = [p for p in [prefix, "users", safe_user, "runs", f"{run_id}.json"] if p]
        return "/".join(parts)
    
    def load(self, username: str, run_id: str) -> Optional[RunState]:
        """Load run state from S3."""
        key = self._get_run_key(username, run_id)
        try:
            resp = self.s3_client.get_object(Bucket=self.bucket, Key=key)
            data = json.loads(resp["Body"].read().decode("utf-8"))
            return RunState(
                run_id=data.get("run_id", run_id),
                username=data.get("username", username),
                skill_id=data.get("skill_id", ""),
                skill_name=data.get("skill_name", ""),
                status=data.get("status", "queued"),
                sqs_message_id=data.get("sqs_message_id"),
                ecs_task_arn=data.get("ecs_task_arn"),
                created_at=data.get("created_at"),
                updated_at=data.get("updated_at"),
                started_at=data.get("started_at"),
                completed_at=data.get("completed_at"),
                error=data.get("error"),
                current_node=data.get("current_node"),
                cancel_requested=data.get("status") == "cancelled",
            )
        except Exception as e:
            logger.warning(f"[RunStateManager] Failed to load run state: {e}")
            return None
    
    def save(self, state: RunState) -> None:
        """Save run state to S3."""
        key = self._get_run_key(state.username, state.run_id)
        data = {
            "run_id": state.run_id,
            "username": state.username,
            "skill_id": state.skill_id,
            "skill_name": state.skill_name,
            "status": state.status,
            "sqs_message_id": state.sqs_message_id,
            "ecs_task_arn": state.ecs_task_arn,
            "created_at": state.created_at,
            "updated_at": state.updated_at,
            "started_at": state.started_at,
            "completed_at": state.completed_at,
            "error": state.error,
            "current_node": state.current_node,
        }
        try:
            self.s3_client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=json.dumps(data, ensure_ascii=False, indent=2),
                ContentType="application/json",
            )
            logger.info(f"[RunStateManager] Saved run state: {key}")
        except Exception as e:
            logger.error(f"[RunStateManager] Failed to save run state: {e}")


# =============================================================================
# AppSync Subscription Listener for Run Control Commands
# =============================================================================

class RunControlListener:
    """
    Listens to AppSync subscriptions for run control commands (cancel, pause, resume, step).
    Runs in a background thread/task and updates the RunState when commands are received.
    """
    
    def __init__(
        self,
        appsync_url: str,
        appsync_api_key: str,
        run_state: RunState,
        on_command: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ):
        self.appsync_url = appsync_url
        self.appsync_api_key = appsync_api_key
        self.run_state = run_state
        self.on_command = on_command
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
    
    async def _handle_envelope(self, envelope: Dict[str, Any]) -> None:
        """Handle incoming subscription envelope."""
        try:
            event_type = envelope.get("eventType") or ""
            payload_raw = envelope.get("payload")
            
            if isinstance(payload_raw, str):
                try:
                    payload = json.loads(payload_raw)
                except json.JSONDecodeError:
                    payload = {"raw": payload_raw}
            else:
                payload = payload_raw or {}
            
            logger.info(f"[RunControlListener] Received event: type={event_type}")
            
            # Check if this event is for our run
            event_run_id = payload.get("run_id") or envelope.get("sessionId")
            if event_run_id and event_run_id != self.run_state.run_id:
                return  # Not for us
            
            # Handle control commands
            if event_type == "run_cancelled" or payload.get("type") == "run_cancelled":
                logger.info(f"[RunControlListener] Cancel requested for run {self.run_state.run_id}")
                self.run_state.cancel_requested = True
                
            elif event_type == "run_paused" or payload.get("type") == "run_paused":
                logger.info(f"[RunControlListener] Pause requested for run {self.run_state.run_id}")
                self.run_state.pause_requested = True
                
            elif event_type == "run_resumed" or payload.get("type") == "run_resumed":
                logger.info(f"[RunControlListener] Resume requested for run {self.run_state.run_id}")
                self.run_state.pause_requested = False
                
            elif event_type == "run_step" or payload.get("type") == "run_step":
                logger.info(f"[RunControlListener] Step requested for run {self.run_state.run_id}")
                self.run_state.step_requested = True
            
            elif event_type == "ping" or payload.get("type") == "ping":
                logger.info(f"[RunControlListener] Ping received for run {self.run_state.run_id} - worker is alive!")
            
            # Call custom handler if provided
            if self.on_command:
                self.on_command(event_type, payload)
                
        except Exception as e:
            logger.error(f"[RunControlListener] Error handling envelope: {e}")
    
    async def start(self) -> None:
        """Start listening for run control commands."""
        from agent.ec_tasks.appsync_pubsub import AppSyncApiKeyConfig, _subscribe
        
        config = AppSyncApiKeyConfig(
            http_endpoint=self.appsync_url,
            api_key=self.appsync_api_key,
        )
        
        # Subscribe to skill editor stream events for this user
        # The subscription filters by owner (username)
        query = """
        subscription OnSkillEditorStreamEvent($owner: String!) {
          onSkillEditorStreamEvent(owner: $owner) {
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
        
        try:
            await _subscribe(
                config=config,
                query=query,
                variables={"owner": self.run_state.username},
                operation_name="OnSkillEditorStreamEvent",
                field_name="onSkillEditorStreamEvent",
                on_envelope=self._handle_envelope,
                max_retries=5,
            )
        except asyncio.CancelledError:
            logger.info("[RunControlListener] Subscription cancelled")
        except Exception as e:
            logger.error(f"[RunControlListener] Subscription error: {e}")
    
    def start_background(self, loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
        """Start the listener in the background."""
        if loop is None:
            loop = asyncio.get_event_loop()
        self._task = loop.create_task(self.start())
        logger.info(f"[RunControlListener] Started background listener for run {self.run_state.run_id}")
    
    def stop(self) -> None:
        """Stop the listener."""
        if self._task and not self._task.done():
            self._task.cancel()
            logger.info("[RunControlListener] Stopped listener")


# =============================================================================
# AppSync Subscription Listener for Passive Step Results (L2C - Local to Cloud)
# =============================================================================

class PassiveStepResultListener:
    """
    Listens to AppSync subscriptions for passive step results from local clients.
    Used in hybrid cloud mode where local browser sends results back to cloud worker.
    Also useful for L2C WS Test to verify local-to-cloud pub/sub.
    """
    
    def __init__(
        self,
        appsync_url: str,
        appsync_api_key: str,
        client_id: str,
        run_id: str,
        owner: str,
        auth_token: Optional[str] = None,
        on_result: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        self.appsync_url = appsync_url
        self.appsync_api_key = appsync_api_key
        self.client_id = client_id
        self.run_id = run_id
        self.owner = owner
        self.auth_token = auth_token
        self.on_result = on_result
        self._task: Optional[asyncio.Task] = None
        self._thread: Optional[threading.Thread] = None
        # Event that signals first result received (for L2C test mode)
        self.first_result_received: asyncio.Event = asyncio.Event()
        self._subscription_ready: asyncio.Event = asyncio.Event()
    
    async def _handle_envelope(self, envelope: Dict[str, Any]) -> None:
        """Handle incoming passive step result."""
        try:
            logger.info(
                f"[PassiveStepResultListener] Raw envelope: {json.dumps(envelope, default=str)[:500]}"
            )
            step_id = envelope.get("stepId", "")
            result_raw = envelope.get("result")
            dom_tree_raw = envelope.get("dom_tree")
            
            # Parse AWSJSON fields (may be double-encoded by VTL escaping)
            if isinstance(result_raw, str):
                try:
                    result = json.loads(result_raw)
                    if isinstance(result, str):  # double-encoded
                        result = json.loads(result)
                except json.JSONDecodeError:
                    result = {"raw": result_raw}
            else:
                result = result_raw or {}
            
            logger.info(f"[PassiveStepResultListener] Received step result: stepId={step_id}, clientId={self.client_id}")
            
            # Echo back via SkillEditorStreamEvent for testing/debugging
            se_logger = get_skill_editor_logger()
            if se_logger:
                # Truncate screenshot for logging
                from agent.ec_skills.browser_use_extension.passive_utils import truncate_screenshot_for_logging
                log_result = truncate_screenshot_for_logging(result)
                se_logger.log(
                    f"[L2C] ✅ Received PassiveStepResult: stepId={step_id}, result={json.dumps(log_result)[:500]}"
                )
            
            # Signal that first result is received (for L2C test mode)
            if not self.first_result_received.is_set():
                self.first_result_received.set()
                logger.info(f"[PassiveStepResultListener] First result received, signaling ready to proceed")
            
            # Call custom handler if provided
            if self.on_result:
                self.on_result(envelope)
                
        except Exception as e:
            logger.error(f"[PassiveStepResultListener] Error handling envelope: {e}")
    
    async def start(self) -> None:
        """Start listening for passive step results."""
        from agent.ec_tasks.appsync_pubsub import AppSyncApiKeyConfig, _subscribe
        
        config = AppSyncApiKeyConfig(
            http_endpoint=self.appsync_url,
            api_key=self.appsync_api_key,
            auth_token=self.auth_token,
        )
        
        # Subscribe to passive step results for this client/run
        query = """
        subscription OnPassiveStepResult($clientId: ID!, $runId: ID!) {
          onPassiveStepResult(clientId: $clientId, runId: $runId) {
            clientId
            runId
            stepId
            result
            dom_tree
            timestamp
          }
        }
        """
        
        logger.info(f"[PassiveStepResultListener] Starting subscription for clientId={self.client_id}, runId={self.run_id}")
        
        # Log to skill editor console that listener is ready
        se_logger = get_skill_editor_logger()
        if se_logger:
            se_logger.log(
                f"[L2C] 🎧 PassiveStepResultListener READY - waiting for messages on clientId={self.client_id}, runId={self.run_id}"
            )
        
        # Signal that subscription is ready
        self._subscription_ready.set()
        
        try:
            await _subscribe(
                config=config,
                query=query,
                variables={"clientId": self.client_id, "runId": self.run_id},
                operation_name="OnPassiveStepResult",
                field_name="onPassiveStepResult",
                on_envelope=self._handle_envelope,
                max_retries=5,
            )
        except asyncio.CancelledError:
            logger.info("[PassiveStepResultListener] Subscription cancelled")
        except Exception as e:
            logger.error(f"[PassiveStepResultListener] Subscription error: {e}")
    
    def start_background(self, loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
        """Start the listener in a DEDICATED DAEMON THREAD with its own event loop.

        CRITICAL: Must NOT share the main event loop.  When a LangGraph sync node
        calls run_async_in_sync() it blocks the current thread (which is the main
        event loop's thread).  If the subscription ran as a task on that same loop,
        websocket.receive() would stall for the entire timeout+grace window — exactly
        the bug observed where the result always arrives ~108 ms after grace expires.
        A dedicated thread+loop receives AppSync messages in real-time regardless of
        what the main loop is doing.
        """
        def _run_in_thread() -> None:
            thread_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(thread_loop)
            try:
                thread_loop.run_until_complete(self.start())
            except Exception as exc:
                logger.error(f"[PassiveStepResultListener] Dedicated thread loop error: {exc}")
            finally:
                try:
                    thread_loop.close()
                except Exception:
                    pass

        self._thread = threading.Thread(
            target=_run_in_thread,
            daemon=True,
            name=f"passive-listener-{self.run_id[-8:]}",
        )
        self._thread.start()
        logger.info(f"[PassiveStepResultListener] Started DEDICATED THREAD listener for client={self.client_id}, run={self.run_id}")
    
    def stop(self) -> None:
        """Stop the listener."""
        # The thread is daemon=True so it exits with the process automatically.
        # We cancel the asyncio task if it exists (for cases where start_background
        # was called with loop= and used the old create_task path).
        if self._task and not self._task.done():
            self._task.cancel()
        logger.info("[PassiveStepResultListener] Stopped listener")


# =============================================================================
# Original WorkerMessage (kept for backwards compatibility)
# =============================================================================

@dataclass(frozen=True)
class WorkerMessage:
    user_email: str
    chat_id: str
    sender_id: str
    skill_name: str
    prompt: str = ""


def _looks_like_auth_error(result: Any) -> bool:
    if not isinstance(result, dict):
        return False

    errors = result.get("errors")
    if not isinstance(errors, list):
        return False

    for err in errors:
        if not isinstance(err, dict):
            continue
        msg = (err.get("message") or "").lower()
        etype = (err.get("errorType") or "").lower()
        if "unauthorized" in msg or "not authorized" in msg:
            return True
        if etype in {"unauthorized", "forbidden"}:
            return True

    return False


def _parse_worker_message(raw: Any) -> WorkerMessage:
    if isinstance(raw, str):
        raw = json.loads(raw)
    if not isinstance(raw, dict):
        raise ValueError("worker message must be a dict")

    user_email = (raw.get("user_email") or raw.get("userEmail") or "").strip()
    chat_id = (raw.get("chat_id") or raw.get("chatId") or "").strip()
    sender_id = (raw.get("sender_id") or raw.get("senderId") or "").strip()
    skill_name = (raw.get("skill_name") or raw.get("skillName") or "").strip()
    prompt = (raw.get("prompt") or raw.get("text") or "").strip()

    missing = [k for k, v in [("user_email", user_email), ("chat_id", chat_id), ("sender_id", sender_id), ("skill_name", skill_name)] if not v]
    if missing:
        raise ValueError(f"worker message missing required fields: {', '.join(missing)}")

    return WorkerMessage(user_email=user_email, chat_id=chat_id, sender_id=sender_id, skill_name=skill_name, prompt=prompt)


async def _publish_event(
    *,
    loader: S3SettingsLoader,
    user_email: str,
    chat_id: str,
    sender_id: str,
    text: str,
    event_type: str,
    bucket: str,
    base_prefix: str,
    region: str,
    extra_metadata: Optional[Dict[str, Any]] = None,
) -> None:
    from a2a.types import Message, TextPart
    from agent.chats.wan_a2a_chat import wan_a2a_send_message

    channel_id = f"chat:{chat_id}"

    def _mk_msg() -> Message:
        return Message(
            role="assistant",
            parts=[TextPart(type="text", text=text)],
            message_id=str(uuid4()),
        )

    settings = loader.load(force_refresh=False)
    cfg = build_appsync_a2a_worker_config(settings)

    md = {"schema_version": 1, "event_type": event_type, "chat_id": chat_id}
    if extra_metadata:
        md.update(extra_metadata)

    result = await wan_a2a_send_message(
        mainwin=None,
        channel_id=channel_id,
        message=_mk_msg(),
        sender_id=sender_id,
        session_id=chat_id,
        recipient_id=None,
        auth_headers=cfg.auth_headers,
        endpoints=cfg.endpoints,
        metadata=md,
    )

    if _looks_like_auth_error(result):
        loader.invalidate()
        settings = loader.load(force_refresh=True)
        cfg = build_appsync_a2a_worker_config(settings)
        await wan_a2a_send_message(
            mainwin=None,
            channel_id=channel_id,
            message=_mk_msg(),
            sender_id=sender_id,
            session_id=chat_id,
            recipient_id=None,
            auth_headers=cfg.auth_headers,
            endpoints=cfg.endpoints,
            metadata=md,
        )


def _download_s3_prefix_to_dir(*, bucket: str, prefix: str, dest_dir: Path, region: str) -> int:
    import boto3
    from botocore.config import Config

    client = boto3.client("s3", config=Config(region_name=region, retries={"max_attempts": 5, "mode": "standard"}))

    downloaded = 0
    continuation_token: Optional[str] = None
    while True:
        kwargs: Dict[str, Any] = {"Bucket": bucket, "Prefix": prefix}
        if continuation_token:
            kwargs["ContinuationToken"] = continuation_token

        resp = client.list_objects_v2(**kwargs)
        contents = resp.get("Contents") or []

        for obj in contents:
            key = obj.get("Key")
            if not key or key.endswith("/"):
                continue
            rel = key[len(prefix) :]
            rel = rel.lstrip("/")
            local_path = dest_dir / rel
            local_path.parent.mkdir(parents=True, exist_ok=True)
            client.download_file(bucket, key, str(local_path))
            downloaded += 1

        if resp.get("IsTruncated"):
            continuation_token = resp.get("NextContinuationToken")
            continue
        break

    return downloaded


def _derive_fallback_skill_prefixes(*, username: str, skill_folder_name: str, skill_data: Dict[str, Any]) -> List[str]:
    safe_user = normalize_user_email_for_s3_prefix(username)

    prefixes: List[str] = []

    raw_path = (skill_data.get("path") or "").strip()
    if raw_path and "/my_skills/" in raw_path:
        # Example:
        #   songc_yahoo_com/my_skills/test_local_tool_skill/diagram_dir/...
        parts = [p for p in raw_path.split("/") if p]
        try:
            idx = parts.index("my_skills")
            if idx + 1 < len(parts):
                prefixes.append("/".join(parts[: idx + 2]))
        except ValueError:
            pass

    # Legacy layout observed in ecan-skills bucket root
    prefixes.append(f"{safe_user}/my_skills/{skill_folder_name}")
    # Some older clients store without _skill suffix
    if skill_folder_name.endswith("_skill"):
        prefixes.append(f"{safe_user}/my_skills/{skill_folder_name[:-6]}")

    # De-dupe while preserving order
    seen = set()
    out: List[str] = []
    for p in prefixes:
        p2 = (p or "").strip().strip("/")
        if not p2 or p2 in seen:
            continue
        seen.add(p2)
        out.append(p2)
    return out


def _find_skill_folder(root: Path) -> Path:
    if not root.exists():
        raise FileNotFoundError(str(root))

    if (root / "diagram_dir").exists() or (root / "code_skill").exists() or (root / "code_dir").exists():
        return root

    candidates = []
    for p in root.rglob("diagram_dir"):
        candidates.append(p.parent)
    for p in root.rglob("code_skill"):
        candidates.append(p.parent)
    for p in root.rglob("code_dir"):
        candidates.append(p.parent)

    candidates = [c for c in candidates if c.is_dir()]
    if not candidates:
        raise FileNotFoundError(f"No skill folder found under {root}")

    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def _run_skill_once(*, msg: WorkerMessage, skill_root: Path) -> Dict[str, Any]:
    from agent.ec_skills.build_agent_skills import load_skill_from_folder
    from agent.ec_skills.prep_skills_run import prep_skills_run
    from agent.ec_tasks.executor import execute_task_hybrid
    from agent.ec_tasks.models import ManagedTask
    from a2a.types import TaskState, TaskStatus

    skill = load_skill_from_folder(skill_root, mainwin=None)
    if skill is None:
        raise RuntimeError(f"Failed to load skill from {skill_root}")

    class _Card:
        def __init__(self, _id: str):
            self.id = _id

    class _Agent:
        def __init__(self, _id: str):
            self.card = _Card(_id)

    agent = _Agent(msg.sender_id)

    in_msg = {
        "id": str(uuid4()),
        "method": "skill_run",
        "params": {
            "message": {
                "parts": [{"kind": "text", "text": msg.prompt or ""}],
            },
            "metadata": {
                "mtype": "skill_run",
                "params": {"chatId": msg.chat_id},
                "async_response": True,
            },
            "sessionId": msg.chat_id,
        },
    }

    # Create task with required a2a.types.Task fields
    task = ManagedTask(
        run_id=msg.chat_id,
        name=skill.name or msg.skill_name,
        description="cloud_worker_run",
        skill=skill,
        metadata={},
        contextId=msg.chat_id,  # Required by a2a.types.Task
        status=TaskStatus(state=TaskState.submitted),  # Required by a2a.types.Task
    )

    state = prep_skills_run(skill, agent, task.id, in_msg, None)
    if isinstance(state, dict):
        attrs = state.get("attributes") if isinstance(state.get("attributes"), dict) else {}
        attrs["chat_id"] = msg.chat_id
        attrs["run_id"] = msg.chat_id
        attrs["passive_run_id"] = msg.chat_id
        state["attributes"] = attrs

        meta = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
        meta["run_id"] = msg.chat_id
        meta["passive_run_id"] = msg.chat_id
        state["metadata"] = meta

        state["browser_use_run_id"] = msg.chat_id
    task.metadata["state"] = state

    return execute_task_hybrid(task, state, use_async=True)


async def handle_one_message(
    *,
    raw_message: Any,
    bucket: str,
    base_prefix: str,
    region: str,
) -> None:
    msg = _parse_worker_message(raw_message)

    loader, _cfg = load_appsync_a2a_worker_config_from_s3_for_user(
        bucket=bucket,
        user_email=msg.user_email,
        base_prefix=base_prefix,
        region=region,
        ttl_seconds=60,
    )

    await _publish_event(
        loader=loader,
        user_email=msg.user_email,
        chat_id=msg.chat_id,
        sender_id=msg.sender_id,
        text=f"[worker] starting skill '{msg.skill_name}'",
        event_type="worker_start",
        bucket=bucket,
        base_prefix=base_prefix,
        region=region,
    )

    skills_prefix = build_user_skills_s3_prefix(user_email=msg.user_email, base_prefix=base_prefix)
    skill_prefix = f"{skills_prefix}/{msg.skill_name}"

    tmp_dir = Path(tempfile.mkdtemp(prefix="ecan_skill_"))
    try:
        downloaded = _download_s3_prefix_to_dir(bucket=bucket, prefix=skill_prefix, dest_dir=tmp_dir, region=region)
        if downloaded == 0:
            safe_user = normalize_user_email_for_s3_prefix(msg.user_email)
            legacy_prefixes = [
                f"{safe_user}/my_skills/{msg.skill_name}",
                f"{safe_user}/my_skills/{msg.skill_name}_skill",
            ]
            for p in legacy_prefixes:
                logger.warning(f"[cloud_worker] No files found under {skill_prefix}; trying legacy prefix: {p}")
                downloaded = _download_s3_prefix_to_dir(bucket=bucket, prefix=p, dest_dir=tmp_dir, region=region)
                if downloaded > 0:
                    break
        skill_folder = _find_skill_folder(tmp_dir)

        await _publish_event(
            loader=loader,
            user_email=msg.user_email,
            chat_id=msg.chat_id,
            sender_id=msg.sender_id,
            text=f"[worker] loaded skill folder: {skill_folder.name}",
            event_type="skill_loaded",
            bucket=bucket,
            base_prefix=base_prefix,
            region=region,
        )

        result = _run_skill_once(msg=msg, skill_root=skill_folder)

        await _publish_event(
            loader=loader,
            user_email=msg.user_email,
            chat_id=msg.chat_id,
            sender_id=msg.sender_id,
            text=f"[worker] skill finished (success={bool(result.get('success', True))})",
            event_type="worker_done",
            bucket=bucket,
            base_prefix=base_prefix,
            region=region,
            extra_metadata={"result": result},
        )

    except Exception as e:
        await _publish_event(
            loader=loader,
            user_email=msg.user_email,
            chat_id=msg.chat_id,
            sender_id=msg.sender_id,
            text=f"[worker] skill failed: {e}",
            event_type="worker_error",
            bucket=bucket,
            base_prefix=base_prefix,
            region=region,
        )
        raise


async def run_long_poll(*, queue_url: str, bucket: str, base_prefix: str, region: str) -> None:
    import boto3
    from botocore.config import Config
    from datetime import datetime, timezone

    client = boto3.client("sqs", config=Config(region_name=region, retries={"max_attempts": 5, "mode": "standard"}))
    
    # Initialize run state manager
    state_manager = RunStateManager(bucket=bucket, key_root=base_prefix, region=region)
    
    # Get ECS task ARN from metadata service (if running in Fargate)
    ecs_task_arn = None
    try:
        import urllib.request
        metadata_uri = os.environ.get("ECS_CONTAINER_METADATA_URI_V4")
        if metadata_uri:
            with urllib.request.urlopen(f"{metadata_uri}/task", timeout=2) as resp:
                task_meta = json.loads(resp.read().decode("utf-8"))
                ecs_task_arn = task_meta.get("TaskARN")
                logger.info(f"[cloud_worker] Running as ECS task: {ecs_task_arn}")
    except Exception as e:
        logger.debug(f"[cloud_worker] Not running in ECS or failed to get task ARN: {e}")

    while True:
        resp = client.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=20,
            VisibilityTimeout=300,
            MessageAttributeNames=["All"],
        )

        msgs = resp.get("Messages") or []
        if not msgs:
            continue

        m = msgs[0]
        receipt = m.get("ReceiptHandle")
        body = m.get("Body")
        msg_attrs = m.get("MessageAttributes") or {}
        
        # Extract run metadata from message attributes
        run_id = msg_attrs.get("run_id", {}).get("StringValue")
        username = msg_attrs.get("username", {}).get("StringValue")
        skill_id = msg_attrs.get("skill_id", {}).get("StringValue")
        
        run_state: Optional[RunState] = None
        control_listener: Optional[RunControlListener] = None
        
        try:
            # Parse message body
            if isinstance(body, str):
                msg_data = json.loads(body)
            else:
                msg_data = body or {}
            
            # Check if this is a new-format message from Lambda (runSkill)
            if "run_id" in msg_data:
                run_id = run_id or msg_data.get("run_id")
                username = username or msg_data.get("username")
                skill_id = skill_id or msg_data.get("skill_id")
                skill_name = msg_data.get("skill_name", "unnamed")

                ecs_task_id = _ecs_task_id_from_arn(ecs_task_arn)
                if ecs_task_id:
                    if run_id and str(run_id) != ecs_task_id:
                        logger.warning(
                            "[cloud_worker] Overriding launch run_id with ECS task id "
                            f"for canonical passive routing (launch_run_id={run_id}, ecs_task_id={ecs_task_id})"
                        )
                    run_id = ecs_task_id
                    msg_data["run_id"] = run_id
                    msg_data["passive_run_id"] = run_id
                
                logger.info(f"[cloud_worker] Processing skill run: run_id={run_id}, skill={skill_name}")
                
                # Check if run was cancelled before we started
                existing_state = state_manager.load(username, run_id) if (username and run_id) else None
                if existing_state and existing_state.status == "cancelled":
                    logger.info(f"[cloud_worker] Run {run_id} was cancelled, skipping")
                    if receipt:
                        client.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt)
                    continue
                
                # Create/update run state
                now_iso = datetime.now(timezone.utc).isoformat()
                run_state = RunState(
                    run_id=run_id,
                    username=username,
                    skill_id=skill_id,
                    skill_name=skill_name,
                    status="running",
                    ecs_task_arn=ecs_task_arn,
                    created_at=msg_data.get("created_at", now_iso),
                    updated_at=now_iso,
                    started_at=now_iso,
                )
                
                # Save running state
                if username and run_id:
                    state_manager.save(run_state)
                
                # Start AppSync subscription listener for control commands
                appsync_url = os.environ.get("APPSYNC_API_URL", "")
                appsync_key = os.environ.get("APPSYNC_API_KEY", "")
                if appsync_url and appsync_key and run_state:
                    control_listener = RunControlListener(
                        appsync_url=appsync_url,
                        appsync_api_key=appsync_key,
                        run_state=run_state,
                    )
                    control_listener.start_background()
                
                # Publish start event
                await _publish_run_status_event(
                    bucket=bucket,
                    base_prefix=base_prefix,
                    region=region,
                    run_state=run_state,
                    event_type="run_started",
                    message=f"Skill '{skill_name}' started",
                )
                
                # Process the skill run
                await handle_skill_run_message(
                    msg_data=msg_data,
                    run_state=run_state,
                    bucket=bucket,
                    base_prefix=base_prefix,
                    region=region,
                )
                
                # Update state to completed
                run_state.status = "completed"
                run_state.completed_at = datetime.now(timezone.utc).isoformat()
                run_state.updated_at = run_state.completed_at
                if username and run_id:
                    state_manager.save(run_state)
                
                # Publish completion event
                await _publish_run_status_event(
                    bucket=bucket,
                    base_prefix=base_prefix,
                    region=region,
                    run_state=run_state,
                    event_type="run_completed",
                    message=f"Skill '{skill_name}' completed successfully",
                )
            else:
                # Legacy message format - use old handler
                await handle_one_message(raw_message=body, bucket=bucket, base_prefix=base_prefix, region=region)
            
            # Delete message on success
            if receipt:
                client.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt)
                
        except Exception as e:
            logger.error("[cloud_worker] message processing failed", exc_info=True)
            
            # Update run state to failed
            if run_state:
                run_state.status = "failed"
                run_state.error = str(e)
                run_state.completed_at = datetime.now(timezone.utc).isoformat()
                run_state.updated_at = run_state.completed_at
                if username and run_id:
                    try:
                        state_manager.save(run_state)
                    except Exception:
                        pass
                
                # Publish failure event
                try:
                    await _publish_run_status_event(
                        bucket=bucket,
                        base_prefix=base_prefix,
                        region=region,
                        run_state=run_state,
                        event_type="run_failed",
                        message=f"Skill run failed: {e}",
                    )
                except Exception:
                    pass
            
            # Make message visible again for retry
            try:
                if receipt:
                    client.change_message_visibility(QueueUrl=queue_url, ReceiptHandle=receipt, VisibilityTimeout=0)
            except Exception:
                pass
        finally:
            # Stop the control listener
            if control_listener:
                control_listener.stop()


async def _publish_run_status_event(
    *,
    bucket: str,
    base_prefix: str,
    region: str,
    run_state: RunState,
    event_type: str,
    message: str,
) -> None:
    """Publish run status event via AppSync for real-time UI updates."""
    appsync_url = os.environ.get("APPSYNC_API_URL", "")
    appsync_key = os.environ.get("APPSYNC_API_KEY", "")
    
    if not appsync_url or not appsync_key:
        logger.debug("[cloud_worker] AppSync not configured, skipping status publish")
        return
    
    try:
        from agent.ec_tasks.appsync_pubsub import AppSyncApiKeyConfig, publish_skill_editor_stream_event
        
        config = AppSyncApiKeyConfig(
            http_endpoint=appsync_url,
            api_key=appsync_key,
        )
        
        await publish_skill_editor_stream_event(
            config=config,
            owner=run_state.username,
            session_id=run_state.run_id,
            event_type=event_type,
            payload={
                "run_id": run_state.run_id,
                "skill_id": run_state.skill_id,
                "skill_name": run_state.skill_name,
                "status": run_state.status,
                "current_node": run_state.current_node,
                "message": message,
                "error": run_state.error,
                "ecs_task_arn": run_state.ecs_task_arn,
            },
        )
        logger.info(f"[cloud_worker] Published {event_type} event for run {run_state.run_id}")
    except Exception as e:
        logger.warning(f"[cloud_worker] Failed to publish status event: {e}")


async def handle_skill_run_message(
    *,
    msg_data: Dict[str, Any],
    run_state: RunState,
    bucket: str,
    base_prefix: str,
    region: str,
) -> None:
    """
    Handle a skill run message from the Lambda runSkill handler.
    
    Expected msg_data format:
    {
        "run_id": str,
        "username": str,
        "skill_id": str,
        "skill_name": str,
        "skill_run_mode": str,
        "dev_mode": bool,  # If true, run with dev runner (breakpoints, step, etc.)
        "skill": {
            "skill_id": str,
            "skill_name": str,
            "diagram": {...},  # Flowgram diagram (nodes, edges, etc.)
            "bundle": {...},   # Optional bundle JSON (sheets data)
            "testInputs": {...},  # Optional test inputs
        },
        "created_at": str,
    }
    
    Strategy:
    - If dev_mode is true, use _run_skill_dev_mode() which sets up a TaskRunner
      with DevRunner for breakpoint/step support
    - Otherwise, save flowgram to S3 and use _run_skill_once() for simple execution
    """
    skill_data = msg_data.get("skill") or {}
    skill_name = skill_data.get("skill_name") or msg_data.get("skill_name") or "unnamed"
    diagram = skill_data.get("diagram") or {}
    # Bundle is nested inside diagram (frontend structure: diagram.bundle.sheets)
    bundle = diagram.get("bundle") or skill_data.get("bundle") or {}
    # Data mapping can come from skill_data or diagram
    data_mapping = skill_data.get("dataMapping") or skill_data.get("data_mapping") or diagram.get("dataMapping") or {}
    test_inputs = skill_data.get("testInputs") or {}
    dev_mode = msg_data.get("dev_mode", False)
    
    username = msg_data.get("username", "")
    # skill_owner is the original author — use for prompt resolution so
    # rented skills load the author's prompts, not the runner's.
    skill_owner = skill_data.get("skill_owner") or msg_data.get("skill_owner") or ""
    
    # Check for cancellation before starting
    if run_state.cancel_requested:
        logger.info(f"[cloud_worker] Run {run_state.run_id} cancelled before execution")
        run_state.status = "cancelled"
        return
    
    # Build skills prefix for this user
    skills_prefix = build_user_skills_s3_prefix(user_email=username, base_prefix=base_prefix)
    
    # Normalize skill name (ensure it ends with _skill for folder name)
    skill_folder_name = skill_name if skill_name.endswith("_skill") else f"{skill_name}_skill"
    skill_base_name = skill_name[:-6] if skill_name.endswith("_skill") else skill_name
    
    # If we have a diagram from frontend, save it to S3 first
    if diagram and diagram.get("nodes"):
        logger.info(f"[cloud_worker] Saving flowgram to S3 before execution: {skill_name}")
        await _save_flowgram_to_s3(
            bucket=bucket,
            skills_prefix=skills_prefix,
            skill_folder_name=skill_folder_name,
            skill_base_name=skill_base_name,
            diagram=diagram,
            bundle=bundle,
            data_mapping=data_mapping,
            region=region,
        )
    
    # Choose execution mode
    # Set up cloud prompt context for DynamoDB-based prompt loading.
    # Use skill_owner (original author) so rented skills resolve prompts
    # from the author's DynamoDB partition, not the runner's.
    from agent.cloud.cloud_prompt_loader import set_cloud_prompt_context, clear_cloud_prompt_context
    prompt_owner = skill_owner or username
    set_cloud_prompt_context(owner_id=prompt_owner, region=region)
    logger.info(f"[cloud_worker] Prompt context: owner={prompt_owner} (skill_owner={skill_owner}, runner={username})")
    
    try:
        if dev_mode and diagram and diagram.get("nodes"):
            # Dev mode: use TaskRunner with DevRunner for breakpoint/step support
            logger.info(f"[cloud_worker] Running in DEV MODE: {skill_name}")
            await _run_skill_dev_mode(
                diagram=diagram,
                bundle=bundle,
                test_inputs=test_inputs,
                run_state=run_state,
                bucket=bucket,
                base_prefix=base_prefix,
                region=region,
            )
        else:
            # Standard mode: download from S3 and run with _run_skill_once
            logger.info(f"[cloud_worker] Loading skill from S3: {skill_name}")
            skill_prefix = f"{skills_prefix}/{skill_folder_name}"
            
            tmp_dir = Path(tempfile.mkdtemp(prefix="ecan_skill_"))
            try:
                downloaded = _download_s3_prefix_to_dir(bucket=bucket, prefix=skill_prefix, dest_dir=tmp_dir, region=region)
                if downloaded == 0:
                    for p in _derive_fallback_skill_prefixes(username=username, skill_folder_name=skill_folder_name, skill_data=skill_data):
                        logger.warning(f"[cloud_worker] No files found under {skill_prefix}; trying fallback prefix: {p}")
                        downloaded = _download_s3_prefix_to_dir(bucket=bucket, prefix=p, dest_dir=tmp_dir, region=region)
                        if downloaded > 0:
                            break
                skill_folder = _find_skill_folder(tmp_dir)
                
                # Create a compatible WorkerMessage for the skill runner
                legacy_msg = WorkerMessage(
                    user_email=username,
                    chat_id=run_state.run_id,
                    sender_id=run_state.skill_id or "cloud_worker",
                    skill_name=skill_base_name,
                    prompt=json.dumps(test_inputs) if test_inputs else "",
                )
                
                result = _run_skill_once(msg=legacy_msg, skill_root=skill_folder)
                logger.info(f"[cloud_worker] Skill result: success={result.get('success', True)}")
            finally:
                # Cleanup temp directory
                import shutil
                try:
                    shutil.rmtree(tmp_dir, ignore_errors=True)
                except Exception:
                    pass
    finally:
        # Always clear cloud prompt context
        clear_cloud_prompt_context()


async def _save_flowgram_to_s3(
    *,
    bucket: str,
    skills_prefix: str,
    skill_folder_name: str,
    skill_base_name: str,
    diagram: Dict[str, Any],
    bundle: Dict[str, Any],
    data_mapping: Dict[str, Any],
    region: str,
) -> None:
    """
    Save a flowgram diagram to S3 in the proper skill folder structure.
    
    This creates:
        <skills_prefix>/<skill_folder_name>/diagram_dir/<skill_base_name>_skill.json
        <skills_prefix>/<skill_folder_name>/diagram_dir/<skill_base_name>_skill_bundle.json (if bundle provided)
        <skills_prefix>/<skill_folder_name>/data_mapping.json (if data_mapping provided)
    
    The flowgram can then be loaded by _run_skill_once() which will convert it
    to a LangGraph CompiledGraph for execution.
    """
    import boto3
    from botocore.config import Config
    
    client = boto3.client("s3", config=Config(region_name=region, retries={"max_attempts": 5, "mode": "standard"}))
    
    # Build the S3 key paths
    skill_root_prefix = f"{skills_prefix}/{skill_folder_name}"
    diagram_dir_prefix = f"{skill_root_prefix}/diagram_dir"
    skill_json_key = f"{diagram_dir_prefix}/{skill_base_name}_skill.json"
    bundle_json_key = f"{diagram_dir_prefix}/{skill_base_name}_skill_bundle.json"
    data_mapping_key = f"{skill_root_prefix}/data_mapping.json"
    
    # Save the main skill JSON (the flowgram diagram)
    skill_json_content = json.dumps(diagram, indent=2, ensure_ascii=False)
    logger.info(f"[cloud_worker] Saving skill JSON to s3://{bucket}/{skill_json_key}")
    client.put_object(
        Bucket=bucket,
        Key=skill_json_key,
        Body=skill_json_content.encode("utf-8"),
        ContentType="application/json",
    )
    
    # Save the bundle JSON if provided
    if bundle:
        bundle_json_content = json.dumps(bundle, indent=2, ensure_ascii=False)
        logger.info(f"[cloud_worker] Saving bundle JSON to s3://{bucket}/{bundle_json_key}")
        client.put_object(
            Bucket=bucket,
            Key=bundle_json_key,
            Body=bundle_json_content.encode("utf-8"),
            ContentType="application/json",
        )
    
    # Save the data_mapping.json at skill root level (not in diagram_dir)
    if data_mapping:
        data_mapping_content = json.dumps(data_mapping, indent=2, ensure_ascii=False)
        logger.info(f"[cloud_worker] Saving data_mapping.json to s3://{bucket}/{data_mapping_key}")
        client.put_object(
            Bucket=bucket,
            Key=data_mapping_key,
            Body=data_mapping_content.encode("utf-8"),
            ContentType="application/json",
        )
    
    logger.info(f"[cloud_worker] Flowgram saved to S3: {skill_folder_name}")


async def _run_skill_dev_mode(
    *,
    diagram: Dict[str, Any],
    bundle: Dict[str, Any],
    test_inputs: Dict[str, Any],
    run_state: RunState,
    bucket: str,
    base_prefix: str,
    region: str,
) -> None:
    """
    Run a skill in development mode with breakpoint and step support.
    
    This mirrors what the desktop app does in skill_dev_utils.py:
    1. Convert flowgram to langgraph using flowgram2langgraph_v2()
    2. Set up a DevRunner with breakpoint manager
    3. Create a ManagedTask
    4. Launch via the dev runner loop
    
    The key difference from _run_skill_once() is that dev mode:
    - Honors breakpoints marked in nodes (node.data.break_point = true)
    - Supports pause/step/resume via AppSync subscription
    - Publishes node-by-node progress events
    """
    from agent.ec_skill import EC_Skill, NodeState
    from agent.ec_skills.flowgram2langgraph_v2 import flowgram2langgraph_v2
    from agent.ec_skills.dev_defs import BreakpointManager
    from agent.ec_tasks.models import ManagedTask
    from agent.ec_tasks.dev_runner import DevRunner
    
    # Get skill editor logger for dev mode logs
    skill_logger = get_skill_editor_logger()
    
    logger.info(f"[cloud_worker] Setting up dev mode execution for run {run_state.run_id}")
    skill_logger.log(f"Starting dev mode execution for skill: {run_state.skill_name}")
    
    # Initialize breakpoint manager
    bp_manager = BreakpointManager()
    
    # Convert flowgram to langgraph (this also extracts breakpoints)
    try:
        skill_logger.log("Converting flowgram to LangGraph...")
        workflow, breakpoints = flowgram2langgraph_v2(
            diagram,
            bundle_json=bundle,
            enable_subgraph=False,
            bp_mgr=bp_manager,
        )
        if not workflow:
            raise RuntimeError("flowgram2langgraph_v2 returned empty workflow")
        logger.info(f"[cloud_worker] Converted flowgram to langgraph, breakpoints: {breakpoints}")
        skill_logger.log(f"Flowgram converted successfully. Breakpoints: {breakpoints}")
    except Exception as e:
        logger.error(f"[cloud_worker] Failed to convert flowgram: {e}")
        skill_logger.error(f"Failed to convert flowgram: {e}")
        raise
    
    # Set breakpoints if any were extracted from nodes
    if breakpoints:
        bp_manager.set_breakpoints(breakpoints)
        logger.info(f"[cloud_worker] Breakpoints set: {bp_manager.get_breakpoints()}")
    
    # Create an EC_Skill with the workflow
    skill = EC_Skill(
        name=run_state.skill_name or "dev_skill",
        description="Cloud worker dev run",
        source="ui",
    )
    skill.set_work_flow(workflow)
    
    # Create a ManagedTask for the dev run
    dev_task = ManagedTask(
        id=run_state.run_id,
        context_id=run_state.run_id,  # Required by a2a-sdk Task
        run_id=run_state.run_id,
        name=f"dev:run task for skill {run_state.skill_name}",
        description="Cloud worker development run",
        skill=skill,
        metadata={"state": {}},
    )
    
    # Create initial state (similar to skill_dev_utils.run_dev_skill)
    init_state = NodeState(
        messages=[],
        input=json.dumps(test_inputs) if test_inputs else "",
        attachments=[],
        prompts=[],
        history=[],
        attributes={},
        result={},
        tool_input=test_inputs if isinstance(test_inputs, dict) else {},
        tool_result={},
        threads=[],
        metadata={
            "run_id": run_state.run_id,
            "username": run_state.username,
            "skill_id": run_state.skill_id,
        },
        error="",
        retries=3,
        condition=False,
        case="",
        goals=[],
    )
    
    # Initialize DevRunner
    dev_runner = DevRunner()
    dev_runner.bp_manager = bp_manager
    
    # Execute the workflow in dev mode
    # We'll run it using the compiled graph directly, checking for control signals
    logger.info(f"[cloud_worker] Starting dev mode execution")
    skill_logger.log("Starting workflow execution...")
    
    try:
        # Get the compiled graph from the skill
        compiled_graph = skill.get_runnable()
        if not compiled_graph:
            raise RuntimeError("Skill has no compiled workflow")
        
        # Convert NodeState to dict for langgraph
        state_dict = init_state.model_dump() if hasattr(init_state, 'model_dump') else dict(init_state)
        
        # Stream through the graph, checking for control signals at each step
        current_node = None
        graph_config = {
            "configurable": {"thread_id": run_state.run_id},
            "recursion_limit": 200,
        }
        # Runtime context required by node_wrapper (ec_skill.py) for runtime.context
        graph_context = {
            "id": run_state.run_id,
            "run_id": run_state.run_id,
            "chat_id": run_state.run_id,
            "passive_run_id": run_state.run_id,
            "topic": "",
            "summary": "",
            "msg_thread_id": "",
            "tot_context": {},
            "app_context": {},
            "this_node": {"name": ""},
        }
        async for event in compiled_graph.astream(state_dict, config=graph_config, context=graph_context, stream_mode="updates"):
            # Check for cancellation
            if run_state.cancel_requested:
                logger.info(f"[cloud_worker] Cancellation requested at node {current_node}")
                skill_logger.warning(f"Execution cancelled at node: {current_node}")
                run_state.status = "cancelled"
                return
            
            # Extract current node info from event
            for node_name, node_output in event.items():
                current_node = node_name
                run_state.current_node = node_name
                logger.info(f"[cloud_worker] Dev mode executing node: {node_name}")
                skill_logger.log(f"Executing node: {node_name}")
                
                # Publish progress event
                await _publish_run_status_event(
                    bucket=bucket,
                    base_prefix=base_prefix,
                    region=region,
                    run_state=run_state,
                    event_type="run_progress",
                    message=f"Executing node: {node_name}",
                )
                
                # Check if this node is a breakpoint
                if bp_manager.has_breakpoint(node_name):
                    logger.info(f"[cloud_worker] Hit breakpoint at node: {node_name}")
                    skill_logger.log(f"⏸️ Breakpoint hit at node: {node_name}")
                    run_state.pause_requested = True
                    
                    # Publish breakpoint hit event
                    await _publish_run_status_event(
                        bucket=bucket,
                        base_prefix=base_prefix,
                        region=region,
                        run_state=run_state,
                        event_type="run_breakpoint",
                        message=f"Breakpoint hit at node: {node_name}",
                    )
                
                # Handle pause/step
                while run_state.pause_requested and not run_state.cancel_requested:
                    logger.debug(f"[cloud_worker] Paused at node {node_name}, waiting...")
                    await asyncio.sleep(0.5)
                    
                    # Check for step request
                    if run_state.step_requested:
                        logger.info(f"[cloud_worker] Step requested, continuing one node")
                        run_state.step_requested = False
                        run_state.pause_requested = True  # Will pause again after next node
                        break
        
        logger.info(f"[cloud_worker] Dev mode execution completed successfully")
        skill_logger.log("✅ Workflow execution completed successfully")
        
    except Exception as e:
        logger.error(f"[cloud_worker] Dev mode execution failed: {e}", exc_info=True)
        skill_logger.error(f"❌ Workflow execution failed: {e}")
        raise


async def run_single(*, message_json: str, bucket: str, base_prefix: str, region: str) -> None:
    """
    Run a single skill execution (one-shot mode for Fargate tasks).
    
    This mode is used when Lambda starts a Fargate task directly.
    The task processes one skill run and exits.
    """
    from datetime import datetime, timezone
    import boto3
    
    # Parse the message
    if isinstance(message_json, str):
        msg_data = json.loads(message_json)
    else:
        msg_data = message_json or {}
    
    # Check if this is a reference to S3 payload (to handle large skill data)
    if "payload_s3_bucket" in msg_data and "payload_s3_key" in msg_data:
        payload_bucket = msg_data["payload_s3_bucket"]
        payload_key = msg_data["payload_s3_key"]
        logger.info(f"[cloud_worker] Fetching full payload from S3: s3://{payload_bucket}/{payload_key}")
        try:
            s3_client = boto3.client("s3", region_name=region)
            resp = s3_client.get_object(Bucket=payload_bucket, Key=payload_key)
            full_payload = json.loads(resp["Body"].read().decode("utf-8"))
            # Merge full payload into msg_data (full payload takes precedence)
            msg_data = {**msg_data, **full_payload}
            logger.info(f"[cloud_worker] Loaded full payload from S3 successfully")
        except Exception as e:
            logger.error(f"[cloud_worker] Failed to fetch payload from S3: {e}")
            raise RuntimeError(f"Failed to fetch run payload from S3: {e}")
    
    # Initialize run state manager
    state_manager = RunStateManager(bucket=bucket, key_root=base_prefix, region=region)
    
    # Get ECS task ARN from metadata service (if running in Fargate)
    ecs_task_arn = None
    try:
        import urllib.request
        metadata_uri = os.environ.get("ECS_CONTAINER_METADATA_URI_V4")
        if metadata_uri:
            with urllib.request.urlopen(f"{metadata_uri}/task", timeout=2) as resp:
                task_meta = json.loads(resp.read().decode("utf-8"))
                ecs_task_arn = task_meta.get("TaskARN")
                logger.info(f"[cloud_worker] Running as ECS task: {ecs_task_arn}")
    except Exception as e:
        logger.debug(f"[cloud_worker] Not running in ECS or failed to get task ARN: {e}")
    
    # Check if this is a new-format message (from Lambda runSkill)
    if "run_id" in msg_data:
        run_id = msg_data.get("run_id")
        username = msg_data.get("username", "")
        skill_id = msg_data.get("skill_id", "")
        skill_name = msg_data.get("skill_name", "unnamed")

        ecs_task_id = _ecs_task_id_from_arn(ecs_task_arn)
        if ecs_task_id:
            if run_id and str(run_id) != ecs_task_id:
                logger.warning(
                    "[cloud_worker] Overriding launch run_id with ECS task id "
                    f"for canonical passive routing (launch_run_id={run_id}, ecs_task_id={ecs_task_id})"
                )
            run_id = ecs_task_id
            msg_data["run_id"] = run_id
            msg_data["passive_run_id"] = run_id
        
        logger.info(f"[cloud_worker] Processing skill run: run_id={run_id}, skill={skill_name}")
        
        # Check if run was cancelled before we started
        existing_state = state_manager.load(username, run_id) if (username and run_id) else None
        if existing_state and existing_state.status == "cancelled":
            logger.info(f"[cloud_worker] Run {run_id} was already cancelled, exiting")
            return
        
        # Create run state
        now_iso = datetime.now(timezone.utc).isoformat()
        run_state = RunState(
            run_id=run_id,
            username=username,
            skill_id=skill_id,
            skill_name=skill_name,
            status="running",
            ecs_task_arn=ecs_task_arn,
            created_at=msg_data.get("created_at", now_iso),
            updated_at=now_iso,
            started_at=now_iso,
        )
        
        # Save running state
        if username and run_id:
            state_manager.save(run_state)
        
        # Start AppSync subscription listener for control commands
        control_listener: Optional[RunControlListener] = None
        passive_listener: Optional[PassiveStepResultListener] = None
        appsync_url = os.environ.get("APPSYNC_API_URL", "")
        appsync_key = os.environ.get("APPSYNC_API_KEY", "")
        appsync_auth_token = (
            os.environ.get("APPSYNC_AUTH_TOKEN")
            or os.environ.get("EC_APPSYNC_TOKEN")
            or os.environ.get("EC_BROWSER_PASSIVE_TOKEN")
            or ""
        ).strip() or None
        if appsync_url and appsync_key:
            control_listener = RunControlListener(
                appsync_url=appsync_url,
                appsync_api_key=appsync_key,
                run_state=run_state,
            )
            control_listener.start_background()
            
            # Configure cloud logger for skill editor logs
            configure_cloud_logger(
                appsync_url=appsync_url,
                appsync_api_key=appsync_key,
                owner=username,
                session_id=run_id,
                flowgram_id=skill_id,
            )
            logger.info(f"[cloud_worker] Cloud logger configured for run {run_id}")
            
            # Start passive step result listener for L2C (local-to-cloud) communication
            # This enables hybrid cloud mode and L2C WS Test
            passive_client_id = msg_data.get("passive_client_id") or os.environ.get("EC_BROWSER_PASSIVE_CLIENT_ID", "")
            passive_run_id = msg_data.get("passive_run_id") or msg_data.get("chat_id") or msg_data.get("chatId")
            if passive_client_id:
                # Create the CloudWorkerPassiveTransport for CloudAgent to use
                from agent.ec_skills.browser_use_extension.cloud_agent import CloudWorkerPassiveTransport
                from agent.ec_skills.browser_use_extension.passive_protocol import PassiveBrowserStepResult
                
                passive_transport = CloudWorkerPassiveTransport(
                    appsync_url=appsync_url,
                    appsync_api_key=appsync_key,
                    client_id=passive_client_id,
                )
                
                # Register transport globally so CloudAgent can access it
                set_global_passive_transport(passive_transport)
                logger.info(f"[cloud_worker] CloudWorkerPassiveTransport registered for client={passive_client_id}")
                
                # Callback to deliver results to the transport
                def on_passive_result(envelope: Dict[str, Any]) -> None:
                    try:
                        result_raw = envelope.get("result")
                        if isinstance(result_raw, str):
                            result_dict = json.loads(result_raw)
                            if isinstance(result_dict, str):  # double-encoded AWSJSON
                                result_dict = json.loads(result_dict)
                        else:
                            result_dict = result_raw or {}
                        
                        # Parse dom_tree from the ENVELOPE (separate field from result)
                        # The client sends dom_tree as a top-level envelope field, not inside result
                        dom_tree_data = None
                        dom_tree_raw = envelope.get("dom_tree")
                        if dom_tree_raw:
                            try:
                                dom_tree_data = json.loads(dom_tree_raw) if isinstance(dom_tree_raw, str) else dom_tree_raw
                                if isinstance(dom_tree_data, str):  # double-encoded AWSJSON
                                    dom_tree_data = json.loads(dom_tree_data)
                                # Ignore empty dict — treat as no dom_tree
                                if isinstance(dom_tree_data, dict) and not dom_tree_data:
                                    dom_tree_data = None
                            except (json.JSONDecodeError, TypeError):
                                dom_tree_data = None
                        # Fallback: check inside result_dict (legacy format)
                        if not dom_tree_data:
                            dom_tree_data = result_dict.get("dom_tree")

                        # Build PassiveBrowserStepResult from envelope
                        step_result = PassiveBrowserStepResult(
                            run_id=envelope.get("runId", run_id),
                            step_id=envelope.get("stepId", ""),
                            ok=result_dict.get("ok", result_dict.get("success", True)),
                            elapsed_ms=result_dict.get("elapsed_ms", 0),
                            actions=result_dict.get("actions", []),
                            action_results=result_dict.get("action_results", []),
                            errors=result_dict.get("errors", []),
                            browser=result_dict.get("browser_state") or result_dict.get("browser", {}),
                            dom_tree=dom_tree_data,
                        )
                        
                        # Deliver to transport's queue
                        passive_transport.deliver_result(step_result)
                        logger.info(f"[cloud_worker] Delivered PassiveStepResult to transport: stepId={step_result.step_id}")
                    except Exception as e:
                        logger.error(f"[cloud_worker] Failed to deliver result to transport: {e}")
                
                if passive_run_id and str(passive_run_id) != str(run_id):
                    logger.warning(
                        "[cloud_worker] passive_run_id differs from run_id; forcing canonical run_id for listener "
                        f"(passive_run_id={passive_run_id}, run_id={run_id})"
                    )
                listener_run_id = run_id
                logger.info(
                    f"[cloud_worker] Passive listener identifiers: client_id={passive_client_id}, run_id={listener_run_id}"
                )
                passive_listener = PassiveStepResultListener(
                    appsync_url=appsync_url,
                    appsync_api_key=appsync_key,
                    client_id=passive_client_id,
                    run_id=listener_run_id,
                    owner=username,
                    auth_token=appsync_auth_token,
                    on_result=on_passive_result,  # Connect listener to transport
                )
                passive_listener.start_background()
                logger.info(f"[cloud_worker] Passive step result listener started for client={passive_client_id}")
                
                # # L2C TEST MODE: Wait for subscription to be ready, then wait for first message
                # # Uncomment this block to test L2C WebSocket pub/sub
                # if L2C_TEST_MODE:
                #     se_logger = get_skill_editor_logger()
                #     
                #     # Wait for subscription to be ready (max 5 seconds)
                #     try:
                #         await asyncio.wait_for(passive_listener._subscription_ready.wait(), timeout=5.0)
                #         logger.info(f"[cloud_worker] L2C TEST: Subscription is ready")
                #         if se_logger:
                #             se_logger.log("[L2C TEST] ⏳ Waiting for first PassiveStepResult message before running skill...")
                #     except asyncio.TimeoutError:
                #         logger.warning("[cloud_worker] L2C TEST: Subscription ready timeout, proceeding anyway")
                #         if se_logger:
                #             se_logger.log("[L2C TEST] ⚠️ Subscription ready timeout, proceeding anyway")
                #     
                #     # Wait for first result (max 120 seconds)
                #     logger.info(f"[cloud_worker] L2C TEST: Waiting for first PassiveStepResult (max 120s)...")
                #     if se_logger:
                #         se_logger.log("[L2C TEST] 📡 Now listening... Send L2C_WS_Test to continue!")
                #     try:
                #         await asyncio.wait_for(passive_listener.first_result_received.wait(), timeout=120.0)
                #         logger.info(f"[cloud_worker] L2C TEST: First result received, proceeding with skill run")
                #         if se_logger:
                #             se_logger.log("[L2C TEST] ✅ First message received! Proceeding with skill run...")
                #     except asyncio.TimeoutError:
                #         logger.warning("[cloud_worker] L2C TEST: Timeout waiting for first result, proceeding anyway")
                #         if se_logger:
                #             se_logger.log("[L2C TEST] ⏱️ Timeout (120s) waiting for message, proceeding anyway")
            else:
                logger.debug("[cloud_worker] No passive_client_id provided, skipping passive listener")
        
        try:
            # Publish start event
            await _publish_run_status_event(
                bucket=bucket,
                base_prefix=base_prefix,
                region=region,
                run_state=run_state,
                event_type="run_started",
                message=f"Skill '{skill_name}' started",
            )
            
            # Process the skill run
            await handle_skill_run_message(
                msg_data=msg_data,
                run_state=run_state,
                bucket=bucket,
                base_prefix=base_prefix,
                region=region,
            )
            
            # Update state to completed (unless cancelled)
            if run_state.status != "cancelled":
                run_state.status = "completed"
            run_state.completed_at = datetime.now(timezone.utc).isoformat()
            run_state.updated_at = run_state.completed_at
            if username and run_id:
                state_manager.save(run_state)
            
            # Publish completion event
            await _publish_run_status_event(
                bucket=bucket,
                base_prefix=base_prefix,
                region=region,
                run_state=run_state,
                event_type="run_completed" if run_state.status == "completed" else "run_cancelled",
                message=f"Skill '{skill_name}' {run_state.status}",
            )
            
        except Exception as e:
            logger.error("[cloud_worker] skill run failed", exc_info=True)
            
            # Update run state to failed
            run_state.status = "failed"
            run_state.error = str(e)
            run_state.completed_at = datetime.now(timezone.utc).isoformat()
            run_state.updated_at = run_state.completed_at
            if username and run_id:
                try:
                    state_manager.save(run_state)
                except Exception:
                    pass
            
            # Publish failure event
            try:
                await _publish_run_status_event(
                    bucket=bucket,
                    base_prefix=base_prefix,
                    region=region,
                    run_state=run_state,
                    event_type="run_failed",
                    message=f"Skill run failed: {e}",
                )
            except Exception:
                pass
            
            raise
        finally:
            if passive_listener:
                grace_seconds = int(os.getenv("ECAN_PASSIVE_RESULT_GRACE_SECONDS", "300"))
                if grace_seconds > 0 and not passive_listener.first_result_received.is_set():
                    logger.info(
                        f"[cloud_worker] Waiting up to {grace_seconds}s for passive step result before shutdown"
                    )
                    try:
                        await asyncio.wait_for(
                            passive_listener.first_result_received.wait(),
                            timeout=grace_seconds,
                        )
                        logger.info("[cloud_worker] Passive step result received during grace period")
                    except asyncio.TimeoutError:
                        logger.warning("[cloud_worker] Grace period elapsed without passive step result")
            # Stop the passive step result listener
            if passive_listener:
                passive_listener.stop()
            # Clear global passive transport
            clear_global_passive_transport()
            # Stop the control listener
            if control_listener:
                control_listener.stop()
            # Stop the cloud logger
            stop_cloud_logger()
    else:
        # Legacy message format
        await handle_one_message(raw_message=message_json, bucket=bucket, base_prefix=base_prefix, region=region)


async def run_single_with_timeout(*, message_json: str, bucket: str, base_prefix: str, region: str, timeout_seconds: int) -> None:
    """
    Wrapper to run a single skill execution with a timeout.
    If the task exceeds the timeout, it will be forcefully terminated.
    """
    try:
        await asyncio.wait_for(
            run_single(message_json=message_json, bucket=bucket, base_prefix=base_prefix, region=region),
            timeout=timeout_seconds
        )
    except asyncio.TimeoutError:
        logger.error(f"[cloud_worker] Task exceeded timeout of {timeout_seconds}s ({timeout_seconds/3600:.1f} hours), forcing exit")
        raise SystemExit(f"Task timeout after {timeout_seconds}s")


def main() -> None:
    # Default timeout: 3 hours = 10800 seconds
    DEFAULT_TIMEOUT_SECONDS = 10800
    
    parser = argparse.ArgumentParser(prog="ecan-cloud-worker")
    parser.add_argument("--mode", choices=["long-poll", "single"], default=os.getenv("ECAN_WORKER_MODE", "long-poll"))
    parser.add_argument("--queue-url", default=os.getenv("ECAN_SQS_QUEUE_URL", ""))
    parser.add_argument("--message-json", default=os.getenv("ECAN_WORKER_MESSAGE_JSON", ""))
    parser.add_argument("--bucket", default=os.getenv("ECAN_SKILLS_BUCKET", DEFAULT_ECAN_SKILLS_BUCKET))
    parser.add_argument("--base-prefix", default=os.getenv("ECAN_USER_BASE_PREFIX", DEFAULT_USER_BASE_PREFIX))
    parser.add_argument("--region", default=os.getenv("AWS_DEFAULT_REGION", "us-east-1"))
    parser.add_argument("--timeout", type=int, default=int(os.getenv("ECAN_WORKER_TIMEOUT", DEFAULT_TIMEOUT_SECONDS)),
                        help=f"Maximum execution time in seconds (default: {DEFAULT_TIMEOUT_SECONDS}s = 3 hours). Set to 0 to disable timeout.")

    args = parser.parse_args()

    if args.mode == "long-poll" and not args.queue_url:
        raise SystemExit("--queue-url is required for --mode long-poll")
    if args.mode == "single" and not args.message_json:
        raise SystemExit("--message-json is required for --mode single")

    t0 = time.time()
    timeout_info = f"timeout={args.timeout}s" if args.timeout > 0 else "timeout=disabled"
    logger.info(f"[cloud_worker] starting rev={WORKER_REVISION} mode={args.mode} {timeout_info} bucket={args.bucket} region={args.region}")
    try:
        openai_key = (os.getenv("OPENAI_API_KEY") or "").strip()
        if openai_key:
            masked = f"{openai_key[:8]}......{openai_key[-8:]}" if len(openai_key) > 16 else "[masked]"
            logger.info(f"[cloud_worker] OPENAI_API_KEY detected: {masked}")
        else:
            logger.warning("[cloud_worker] OPENAI_API_KEY not set in environment")
    except Exception:
        pass

    try:
        if args.mode == "long-poll":
            asyncio.run(run_long_poll(queue_url=args.queue_url, bucket=args.bucket, base_prefix=args.base_prefix, region=args.region))
        else:
            if args.timeout > 0:
                asyncio.run(run_single_with_timeout(
                    message_json=args.message_json,
                    bucket=args.bucket,
                    base_prefix=args.base_prefix,
                    region=args.region,
                    timeout_seconds=args.timeout
                ))
            else:
                asyncio.run(run_single(message_json=args.message_json, bucket=args.bucket, base_prefix=args.base_prefix, region=args.region))
    finally:
        logger.info(f"[cloud_worker] exiting after {time.time() - t0:.2f}s")


if __name__ == "__main__":
    main()
