"""Cloud file sync for skill source directories via S3 presigned URLs.

Each skill lives in a local directory under ``my_skills/<skill_name>_skill/``.
To sync to cloud we:
  1. Zip the entire skill directory into a temp file.
  2. Request a presigned **upload** URL from the cloud (GraphQL mutation).
  3. PUT the zip to S3 via the presigned URL.

To download from cloud:
  1. Request a presigned **download** URL from the cloud (GraphQL query).
  2. GET the zip from S3.
  3. Unzip into the local skill directory.

Cloud-side contract (to be implemented in Lambda + AppSync schema):
  Mutation: requestSkillFileUploadUrl(input: SkillFileUploadInput!) → SkillFileUploadResult
    input  { skillId: ID!, owner: String!, fileName: String! }
    result { uploadUrl: String!, s3Key: String!, expiresIn: Int }

  Query:   requestSkillFileDownloadUrl(skillId: ID!, owner: String!) → SkillFileDownloadResult
    result { downloadUrl: String!, s3Key: String!, expiresIn: Int }
"""

from __future__ import annotations

import io
import json
import os
import threading
import time
import traceback
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests as http_requests

from utils.logger_helper import logger_helper as logger

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

def _get_my_skills_dir() -> Path:
    """Return the my_skills directory path with proper path resolution.

    In dev mode: <project_root>/my_skills
    In prod mode: <appdata>/my_skills
    
    Now uses unified resolution from extern_skills.
    """
    from agent.ec_skills.extern_skills.extern_skills import user_skills_root
    return user_skills_root()


MY_SKILLS_DIR = _get_my_skills_dir()
_MISSING_DOWNLOAD_URL_LOGGED: set[str] = set()
_MISSING_DOWNLOAD_URL_CACHE: Dict[str, float] = {}
_MISSING_DOWNLOAD_URL_TTL_SECONDS = 120

# ---------------------------------------------------------------------------
# Auth helpers (reuse prompt_cloud_sync pattern)
# ---------------------------------------------------------------------------

def _get_cloud_context() -> Optional[Dict[str, Any]]:
    """Return {session, token, endpoint, owner} from the running MainWindow, or None."""
    try:
        from app_context import AppContext
        mainwin = AppContext.get_main_window()
        if mainwin is None:
            logger.debug("[skill_file_sync] MainWindow not available – skipping")
            return None

        token = mainwin.get_auth_token()
        if not token:
            logger.debug("[skill_file_sync] No auth token – skipping")
            return None

        session = mainwin.session
        endpoint = mainwin.getWanApiEndpoint() if hasattr(mainwin, 'getWanApiEndpoint') else None
        from agent.cloud_api.cloud_api import normalize_cloud_owner
        owner = normalize_cloud_owner(getattr(mainwin, 'user', None) or "")

        if not owner:
            logger.debug("[skill_file_sync] No owner/user – skipping")
            return None

        return {
            "session": session,
            "token": token,
            "endpoint": endpoint,
            "owner": owner,
        }
    except Exception as exc:
        logger.debug(f"[skill_file_sync] Failed to get cloud context: {exc}")
        return None


def _appsync_request(query_string: str, ctx: Dict[str, Any], variables: Optional[Dict] = None) -> Dict:
    """Send a GraphQL request to AppSync with application/json Content-Type."""
    from agent.cloud_api.cloud_api import get_appsync_endpoint, _http_auth_header

    endpoint = ctx.get("endpoint") or get_appsync_endpoint()
    token = ctx["token"]
    session = ctx["session"]

    headers = {
        "Content-Type": "application/json",
        # CN needs the session-token bearer; Intl passes the token through.
        "Authorization": _http_auth_header(token),
        "cache-control": "no-cache",
    }

    payload: Dict[str, Any] = {"query": query_string}
    if variables:
        payload["variables"] = variables

    try:
        resp = session.request(
            url=endpoint, method="POST", timeout=30,
            headers=headers, json=payload,
        )
        jresp = resp.json()
        logger.debug(f"[skill_file_sync] AppSync response status={resp.status_code}")
        return jresp
    except Exception as exc:
        logger.warning(f"[skill_file_sync] AppSync request failed: {exc}")
        return {"errors": [{"errorType": "RequestError", "message": str(exc)}]}


# ---------------------------------------------------------------------------
# Zip helpers
# ---------------------------------------------------------------------------

def _zip_skill_dir(skill_dir: Path) -> Optional[bytes]:
    """Zip the contents of *skill_dir* into an in-memory bytes buffer.

    Returns the raw zip bytes, or None on failure.
    """
    if not skill_dir.is_dir():
        logger.warning(f"[skill_file_sync] Skill dir does not exist: {skill_dir}")
        return None

    buf = io.BytesIO()
    try:
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _dirs, files in os.walk(skill_dir):
                for fname in files:
                    abs_path = os.path.join(root, fname)
                    arc_name = os.path.relpath(abs_path, skill_dir)
                    zf.write(abs_path, arc_name)
        buf.seek(0)
        zip_bytes = buf.read()
        logger.info(f"[skill_file_sync] Zipped {skill_dir.name}: {len(zip_bytes)} bytes")
        return zip_bytes
    except Exception as exc:
        logger.error(f"[skill_file_sync] Failed to zip {skill_dir}: {exc}")
        return None


def _unzip_to_skill_dir(zip_bytes: bytes, skill_dir: Path) -> bool:
    """Unzip *zip_bytes* into *skill_dir* (creates or overwrites).

    Entries that would escape *skill_dir* (absolute paths, ``..`` segments —
    zip-slip) are skipped: downloaded packages are author-controlled input.
    """
    try:
        skill_dir.mkdir(parents=True, exist_ok=True)
        base = skill_dir.resolve()
        buf = io.BytesIO(zip_bytes)
        skipped = 0
        with zipfile.ZipFile(buf, "r") as zf:
            for info in zf.infolist():
                name = info.filename
                dest = (base / name).resolve()
                if not str(dest).startswith(str(base)):
                    skipped += 1
                    logger.warning(f"[skill_file_sync] Skipping unsafe zip entry: {name!r}")
                    continue
                if info.is_dir():
                    dest.mkdir(parents=True, exist_ok=True)
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src:
                    dest.write_bytes(src.read())
        logger.info(f"[skill_file_sync] Unzipped into {skill_dir}"
                    + (f" ({skipped} unsafe entries skipped)" if skipped else ""))
        return True
    except Exception as exc:
        logger.error(f"[skill_file_sync] Failed to unzip into {skill_dir}: {exc}")
        return False


# ---------------------------------------------------------------------------
# S3 presigned URL operations
# ---------------------------------------------------------------------------

def _request_upload_url(skill_id: str, owner: str, file_name: str, ctx: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """Request a presigned upload URL from the cloud.

    Returns dict with {uploadUrl, s3Key, expiresIn} or None.
    """
    mutation = """
        mutation RequestSkillFileUploadUrl($input: SkillFileUploadInput!) {
            requestSkillFileUploadUrl(input: $input) {
                uploadUrl s3Key expiresIn
            }
        }
    """
    variables = {
        "input": {
            "skillId": skill_id,
            "owner": owner,
            "fileName": file_name,
        }
    }
    resp = _appsync_request(mutation, ctx, variables=variables)
    errors = resp.get("errors")
    if errors:
        logger.warning(f"[skill_file_sync] requestSkillFileUploadUrl error: {errors}")
        return None
    data = resp.get("data", {}).get("requestSkillFileUploadUrl")
    if not data or not data.get("uploadUrl"):
        logger.warning(f"[skill_file_sync] No uploadUrl in response: {resp}")
        return None
    return data


def _request_download_url(skill_id: str, owner: str, ctx: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """Request a presigned download URL from the cloud.

    Returns dict with {downloadUrl, s3Key, expiresIn} or None.
    """
    cache_key = f"{owner}:{skill_id}"
    last_missing_at = _MISSING_DOWNLOAD_URL_CACHE.get(cache_key)
    if last_missing_at and (time.time() - last_missing_at) < _MISSING_DOWNLOAD_URL_TTL_SECONDS:
        ttl_left = int(_MISSING_DOWNLOAD_URL_TTL_SECONDS - (time.time() - last_missing_at))
        logger.info(
            f"[skill_file_sync] Skip requestSkillFileDownloadUrl via cache hit for skill '{skill_id}' "
            f"(owner={owner}, ttl_left={max(ttl_left, 0)}s)"
        )
        return None

    query = """
        query RequestSkillFileDownloadUrl($skillId: ID!, $owner: String!) {
            requestSkillFileDownloadUrl(skillId: $skillId, owner: $owner) {
                downloadUrl s3Key expiresIn
            }
        }
    """
    variables = {"skillId": skill_id, "owner": owner}
    resp = _appsync_request(query, ctx, variables=variables)
    errors = resp.get("errors")
    if errors:
        # Many skills (especially cloud/public skills) may not have uploaded file archives yet.
        # AppSync can surface this as non-nullable field errors for downloadUrl/s3Key.
        # Treat that as expected/missing-file and avoid warning spam.
        errors_text = str(errors)
        missing_file_error = (
            "Cannot return null for non-nullable type" in errors_text
            and "requestSkillFileDownloadUrl" in errors_text
        )
        if missing_file_error:
            _MISSING_DOWNLOAD_URL_CACHE[cache_key] = time.time()
            warn_key = cache_key
            if warn_key not in _MISSING_DOWNLOAD_URL_LOGGED:
                logger.info(
                    f"[skill_file_sync] No downloadable archive in cloud yet for skill '{skill_id}' (owner={owner})"
                )
                _MISSING_DOWNLOAD_URL_LOGGED.add(warn_key)
            else:
                logger.debug(
                    f"[skill_file_sync] Missing archive detected again for skill '{skill_id}' (owner={owner}); cache refreshed"
                )
        else:
            logger.warning(f"[skill_file_sync] requestSkillFileDownloadUrl error: {errors}")
        return None
    data = resp.get("data", {}).get("requestSkillFileDownloadUrl")
    if not data or not data.get("downloadUrl"):
        logger.warning(f"[skill_file_sync] No downloadUrl in response: {resp}")
        return None
    _MISSING_DOWNLOAD_URL_CACHE.pop(cache_key, None)
    if cache_key in _MISSING_DOWNLOAD_URL_LOGGED:
        logger.info(
            f"[skill_file_sync] Download URL available again for skill '{skill_id}' (owner={owner}); clearing missing-archive marker"
        )
        _MISSING_DOWNLOAD_URL_LOGGED.discard(cache_key)
    return data


def _process_skill_zip(skill_name: str, ctx: Dict[str, Any]) -> bool:
    """Call processSkillZipUpload mutation to extract zip contents in S3."""
    query = """
    mutation ProcessSkillZip($input: ProcessSkillZipInput!) {
        processSkillZipUpload(input: $input) {
            success error extractedFiles
        }
    }
    """
    variables = {"input": {"skillName": skill_name, "owner": ctx["owner"]}}
    resp = _appsync_request(query, ctx, variables=variables)
    errors = resp.get("errors")
    if errors:
        logger.warning(f"[skill_file_sync] processSkillZipUpload error: {errors}")
        return False
    data = resp.get("data", {}).get("processSkillZipUpload") or {}
    if data.get("success"):
        logger.info(f"[skill_file_sync] Zip extracted: {len(data.get('extractedFiles', []))} files for '{skill_name}'")
        return True
    logger.warning(f"[skill_file_sync] processSkillZipUpload failed: {data.get('error')}")
    return False


def _upload_to_s3(upload_url: str, zip_bytes: bytes) -> bool:
    """PUT zip bytes to S3 via presigned URL."""
    try:
        resp = http_requests.put(
            upload_url,
            data=zip_bytes,
            headers={"Content-Type": "application/zip"},
            timeout=120,
        )
        if resp.status_code in (200, 204):
            logger.info(f"[skill_file_sync] S3 upload success ({len(zip_bytes)} bytes)")
            return True
        else:
            logger.warning(f"[skill_file_sync] S3 upload failed: {resp.status_code} {resp.text[:200]}")
            return False
    except Exception as exc:
        logger.error(f"[skill_file_sync] S3 upload error: {exc}")
        return False


def _download_from_s3(download_url: str) -> Optional[bytes]:
    """GET zip bytes from S3 via presigned URL."""
    try:
        resp = http_requests.get(download_url, timeout=120)
        if resp.status_code == 200:
            logger.info(f"[skill_file_sync] S3 download success ({len(resp.content)} bytes)")
            return resp.content
        else:
            logger.warning(f"[skill_file_sync] S3 download failed: {resp.status_code} {resp.text[:200]}")
            return None
    except Exception as exc:
        logger.error(f"[skill_file_sync] S3 download error: {exc}")
        return None


# ---------------------------------------------------------------------------
# Resolve local skill directory from skill metadata
# ---------------------------------------------------------------------------

def _resolve_skill_dir(skill_data: Dict[str, Any]) -> Optional[Path]:
    """Determine the local directory for a skill.

    Looks at skill_data['path'] first, then falls back to
    ``my_skills/<name>_skill/``.
    """
    # Try explicit path from skill metadata
    path_str = skill_data.get("path", "")
    if path_str:
        p = Path(path_str)
        # path may point to a file (e.g. diagram_dir/skill.json) — go up to skill root
        if p.suffix:
            p = p.parent
        # Ensure we're at the *_skill level (not inside diagram_dir etc.)
        # Safety: limit iterations to avoid walking up to C:\ / filesystem root
        for _ in range(10):
            if not p.name:
                break
            if p.name.endswith("_skill"):
                break
            parent = p.parent
            if parent == p:
                break  # reached filesystem root
            p = parent
        if p.name.endswith("_skill") and p.is_dir():
            return p

    # Fallback: derive from skill name
    name = skill_data.get("name", "")
    if name:
        dir_name = name.strip().lower().replace(" ", "_")
        # Try the name as-is first (handles names that already end with _skill)
        candidate = MY_SKILLS_DIR / dir_name
        if candidate.is_dir():
            return candidate
        # Then try with _skill suffix appended
        if not dir_name.endswith("_skill"):
            candidate = MY_SKILLS_DIR / (dir_name + "_skill")
            if candidate.is_dir():
                return candidate

    # Fallback: derive from skill ID
    skill_id = skill_data.get("id", "")
    if skill_id:
        try:
            for child in MY_SKILLS_DIR.iterdir():
                if child.is_dir() and skill_id in child.name:
                    return child
        except OSError:
            pass

    logger.debug(f"[skill_file_sync] Could not resolve skill dir for: {skill_data.get('name', skill_data.get('id', '?'))}")
    return None


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _is_valid_skill_dir(skill_dir: Path, skill_name: str = "") -> bool:
    """Return True if *skill_dir* looks like a well-formed skill directory.

    Rejects directories that:
    - Don't end with ``_skill``
    - Are outside ``my_skills/`` (e.g. resolved to C:\\ or another root)
    - Have suspicious names (empty, whitespace-only, etc.)
    """
    name = skill_dir.name
    if not name or not name.strip():
        logger.warning(f"[skill_file_sync] Skipping skill '{skill_name}': empty dir name")
        return False
    if not name.endswith("_skill"):
        logger.warning(f"[skill_file_sync] Skipping skill '{skill_name}': dir '{name}' does not end with '_skill'")
        return False
    # Guard against dirs that resolved outside the project (e.g. C:\ or /)
    try:
        resolved = skill_dir.resolve()
        if resolved == resolved.parent:
            logger.warning(f"[skill_file_sync] Skipping skill '{skill_name}': resolved to filesystem root")
            return False
    except Exception:
        pass
    return True


# ---------------------------------------------------------------------------
# Public API — fire-and-forget (background threads)
# ---------------------------------------------------------------------------

def _is_intl_app() -> bool:
    """True when running on the Intl (AWS AppSync) backend.

    The S3-presigned-URL flow in this module is Intl-only: the AWS AppSync
    schema declares ``requestSkillFileUploadUrl`` / ``requestSkillFileDownloadUrl``
    / ``processSkillZipUpload`` / ``deleteSkillFiles`` plus their ``SkillFileUploadInput``
    and ``SkillFileUploadResult`` types, but the CN (cloudbase-graphql) backend
    has no equivalent mutations — CN writes skill files directly via
    ``writeSkillFile`` (see ``agent.cloud_api.upload_skill_files_to_cloud``)
    and stores them in CloudBase / COS rather than S3.

    Calling any of those Intl-only mutations from CN returns
    ``GRAPHQL_VALIDATION_FAILED`` from the cloud function, which the logger
    surfaces as a ``[skill_file_sync] requestSkillFileUploadUrl error: …``
    warning every time a skill is loaded or saved. Short-circuit at the
    public entry points so the rest of the module only runs on Intl.
    """
    try:
        from utils.app_env import is_cn
        return not is_cn()
    except Exception:
        # Default to Intl-safe behaviour if app_env isn't ready yet: let the
        # request through. Worst case it 404s on Intl, but if we're really on
        # Intl a CN check would also be wrong here.
        return True


# ── CN (TCB/COS) upload path ────────────────────────────────────────────
# ZIP-ONLY SAVE via the presigned flow (live-verified against the deployed
# TCB backend 2026-08-27): requestSkillFileUploadUrl(skillId, owner,
# fileName) returns a signed COS PUT (the resolver canonicalizes the
# object key to ``users/<owner>/skills/<name>_skill.zip``); the client
# PUTs the raw zip bytes. Same flow as intl minus processSkillZipUpload
# (mutation absent on the CN SDL — server-side explode is specced in
# docs/OPEN_ITEMS.md). Subscribers download the same object via
# requestSkillFileDownloadUrl.
_CN_MAX_PACKAGE_BYTES = 20 * 1024 * 1024
# Per-process dedupe so panel-load bulk syncs don't re-upload unchanged
# skills on every request; a skill re-uploads after an explicit save
# because save calls upload_skill_files_to_cloud directly (force=True).
_CN_SYNCED_SKILL_DIRS: set = set()


def _cn_upload_skill_package(skill_dir: Path, ctx: Dict[str, Any], skill_id: str) -> bool:
    """Upload the skill directory as ONE zip via the presigned flow (CN)."""
    owner = str(ctx.get("owner") or "")
    if not skill_id or not owner:
        logger.debug(f"[skill_file_sync] CN package upload skipped for {skill_dir.name}: no skill id/owner")
        return False
    zip_bytes = _zip_skill_dir(skill_dir)
    if not zip_bytes:
        return False
    if len(zip_bytes) > _CN_MAX_PACKAGE_BYTES:
        logger.warning(
            f"[skill_file_sync] CN package for {skill_dir.name} too large "
            f"({len(zip_bytes)} bytes > {_CN_MAX_PACKAGE_BYTES}) — skipping zip artifact"
        )
        return False
    try:
        url_info = _request_upload_url(skill_id, owner, f"{skill_dir.name}.zip", ctx)
        if not url_info:
            return False
        if _upload_to_s3(url_info["uploadUrl"], zip_bytes):
            logger.info(
                f"[skill_file_sync] CN package uploaded for {skill_dir.name}: "
                f"{len(zip_bytes)} bytes -> {url_info.get('s3Key')}"
            )
            return True
        return False
    except Exception as exc:
        logger.warning(f"[skill_file_sync] CN package upload failed for {skill_dir.name}: {exc}")
        return False


def upload_skill_files_to_cloud(skill_data: Dict[str, Any]) -> None:
    """Upload a single skill's files to cloud storage. Runs in background thread.

    Intl: zip + S3 presigned-URL flow. CN: zip + writeSkillFile-signed COS
    PUT (zip-only save; the server explodes the package into per-file
    objects for listSkillFiles/readSkillFile consumers).
    """
    if not _is_intl_app():
        def _do_cn():
            try:
                ctx = _get_cloud_context()
                if ctx is None:
                    return
                skill_dir = _resolve_skill_dir(skill_data)
                if skill_dir is None or not skill_dir.is_dir():
                    logger.debug(
                        f"[skill_file_sync] CN: no local dir for skill "
                        f"'{skill_data.get('name')}' — skip upload"
                    )
                    return
                if not _is_valid_skill_dir(skill_dir, skill_data.get('name', '')):
                    return
                if _cn_upload_skill_package(skill_dir, ctx, str(skill_data.get('id') or '')):
                    _CN_SYNCED_SKILL_DIRS.add(str(skill_dir))
            except Exception as exc:
                logger.warning(
                    f"[skill_file_sync] CN upload failed for skill "
                    f"'{skill_data.get('id', '?')}': {exc}"
                )
        threading.Thread(target=_do_cn, daemon=True, name="skill-file-upload-cn").start()
        return

    def _do():
        try:
            ctx = _get_cloud_context()
            if ctx is None:
                return

            skill_id = skill_data.get("id", "")
            if not skill_id:
                logger.warning("[skill_file_sync] No skill ID — cannot upload")
                return

            skill_dir = _resolve_skill_dir(skill_data)
            if skill_dir is None:
                logger.debug(f"[skill_file_sync] No local dir for skill '{skill_data.get('name')}' — skip upload")
                return
            if not _is_valid_skill_dir(skill_dir, skill_data.get('name', '')):
                return

            # Use the directory name as the skill identifier for S3 paths.
            # e.g. skill_dir.name='passive0_skill' -> cloud_skill_id='passive0'
            # This avoids sending internal DB IDs (like 'skill_985de41be1284b38')
            # which create spurious S3 directories.
            cloud_skill_id = skill_dir.name
            if cloud_skill_id.endswith("_skill"):
                cloud_skill_id = cloud_skill_id[:-6]  # strip '_skill' suffix

            # Zip
            zip_bytes = _zip_skill_dir(skill_dir)
            if not zip_bytes:
                return

            # Request presigned upload URL
            file_name = f"{skill_dir.name}.zip"
            url_info = _request_upload_url(cloud_skill_id, ctx["owner"], file_name, ctx)
            if not url_info:
                return

            # Upload
            ok = _upload_to_s3(url_info["uploadUrl"], zip_bytes)
            if ok:
                logger.info(f"[skill_file_sync] ✅ Uploaded skill files '{skill_dir.name}' to S3 (key={url_info.get('s3Key')})")
                # Extract zip contents into individual S3 objects
                _process_skill_zip(skill_dir.name, ctx)
            else:
                logger.warning(f"[skill_file_sync] ❌ Failed to upload skill files '{skill_dir.name}'")
        except Exception as exc:
            logger.warning(f"[skill_file_sync] Upload failed for skill '{skill_data.get('id', '?')}': {exc}\n{traceback.format_exc()}")

    t = threading.Thread(target=_do, daemon=True, name="skill-file-upload")
    t.start()


def _download_skill_files_cn(
    skill_data: Dict[str, Any],
    file_owner: Optional[str] = None,
    trace_id: Optional[str] = None,
) -> None:
    """CN skill-file download. Runs in a background thread; best-effort.

    PRIMARY (live-verified against the deployed TCB backend 2026-08-27):
    the same presigned-zip flow as intl — ``requestSkillFileDownloadUrl``
    (with the REAL skill id; the CN resolver canonicalizes the object key
    to ``users/<owner>/skills/<name>_skill.zip``) → signed GET → unzip.

    FALLBACK: per-file ``listSkillFiles``/``readSkillFile``. NOTE the
    deployed SDL returns TYPED results needing a selection set, and
    ``readSkillFile`` returns the file ``content`` INLINE (there is no
    downloadUrl field) — the old scalar-shaped queries failed validation
    and were silently swallowed as "no files listed" (v0.9.95n incident).

    ``file_owner``: the namespace owner — the AUTHOR for subscribed
    skills. Cross-owner reads require the server to authorize public
    skills' files for a non-owner caller.
    """
    def _do():
        trace_prefix = f"[trace={trace_id}] " if trace_id else ""
        try:
            ctx = _get_cloud_context()
            if ctx is None:
                return
            skill_name = str(skill_data.get("name") or "").strip()
            if not skill_name:
                return
            folder = skill_name if skill_name.endswith("_skill") else f"{skill_name}_skill"
            root = _get_my_skills_dir()
            dest_dir = Path(root) / folder
            owner = str(file_owner or ctx.get("owner") or "")
            skill_id = str(skill_data.get("id") or "")

            # ── PRIMARY: presigned zip ─────────────────────────────────
            if skill_id and owner:
                url_info = _request_download_url(skill_id, owner, ctx)
                if url_info:
                    zip_bytes = _download_from_s3(url_info["downloadUrl"])
                    if zip_bytes and _unzip_to_skill_dir(zip_bytes, dest_dir):
                        logger.info(
                            f"[skill_file_sync] {trace_prefix}CN zip download for '{folder}' "
                            f"(owner={owner}): {len(zip_bytes)} bytes -> {dest_dir}"
                        )
                        return
                logger.info(
                    f"[skill_file_sync] {trace_prefix}CN zip not available for '{folder}' "
                    f"(owner={owner}) — falling back to per-file download"
                )

            # ── FALLBACK: per-file (typed selection sets, inline content) ──
            list_query = """
                query ListSkillFiles($prefix: String, $userId: String) {
                    listSkillFiles(prefix: $prefix, userId: $userId) { filePath }
                }
            """
            variables: Dict[str, Any] = {"prefix": folder}
            if file_owner:
                variables["userId"] = file_owner
            resp = _appsync_request(list_query, ctx, variables=variables)
            if resp.get("errors"):
                logger.warning(
                    f"[skill_file_sync] {trace_prefix}CN listSkillFiles error: {resp['errors']}"
                )
            files = (resp.get("data") or {}).get("listSkillFiles") or []
            if not isinstance(files, list) or not files:
                logger.info(
                    f"[skill_file_sync] {trace_prefix}CN download: no files listed for "
                    f"'{folder}' (owner={file_owner or 'self'})"
                )
                return

            read_query = """
                query ReadSkillFile($filePath: String!, $userId: String) {
                    readSkillFile(filePath: $filePath, userId: $userId) { filePath content }
                }
            """
            saved, failed = 0, 0
            for meta in files:
                fpath = (meta or {}).get("filePath") or ""
                if not fpath:
                    continue
                if fpath.endswith(".zip"):
                    continue  # zip artifacts are not skill source files
                try:
                    rvars: Dict[str, Any] = {"filePath": fpath}
                    if file_owner:
                        rvars["userId"] = file_owner
                    rresp = _appsync_request(read_query, ctx, variables=rvars)
                    items = (rresp.get("data") or {}).get("readSkillFile") or []
                    content = (items[0] or {}).get("content") if items else None
                    if content is None:
                        failed += 1
                        continue
                    # The server may return namespace-relative paths
                    # ("<folder>/x.py") or owner-prefixed ones
                    # ("<owner>/my_skills/<folder>/x.py"); normalize both to
                    # the local skills root.
                    rel = fpath
                    idx = rel.find("my_skills/")
                    if idx != -1:
                        rel = rel[idx + len("my_skills/"):]
                    dest = Path(root) / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_text(content, encoding="utf-8")
                    saved += 1
                except Exception as fe:
                    failed += 1
                    logger.debug(f"[skill_file_sync] {trace_prefix}CN file fetch failed {fpath}: {fe}")

            logger.info(
                f"[skill_file_sync] {trace_prefix}CN download for '{folder}' "
                f"(owner={file_owner or 'self'}): {saved} saved, {failed} failed"
            )
        except Exception as e:
            logger.warning(f"[skill_file_sync] {trace_prefix}CN download error: {e}")

    threading.Thread(target=_do, daemon=True, name="cn-skill-file-download").start()


def download_skill_files_from_cloud(
    skill_data: Dict[str, Any],
    target_dir: Optional[Path] = None,
    trace_id: Optional[str] = None,
    file_owner: Optional[str] = None,
) -> None:
    """Download a skill's files from cloud storage. Runs in background thread.

    Intl: S3 presigned-zip flow. CN: per-file COS download via
    listSkillFiles/readSkillFile (``file_owner`` selects the namespace —
    pass the AUTHOR for subscribed skills).
    """
    if not _is_intl_app():
        _download_skill_files_cn(skill_data, file_owner=file_owner, trace_id=trace_id)
        return

    def _do():
        try:
            trace_prefix = f"[trace={trace_id}] " if trace_id else ""
            ctx = _get_cloud_context()
            if ctx is None:
                return

            skill_id = skill_data.get("id", "")
            if not skill_id:
                logger.warning("[skill_file_sync] No skill ID — cannot download")
                return

            # Derive cloud skill ID from skill name (not internal DB ID)
            cloud_skill_id = skill_data.get("name", "").strip().lower().replace(" ", "_")
            if not cloud_skill_id:
                cloud_skill_id = skill_id  # fallback to DB ID
            # Strip _skill suffix if present — cloud Lambda appends it
            if cloud_skill_id.endswith("_skill"):
                cloud_skill_id = cloud_skill_id[:-6]

            # Request presigned download URL
            url_info = _request_download_url(cloud_skill_id, ctx["owner"], ctx)
            if not url_info:
                logger.info(
                    f"[skill_file_sync] {trace_prefix}Skip download for skill '{skill_data.get('name', skill_id)}': no download URL available"
                )
                return

            # Download
            zip_bytes = _download_from_s3(url_info["downloadUrl"])
            if not zip_bytes:
                logger.warning(
                    f"[skill_file_sync] {trace_prefix}Download content fetch failed for skill '{skill_data.get('name', skill_id)}'"
                )
                return

            # Determine target directory
            dest = target_dir
            if dest is None:
                dest = _resolve_skill_dir(skill_data)
            if dest is None:
                # Create new dir based on skill name
                name = skill_data.get("name", skill_id)
                dir_name = name.strip().lower().replace(" ", "_")
                if not dir_name.endswith("_skill"):
                    dir_name += "_skill"
                dest = MY_SKILLS_DIR / dir_name

            ok = _unzip_to_skill_dir(zip_bytes, dest)
            if ok:
                logger.info(f"[skill_file_sync] {trace_prefix}✅ Downloaded skill files to '{dest}'")
            else:
                logger.warning(f"[skill_file_sync] {trace_prefix}❌ Failed to extract skill files to '{dest}'")
        except Exception as exc:
            logger.warning(
                f"[skill_file_sync] {trace_prefix}Download failed for skill '{skill_data.get('id', '?')}': {exc}\n{traceback.format_exc()}"
            )

    t = threading.Thread(target=_do, daemon=True, name="skill-file-download")
    t.start()


def delete_skill_files_from_cloud(skill_id: str) -> None:
    """Request deletion of a skill's files from S3. Runs in background thread.

    Uses a mutation to tell the Lambda to remove the S3 object.
    No-op on CN (cloudbase-graphql) — see ``_is_intl_app`` for the rationale.
    """
    if not _is_intl_app():
        logger.debug(f"[skill_file_sync] Delete skipped on CN for skill '{skill_id}'")
        return

    def _do():
        try:
            ctx = _get_cloud_context()
            if ctx is None:
                return

            mutation = """
                mutation DeleteSkillFiles($skillId: ID!, $owner: String!) {
                    deleteSkillFiles(skillId: $skillId, owner: $owner) {
                        success error
                    }
                }
            """
            variables = {"skillId": skill_id, "owner": ctx["owner"]}
            resp = _appsync_request(mutation, ctx, variables=variables)
            errors = resp.get("errors")
            if errors:
                logger.warning(f"[skill_file_sync] deleteSkillFiles error: {errors}")
            else:
                data = resp.get("data", {}).get("deleteSkillFiles", {})
                if data.get("success"):
                    logger.info(f"[skill_file_sync] ✅ Deleted skill files from S3: {skill_id}")
                else:
                    logger.warning(f"[skill_file_sync] deleteSkillFiles returned: {data}")
        except Exception as exc:
            logger.warning(f"[skill_file_sync] Delete failed for skill '{skill_id}': {exc}")

    t = threading.Thread(target=_do, daemon=True, name="skill-file-delete")
    t.start()


def sync_all_skill_files_to_cloud(skills: List[Dict[str, Any]]) -> None:
    """Bulk upload all local user skills to S3. Runs in background thread.

    Skips code-sourced skills (source='code') and skills without local dirs.
    CN: uploads each owned skill dir as ONE zip package (zip-only save),
    once per process per skill dir (an explicit save re-uploads via
    upload_skill_files_to_cloud).
    """
    if not _is_intl_app():
        def _do_cn_bulk():
            try:
                ctx = _get_cloud_context()
                if ctx is None:
                    return
                owner = str(ctx.get("owner") or "")
                done = 0
                for sk in skills:
                    if sk.get("source") == "code" or not sk.get("id"):
                        continue
                    # Only the current user's skills sync under their COS
                    # prefix — legacy/other-owner skills stay local.
                    if str(sk.get("owner") or "") != owner:
                        continue
                    skill_dir = _resolve_skill_dir(sk)
                    if not skill_dir or not skill_dir.is_dir():
                        continue
                    if str(skill_dir) in _CN_SYNCED_SKILL_DIRS:
                        continue
                    if not _is_valid_skill_dir(skill_dir, sk.get('name', '')):
                        continue
                    if _cn_upload_skill_package(skill_dir, ctx, str(sk.get('id') or '')):
                        _CN_SYNCED_SKILL_DIRS.add(str(skill_dir))
                        done += 1
                if done:
                    logger.info(f"[skill_file_sync] CN bulk sync uploaded {done} skill dir(s)")
            except Exception as exc:
                logger.warning(f"[skill_file_sync] CN bulk sync failed: {exc}")
        threading.Thread(target=_do_cn_bulk, daemon=True, name="skill-file-bulk-cn").start()
        return

    def _do():
        try:
            ctx = _get_cloud_context()
            if ctx is None:
                return

            # Filter to user-owned, non-code skills that have local dirs
            to_sync = []
            for sk in skills:
                if sk.get("source") == "code":
                    continue
                if not sk.get("id"):
                    continue
                skill_dir = _resolve_skill_dir(sk)
                if skill_dir and skill_dir.is_dir():
                    if not _is_valid_skill_dir(skill_dir, sk.get('name', '')):
                        continue
                    to_sync.append((sk, skill_dir))

            if not to_sync:
                logger.debug("[skill_file_sync] No skill dirs to sync")
                return

            logger.info(f"[skill_file_sync] Bulk uploading {len(to_sync)} skill dirs to S3...")

            ok_count = 0
            err_count = 0
            for sk, skill_dir in to_sync:
                try:
                    zip_bytes = _zip_skill_dir(skill_dir)
                    if not zip_bytes:
                        err_count += 1
                        continue

                    file_name = f"{skill_dir.name}.zip"
                    # Use dir name as cloud skill ID (not internal DB ID)
                    cloud_skill_id = skill_dir.name
                    if cloud_skill_id.endswith("_skill"):
                        cloud_skill_id = cloud_skill_id[:-6]
                    url_info = _request_upload_url(cloud_skill_id, ctx["owner"], file_name, ctx)
                    if not url_info:
                        err_count += 1
                        continue

                    if _upload_to_s3(url_info["uploadUrl"], zip_bytes):
                        _process_skill_zip(skill_dir.name, ctx)
                        ok_count += 1
                    else:
                        err_count += 1
                except Exception as exc:
                    logger.warning(f"[skill_file_sync] Bulk upload error for '{sk.get('name')}': {exc}")
                    err_count += 1

            logger.info(f"[skill_file_sync] Bulk upload complete: {ok_count} ok, {err_count} errors")
        except Exception as exc:
            logger.warning(f"[skill_file_sync] Bulk upload failed: {exc}\n{traceback.format_exc()}")

    t = threading.Thread(target=_do, daemon=True, name="skill-file-bulk-upload")
    t.start()


# ---------------------------------------------------------------------------
# Startup auto-refresh for subscribed skills
# ---------------------------------------------------------------------------

def _auto_fetch_sub_skills_enabled(mainwin) -> bool:
    """ECAN_AUTO_FETCH_SUB_SKILLS option: auto-download subscribed skills
    whose files are missing from my_skills. Env var wins over the persisted
    settings field of the same name; default ON."""
    env = str(os.environ.get("ECAN_AUTO_FETCH_SUB_SKILLS", "") or "").strip()
    if env:
        return env not in ("0", "false", "no", "off")
    try:
        gs = mainwin.config_manager.general_settings
        value = gs.get_field("ECAN_AUTO_FETCH_SUB_SKILLS", 1)
        return str(value).strip().lower() not in ("0", "false", "no", "off")
    except Exception:
        return True


def refresh_subscribed_skills_from_cloud(mainwin) -> int:
    """Auto-update SUBSCRIBED (non-owned, read-only) skills from the cloud.

    Called synchronously at startup BEFORE the skill compile: for every local
    DB skill row whose owner differs from the logged-in user (subscribed rows
    keep the AUTHOR as owner), compare versions with the author's cloud copy.
    When the cloud copy is newer, download the presigned zip into my_skills
    (the compiler is local-file-first, so refreshing the files is what makes
    the update take effect) and then sync the DB row's diagram + version.

    2026-08-31 addition: independent of version freshness, a subscribed skill
    whose FILES are missing from my_skills (never downloaded, wiped, or a
    failed earlier fetch) is fetched automatically when the
    ECAN_AUTO_FETCH_SUB_SKILLS option is on (default 1; env var beats the
    persisted settings field).

    Rationale (v0.9.95x incident): a republished rented skill only reached
    subscribers via a manual skills-page update click; two consecutive live
    tests missed that step and ran a stale dispatch config. Rented skills are
    read-only for the subscriber, so tracking the author's published version
    automatically is safe by definition — there is no local work to clobber.

    Best-effort: any cloud failure logs a WARNING and leaves the local copy
    untouched (graceful offline fallback). The DB row is only bumped when the
    files actually refreshed (or none existed), so a failed download keeps the
    GUI's update indicator honest. Returns the number of skills refreshed.
    """
    refreshed = 0
    try:
        from utils.skill_version import compare_skill_versions, CLOUD_NEWER

        ctx = _get_cloud_context()
        if ctx is None:
            return 0
        me = str(ctx.get("owner") or "").strip()
        db_mgr = getattr(mainwin, "ec_db_mgr", None)
        svc = getattr(db_mgr, "skill_service", None)
        if not me or svc is None:
            return 0

        rows_result = svc.query_skills()
        rows = rows_result.get("data", []) if rows_result.get("success") else []
        subscribed = [
            r for r in rows
            if isinstance(r, dict) and str(r.get("owner") or "").strip()
            and str(r.get("owner")).strip() != me
        ]
        if not subscribed:
            return 0

        for row in subscribed:
            sid = str(row.get("id") or "").strip()
            author = str(row.get("owner") or "").strip()
            name = str(row.get("name") or "").strip()
            if not sid or not author or not name:
                continue
            try:
                resp = _appsync_request(
                    "query($i: SkillQueryInput!) { getAgentSkills(input: $i) "
                    "{ id version diagram } }",
                    ctx, {"i": {"id": sid, "owner": author}},
                )
                data = (resp.get("data") or {}).get("getAgentSkills") or []
                if isinstance(data, dict):
                    data = [data]
                cloud = next(
                    (c for c in data if isinstance(c, dict) and str(c.get("id")) == sid),
                    None,
                )
                if not cloud:
                    continue
                folder = name if name.endswith("_skill") else f"{name}_skill"
                dest_dir = Path(_get_my_skills_dir()) / folder
                cloud_newer = compare_skill_versions(
                    row.get("version"), cloud.get("version")) == CLOUD_NEWER
                # "Missing" = no dir, or a dir with no JSON anywhere (the
                # compiler needs at least the diagram_dir json; an empty husk
                # from a failed earlier unzip counts as missing).
                try:
                    files_missing = not (dest_dir.is_dir()
                                         and any(dest_dir.rglob("*.json")))
                except Exception:
                    files_missing = not dest_dir.is_dir()
                if not cloud_newer and not (files_missing
                                            and _auto_fetch_sub_skills_enabled(mainwin)):
                    continue
                if files_missing and not cloud_newer:
                    logger.info(
                        f"[skill_file_sync] subscribed skill '{name}' ({sid}) has no "
                        f"local files — auto-fetching (ECAN_AUTO_FETCH_SUB_SKILLS)"
                    )
                got_files = False
                url_info = _request_download_url(sid, author, ctx)
                if url_info and url_info.get("downloadUrl"):
                    zip_bytes = _download_from_s3(url_info["downloadUrl"])
                    if zip_bytes and _unzip_to_skill_dir(zip_bytes, dest_dir):
                        got_files = True
                if not got_files and not cloud_newer:
                    # Missing-files fetch failed and there is no version delta —
                    # nothing achieved; don't touch the row or count a refresh.
                    logger.warning(
                        f"[skill_file_sync] auto-fetch failed for subscribed skill "
                        f"'{name}' ({sid}) — files still missing"
                    )
                    continue
                if not got_files and dest_dir.is_dir():
                    # Files exist locally but couldn't refresh — the stale files
                    # would win over any DB update (local-file-first compile), so
                    # leave the row untouched and keep the update indicator up.
                    logger.warning(
                        f"[skill_file_sync] subscribed skill '{name}' ({sid}) has a newer "
                        f"cloud version {cloud.get('version')!r} but the file download "
                        f"failed — keeping local copy {row.get('version')!r}"
                    )
                    continue

                fields = {"version": cloud.get("version")}
                diagram = cloud.get("diagram")
                if isinstance(diagram, str) and diagram.strip():
                    try:
                        fields["diagram"] = json.loads(diagram)
                    except Exception:
                        pass
                elif isinstance(diagram, dict):
                    fields["diagram"] = diagram
                svc.update_skill(sid, fields)
                refreshed += 1
                logger.info(
                    f"[skill_file_sync] auto-refreshed subscribed skill '{name}' ({sid}) "
                    f"from author {author}: {row.get('version')!r} -> "
                    f"{cloud.get('version')!r} (files={'zip' if got_files else 'db-only'})"
                )
            except Exception as exc:
                logger.warning(
                    f"[skill_file_sync] subscribed-skill refresh failed for "
                    f"'{name}' ({sid}): {exc}"
                )
    except Exception as exc:
        logger.warning(f"[skill_file_sync] subscribed-skill refresh aborted: {exc}")
    return refreshed
