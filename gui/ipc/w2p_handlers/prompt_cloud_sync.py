"""Cloud sync for prompts: push local prompts to DynamoDB via AppSync GraphQL.

Flow: local prompt_handler.py CRUD → this module → AppSync addPrompts / removePrompts

DynamoDB schema (Agent_Prompts table):
  - owner_id (PK): user email (e.g. "songc@yahoo.com")
  - agent_id (SK): "any~{prompt_id}"
  - prompt (JSON string): {title, topic, sections, userSections, humanInputs, usageCount, ...}

GraphQL mutations used:
  - addPrompts(input: [PromptInput!]!) → also handles upsert
  - removePrompts(input: [ID!]!)
"""

from __future__ import annotations

import json
import threading
import traceback
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from utils.logger_helper import logger_helper as logger

_CLOUD_PROMPTS_CACHE_TTL_SECONDS = 15
_cloud_prompts_cache_lock = threading.Lock()
_cloud_prompts_cache: Dict[str, Dict[str, Any]] = {}


def invalidate_cloud_prompts_cache(owner: Optional[str] = None) -> None:
    with _cloud_prompts_cache_lock:
        if owner:
            removed = _cloud_prompts_cache.pop(owner, None)
            if removed is not None:
                logger.info(f"[prompt_sync] Invalidated cloud prompts cache for {owner}")
            return
        if _cloud_prompts_cache:
            _cloud_prompts_cache.clear()
            logger.info("[prompt_sync] Invalidated cloud prompts cache for all owners")

# ---------------------------------------------------------------------------
# Helpers to obtain auth context from the running app
# ---------------------------------------------------------------------------

def _get_cloud_context() -> Optional[Dict[str, Any]]:
    """Return {session, token, endpoint, owner} from the running MainWindow, or None."""
    try:
        from app_context import AppContext
        mainwin = AppContext.get_main_window()
        if mainwin is None:
            logger.warning("[prompt_sync] ⚠️ MainWindow not available – skipping cloud sync")
            return None

        token = mainwin.get_auth_token()
        if not token:
            logger.warning("[prompt_sync] ⚠️ No auth token – skipping cloud sync")
            return None

        session = mainwin.session
        endpoint = mainwin.getWanApiEndpoint() if hasattr(mainwin, 'getWanApiEndpoint') else None
        owner = getattr(mainwin, 'user', None) or ""

        if not owner:
            logger.warning("[prompt_sync] ⚠️ No owner/user – skipping cloud sync")
            return None

        logger.info(f"[prompt_sync] ✅ Cloud context obtained - owner: {owner}, endpoint: {endpoint}")
        return {
            "session": session,
            "token": token,
            "endpoint": endpoint,
            "owner": owner,
        }
    except Exception as exc:
        logger.error(f"[prompt_sync] ❌ Failed to get cloud context: {exc}")
        logger.error(f"[prompt_sync] Traceback: {traceback.format_exc()}")
        return None


def _appsync_request(query_string: str, ctx: Dict[str, Any], variables: Optional[Dict] = None) -> Dict:
    """Send a GraphQL request to AppSync with variables support.

    Uses Content-Type: application/json (matching the web app's appSyncClient.ts)
    because AppSync requires JSON content-type when ``variables`` are present.
    The shared ``appsync_http_request`` uses ``application/graphql`` which causes
    AppSync to ignore the variables dict.
    """
    from agent.cloud_api.cloud_api import get_appsync_endpoint

    endpoint = ctx.get("endpoint") or get_appsync_endpoint()
    token = ctx["token"]
    session = ctx["session"]

    headers = {
        "Content-Type": "application/json",
        "Authorization": token,
        "cache-control": "no-cache",
    }

    payload: Dict[str, Any] = {"query": query_string}
    if variables:
        payload["variables"] = variables

    try:
        resp = session.request(
            url=endpoint,
            method="POST",
            timeout=30,
            headers=headers,
            json=payload,
        )
        jresp = resp.json()
        logger.debug(f"[prompt_sync] AppSync response status={resp.status_code}, keys={list(jresp.keys()) if isinstance(jresp, dict) else 'N/A'}")
        return jresp
    except Exception as exc:
        logger.warning(f"[prompt_sync] AppSync request failed: {exc}")
        return {"errors": [{"errorType": "RequestError", "message": str(exc)}]}


# ---------------------------------------------------------------------------
# Build GraphQL payloads matching the PromptInput schema used by addPrompts
# ---------------------------------------------------------------------------

def _prompt_to_graphql_input(prompt: Dict[str, Any], owner: str) -> Dict[str, Any]:
    """Convert a local normalized prompt dict to a PromptInput for the addPrompts mutation.

    GraphQL PromptInput: { id: ID!, owner: String!, prompt: AWSJSON!, version: String }
    The *prompt* field is a JSON-encoded string containing the full prompt content.
    """
    prompt_id = prompt.get("id", "")
    # If this prompt has rawContent (plain-text, not structured JSON), send it as-is
    raw_content = prompt.get("rawContent")
    if raw_content:
        return {
            "id": prompt_id,
            "owner": owner,
            "prompt": json.dumps(raw_content, ensure_ascii=False),
            "version": prompt.get("version", "0.1"),
        }

    # Check if this is a markdown-mode prompt (has mdContent)
    md_content = prompt.get("mdContent")
    
    prompt_content = {
        "title": prompt.get("title", ""),
        "topic": prompt.get("topic", ""),
        "usageCount": prompt.get("usageCount", 0),
        "sections": prompt.get("sections", []),
        "userSections": prompt.get("userSections", []),
        # Clear humanInputs if mdContent is present to avoid stale data
        "humanInputs": [] if md_content else prompt.get("humanInputs", []),
        "source": prompt.get("source", "my_prompts"),
        "readOnly": False,
        "lastModified": prompt.get("lastModified", datetime.utcnow().isoformat()),
    }
    # Preserve markdown-mode fields so cloud stays in sync with local
    fmt = prompt.get("format")
    if fmt in ("json", "md"):
        prompt_content["format"] = fmt
    if md_content:
        prompt_content["mdContent"] = md_content

    return {
        "id": prompt_id,
        "owner": owner,
        "prompt": json.dumps(prompt_content, ensure_ascii=False),
        "version": prompt.get("version", "0.1"),
    }


# ---------------------------------------------------------------------------
# Public API – fire-and-forget cloud sync (non-blocking)
# ---------------------------------------------------------------------------

def sync_prompt_to_cloud(prompt: Dict[str, Any]) -> None:
    """Push a single prompt to cloud (upsert). Runs in background thread."""
    def _do():
        try:
            ctx = _get_cloud_context()
            if ctx is None:
                logger.warning(f"[prompt_sync] ⚠️ CLOUD CONTEXT NOT AVAILABLE - Cannot sync prompt '{prompt.get('id')}'")
                logger.warning(f"[prompt_sync] This may be due to missing/invalid AWS AppSync settings")
                return

            owner = ctx["owner"]
            endpoint = ctx.get("endpoint", "?")
            gql_input = _prompt_to_graphql_input(prompt, owner)

            logger.warning(f"[prompt_sync] 🚀 >>> SYNCING PROMPT TO CLOUD <<<")
            logger.warning(f"[prompt_sync] Prompt ID: '{prompt.get('id')}'")
            logger.warning(f"[prompt_sync] Prompt Title: '{prompt.get('title')}'")
            logger.warning(f"[prompt_sync] Owner: '{owner}'")
            logger.warning(f"[prompt_sync] Endpoint: {endpoint}")
            logger.warning(f"[prompt_sync] Payload size: {len(gql_input.get('prompt',''))} chars")
            logger.debug(f"[prompt_sync] >>> gql_input keys={list(gql_input.keys())}, id={gql_input.get('id')}, owner={gql_input.get('owner')}, prompt_len={len(gql_input.get('prompt',''))}")

            mutation = """
                mutation AddPrompts($input: [PromptInput!]!) {
                    addPrompts(input: $input) { id success error }
                }
            """

            logger.warning(f"[prompt_sync] 📡 Calling AppSync GraphQL mutation: addPrompts")
            resp = _appsync_request(mutation, ctx, variables={"input": [gql_input]})

            # Check response
            logger.warning(f"[prompt_sync] 📥 <<< CLOUD RESPONSE RECEIVED <<<")
            logger.warning(f"[prompt_sync] Full response for '{prompt.get('id')}': {resp}")
            errors = resp.get("errors")
            if errors:
                logger.error(f"[prompt_sync] ❌ CLOUD SYNC FAILED for {prompt.get('id')}: {errors}")
                logger.error(f"[prompt_sync] This indicates AWS AppSync settings may be incorrect")
            else:
                data = resp.get("data", {}).get("addPrompts", [])
                logger.warning(f"[prompt_sync] ✅ SUCCESS - Synced prompt '{prompt.get('id')}' to cloud: {data}")
        except Exception as exc:
            logger.error(f"[prompt_sync] ❌ EXCEPTION during cloud sync for '{prompt.get('id', '?')}': {exc}")
            logger.error(f"[prompt_sync] Traceback: {traceback.format_exc()}")

    t = threading.Thread(target=_do, daemon=True, name="prompt-cloud-sync")
    t.start()


def delete_prompt_from_cloud(prompt_id: str) -> None:
    """Remove a prompt from cloud by ID. Runs in background thread."""
    def _do():
        try:
            ctx = _get_cloud_context()
            if ctx is None:
                return

            mutation = """
                mutation RemovePrompts($input: [ID!]!) {
                    removePrompts(input: $input) { id success error }
                }
            """

            resp = _appsync_request(mutation, ctx, variables={"input": [prompt_id]})

            errors = resp.get("errors")
            if errors:
                logger.warning(f"[prompt_sync] removePrompts error for {prompt_id}: {errors}")
            else:
                data = resp.get("data", {}).get("removePrompts", [])
                logger.info(f"[prompt_sync] Deleted prompt '{prompt_id}' from cloud: {data}")
        except Exception as exc:
            logger.warning(f"[prompt_sync] Failed to delete prompt '{prompt_id}' from cloud: {exc}")

    t = threading.Thread(target=_do, daemon=True, name="prompt-cloud-delete")
    t.start()


def fetch_cloud_prompts() -> List[Dict[str, Any]]:
    """Download all prompts for the current user from cloud DynamoDB.

    Returns a list of normalized prompt dicts (same shape as local prompts).
    Returns an empty list on any failure so callers can safely merge.
    This is a **synchronous** call — intended to be used inside get_prompts
    before the IPC response is sent so the UI gets the full superset.
    """
    try:
        ctx = _get_cloud_context()
        if ctx is None:
            return []

        owner = ctx["owner"]
        now = time.time()

        with _cloud_prompts_cache_lock:
            cached = _cloud_prompts_cache.get(owner)
            if cached and now - float(cached.get("timestamp", 0)) < _CLOUD_PROMPTS_CACHE_TTL_SECONDS:
                prompts = cached.get("prompts") or []
                logger.info(f"[prompt_sync] Using cached cloud prompts for {owner}: {len(prompts)} prompts")
                return [dict(p) for p in prompts]

        query = """
            query QueryPrompts($input: PromptQueryInput) {
                queryPrompts(input: $input) {
                    id
                    owner
                    version
                    prompt
                }
            }
        """

        resp = _appsync_request(query, ctx, variables={"input": {"owner": owner}})

        errors = resp.get("errors")
        if errors:
            logger.warning(f"[prompt_sync] queryPrompts error: {errors}")
            return []

        raw_items = resp.get("data", {}).get("queryPrompts") or []
        logger.info(f"[prompt_sync] Fetched {len(raw_items)} prompts from cloud")

        prompts: List[Dict[str, Any]] = []
        for item in raw_items:
            try:
                prompt_id = item.get("id", "")
                prompt_json = item.get("prompt", "{}")
                if isinstance(prompt_json, str):
                    try:
                        prompt_data = json.loads(prompt_json)
                    except (json.JSONDecodeError, ValueError):
                        # Raw text prompt (not JSON) — preserve as-is
                        prompt_data = prompt_json  # will be handled as non-dict below
                elif isinstance(prompt_json, dict):
                    prompt_data = prompt_json
                else:
                    prompt_data = {}

                # Build a normalized prompt dict matching local format
                if isinstance(prompt_data, dict):
                    normalized: Dict[str, Any] = {
                        "id": prompt_id,
                        "title": prompt_data.get("title", ""),
                        "topic": prompt_data.get("topic", ""),
                        "usageCount": prompt_data.get("usageCount", 0),
                        "sections": prompt_data.get("sections", []),
                        "userSections": prompt_data.get("userSections", []),
                        "humanInputs": prompt_data.get("humanInputs", []),
                        "lastModified": prompt_data.get("lastModified", ""),
                        "source": "cloud",
                        "readOnly": False,
                    }
                    # Restore markdown-mode fields if present
                    if prompt_data.get("format"):
                        normalized["format"] = prompt_data["format"]
                    if prompt_data.get("mdContent"):
                        normalized["mdContent"] = prompt_data["mdContent"]
                else:
                    # prompt_data is a raw string (not structured JSON) — preserve as rawContent
                    normalized: Dict[str, Any] = {
                        "id": prompt_id,
                        "title": prompt_id,
                        "topic": prompt_id,
                        "usageCount": 0,
                        "sections": [],
                        "userSections": [],
                        "humanInputs": [],
                        "lastModified": "",
                        "source": "cloud",
                        "readOnly": False,
                        "rawContent": str(prompt_data),
                    }
                if prompt_id:
                    prompts.append(normalized)
            except Exception as parse_exc:
                logger.warning(f"[prompt_sync] Failed to parse cloud prompt {item.get('id', '?')}: {parse_exc}")
                continue

        with _cloud_prompts_cache_lock:
            _cloud_prompts_cache[owner] = {
                "timestamp": now,
                "prompts": [dict(p) for p in prompts],
            }

        return prompts
    except Exception as exc:
        logger.warning(f"[prompt_sync] fetch_cloud_prompts failed: {exc}")
        return []


def sync_all_prompts_to_cloud(prompts: List[Dict[str, Any]]) -> None:
    """Bulk-push all local prompts to cloud. Skips read-only/sample prompts.
    Runs in background thread so it doesn't block the IPC response."""
    def _do():
        try:
            ctx = _get_cloud_context()
            if ctx is None:
                return

            owner = ctx["owner"]

            # Only sync user-owned prompts (not sample/read-only, not system)
            to_sync = [p for p in prompts if not p.get("readOnly") and p.get("id") and p.get("owner") != "system"]
            if not to_sync:
                logger.debug("[prompt_sync] No user prompts to sync to cloud")
                return

            logger.info(f"[prompt_sync] Syncing {len(to_sync)} local prompts to cloud...")

            # Batch in groups of 25 to avoid oversized requests
            BATCH_SIZE = 25
            total_ok = 0
            total_err = 0

            for i in range(0, len(to_sync), BATCH_SIZE):
                batch = to_sync[i:i + BATCH_SIZE]
                gql_inputs = [_prompt_to_graphql_input(p, owner) for p in batch]

                mutation = """
                    mutation AddPrompts($input: [PromptInput!]!) {
                        addPrompts(input: $input) { id success error }
                    }
                """

                resp = _appsync_request(mutation, ctx, variables={"input": gql_inputs})

                errors = resp.get("errors")
                if errors:
                    logger.warning(f"[prompt_sync] Batch sync error: {errors}")
                    total_err += len(batch)
                else:
                    results = resp.get("data", {}).get("addPrompts", [])
                    for r in results:
                        if r.get("success"):
                            total_ok += 1
                        else:
                            total_err += 1
                            logger.warning(f"[prompt_sync] Failed to sync prompt {r.get('id')}: {r.get('error')}")

            logger.info(f"[prompt_sync] Bulk sync complete: {total_ok} ok, {total_err} errors out of {len(to_sync)} prompts")
        except Exception as exc:
            logger.warning(f"[prompt_sync] Bulk sync failed: {exc}\n{traceback.format_exc()}")

    t = threading.Thread(target=_do, daemon=True, name="prompt-cloud-bulk-sync")
    t.start()
