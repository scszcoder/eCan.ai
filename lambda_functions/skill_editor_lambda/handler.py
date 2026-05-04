import io
import json
import logging
import os
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

import boto3

from agent.ec_tasks.appsync_pubsub import AppSyncApiKeyConfig, publish_skill_editor_stream_event
from agent.skill_editor.skill_editor_agent import SkillEditorAgent, _safe_user_dir_name
from agent.skill_editor.token_tracker import token_tracker

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Cache detected S3 base prefixes per owner to avoid repeated list calls within
# the same warm Lambda environment.
_USER_BASE_PREFIX_CACHE: Dict[str, str] = {}
_PUBLIC_SKILLS_PREFIX_CACHE: Optional[str] = None

# =============================================================================
# DEV MODE Constants for Skill Editor Testing
# When dev_mode=True, use deterministic client_id and run_id for predictable
# WebSocket pub/sub matching between cloud worker and local passive agent
# =============================================================================
DEV_MODE_RUN_ID = "test-run-001"
DEV_MODE_DEFAULT_SITE = "SCHOME"


def _generate_dev_mode_client_id(username: str, skill: Dict[str, Any]) -> str:
    """
    Generate client_id for dev mode matching local passive agent's getAcctSiteID().
    
    Format: {user}_{site}
    - user: username with @ and . replaced with _
    - site: from skill's diagram.local_helper_machine, fallback to DEV_MODE_DEFAULT_SITE
    
    This matches the client-side logic:
        def getAcctSiteID(self):
            site = self.machine_name
            user = self.user.replace("@", "_").replace(".", "_")
            return f"{user}_{site}"
    """
    # Normalize username: replace @ and . with _
    user_part = (username or "unknown").replace("@", "_").replace(".", "_")
    
    # Get site from skill's diagram or flowgram settings
    # Priority: diagram.local_helper_machine > skill.local_helper_machine > fallback
    diagram = skill.get("diagram") or {}
    site = (
        diagram.get("local_helper_machine") or 
        skill.get("local_helper_machine") or 
        DEV_MODE_DEFAULT_SITE
    )
    
    client_id = f"{user_part}_{site}"
    return client_id

# Re-use the authoritative baseline mappings from code_agent so that
# scaffold, lazy-create, and code-generation all produce the same defaults.
from agent.skill_editor.code_agent import DEFAULT_BASELINE_MAPPINGS as DEFAULT_DATA_MAPPING


@dataclass(frozen=True)
class _Env:
    s3_bucket: str
    s3_key_root: str
    appsync_api_url: str
    appsync_api_key: str
    # Run control config (optional - may not be set in all environments)
    sqs_queue_url: Optional[str] = None
    ecs_cluster: Optional[str] = None
    ecs_task_definition: Optional[str] = None
    ecs_subnets: Optional[List[str]] = None
    ecs_security_groups: Optional[List[str]] = None
    # SNS topic ARN for Fargate-to-Lambda skill run result notifications.
    # Set SKILL_RUN_RESULT_TOPIC_ARN in Lambda env vars.
    # The Fargate task must publish to this topic on completion (success or failure).
    skill_run_result_topic_arn: Optional[str] = None
    # Aurora Serverless RDS Data API — used by debug workspace for agent_skills queries.
    # Lambda IAM role must have rds-data:ExecuteStatement + secretsmanager:GetSecretValue.
    rds_cluster_arn: Optional[str] = None
    rds_secret_arn: Optional[str] = None
    rds_database: Optional[str] = None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_env(name: str) -> str:
    value = (os.environ.get(name) or "").strip()
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def _mask_secret(value: str, prefix: int = 8, suffix: int = 8) -> str:
    raw = (value or "").strip()
    if len(raw) <= prefix + suffix:
        return raw
    return f"{raw[:prefix]}....{raw[-suffix:]}"


def _load_env() -> _Env:
    # Parse comma-separated lists for ECS networking
    subnets_str = os.environ.get("ECS_SUBNETS", "").strip()
    security_groups_str = os.environ.get("ECS_SECURITY_GROUPS", "").strip()
    
    return _Env(
        s3_bucket=_require_env("S3_BUCKET"),
        s3_key_root=(os.environ.get("S3_KEY_ROOT") or "").strip(),
        appsync_api_url=_require_env("APPSYNC_API_URL"),
        appsync_api_key=_require_env("APPSYNC_API_KEY"),
        # Optional run control config
        sqs_queue_url=os.environ.get("SQS_WORKER_QUEUE_URL", "").strip() or None,
        ecs_cluster=os.environ.get("ECS_CLUSTER", "").strip() or None,
        ecs_task_definition=os.environ.get("ECS_TASK_DEFINITION", "").strip() or None,
        ecs_subnets=[s.strip() for s in subnets_str.split(",") if s.strip()] or None,
        ecs_security_groups=[s.strip() for s in security_groups_str.split(",") if s.strip()] or None,
        skill_run_result_topic_arn=os.environ.get("SKILL_RUN_RESULT_TOPIC_ARN", "").strip() or None,
        rds_cluster_arn=os.environ.get("DBAuroraClusterArn", "").strip() or None,
        rds_secret_arn=os.environ.get("DBSecretsStoreArn", "").strip() or None,
        rds_database=os.environ.get("DatabaseName", "").strip() or None,
    )


def _norm_prefix(prefix: str) -> str:
    p = (prefix or "").strip().strip("/")
    return p


def _s3_key(prefix: str, *parts: str) -> str:
    clean = [p.strip("/") for p in [prefix, *parts] if p and str(p).strip("/")]
    return "/".join(clean)


def _s3_client():
    return boto3.client("s3")


def _s3_exists(*, bucket: str, key: str) -> bool:
    try:
        _s3_client().head_object(Bucket=bucket, Key=key)
        return True
    except Exception:
        return False


def _default_data_mapping_json() -> str:
    return json.dumps(DEFAULT_DATA_MAPPING, ensure_ascii=False, indent=2)


def _s3_get_json(*, bucket: str, key: str) -> Optional[Dict[str, Any]]:
    try:
        resp = _s3_client().get_object(Bucket=bucket, Key=key)
        raw = resp["Body"].read().decode("utf-8")
        return json.loads(raw)
    except _s3_client().exceptions.NoSuchKey:
        return None
    except Exception:
        return None


def _s3_put_json(*, bucket: str, key: str, data: Dict[str, Any]) -> None:
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    _s3_client().put_object(Bucket=bucket, Key=key, Body=body, ContentType="application/json")


def _s3_put_empty(*, bucket: str, key: str) -> None:
    _s3_client().put_object(Bucket=bucket, Key=key, Body=b"", ContentType="application/octet-stream")


def _s3_list_keys(*, bucket: str, prefix: str) -> List[str]:
    client = _s3_client()
    keys: List[str] = []
    continuation: Optional[str] = None
    while True:
        kwargs: Dict[str, Any] = {"Bucket": bucket, "Prefix": prefix}
        if continuation:
            kwargs["ContinuationToken"] = continuation
        resp = client.list_objects_v2(**kwargs)
        for obj in resp.get("Contents") or []:
            k = obj.get("Key")
            if k and not k.endswith("/"):
                keys.append(k)
        if resp.get("IsTruncated"):
            continuation = resp.get("NextContinuationToken")
            continue
        break
    return keys


def _s3_list_objects(*, bucket: str, prefix: str, continuation: Optional[str] = None) -> tuple[List[Dict[str, Any]], Optional[str]]:
    client = _s3_client()
    kwargs: Dict[str, Any] = {"Bucket": bucket, "Prefix": prefix}
    if continuation:
        kwargs["ContinuationToken"] = continuation
    resp = client.list_objects_v2(**kwargs)
    objects: List[Dict[str, Any]] = []
    for obj in resp.get("Contents") or []:
        key = obj.get("Key")
        if key and not key.endswith("/"):
            objects.append(obj)
    next_token = resp.get("NextContinuationToken") if resp.get("IsTruncated") else None
    return objects, next_token


def _s3_prefix_has_any(*, bucket: str, prefix: str) -> bool:
    """Return True if there is at least one object under prefix."""
    p = (prefix or "").strip()
    if not p:
        return False
    try:
        resp = _s3_client().list_objects_v2(Bucket=bucket, Prefix=p, MaxKeys=1)
        return bool(resp.get("Contents"))
    except Exception:
        return False


def _owner_from_event(event: Dict[str, Any]) -> str:
    """
    Extract owner (user identifier) from event.
    Priority:
    1. Explicit userId in arguments (direct or in input wrapper) — skip if placeholder
    2. Email from Cognito claims (preferred for consistent S3 paths)
    3. Cognito username (fallback)
    """
    _PLACEHOLDER_IDS = {"unknown@local", "unknown", ""}
    args = (event.get("arguments") or {})
    
    # Check for userId in input wrapper (mutation pattern - single object)
    if isinstance(args.get("input"), dict):
        user_id = args["input"].get("userId")
        if isinstance(user_id, str) and user_id.strip() and user_id.strip() not in _PLACEHOLDER_IDS:
            return user_id.strip()
    
    # Check for userId in input wrapper (mutation pattern - array of objects)
    if isinstance(args.get("input"), list) and len(args["input"]) > 0:
        first_item = args["input"][0]
        if isinstance(first_item, dict):
            user_id = first_item.get("userId")
            if isinstance(user_id, str) and user_id.strip() and user_id.strip() not in _PLACEHOLDER_IDS:
                return user_id.strip()
    
    # Check for direct userId in arguments (query pattern)
    user_id = args.get("userId")
    if isinstance(user_id, str) and user_id.strip() and user_id.strip() not in _PLACEHOLDER_IDS:
        return user_id.strip()

    ident = event.get("identity") or {}
    
    # Prefer email from claims for consistent S3 paths
    # Email is sanitized by _safe_user_dir_name to become "user_domain_com"
    claims = ident.get("claims") or {}
    if isinstance(claims, dict):
        email = claims.get("email")
        if isinstance(email, str) and email.strip():
            return email.strip()
    
    # Fallback to username/sub
    for key in ("username", "sub"):
        v = ident.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()

    return "unknown@local"


def _session_meta_key(env: _Env, owner: str, session_id: str) -> str:
    prefix = _norm_prefix(env.s3_key_root)
    user_dir = _safe_user_dir_name(owner)
    return _s3_key(prefix, user_dir, "skill_editor_chat", "sessions", f"{session_id}.json")


def _session_history_key(env: _Env, owner: str, session_id: str) -> str:
    prefix = _norm_prefix(env.s3_key_root)
    user_dir = _safe_user_dir_name(owner)
    return _s3_key(prefix, user_dir, "skill_editor_chat", "histories", f"{session_id}.json")


def _safe_skill_dir_name(skill_name: str) -> str:
    name = (skill_name or "").strip() or "untitled_skill"
    return name.replace("/", "_").replace("\\", "_").replace("..", "_").strip() or "untitled_skill"


def _skill_root_prefix(env: _Env, owner: str, skill_name: str) -> str:
    prefix = _norm_prefix(env.s3_key_root)
    user_dir = _safe_user_dir_name(owner)
    safe_skill = _safe_skill_dir_name(skill_name)
    return _s3_key(prefix, user_dir, "my_skills", safe_skill)


def _user_skills_prefix(env: _Env, owner: str) -> str:
    """Return the my_skills directory path for a user."""
    prefix = _norm_prefix(env.s3_key_root)
    user_dir = _safe_user_dir_name(owner)
    return _s3_key(prefix, user_dir, "my_skills")


def _ensure_user_skills_dir(env: _Env, owner: str) -> None:
    """Ensure the user's my_skills directory exists."""
    try:
        base = _user_skills_prefix(env, owner)
        _s3_put_empty(bucket=env.s3_bucket, key=_s3_key(base, ".keep"))
        logger.info(f"[skill] Ensured user skills dir: {base}")
    except Exception as e:
        logger.warning(f"[skill] Failed to ensure user skills dir: {e}")


def _skill_diagram_dir(env: _Env, owner: str, skill_name: str) -> str:
    return _s3_key(_skill_root_prefix(env, owner, skill_name), "diagram_dir")


def _skill_code_dir(env: _Env, owner: str, skill_name: str) -> str:
    return _s3_key(_skill_root_prefix(env, owner, skill_name), "code_dir")


def _skill_data_mapping_key(env: _Env, owner: str, skill_name: str) -> str:
    return _s3_key(_skill_root_prefix(env, owner, skill_name), "data_mapping.json")


def _skill_revisions_prefix(env: _Env, owner: str, skill_name: str) -> str:
    return _s3_key(_skill_root_prefix(env, owner, skill_name), ".revisions")


def _snapshot_skill_before_write(env: _Env, owner: str, resolved_key: str, skill_name: str) -> None:
    """Save a timestamped copy of the current file to .revisions/ before overwriting."""
    try:
        resp = _s3_client().get_object(Bucket=env.s3_bucket, Key=resolved_key)
        body = resp["Body"].read()
    except Exception:
        return  # No existing file to snapshot

    file_name = resolved_key.split("/")[-1]
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    rev_key = _s3_key(
        _skill_revisions_prefix(env, owner, skill_name),
        f"{ts}_{file_name}",
    )
    try:
        _s3_client().put_object(
            Bucket=env.s3_bucket, Key=rev_key, Body=body,
            ContentType="application/json",
        )
        logger.info(f"[revision] Snapshot saved: {rev_key} ({len(body)} bytes)")
    except Exception as e:
        logger.warning(f"[revision] Failed to save snapshot: {e}")

    # Prune revisions older than 7 days (non-fatal, best-effort)
    _prune_old_revisions(env, owner, skill_name, max_age_days=7)


_REVISION_PRUNE_INTERVAL: Dict[str, datetime] = {}  # skill_key → last prune time


def _prune_old_revisions(env: _Env, owner: str, skill_name: str, max_age_days: int = 7) -> None:
    """Delete revision snapshots older than max_age_days. Runs at most once per hour per skill."""
    cache_key = f"{owner}/{skill_name}"
    now = datetime.now(timezone.utc)
    last_prune = _REVISION_PRUNE_INTERVAL.get(cache_key)
    if last_prune and (now - last_prune) < timedelta(hours=1):
        return  # Skip — pruned recently
    _REVISION_PRUNE_INTERVAL[cache_key] = now

    prefix = _skill_revisions_prefix(env, owner, skill_name) + "/"
    cutoff = now - timedelta(days=max_age_days)
    cutoff_str = cutoff.strftime("%Y%m%dT%H%M%SZ")
    client = _s3_client()
    try:
        paginator = client.get_paginator("list_objects_v2")
        to_delete = []
        for page in paginator.paginate(Bucket=env.s3_bucket, Prefix=prefix):
            for obj in page.get("Contents") or []:
                name = obj["Key"].rsplit("/", 1)[-1]
                ts_part = name.split("_", 1)[0] if "_" in name else ""
                if ts_part and ts_part < cutoff_str:
                    to_delete.append({"Key": obj["Key"]})
        if to_delete:
            # S3 delete_objects supports up to 1000 keys per call
            for i in range(0, len(to_delete), 1000):
                client.delete_objects(
                    Bucket=env.s3_bucket,
                    Delete={"Objects": to_delete[i : i + 1000]},
                )
            logger.info(f"[revision] Pruned {len(to_delete)} old revisions for {skill_name}")
    except Exception as e:
        logger.warning(f"[revision] Prune failed: {e}")


def _extract_skill_name_from_key(key: str) -> Optional[str]:
    if not key:
        return None
    parts = key.split("/")
    if "my_skills" in parts:
        idx = parts.index("my_skills")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    return None


def _ensure_skill_dirs(env: _Env, owner: str, skill_name: str) -> None:
    try:
        base = _skill_root_prefix(env, owner, skill_name)
        diagram_dir = _skill_diagram_dir(env, owner, skill_name)
        code_dir = _skill_code_dir(env, owner, skill_name)
        _s3_put_empty(bucket=env.s3_bucket, key=_s3_key(base, ".keep"))
        _s3_put_empty(bucket=env.s3_bucket, key=_s3_key(diagram_dir, ".keep"))
        _s3_put_empty(bucket=env.s3_bucket, key=_s3_key(code_dir, ".keep"))

        mapping_key = _skill_data_mapping_key(env, owner, skill_name)
        if not _s3_exists(bucket=env.s3_bucket, key=mapping_key):
            _s3_client().put_object(
                Bucket=env.s3_bucket,
                Key=mapping_key,
                Body=_default_data_mapping_json().encode("utf-8"),
                ContentType="application/json",
            )
    except Exception as e:
        logger.warning(f"[skill] Failed to ensure skill dirs: {e}")


def _skill_context_base_prefix(env: _Env, owner: str, skill_name: str) -> str:
    prefix = _norm_prefix(env.s3_key_root)
    user_dir = _safe_user_dir_name(owner)
    safe_skill = _safe_skill_dir_name(skill_name)
    return _s3_key(prefix, user_dir, "my_skills", safe_skill, "contexts")


def _skill_context_sessions_prefix(env: _Env, owner: str, skill_name: str) -> str:
    return _s3_key(_skill_context_base_prefix(env, owner, skill_name), "sessions")


def _skill_context_topics_prefix(env: _Env, owner: str, skill_name: str) -> str:
    return _s3_key(_skill_context_base_prefix(env, owner, skill_name), "topics")


def _ensure_context_dirs(env: _Env, owner: str, skill_name: str) -> None:
    base = _skill_context_base_prefix(env, owner, skill_name)
    sessions = _skill_context_sessions_prefix(env, owner, skill_name)
    topics = _skill_context_topics_prefix(env, owner, skill_name)
    try:
        _s3_put_empty(bucket=env.s3_bucket, key=_s3_key(base, ".keep"))
        _s3_put_empty(bucket=env.s3_bucket, key=_s3_key(sessions, ".keep"))
        _s3_put_empty(bucket=env.s3_bucket, key=_s3_key(topics, ".keep"))
    except Exception as e:
        logger.warning(f"[context] Failed to ensure context dirs: {e}")


def _user_base_prefix(env: _Env, owner: str) -> str:
    """Return the effective base prefix for this owner.

    Historically, this project has used multiple S3 layouts:
    - With key root:   {S3_KEY_ROOT}/{userDir}/...
    - Without key root:{userDir}/...

    If S3_KEY_ROOT is set but the rooted layout is empty for this owner,
    auto-fallback to the rootless layout so the Skill Editor can still find
    previously-saved skills.
    """
    prefix_root = _norm_prefix(env.s3_key_root)
    user_dir = _safe_user_dir_name(owner)

    cache_key = f"{env.s3_bucket}:{prefix_root}:{user_dir}"
    cached = _USER_BASE_PREFIX_CACHE.get(cache_key)
    if cached:
        return cached

    base_no_root = _s3_key("", user_dir)
    base_with_root = _s3_key(prefix_root, user_dir) if prefix_root else base_no_root

    selected = base_no_root
    if prefix_root and base_with_root != base_no_root:
        rooted_has = _s3_prefix_has_any(bucket=env.s3_bucket, prefix=base_with_root.rstrip("/") + "/") or _s3_prefix_has_any(
            bucket=env.s3_bucket, prefix=base_with_root
        )
        rootless_has = _s3_prefix_has_any(bucket=env.s3_bucket, prefix=base_no_root.rstrip("/") + "/") or _s3_prefix_has_any(
            bucket=env.s3_bucket, prefix=base_no_root
        )

        if rooted_has:
            selected = base_with_root
        elif rootless_has:
            selected = base_no_root
        else:
            # Default to rooted to preserve configured behavior.
            selected = base_with_root

    _USER_BASE_PREFIX_CACHE[cache_key] = selected
    logger.info(
        f"[s3_prefix] user_base_prefix={selected} root={prefix_root or '(none)'} owner={owner} user_dir={user_dir}"
    )
    return selected


def _public_skills_prefix(env: _Env) -> str:
    global _PUBLIC_SKILLS_PREFIX_CACHE
    if _PUBLIC_SKILLS_PREFIX_CACHE:
        return _PUBLIC_SKILLS_PREFIX_CACHE

    prefix_root = _norm_prefix(env.s3_key_root)
    rooted = f"{prefix_root}/public/skills/" if prefix_root else "public/skills/"
    rootless = "public/skills/"

    selected = rooted
    if prefix_root and rooted != rootless:
        if _s3_prefix_has_any(bucket=env.s3_bucket, prefix=rooted):
            selected = rooted
        elif _s3_prefix_has_any(bucket=env.s3_bucket, prefix=rootless):
            selected = rootless
        else:
            selected = rooted

    _PUBLIC_SKILLS_PREFIX_CACHE = selected
    logger.info(f"[s3_prefix] public_skills_prefix={selected} root={prefix_root or '(none)'}")
    return selected


def _normalize_rel_path(path: str) -> str:
    raw = (path or "").strip().replace("\\", "/")
    raw = raw.lstrip("/")
    parts: List[str] = []
    for part in raw.split("/"):
        if not part or part == ".":
            continue
        if part == "..":
            continue
        parts.append(part)
    return "/".join(parts)


def _allowed_user_bases(env: _Env, owner: str) -> List[str]:
    """Bases we accept for incoming filePath/prefix scope checks."""
    user_dir = _safe_user_dir_name(owner)
    prefix_root = _norm_prefix(env.s3_key_root)
    base_no_root = _s3_key("", user_dir)
    base_with_root = _s3_key(prefix_root, user_dir) if prefix_root else base_no_root
    bases: List[str] = []
    for b in (base_with_root, base_no_root):
        if b and b not in bases:
            bases.append(b)
    return bases


def _resolve_user_key(env: _Env, owner: str, file_path: str) -> str:
    if not file_path or not isinstance(file_path, str):
        raise RuntimeError("filePath is required")

    base = _user_base_prefix(env, owner)
    allowed_bases = _allowed_user_bases(env, owner)
    if file_path.startswith("s3://"):
        without = file_path[len("s3://") :]
        bucket, _, key = without.partition("/")
        if bucket and bucket != env.s3_bucket:
            raise RuntimeError("Invalid bucket for filePath")
        key = _normalize_rel_path(key)
    else:
        key = _normalize_rel_path(file_path)

    # If caller already passed a fully-qualified key under an allowed base,
    # accept it as-is.
    if any(key.startswith(b + "/") or key == b for b in allowed_bases):
        resolved = key
    else:
        resolved = _s3_key(base, key)

    if not any(resolved.startswith(b + "/") or resolved == b for b in allowed_bases):
        raise RuntimeError("Invalid filePath scope")

    return resolved


def _resolve_user_prefix(env: _Env, owner: str, prefix: Optional[str]) -> str:
    base = _user_base_prefix(env, owner)
    allowed_bases = _allowed_user_bases(env, owner)
    if not prefix:
        # Search entire user folder to find skills at any nesting level
        # (skills may be at base/my_skills/ or base/C_/.../my_skills/ due to desktop saves)
        return base

    normalized = _normalize_rel_path(prefix)
    if any(normalized.startswith(b + "/") or normalized == b for b in allowed_bases):
        resolved = normalized
    else:
        resolved = _s3_key(base, normalized)

    if not any(resolved.startswith(b + "/") or resolved == b for b in allowed_bases):
        raise RuntimeError("Invalid prefix scope")

    return resolved


def _infer_skill_name_from_key(key: str) -> Optional[str]:
    if not key:
        return None
    parts = key.split("/")
    if "my_skills" in parts:
        idx = parts.index("my_skills")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    name = parts[-1]
    if name.endswith("_skill.json"):
        return name[: -len("_skill.json")]
    if name.endswith(".json"):
        return name[: -len(".json")]
    return None


def _list_skills_from_prefix(
    bucket: str, 
    prefix: str, 
    limit: Optional[int], 
    continuation: Optional[str],
    items: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Helper to list skill files from a given S3 prefix."""
    while True:
        objects, next_token = _s3_list_objects(bucket=bucket, prefix=prefix, continuation=continuation)
        for obj in objects:
            key = obj.get("Key")
            if not key or key.endswith("/"):
                continue
            if key.endswith(".keep"):
                continue
            if "/contexts/" in key:
                continue
            if "/diagram_dir/" not in key:
                continue
            if key.endswith("data_mapping.json"):
                continue
            if key.endswith("_bundle.json") or key.endswith("_skill_bundle.json"):
                continue
            if not key.endswith(".json"):
                continue

            file_name = key.split("/")[-1]
            skill_name = _infer_skill_name_from_key(key)
            updated_at = obj.get("LastModified")
            if isinstance(updated_at, datetime):
                updated_at = updated_at.replace(tzinfo=timezone.utc).isoformat()
            elif updated_at:
                updated_at = str(updated_at)

            items.append({
                "filePath": key,
                "fileName": file_name,
                "fileSize": obj.get("Size") or 0,
                "skillName": skill_name,
                "updatedAt": updated_at,
            })

            if isinstance(limit, int) and limit > 0 and len(items) >= limit:
                return items

        if not next_token:
            break
        if isinstance(limit, int) and limit > 0 and len(items) >= limit:
            break
        continuation = next_token
    
    return items


def _handle_list_skill_files(event: Dict[str, Any]) -> List[Dict[str, Any]]:
    logger.info("[listSkillFiles] Starting handler")
    # Log the full identity for debugging
    identity = event.get("identity") or {}
    logger.info(f"[listSkillFiles] Identity received: {identity}")
    env = _load_env()
    args = event.get("arguments") or {}
    owner = _owner_from_event(event)
    logger.info(f"[listSkillFiles] Resolved owner: {owner}")

    user_prefix = _resolve_user_prefix(env, owner, args.get("prefix"))
    limit = args.get("limit")
    continuation = args.get("nextToken")
    if user_prefix:
        user_prefix = user_prefix.rstrip("/") + "/"

    items: List[Dict[str, Any]] = []
    
    # First, list user's skills
    logger.info(f"[listSkillFiles] Listing user S3 prefix: {user_prefix}")
    items = _list_skills_from_prefix(env.s3_bucket, user_prefix, limit, continuation, items)
    
    # If we haven't hit the limit yet, also list public skills
    if not args.get("prefix") and (not limit or len(items) < limit):
        public_prefix = _public_skills_prefix(env)
        logger.info(f"[listSkillFiles] Listing public S3 prefix: {public_prefix}")
        remaining_limit = (limit - len(items)) if limit else None
        items = _list_skills_from_prefix(env.s3_bucket, public_prefix, remaining_limit, None, items)

    logger.info(f"[listSkillFiles] Returning {len(items)} items")
    return items


def _handle_read_skill_file(event: Dict[str, Any], *, allow_skill_name: bool) -> List[Dict[str, Any]]:
    env = _load_env()
    args = event.get("arguments") or {}
    owner = _owner_from_event(event)

    file_path = args.get("filePath") or ""
    resolved = _resolve_user_key(env, owner, file_path)

    def _derive_related_paths(key: str) -> List[str]:
        norm = (key or "").replace("\\", "/")
        is_mapping = norm.endswith("/data_mapping.json") or norm.endswith("data_mapping.json")
        is_bundle = norm.endswith("_bundle.json") or norm.endswith("_skill_bundle.json")

        skill_name_local = _extract_skill_name_from_key(norm)
        if not skill_name_local:
            file_name_local = norm.split("/")[-1] if "/" in norm else norm
            skill_name_local = file_name_local.replace(".json", "").replace("_skill", "")

        if "/diagram_dir/" in norm:
            root = norm.split("/diagram_dir/")[0]
        else:
            root = norm.rsplit("/", 1)[0] if "/" in norm else ""

        main_path: Optional[str]
        if is_mapping:
            main_path = f"{root}/diagram_dir/{skill_name_local}_skill.json" if skill_name_local else None
        elif is_bundle:
            main_path = norm.replace("_skill_bundle.json", "_skill.json").replace("_bundle.json", ".json")
        else:
            main_path = norm

        bundle_path: Optional[str]
        if main_path:
            bundle_path = main_path.replace("_skill.json", "_skill_bundle.json")
            if bundle_path == main_path:
                bundle_path = main_path.replace(".json", "_bundle.json")
        else:
            bundle_path = norm if is_bundle else None

        mapping_path = f"{root}/data_mapping.json" if root else "data_mapping.json"

        return [p for p in [main_path, bundle_path, mapping_path] if p]

    logger.info(f"[readSkillFile] Loading file(s): {resolved}")
    client = _s3_client()
    results: List[Dict[str, Any]] = []

    derived_paths = _derive_related_paths(resolved)
    logger.info(f"[readSkillFile] Derived paths: {derived_paths}")

    for path in derived_paths:
        is_mapping = path.endswith("/data_mapping.json") or path.endswith("data_mapping.json")
        is_bundle = path.endswith("_bundle.json") or path.endswith("_skill_bundle.json")

        try:
            resp = client.get_object(Bucket=env.s3_bucket, Key=path)
            content = resp["Body"].read().decode("utf-8")
        except client.exceptions.NoSuchKey:
            if is_mapping:
                logger.info(f"[readSkillFile] data_mapping.json missing, creating default: {path}")
                skill_name = _extract_skill_name_from_key(path)
                if skill_name:
                    _ensure_skill_dirs(env, owner, skill_name)
                content = _default_data_mapping_json()
                client.put_object(
                    Bucket=env.s3_bucket,
                    Key=path,
                    Body=content.encode("utf-8"),
                    ContentType="application/json",
                )
                resp = {"ContentLength": len(content.encode("utf-8"))}
            elif is_bundle:
                logger.info(f"[readSkillFile] Bundle missing, returning empty content: {path}")
                content = ""
                resp = {"ContentLength": 0}
            else:
                raise

        file_name = path.split("/")[-1]
        file_size = resp.get("ContentLength") or len(content)
        if allow_skill_name:
            skill_name = args.get("skillName") or _infer_skill_name_from_key(path)
        else:
            skill_name = _infer_skill_name_from_key(path)

        results.append(
            {
                "content": content,
                "filePath": path,
                "fileName": file_name,
                "fileSize": file_size,
                "skillName": skill_name,
            }
        )

    return results


def _handle_write_skill_file(event: Dict[str, Any]) -> Dict[str, Any]:
    env = _load_env()
    args = event.get("arguments") or {}
    input_ = args.get("input") or {}
    owner = _owner_from_event(event)

    # Ensure user's my_skills directory exists
    _ensure_user_skills_dir(env, owner)

    items = input_ if isinstance(input_, list) else [input_]
    results: List[Dict[str, Any]] = []

    for item in items:
        if not isinstance(item, dict):
            continue
        file_path = item.get("filePath") or ""
        content = item.get("content") or ""
        if not file_path:
            raise RuntimeError("filePath is required")

        resolved = _resolve_user_key(env, owner, file_path)
        skill_name = _extract_skill_name_from_key(resolved)
        if skill_name:
            _ensure_skill_dirs(env, owner, skill_name)
            # Snapshot current file before overwriting (non-fatal)
            if "/diagram_dir/" in resolved or resolved.endswith("data_mapping.json"):
                _snapshot_skill_before_write(env, owner, resolved, skill_name)

        logger.info(f"[writeSkillFile] Saving file: {resolved}")
        _s3_client().put_object(
            Bucket=env.s3_bucket,
            Key=resolved,
            Body=content.encode("utf-8"),
            ContentType="application/json",
        )

        file_name = resolved.split("/")[-1]
        results.append({
            "filePath": resolved,
            "fileName": file_name,
            "fileSize": len(content.encode("utf-8")),
            "success": True,
            "skillName": skill_name,
        })

    return results


# ---------------------------------------------------------------------------
# Skill Revision History
# ---------------------------------------------------------------------------

def _handle_list_skill_revisions(event: Dict[str, Any]) -> List[Dict[str, Any]]:
    """List available revision snapshots for a skill."""
    env = _load_env()
    args = event.get("arguments") or {}
    input_ = args.get("input") or {}
    owner = _owner_from_event(event)
    skill_name = input_.get("skillName") or ""
    if not skill_name:
        raise ValueError("skillName is required")

    prefix = _skill_revisions_prefix(env, owner, skill_name) + "/"
    client = _s3_client()
    revisions: List[Dict[str, Any]] = []
    paginator = client.get_paginator("list_objects_v2")

    for page in paginator.paginate(Bucket=env.s3_bucket, Prefix=prefix):
        for obj in page.get("Contents") or []:
            key = obj["Key"]
            name = key.rsplit("/", 1)[-1]
            # name format: 20260312T153045Z_my_skill_skill.json
            ts_str = name.split("_", 1)[0] if "_" in name else ""
            revisions.append({
                "key": key,
                "fileName": name,
                "timestamp": ts_str,
                "size": obj.get("Size", 0),
                "lastModified": obj.get("LastModified", "").isoformat() if obj.get("LastModified") else "",
            })

    revisions.sort(key=lambda r: r["timestamp"], reverse=True)
    logger.info(f"[revision] Listed {len(revisions)} revisions for skill={skill_name}")
    return revisions


def _handle_revert_skill_revision(event: Dict[str, Any]) -> Dict[str, Any]:
    """Revert a skill file to a specific revision snapshot."""
    env = _load_env()
    args = event.get("arguments") or {}
    input_ = args.get("input") or {}
    owner = _owner_from_event(event)
    skill_name = input_.get("skillName") or ""
    revision_key = input_.get("revisionKey") or ""
    if not skill_name or not revision_key:
        raise ValueError("skillName and revisionKey are required")

    # Validate revision key belongs to this user's skill
    expected_prefix = _skill_revisions_prefix(env, owner, skill_name) + "/"
    if not revision_key.startswith(expected_prefix):
        raise RuntimeError("Invalid revisionKey")

    # Read the revision
    try:
        resp = _s3_client().get_object(Bucket=env.s3_bucket, Key=revision_key)
        body = resp["Body"].read()
    except Exception as e:
        raise RuntimeError(f"Revision not found: {e}")

    # Determine the original file name from revision key
    # revision name: 20260312T153045Z_my_skill_skill.json
    rev_name = revision_key.rsplit("/", 1)[-1]
    # Strip timestamp prefix (everything up to first _)
    original_name = rev_name.split("_", 1)[1] if "_" in rev_name else rev_name

    # Route to correct location based on file name
    if original_name == "data_mapping.json":
        target_key = _skill_data_mapping_key(env, owner, skill_name)
    else:
        target_key = _s3_key(_skill_diagram_dir(env, owner, skill_name), original_name)

    # Snapshot current before reverting
    _snapshot_skill_before_write(env, owner, target_key, skill_name)

    # Write the revision content to the target
    _s3_client().put_object(
        Bucket=env.s3_bucket, Key=target_key, Body=body,
        ContentType="application/json",
    )
    logger.info(f"[revision] Reverted {target_key} from {revision_key} ({len(body)} bytes)")

    return {
        "success": True,
        "restoredFrom": revision_key,
        "restoredTo": target_key,
        "size": len(body),
    }


def _parse_iso(ts: Optional[str]) -> Optional[datetime]:
    if not ts or not isinstance(ts, str):
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def _session_filename(dt: datetime) -> str:
    return f"session_{dt.strftime('%Y%m%dT%H%M%SZ')}.json"


def _parse_session_filename(name: str) -> Optional[datetime]:
    try:
        if not name.startswith("session_") or not name.endswith(".json"):
            return None
        stamp = name[len("session_") : -len(".json")]
        return datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _list_context_session_keys(env: _Env, owner: str, skill_name: str) -> List[str]:
    prefix = _skill_context_sessions_prefix(env, owner, skill_name)
    if prefix:
        prefix += "/"
    return _s3_list_keys(bucket=env.s3_bucket, prefix=prefix)


def _load_context_session(env: _Env, key: str) -> Optional[Dict[str, Any]]:
    return _s3_get_json(bucket=env.s3_bucket, key=key)


def _pick_latest_session_key(keys: List[str]) -> Optional[str]:
    dated: List[tuple[datetime, str]] = []
    for key in keys:
        name = key.split("/")[-1]
        dt = _parse_session_filename(name)
        if dt:
            dated.append((dt, key))
    if not dated:
        return None
    dated.sort(key=lambda x: x[0])
    return dated[-1][1]


def _get_or_create_context_session(
    env: _Env,
    owner: str,
    skill_name: str,
    now_dt: datetime,
) -> tuple[str, Dict[str, Any]]:
    _ensure_context_dirs(env, owner, skill_name)
    keys = _list_context_session_keys(env, owner, skill_name)
    latest_key = _pick_latest_session_key(keys)
    if latest_key:
        session_doc = _load_context_session(env, latest_key) or {}
        messages = session_doc.get("messages") if isinstance(session_doc.get("messages"), list) else []
        last_ts = None
        if messages:
            last_ts = _parse_iso(messages[-1].get("timestamp"))
        if not last_ts:
            last_ts = _parse_iso(session_doc.get("updatedAt")) or _parse_iso(session_doc.get("startedAt"))
        if last_ts and now_dt - last_ts <= timedelta(hours=6):
            return latest_key, session_doc

    session_doc = {
        "sessionId": str(uuid4()),
        "skillName": skill_name,
        "startedAt": now_dt.isoformat(),
        "updatedAt": now_dt.isoformat(),
        "messages": [],
    }
    key = _s3_key(_skill_context_sessions_prefix(env, owner, skill_name), _session_filename(now_dt))
    return key, session_doc


def _append_context_messages(
    env: _Env,
    owner: str,
    skill_name: str,
    messages: List[Dict[str, Any]],
) -> None:
    if not messages:
        return
    now_dt = datetime.now(timezone.utc)
    key, session_doc = _get_or_create_context_session(env, owner, skill_name, now_dt)
    session_doc.setdefault("messages", [])
    if isinstance(session_doc["messages"], list):
        session_doc["messages"].extend(messages)
    session_doc["updatedAt"] = now_dt.isoformat()
    _s3_put_json(bucket=env.s3_bucket, key=key, data=session_doc)


def _load_recent_context_sessions(
    env: _Env,
    owner: str,
    skill_name: str,
    limit: int = 3,
) -> List[Dict[str, Any]]:
    _ensure_context_dirs(env, owner, skill_name)
    keys = _list_context_session_keys(env, owner, skill_name)
    dated: List[tuple[datetime, str]] = []
    for key in keys:
        dt = _parse_session_filename(key.split("/")[-1])
        if dt:
            dated.append((dt, key))
    dated.sort(key=lambda x: x[0], reverse=True)
    sessions: List[Dict[str, Any]] = []
    for _, key in dated[: max(limit, 0)]:
        doc = _load_context_session(env, key)
        if isinstance(doc, dict):
            sessions.append(doc)
    return sessions


def _load_session(env: _Env, owner: str, session_id: str) -> Optional[Dict[str, Any]]:
    return _s3_get_json(bucket=env.s3_bucket, key=_session_meta_key(env, owner, session_id))


def _save_session(env: _Env, owner: str, session: Dict[str, Any]) -> None:
    _s3_put_json(bucket=env.s3_bucket, key=_session_meta_key(env, owner, str(session.get("id"))), data=session)


def _load_history(env: _Env, owner: str, session_id: str) -> Dict[str, Any]:
    return _s3_get_json(bucket=env.s3_bucket, key=_session_history_key(env, owner, session_id)) or {
        "sessionId": session_id,
        "messages": [],
    }


def _save_history(env: _Env, owner: str, session_id: str, history: Dict[str, Any]) -> None:
    _s3_put_json(bucket=env.s3_bucket, key=_session_history_key(env, owner, session_id), data=history)


def _mk_appsync_cfg(env: _Env) -> AppSyncApiKeyConfig:
    return AppSyncApiKeyConfig(http_endpoint=env.appsync_api_url, api_key=env.appsync_api_key)


def _publish(env: _Env, *, owner: str, session_id: str, flowgram_id: Optional[str], event_type: str, payload: Any) -> None:
    cfg = _mk_appsync_cfg(env)

    import asyncio

    async def _do():
        await publish_skill_editor_stream_event(
            config=cfg,
            owner=owner,
            session_id=session_id,
            flowgram_id=flowgram_id,
            event_type=event_type,
            payload=payload,
        )

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Use a dedicated thread to avoid importing heavy agent modules
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, _do())
                future.result(timeout=10)
        else:
            loop.run_until_complete(_do())
    except RuntimeError:
        asyncio.run(_do())


def _to_session_gql(session: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": session["id"],
        "name": session.get("name") or "New Chat",
        "flowgramId": session.get("flowgramId"),
        "createdAt": session.get("createdAt") or _utc_now_iso(),
        "updatedAt": session.get("updatedAt") or session.get("createdAt") or _utc_now_iso(),
    }


def _to_message_gql(msg: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": msg["id"],
        "role": msg.get("role") or "assistant",
        "content": msg.get("content") or "",
        "timestamp": msg.get("timestamp") or _utc_now_iso(),
        "attachments": msg.get("attachments"),
        "metadata": msg.get("metadata"),
    }


def _handle_create_session(event: Dict[str, Any]) -> Dict[str, Any]:
    logger.info("[createSkillEditorChatSession] Starting handler")
    env = _load_env()
    args = event.get("arguments") or {}
    input_ = args.get("input") or {}

    owner = _owner_from_event(event)
    session_id = str(uuid4())
    now = _utc_now_iso()

    logger.info(f"[createSkillEditorChatSession] owner={owner}, session_id={session_id}, name={input_.get('name')}")

    session = {
        "id": session_id,
        "name": (input_.get("name") or "New Chat"),
        "flowgramId": input_.get("flowgramId"),
        "createdAt": now,
        "updatedAt": now,
        "pipelineState": "idle",
        "currentPlan": None,
        "currentRequest": None,
    }

    _save_session(env, owner, session)
    _save_history(env, owner, session_id, {"sessionId": session_id, "messages": []})

    logger.info(f"[createSkillEditorChatSession] Session created successfully: {session_id}")
    return _to_session_gql(session)


def _handle_get_sessions(event: Dict[str, Any]) -> List[Dict[str, Any]]:
    logger.info("[getSkillEditorChatSessions] Starting handler")
    env = _load_env()
    args = event.get("arguments") or {}
    owner = (args.get("userId") or _owner_from_event(event) or "").strip() or _owner_from_event(event)

    logger.info(f"[getSkillEditorChatSessions] owner={owner}")

    prefix = _norm_prefix(env.s3_key_root)
    user_dir = _safe_user_dir_name(owner)
    sessions_prefix = _s3_key(prefix, user_dir, "skill_editor_chat", "sessions")
    if sessions_prefix:
        sessions_prefix += "/"

    logger.info(f"[getSkillEditorChatSessions] Listing S3 prefix: {sessions_prefix}")
    keys = _s3_list_keys(bucket=env.s3_bucket, prefix=sessions_prefix)
    logger.info(f"[getSkillEditorChatSessions] Found {len(keys)} session keys")

    sessions: List[Dict[str, Any]] = []
    for k in keys:
        doc = _s3_get_json(bucket=env.s3_bucket, key=k)
        if isinstance(doc, dict) and doc.get("id"):
            sessions.append(doc)

    sessions.sort(key=lambda s: (s.get("updatedAt") or ""), reverse=True)
    logger.info(f"[getSkillEditorChatSessions] Returning {len(sessions)} sessions")
    return [_to_session_gql(s) for s in sessions]


def _handle_get_history(event: Dict[str, Any]) -> List[Dict[str, Any]]:
    logger.info("[getSkillEditorChatHistory] Starting handler")
    env = _load_env()
    args = event.get("arguments") or {}
    session_id = str(args.get("sessionId") or "")
    owner = _owner_from_event(event)

    logger.info(f"[getSkillEditorChatHistory] owner={owner}, session_id={session_id}")

    limit = args.get("limit")
    offset = int(args.get("offset") or 0)

    history = _load_history(env, owner, session_id)
    messages = history.get("messages") or []
    if not isinstance(messages, list):
        messages = []

    logger.info(f"[getSkillEditorChatHistory] Found {len(messages)} messages, offset={offset}, limit={limit}")

    sliced = messages[offset:]
    if isinstance(limit, int) and limit > 0:
        sliced = sliced[:limit]

    logger.info(f"[getSkillEditorChatHistory] Returning {len(sliced)} messages")
    return [_to_message_gql(m) for m in sliced if isinstance(m, dict) and m.get("id")]


def _handle_delete_session(event: Dict[str, Any]) -> bool:
    logger.info("[deleteSkillEditorChatSession] Starting handler")
    env = _load_env()
    args = event.get("arguments") or {}
    session_id = str(args.get("sessionId") or "")
    owner = _owner_from_event(event)

    logger.info(f"[deleteSkillEditorChatSession] owner={owner}, session_id={session_id}")

    if not session_id:
        logger.warning("[deleteSkillEditorChatSession] No session_id provided")
        return False

    client = _s3_client()
    deleted_any = False
    for key in (
        _session_meta_key(env, owner, session_id),
        _session_history_key(env, owner, session_id),
    ):
        try:
            client.delete_object(Bucket=env.s3_bucket, Key=key)
            logger.info(f"[deleteSkillEditorChatSession] Deleted S3 key: {key}")
            deleted_any = True
        except Exception as e:
            logger.warning(f"[deleteSkillEditorChatSession] Failed to delete {key}: {e}")
            continue

    logger.info(f"[deleteSkillEditorChatSession] Completed, deleted_any={deleted_any}")
    return deleted_any


def _handle_cancel_generation(event: Dict[str, Any]) -> bool:
    logger.info("[cancelSkillEditorChatGeneration] Starting handler")
    # Best-effort only in Lambda: we cannot cancel an in-flight invocation.
    # Return true so UI can stop waiting / reset local streaming state.
    _ = event
    logger.info("[cancelSkillEditorChatGeneration] Returning True (best-effort)")
    return True


# =============================================================================
# Skill Run Control Handlers
# =============================================================================

def _sqs_client():
    return boto3.client("sqs")


def _ecs_client():
    return boto3.client("ecs")


def _get_run_state_key(env: _Env, username: str, run_id: str) -> str:
    """S3 key for storing run state metadata."""
    safe_user = _safe_user_dir_name(username)
    prefix = _norm_prefix(env.s3_key_root)
    return _s3_key(prefix, "users", safe_user, "runs", f"{run_id}.json")


def _save_run_state(env: _Env, username: str, run_state: Dict[str, Any]) -> None:
    """Save run state to S3."""
    run_id = run_state.get("run_id")
    if not run_id:
        raise ValueError("run_state must have run_id")
    key = _get_run_state_key(env, username, run_id)
    _s3_client().put_object(
        Bucket=env.s3_bucket,
        Key=key,
        Body=json.dumps(run_state, ensure_ascii=False, indent=2),
        ContentType="application/json",
    )
    logger.info(f"[_save_run_state] Saved run state: {key}")


def _load_run_state(env: _Env, username: str, run_id: str) -> Optional[Dict[str, Any]]:
    """Load run state from S3."""
    key = _get_run_state_key(env, username, run_id)
    return _s3_get_json(bucket=env.s3_bucket, key=key)


def _find_active_run_by_skill(env: _Env, username: str, skill_id: str) -> Optional[Dict[str, Any]]:
    """Find the most recent active run for a skill (queued or running)."""
    safe_user = _safe_user_dir_name(username)
    prefix = _norm_prefix(env.s3_key_root)
    runs_prefix = _s3_key(prefix, "users", safe_user, "runs") + "/"
    
    try:
        client = _s3_client()
        response = client.list_objects_v2(Bucket=env.s3_bucket, Prefix=runs_prefix)
        
        active_runs = []
        for obj in response.get("Contents", []):
            try:
                run_data = _s3_get_json(bucket=env.s3_bucket, key=obj["Key"])
                if run_data and run_data.get("skill_id") == skill_id:
                    status = run_data.get("status")
                    if status in ("queued", "running"):
                        active_runs.append(run_data)
            except Exception as e:
                logger.warning(f"[_find_active_run_by_skill] Error reading {obj['Key']}: {e}")
                continue
        
        # Return most recent by created_at
        if active_runs:
            active_runs.sort(key=lambda r: r.get("created_at", ""), reverse=True)
            return active_runs[0]
        return None
    except Exception as e:
        logger.error(f"[_find_active_run_by_skill] Error listing runs: {e}")
        return None


def _handle_run_skill(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle runSkill mutation.
    
    Starts a Fargate task to execute the skill. The task runs asynchronously
    and reports progress via AppSync subscriptions.
    
    Input (RunSkillInput):
        username: String
        skill: AWSJSON! containing:
            - skill_id: string
            - skill_name: string
            - skill_run_mode: string (local/cloud/hybrid)
            - diagram: object (the workflow definition)
            - testInputs: object (optional test inputs)
    
    Returns:
        RunControlResult: { runId, status, message, data }
    """
    logger.info("[runSkill] Starting handler")
    env = _load_env()
    
    args = event.get("arguments") or {}
    input_data = args.get("input") or {}
    username = input_data.get("username") or _owner_from_event(event)
    skill_json = input_data.get("skill")
    
    # Parse skill if it's a string
    if isinstance(skill_json, str):
        try:
            skill = json.loads(skill_json)
        except json.JSONDecodeError as e:
            logger.error(f"[runSkill] Failed to parse skill JSON: {e}")
            return {
                "runId": None,
                "status": "error",
                "message": f"Invalid skill JSON: {e}",
                "data": None,
            }
    else:
        skill = skill_json or {}
    
    # Parse meta_data if provided
    meta_data_json = input_data.get("meta_data")
    if isinstance(meta_data_json, str):
        try:
            meta_data = json.loads(meta_data_json)
        except json.JSONDecodeError:
            meta_data = {}
    else:
        meta_data = meta_data_json or {}
    
    # Extract run_in_cloud flag and optional client_id/run_id from meta_data
    # For hybrid workflow:
    # - client_id: identifies the local passive agent (same as agent_id on client)
    # - run_id: unique ID for this run session (generated on client side)
    meta_run_in_cloud = meta_data.get("run_in_cloud", False)
    meta_client_id = meta_data.get("client_id")  # From local client for hybrid mode
    meta_run_id = meta_data.get("run_id")  # From local client for hybrid mode
    meta_jwt = meta_data.get("jwt") or meta_data.get("token")
    passive_run_id = (
        meta_run_id
        or input_data.get("sessionId")
        or input_data.get("chatId")
        or input_data.get("session_id")
        or input_data.get("chat_id")
    )
    
    skill_id = skill.get("skill_id") or str(uuid4())
    skill_name = skill.get("skill_name") or "unnamed_skill"
    skill_run_mode = skill.get("skill_run_mode") or "cloud"
    # Dev mode enables breakpoint/step support in cloud worker
    # Check input_data, skill, and meta_data (frontend sends dev_mode in meta_data)
    dev_mode = input_data.get("dev_mode", False) or skill.get("dev_mode", False) or meta_data.get("dev_mode", False)
    
    logger.info(f"[runSkill] username={username}, skill_id={skill_id}, skill_name={skill_name}, mode={skill_run_mode}, dev_mode={dev_mode}")
    logger.info(f"[runSkill] meta_data: run_in_cloud={meta_run_in_cloud}, client_id={meta_client_id}, run_id={meta_run_id}")
    logger.info(f"[runSkill] meta_jwt present: {bool(meta_jwt)}, meta_data keys: {list(meta_data.keys())}")
    
    # Validate environment for cloud runs
    if skill_run_mode in ("cloud", "hybrid"):
        if not env.ecs_cluster or not env.ecs_task_definition:
            logger.error("[runSkill] ECS_CLUSTER or ECS_TASK_DEFINITION not configured")
            return {
                "runId": None,
                "status": "error",
                "message": "Cloud worker not configured (missing ECS settings)",
                "data": None,
            }
        if not env.ecs_subnets:
            logger.error("[runSkill] ECS_SUBNETS not configured")
            return {
                "runId": None,
                "status": "error",
                "message": "Cloud worker not configured (missing network settings)",
                "data": None,
            }
    
    # Generate run ID
    # Priority: 1) meta_data.run_id (from local client), 2) dev_mode deterministic, 3) random UUID
    if meta_run_id:
        run_id = meta_run_id
        logger.info(f"[runSkill] Using run_id from meta_data: {run_id}")
    elif dev_mode:
        run_id = DEV_MODE_RUN_ID
        logger.info(f"[runSkill] dev_mode enabled - using deterministic run_id={run_id}")
    else:
        run_id = str(uuid4())
        logger.info(f"[runSkill] Generated random run_id: {run_id}")
    created_at = _utc_now_iso()
    
    # Generate passive_client_id early so it can be included in payloads
    # Priority: 1) meta_data.client_id (from local client), 2) dev_mode deterministic, 3) skill.passive_client_id, 4) auto-generated
    if meta_client_id:
        passive_client_id = meta_client_id
        logger.info(f"[runSkill] Using client_id from meta_data: {passive_client_id}")
    elif dev_mode:
        # In dev mode, generate client_id matching local passive agent's getAcctSiteID()
        passive_client_id = _generate_dev_mode_client_id(username, skill)
        logger.info(f"[runSkill] dev_mode enabled - using deterministic passive_client_id={passive_client_id}")
    else:
        passive_client_id = skill.get("passive_client_id") or f"cloud-worker-{run_id}"
        logger.info(f"[runSkill] Using passive_client_id: {passive_client_id}")
    
    # Create the skill run payload
    run_payload = {
        "run_id": run_id,
        "passive_run_id": passive_run_id,
        "username": username,
        "skill_id": skill_id,
        "skill_name": skill_name,
        "skill_run_mode": skill_run_mode,
        "dev_mode": dev_mode,  # Enable breakpoint/step support in worker
        "skill": skill,  # Full skill payload including diagram
        "passive_client_id": passive_client_id,  # For hybrid cloud browser automation
        "created_at": created_at,
    }
    
    # Save the run payload to S3 (to avoid ECS container override 8KB limit)
    # The worker will fetch this from S3 using the reference
    user_dir = _safe_user_dir_name(username)
    payload_s3_key = _s3_key(_norm_prefix(env.s3_key_root), user_dir, "run_payloads", f"{run_id}.json")
    try:
        _s3_put_json(bucket=env.s3_bucket, key=payload_s3_key, data=run_payload)
        logger.info(f"[runSkill] Saved run payload to S3: s3://{env.s3_bucket}/{payload_s3_key}")
    except Exception as e:
        logger.error(f"[runSkill] Failed to save run payload to S3: {e}")
        return {
            "runId": run_id,
            "status": "error",
            "message": f"Failed to save run payload: {e}",
            "data": None,
        }
    
    # Create a small reference payload for the container override
    # This stays well under the 8KB limit
    ref_payload = {
        "run_id": run_id,
        "passive_run_id": passive_run_id,
        "passive_jwt": meta_jwt,
        "username": username,
        "skill_id": skill_id,
        "skill_name": skill_name,
        "payload_s3_bucket": env.s3_bucket,
        "payload_s3_key": payload_s3_key,
        "passive_client_id": passive_client_id,  # For hybrid cloud browser automation
        "created_at": created_at,
    }
    
    # Start Fargate task
    ecs_task_arn = None
    try:
        ecs = _ecs_client()
        
        # Build base container environment variables
        # passive_client_id was already determined earlier
        container_env = [
            {"name": "ECAN_WORKER_MODE", "value": "single"},
            {"name": "ECAN_WORKER_MESSAGE_JSON", "value": json.dumps(ref_payload, ensure_ascii=False)},
            {"name": "ECAN_RUN_ID", "value": run_id},
            {"name": "ECAN_USERNAME", "value": username},
            # Pass AppSync config for real-time status updates (cloud_logger)
            {"name": "APPSYNC_API_URL", "value": env.appsync_api_url},
            {"name": "APPSYNC_API_KEY", "value": env.appsync_api_key},
            # Always provide browser passive transport config for cloud runs
            # Individual browser automation nodes may be configured for hybrid_cloud mode
            # which requires these to communicate with local PassiveAgent
            {"name": "EC_BROWSER_PASSIVE_TRANSPORT", "value": "appsync"},
            {"name": "EC_APPSYNC_HTTP_ENDPOINT", "value": env.appsync_api_url},
            {"name": "EC_APPSYNC_TOKEN", "value": meta_jwt or env.appsync_api_key},
            {"name": "EC_BROWSER_PASSIVE_CLIENT_ID", "value": passive_client_id},
        ]
        openai_api_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
        if openai_api_key:
            masked_key = _mask_secret(openai_api_key)
            logger.info(f"[runSkill] OPENAI_API_KEY detected for ECS: {masked_key}")
            container_env.append({"name": "OPENAI_API_KEY", "value": openai_api_key})
        else:
            logger.warning("[runSkill] OPENAI_API_KEY not set in Lambda env; cloud worker may fail LLM calls")
        if meta_jwt:
            container_env.append({"name": "APPSYNC_AUTH_TOKEN", "value": meta_jwt})

        grace_seconds = (os.environ.get("ECAN_PASSIVE_RESULT_GRACE_SECONDS") or "").strip()
        if grace_seconds:
            container_env.append({"name": "ECAN_PASSIVE_RESULT_GRACE_SECONDS", "value": grace_seconds})
        
        logger.info(f"[runSkill] Cloud run with passive_client_id={passive_client_id} for hybrid node support")
        
        # Build container overrides with reference to S3 payload
        container_overrides = {
            "name": "ecan-cloud-worker",  # Must match container name in task def
            "environment": container_env,
        }
        
        # Build network configuration
        network_config = {
            "awsvpcConfiguration": {
                "subnets": env.ecs_subnets,
                "assignPublicIp": "ENABLED",  # Required for pulling images from ECR
            }
        }
        if env.ecs_security_groups:
            network_config["awsvpcConfiguration"]["securityGroups"] = env.ecs_security_groups
        
        # Start the task (async - returns immediately)
        response = ecs.run_task(
            cluster=env.ecs_cluster,
            taskDefinition=env.ecs_task_definition,
            launchType="FARGATE",
            networkConfiguration=network_config,
            overrides={
                "containerOverrides": [container_overrides],
            },
            tags=[
                {"key": "run_id", "value": run_id},
                {"key": "username", "value": username},
                {"key": "skill_name", "value": skill_name[:128]},  # Tag value max 256 chars
            ],
        )
        
        # Get task ARN from response
        tasks = response.get("tasks") or []
        if tasks:
            ecs_task_arn = tasks[0].get("taskArn")
            logger.info(f"[runSkill] Fargate task started: {ecs_task_arn}")
        else:
            failures = response.get("failures") or []
            failure_reason = failures[0].get("reason") if failures else "Unknown"
            logger.error(f"[runSkill] Failed to start Fargate task: {failure_reason}")
            return {
                "runId": run_id,
                "status": "error",
                "message": f"Failed to start cloud worker: {failure_reason}",
                "data": None,
            }
            
    except Exception as e:
        logger.error(f"[runSkill] Failed to start Fargate task: {e}")
        return {
            "runId": run_id,
            "status": "error",
            "message": f"Failed to start cloud worker: {e}",
            "data": None,
        }
    
    # Save run state to S3 for tracking
    run_state = {
        "run_id": run_id,
        "username": username,
        "skill_id": skill_id,
        "skill_name": skill_name,
        "status": "starting",
        "ecs_task_arn": ecs_task_arn,
        "created_at": created_at,
        "updated_at": created_at,
        "started_at": created_at,
        "completed_at": None,
        "error": None,
    }
    
    try:
        _save_run_state(env, username, run_state)
    except Exception as e:
        logger.warning(f"[runSkill] Failed to save run state (non-fatal): {e}")
    
    logger.info(f"[runSkill] Skill run started successfully: run_id={run_id}, task_arn={ecs_task_arn}")
    
    # Build response data with task ARN and passive client info for hybrid node support
    response_data = {
        "ecs_task_arn": ecs_task_arn,
        "passive_client_id": passive_client_id,  # For hybrid nodes that need local PassiveAgent
    }
    
    return {
        "runId": run_id,
        "status": "starting",
        "message": f"Skill '{skill_name}' starting on cloud worker",
        "data": json.dumps(response_data),
    }


def _handle_cancel_run_skill(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle cancelRunSkill mutation.
    
    Cancels a skill run:
    1. If queued: attempts to delete from SQS (best effort - message may have been consumed)
    2. If running: stops the ECS Fargate task
    
    Input (RunControlInput):
        username: String
        skill: AWSJSON containing:
            - skill_id: string (to find the active run)
            - run_id: string (optional, if known)
    
    Returns:
        RunControlResult: { runId, status, message, data }
    """
    logger.info("[cancelRunSkill] Starting handler")
    env = _load_env()
    
    args = event.get("arguments") or {}
    input_data = args.get("input") or {}
    username = input_data.get("username") or _owner_from_event(event)
    skill_json = input_data.get("skill")
    
    # Parse skill if it's a string
    if isinstance(skill_json, str):
        try:
            skill = json.loads(skill_json)
        except json.JSONDecodeError:
            skill = {}
    else:
        skill = skill_json or {}
    
    run_id = skill.get("run_id")
    # Support both snake_case (backend) and camelCase (frontend) key names
    skill_id = skill.get("skill_id") or skill.get("skillId")
    
    logger.info(f"[cancelRunSkill] username={username}, run_id={run_id}, skill_id={skill_id}")
    
    # Find the run to cancel
    run_state = None
    if run_id:
        run_state = _load_run_state(env, username, run_id)
    elif skill_id:
        run_state = _find_active_run_by_skill(env, username, skill_id)
    
    if not run_state:
        logger.warning("[cancelRunSkill] No active run found to cancel")
        return {
            "runId": run_id,
            "status": "not_found",
            "message": "No active run found to cancel",
            "data": None,
        }
    
    run_id = run_state.get("run_id")
    status = run_state.get("status")
    
    logger.info(f"[cancelRunSkill] Found run: run_id={run_id}, status={status}")
    
    # Already terminal state
    if status in ("completed", "failed", "cancelled"):
        return {
            "runId": run_id,
            "status": status,
            "message": f"Run already in terminal state: {status}",
            "data": None,
        }
    
    cancelled = False
    cancel_message = ""
    
    # Case 1: Queued - try to remove from SQS
    if status == "queued":
        # Note: We can't easily delete a specific message from SQS without the receipt handle.
        # The receipt handle is only available when the message is received by a consumer.
        # Best we can do is mark it as cancelled in our state so the worker skips it.
        cancelled = True
        cancel_message = "Run marked as cancelled (worker will skip if it picks up the message)"
        logger.info(f"[cancelRunSkill] Marked queued run as cancelled: {run_id}")
    
    # Case 2: Running - stop the ECS task
    elif status == "running":
        ecs_task_arn = run_state.get("ecs_task_arn")
        if ecs_task_arn and env.ecs_cluster:
            try:
                ecs = _ecs_client()
                ecs.stop_task(
                    cluster=env.ecs_cluster,
                    task=ecs_task_arn,
                    reason=f"Cancelled by user {username}",
                )
                cancelled = True
                cancel_message = f"ECS task stopped: {ecs_task_arn}"
                logger.info(f"[cancelRunSkill] Stopped ECS task: {ecs_task_arn}")
            except Exception as e:
                logger.error(f"[cancelRunSkill] Failed to stop ECS task: {e}")
                cancel_message = f"Failed to stop ECS task: {e}"
        else:
            cancelled = True
            cancel_message = "Run marked as cancelled (no ECS task ARN available)"
            logger.warning(f"[cancelRunSkill] No ECS task ARN for running task: {run_id}")
    
    # Update run state
    run_state["status"] = "cancelled"
    run_state["updated_at"] = _utc_now_iso()
    run_state["completed_at"] = _utc_now_iso()
    
    try:
        _save_run_state(env, username, run_state)
    except Exception as e:
        logger.warning(f"[cancelRunSkill] Failed to update run state (non-fatal): {e}")
    
    # Publish cancellation event via AppSync for real-time UI update
    try:
        appsync_config = AppSyncApiKeyConfig(
            api_url=env.appsync_api_url,
            api_key=env.appsync_api_key,
        )
        publish_skill_editor_stream_event(
            config=appsync_config,
            owner=username,
            session_id=run_id,
            payload={
                "type": "run_cancelled",
                "run_id": run_id,
                "skill_id": skill_id,
                "message": cancel_message,
            },
        )
    except Exception as e:
        logger.warning(f"[cancelRunSkill] Failed to publish AppSync event (non-fatal): {e}")
    
    return {
        "runId": run_id,
        "status": "cancelled" if cancelled else "error",
        "message": cancel_message,
        "data": None,
    }


def _handle_pause_run_skill(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle pauseRunSkill mutation.
    
    Placeholder - pause functionality requires worker-side support.
    """
    logger.info("[pauseRunSkill] Starting handler (placeholder)")
    
    args = event.get("arguments") or {}
    input_data = args.get("input") or {}
    skill_json = input_data.get("skill")
    
    if isinstance(skill_json, str):
        try:
            skill = json.loads(skill_json)
        except json.JSONDecodeError:
            skill = {}
    else:
        skill = skill_json or {}
    
    run_id = skill.get("run_id")
    
    # TODO: Implement pause via worker communication (e.g., SQS control message or DynamoDB flag)
    return {
        "runId": run_id,
        "status": "not_implemented",
        "message": "Pause functionality not yet implemented for cloud runs",
        "data": None,
    }


def _handle_resume_run_skill(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle resumeRunSkill mutation.
    
    Placeholder - resume functionality requires worker-side support.
    """
    logger.info("[resumeRunSkill] Starting handler (placeholder)")
    
    args = event.get("arguments") or {}
    input_data = args.get("input") or {}
    skill_json = input_data.get("skill")
    
    if isinstance(skill_json, str):
        try:
            skill = json.loads(skill_json)
        except json.JSONDecodeError:
            skill = {}
    else:
        skill = skill_json or {}
    
    run_id = skill.get("run_id")
    
    # TODO: Implement resume via worker communication
    return {
        "runId": run_id,
        "status": "not_implemented",
        "message": "Resume functionality not yet implemented for cloud runs",
        "data": None,
    }


def _handle_step_run_skill(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle stepRunSkill mutation.
    
    Placeholder - step functionality requires worker-side support.
    """
    logger.info("[stepRunSkill] Starting handler (placeholder)")
    
    args = event.get("arguments") or {}
    input_data = args.get("input") or {}
    skill_json = input_data.get("skill")
    
    if isinstance(skill_json, str):
        try:
            skill = json.loads(skill_json)
        except json.JSONDecodeError:
            skill = {}
    else:
        skill = skill_json or {}
    
    run_id = skill.get("run_id")
    
    # TODO: Implement step via worker communication
    return {
        "runId": run_id,
        "status": "not_implemented",
        "message": "Step functionality not yet implemented for cloud runs",
        "data": None,
    }


def _handle_send_message(event: Dict[str, Any]) -> Dict[str, Any]:
    logger.info("[sendSkillEditorChatMessage] Starting handler")
    env = _load_env()
    args = event.get("arguments") or {}
    input_ = args.get("input") or {}

    owner = _owner_from_event(event)
    session_id = str(input_.get("sessionId") or "")
    content = str(input_.get("content") or "")

    logger.info(f"[sendSkillEditorChatMessage] owner={owner}, session_id={session_id}, content_len={len(content)}")

    if not session_id:
        logger.error("[sendSkillEditorChatMessage] sessionId is required")
        raise ValueError("sessionId is required")
    if not content.strip():
        logger.error("[sendSkillEditorChatMessage] content is required")
        raise ValueError("content is required")

    # Initialize variables for finally block
    session: Optional[Dict[str, Any]] = None
    history: Optional[Dict[str, Any]] = None
    agent: Optional[SkillEditorAgent] = None
    assistant_message_id = str(uuid4())
    error_occurred: Optional[str] = None
    response = None
    user_msg: Optional[Dict[str, Any]] = None
    assistant_msg: Optional[Dict[str, Any]] = None
    skill_name = _resolve_skill_name(input_)
    _ensure_context_dirs(env, owner, skill_name)

    try:
        logger.info(f"[sendSkillEditorChatMessage] Loading session from S3...")
        session = _load_session(env, owner, session_id)
        if not session:
            logger.info(f"[sendSkillEditorChatMessage] Session not found, auto-creating...")
            now = _utc_now_iso()
            session = {
                "id": session_id,
                "name": "New Chat",
                "flowgramId": input_.get("flowgramId"),
                "createdAt": now,
                "updatedAt": now,
                "pipelineState": "idle",
                "currentPlan": None,
                "currentRequest": None,
            }
        else:
            logger.info(f"[sendSkillEditorChatMessage] Session loaded, pipelineState={session.get('pipelineState')}")

        history = _load_history(env, owner, session_id)
        logger.info(f"[sendSkillEditorChatMessage] History loaded, {len(history.get('messages', []))} existing messages")

        now = _utc_now_iso()
        user_msg = {
            "id": str(uuid4()),
            "role": "user",
            "content": content,
            "timestamp": now,
            "attachments": input_.get("attachments"),
            "metadata": {
                "canvasContext": input_.get("canvasContext"),
                "clarificationResponses": input_.get("clarificationResponses"),
            },
        }
        history.setdefault("messages", [])
        if isinstance(history["messages"], list):
            history["messages"].append(user_msg)

        chunk_index = 0
        flowgram_id = input_.get("flowgramId")

        def on_event(evt: Dict[str, Any]) -> None:
            nonlocal chunk_index
            if not isinstance(evt, dict):
                return
            etype = evt.get("type")
            if etype not in {"progress", "chunk", "flowgram"}:
                return

            # Handle flowgram events — publish via skill_editor.event so
            # the frontend canvas loads even if AppSync times out.
            if etype == "flowgram":
                fg_data = evt.get("data")
                if not isinstance(fg_data, dict):
                    return
                # Convert raw Flowgram model_dump → UI-formatted workFlow shape
                # so the frontend receives {id, type, meta:{position}, data:{title, inputsValues, ...}}
                try:
                    from agent.skill_editor.schemas import Flowgram as _Flowgram
                    _fg = _Flowgram.model_validate(fg_data)
                    fg_data = {
                        "nodes": [agent._node_to_json(n) for n in _fg.nodes],
                        "edges": [
                            {
                                "sourceNodeID": e.sourceNodeID,
                                "targetNodeID": e.targetNodeID,
                                **({"sourcePortID": e.sourcePortID} if e.sourcePortID else {}),
                                **({"targetPortID": e.targetPortID} if e.targetPortID else {}),
                            }
                            for e in _fg.edges
                        ],
                    }
                except Exception as _conv_err:
                    logger.warning(f"[sendSkillEditorChatMessage] flowgram UI conversion failed, using raw: {_conv_err}")
                try:
                    _publish(
                        env,
                        owner=owner,
                        session_id=session_id,
                        flowgram_id=flowgram_id,
                        event_type="skill_editor.event",
                        payload={
                            "type": "canvas.load_flowgram_data",
                            "payload": {"flowgram": fg_data},
                        },
                    )
                    logger.info("[sendSkillEditorChatMessage] Published flowgram event via on_event")
                except Exception as pub_err:
                    logger.warning(f"[sendSkillEditorChatMessage] Error publishing flowgram event: {pub_err}")
                return

            data = evt.get("data") or {}
            text = data.get("message") if etype == "progress" else data.get("content")
            if not isinstance(text, str) or not text.strip():
                return
            payload = {
                "messageId": assistant_message_id,
                "chunk": text,
                "index": chunk_index,
            }
            try:
                _publish(
                    env,
                    owner=owner,
                    session_id=session_id,
                    flowgram_id=flowgram_id,
                    event_type="skill_editor.chat.stream_chunk",
                    payload=payload,
                )
            except Exception as pub_err:
                logger.warning(f"[sendSkillEditorChatMessage] Error publishing chunk: {pub_err}")
            chunk_index += 1

        logger.info("[sendSkillEditorChatMessage] Creating SkillEditorAgent...")
        llm_instance = None
        try:
            anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
            openai_key = os.environ.get("OPENAI_API_KEY")
            model_name = os.environ.get("SKILL_EDITOR_MODEL", "")

            if anthropic_key:
                from langchain_community.chat_models import ChatAnthropic
                effective_model = model_name or "claude-sonnet-4-6"
                llm_instance = ChatAnthropic(model=effective_model, api_key=anthropic_key, temperature=0)
                logger.info(f"[sendSkillEditorChatMessage] Using Anthropic LLM model={effective_model}")
            elif openai_key:
                from langchain_openai import ChatOpenAI
                effective_model = model_name or "gpt-5.5"
                llm_instance = ChatOpenAI(model=effective_model, api_key=openai_key, temperature=0)
                logger.info(f"[sendSkillEditorChatMessage] Anthropic key absent — using OpenAI fallback model={effective_model}")
            else:
                logger.warning("[sendSkillEditorChatMessage] No LLM API key found; agent will use internal LLM selection")
        except Exception as e:
            logger.warning(f"[sendSkillEditorChatMessage] Failed to init LLM: {e}")

        agent = SkillEditorAgent(llm=llm_instance, user_name=owner)

        try:
            pipeline_state = session.get("pipelineState")
            if isinstance(pipeline_state, str) and pipeline_state and pipeline_state != "idle":
                logger.info(f"[sendSkillEditorChatMessage] Restoring agent state: {pipeline_state}")
                agent.restore_state(
                    pipeline_state=pipeline_state,
                    current_plan=session.get("currentPlan") if isinstance(session.get("currentPlan"), dict) else session.get("currentPlan"),
                    current_request=session.get("currentRequest") if isinstance(session.get("currentRequest"), str) else None,
                    classified_domain=session.get("classifiedDomain"),
                    classified_intent_taxonomy=session.get("classifiedIntentTaxonomy"),
                    requirement_answers=session.get("requirementAnswers"),
                    domain_qa_done=bool(session.get("domainQaDone", False)),
                    workflow_description=session.get("workflowDescription"),
                    accumulated_clarification_answers=session.get("accumulatedClarificationAnswers"),
                    clarification_round=int(session.get("clarificationRound", 0) or 0),
                    pending_clarification=session.get("pendingClarification"),
                    pending_log_analysis_info=session.get("pendingLogAnalysisInfo"),
                    log_analysis_context=session.get("logAnalysisContext"),
                    last_saved_skill_name=session.get("lastSavedSkillName"),
                    cached_flowgram_dict=session.get("cachedFlowgramDict"),
                    user_lang=session.get("userLang"),
                    last_run_error=session.get("lastRunError"),
                )
        except Exception as e:
            logger.warning(f"[sendSkillEditorChatMessage] Failed to restore agent state: {e}")

        canvas_context = input_.get("canvasContext")
        # AWSJSON arrives as a JSON string from AppSync — parse it first
        if isinstance(canvas_context, str):
            try:
                canvas_context = json.loads(canvas_context)
            except (json.JSONDecodeError, TypeError):
                canvas_context = None
        clarification = input_.get("clarificationResponses")
        recent_context_sessions = _load_recent_context_sessions(env, owner, skill_name, limit=3)
        if isinstance(canvas_context, dict):
            canvas_context = {**canvas_context, "contextSessions": recent_context_sessions}
        elif recent_context_sessions:
            canvas_context = {"contextSessions": recent_context_sessions}

        logger.info(f"[sendSkillEditorChatMessage] Calling agent.process_message_sync, canvas_context_type={type(canvas_context).__name__}")
        token_tracker.reset()   # clear any stale data from warm-Lambda reuse
        response = agent.process_message_sync(
            message=content,
            canvas_context=canvas_context,
            session_id=session_id,
            clarification_responses=clarification,
            on_event=on_event,
        )
        logger.info(f"[sendSkillEditorChatMessage] Agent response received, intent={getattr(response, 'intent', None)}, message_len={len(response.message or '')}")

        # --- Flush token usage to S3 (best-effort) ---
        try:
            token_tracker.flush_to_s3(
                owner=owner,
                session_id=session_id,
                request_summary=content[:200] if content else "",
            )
        except Exception as _tok_err:
            logger.warning(f"[sendSkillEditorChatMessage] token_tracker flush failed: {_tok_err}")

        logger.info("[sendSkillEditorChatMessage] Publishing stream_end event...")

        # Inject dynamic choices into any question with data_source="user_skills"
        # before serializing — this fills the skill multi-select dropdown. Pass
        # the agent's user_lang so the fallback "no skills found" entry localizes.
        if getattr(response, "clarification", None):
            try:
                _ulang = getattr(agent, "user_lang", "en") or "en"
                response.clarification = _inject_skill_choices_into_clarification(
                    env, owner, response.clarification, user_lang=_ulang
                )
            except Exception as _inj_err:
                logger.warning(f"[sendSkillEditorChatMessage] Skill choice injection failed: {_inj_err}")

        try:
            stream_end_payload = {
                "messageId": assistant_message_id,
                "fullContent": response.message or "",
                "state": agent.pipeline_state.value if agent else "idle",
                "intent": response.intent.value if getattr(response, "intent", None) is not None else None,
                "clarification": [q.model_dump() for q in (response.clarification or [])] if getattr(response, "clarification", None) else None,
                "plan": response.plan.model_dump() if getattr(response, "plan", None) else None,
                "flowgram": None,
                "validation": response.validation.model_dump() if getattr(response, "validation", None) else None,
            }
            # Forward log_upload_request so the client can upload the file.
            # Override state to "processing" so the frontend doesn't re-show
            # clarification Q&A while the client uploads.
            _resp_meta = getattr(response, "metadata", None) or {}
            if isinstance(_resp_meta, dict) and _resp_meta.get("log_upload_request"):
                stream_end_payload["log_upload_request"] = _resp_meta["log_upload_request"]
                stream_end_payload["state"] = "processing"
            # Convert flowgram to UI format (same as on_event conversion)
            if getattr(response, "flowgram", None):
                try:
                    _fg = response.flowgram
                    stream_end_payload["flowgram"] = {
                        "nodes": [agent._node_to_json(n) for n in _fg.nodes],
                        "edges": [
                            {
                                "sourceNodeID": e.sourceNodeID,
                                "targetNodeID": e.targetNodeID,
                                **({"sourcePortID": e.sourcePortID} if e.sourcePortID else {}),
                                **({"targetPortID": e.targetPortID} if e.targetPortID else {}),
                            }
                            for e in _fg.edges
                        ],
                    }
                except Exception as _conv_err:
                    logger.warning(f"[sendSkillEditorChatMessage] stream_end flowgram conversion failed: {_conv_err}")
                    stream_end_payload["flowgram"] = response.flowgram.model_dump(exclude_none=True)
            logger.info(f"[sendSkillEditorChatMessage] stream_end payload keys: {list(stream_end_payload.keys())}, "
                        f"hasClarification={stream_end_payload.get('clarification') is not None}, "
                        f"hasPlan={stream_end_payload.get('plan') is not None}, "
                        f"hasFlowgram={stream_end_payload.get('flowgram') is not None}")
            _publish(
                env,
                owner=owner,
                session_id=session_id,
                flowgram_id=flowgram_id,
                event_type="skill_editor.chat.stream_end",
                payload=stream_end_payload,
            )
        except Exception as pub_err:
            logger.warning(f"[sendSkillEditorChatMessage] Error publishing stream_end: {pub_err}")

        try:
            commands_count = len(response.commands or [])
            if commands_count > 0:
                logger.info(f"[sendSkillEditorChatMessage] Publishing {commands_count} commands...")
            for cmd in response.commands or []:
                cmd_dict = cmd.to_dict() if hasattr(cmd, "to_dict") else (cmd or {})
                _publish(
                    env,
                    owner=owner,
                    session_id=session_id,
                    flowgram_id=flowgram_id,
                    event_type="skill_editor.event",
                    payload={
                        "type": cmd_dict.get("type"),
                        "payload": cmd_dict.get("payload"),
                    },
                )
        except Exception as e:
            logger.warning(f"[sendSkillEditorChatMessage] Error publishing commands: {e}")

        # If this request carries clarification answers, attach them to the
        # previous assistant message that originally asked the questions so the
        # frontend can render a read-only card after page reload.
        if clarification and isinstance(history.get("messages"), list):
            for prev_msg in reversed(history["messages"]):
                if (
                    prev_msg.get("role") == "assistant"
                    and isinstance(prev_msg.get("metadata"), dict)
                    and prev_msg["metadata"].get("clarification")
                ):
                    prev_msg["metadata"]["clarificationAnswers"] = clarification
                    break

        assistant_msg = {
            "id": assistant_message_id,
            "role": "assistant",
            "content": response.message or "",
            "timestamp": _utc_now_iso(),
            "attachments": None,
            "metadata": {
                "state": response.metadata.get("state") if isinstance(getattr(response, "metadata", None), dict) else None,
                "intent": response.intent.value if getattr(response, "intent", None) is not None else None,
                "clarification": (
                    [q.model_dump() for q in response.clarification]
                    if getattr(response, "clarification", None)
                    else None
                ),
                "clarificationAnswers": None,
                "plan": response.plan.model_dump() if getattr(response, "plan", None) else None,
                "hasClarification": bool(getattr(response, "clarification", None)),
                "hasPlan": bool(getattr(response, "plan", None)),
                "hasFlowgram": bool(getattr(response, "flowgram", None)),
                "log_upload_request": (
                    response.metadata.get("log_upload_request")
                    if isinstance(getattr(response, "metadata", None), dict)
                    else None
                ),
            },
        }

        if isinstance(history.get("messages"), list):
            history["messages"].append(assistant_msg)

        session["updatedAt"] = _utc_now_iso()
        session["pipelineState"] = agent.pipeline_state.value
        session["currentPlan"] = agent.current_plan.model_dump() if agent.current_plan else None
        session["currentRequest"] = agent.current_request
        session["classifiedDomain"] = agent.classified_domain
        session["classifiedIntentTaxonomy"] = agent.classified_intent_taxonomy
        session["requirementAnswers"] = agent.requirement_answers or None
        session["domainQaDone"] = agent.domain_qa_done
        session["workflowDescription"] = agent.workflow_description
        session["accumulatedClarificationAnswers"] = agent.accumulated_clarification_answers or None
        session["clarificationRound"] = agent.clarification_round
        session["pendingClarification"] = (
            [q.model_dump() for q in agent.get_pending_clarification()]
            if agent.get_pending_clarification()
            else None
        )
        session["pendingLogAnalysisInfo"] = agent.pending_log_analysis_info
        session["lastSavedSkillName"] = agent.last_saved_skill_name
        session["userLang"] = agent.user_lang

        # Cache last flowgram dict so edits work across Lambda invocations.
        # Truncate to stay comfortably under DynamoDB 400KB item limit.
        cfd = agent.cached_flowgram_dict
        if cfd:
            import json as _json
            cfd_str = _json.dumps(cfd, ensure_ascii=False)
            if len(cfd_str) > 200_000:
                logger.info(f"[sendSkillEditorChatMessage] cachedFlowgramDict too large ({len(cfd_str)}), truncating nodes")
                cfd = None  # drop rather than risk DDB failure
            session["cachedFlowgramDict"] = cfd
        else:
            session["cachedFlowgramDict"] = None

        # Save log analysis context (truncate log_content to stay within DynamoDB limits)
        lac = agent.log_analysis_context
        if lac and isinstance(lac, dict):
            persisted_lac = {k: v for k, v in lac.items()}
            if "log_content" in persisted_lac and isinstance(persisted_lac["log_content"], str):
                persisted_lac["log_content"] = persisted_lac["log_content"][:50000]
            session["logAnalysisContext"] = persisted_lac
        else:
            session["logAnalysisContext"] = None

    except Exception as e:
        import traceback
        error_occurred = str(e)
        error_traceback = traceback.format_exc()
        logger.error(f"[sendSkillEditorChatMessage] Exception occurred: {error_occurred}")
        logger.error(f"[sendSkillEditorChatMessage] Traceback: {error_traceback}")

        # Create error message for chat history
        error_msg = {
            "id": assistant_message_id,
            "role": "assistant",
            "content": f"An error occurred while processing your request: {error_occurred}",
            "timestamp": _utc_now_iso(),
            "attachments": None,
            "metadata": {
                "error": True,
                "errorMessage": error_occurred,
                "errorTraceback": error_traceback,
            },
        }

        assistant_msg = error_msg

        if history and isinstance(history.get("messages"), list):
            history["messages"].append(error_msg)

        if session:
            session["updatedAt"] = _utc_now_iso()
            session["lastError"] = {
                "message": error_occurred,
                "traceback": error_traceback,
                "timestamp": _utc_now_iso(),
            }

        # Publish error event to frontend
        try:
            _publish(
                env,
                owner=owner,
                session_id=session_id,
                flowgram_id=input_.get("flowgramId"),
                event_type="skill_editor.chat.stream_end",
                payload={
                    "messageId": assistant_message_id,
                    "fullContent": f"Error: {error_occurred}",
                    "error": True,
                },
            )
        except Exception as pub_err:
            logger.warning(f"[sendSkillEditorChatMessage] Failed to publish error event: {pub_err}")

    finally:
        # Always save history and session to S3, even on error
        logger.info(f"[sendSkillEditorChatMessage] Finally block: saving history and session to S3...")
        try:
            if history:
                _save_history(env, owner, session_id, history)
                logger.info(f"[sendSkillEditorChatMessage] History saved successfully")
        except Exception as save_err:
            logger.error(f"[sendSkillEditorChatMessage] Failed to save history: {save_err}")

        try:
            if session:
                _save_session(env, owner, session)
                logger.info(f"[sendSkillEditorChatMessage] Session saved successfully")
        except Exception as save_err:
            logger.error(f"[sendSkillEditorChatMessage] Failed to save session: {save_err}")

        try:
            context_messages: List[Dict[str, Any]] = []
            if isinstance(user_msg, dict):
                context_messages.append(user_msg)
            if isinstance(assistant_msg, dict):
                context_messages.append(assistant_msg)
            _append_context_messages(env, owner, skill_name, context_messages)
        except Exception as save_err:
            logger.error(f"[sendSkillEditorChatMessage] Failed to append context session: {save_err}")

    # If error occurred, raise it after saving
    if error_occurred:
        logger.info(f"[sendSkillEditorChatMessage] Re-raising error after saving state")
        # Return error response instead of raising to allow frontend to handle gracefully
        return {
            "sessionId": session_id,
            "sessionName": session.get("name") if session else "New Chat",
            "state": "error",
            "intent": None,
            "message": {
                "id": assistant_message_id,
                "role": "assistant",
                "content": f"An error occurred: {error_occurred}",
                "timestamp": _utc_now_iso(),
                "attachments": None,
                "metadata": {"error": True, "errorMessage": error_occurred},
            },
            "clarification": None,
            "plan": None,
            "flowgram": None,
            "validation": None,
        }

    logger.info(f"[sendSkillEditorChatMessage] Completed successfully, returning response")
    return {
        "sessionId": session_id,
        "sessionName": session.get("name") or "New Chat",
        "state": agent.pipeline_state.value if agent else "idle",
        "intent": response.intent.value if response and getattr(response, "intent", None) is not None else None,
        "message": _to_message_gql(assistant_msg),
        "clarification": [q.model_dump() for q in (response.clarification or [])] if response and getattr(response, "clarification", None) else None,
        "plan": response.plan.model_dump() if response and getattr(response, "plan", None) else None,
        "flowgram": response.flowgram.model_dump(exclude_none=True) if response and getattr(response, "flowgram", None) else None,
        "validation": response.validation.model_dump() if response and getattr(response, "validation", None) else None,
    }


def _resolve_skill_name(input_: Dict[str, Any]) -> str:
    canvas_context = input_.get("canvasContext")
    if isinstance(canvas_context, dict):
        name = canvas_context.get("skillName")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return "untitled_skill"


def _sanitize_owner(owner: str) -> str:
    """Sanitize owner email for S3 path: replace @ and . with _."""
    return (owner or "unknown").replace("@", "_").replace(".", "_")


def _skill_dir_name(skill_id: str) -> str:
    """Ensure skill directory has the '_skill' suffix."""
    if skill_id.endswith("_skill"):
        return skill_id
    return f"{skill_id}_skill"


def _build_skills_s3_prefix(env: _Env, owner: str, skill_id: str) -> str:
    """Construct the S3 prefix used for skill files.

    Uses "{sanitized_owner}/my_skills/{skillId}_skill/" layout to match
    the existing desktop/cloud skill storage convention.
    """
    prefix = _norm_prefix(env.s3_key_root)
    sanitized = _sanitize_owner(owner)
    skill_dir = _skill_dir_name(skill_id)
    return _s3_key(prefix, sanitized, "my_skills", skill_dir)


# ---------------------------------------------------------------------------
# Log Analysis
# ---------------------------------------------------------------------------

_LOG_ANALYSIS_MAX_BYTES = 1024 * 1024  # 1 MB log cap — fits typical 4-part rotation in Sonnet 200K context
_MAX_FLOWGRAM_INLINE = 64 * 1024       # 64 KB flowgram JSON cap for inline LLM context


def _find_log_file_key(env: _Env, owner: str, log_file_name: str) -> Optional[str]:
    """Search the user's skill tree in S3 for a log file matching *log_file_name*.

    Looks under ``<root>/<owner>/my_skills/`` recursively.
    If *log_file_name* is already a full S3 key that exists, use it directly.
    """
    client = _s3_client()
    # 1. Exact key check (caller may provide a full S3 key)
    if log_file_name and "/" in log_file_name:
        try:
            client.head_object(Bucket=env.s3_bucket, Key=log_file_name)
            return log_file_name
        except Exception:
            pass

    # 2. Search under the owner's skills prefix
    prefix = _norm_prefix(env.s3_key_root)
    sanitized = _sanitize_owner(owner)
    search_prefix = _s3_key(prefix, sanitized, "my_skills")
    if search_prefix and not search_prefix.endswith("/"):
        search_prefix += "/"

    keys = _s3_list_keys(bucket=env.s3_bucket, prefix=search_prefix)
    target = (log_file_name or "").strip().lower()
    for k in keys:
        if k.lower().endswith(target) or k.split("/")[-1].lower() == target:
            return k
    return None


def _read_s3_text(
    bucket: str, key: str, max_bytes: int = _LOG_ANALYSIS_MAX_BYTES
) -> tuple:
    """Read a text object from S3, truncating to *max_bytes*.

    Returns:
        (content: str, total_bytes: int)  — total_bytes is the full object size.
    """
    resp = _s3_client().get_object(Bucket=bucket, Key=key)
    total_bytes: int = resp.get("ContentLength", 0)
    raw = resp["Body"].read(max_bytes)
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError:
        content = raw.decode("latin-1")
    return content, total_bytes


def _run_sub_agent(
    llm: Any,
    system_prompt: str,
    user_message: str,
    *,
    label: str = "sub-agent",
    tool_schema: Optional[Dict[str, Any]] = None,
) -> Any:
    """Run a sub-agent LLM call and return structured tool_use output or plain text.

    When *tool_schema* is provided the model is called with tool_choice="required"
    and the first tool_call args dict is returned (guaranteed structure, no free-text
    parsing needed).  Falls back to plain text if tool_use fails.
    """
    from langchain_core.messages import SystemMessage as _SM, HumanMessage as _HM

    logger.info(f"[reqLogAnalysis:{label}] Invoking, user_msg_len={len(user_message)}, structured={tool_schema is not None}")

    if tool_schema:
        try:
            llm_with_tool = llm.bind_tools([tool_schema], tool_choice={"type": "tool", "name": tool_schema["name"]})
            resp = llm_with_tool.invoke([_SM(content=system_prompt), _HM(content=user_message)])
            tool_calls = getattr(resp, "tool_calls", None)
            if tool_calls:
                result = tool_calls[0].get("args", {})
                logger.info(f"[reqLogAnalysis:{label}] Structured result keys={list(result.keys())}")
                return result
        except Exception as e:
            logger.warning(f"[reqLogAnalysis:{label}] Structured tool_use failed ({e}), falling back to text")

    resp = llm.invoke([_SM(content=system_prompt), _HM(content=user_message)])
    text = resp.content if hasattr(resp, "content") else str(resp)
    logger.info(f"[reqLogAnalysis:{label}] Text response_len={len(text)}")
    return text


# ---------------------------------------------------------------------------
# Structured output schemas for log-analysis sub-agents
# ---------------------------------------------------------------------------

_LOG_PARSER_TOOL = {
    "name": "parsed_log_events",
    "description": "Structured parse of a skill-run log into timestamped events.",
    "parameters": {
        "type": "object",
        "properties": {
            "events": {
                "type": "array",
                "description": "Ordered list of log events",
                "items": {
                    "type": "object",
                    "properties": {
                        "timestamp": {"type": "string"},
                        "node_id": {"type": "string"},
                        "node_type": {"type": "string"},
                        "level": {"type": "string", "enum": ["info", "warning", "error", "debug"]},
                        "message": {"type": "string"},
                        "data": {"type": "object"},
                    },
                    "required": ["message", "level"],
                },
            },
            "error_events": {
                "type": "array",
                "description": "Subset of events that represent errors or failures",
                "items": {"type": "object"},
            },
            "first_failure_node": {"type": "string", "description": "node_id of the first node that failed, if any"},
            "summary": {"type": "string", "description": "1-3 sentence summary of what happened"},
            "was_truncated": {"type": "boolean", "description": "True if the log appeared to be cut off"},
        },
        "required": ["events", "summary"],
    },
}

_FLOWGRAM_CORRELATOR_TOOL = {
    "name": "flowgram_correlation",
    "description": "Maps parsed log events onto flowgram nodes and edges.",
    "parameters": {
        "type": "object",
        "properties": {
            "node_execution_order": {
                "type": "array",
                "items": {"type": "string"},
                "description": "node_ids in the order they executed (as seen in the log)",
            },
            "node_outcomes": {
                "type": "object",
                "description": "Map of node_id -> {status: success|failure|skipped, error: str|null}",
            },
            "failed_nodes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "node_id": {"type": "string"},
                        "node_type": {"type": "string"},
                        "error_type": {"type": "string"},
                        "error_message": {"type": "string"},
                        "input_snapshot": {"type": "object"},
                    },
                    "required": ["node_id", "error_message"],
                },
            },
            "unmatched_log_lines": {"type": "array", "items": {"type": "string"}},
            "summary": {"type": "string"},
        },
        "required": ["node_outcomes", "summary"],
    },
}

_ROOT_CAUSE_TOOL = {
    "name": "root_cause_analysis",
    "description": "Diagnoses the root cause of a skill run failure and recommends fixes.",
    "parameters": {
        "type": "object",
        "properties": {
            "root_cause": {"type": "string", "description": "Plain-language description of WHY it failed"},
            "hypothesis": {"type": "string", "description": "1-2 sentence targeted diagnosis (the specific bug)"},
            "failed_node_id": {"type": "string"},
            "failed_node_type": {"type": "string"},
            "error_type": {"type": "string"},
            "error_message": {"type": "string"},
            "input_at_failure": {"type": "object", "description": "Node input snapshot at point of failure"},
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            "fix_steps": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Ordered list of concrete fix steps",
            },
            "affected_nodes": {"type": "array", "items": {"type": "string"}},
            "is_prompt_fix": {"type": "boolean", "description": "True if the fix is a prompt improvement (not structural)"},
            "fix_tier": {
                "type": "string",
                "enum": ["prompt_only", "node_params", "flowgram_struct", "combo", "platform_code"],
                "description": (
                    "Cheapest tier of fix that will resolve the bug. Always pick the LOWEST tier that works.\n"
                    "  prompt_only     – tweak a node's prompt text (rules, examples, format constraints).\n"
                    "  node_params     – change non-prompt node attributes (model, temperature, condition expr, loop config, timeout).\n"
                    "  flowgram_struct – add/remove/rewire nodes or edges on the canvas.\n"
                    "  combo           – requires changes across two or more of the above tiers.\n"
                    "  platform_code   – not fixable in the Skill Editor — requires changing eCan.ai source code."
                ),
            },
            "bug_category": {
                "type": "string",
                "enum": ["skill_config", "platform_code", "infra_config", "quota_billing"],
                "description": (
                    "skill_config: fixable by editing flowgram nodes/prompts/edges — CodeAgent handles this. "
                    "platform_code: bug in the eCan.ai framework/runtime code — needs developer code review. "
                    "infra_config: AWS/cloud infrastructure misconfiguration (IAM, VPC, ECS, etc.). "
                    "quota_billing: rate limits, quota exhaustion, or billing issues (HTTP 429, ThrottlingException)."
                ),
            },
            "code_file_hints": {
                "type": "array",
                "items": {"type": "string"},
                "description": "For platform_code bugs: list of suspected source file paths or module names (e.g. 'agent/ec_tasks/appsync_pubsub.py'). Empty for other categories.",
            },
        },
        "required": ["root_cause", "fix_steps", "confidence", "bug_category", "fix_tier"],
    },
}

# Structured output schema for the Code Review Agent
_WRITE_BUG_REPORT_TOOL = {
    "name": "write_bug_report",
    "description": "Write a structured bug report for a platform_code defect found in the eCan.ai source.",
    "parameters": {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Repo-relative path to the defective file"},
            "line_number": {"type": "integer", "description": "Approximate line number of the defect"},
            "function_name": {"type": "string", "description": "Function or method containing the bug"},
            "root_cause": {"type": "string", "description": "Precise technical description of the defect"},
            "error_evidence": {"type": "string", "description": "Log snippet or error message that points to this location"},
            "suggested_fix": {"type": "string", "description": "Concrete code-level fix recommendation"},
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        },
        "required": ["file_path", "root_cause", "suggested_fix", "confidence"],
    },
}

# ---------------------------------------------------------------------------
# Pattern tables for deterministic infra_config / quota_billing detection
# (no LLM needed — match on well-known AWS error codes and HTTP status)
# ---------------------------------------------------------------------------
_QUOTA_PATTERNS = [
    "429", "too many requests", "throt", "rate limit", "ratelimit",
    "insufficient_quota", "quotaexceeded", "requestlimitexceeded",
    "slowdown", "serviceunavailable",  # S3 SlowDown is effectively quota
    "you exceeded your current quota",
]

# Higher-priority subset: LLM-provider account quota / billing exhaustion.
# These are the most user-actionable failures — they need a recharge, not a
# code fix. We scan for these FIRST and short-circuit the analysis pipeline.
_LLM_QUOTA_PATTERNS = [
    "insufficient_quota",
    "you exceeded your current quota",
    "billing_hard_limit_reached",
    "quota_exceeded",
    "credit balance is too low",
    "account has insufficient",
    "please check your plan and billing",
    "rate_limit_exceeded",  # OpenAI/Anthropic rate-limit
    "ratelimiterror",
    "anthropic.api_error",  # generic Anthropic auth/billing failure surface
    "openai.error.ratelimiterror",
]


def _get_user_lang_for_session(env: _Env, owner: str, session_id: Optional[str]) -> str:
    """Return 'zh' or 'en' for the given session. Defaults to 'en' on miss."""
    if not session_id:
        return "en"
    try:
        session = _load_session(env, owner, session_id) or {}
        raw = (session.get("userLang") or "en").strip().lower()
        return "zh" if raw.startswith("zh") else "en"
    except Exception:
        return "en"


def _build_language_directive(user_lang: str) -> str:
    """Prepend a strict language directive to the orchestrator system prompt.

    The user's chat language determines the report language. Raw log lines
    quoted verbatim stay in their original (English) form because logs are
    written in English by the runtime.
    """
    if user_lang == "zh":
        return (
            "==== LANGUAGE DIRECTIVE (HIGHEST PRIORITY) ====\n"
            "用户使用**中文**对话。所有标题、章节名、说明文字、根因分析、"
            "推荐修复步骤、错误描述等所有由你撰写的内容，**必须**全部用简体中文回答。\n"
            "唯一例外：当你**逐字引用**原始日志行（log line）时，保留其英文原文不翻译。\n"
            "不要用英文写章节标题（例如 'Log Summary'），改用中文（例如 '日志摘要'）。\n"
            "不要用英文写表格列名，改用中文。\n"
            "不要用英文撰写解释段落。\n"
            "==== END LANGUAGE DIRECTIVE ====\n\n"
        )
    return ""


def _detect_llm_quota_exhaustion(text: str) -> Optional[Dict[str, str]]:
    """Fast pre-check: scan log text for LLM provider quota / billing errors.

    Returns a dict with {provider, signal, line} when a match is found, else None.
    Operates on lowercase to avoid case sensitivity. Only the FIRST match is returned
    so the user can see exactly which line of the log triggered it.
    """
    if not text:
        return None
    lower = text.lower()
    for pat in _LLM_QUOTA_PATTERNS:
        idx = lower.find(pat)
        if idx == -1:
            continue
        # Locate the line containing the match for user-facing context
        line_start = lower.rfind("\n", 0, idx) + 1
        line_end = lower.find("\n", idx)
        if line_end == -1:
            line_end = min(len(text), idx + 240)
        snippet = text[line_start:line_end].strip()[:240]
        # Heuristic provider attribution
        provider = "unknown"
        if "openai" in lower[max(0, idx - 100):idx + 100]:
            provider = "OpenAI"
        elif "anthropic" in lower[max(0, idx - 100):idx + 100] or "claude" in lower[max(0, idx - 100):idx + 100]:
            provider = "Anthropic"
        return {"provider": provider, "signal": pat, "line": snippet}
    return None

_INFRA_PATTERNS = [
    "accessdenied", "access denied", "not authorized", "unauthorized",
    "nosuchbucket", "nosuchkey", "invalidbucketname",
    "networkingerror", "endpoint url",
    "taskfailed", "task stopped", "ecs", "fargate",
    "securitygroup", "subnet", "vpc",
    "credentialserror", "invalidclienttokenid", "tokenrefresherror",
    "ssm", "secretsmanager", "parameter not found",
    "certificate", "ssl", "handshake",
]


def _quick_classify(text: str) -> Optional[str]:
    """Fast deterministic pre-classifier before running the LLM RCA step.

    Returns 'quota_billing', 'infra_config', or None (let LLM decide).
    Operates on lowercase text to avoid case sensitivity issues.
    """
    lower = text.lower()
    for pat in _QUOTA_PATTERNS:
        if pat in lower:
            return "quota_billing"
    for pat in _INFRA_PATTERNS:
        if pat in lower:
            return "infra_config"
    return None


# ---------------------------------------------------------------------------
# Source-reading tools for the Code Review Agent
# ---------------------------------------------------------------------------
_CODE_REVIEW_REPO_ROOT: Optional[str] = None

def _get_repo_root() -> str:
    """Return the eCan.ai repo root, resolved once and cached."""
    global _CODE_REVIEW_REPO_ROOT
    if _CODE_REVIEW_REPO_ROOT is None:
        # In Lambda the code is laid out flat; in dev, it's the repo root.
        # Try to find the repo root relative to this file.
        this_dir = os.path.dirname(os.path.abspath(__file__))
        candidate = os.path.normpath(os.path.join(this_dir, "..", ".."))
        if os.path.isdir(os.path.join(candidate, "agent")):
            _CODE_REVIEW_REPO_ROOT = candidate
        else:
            # Lambda flat layout: the package root is two levels up from handler.py
            _CODE_REVIEW_REPO_ROOT = this_dir
    return _CODE_REVIEW_REPO_ROOT


_ALLOWED_CODE_PREFIXES = ("agent/", "utils/", "config/", "common/")


def _validate_source_path(rel_path: str) -> str:
    """Validate and normalize a repo-relative path for source reading.

    Raises ValueError if the path traverses outside allowed directories.
    Returns the absolute path.
    """
    # Strip leading slashes so callers can pass either style
    rel_clean = rel_path.lstrip("/").replace("\\", "/")
    # Block directory traversal
    normalized = os.path.normpath(rel_clean)
    if normalized.startswith(".."):
        raise ValueError(f"Path traversal not allowed: {rel_path!r}")
    # Must be under an allowed prefix
    if not any(normalized.startswith(p) for p in _ALLOWED_CODE_PREFIXES):
        raise ValueError(
            f"Path {rel_path!r} is outside allowed prefixes: {_ALLOWED_CODE_PREFIXES}"
        )
    return os.path.join(_get_repo_root(), normalized)


def _grep_source(pattern: str, path_prefix: str = "agent/", context_lines: int = 5) -> str:
    """Grep the eCan.ai source tree for *pattern* under *path_prefix*.

    Returns ripgrep output (or Python fallback) as a string, capped at 8 KB.
    Safe: path_prefix is validated against _ALLOWED_CODE_PREFIXES.
    """
    import subprocess, shutil

    try:
        abs_prefix = _validate_source_path(path_prefix.rstrip("/") + "/dummy.txt")
        search_dir = os.path.dirname(abs_prefix)
    except ValueError as e:
        return f"[grep_source error] {e}"

    if not os.path.isdir(search_dir):
        return f"[grep_source] directory not found: {search_dir}"

    MAX_OUTPUT = 8192
    try:
        rg = shutil.which("rg") or shutil.which("ripgrep")
        if rg:
            cmd = [rg, "-n", f"-C{context_lines}", "--max-filesize=500K", pattern, search_dir]
        else:
            cmd = ["grep", "-rn", f"--context={context_lines}", pattern, search_dir]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        output = result.stdout or result.stderr or "(no matches)"
        if len(output) > MAX_OUTPUT:
            output = output[:MAX_OUTPUT] + f"\n[...output truncated at {MAX_OUTPUT} bytes...]"
        return output
    except Exception as e:
        return f"[grep_source error] {e}"


def _read_source_file(rel_path: str, start_line: Optional[int] = None, end_line: Optional[int] = None) -> str:
    """Read a source file (or slice) from the repo, restricted to allowed paths.

    Returns the file contents (with line numbers), capped at 10 KB.
    """
    MAX_CHARS = 10240
    try:
        abs_path = _validate_source_path(rel_path)
    except ValueError as e:
        return f"[read_source_file error] {e}"

    if not os.path.isfile(abs_path):
        return f"[read_source_file] file not found: {rel_path}"

    try:
        with open(abs_path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()

        s = (start_line or 1) - 1
        e = end_line or len(lines)
        slice_ = lines[max(0, s):e]
        numbered = "".join(f"{s + i + 1:4d}  {ln}" for i, ln in enumerate(slice_))
        if len(numbered) > MAX_CHARS:
            numbered = numbered[:MAX_CHARS] + f"\n[...truncated at {MAX_CHARS} chars...]"
        return numbered
    except Exception as ex:
        return f"[read_source_file error] {ex}"


def _run_code_review_agent(
    llm: Any,
    rca_result: Dict[str, Any],
    log_content: str,
) -> Dict[str, Any]:
    """Agentic loop: grep + read source files to produce a structured bug report.

    Called only when rca_result["bug_category"] == "platform_code".
    Runs up to _CODE_REVIEW_MAX_TURNS tool-call rounds, then forces write_bug_report.

    Returns the write_bug_report args dict, or a minimal fallback on failure.
    """
    from langchain_core.messages import SystemMessage as _SM, HumanMessage as _HM, AIMessage as _AI, ToolMessage as _TM

    _CODE_REVIEW_MAX_TURNS = 6

    grep_schema = {
        "name": "grep_source",
        "description": "Search the eCan.ai source tree with a regex pattern.",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regex pattern to search for"},
                "path_prefix": {"type": "string", "description": "Repo-relative dir to search (e.g. 'agent/', 'utils/')"},
                "context_lines": {"type": "integer", "description": "Lines of context around each match", "default": 5},
            },
            "required": ["pattern"],
        },
    }
    read_schema = {
        "name": "read_source_file",
        "description": "Read a source file (or line range) from the repo.",
        "parameters": {
            "type": "object",
            "properties": {
                "rel_path": {"type": "string", "description": "Repo-relative file path"},
                "start_line": {"type": "integer"},
                "end_line": {"type": "integer"},
            },
            "required": ["rel_path"],
        },
    }

    system_prompt = (
        "You are a senior platform engineer performing a code review of the eCan.ai skill execution framework.\n"
        "A skill run failed and root-cause analysis determined the bug is in the platform code, NOT in the skill config.\n\n"
        "Your job:\n"
        "1. Use grep_source and read_source_file to locate the exact defective code.\n"
        "2. Once you have found the specific file + line + function, call write_bug_report with a precise, actionable report.\n\n"
        "Rules:\n"
        "- Never guess file paths — always grep first to confirm the location.\n"
        "- Reference specific line numbers and function names in your report.\n"
        "- The suggested_fix must be a concrete code-level change (not 'look at the logs').\n"
        "- Stop as soon as you have enough evidence. Do not keep searching after you've found the bug."
    )

    code_file_hints = rca_result.get("code_file_hints") or []
    hints_str = "\n".join(f"  - {h}" for h in code_file_hints) if code_file_hints else "  (no hints — use grep_source to find the defect)"

    user_msg = (
        f"## Root Cause Analysis\n\n"
        f"**Error**: {rca_result.get('error_message', '(unknown)')}\n"
        f"**Hypothesis**: {rca_result.get('hypothesis', rca_result.get('root_cause', ''))}\n"
        f"**Failed node type**: {rca_result.get('failed_node_type', '(unknown)')}\n\n"
        f"## Suspected Files\n{hints_str}\n\n"
        f"## Log Excerpt (first 2000 chars)\n```\n{log_content[:2000]}\n```\n\n"
        "Now investigate and call write_bug_report when you have a precise finding."
    )

    tools = [grep_schema, read_schema, _WRITE_BUG_REPORT_TOOL]
    llm_with_tools = llm.bind_tools(tools)
    messages = [_SM(content=system_prompt), _HM(content=user_msg)]

    for turn in range(_CODE_REVIEW_MAX_TURNS):
        try:
            resp = llm_with_tools.invoke(messages)
        except Exception as e:
            logger.warning(f"[code_review_agent] LLM call failed on turn {turn}: {e}")
            break

        tool_calls = getattr(resp, "tool_calls", None) or []
        if not tool_calls:
            # Model responded with text — nudge it to use a tool
            messages.append(resp)
            messages.append(_HM(content="Please call one of the tools to continue your investigation, or call write_bug_report if you have enough evidence."))
            continue

        messages.append(resp)
        finished = False
        for tc in tool_calls:
            tool_name = tc.get("name") or tc.get("function", {}).get("name", "")
            tool_args = tc.get("args") or tc.get("function", {}).get("arguments") or {}
            if isinstance(tool_args, str):
                try:
                    tool_args = json.loads(tool_args)
                except Exception:
                    tool_args = {}
            tc_id = tc.get("id") or f"call_{turn}"

            if tool_name == "write_bug_report":
                logger.info(f"[code_review_agent] Bug report written: {list(tool_args.keys())}")
                return tool_args

            elif tool_name == "grep_source":
                result = _grep_source(
                    pattern=tool_args.get("pattern", ""),
                    path_prefix=tool_args.get("path_prefix", "agent/"),
                    context_lines=int(tool_args.get("context_lines", 5)),
                )
                messages.append(_TM(content=result, tool_call_id=tc_id))

            elif tool_name == "read_source_file":
                result = _read_source_file(
                    rel_path=tool_args.get("rel_path", ""),
                    start_line=tool_args.get("start_line"),
                    end_line=tool_args.get("end_line"),
                )
                messages.append(_TM(content=result, tool_call_id=tc_id))

            else:
                messages.append(_TM(content=f"Unknown tool: {tool_name}", tool_call_id=tc_id))

    # Exhausted turns without write_bug_report — return a minimal fallback
    logger.warning("[code_review_agent] Exhausted turns without producing bug report — returning fallback")
    return {
        "file_path": (code_file_hints[0] if code_file_hints else "unknown"),
        "root_cause": rca_result.get("hypothesis") or rca_result.get("root_cause", "(see RCA)"),
        "suggested_fix": "Manual investigation required — auto code review did not converge.",
        "confidence": "low",
    }


# =============================================================================
# Debug workspace — RDS helpers, skill listing, workspace assembly
# =============================================================================

def _rds_execute(env: _Env, sql: str, params: Optional[List[Dict]] = None) -> List[Dict[str, Any]]:
    """Execute a SQL statement via Aurora Serverless RDS Data API.

    Returns a list of row dicts. Returns [] (not an error) if RDS is not configured.
    params format: [{"name": "owner", "value": {"stringValue": "..."}}]
    """
    if not (env.rds_cluster_arn and env.rds_secret_arn and env.rds_database):
        logger.warning("[rds_execute] RDS not configured — skipping DB query")
        return []
    try:
        client = boto3.client("rds-data", region_name=os.environ.get("AWS_REGION", "us-east-1"))
        kwargs: Dict[str, Any] = {
            "resourceArn": env.rds_cluster_arn,
            "secretArn": env.rds_secret_arn,
            "database": env.rds_database,
            "sql": sql,
            "includeResultMetadata": True,
        }
        if params:
            kwargs["parameters"] = params
        resp = client.execute_statement(**kwargs)
        cols = [c["name"].lower() for c in (resp.get("columnMetadata") or [])]
        rows = []
        for raw_row in resp.get("records") or []:
            obj: Dict[str, Any] = {}
            for col, field in zip(cols, raw_row):
                if not field:
                    obj[col] = None
                elif "stringValue" in field:
                    obj[col] = field["stringValue"]
                elif "longValue" in field:
                    obj[col] = field["longValue"]
                elif "doubleValue" in field:
                    obj[col] = field["doubleValue"]
                elif "booleanValue" in field:
                    obj[col] = field["booleanValue"]
                elif field.get("isNull"):
                    obj[col] = None
                else:
                    obj[col] = None
            rows.append(obj)
        return rows
    except Exception as e:
        logger.warning(f"[rds_execute] Query failed: {e}")
        return []


def _fetch_skill_db_rows(env: _Env, owner: str, skill_names: List[str]) -> List[Dict[str, Any]]:
    """Fetch agent_skills rows for the given owner and skill names.

    Returns list of row dicts. Includes config and diagram JSON columns.
    """
    if not skill_names:
        return []
    placeholders = ", ".join(f":sn{i}" for i in range(len(skill_names)))
    sql = f"SELECT * FROM agent_skills WHERE owner = :owner AND name IN ({placeholders})"
    params = [{"name": "owner", "value": {"stringValue": owner}}]
    for i, name in enumerate(skill_names):
        params.append({"name": f"sn{i}", "value": {"stringValue": name}})
    return _rds_execute(env, sql, params)


def _list_user_skills_for_qa(env: _Env, owner: str) -> List[Dict[str, str]]:
    """Return a list of the user's skill names from S3 for Q&A dropdown choices.

    Format: [{"id": skill_name, "label": skill_name, "description": ""}]
    Falls back to empty list if S3 listing fails.
    """
    try:
        prefix = _norm_prefix(env.s3_key_root)
        user_dir = _safe_user_dir_name(owner)
        skills_prefix = _s3_key(prefix, user_dir, "my_skills") + "/"
        keys = _s3_list_keys(bucket=env.s3_bucket, prefix=skills_prefix)

        seen: Dict[str, bool] = {}
        for key in keys:
            parts = key.replace(skills_prefix, "").split("/")
            if parts and parts[0]:
                seen[parts[0]] = True

        return [
            {"id": name, "label": name, "description": ""}
            for name in sorted(seen.keys())
        ]
    except Exception as e:
        logger.warning(f"[list_user_skills_for_qa] Failed: {e}")
        return []


def _inject_skill_choices_into_clarification(
    env: _Env, owner: str, clarification: Optional[List[Any]],
    user_lang: str = "en",
) -> Optional[List[Any]]:
    """Find any ClarificationQuestion with data_source='user_skills' and fill its choices.

    Works on both ClarificationQuestion objects and their model_dump() dicts.
    """
    if not clarification:
        return clarification

    from agent.skill_editor.schemas import ClarificationChoice
    from agent.skill_editor.i18n import t as _t

    skills = None  # lazy-fetch once

    def _ensure_skills() -> List[Dict[str, str]]:
        nonlocal skills
        if skills is None:
            skills = _list_user_skills_for_qa(env, owner)
        return skills or []

    result = []
    for q in clarification:
        is_dict = isinstance(q, dict)
        src = q.get("data_source") if is_dict else getattr(q, "data_source", None)
        if src == "user_skills":
            skill_list = _ensure_skills()
            new_choices = [
                ClarificationChoice(id=s["id"], label=s["label"], description=s.get("description", ""))
                for s in skill_list
            ] if skill_list else [
                ClarificationChoice(
                    id="_none",
                    label=_t("log_qa_skill_none_label", user_lang),
                    description=_t("log_qa_skill_none_desc", user_lang),
                )
            ]
            if is_dict:
                q = dict(q)
                q["choices"] = [c.model_dump() for c in new_choices]
            else:
                object.__setattr__(q, "choices", new_choices) if hasattr(q, "__fields__") else setattr(q, "_choices", new_choices)
                try:
                    q.choices = new_choices
                except Exception:
                    q = q.model_copy(update={"choices": new_choices})
        result.append(q)
    return result


# ---------------------------------------------------------------------------
# Debug workspace — assembles all debug context under EFS (or /tmp fallback)
# ---------------------------------------------------------------------------

_DEBUG_WS_ROOT = "/mnt/efs/debug"      # EFS persistent workspace root
_DEBUG_WS_TMP = "/tmp/debug"           # fallback if EFS is unavailable


def _debug_ws_root() -> str:
    """Return the writable workspace root (EFS preferred, /tmp fallback)."""
    try:
        if os.path.isdir("/mnt/efs"):
            os.makedirs(_DEBUG_WS_ROOT, exist_ok=True)
            return _DEBUG_WS_ROOT
    except OSError:
        pass
    return _DEBUG_WS_TMP


@dataclass
class DebugWorkspace:
    """Paths to all locally-staged debug artifacts for one debug session."""
    root: str                             # absolute path to session workspace dir
    log_path: Optional[str]              # path to downloaded log file
    skill_dirs: Dict[str, str]           # skill_name → path to skill dir
    prompt_dir: str                       # path to prompts/ dir (Lambda package copy)
    source_root: str                      # path to source code root (/var/task in Lambda)
    db_records: Dict[str, Any]           # skill_name → agent_skills row dict
    is_complete: bool = False            # True after all downloads finished


def _assemble_debug_workspace(
    env: _Env,
    owner: str,
    session_id: str,
    skill_names: List[str],
    log_s3_key: Optional[str],
) -> DebugWorkspace:
    """Download log + skill flowgrams + DB rows into a local workspace dir.

    Layout:
      {ws}/log/{filename}
      {ws}/skills/{skill_name}/flowgram.json
      {ws}/skills/{skill_name}/data_mapping.json
      {ws}/skills/{skill_name}/db_record.json
      {ws}/prompts/          → symlink or copy from /var/task/prompts/
      source code:           /var/task/ (Lambda package, read-only)
    """
    sanitized_owner = _sanitize_owner(owner)
    ws_root = os.path.join(_debug_ws_root(), sanitized_owner, session_id)
    os.makedirs(ws_root, exist_ok=True)

    log_dir = os.path.join(ws_root, "log")
    os.makedirs(log_dir, exist_ok=True)

    # --- Download log from S3 ---
    log_path: Optional[str] = None
    if log_s3_key:
        try:
            log_resp = _s3_client().get_object(Bucket=env.s3_bucket, Key=log_s3_key)
            log_bytes = log_resp["Body"].read()
            log_filename = log_s3_key.split("/")[-1] or "run.log"
            log_path = os.path.join(log_dir, log_filename)
            with open(log_path, "wb") as fh:
                fh.write(log_bytes)
            logger.info(f"[assemble_debug_ws] Log saved: {log_path} ({len(log_bytes):,} bytes)")
        except Exception as e:
            logger.warning(f"[assemble_debug_ws] Log download failed: {e}")

    # --- Download skill flowgrams from S3 + fetch DB rows ---
    skill_dirs: Dict[str, str] = {}
    db_records: Dict[str, Any] = {}

    # Fetch all DB rows in one query
    if skill_names:
        rows = _fetch_skill_db_rows(env, owner, skill_names)
        for row in rows:
            db_records[row.get("name", "")] = row
        logger.info(f"[assemble_debug_ws] DB rows fetched: {list(db_records.keys())}")

    prefix = _norm_prefix(env.s3_key_root)
    s3 = _s3_client()
    for skill_name in skill_names:
        skill_dir = os.path.join(ws_root, "skills", skill_name)
        os.makedirs(skill_dir, exist_ok=True)
        skill_dirs[skill_name] = skill_dir

        # Write DB record
        db_row = db_records.get(skill_name)
        if db_row:
            db_record_path = os.path.join(skill_dir, "db_record.json")
            with open(db_record_path, "w", encoding="utf-8") as fh:
                json.dump(db_row, fh, ensure_ascii=False, indent=2, default=str)

        # Download flowgram (the most recent .json under diagram_dir/)
        skill_root = _skill_root_prefix(env, owner, skill_name)
        diagram_prefix = _skill_diagram_dir(env, owner, skill_name) + "/"
        try:
            diagram_keys = _s3_list_keys(bucket=env.s3_bucket, prefix=diagram_prefix)
            json_keys = [k for k in diagram_keys if k.endswith(".json")]
            if json_keys:
                fg_key = sorted(json_keys)[-1]  # lexicographically last = most recent timestamp
                fg_resp = s3.get_object(Bucket=env.s3_bucket, Key=fg_key)
                fg_bytes = fg_resp["Body"].read()
                fg_path = os.path.join(skill_dir, "flowgram.json")
                with open(fg_path, "wb") as fh:
                    fh.write(fg_bytes)
                logger.info(f"[assemble_debug_ws] Flowgram saved: {fg_path} ({len(fg_bytes):,} bytes)")
        except Exception as e:
            logger.warning(f"[assemble_debug_ws] Flowgram download failed for {skill_name}: {e}")

        # Download data_mapping.json
        dm_key = _skill_data_mapping_key(env, owner, skill_name)
        try:
            dm_resp = s3.get_object(Bucket=env.s3_bucket, Key=dm_key)
            dm_path = os.path.join(skill_dir, "data_mapping.json")
            with open(dm_path, "wb") as fh:
                fh.write(dm_resp["Body"].read())
        except Exception:
            pass  # data_mapping.json is optional

    # --- Prompts: link to Lambda package copy (already on disk) ---
    lambda_prompts = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts")
    prompt_dir = os.path.join(ws_root, "prompts")
    if not os.path.exists(prompt_dir):
        try:
            os.symlink(lambda_prompts, prompt_dir)
        except OSError:
            # EFS may not support symlinks — just record the path
            prompt_dir = lambda_prompts

    # Source code root: Lambda package is at /var/task; EFS may also have a checkout
    efs_src = "/mnt/efs/repo/eCan.ai"
    source_root = efs_src if os.path.isdir(efs_src) else "/var/task"

    logger.info(
        f"[assemble_debug_ws] Workspace ready: {ws_root}, "
        f"skills={list(skill_dirs.keys())}, log={log_path}, source={source_root}"
    )

    return DebugWorkspace(
        root=ws_root,
        log_path=log_path,
        skill_dirs=skill_dirs,
        prompt_dir=prompt_dir,
        source_root=source_root,
        db_records=db_records,
        is_complete=True,
    )


# =============================================================================
# Code-fix agent (PLACEHOLDER)
# =============================================================================
#
# Eventual design — when implemented, this agent will:
#   1. Authenticate to GitHub via a fine-grained PAT stored in Secrets Manager
#      (env: GITHUB_FIX_AGENT_TOKEN_ARN).
#   2. Create a branch off `sc_cloud` named `auto-fix/{session_id}/{short-sha}`
#      via `POST /repos/scszcoder/eCan.ai/git/refs`.
#   3. For each file in `bug_report.file_path`: fetch current contents, apply
#      the LLM-proposed edit (using a contained edit_source_file tool), commit
#      via `PUT /repos/.../contents/{path}`.
#   4. Trigger a GitHub Actions workflow_dispatch to build the desktop installer
#      for the affected platforms (Windows / macOS).
#   5. Poll the workflow run until artifacts are produced, fetch artifact
#      download URLs, return them to the user.
#   6. Open a PR back to `sc_cloud` for human review (does NOT auto-merge).
#
# Why placeholder for now: steps 1–3 are ~150 lines and feasible; step 4 needs a
# GitHub Actions workflow that builds the eCan.ai installer (doesn't exist yet);
# step 5 polls CI which adds latency the synchronous Lambda call can't tolerate
# (would need to be moved to a Step Function or async invocation pattern).
#
# Safe placeholder behaviour: return the structured bug report (already produced
# by the Code Review Agent) plus a "next steps for engineering" section, so the
# user knows exactly what would happen and can manually drive it for now.
# =============================================================================

def _run_code_fix_agent_placeholder(
    code_review_report: Dict[str, Any],
    rca_result: Dict[str, Any],
) -> Dict[str, Any]:
    """Placeholder for the future code-fix agent.

    Today: returns a structured stub that explains what would happen, attaches
    the existing bug report so the developer has everything they need.

    When real: branch from sc_cloud, apply file edits, trigger CI, return
    artifact download URLs + PR link.
    """
    return {
        "status": "not_implemented",
        "next_action": (
            "auto_branch_and_build (planned) — would create a branch off "
            "sc_cloud, apply the suggested fix, build the desktop installer "
            "via GitHub Actions, and return a download link plus a PR for "
            "human review."
        ),
        "what_developer_should_do_now": [
            "Read the structured bug report below for file:line + suggested fix.",
            "Open a branch manually, apply the edit, run the build pipeline.",
            "Open a PR to sc_cloud — that flow will be automated in a later release.",
        ],
        "bug_report": code_review_report,
        "rca_summary": {
            "hypothesis": rca_result.get("hypothesis"),
            "error_type": rca_result.get("error_type"),
            "error_message": rca_result.get("error_message"),
        },
    }


def _handle_req_log_analysis(event: Dict[str, Any]) -> Dict[str, Any]:
    """Handle reqLogAnalysis mutation.

    Runs a multi-agent pipeline to analyze a skill-run log against the
    skill's flowgram and the user's behavioural observations.

    Sub-agents (prompts loaded from Agent_Prompts DynamoDB):
      1. log_parser          – parse raw log into structured events
      2. flowgram_correlator – map events onto flowgram nodes/edges
      3. root_cause_analyzer – diagnose root cause + suggest fixes
      4. log_analysis_orchestrator – compose the final report

    Input (LogAnalysisInput — extended fields accepted from input object):
        description: String       – free-form description / question
        log_file_name: String     – log file name or S3 key
        flowgram_json: AWSJSON    – the skill's flowgram JSON (optional)
        user_observation: String  – what the user saw happen
        expected_behavior: String – what the user expected
        sessionId: String         – chat session to stream into (optional)
        flowgramId: String        – flowgram id for pub/sub (optional)

    Returns:
        logAnalysisResponse { status }
    """
    logger.info("[reqLogAnalysis] Starting handler")
    env = _load_env()
    args = event.get("arguments") or {}
    input_ = args.get("input") or {}

    owner = _owner_from_event(event)
    description = (input_.get("description") or "").strip()
    log_file_name = (input_.get("log_file_name") or "").strip()
    flowgram_raw = input_.get("flowgram_json") or input_.get("flowgramJson") or ""
    user_observation = (input_.get("user_observation") or input_.get("userObservation") or description).strip()
    expected_behavior = (input_.get("expected_behavior") or input_.get("expectedBehavior") or "").strip()

    logger.info(
        f"[reqLogAnalysis] owner={owner}, log_file_name={log_file_name}, "
        f"description_len={len(description)}, observation_len={len(user_observation)}, "
        f"expected_len={len(expected_behavior)}, has_flowgram={bool(flowgram_raw)}"
    )

    if not log_file_name:
        return {"status": "error: log_file_name is required"}

    # --- Locate and read the log file from S3 ---
    s3_key = _find_log_file_key(env, owner, log_file_name)
    if not s3_key:
        logger.warning(f"[reqLogAnalysis] Log file not found: {log_file_name}")
        return {"status": f"error: log file not found – {log_file_name}"}

    logger.info(f"[reqLogAnalysis] Reading log from s3://{env.s3_bucket}/{s3_key}")
    try:
        log_content, log_total_bytes = _read_s3_text(env.s3_bucket, s3_key)
    except Exception as e:
        logger.error(f"[reqLogAnalysis] Failed to read log file: {e}")
        return {"status": f"error: could not read log file – {e}"}

    if not log_content.strip():
        return {"status": "error: log file is empty"}

    # Build a truncation signal that tells the LLM exactly how much was cut so it
    # can hedge its conclusions and the user can know to re-run with a smaller log.
    truncated_note = ""
    is_truncated = log_total_bytes > _LOG_ANALYSIS_MAX_BYTES
    if is_truncated:
        remaining_bytes = log_total_bytes - _LOG_ANALYSIS_MAX_BYTES
        truncated_note = (
            f"\n\n[LOG TRUNCATED: showing first {_LOG_ANALYSIS_MAX_BYTES // 1024} KB "
            f"of {log_total_bytes // 1024} KB total. "
            f"{remaining_bytes // 1024} KB ({remaining_bytes:,} bytes) not shown. "
            f"Root cause may lie in the truncated portion — analysis covers only the visible section.]"
        )

    # Parse flowgram JSON if provided as string
    flowgram_json_str = ""
    if flowgram_raw:
        if isinstance(flowgram_raw, str):
            flowgram_json_str = flowgram_raw
        else:
            flowgram_json_str = json.dumps(flowgram_raw, ensure_ascii=False)
    else:
        flowgram_json_str = "(not provided — analyze from log references only)"

    # --- Setup LLM ---
    analysis_message_id = str(uuid4())
    session_id = input_.get("sessionId") or f"log-analysis-{uuid4()}"
    flowgram_id = input_.get("flowgramId")

    try:
        anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
        openai_key = os.environ.get("OPENAI_API_KEY")
        model_name = os.environ.get("SKILL_EDITOR_MODEL", "")

        if anthropic_key:
            from langchain_community.chat_models import ChatAnthropic
            effective_model = model_name or "claude-sonnet-4-6"
            llm = ChatAnthropic(model=effective_model, api_key=anthropic_key, temperature=0)
            logger.info(f"[reqLogAnalysis] Using Anthropic LLM model={effective_model}")
        elif openai_key:
            from langchain_openai import ChatOpenAI
            effective_model = model_name or "gpt-4o"
            llm = ChatOpenAI(model=effective_model, api_key=openai_key, temperature=0)
            logger.info(f"[reqLogAnalysis] Anthropic key absent — using OpenAI fallback model={effective_model}")
        else:
            logger.error("[reqLogAnalysis] Neither ANTHROPIC_API_KEY nor OPENAI_API_KEY is set")
            return {"status": "error: LLM not configured — set ANTHROPIC_API_KEY or OPENAI_API_KEY"}

        # Helper: stream a progress message to the client
        chunk_index = 0

        def _stream_progress(msg: str) -> None:
            nonlocal chunk_index
            try:
                _publish(
                    env, owner=owner, session_id=session_id,
                    flowgram_id=flowgram_id,
                    event_type="skill_editor.chat.stream_chunk",
                    payload={"messageId": analysis_message_id, "chunk": msg, "index": chunk_index},
                )
            except Exception:
                pass
            chunk_index += 1

        # ======================================================
        # PRE-CHECK 0 — LLM provider quota exhaustion
        #
        # Before burning any LLM tokens on analysis, scan the log for
        # provider-side billing/quota errors. These are the most common AND
        # most user-actionable failures: the user just needs to recharge or
        # raise their plan limit. There's no point running the full RCA
        # pipeline for a quota issue — the cause is in the error itself.
        # ======================================================
        _quota_hit = _detect_llm_quota_exhaustion(log_content)
        if _quota_hit:
            _stream_progress(
                f"### ⚠️ LLM Quota Exhaustion Detected\n\n"
                f"The skill failed because the **{_quota_hit['provider']}** account "
                f"hit a quota / billing limit. No skill or code fix will resolve this — "
                f"the account needs attention.\n\n"
                f"**Signal**: `{_quota_hit['signal']}`\n\n"
                f"**Log line**:\n```\n{_quota_hit['line']}\n```\n\n"
                f"**What to do:**\n"
                f"1. Check your {_quota_hit['provider']} dashboard for current usage and quota.\n"
                f"2. Recharge credits or upgrade the plan.\n"
                f"3. If you're rate-limited (not out of quota), add retry/back-off in the skill.\n\n"
                f"_(Skipping deeper RCA — quota is the obvious cause.)_\n"
            )
            try:
                if session_id:
                    session = _load_session(env, owner, session_id) or {}
                    session["lastRunError"] = {
                        "bug_category": "quota_billing",
                        "error_type": "llm_quota_exhausted",
                        "provider": _quota_hit["provider"],
                        "signal": _quota_hit["signal"],
                        "error_message": _quota_hit["line"],
                        "fix_hypothesis": f"{_quota_hit['provider']} account quota / billing limit reached.",
                        "iteration": 1,
                    }
                    session["updatedAt"] = _utc_now_iso()
                    _save_session(env, owner, session)
            except Exception:
                pass
            try:
                _publish(
                    env, owner=owner, session_id=session_id,
                    flowgram_id=flowgram_id,
                    event_type="skill_editor.chat.stream_end",
                    payload={
                        "messageId": analysis_message_id,
                        "fullContent": "LLM quota exhausted — see above.",
                        "state": "complete",
                        "intent": "log_analysis",
                        "shortCircuit": "quota_billing",
                    },
                )
            except Exception:
                pass
            return {"status": "ok", "shortCircuit": "quota_billing"}

        # ---- Load prompts from DynamoDB (with defaults) ----
        from agent.skill_editor.prompt_store import prompt_store as _ps

        log_parser_prompt = _ps.get("log_parser", default="Parse the following log into structured JSON events.")
        correlator_prompt = _ps.get("flowgram_correlator", default="Correlate parsed events with the flowgram.")
        rca_prompt = _ps.get("root_cause_analyzer", default="Determine root cause and suggest fixes.")
        orchestrator_prompt = _ps.get(
            "log_analysis_orchestrator",
            default="Analyze the log, correlate with the flowgram, and provide a diagnosis.",
        )

        # ======================================================
        # Steps 1 → 2 → 3 pipeline using ThreadPoolExecutor
        #
        # Each step is submitted as soon as its inputs are ready.
        # Running LLM calls in daemon threads keeps the main Lambda thread free
        # for streaming progress notifications between steps.
        # The dependency chain is 1 → 2 → 3 → 4(streaming), so true concurrency
        # between LLM steps is not possible, but the thread model avoids blocking
        # the event loop used by _stream_progress / AppSync publishing.
        # ======================================================
        import concurrent.futures as _futures

        executor = _futures.ThreadPoolExecutor(max_workers=1)

        # ---- Step 1: Log Parser ----
        _stream_progress("**Step 1/4** — Parsing log events…\n\n")
        parser_input = f"""Parse the following skill-run log into structured events.

--- BEGIN LOG ({log_file_name}) ---
{log_content}{truncated_note}
--- END LOG ---"""

        parse_future = executor.submit(
            _run_sub_agent, llm, log_parser_prompt, parser_input,
            **{"label": "log_parser", "tool_schema": _LOG_PARSER_TOOL},
        )

        # Stream a live dot while waiting so the client knows we're still running.
        parsed_result = parse_future.result()
        if isinstance(parsed_result, dict):
            parsed_events_text = json.dumps(parsed_result, ensure_ascii=False)
        else:
            parsed_result = {}
            parsed_events_text = str(parsed_result)
        _stream_progress("**Step 1 complete** — Log parsed.\n\n")

        # ---- Step 2: Flowgram Correlator ----
        _stream_progress("**Step 2/4** — Correlating with flowgram…\n\n")
        correlator_input = f"""Correlate the following parsed log events with the flowgram.

--- PARSED EVENTS ---
{parsed_events_text}

--- FLOWGRAM ---
{flowgram_json_str}"""

        correlate_future = executor.submit(
            _run_sub_agent, llm, correlator_prompt, correlator_input,
            **{"label": "flowgram_correlator", "tool_schema": _FLOWGRAM_CORRELATOR_TOOL},
        )
        correlation_result = correlate_future.result()
        if isinstance(correlation_result, dict):
            correlation_text = json.dumps(correlation_result, ensure_ascii=False)
        else:
            correlation_result = {}
            correlation_text = str(correlation_result)
        _stream_progress("**Step 2 complete** — Correlation done.\n\n")

        executor.shutdown(wait=False)

        # ======================================================
        # Step 3 — Root Cause Analyzer sub-agent (structured output)
        # ======================================================
        _stream_progress("**Step 3/4** — Analyzing root cause…\n\n")
        rca_input = f"""Determine the root cause based on the following.

--- CORRELATION MAP ---
{correlation_text}

--- USER OBSERVATION ---
{user_observation or '(not provided)'}

--- EXPECTED BEHAVIOR ---
{expected_behavior or '(not provided)'}

--- FLOWGRAM (for reference) ---
{flowgram_json_str}"""

        # Submit step 3 while step 4's orchestrator prompt is being built (overlap).
        rca_executor = _futures.ThreadPoolExecutor(max_workers=1)
        rca_future = rca_executor.submit(
            _run_sub_agent, llm, rca_prompt, rca_input,
            **{"label": "root_cause_analyzer", "tool_schema": _ROOT_CAUSE_TOOL},
        )
        rca_result = rca_future.result()
        rca_executor.shutdown(wait=False)
        if isinstance(rca_result, dict):
            rca_text = json.dumps(rca_result, ensure_ascii=False)
        else:
            rca_result = {}
            rca_text = str(rca_result)
        _stream_progress("**Step 3 complete** — Root cause identified.\n\n")

        # ======================================================
        # Step 3b — 4-way bug classification + category routing
        #
        # bug_category drives what happens next:
        #   skill_config   → CodeAgent will fix (normal path)
        #   platform_code  → Code Review Agent (grep + read loop)
        #   infra_config   → deterministic AWS error pattern report
        #   quota_billing  → deterministic rate-limit report
        # ======================================================

        # Run quick deterministic pre-classifier first (no LLM cost)
        _quick_cat = _quick_classify(log_content + " " + rca_result.get("error_message", ""))
        bug_category = rca_result.get("bug_category") or _quick_cat or "skill_config"

        code_review_report: Optional[Dict[str, Any]] = None

        if bug_category == "platform_code":
            _stream_progress(
                "**Classification: platform_code** — Running code review agent to locate the defect…\n\n"
            )
            try:
                code_review_report = _run_code_review_agent(llm, rca_result, log_content)
                logger.info(f"[reqLogAnalysis] Code review report: {list(code_review_report.keys())}")
            except Exception as cr_err:
                logger.warning(f"[reqLogAnalysis] Code review agent failed: {cr_err}")
                code_review_report = {
                    "root_cause": rca_result.get("root_cause", "(see RCA)"),
                    "suggested_fix": "Code review agent encountered an error — manual investigation required.",
                    "confidence": "low",
                }
            # Attach code-fix agent placeholder — describes the planned auto-fix
            # flow (branch → edit → build → download). Real implementation TBD.
            try:
                code_review_report["code_fix_agent"] = _run_code_fix_agent_placeholder(
                    code_review_report, rca_result
                )
            except Exception:
                pass
            _stream_progress("**Code review complete** — Platform bug located.\n\n")

        elif bug_category == "infra_config":
            _stream_progress("**Classification: infra_config** — Infrastructure/AWS configuration issue detected.\n\n")
            code_review_report = {
                "category": "infra_config",
                "root_cause": rca_result.get("root_cause", "AWS/infrastructure configuration error"),
                "suggested_fix": (
                    "Check AWS IAM permissions, VPC/subnet/security-group configuration, "
                    "ECS task definition environment variables, and AWS service quotas in the console. "
                    "Review CloudWatch logs for the Fargate task for the full AWS error message."
                ),
                "confidence": rca_result.get("confidence", "medium"),
            }

        elif bug_category == "quota_billing":
            _stream_progress("**Classification: quota_billing** — Rate limit / quota exhaustion detected.\n\n")
            code_review_report = {
                "category": "quota_billing",
                "root_cause": rca_result.get("root_cause", "API rate limit or quota exhaustion"),
                "suggested_fix": (
                    "Check API provider dashboards (OpenAI, Anthropic, AWS) for quota limits and usage. "
                    "Add retry logic with exponential back-off in the skill or upgrade the plan. "
                    "For AWS, request a service quota increase via the Service Quotas console."
                ),
                "confidence": rca_result.get("confidence", "high"),
            }

        else:
            _stream_progress("**Classification: skill_config** — Flowgram/prompt fix in progress…\n\n")

        # ======================================================
        # Step 4 — Orchestrator composes final report (streamed)
        # ======================================================
        _stream_progress("**Step 4/4** — Composing report…\n\n")

        # Fill runtime variables into the orchestrator prompt.
        # Keep the truncation signal here too so the orchestrator knows the log was cut.
        _ORCH_LOG_LIMIT = 4000
        if len(log_content) > _ORCH_LOG_LIMIT:
            _orch_remaining = log_total_bytes - _ORCH_LOG_LIMIT
            orch_log_snippet = (
                log_content[:_ORCH_LOG_LIMIT]
                + f"\n[...LOG TRUNCATED: {_orch_remaining:,} bytes not shown...]"
            )
        else:
            orch_log_snippet = log_content + (truncated_note if is_truncated else "")

        _user_lang = _get_user_lang_for_session(env, owner, session_id)
        _lang_directive = _build_language_directive(_user_lang)
        final_system = _lang_directive + orchestrator_prompt.replace(
            "{flowgram_json}", flowgram_json_str
        ).replace(
            "{run_log}", orch_log_snippet
        ).replace(
            "{user_observation}", user_observation or "(not provided)"
        ).replace(
            "{expected_behavior}", expected_behavior or "(not provided)"
        )

        code_review_section = ""
        if code_review_report:
            code_review_section = f"\n\n--- CODE REVIEW / CLASSIFICATION REPORT ---\nBug Category: {bug_category}\n{json.dumps(code_review_report, ensure_ascii=False, indent=2)}"

        final_user_msg = f"""Here are the outputs from each analysis sub-agent.
Synthesize them into a single, clear, actionable report.

Bug Category: {bug_category}

--- LOG PARSER OUTPUT ---
{parsed_events_text}

--- FLOWGRAM CORRELATOR OUTPUT ---
{correlation_text}

--- ROOT CAUSE ANALYZER OUTPUT ---
{rca_text}{code_review_section}"""

        # Stream the final orchestrator output
        from langchain_core.messages import SystemMessage as _SM, HumanMessage as _HM
        full_content_parts: List[str] = []

        for chunk in llm.stream([_SM(content=final_system), _HM(content=final_user_msg)]):
            text = chunk.content if hasattr(chunk, "content") else str(chunk)
            if not text:
                continue
            full_content_parts.append(text)
            try:
                _publish(
                    env, owner=owner, session_id=session_id,
                    flowgram_id=flowgram_id,
                    event_type="skill_editor.chat.stream_chunk",
                    payload={"messageId": analysis_message_id, "chunk": text, "index": chunk_index},
                )
            except Exception:
                pass
            chunk_index += 1

        full_content = "".join(full_content_parts)
        logger.info(f"[reqLogAnalysis] Final report complete, length={len(full_content)}")

        # Persist structured RCA result as lastRunError in session metadata so the
        # CodeAgent has a typed, targeted fix signal on the next sendSkillEditorChatMessage.
        if isinstance(rca_result, dict) and session_id:
            try:
                session = _load_session(env, owner, session_id) or {}
                last_run_error: Dict[str, Any] = {
                    "failed_node_id": rca_result.get("failed_node_id"),
                    "failed_node_type": rca_result.get("failed_node_type"),
                    "error_type": rca_result.get("error_type"),
                    "error_message": rca_result.get("error_message"),
                    "input_at_failure": rca_result.get("input_at_failure"),
                    "fix_hypothesis": rca_result.get("hypothesis"),
                    "bug_category": bug_category,
                    "fix_tier": rca_result.get("fix_tier"),
                    "iteration": 1,
                }
                if code_review_report:
                    last_run_error["code_review_report"] = code_review_report
                session["lastRunError"] = last_run_error
                session["updatedAt"] = _utc_now_iso()
                _save_session(env, owner, session)
                logger.info(f"[reqLogAnalysis] Persisted lastRunError (category={bug_category}) to session {session_id}")
            except Exception as e:
                logger.warning(f"[reqLogAnalysis] Failed to persist lastRunError: {e}")

        # Publish stream_end
        try:
            _publish(
                env, owner=owner, session_id=session_id,
                flowgram_id=flowgram_id,
                event_type="skill_editor.chat.stream_end",
                payload={
                    "messageId": analysis_message_id,
                    "fullContent": full_content,
                    "state": "complete",
                    "intent": "log_analysis",
                },
            )
        except Exception as pub_err:
            logger.warning(f"[reqLogAnalysis] Error publishing stream_end: {pub_err}")

        return {"status": "ok"}

    except Exception as e:
        import traceback
        logger.error(f"[reqLogAnalysis] Error: {e}")
        logger.error(f"[reqLogAnalysis] Traceback: {traceback.format_exc()}")
        try:
            _publish(
                env, owner=owner, session_id=session_id,
                flowgram_id=flowgram_id,
                event_type="skill_editor.chat.stream_end",
                payload={
                    "messageId": analysis_message_id,
                    "fullContent": f"Error analyzing log: {e}",
                    "state": "error",
                    "intent": "log_analysis",
                },
            )
        except Exception:
            pass
        return {"status": f"error: {e}"}


def _run_debug_analysis_loop(
    env: _Env,
    owner: str,
    session_id: Optional[str],
    flowgram_id: Optional[str],
    workspace: DebugWorkspace,
    llm: Any,
    analysis_message_id: str,
    _stream_progress: Any,
    user_observation: str,
    expected_behavior: str,
) -> str:
    """Multi-round analysis loop reading from the local debug workspace.

    Each round runs the full 4-step pipeline (log_parser → flowgram_correlator →
    root_cause_analyzer → orchestrator) for one skill, using local files.

    Returns the final assembled report as a string.
    """
    from langchain_core.messages import SystemMessage as _SM, HumanMessage as _HM

    skill_names = list(workspace.skill_dirs.keys())
    all_reports: List[str] = []
    chunk_index = [0]  # mutable container for closure

    def _publish_chunk(text: str) -> None:
        try:
            from agent.ec_tasks.appsync_pubsub import publish_skill_editor_stream_event
            _publish(
                env, owner=owner, session_id=session_id,
                flowgram_id=flowgram_id,
                event_type="skill_editor.chat.stream_chunk",
                payload={"messageId": analysis_message_id, "chunk": text, "index": chunk_index[0]},
            )
        except Exception:
            pass
        chunk_index[0] += 1

    # Load prompts once (reused across skill loops)
    try:
        from agent.skill_editor.prompt_store import prompt_store as _ps
        log_parser_prompt = _ps.get("log_parser", default="Parse the following log into structured JSON events.")
        correlator_prompt = _ps.get("flowgram_correlator", default="Correlate parsed events with the flowgram.")
        rca_prompt = _ps.get("root_cause_analyzer", default="Determine root cause and suggest fixes.")
        orchestrator_prompt = _ps.get(
            "log_analysis_orchestrator",
            default="Analyze the log, correlate with the flowgram, and provide a diagnosis.",
        )
    except Exception as _pe:
        logger.warning(f"[debug_analysis_loop] Failed to load prompts: {_pe}")
        log_parser_prompt = correlator_prompt = rca_prompt = orchestrator_prompt = ""

    # Read log content from workspace
    log_content = ""
    log_total_bytes = 0
    if workspace.log_path and os.path.isfile(workspace.log_path):
        try:
            log_total_bytes = os.path.getsize(workspace.log_path)
            with open(workspace.log_path, "r", encoding="utf-8", errors="replace") as fh:
                log_content = fh.read(_LOG_ANALYSIS_MAX_BYTES)
            truncated_note = ""
            if log_total_bytes > _LOG_ANALYSIS_MAX_BYTES:
                remaining = log_total_bytes - _LOG_ANALYSIS_MAX_BYTES
                truncated_note = (
                    f"\n\n[LOG TRUNCATED: showing first {_LOG_ANALYSIS_MAX_BYTES // 1024} KB "
                    f"of {log_total_bytes // 1024} KB total. {remaining // 1024} KB not shown.]"
                )
                log_content += truncated_note
        except Exception as e:
            logger.warning(f"[debug_analysis_loop] Log read failed: {e}")

    # Pre-check: LLM provider quota exhaustion. Short-circuit before per-skill
    # pipeline runs — quota is the most user-actionable failure class.
    _quota_hit = _detect_llm_quota_exhaustion(log_content)
    if _quota_hit:
        msg = (
            f"### ⚠️ LLM Quota Exhaustion Detected\n\n"
            f"The skill failed because the **{_quota_hit['provider']}** account "
            f"hit a quota / billing limit. No skill or code fix will resolve this — "
            f"the account needs attention.\n\n"
            f"**Signal**: `{_quota_hit['signal']}`\n\n"
            f"**Log line**:\n```\n{_quota_hit['line']}\n```\n\n"
            f"**What to do:**\n"
            f"1. Check your {_quota_hit['provider']} dashboard for current usage and quota.\n"
            f"2. Recharge credits or upgrade the plan.\n"
            f"3. If you're rate-limited (not out of quota), add retry/back-off in the skill.\n\n"
            f"_(Skipping deeper RCA — quota is the obvious cause.)_\n"
        )
        _stream_progress(msg)
        return msg

    if not skill_names:
        # No specific skills selected — run log-only analysis
        skill_names = ["(no skill selected)"]
        workspace.skill_dirs["(no skill selected)"] = workspace.root

    for skill_idx, skill_name in enumerate(skill_names):
        _stream_progress(f"\n\n### Skill {skill_idx + 1}/{len(skill_names)}: **{skill_name}**\n\n")

        skill_dir = workspace.skill_dirs.get(skill_name, "")

        # Load flowgram from workspace
        flowgram_json_str = ""
        fg_path = os.path.join(skill_dir, "flowgram.json") if skill_dir else ""
        if os.path.isfile(fg_path):
            try:
                with open(fg_path, "r", encoding="utf-8") as fh:
                    fg_raw = json.load(fh)
                fg_str = json.dumps(fg_raw, ensure_ascii=False)
                flowgram_json_str = fg_str[:_MAX_FLOWGRAM_INLINE] if len(fg_str) > _MAX_FLOWGRAM_INLINE else fg_str
            except Exception as e:
                logger.warning(f"[debug_analysis_loop] Flowgram read failed for {skill_name}: {e}")

        # Load DB record summary
        db_record = workspace.db_records.get(skill_name, {})
        db_summary = ""
        if db_record:
            db_summary = (
                f"\n## DB Record (agent_skills)\n"
                f"- id: {db_record.get('id', 'N/A')}\n"
                f"- version: {db_record.get('version', 'N/A')}\n"
                f"- level: {db_record.get('level', 'N/A')}\n"
                f"- tags: {db_record.get('tags', 'N/A')}\n"
                f"- updated_at: {db_record.get('updated_at', 'N/A')}\n"
            )

        # ---- Step 1: Log Parser ----
        _stream_progress("**Step 1/4** — Parsing log events…\n\n")
        parser_input = (
            f"Parse the following skill-run log into structured events.\n\n"
            f"Skill: {skill_name}{db_summary}\n\n"
            f"--- BEGIN LOG ---\n{log_content}\n--- END LOG ---"
        )
        parsed_result = _run_sub_agent(llm, log_parser_prompt, parser_input,
                                       label=f"{skill_name}:log_parser", tool_schema=_LOG_PARSER_TOOL)
        parsed_events_text = json.dumps(parsed_result, ensure_ascii=False) if isinstance(parsed_result, dict) else str(parsed_result)
        _stream_progress("**Step 1 complete** — Log parsed.\n\n")

        # ---- Step 2: Flowgram Correlator ----
        _stream_progress("**Step 2/4** — Correlating with flowgram…\n\n")
        correlator_input = (
            f"Correlate the following parsed log events with the flowgram for skill '{skill_name}'.\n\n"
            f"--- PARSED EVENTS ---\n{parsed_events_text}\n\n"
            f"--- FLOWGRAM ---\n{flowgram_json_str or '(not available)'}"
        )
        correlation_result = _run_sub_agent(llm, correlator_prompt, correlator_input,
                                            label=f"{skill_name}:correlator", tool_schema=_FLOWGRAM_CORRELATOR_TOOL)
        correlation_text = json.dumps(correlation_result, ensure_ascii=False) if isinstance(correlation_result, dict) else str(correlation_result)
        _stream_progress("**Step 2 complete** — Correlation done.\n\n")

        # ---- Step 3: Root Cause Analyzer ----
        _stream_progress("**Step 3/4** — Analyzing root cause…\n\n")
        rca_input = (
            f"Determine the root cause based on the following.\n\n"
            f"--- CORRELATION MAP ---\n{correlation_text}\n\n"
            f"--- USER OBSERVATION ---\n{user_observation or '(not provided)'}\n\n"
            f"--- EXPECTED BEHAVIOR ---\n{expected_behavior or '(not provided)'}\n\n"
            f"--- FLOWGRAM (for reference) ---\n{flowgram_json_str or '(not available)'}"
        )
        rca_result = _run_sub_agent(llm, rca_prompt, rca_input,
                                    label=f"{skill_name}:rca", tool_schema=_ROOT_CAUSE_TOOL)
        if not isinstance(rca_result, dict):
            rca_result = {}
        rca_text = json.dumps(rca_result, ensure_ascii=False)
        _stream_progress("**Step 3 complete** — Root cause identified.\n\n")

        # ---- Step 3b: Classification routing (reuse shared logic) ----
        _quick_cat = _quick_classify(log_content + " " + rca_result.get("error_message", ""))
        bug_category = rca_result.get("bug_category") or _quick_cat or "skill_config"
        code_review_report: Optional[Dict[str, Any]] = None

        if bug_category == "platform_code":
            _stream_progress("**Classification: platform_code** — Running code review agent…\n\n")
            try:
                code_review_report = _run_code_review_agent(llm, rca_result, log_content)
            except Exception as cr_err:
                logger.warning(f"[debug_analysis_loop] Code review failed: {cr_err}")
            if isinstance(code_review_report, dict):
                try:
                    code_review_report["code_fix_agent"] = _run_code_fix_agent_placeholder(
                        code_review_report, rca_result
                    )
                except Exception:
                    pass
            _stream_progress("**Code review complete.**\n\n")
        elif bug_category == "infra_config":
            _stream_progress("**Classification: infra_config** — Infrastructure issue detected.\n\n")
            code_review_report = {
                "category": "infra_config",
                "root_cause": rca_result.get("root_cause", "AWS/infrastructure configuration error"),
                "suggested_fix": "Check IAM permissions, VPC/subnet, ECS task definition, and AWS service quotas.",
            }
        elif bug_category == "quota_billing":
            _stream_progress("**Classification: quota_billing** — Rate limit / quota exhaustion.\n\n")
            code_review_report = {
                "category": "quota_billing",
                "root_cause": rca_result.get("root_cause", "API rate limit or quota exhaustion"),
                "suggested_fix": "Check API provider dashboards. Add retry with exponential back-off or upgrade the plan.",
            }

        # ---- Step 4: Orchestrator ----
        _stream_progress("**Step 4/4** — Composing report…\n\n")
        _ORCH_LOG_LIMIT = 4000
        orch_log_snippet = log_content[:_ORCH_LOG_LIMIT] if len(log_content) > _ORCH_LOG_LIMIT else log_content
        code_review_section = ""
        if code_review_report:
            code_review_section = f"\n\n--- CODE REVIEW / CLASSIFICATION REPORT ---\nBug Category: {bug_category}\n{json.dumps(code_review_report, ensure_ascii=False, indent=2)}"

        _user_lang = _get_user_lang_for_session(env, owner, session_id)
        _lang_directive = _build_language_directive(_user_lang)
        final_system = _lang_directive + orchestrator_prompt.replace(
            "{flowgram_json}", flowgram_json_str or "(not available)"
        ).replace("{run_log}", orch_log_snippet).replace(
            "{user_observation}", user_observation or "(not provided)"
        ).replace("{expected_behavior}", expected_behavior or "(not provided)")

        final_user_msg = (
            f"Skill under analysis: **{skill_name}**\nBug Category: {bug_category}\n\n"
            f"--- LOG PARSER OUTPUT ---\n{parsed_events_text}\n\n"
            f"--- FLOWGRAM CORRELATOR OUTPUT ---\n{correlation_text}\n\n"
            f"--- ROOT CAUSE ANALYZER OUTPUT ---\n{rca_text}{code_review_section}"
        )

        skill_report_parts: List[str] = []
        for chunk in llm.stream([_SM(content=final_system), _HM(content=final_user_msg)]):
            text = chunk.content if hasattr(chunk, "content") else str(chunk)
            if text:
                skill_report_parts.append(text)
                _publish_chunk(text)

        skill_report = "".join(skill_report_parts)
        all_reports.append(f"## Skill: {skill_name}\n\n{skill_report}")

        # Write per-skill report to workspace
        try:
            skill_dir_path = workspace.skill_dirs.get(skill_name, workspace.root)
            report_path = os.path.join(skill_dir_path, "analysis_report.md")
            with open(report_path, "w", encoding="utf-8") as fh:
                fh.write(f"# Debug Analysis Report — {skill_name}\n\n")
                fh.write(f"Generated: {_utc_now_iso()}\n\n")
                fh.write(skill_report)
        except Exception:
            pass

    return "\n\n---\n\n".join(all_reports)


def _handle_req_debug_analysis(event: Dict[str, Any]) -> Dict[str, Any]:
    """Handle reqDebugAnalysis — full multi-skill debug session.

    Flow:
      1. Parse input (skill_names, log_s3_key or log_file_name, observation, etc.)
      2. Assemble debug workspace: download log + flowgrams from S3, fetch DB rows
      3. Run multi-skill analysis loop (4-step pipeline per skill, reading from local files)
      4. Stream progress + final report via AppSync
      5. Persist structured lastRunError to session

    GraphQL input (DebugAnalysisInput):
      sessionId: String
      skillNames: [String]          — from multi-select Q&A
      logFileName: String           — S3 key or filename (passed after upload)
      userObservation: String
      expectedBehavior: String
      flowgramId: String
    """
    logger.info("[reqDebugAnalysis] Starting handler")
    env = _load_env()
    args = event.get("arguments") or {}
    input_ = args.get("input") or {}
    owner = _owner_from_event(event)

    session_id = input_.get("sessionId") or input_.get("session_id")
    flowgram_id = input_.get("flowgramId") or input_.get("flowgram_id")
    skill_names: List[str] = input_.get("skillNames") or input_.get("skill_names") or []
    log_file_name = (input_.get("logFileName") or input_.get("log_file_name") or "").strip()
    user_observation = (input_.get("userObservation") or input_.get("user_observation") or "").strip()
    expected_behavior = (input_.get("expectedBehavior") or input_.get("expected_behavior") or "").strip()

    logger.info(
        f"[reqDebugAnalysis] owner={owner}, skills={skill_names}, "
        f"log={log_file_name}, session={session_id}"
    )

    analysis_message_id = str(uuid4())

    def _stream_progress(msg: str) -> None:
        try:
            _publish(
                env, owner=owner, session_id=session_id,
                flowgram_id=flowgram_id,
                event_type="skill_editor.chat.stream_chunk",
                payload={"messageId": analysis_message_id, "chunk": msg, "index": 0},
            )
        except Exception:
            pass

    try:
        # --- Init LLM ---
        anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
        openai_key = os.environ.get("OPENAI_API_KEY")
        model_name = os.environ.get("SKILL_EDITOR_MODEL", "")
        if anthropic_key:
            from langchain_community.chat_models import ChatAnthropic
            llm = ChatAnthropic(model=model_name or "claude-sonnet-4-6", api_key=anthropic_key, temperature=0)
        elif openai_key:
            from langchain_openai import ChatOpenAI
            llm = ChatOpenAI(model=model_name or "gpt-4o", api_key=openai_key, temperature=0)
        else:
            return {"status": "error: LLM not configured — set ANTHROPIC_API_KEY or OPENAI_API_KEY"}

        # --- Locate log in S3 ---
        log_s3_key: Optional[str] = None
        if log_file_name:
            log_s3_key = _find_log_file_key(env, owner, log_file_name)
            if not log_s3_key:
                _stream_progress(f"⚠️ Log file not found: `{log_file_name}`. Proceeding without log.\n\n")

        # --- Assemble workspace ---
        _stream_progress("**Assembling debug workspace** — downloading log, flowgrams, and DB records…\n\n")
        workspace = _assemble_debug_workspace(
            env=env,
            owner=owner,
            session_id=session_id or str(uuid4()),
            skill_names=skill_names,
            log_s3_key=log_s3_key,
        )
        _stream_progress(
            f"**Workspace ready** at `{workspace.root}`\n"
            f"- Skills: {', '.join(workspace.skill_dirs.keys()) or '(none)'}\n"
            f"- Log: `{workspace.log_path or 'not found'}`\n"
            f"- Source: `{workspace.source_root}`\n\n"
        )

        # --- Run analysis loop ---
        _stream_progress("**Starting multi-skill analysis loop…**\n\n")
        full_report = _run_debug_analysis_loop(
            env=env,
            owner=owner,
            session_id=session_id,
            flowgram_id=flowgram_id,
            workspace=workspace,
            llm=llm,
            analysis_message_id=analysis_message_id,
            _stream_progress=_stream_progress,
            user_observation=user_observation,
            expected_behavior=expected_behavior,
        )

        # Write master report to workspace
        try:
            master_report_path = os.path.join(workspace.root, "master_report.md")
            with open(master_report_path, "w", encoding="utf-8") as fh:
                fh.write(f"# Debug Analysis Master Report\n\nGenerated: {_utc_now_iso()}\n\n")
                fh.write(full_report)
        except Exception:
            pass

        # --- Publish stream_end ---
        try:
            _publish(
                env, owner=owner, session_id=session_id,
                flowgram_id=flowgram_id,
                event_type="skill_editor.chat.stream_end",
                payload={
                    "messageId": analysis_message_id,
                    "fullContent": full_report,
                    "state": "complete",
                    "intent": "debug_analysis",
                    "workspacePath": workspace.root,
                },
            )
        except Exception as pub_err:
            logger.warning(f"[reqDebugAnalysis] stream_end publish failed: {pub_err}")

        return {"status": "ok", "workspacePath": workspace.root}

    except Exception as e:
        import traceback
        logger.error(f"[reqDebugAnalysis] Error: {e}")
        logger.error(f"[reqDebugAnalysis] Traceback: {traceback.format_exc()}")
        try:
            _publish(
                env, owner=owner, session_id=session_id,
                flowgram_id=flowgram_id,
                event_type="skill_editor.chat.stream_end",
                payload={
                    "messageId": analysis_message_id,
                    "fullContent": f"Debug analysis error: {e}",
                    "state": "error",
                    "intent": "debug_analysis",
                },
            )
        except Exception:
            pass
        return {"status": f"error: {e}"}


def _handle_request_skill_file_upload_url(event: Dict[str, Any]) -> Dict[str, Any]:
    logger.info("[requestSkillFileUploadUrl] Starting handler")
    env = _load_env()
    args = event.get("arguments") or {}
    input_ = args.get("input") or {}

    skill_id = input_.get("skillId") or args.get("skillId")
    owner = input_.get("owner") or args.get("owner") or _owner_from_event(event)
    file_name = input_.get("fileName") or args.get("fileName")

    if not skill_id or not owner or not file_name:
        raise RuntimeError("skillId, owner and fileName are required")

    s3_key = _s3_key(_build_skills_s3_prefix(env, owner, skill_id), file_name)
    client = _s3_client()

    expires = 900  # 15 minutes
    try:
        url = client.generate_presigned_url(
            "put_object",
            Params={"Bucket": env.s3_bucket, "Key": s3_key},
            ExpiresIn=expires,
        )
        logger.info(f"[requestSkillFileUploadUrl] Generated presigned PUT for {s3_key}")
        return {"uploadUrl": url, "s3Key": s3_key, "expiresIn": expires}
    except Exception as e:
        logger.error(f"[requestSkillFileUploadUrl] Failed to create presigned url: {e}")
        raise


def _handle_process_skill_zip_upload(event: Dict[str, Any]) -> Dict[str, Any]:
    """Download a skill zip from S3, extract contents, and write individual files."""
    logger.info("[processSkillZipUpload] Starting handler")
    env = _load_env()
    args = event.get("arguments") or {}
    input_ = args.get("input") or {}

    skill_name = input_.get("skillName") or args.get("skillName")
    owner = input_.get("owner") or args.get("owner") or _owner_from_event(event)

    if not skill_name or not owner:
        raise RuntimeError("skillName and owner are required")

    safe_skill = _safe_skill_dir_name(skill_name)
    skill_root = _skill_root_prefix(env, owner, safe_skill)
    zip_key = _s3_key(skill_root, f"{safe_skill}.zip")

    client = _s3_client()
    bucket = env.s3_bucket

    # Download the zip
    try:
        resp = client.get_object(Bucket=bucket, Key=zip_key)
        zip_bytes = resp["Body"].read()
    except Exception as e:
        logger.error(f"[processSkillZipUpload] Failed to download zip {zip_key}: {e}")
        return {"success": False, "error": f"Zip not found: {zip_key}", "extractedFiles": []}

    # Extract and upload individual files
    extracted: List[str] = []
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
            for name in zf.namelist():
                # Skip directories and hidden files
                if name.endswith("/") or "/__MACOSX" in name or name.startswith("__MACOSX"):
                    continue

                content = zf.read(name)
                target_key = _s3_key(skill_root, name)

                content_type = "application/json" if name.endswith(".json") else "application/octet-stream"
                if name.endswith(".md"):
                    content_type = "text/markdown"
                elif name.endswith(".py"):
                    content_type = "text/x-python"

                client.put_object(
                    Bucket=bucket,
                    Key=target_key,
                    Body=content,
                    ContentType=content_type,
                )
                extracted.append(target_key)
                logger.info(f"[processSkillZipUpload] Extracted: {target_key} ({len(content)} bytes)")
    except zipfile.BadZipFile:
        logger.error(f"[processSkillZipUpload] Invalid zip file: {zip_key}")
        return {"success": False, "error": "Invalid zip file", "extractedFiles": []}

    # Ensure skill directory structure
    _ensure_skill_dirs(env, owner, safe_skill)

    logger.info(f"[processSkillZipUpload] Done. Extracted {len(extracted)} files from {zip_key}")
    return {"success": True, "error": None, "extractedFiles": extracted}


def _handle_request_skill_file_download_url(event: Dict[str, Any]) -> Dict[str, Any]:
    logger.info("[requestSkillFileDownloadUrl] Starting handler")
    env = _load_env()
    args = event.get("arguments") or {}
    owner = args.get("owner") or _owner_from_event(event)
    skill_id = args.get("skillId") or args.get("skillID") or args.get("id")

    if not owner or not skill_id:
        raise RuntimeError("owner and skillId are required")

    prefix = _build_skills_s3_prefix(env, owner, skill_id)
    if prefix and not prefix.endswith("/"):
        prefix = prefix + "/"

    client = _s3_client()
    try:
        resp = client.list_objects_v2(Bucket=env.s3_bucket, Prefix=prefix, MaxKeys=100)
        contents = resp.get("Contents") or []
        # Prefer largest or most recent object; pick the first valid object for now
        obj = None
        if contents:
            # sort by LastModified desc
            contents.sort(key=lambda o: o.get("LastModified") or 0, reverse=True)
            for c in contents:
                k = c.get("Key")
                if k and not k.endswith("/"):
                    obj = c
                    break

        if not obj:
            raise RuntimeError("No skill files found for given owner/skillId")

        key = obj.get("Key")
        expires = 900
        url = client.generate_presigned_url(
            "get_object",
            Params={"Bucket": env.s3_bucket, "Key": key},
            ExpiresIn=expires,
        )
        logger.info(f"[requestSkillFileDownloadUrl] Generated presigned GET for {key}")
        return {"downloadUrl": url, "s3Key": key, "expiresIn": expires}
    except Exception as e:
        logger.error(f"[requestSkillFileDownloadUrl] Error: {e}")
        raise


def _handle_delete_skill_files(event: Dict[str, Any]) -> Dict[str, Any]:
    logger.info("[deleteSkillFiles] Starting handler")
    env = _load_env()
    args = event.get("arguments") or {}
    owner = args.get("owner") or _owner_from_event(event)
    skill_id = args.get("skillId")

    if not owner or not skill_id:
        return {"success": False, "error": "owner and skillId are required"}

    prefix = _build_skills_s3_prefix(env, owner, skill_id)
    if prefix and not prefix.endswith("/"):
        prefix = prefix + "/"

    client = _s3_client()
    try:
        # List objects under the prefix
        to_delete = []
        continuation = None
        while True:
            kwargs = {"Bucket": env.s3_bucket, "Prefix": prefix}
            if continuation:
                kwargs["ContinuationToken"] = continuation
            resp = client.list_objects_v2(**kwargs)
            for obj in resp.get("Contents") or []:
                k = obj.get("Key")
                if k and not k.endswith("/"):
                    to_delete.append({"Key": k})
            if resp.get("IsTruncated"):
                continuation = resp.get("NextContinuationToken")
                continue
            break

        if not to_delete:
            logger.info("[deleteSkillFiles] No objects to delete")
            return {"success": True}

        # Batch delete (max 1000 per request)
        for i in range(0, len(to_delete), 1000):
            batch = to_delete[i : i + 1000]
            client.delete_objects(Bucket=env.s3_bucket, Delete={"Objects": batch, "Quiet": True})

        logger.info(f"[deleteSkillFiles] Deleted {len(to_delete)} objects under {prefix}")
        return {"success": True}
    except Exception as e:
        logger.error(f"[deleteSkillFiles] Error deleting objects: {e}")
        return {"success": False, "error": str(e)}


def _handle_load_skill_editor_contexts(event: Dict[str, Any]) -> Dict[str, Any]:
    """Load skill editor contexts from S3 (per user, per skill)."""
    logger.info("[loadSkillEditorContexts] Starting handler")
    env = _load_env()
    args = event.get("arguments") or {}
    input_ = args.get("input") or {}
    
    owner = _owner_from_event(event)
    skill_names = input_.get("skillNames") or []
    skill_ids = input_.get("skillIds") or []
    
    logger.info(f"[loadSkillEditorContexts] owner={owner}, skillNames={skill_names}, skillIds={skill_ids}")
    
    items: List[Dict[str, Any]] = []
    
    # If specific skill names requested, load those
    if skill_names:
        logger.info(f"[loadSkillEditorContexts] Loading {len(skill_names)} specific skills")
        for idx, skill_name in enumerate(skill_names):
            resolved_name = _safe_skill_dir_name(skill_name)
            _ensure_context_dirs(env, owner, resolved_name)
            keys = _list_context_session_keys(env, owner, resolved_name)
            latest_key = _pick_latest_session_key(keys)
            if not latest_key:
                logger.info(f"[loadSkillEditorContexts] No sessions found for skill: {resolved_name}")
                continue

            logger.info(f"[loadSkillEditorContexts] Fetching latest session: {latest_key}")
            context_data = _load_context_session(env, latest_key)
            if context_data is not None:
                try:
                    resp = _s3_client().head_object(Bucket=env.s3_bucket, Key=latest_key)
                    last_modified = resp.get("LastModified")
                    updated_at = last_modified.isoformat() if last_modified else _utc_now_iso()
                except Exception as e:
                    logger.warning(f"[loadSkillEditorContexts] Failed to get LastModified for {latest_key}: {e}")
                    updated_at = _utc_now_iso()

                items.append({
                    "skillId": skill_ids[idx] if idx < len(skill_ids) else None,
                    "skillName": resolved_name,
                    "context": json.dumps(context_data) if isinstance(context_data, dict) else context_data,
                    "updatedAt": updated_at,
                })
    
    # If no specific skills requested, list all available contexts for this user
    elif not skill_names and not skill_ids:
        prefix = _norm_prefix(env.s3_key_root)
        user_dir = _safe_user_dir_name(owner)
        skills_prefix = _s3_key(prefix, user_dir, "my_skills")
        if skills_prefix:
            skills_prefix += "/"

        logger.info(f"[loadSkillEditorContexts] Listing all skills with prefix: {skills_prefix}")
        keys = _s3_list_keys(bucket=env.s3_bucket, prefix=skills_prefix)
        logger.info(f"[loadSkillEditorContexts] Found {len(keys)} keys")

        latest_by_skill: Dict[str, str] = {}
        for key in keys:
            parts = key.split("/")
            if "my_skills" not in parts:
                continue
            idx = parts.index("my_skills")
            if idx + 1 >= len(parts):
                continue
            skill_name = parts[idx + 1]
            if "/contexts/sessions/" not in key or not key.endswith(".json"):
                continue
            latest_key = latest_by_skill.get(skill_name)
            if latest_key is None:
                latest_by_skill[skill_name] = key
                continue
            prev_dt = _parse_session_filename(latest_key.split("/")[-1])
            cur_dt = _parse_session_filename(key.split("/")[-1])
            if cur_dt and (not prev_dt or cur_dt > prev_dt):
                latest_by_skill[skill_name] = key

        for skill_name, key in latest_by_skill.items():
            logger.info(f"[loadSkillEditorContexts] Loading latest session for skill: {skill_name} from {key}")
            context_data = _load_context_session(env, key)
            if context_data is not None:
                try:
                    resp = _s3_client().head_object(Bucket=env.s3_bucket, Key=key)
                    last_modified = resp.get("LastModified")
                    updated_at = last_modified.isoformat() if last_modified else _utc_now_iso()
                except Exception as e:
                    logger.warning(f"[loadSkillEditorContexts] Failed to get LastModified for {key}: {e}")
                    updated_at = _utc_now_iso()

                items.append({
                    "skillId": None,
                    "skillName": skill_name,
                    "context": json.dumps(context_data) if isinstance(context_data, dict) else context_data,
                    "updatedAt": updated_at,
                })
    
    logger.info(f"[loadSkillEditorContexts] Returning {len(items)} context items")
    return {"items": items}


# ---------------------------------------------------------------------------
# Auto-cycle constants
# ---------------------------------------------------------------------------
_MAX_AUTO_CYCLE_ITERATIONS = int(os.environ.get("SKILL_AUTO_CYCLE_MAX", "3"))


def _sns_client():
    return boto3.client("sns")


def _handle_skill_run_result(event: Dict[str, Any]) -> Dict[str, Any]:
    """Handle SNS notifications from Fargate task completion for the auto-cycle loop.

    The Fargate skill-runner task must publish to the SNS topic configured via
    SKILL_RUN_RESULT_TOPIC_ARN when a run finishes (success or failure).

    Expected SNS message JSON shape:
    {
        "owner":            "<user-id>",
        "session_id":       "<chat-session-id>",
        "run_id":           "<run-id>",
        "skill_name":       "<skill-name>",
        "success":          true | false,
        "iteration":        <int>,        # 0-based, incremented each auto-cycle loop
        "log_s3_key":       "<s3-key>",   # S3 key of the run log
        "failed_node_id":   "<node-id>" | null,
        "failed_node_type": "<type>"     | null,
        "error_type":       "<ErrorType>" | null,
        "error_message":    "<message>"  | null,
        "input_at_failure": {<dict>}     | null
    }

    On success: publish a completion notification to the user via AppSync.
    On failure (iteration < _MAX_AUTO_CYCLE_ITERATIONS):
      1. Persist structured lastRunError to session metadata.
      2. Trigger log analysis pipeline.
      3. Re-generate the flowgram with fix context.
      4. Increment iteration and re-run the skill via Fargate.
    On failure (iteration >= _MAX_AUTO_CYCLE_ITERATIONS): escalate to user.

    Fargate-side change required (in your skill-runner container):
        import boto3, json, os
        sns = boto3.client("sns")
        sns.publish(
            TopicArn=os.environ["SKILL_RUN_RESULT_TOPIC_ARN"],
            Message=json.dumps({
                "owner": owner, "session_id": session_id, "run_id": run_id,
                "skill_name": skill_name, "success": success,
                "iteration": iteration, "log_s3_key": log_s3_key,
                "failed_node_id": failed_node_id, "failed_node_type": failed_node_type,
                "error_type": error_type, "error_message": error_message,
                "input_at_failure": input_at_failure,
            }),
            Subject="skill_run_result",
        )
    """
    logger.info("[skillRunResult] Received SNS notification")
    env = _load_env()

    # SNS wraps the payload in Records[0].Sns.Message
    records = event.get("Records") or []
    if not records:
        logger.warning("[skillRunResult] No SNS records in event")
        return {"status": "no_records"}

    try:
        sns_body = json.loads(records[0]["Sns"]["Message"])
    except Exception as e:
        logger.error(f"[skillRunResult] Failed to parse SNS message: {e}")
        return {"status": f"parse_error: {e}"}

    owner = sns_body.get("owner", "")
    session_id = sns_body.get("session_id", "")
    run_id = sns_body.get("run_id", "")
    skill_name = sns_body.get("skill_name", "")
    success = bool(sns_body.get("success", False))
    iteration = int(sns_body.get("iteration", 0))
    log_s3_key = sns_body.get("log_s3_key", "")

    logger.info(
        f"[skillRunResult] owner={owner}, session={session_id}, run={run_id}, "
        f"success={success}, iteration={iteration}"
    )

    if success:
        # Run succeeded — notify user via AppSync and clear any stored run error.
        msg = (
            f"✅ Skill **{skill_name}** completed successfully"
            + (f" after {iteration} auto-fix iteration(s)" if iteration > 0 else "")
            + "."
        )
        try:
            _publish(
                env, owner=owner, session_id=session_id, flowgram_id=None,
                event_type="skill_editor.chat.stream_end",
                payload={
                    "messageId": f"run-result-{run_id}",
                    "fullContent": msg,
                    "state": "complete",
                    "intent": "run_complete",
                },
            )
        except Exception as pub_err:
            logger.warning(f"[skillRunResult] Failed to publish success notification: {pub_err}")

        # Clear lastRunError from session so subsequent edits start clean.
        try:
            session = _load_session(env, owner, session_id) or {}
            if session.get("lastRunError"):
                session.pop("lastRunError", None)
                session["updatedAt"] = _utc_now_iso()
                _save_session(env, owner, session)
        except Exception as e:
            logger.warning(f"[skillRunResult] Failed to clear lastRunError: {e}")

        return {"status": "ok"}

    # ---- Run failed ----
    failed_node_id = sns_body.get("failed_node_id")
    failed_node_type = sns_body.get("failed_node_type")
    error_type = sns_body.get("error_type")
    error_message = sns_body.get("error_message", "")
    input_at_failure = sns_body.get("input_at_failure")

    structured_error = {
        "failed_node_id": failed_node_id,
        "failed_node_type": failed_node_type,
        "error_type": error_type,
        "error_message": error_message,
        "input_at_failure": input_at_failure,
        "iteration": iteration + 1,  # next fix attempt number
        "fix_hypothesis": None,  # filled in by log analysis below
    }

    if iteration >= _MAX_AUTO_CYCLE_ITERATIONS:
        # Exceeded retry budget — surface to user for manual intervention.
        logger.warning(
            f"[skillRunResult] Auto-cycle exhausted after {iteration} iterations for run={run_id}"
        )
        msg = (
            f"⚠️ Skill **{skill_name}** failed after {iteration} automatic fix attempt(s).\n\n"
            f"**Last error**: `{error_type}: {error_message}`\n"
            + (f"**Node**: `{failed_node_id}`\n" if failed_node_id else "")
            + "\nPlease review the skill manually or upload the log for detailed analysis."
        )
        try:
            _publish(
                env, owner=owner, session_id=session_id, flowgram_id=None,
                event_type="skill_editor.chat.stream_end",
                payload={
                    "messageId": f"run-result-{run_id}",
                    "fullContent": msg,
                    "state": "error",
                    "intent": "run_complete",
                },
            )
        except Exception as pub_err:
            logger.warning(f"[skillRunResult] Failed to publish exhausted notification: {pub_err}")
        return {"status": "max_iterations_reached"}

    # ---- Auto-cycle: persist error, run log analysis, regenerate, re-run ----
    try:
        session = _load_session(env, owner, session_id) or {}
        session["lastRunError"] = structured_error
        session["updatedAt"] = _utc_now_iso()
        _save_session(env, owner, session)
        logger.info(f"[skillRunResult] Persisted lastRunError to session {session_id}")
    except Exception as e:
        logger.error(f"[skillRunResult] Failed to persist lastRunError: {e}")

    # Notify user that an auto-fix is in progress.
    try:
        _publish(
            env, owner=owner, session_id=session_id, flowgram_id=None,
            event_type="skill_editor.chat.stream_chunk",
            payload={
                "messageId": f"run-result-{run_id}",
                "chunk": (
                    f"🔄 Run failed at node `{failed_node_id or 'unknown'}` "
                    f"(`{error_type}: {error_message[:120]}`). "
                    f"Auto-fixing (attempt {iteration + 1}/{_MAX_AUTO_CYCLE_ITERATIONS})…\n\n"
                ),
                "index": 0,
            },
        )
    except Exception:
        pass

    # Run the log analysis pipeline inline (reuses the existing 4-step pipeline).
    if log_s3_key:
        try:
            log_analysis_event = {
                "arguments": {
                    "input": {
                        "owner": owner,
                        "session_id": session_id,
                        "log_file_name": log_s3_key,
                        "flowgram_json": session.get("cachedFlowgramDict"),
                        "user_observation": f"Node {failed_node_id} failed with {error_type}: {error_message}",
                        "expected_behavior": "Skill completes successfully without errors",
                    }
                },
                "identity": {"username": owner},
            }
            _handle_req_log_analysis(log_analysis_event)
            logger.info("[skillRunResult] Log analysis pipeline completed")
        except Exception as e:
            logger.warning(f"[skillRunResult] Log analysis failed (non-fatal): {e}")

    logger.info(
        f"[skillRunResult] Auto-cycle iteration {iteration + 1} complete. "
        "Frontend should send 'fix it' message to trigger re-generation, "
        "or implement direct re-generation here when code_agent is available."
    )
    return {"status": "auto_cycle_triggered"}


def handler(event, context):
    _ = context

    # SNS events (e.g. skill run result from Fargate) arrive via Records, not info.fieldName.
    if event.get("Records") and event["Records"][0].get("EventSource") == "aws:sns":
        return _handle_skill_run_result(event)

    info = event.get("info") or {}
    field = info.get("fieldName")

    logger.info(f"[handler] Lambda invoked, fieldName={field}")

    try:
        if field == "createSkillEditorChatSession":
            return _handle_create_session(event)
        if field == "getSkillEditorChatSessions":
            return _handle_get_sessions(event)
        if field == "getSkillEditorChatHistory":
            return _handle_get_history(event)
        if field == "sendSkillEditorChatMessage":
            return _handle_send_message(event)
        if field == "cancelSkillEditorChatGeneration":
            return _handle_cancel_generation(event)
        if field == "deleteSkillEditorChatSession":
            return _handle_delete_session(event)
        if field == "loadSkillEditorContexts":
            return _handle_load_skill_editor_contexts(event)
        if field == "listSkillFiles":
            return _handle_list_skill_files(event)
        if field == "openSkillFile":
            result = _handle_read_skill_file(event, allow_skill_name=True)
            return result[0] if isinstance(result, list) and result else None
        if field == "readSkillFile":
            return _handle_read_skill_file(event, allow_skill_name=False)
        if field == "writeSkillFile":
            return _handle_write_skill_file(event)
        if field == "requestSkillFileUploadUrl":
            return _handle_request_skill_file_upload_url(event)
        if field == "processSkillZipUpload":
            return _handle_process_skill_zip_upload(event)
        if field == "requestSkillFileDownloadUrl":
            return _handle_request_skill_file_download_url(event)
        if field == "deleteSkillFiles":
            return _handle_delete_skill_files(event)
        if field == "listSkillRevisions":
            return _handle_list_skill_revisions(event)
        if field == "revertSkillRevision":
            return _handle_revert_skill_revision(event)
        
        # Skill Run Control
        if field == "runSkill":
            return _handle_run_skill(event)
        if field == "cancelRunSkill":
            return _handle_cancel_run_skill(event)
        if field == "pauseRunSkill":
            return _handle_pause_run_skill(event)
        if field == "resumeRunSkill":
            return _handle_resume_run_skill(event)
        if field == "stepRunSkill":
            return _handle_step_run_skill(event)

        # Log / Debug Analysis
        if field == "reqLogAnalysis":
            return _handle_req_log_analysis(event)
        if field == "reqDebugAnalysis":
            return _handle_req_debug_analysis(event)

        logger.error(f"[handler] Unsupported fieldName: {field}")
        raise RuntimeError(f"Unsupported fieldName: {field}")

    except Exception as e:
        import traceback
        error_msg = str(e)
        error_tb = traceback.format_exc()
        logger.error(f"[handler] Unhandled exception in {field}: {error_msg}")
        logger.error(f"[handler] Traceback: {error_tb}")
        
        # For sendSkillEditorChatMessage, the error is already handled with S3 persistence
        # For other operations, re-raise to let AppSync handle the error
        raise
