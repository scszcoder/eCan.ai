import json
from typing import Any

import httpx

from utils.logger_helper import logger_helper as logger


def _truncate_string(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "..."


def _mask_large_field(value: Any) -> str:
    try:
        encoded = json.dumps(value)
        return f"[MASKED:{len(encoded)} bytes]"
    except Exception:
        return "[MASKED]"


    def _build_auth_headers(auth_token: str) -> dict[str, str]:
        tok = (auth_token or "").strip()
        if not tok:
            return {}
        if tok.lower().startswith("bearer "):
            return {"Authorization": tok}
        if tok.count(".") >= 2:
            return {"Authorization": tok}
        return {"x-api-key": tok}


    def _publish_step_result_mutation() -> str:
        return """
        mutation PublishPassiveStepResult($input: PassiveBrowserStepResultEnvelopeInput!) {
          publishPassiveStepResult(input: $input) {
            runId
            clientId
            stepId
            result
            dom_tree
          }
        }
        """


def truncate_screenshot_for_logging(
    data: Any,
    *,
    max_str: int = 500,
    max_list: int = 20,
    max_depth: int = 5,
) -> Any:
    """Best-effort log truncation for large browser payloads."""

    def _walk(value: Any, depth: int) -> Any:
        if depth > max_depth:
            return "[TRUNCATED_DEPTH]"

        if isinstance(value, dict):
            out: dict[str, Any] = {}
            for key, val in value.items():
                if key == "screenshot_base64" and isinstance(val, str):
                    out[key] = f"[MASKED:{len(val)} bytes]"
                    continue
                if key in {"dom_text", "selector_map", "dom_tree", "page_source", "html"}:
                    if isinstance(val, str):
                        out[key] = _truncate_string(val, max_str)
                    else:
                        out[key] = _mask_large_field(val)
                    continue
                out[key] = _walk(val, depth + 1)
            return out

        if isinstance(value, list):
            if not value:
                return value
            trimmed = [_walk(item, depth + 1) for item in value[:max_list]]
            if len(value) > max_list:
                trimmed.append(f"[TRUNCATED_LIST:{len(value)} items]")
            return trimmed

        if isinstance(value, str):
            return _truncate_string(value, max_str)

        return value

    return _walk(data, 0)


def remove_null_values(value: Any) -> Any:
    """Recursively remove None values from dicts/lists."""
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            if item is None:
                continue
            cleaned_item = remove_null_values(item)
            if cleaned_item is None:
                continue
            cleaned[key] = cleaned_item
        return cleaned
    if isinstance(value, list):
        cleaned_list = []
        for item in value:
            if item is None:
                continue
            cleaned_item = remove_null_values(item)
            if cleaned_item is None:
                continue
            cleaned_list.append(cleaned_item)
        return cleaned_list
    return value


def _mask_browser_payload(result_dict: dict[str, Any]) -> dict[str, Any]:
    browser_data = result_dict.get("browser")
    if browser_data and isinstance(browser_data, dict):
        screenshot = browser_data.get("screenshot_base64")
        if screenshot and isinstance(screenshot, str) and len(screenshot) > 100:
            browser_data["screenshot_base64"] = f"[MASKED:{len(screenshot)} bytes]"

        selector_map = browser_data.get("selector_map")
        if selector_map and isinstance(selector_map, (list, dict)):
            browser_data["selector_map"] = _mask_large_field(selector_map)

        dom_text = browser_data.get("dom_text")
        if dom_text and isinstance(dom_text, str) and len(dom_text) > 10000:
            browser_data["dom_text"] = f"[MASKED:{len(dom_text)} chars]"
    return result_dict


def _ensure_required_result_fields(result_dict: dict[str, Any]) -> dict[str, Any]:
    defaults = {
        "schema_version": 1,
        "type": "browser_use_passive_step_result",
        "ok": True,
        "elapsed_ms": 0,
        "actions": [],
        "action_results": [],
        "errors": [],
        "browser": {},
    }
    for key, value in defaults.items():
        if key not in result_dict or result_dict.get(key) is None:
            result_dict[key] = value
    return result_dict


async def publish_step_result(
    result: Any,
    http_endpoint: str,
    auth_token: str,
    client_id: str,
) -> None:
    """Publish a passive step result to AppSync."""
    result_dict = result.model_dump() if hasattr(result, "model_dump") else dict(result)
    result_dict = _mask_browser_payload(result_dict)
    result_dict = remove_null_values(result_dict)
    result_dict = _ensure_required_result_fields(result_dict)

    envelope = {
        "runId": result.run_id,
        "clientId": client_id,
        "stepId": result.step_id,
        "result": json.dumps(result_dict),
        "dom_tree": json.dumps({}),
    }

    headers = {
        "Content-Type": "application/json",
        **_build_auth_headers(auth_token),
        "cache-control": "no-cache",
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            http_endpoint,
            json={"query": _publish_step_result_mutation(), "variables": {"input": envelope}},
            headers=headers,
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and data.get("errors"):
            logger.error(f"publish_step_result failed: {data.get('errors')}")
            raise RuntimeError(f"publish_step_result failed: {data.get('errors')}")
