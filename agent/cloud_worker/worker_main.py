import argparse
import asyncio
import json
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

from utils.logger_helper import logger_helper as logger

from agent.cloud.s3_settings_loader import (
    DEFAULT_ECAN_SKILLS_BUCKET,
    DEFAULT_USER_BASE_PREFIX,
    S3SettingsLoader,
    build_user_skills_s3_prefix,
    load_appsync_a2a_worker_config_from_s3_for_user,
    build_appsync_a2a_worker_config,
)


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


def _download_s3_prefix_to_dir(*, bucket: str, prefix: str, dest_dir: Path, region: str) -> None:
    import boto3
    from botocore.config import Config

    client = boto3.client("s3", config=Config(region_name=region, retries={"max_attempts": 5, "mode": "standard"}))

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

        if resp.get("IsTruncated"):
            continuation_token = resp.get("NextContinuationToken")
            continue
        break


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

    task = ManagedTask(name=skill.name or msg.skill_name, description="cloud_worker_run", skill=skill, metadata={})

    state = prep_skills_run(skill, agent, task.id, in_msg, None)
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
        _download_s3_prefix_to_dir(bucket=bucket, prefix=skill_prefix, dest_dir=tmp_dir, region=region)
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

    client = boto3.client("sqs", config=Config(region_name=region, retries={"max_attempts": 5, "mode": "standard"}))

    while True:
        resp = client.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=20,
            VisibilityTimeout=300,
        )

        msgs = resp.get("Messages") or []
        if not msgs:
            continue

        m = msgs[0]
        receipt = m.get("ReceiptHandle")
        body = m.get("Body")

        try:
            await handle_one_message(raw_message=body, bucket=bucket, base_prefix=base_prefix, region=region)
            if receipt:
                client.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt)
        except Exception:
            logger.error("[cloud_worker] message processing failed", exc_info=True)
            try:
                if receipt:
                    client.change_message_visibility(QueueUrl=queue_url, ReceiptHandle=receipt, VisibilityTimeout=0)
            except Exception:
                pass


async def run_single(*, message_json: str, bucket: str, base_prefix: str, region: str) -> None:
    await handle_one_message(raw_message=message_json, bucket=bucket, base_prefix=base_prefix, region=region)


def main() -> None:
    parser = argparse.ArgumentParser(prog="ecan-cloud-worker")
    parser.add_argument("--mode", choices=["long-poll", "single"], default=os.getenv("ECAN_WORKER_MODE", "long-poll"))
    parser.add_argument("--queue-url", default=os.getenv("ECAN_SQS_QUEUE_URL", ""))
    parser.add_argument("--message-json", default=os.getenv("ECAN_WORKER_MESSAGE_JSON", ""))
    parser.add_argument("--bucket", default=os.getenv("ECAN_SKILLS_BUCKET", DEFAULT_ECAN_SKILLS_BUCKET))
    parser.add_argument("--base-prefix", default=os.getenv("ECAN_USER_BASE_PREFIX", DEFAULT_USER_BASE_PREFIX))
    parser.add_argument("--region", default=os.getenv("AWS_DEFAULT_REGION", "us-east-1"))

    args = parser.parse_args()

    if args.mode == "long-poll" and not args.queue_url:
        raise SystemExit("--queue-url is required for --mode long-poll")
    if args.mode == "single" and not args.message_json:
        raise SystemExit("--message-json is required for --mode single")

    t0 = time.time()
    logger.info(f"[cloud_worker] starting mode={args.mode} bucket={args.bucket} region={args.region}")

    try:
        if args.mode == "long-poll":
            asyncio.run(run_long_poll(queue_url=args.queue_url, bucket=args.bucket, base_prefix=args.base_prefix, region=args.region))
        else:
            asyncio.run(run_single(message_json=args.message_json, bucket=args.bucket, base_prefix=args.base_prefix, region=args.region))
    finally:
        logger.info(f"[cloud_worker] exiting after {time.time() - t0:.2f}s")


if __name__ == "__main__":
    main()
