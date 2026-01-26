import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

import boto3

from agent.ec_tasks.appsync_pubsub import AppSyncApiKeyConfig, publish_skill_editor_stream_event
from agent.skill_editor.skill_editor_agent import SkillEditorAgent, _safe_user_dir_name

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

DEFAULT_DATA_MAPPING: Dict[str, Any] = {
    "developing": {
        "mappings": [],
        "options": {
            "strict": False,
            "apply_order": "top_down",
        },
    },
    "released": {
        "mappings": [],
        "options": {
            "strict": True,
            "apply_order": "top_down",
        },
    },
    "node_transfers": {},
    "event_routing": {},
}


@dataclass(frozen=True)
class _Env:
    s3_bucket: str
    s3_key_root: str
    appsync_api_url: str
    appsync_api_key: str


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_env(name: str) -> str:
    value = (os.environ.get(name) or "").strip()
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def _load_env() -> _Env:
    return _Env(
        s3_bucket=_require_env("S3_BUCKET"),
        s3_key_root=(os.environ.get("S3_KEY_ROOT") or "").strip(),
        appsync_api_url=_require_env("APPSYNC_API_URL"),
        appsync_api_key=_require_env("APPSYNC_API_KEY"),
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


def _owner_from_event(event: Dict[str, Any]) -> str:
    args = (event.get("arguments") or {})
    if isinstance(args.get("input"), dict):
        user_id = args["input"].get("userId")
        if isinstance(user_id, str) and user_id.strip():
            return user_id.strip()

    ident = event.get("identity") or {}
    for key in ("username", "sub", "claims"):
        v = ident.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
        if key == "claims" and isinstance(v, dict):
            c = v.get("email") or v.get("cognito:username")
            if isinstance(c, str) and c.strip():
                return c.strip()

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


def _skill_diagram_dir(env: _Env, owner: str, skill_name: str) -> str:
    return _s3_key(_skill_root_prefix(env, owner, skill_name), "diagram_dir")


def _skill_code_dir(env: _Env, owner: str, skill_name: str) -> str:
    return _s3_key(_skill_root_prefix(env, owner, skill_name), "code_dir")


def _skill_data_mapping_key(env: _Env, owner: str, skill_name: str) -> str:
    return _s3_key(_skill_root_prefix(env, owner, skill_name), "data_mapping.json")


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
    prefix = _norm_prefix(env.s3_key_root)
    user_dir = _safe_user_dir_name(owner)
    return _s3_key(prefix, user_dir)


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


def _resolve_user_key(env: _Env, owner: str, file_path: str) -> str:
    if not file_path or not isinstance(file_path, str):
        raise RuntimeError("filePath is required")

    base = _user_base_prefix(env, owner)
    if file_path.startswith("s3://"):
        without = file_path[len("s3://") :]
        bucket, _, key = without.partition("/")
        if bucket and bucket != env.s3_bucket:
            raise RuntimeError("Invalid bucket for filePath")
        key = _normalize_rel_path(key)
    else:
        key = _normalize_rel_path(file_path)

    if key.startswith(base + "/") or key == base:
        resolved = key
    else:
        resolved = _s3_key(base, key)

    if not resolved.startswith(base + "/") and resolved != base:
        raise RuntimeError("Invalid filePath scope")

    return resolved


def _resolve_user_prefix(env: _Env, owner: str, prefix: Optional[str]) -> str:
    base = _user_base_prefix(env, owner)
    if not prefix:
        return _s3_key(base, "my_skills")

    normalized = _normalize_rel_path(prefix)
    if normalized.startswith(base + "/") or normalized == base:
        resolved = normalized
    else:
        resolved = _s3_key(base, normalized)

    if not resolved.startswith(base + "/") and resolved != base:
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


def _handle_list_skill_files(event: Dict[str, Any]) -> List[Dict[str, Any]]:
    logger.info("[listSkillFiles] Starting handler")
    env = _load_env()
    args = event.get("arguments") or {}
    owner = _owner_from_event(event)

    prefix = _resolve_user_prefix(env, owner, args.get("prefix"))
    limit = args.get("limit")
    continuation = args.get("nextToken")
    if prefix:
        prefix = prefix.rstrip("/") + "/"

    items: List[Dict[str, Any]] = []
    logger.info(f"[listSkillFiles] Listing S3 prefix: {prefix}")

    while True:
        objects, next_token = _s3_list_objects(bucket=env.s3_bucket, prefix=prefix, continuation=continuation)
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
                logger.info(f"[listSkillFiles] Reached limit: {limit}")
                return items

        if not next_token:
            break
        if isinstance(limit, int) and limit > 0 and len(items) >= limit:
            break
        continuation = next_token

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
            from agent.ec_skills.llm_utils.llm_utils import run_async_in_sync

            run_async_in_sync(_do())
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
            if etype not in {"progress", "chunk"}:
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
            from langchain_openai import ChatOpenAI

            api_key = os.environ.get("OPENAI_API_KEY")
            if api_key:
                llm_instance = ChatOpenAI(model="gpt-4o", api_key=api_key)
                logger.info("[sendSkillEditorChatMessage] Using OpenAI LLM (hardcoded)")
            else:
                logger.warning("[sendSkillEditorChatMessage] OPENAI_API_KEY missing; falling back to default LLM selection")
        except Exception as e:
            logger.warning(f"[sendSkillEditorChatMessage] Failed to init OpenAI LLM: {e}")

        agent = SkillEditorAgent(llm=llm_instance, user_name=owner)

        try:
            pipeline_state = session.get("pipelineState")
            if isinstance(pipeline_state, str) and pipeline_state and pipeline_state != "idle":
                logger.info(f"[sendSkillEditorChatMessage] Restoring agent state: {pipeline_state}")
                agent.restore_state(
                    pipeline_state=pipeline_state,
                    current_plan=session.get("currentPlan") if isinstance(session.get("currentPlan"), dict) else session.get("currentPlan"),
                    current_request=session.get("currentRequest") if isinstance(session.get("currentRequest"), str) else None,
                )
        except Exception as e:
            logger.warning(f"[sendSkillEditorChatMessage] Failed to restore agent state: {e}")

        canvas_context = input_.get("canvasContext")
        clarification = input_.get("clarificationResponses")
        recent_context_sessions = _load_recent_context_sessions(env, owner, skill_name, limit=3)
        if isinstance(canvas_context, dict):
            canvas_context = {**canvas_context, "contextSessions": recent_context_sessions}
        elif recent_context_sessions:
            canvas_context = {"contextSessions": recent_context_sessions}

        logger.info(f"[sendSkillEditorChatMessage] Calling agent.process_message_sync, canvas_context_type={type(canvas_context).__name__}")
        response = agent.process_message_sync(
            message=content,
            canvas_context=canvas_context,
            session_id=session_id,
            clarification_responses=clarification,
            on_event=on_event,
        )
        logger.info(f"[sendSkillEditorChatMessage] Agent response received, intent={getattr(response, 'intent', None)}, message_len={len(response.message or '')}")

        logger.info("[sendSkillEditorChatMessage] Publishing stream_end event...")
        try:
            _publish(
                env,
                owner=owner,
                session_id=session_id,
                flowgram_id=flowgram_id,
                event_type="skill_editor.chat.stream_end",
                payload={
                    "messageId": assistant_message_id,
                    "fullContent": response.message or "",
                },
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

        assistant_msg = {
            "id": assistant_message_id,
            "role": "assistant",
            "content": response.message or "",
            "timestamp": _utc_now_iso(),
            "attachments": None,
            "metadata": {
                "state": response.metadata.get("state") if isinstance(getattr(response, "metadata", None), dict) else None,
                "intent": response.intent.value if getattr(response, "intent", None) is not None else None,
                "hasClarification": bool(getattr(response, "clarification", None)),
                "hasPlan": bool(getattr(response, "plan", None)),
                "hasFlowgram": bool(getattr(response, "flowgram", None)),
            },
        }

        if isinstance(history.get("messages"), list):
            history["messages"].append(assistant_msg)

        session["updatedAt"] = _utc_now_iso()
        session["pipelineState"] = agent.pipeline_state.value
        session["currentPlan"] = agent.current_plan.model_dump() if agent.current_plan else None
        session["currentRequest"] = agent.current_request

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
        "flowgram": response.flowgram.model_dump() if response and getattr(response, "flowgram", None) else None,
        "validation": response.validation.model_dump() if response and getattr(response, "validation", None) else None,
    }


def _resolve_skill_name(input_: Dict[str, Any]) -> str:
    canvas_context = input_.get("canvasContext")
    if isinstance(canvas_context, dict):
        name = canvas_context.get("skillName")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return "untitled_skill"


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


def handler(event, context):
    _ = context

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
