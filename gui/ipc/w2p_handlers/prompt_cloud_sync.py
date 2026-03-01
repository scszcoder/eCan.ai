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
from datetime import datetime
from typing import Any, Dict, List, Optional

from utils.logger_helper import logger_helper as logger

# ---------------------------------------------------------------------------
# Helpers to obtain auth context from the running app
# ---------------------------------------------------------------------------

def _get_cloud_context() -> Optional[Dict[str, Any]]:
    """Return {session, token, endpoint, owner} from the running MainWindow, or None."""
    try:
        from app_context import AppContext
        mainwin = AppContext.get_main_window()
        if mainwin is None:
            logger.debug("[prompt_sync] MainWindow not available – skipping cloud sync")
            return None

        token = mainwin.get_auth_token()
        if not token:
            logger.debug("[prompt_sync] No auth token – skipping cloud sync")
            return None

        session = mainwin.session
        endpoint = mainwin.getWanApiEndpoint() if hasattr(mainwin, 'getWanApiEndpoint') else None
        owner = getattr(mainwin, 'user', None) or ""

        if not owner:
            logger.debug("[prompt_sync] No owner/user – skipping cloud sync")
            return None

        return {
            "session": session,
            "token": token,
            "endpoint": endpoint,
            "owner": owner,
        }
    except Exception as exc:
        logger.debug(f"[prompt_sync] Failed to get cloud context: {exc}")
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
    prompt_content = {
        "title": prompt.get("title", ""),
        "topic": prompt.get("topic", ""),
        "usageCount": prompt.get("usageCount", 0),
        "sections": prompt.get("sections", []),
        "userSections": prompt.get("userSections", []),
        "humanInputs": prompt.get("humanInputs", []),
        "source": prompt.get("source", "my_prompts"),
        "readOnly": False,
        "lastModified": prompt.get("lastModified", datetime.utcnow().isoformat()),
    }

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
                return

            owner = ctx["owner"]
            gql_input = _prompt_to_graphql_input(prompt, owner)

            mutation = """
                mutation AddPrompts($input: [PromptInput!]!) {
                    addPrompts(input: $input) { id success error }
                }
            """

            resp = _appsync_request(mutation, ctx, variables={"input": [gql_input]})

            # Check response
            errors = resp.get("errors")
            if errors:
                logger.warning(f"[prompt_sync] addPrompts error for {prompt.get('id')}: {errors}")
            else:
                data = resp.get("data", {}).get("addPrompts", [])
                logger.info(f"[prompt_sync] Synced prompt '{prompt.get('id')}' to cloud: {data}")
        except Exception as exc:
            logger.warning(f"[prompt_sync] Failed to sync prompt '{prompt.get('id', '?')}' to cloud: {exc}")

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


def sync_all_prompts_to_cloud(prompts: List[Dict[str, Any]]) -> None:
    """Bulk-push all local prompts to cloud. Skips read-only/sample prompts.
    Runs in background thread so it doesn't block the IPC response."""
    def _do():
        try:
            ctx = _get_cloud_context()
            if ctx is None:
                return

            owner = ctx["owner"]

            # Only sync user-owned prompts (not sample/read-only)
            to_sync = [p for p in prompts if not p.get("readOnly") and p.get("id")]
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
