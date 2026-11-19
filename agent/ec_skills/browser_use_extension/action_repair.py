"""Repair a browser model's reply so its actions match the ones eCan registers.

Models trained on older browser-use releases still answer with ``go_to_url`` or click by
xpath. browser-use rejects the whole reply, and after a few rejections in a row the agent
stops (2026-11-18: a Shopify label run stopped one click short of "Create shipping label",
the model having asked to click it by xpath five times). The Qwen adapter maps these names
for Qwen only; this applies to every model's reply.
"""
import json
import re

# Old action name -> the registered one, where the parameters carry over unchanged.
RENAMES = {"go_to_url": "navigate", "open_url": "navigate", "click_element": "click",
           "click_element_by_index": "click", "input_text": "input",
           "extract_content": "extract", "search_google": "search"}
_XPATH_TEXT = re.compile(r"""(?:text\(\)|\.|normalize-space\([^)]*\))\s*[,=]\s*(['"])(.+?)\1""")


def _click_text(params: dict):
    """The visible text a non-index click aims at, or None."""
    if not isinstance(params, dict) or "index" in params:
        return None
    if isinstance(params.get("text"), str) and params["text"].strip():
        return params["text"].strip()
    m = _XPATH_TEXT.search(str(params.get("xpath") or ""))
    return m.group(2).strip() if m else None


def _repair(action):
    if not isinstance(action, dict) or len(action) != 1:
        return action
    (name, params), = action.items()
    name = RENAMES.get(name, name)
    if name == "click":
        text = _click_text(params)
        if text:
            return {"click_text": {"text": text}}
    return {name: params}


def repair_actions(content: str) -> str:
    """``content`` with its actions repaired, or unchanged when nothing needed (or could be) fixed."""
    try:
        data = json.loads(content)
    except (TypeError, ValueError):
        return content
    if not isinstance(data, dict) or not isinstance(data.get("action"), list):
        return content
    fixed = [_repair(a) for a in data["action"]]
    if fixed == data["action"]:
        return content
    data["action"] = fixed
    return json.dumps(data, ensure_ascii=False)
