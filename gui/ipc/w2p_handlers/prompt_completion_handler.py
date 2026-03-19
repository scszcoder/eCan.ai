"""Prompt auto-completion handler: relays reqPromptAutoCompletion to AppSync cloud."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from gui.ipc.types import IPCRequest, IPCResponse, create_success_response, create_error_response
from gui.ipc.registry import IPCHandlerRegistry
from utils.logger_helper import logger_helper as logger


# ---------------------------------------------------------------------------
# Cloud context helper (reuses pattern from prompt_cloud_sync / skill_editor_cloud_relay)
# ---------------------------------------------------------------------------

def _get_cloud_context() -> Optional[Dict[str, Any]]:
    """Return {session, token, endpoint, owner} from the running MainWindow, or None."""
    try:
        from app_context import AppContext
        mainwin = AppContext.get_main_window()
        if mainwin is None:
            return None

        token = mainwin.get_auth_token()
        if not token:
            return None

        session = mainwin.session
        endpoint = mainwin.getWanApiEndpoint() if hasattr(mainwin, 'getWanApiEndpoint') else None
        owner = getattr(mainwin, 'user', None) or ""

        return {
            "session": session,
            "token": token,
            "endpoint": endpoint,
            "owner": owner,
        }
    except Exception as exc:
        logger.debug(f"[prompt_completion] Failed to get cloud context: {exc}")
        return None


def _appsync_request(query_string: str, ctx: Dict[str, Any],
                     variables: Optional[Dict] = None,
                     timeout: int = 60) -> Dict:
    """Send a GraphQL request to AppSync (JSON content-type for variables support)."""
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
            timeout=timeout,
            headers=headers,
            json=payload,
        )
        jresp = resp.json()
        logger.debug(
            f"[prompt_completion] AppSync response status={resp.status_code}, "
            f"keys={list(jresp.keys()) if isinstance(jresp, dict) else 'N/A'}"
        )
        return jresp
    except Exception as exc:
        logger.warning(f"[prompt_completion] AppSync request failed: {exc}")
        return {"errors": [{"errorType": "RequestError", "message": str(exc)}]}


# ---------------------------------------------------------------------------
# GraphQL mutation string
# ---------------------------------------------------------------------------

_GQL_REQ_PROMPT_AUTO_COMPLETION = """
mutation ReqPromptAutoCompletion($input: PromptAutoCompletionInput!) {
  reqPromptAutoCompletion(input: $input) {
    completion
    model
    error
  }
}
"""


# ---------------------------------------------------------------------------
# IPC Handler
# ---------------------------------------------------------------------------

@IPCHandlerRegistry.handler('reqPromptAutoCompletion')
def handle_req_prompt_auto_completion(request: IPCRequest, params: Optional[dict]) -> IPCResponse:
    """Relay reqPromptAutoCompletion mutation to AppSync cloud.

    Params (from GraphQL variables.input, unwrapped by LocalServer):
        prefix: str         — text before cursor
        suffix: str         — text after cursor
        section: str        — prompt section type
        prompt_name: str    — name of the prompt being edited
        max_tokens: int     — max completion tokens
        temperature: float  — sampling temperature
        provider: str       — optional LLM provider override
        model: str          — optional model override
    """
    try:
        params = params or {}
        logger.info(f"[prompt_completion] reqPromptAutoCompletion called, prefix_len={len(params.get('prefix', ''))}")

        ctx = _get_cloud_context()
        if ctx is None:
            logger.warning("[prompt_completion] No cloud context available")
            return create_success_response(request, {
                "completion": "",
                "model": "",
                "error": "Not authenticated — please log in first."
            })

        # Build the input object for the GraphQL mutation
        completion_input: Dict[str, Any] = {}
        for key in ('prefix', 'suffix', 'section', 'prompt_name',
                     'max_tokens', 'temperature', 'provider', 'model'):
            if key in params and params[key] is not None:
                completion_input[key] = params[key]

        variables = {"input": completion_input}
        jresp = _appsync_request(_GQL_REQ_PROMPT_AUTO_COMPLETION, ctx, variables=variables, timeout=30)

        if "errors" in jresp:
            error_msg = jresp["errors"][0].get("message", "Unknown error") if jresp["errors"] else "Unknown error"
            logger.warning(f"[prompt_completion] AppSync error: {error_msg}")
            return create_success_response(request, {
                "completion": "",
                "model": "",
                "error": error_msg
            })

        data = jresp.get("data", {}).get("reqPromptAutoCompletion")
        
        # Ensure we always return a valid response structure (non-null)
        if data is None:
            logger.warning("[prompt_completion] Cloud returned null, returning empty completion")
            return create_success_response(request, {
                "completion": "",
                "model": "",
                "error": "Cloud service unavailable"
            })
        
        # Ensure all required fields are present
        if "completion" not in data:
            data["completion"] = ""
        if "model" not in data:
            data["model"] = ""
        if "error" not in data:
            data["error"] = ""
            
        return create_success_response(request, data)

    except Exception as e:
        logger.error(f"[prompt_completion] Error: {e}", exc_info=True)
        return create_success_response(request, {
            "completion": "",
            "model": "",
            "error": str(e)
        })
