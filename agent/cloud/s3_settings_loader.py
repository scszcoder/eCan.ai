import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple


@dataclass(frozen=True)
class AppSyncA2AWorkerConfig:
    endpoints: Dict[str, str]
    auth_headers: Dict[str, str]
    settings: Dict[str, Any]


class S3SettingsLoader:
    def __init__(
        self,
        *,
        bucket: str,
        key: str,
        region: str = "us-east-1",
        ttl_seconds: int = 60,
    ) -> None:
        self.bucket = bucket
        self.key = key
        self.region = region
        self.ttl_seconds = int(ttl_seconds)

        self._client = None
        self._cached_settings: Optional[Dict[str, Any]] = None
        self._cached_at_monotonic: Optional[float] = None
        self._cached_etag: Optional[str] = None
        self._cached_last_modified: Optional[Any] = None

    def invalidate(self) -> None:
        self._cached_settings = None
        self._cached_at_monotonic = None
        self._cached_etag = None
        self._cached_last_modified = None

    def _get_client(self):
        if self._client is not None:
            return self._client

        try:
            import boto3
            from botocore.config import Config
        except Exception as e:
            raise RuntimeError("boto3 is required to load settings from S3") from e

        cfg = Config(region_name=self.region, retries={"max_attempts": 5, "mode": "standard"})
        self._client = boto3.client("s3", config=cfg)
        return self._client

    def _is_cache_valid(self) -> bool:
        if self._cached_settings is None or self._cached_at_monotonic is None:
            return False
        if self.ttl_seconds <= 0:
            return False
        return (time.monotonic() - self._cached_at_monotonic) < float(self.ttl_seconds)

    def load(self, *, force_refresh: bool = False) -> Dict[str, Any]:
        if not force_refresh and self._is_cache_valid():
            return self._cached_settings or {}

        client = self._get_client()

        if self._cached_settings is not None:
            try:
                head = client.head_object(Bucket=self.bucket, Key=self.key)
                etag = head.get("ETag")
                last_modified = head.get("LastModified")
                if (
                    etag
                    and self._cached_etag
                    and str(etag).strip('"') == str(self._cached_etag).strip('"')
                    and last_modified == self._cached_last_modified
                ):
                    self._cached_at_monotonic = time.monotonic()
                    return self._cached_settings
            except Exception:
                pass

        obj = client.get_object(Bucket=self.bucket, Key=self.key)
        body = obj["Body"].read()
        settings = json.loads(body.decode("utf-8"))

        self._cached_settings = settings
        self._cached_at_monotonic = time.monotonic()
        self._cached_etag = (obj.get("ETag") or "").strip('"') or None
        self._cached_last_modified = obj.get("LastModified")

        return settings


def normalize_user_email_for_s3_prefix(user_email: str) -> str:
    safe = (user_email or "").strip().lower()
    safe = safe.replace("@", "_").replace(".", "_")
    return safe


DEFAULT_ECAN_SKILLS_BUCKET = "ecan-skills"
DEFAULT_USER_BASE_PREFIX = "users"


def build_user_root_s3_prefix(*, user_email: str, base_prefix: str = DEFAULT_USER_BASE_PREFIX) -> str:
    safe_user = normalize_user_email_for_s3_prefix(user_email)
    if not safe_user:
        raise ValueError("user_email is required")
    prefix = (base_prefix or "").strip().strip("/")
    if prefix:
        return f"{prefix}/{safe_user}"
    return safe_user


def build_user_settings_s3_key(
    *,
    user_email: str,
    base_prefix: str = "users",
    filename: str = "settings.json",
) -> str:
    root = build_user_root_s3_prefix(user_email=user_email, base_prefix=base_prefix)
    fname = (filename or "settings.json").strip().lstrip("/")
    return f"{root}/{fname}"


def build_user_prompts_s3_prefix(*, user_email: str, base_prefix: str = DEFAULT_USER_BASE_PREFIX) -> str:
    root = build_user_root_s3_prefix(user_email=user_email, base_prefix=base_prefix)
    return f"{root}/prompts"


def build_user_skills_s3_prefix(*, user_email: str, base_prefix: str = DEFAULT_USER_BASE_PREFIX) -> str:
    root = build_user_root_s3_prefix(user_email=user_email, base_prefix=base_prefix)
    return f"{root}/skills"


def build_user_context_s3_prefix(*, user_email: str, base_prefix: str = DEFAULT_USER_BASE_PREFIX) -> str:
    root = build_user_root_s3_prefix(user_email=user_email, base_prefix=base_prefix)
    return f"{root}/context"


def build_appsync_a2a_worker_config(settings: Dict[str, Any]) -> AppSyncA2AWorkerConfig:
    wan_api_key = (settings.get("wan_api_key") or "").strip()
    if not wan_api_key:
        raise ValueError("settings missing required field: wan_api_key")

    http_endpoint = (settings.get("wan_api_endpoint") or "").strip()
    ws_endpoint = (settings.get("ws_api_endpoint") or "").strip()
    host = (settings.get("ws_api_host") or "").strip()

    missing = [k for k, v in [("wan_api_endpoint", http_endpoint), ("ws_api_endpoint", ws_endpoint), ("ws_api_host", host)] if not v]
    if missing:
        raise ValueError(f"settings missing required fields: {', '.join(missing)}")

    endpoints = {"http": http_endpoint, "ws": ws_endpoint, "host": host}
    auth_headers = {"x-api-key": wan_api_key}

    return AppSyncA2AWorkerConfig(endpoints=endpoints, auth_headers=auth_headers, settings=settings)


def load_appsync_a2a_worker_config_from_s3(
    *,
    bucket: str,
    key: str,
    region: str = "us-east-1",
    ttl_seconds: int = 60,
    force_refresh: bool = False,
) -> Tuple[S3SettingsLoader, AppSyncA2AWorkerConfig]:
    loader = S3SettingsLoader(bucket=bucket, key=key, region=region, ttl_seconds=ttl_seconds)
    settings = loader.load(force_refresh=force_refresh)
    return loader, build_appsync_a2a_worker_config(settings)


def load_appsync_a2a_worker_config_from_s3_for_user(
    *,
    bucket: str,
    user_email: str,
    base_prefix: str = "users",
    filename: str = "settings.json",
    region: str = "us-east-1",
    ttl_seconds: int = 60,
    force_refresh: bool = False,
) -> Tuple[S3SettingsLoader, AppSyncA2AWorkerConfig]:
    key = build_user_settings_s3_key(user_email=user_email, base_prefix=base_prefix, filename=filename)
    return load_appsync_a2a_worker_config_from_s3(
        bucket=bucket,
        key=key,
        region=region,
        ttl_seconds=ttl_seconds,
        force_refresh=force_refresh,
    )


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


async def example_headless_worker_a2a_pubsub(
    *,
    user_email: str,
    chat_id: str,
    sender_id: str,
    bucket: str = DEFAULT_ECAN_SKILLS_BUCKET,
    base_prefix: str = DEFAULT_USER_BASE_PREFIX,
    region: str = "us-east-1",
) -> None:
    from a2a.types import Message, TextPart
    from agent.chats.wan_a2a_chat import wan_a2a_send_message, wan_a2a_subscribe

    channel_id = f"chat:{chat_id}"

    loader, cfg = load_appsync_a2a_worker_config_from_s3_for_user(
        bucket=bucket,
        user_email=user_email,
        base_prefix=base_prefix,
        region=region,
        ttl_seconds=60,
    )

    def _on_msg(params, remote_sender_id, remote_channel_id) -> None:
        _ = (params, remote_sender_id, remote_channel_id)
        return

    sub_task = asyncio.create_task(
        wan_a2a_subscribe(
            mainwin=None,
            channel_id=channel_id,
            on_message_callback=_on_msg,
            auth_headers=cfg.auth_headers,
            endpoints=cfg.endpoints,
        )
    )

    msg = Message(role="user", parts=[TextPart(type="text", text="worker online")])
    result = await wan_a2a_send_message(
        mainwin=None,
        channel_id=channel_id,
        message=msg,
        sender_id=sender_id,
        session_id=chat_id,
        recipient_id=None,
        auth_headers=cfg.auth_headers,
        endpoints=cfg.endpoints,
        metadata={"schema_version": 1, "event_type": "skill_run_event", "chat_id": chat_id},
    )

    if _looks_like_auth_error(result):
        loader.invalidate()
        settings = loader.load(force_refresh=True)
        cfg = build_appsync_a2a_worker_config(settings)
        await wan_a2a_send_message(
            mainwin=None,
            channel_id=channel_id,
            message=msg,
            sender_id=sender_id,
            session_id=chat_id,
            recipient_id=None,
            auth_headers=cfg.auth_headers,
            endpoints=cfg.endpoints,
            metadata={"schema_version": 1, "event_type": "skill_run_event", "chat_id": chat_id},
        )

    await asyncio.sleep(0.1)

    if not sub_task.done():
        sub_task.cancel()
