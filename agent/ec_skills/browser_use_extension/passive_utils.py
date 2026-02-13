import json
import os
import re
from typing import Any

import httpx

from utils.logger_helper import logger_helper as logger


def _truncate_string(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "..."


def _truncate_base64(value: str, prefix_len: int = 8, suffix_len: int = 8) -> str:
    """Truncate base64 string showing first/last chars with byte count in middle.
    
    Example: 'ABCDEFGH[10567832bytes]HGFEDCBA'
    """
    if len(value) <= prefix_len + suffix_len + 20:
        return value
    return f"{value[:prefix_len]}[{len(value)}bytes]{value[-suffix_len:]}"


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


# Pattern to find screenshot_base64 in string representations
_SCREENSHOT_PATTERN = re.compile(r"'screenshot_base64':\s*'([^']{50,})'")


def _truncate_screenshot_in_string(s: str) -> str:
    """Truncate screenshot_base64 values embedded in string representations."""
    def _replacer(match: re.Match) -> str:
        val = match.group(1)
        if len(val) > 36:
            truncated = _truncate_base64(val)
            return f"'screenshot_base64': '{truncated}'"
        return match.group(0)
    return _SCREENSHOT_PATTERN.sub(_replacer, s)


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
                    out[key] = _truncate_base64(val)
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
            # Also check for embedded screenshot_base64 in string representations
            truncated = _truncate_string(value, max_str)
            if "'screenshot_base64'" in truncated:
                truncated = _truncate_screenshot_in_string(truncated)
            return truncated

        # Handle objects with __dict__ (like ActionMessage)
        if hasattr(value, "__dict__"):
            try:
                obj_dict = _walk(value.__dict__, depth + 1)
                return f"{type(value).__name__}({obj_dict})"
            except Exception:
                return str(value)[:max_str]

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
            browser_data["screenshot_base64"] = _truncate_base64(screenshot)

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
    """Publish a passive step result to AppSync.
    
    Uses sync httpx client to avoid sniffio detection issues when called
    from run_async_in_sync contexts.
    """
    result_dict = result.model_dump() if hasattr(result, "model_dump") else dict(result)
    result_dict.pop("dom_tree", None)  # Remove from result dict, we'll extract from browser.dom_text
    
    # Extract dom_text and selector_map from browser to use as dom_tree (separate AppSync field)
    dom_tree_payload = {}
    browser_data = result_dict.get("browser")
    logger.info(f"[publish_step_result] browser_data type={type(browser_data).__name__}, keys={list(browser_data.keys()) if isinstance(browser_data, dict) else 'N/A'}")
    if browser_data and isinstance(browser_data, dict):
        # Extract dom_text and move to dom_tree field
        dom_text = browser_data.pop("dom_text", None)
        if dom_text and isinstance(dom_text, str):
            dom_tree_payload["dom_text"] = dom_text
            logger.info(f"[publish_step_result] ✅ Extracted dom_text ({len(dom_text)} chars) for dom_tree field")
        else:
            logger.warning(f"[publish_step_result] ⚠️ dom_text missing or not a string: type={type(dom_text).__name__}, truthy={bool(dom_text)}")
        
        # Extract selector_map and move to dom_tree field (cloud worker needs it for element interaction)
        selector_map = browser_data.pop("selector_map", None)
        if selector_map and isinstance(selector_map, (list, dict)):
            dom_tree_payload["selector_map"] = selector_map
            selector_map_len = len(json.dumps(selector_map)) if selector_map else 0
            logger.info(f"[publish_step_result] ✅ Extracted selector_map ({selector_map_len} bytes, {len(selector_map)} items) for dom_tree field")
        else:
            logger.warning(f"[publish_step_result] ⚠️ selector_map missing or empty: type={type(selector_map).__name__ if selector_map is not None else 'None'}, truthy={bool(selector_map)}")
        
        # Replace screenshot with OCR placeholder (not truncated base64)
        screenshot = browser_data.get("screenshot_base64")
        if screenshot and isinstance(screenshot, str) and len(screenshot) > 100:
            screenshot_len = len(screenshot)
            browser_data["screenshot_base64"] = "[OCR_PENDING]"
            browser_data.setdefault("ocr_text", "[OCR_PLACEHOLDER]")
            logger.info(f"[publish_step_result] ✅ Replaced screenshot_base64 with OCR placeholder ({screenshot_len} bytes)")
    else:
        logger.warning(f"[publish_step_result] ⚠️ browser_data is not a dict, cannot extract dom_text/selector_map")
    
    # Remove null values - AppSync AWSJSON cannot handle null in non-nullable fields
    result_dict = remove_null_values(result_dict)
    result_dict = _ensure_required_result_fields(result_dict)

    # Apply size cap to dom_tree to stay within AppSync payload limit (240KB)
    max_dom_tree_bytes = int(os.getenv("ECAN_PASSIVE_DOM_TREE_MAX_BYTES", "204800"))
    dom_tree_json = json.dumps(dom_tree_payload or {})
    if len(dom_tree_json) > max_dom_tree_bytes:
        logger.warning(
            f"[publish_step_result] dom_tree exceeds cap: {len(dom_tree_json)} bytes > {max_dom_tree_bytes} bytes. Reducing."
        )
        from agent.ec_skills.browser_use_extension.appsync_passive_client import _reduce_dom_tree_payload
        dom_tree_payload = _reduce_dom_tree_payload(dom_tree_payload, max_dom_tree_bytes)
        dom_tree_json = json.dumps(dom_tree_payload or {})
        if len(dom_tree_json) > max_dom_tree_bytes:
            dom_tree_payload = {
                "_truncated": True,
                "original_bytes": len(json.dumps(dom_tree_payload)),
                "max_bytes": max_dom_tree_bytes,
                "note": "dom_tree truncated to stay under websocket payload limit",
            }
            dom_tree_json = json.dumps(dom_tree_payload)

    envelope = {
        "runId": result.run_id,
        "clientId": client_id,
        "stepId": result.step_id,
        "result": json.dumps(result_dict),
        "dom_tree": dom_tree_json,
    }
    
    # Log full envelope before sending
    logger.debug(f"[publish_step_result] Sending envelope: runId={envelope['runId']}, stepId={envelope['stepId']}, result_len={len(envelope['result'])}, dom_tree_len={len(envelope['dom_tree'])}")

    headers = {
        "Content-Type": "application/json",
        **_build_auth_headers(auth_token),
        "cache-control": "no-cache",
    }

    # Fix D: Retry with exponential backoff for transient failures
    max_retries = int(os.getenv("ECAN_PASSIVE_PUBLISH_MAX_RETRIES", "3"))
    base_delay = 1.0
    last_error: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            # Use sync client to avoid sniffio "unknown async library" error
            # when called from run_async_in_sync contexts
            with httpx.Client() as client:
                resp = client.post(
                    http_endpoint,
                    json={"query": _publish_step_result_mutation(), "variables": {"input": envelope}},
                    headers=headers,
                    timeout=30.0,
                )
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, dict) and data.get("errors"):
                    logger.error(f"[publish_step_result] GraphQL errors (attempt {attempt}/{max_retries}): {data.get('errors')}")
                    raise RuntimeError(f"publish_step_result failed: {data.get('errors')}")
                if attempt > 1:
                    logger.info(f"[publish_step_result] ✅ Succeeded on retry attempt {attempt}")
                return  # Success
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                delay = base_delay * (2 ** (attempt - 1))  # 1s, 2s, 4s
                logger.warning(f"[publish_step_result] Attempt {attempt}/{max_retries} failed: {e}. Retrying in {delay:.1f}s...")
                import time
                time.sleep(delay)
            else:
                logger.error(f"[publish_step_result] All {max_retries} attempts failed. Last error: {e}")

    if last_error is not None:
        raise last_error
