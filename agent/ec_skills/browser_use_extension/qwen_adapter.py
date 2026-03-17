"""
Qwen/Ollama Output Format Adapter for browser-use

Two-layer architecture:
  Layer 1 (Generic): llm_utils/output_cleaner.py
    - Remove markdown code blocks (```json)
    - Remove <think> tags
    - Extract JSON from mixed text
    - Safe for ALL LLM calls (browser-use and normal)

  Layer 2 (Browser-use specific): THIS FILE
    - Convert flat action format to AgentOutput schema
    - Convert error/status responses to done actions
    - Convert plain text refusals to done actions
    - Ensure required fields exist (evaluation_previous_goal, memory, next_goal, action)

All structural validation is handled by browser-use's Pydantic validation.
"""

import re
from typing import Any

from utils.logger_helper import logger_helper as logger


def _make_agent_output(action_list: list, eval_text: str = '', memory_text: str = '', goal_text: str = '') -> dict:
    """
    Build a valid browser-use AgentOutput dict.
    
    Args:
        action_list: List of action dicts, e.g. [{"go_to_url": {"url": "..."}}]
        eval_text: evaluation_previous_goal text
        memory_text: memory text
        goal_text: next_goal text
    """
    return {
        "evaluation_previous_goal": eval_text or '',
        "memory": memory_text or '',
        "next_goal": goal_text or '',
        "action": action_list
    }


def _convert_flat_action(data: dict) -> dict | None:
    """
    Convert flat/simplified action JSON to browser-use AgentOutput format.
    
    Handles patterns like:
      {"action": "navigate", "url": "https://..."}
      {"action": "click", "element": "..."}
      {"action": "input_text", "text": "...", "index": 5}
      {"action": "done", "text": "result"}
      {"navigate": {"url": "..."}}
      {"go_to_url": {"url": "..."}}
    """
    # Pattern 1: {"action": "<action_name>", ...other_params}
    if 'action' in data and isinstance(data['action'], str):
        action_name = data['action'].lower().strip()
        params = {k: v for k, v in data.items() if k not in ('action', 'thinking', 'evaluation_previous_goal', 'memory', 'next_goal')}
        
        # Map common simplified action names to browser-use registered action names
        # Current browser_use action names (from AgentOutput validation):
        #   navigate, search, go_back, wait, click, input, upload_file,
        #   switch, close, extract, scroll, send_keys, find_text,
        #   dropdown_options, select_dropdown, done
        action_map = {
            'navigate': 'navigate',
            'goto': 'navigate',
            'go_to': 'navigate',
            'open': 'navigate',
            'open_url': 'navigate',
            'go_to_url': 'navigate',
            'click': 'click',
            'click_element': 'click',
            'input': 'input',
            'input_text': 'input',
            'type': 'input',
            'scroll': 'scroll',
            'scroll_down': 'scroll',
            'scroll_up': 'scroll',
            'done': 'done',
            'finish': 'done',
            'complete': 'done',
            'wait': 'wait',
            'extract': 'extract',
            'extract_content': 'extract',
            'screenshot': 'extract',
            'search': 'search',
            'search_google': 'search',
            'go_back': 'go_back',
            'back': 'go_back',
            'send_keys': 'send_keys',
            'find_text': 'find_text',
            'scroll_to': 'find_text',
            'scroll_to_text': 'find_text',
            'switch': 'switch',
            'switch_tab': 'switch',
            'close': 'close',
            'close_tab': 'close',
            'upload_file': 'upload_file',
            'select_dropdown': 'select_dropdown',
            'dropdown_options': 'dropdown_options',
        }
        
        bu_action_name = action_map.get(action_name, action_name)
        
        # Standard browser_use action names (custom controller actions are also allowed)
        valid_bu_actions = {
            'navigate', 'click', 'input', 'scroll', 'extract', 'done', 'search',
            'go_back', 'wait', 'switch', 'close', 'send_keys', 'find_text',
            'upload_file', 'dropdown_options', 'select_dropdown',
        }
        
        # Keep unknown actions as-is to support custom controller actions (e.g. list_files).
        # Validation/execution should be handled by controller/browser-use, not hardcoded here.
        if bu_action_name not in valid_bu_actions:
            logger.info(f"[QwenAdapter] 🔄 Preserving custom action '{action_name}' as '{bu_action_name}'")
            action_obj = {bu_action_name: params or {}}
        # Build action params based on action type
        elif bu_action_name == 'navigate':
            url = params.get('url', params.get('href', params.get('link', '')))
            action_obj = {bu_action_name: {'url': url}}
        elif bu_action_name == 'click':
            raw_index = params.get('index', params.get('element', params.get('xpath')))
            # Check if raw_index is actually a numeric index
            index_val = None
            element_as_text = ''
            if raw_index is not None:
                if str(raw_index).isdigit() and int(raw_index) >= 1:
                    index_val = int(raw_index)
                else:
                    # Non-numeric element value (e.g. "百度一下") — treat as text target
                    element_as_text = str(raw_index)
            target = params.get('target', params.get('label', params.get('text', ''))) or element_as_text
            if index_val is not None:
                action_obj = {bu_action_name: {'index': index_val}}
            elif target:
                # LLM gave text target but no index — use find_text to scroll to it first
                logger.info(f"[QwenAdapter] 🔄 click has target '{target}' but no index, converting to find_text")
                action_obj = {'find_text': {'text': str(target)}}
                bu_action_name = 'find_text'
            else:
                # No index and no target — use extract to observe the page
                logger.info(f"[QwenAdapter] 🔄 click has no index or target, converting to extract")
                action_obj = {'extract': {'query': 'Find clickable elements on the page'}}
                bu_action_name = 'extract'
        elif bu_action_name == 'input':
            raw_index = params.get('index', params.get('element'))
            text = params.get('text', params.get('value', ''))
            # Check if raw_index is actually a numeric index
            index_val = None
            element_as_text = ''
            if raw_index is not None:
                if str(raw_index).isdigit() and int(raw_index) >= 1:
                    index_val = int(raw_index)
                else:
                    element_as_text = str(raw_index)
            target = params.get('target', params.get('label', '')) or element_as_text
            if index_val is not None:
                action_obj = {bu_action_name: {'index': index_val, 'text': str(text)}}
            elif target:
                # LLM gave text target but no index — use find_text to scroll to it first
                logger.info(f"[QwenAdapter] 🔄 input has target '{target}' but no index, converting to find_text")
                action_obj = {'find_text': {'text': str(target)}}
                bu_action_name = 'find_text'
            else:
                # No valid index — use extract to observe the page
                logger.info(f"[QwenAdapter] 🔄 input has no valid index, converting to extract")
                action_obj = {'extract': {'query': 'Find input elements on the page'}}
                bu_action_name = 'extract'
        elif bu_action_name == 'done':
            text = params.get('text', params.get('message', params.get('result', 'Task completed')))
            success = params.get('success', True)
            action_obj = {bu_action_name: {'text': str(text), 'success': bool(success)}}
        elif bu_action_name == 'search':
            query = params.get('query', params.get('text', params.get('q', '')))
            action_obj = {bu_action_name: {'query': query}}
        elif bu_action_name == 'find_text':
            text = params.get('text', params.get('element', params.get('target', params.get('label', ''))))
            if text:
                action_obj = {bu_action_name: {'text': str(text)}}
            else:
                action_obj = {'extract': {'query': 'Find text elements on the page'}}
                bu_action_name = 'extract'
        elif bu_action_name in ('scroll', 'wait', 'extract', 'go_back', 'switch', 'close',
                                'send_keys', 'upload_file', 'dropdown_options', 'select_dropdown'):
            action_obj = {bu_action_name: params or {}}
        else:
            action_obj = {bu_action_name: params}
        
        logger.info(f"[QwenAdapter] 🔄 Converted flat action '{action_name}' → '{bu_action_name}'")
        return _make_agent_output(
            [action_obj],
            eval_text=data.get('evaluation_previous_goal', ''),
            memory_text=data.get('memory', ''),
            goal_text=data.get('next_goal', '')
        )
    
    # Pattern 2: {"go_to_url": {"url": "..."}} or {"navigate": {"url": "..."}}
    # (action dict at top level, no wrapping). Also allow custom one-key actions.
    known_actions = {
        'navigate', 'click', 'input', 'done', 'scroll', 'wait', 'extract',
        'search', 'go_back', 'switch', 'close', 'send_keys', 'find_text',
        'upload_file', 'dropdown_options', 'select_dropdown',
        # Legacy names that LLMs may still output
        'go_to_url', 'click_element', 'input_text', 'scroll_down', 'scroll_up',
        'extract_content', 'open_url', 'open_tab', 'switch_tab', 'close_tab', 'search_google',
    }
    # Map non-standard/legacy top-level action names to current browser-use names
    top_level_action_map = {
        'go_to_url': 'navigate',
        'open_url': 'navigate',
        'click_element': 'click',
        'input_text': 'input',
        'scroll_down': 'scroll',
        'scroll_up': 'scroll',
        'extract_content': 'extract',
        'open_tab': 'navigate',
        'switch_tab': 'switch',
        'close_tab': 'close',
        'search_google': 'search',
    }
    if 'action' not in data and len(data.keys()) == 1:
        action_name = list(data.keys())[0]
        action_params = data[action_name]
        if not isinstance(action_params, dict):
            action_params = {}
        # Remap to browser-use canonical name if needed
        bu_name = top_level_action_map.get(action_name, action_name)
        action_obj = {bu_name: action_params}
        if action_name in known_actions:
            logger.info(f"[QwenAdapter] 🔄 Converted top-level action '{action_name}' → '{bu_name}' to action array")
        else:
            logger.info(f"[QwenAdapter] 🔄 Converted top-level custom action '{action_name}' to action array")
        return _make_agent_output([action_obj])
    
    return None


def _convert_error_response(data: dict) -> dict | None:
    """
    Convert error/status JSON to browser-use AgentOutput format.
    
    Handles patterns like:
      {"status": "error", "message": "Cannot navigate..."}
      {"error": "...", "reason": "..."}
    """
    if 'status' in data and data.get('status') in ('error', 'failed', 'failure'):
        msg = data.get('message', data.get('reason', data.get('error', 'Unknown error')))
        logger.info(f"[QwenAdapter] 🔄 Converted error response to done action")
        return _make_agent_output(
            [{'done': {'text': str(msg)[:500], 'success': False}}],
            eval_text='Model reported an error',
            memory_text=str(msg)[:200],
            goal_text='Handle error and retry'
        )
    
    if 'error' in data and isinstance(data['error'], str):
        msg = data.get('error', '') + ' ' + data.get('reason', '')
        logger.info(f"[QwenAdapter] 🔄 Converted error dict to done action")
        return _make_agent_output(
            [{'done': {'text': msg.strip()[:500], 'success': False}}],
            eval_text='Model reported an error',
            memory_text=msg.strip()[:200],
            goal_text='Handle error and retry'
        )
    
    return None


def _convert_reasoning_response(data: dict) -> dict | None:
    """
    Convert Qwen reasoning model output to browser-use AgentOutput format.
    
    Handles patterns like:
      {"success": true, "results": [...]}
    """
    if 'success' in data or 'results' in data:
        results = data.get('results', [])
        success = data.get('success', True)
        
        if results:
            if isinstance(results, list):
                summary = '\n'.join([str(r.get('title', r)) if isinstance(r, dict) else str(r) for r in results[:5]])
            else:
                summary = str(results)
        else:
            summary = "Task completed" if success else "Task failed"
        
        logger.info(f"[QwenAdapter] 🔄 Converted reasoning model output")
        return _make_agent_output(
            [{'done': {'text': summary[:500]}}],
            eval_text='Completed reasoning task',
            memory_text=f'Reasoning results: {summary[:200]}',
            goal_text='Return results to user'
        )
    
    return None


def _convert_plain_text(content: str) -> str | None:
    """
    Convert plain text (non-JSON) responses to browser-use AgentOutput JSON.
    
    Handles cases where the model outputs plain text refusals like:
      "I cannot directly navigate to external websites..."
    """
    import json
    
    # Check if it looks like a refusal or plain text response
    refusal_patterns = [
        'i cannot', 'i can\'t', 'i am unable', 'i\'m unable',
        'i don\'t have access', 'i do not have access',
        'cannot navigate', 'cannot browse', 'cannot access',
        'not able to', 'unable to navigate', 'unable to browse',
        'no browser available', 'browser is not available',
    ]
    
    content_lower = content.lower().strip()
    is_refusal = any(p in content_lower for p in refusal_patterns)
    
    if is_refusal:
        logger.info(f"[QwenAdapter] 🔄 Detected plain text refusal, converting to done action")
        result = _make_agent_output(
            [{'done': {'text': content[:500], 'success': False}}],
            eval_text='Model refused to execute the action',
            memory_text='Model does not understand its role as browser automation agent',
            goal_text='Retry with clearer instructions'
        )
        return json.dumps(result, ensure_ascii=False)
    
    return None


def _sanitize_action_array(actions: list) -> list:
    """
    Sanitize action array items to fix common LLM output issues:
    1. Unwrap model class names: {"DoneActionModel": {"done": true}} → {"done": {"text": "Task completed", "success": true}}
    2. Fix index values < 1 for click/input actions (browser_use requires index >= 1)
    3. Map legacy action names to current browser_use names
    """
    # Standard browser_use action names
    valid_actions = {
        'navigate', 'click', 'input', 'scroll', 'extract', 'done', 'search',
        'go_back', 'wait', 'switch', 'close', 'send_keys', 'find_text',
        'upload_file', 'dropdown_options', 'select_dropdown',
    }
    # Model class name → action name mapping
    model_class_map = {
        'doneactionmodel': 'done',
        'navigateactionmodel': 'navigate',
        'clickactionmodel': 'click',
        'inputactionmodel': 'input',
        'scrollactionmodel': 'scroll',
        'extractactionmodel': 'extract',
        'searchactionmodel': 'search',
        'gobackactionmodel': 'go_back',
        'waitactionmodel': 'wait',
        'switchactionmodel': 'switch',
        'closeactionmodel': 'close',
        'sendkeysactionmodel': 'send_keys',
        'findtextactionmodel': 'find_text',
        'uploadfileactionmodel': 'upload_file',
        'dropdownoptionsactionmodel': 'dropdown_options',
        'selectdropdownactionmodel': 'select_dropdown',
    }
    # Legacy action name mapping
    legacy_map = {
        'go_to_url': 'navigate', 'open_url': 'navigate',
        'click_element': 'click', 'input_text': 'input',
        'scroll_down': 'scroll', 'scroll_up': 'scroll',
        'scroll_to': 'find_text', 'scroll_to_text': 'find_text',
        'extract_content': 'extract', 'search_google': 'search',
        'switch_tab': 'switch', 'close_tab': 'close', 'open_tab': 'navigate',
    }

    sanitized = []
    for action in actions:
        if not isinstance(action, dict):
            continue

        # Check if action uses model class name as key
        keys = list(action.keys())
        if len(keys) == 1:
            key = keys[0]
            key_lower = key.lower()

            # Unwrap model class name
            if key_lower in model_class_map:
                real_action = model_class_map[key_lower]
                inner = action[key]
                if isinstance(inner, dict):
                    # e.g. {"DoneActionModel": {"done": true}} → {"done": {"text": "Task completed", "success": true}}
                    action = {real_action: inner}
                elif isinstance(inner, bool):
                    # e.g. {"DoneActionModel": {"done": true}} where inner is just True
                    if real_action == 'done':
                        action = {'done': {'text': 'Task completed', 'success': bool(inner)}}
                    else:
                        action = {real_action: {}}
                else:
                    action = {real_action: {}}
                logger.info(f"[QwenAdapter] 🔄 Unwrapped model class '{key}' → '{real_action}'")

            # Map legacy action names
            elif key_lower in legacy_map:
                real_action = legacy_map[key_lower]
                action = {real_action: action[key] if isinstance(action[key], dict) else {}}
                logger.info(f"[QwenAdapter] 🔄 Remapped legacy action '{key}' → '{real_action}'")

        # Keep custom action keys; do not force-convert to extract here.
        action_keys = set(action.keys())
        if not (action_keys & valid_actions):
            logger.info(f"[QwenAdapter] 🔄 Preserving custom action keys: {list(action_keys)}")

        # Fix index values for click/input (must be >= 1)
        for act_name in ('click', 'input'):
            if act_name in action and isinstance(action[act_name], dict):
                idx = action[act_name].get('index')
                if idx is not None and isinstance(idx, (int, float)) and idx < 1:
                    action[act_name]['index'] = 1
                    logger.info(f"[QwenAdapter] 🔧 Fixed {act_name} index {idx} → 1 (minimum)")

        # Fix done action: ensure it has text and success fields
        if 'done' in action and isinstance(action['done'], dict):
            done_params = action['done']
            if 'text' not in done_params:
                done_params['text'] = 'Task completed'
            if 'success' not in done_params:
                done_params['success'] = True

        sanitized.append(action)

    # If all actions were invalid, create a fallback done action
    if not sanitized:
        sanitized = [{'done': {'text': 'Task completed', 'success': True}}]

    return sanitized


def clean_qwen_response(content: str) -> str:
    """
    Clean and adapt Qwen/Ollama model response to browser-use AgentOutput format.
    
    Handles multiple output patterns from weak/non-compliant models:
    1. Remove markdown code blocks (```json)
    2. Convert flat action format: {"action": "navigate", "url": "..."}
    3. Convert error responses: {"status": "error", "message": "..."}
    4. Convert reasoning model format: {"success": true, "results": [...]}
    5. Convert plain text refusals to done actions
    6. Ensure required fields exist and action is a valid array
    
    Args:
        content: Raw response content from LLM
        
    Returns:
        Cleaned and adapted content in browser-use AgentOutput JSON format
    """
    if not content:
        return content
    
    import json
    original_content = content
    
    # Step 1: Basic whitespace cleanup
    # Note: Generic cleaning (markdown, think tags) is already done by LoggingBrowserUseChatOpenAI base class
    content = content.strip()
    
    # Step 2: Try to parse as JSON
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        # Not JSON - try plain text conversion
        converted = _convert_plain_text(content)
        if converted:
            logger.info(f"[QwenAdapter] ✂️ Converted plain text to AgentOutput (original: {len(original_content)})")
            return converted
        # Cannot parse or convert - return as-is, let browser-use handle the error
        return content
    
    if not isinstance(data, dict):
        return content
    
    # Step 3: Check if already valid AgentOutput format
    has_required = all(k in data for k in ['evaluation_previous_goal', 'memory', 'next_goal', 'action'])
    action_is_valid_array = isinstance(data.get('action'), list) and len(data.get('action', [])) > 0
    
    if has_required and action_is_valid_array:
        # Sanitize action array (fix model class names, invalid index values, etc.)
        data['action'] = _sanitize_action_array(data['action'])
        # Clean extra fields
        allowed_fields = {'evaluation_previous_goal', 'memory', 'next_goal', 'action', 'thinking'}
        extra_fields = set(data.keys()) - allowed_fields
        if extra_fields:
            logger.debug(f"[QwenAdapter] Removing extra fields: {extra_fields}")
            for field in extra_fields:
                data.pop(field, None)
        content = json.dumps(data, ensure_ascii=False)
        if content != original_content:
            logger.info(f"[QwenAdapter] ✂️ Cleaned valid response (sanitized actions)")
        return content
    
    # Step 4: Try conversion strategies (in priority order)
    converters = [
        ('flat_action', _convert_flat_action),
        ('error_response', _convert_error_response),
        ('reasoning', _convert_reasoning_response),
    ]
    
    for name, converter in converters:
        result = converter(data)
        if result is not None:
            converted_json = json.dumps(result, ensure_ascii=False)
            logger.info(f"[QwenAdapter] ✂️ Converted via '{name}' (original: {len(original_content)}, converted: {len(converted_json)})")
            return converted_json
    
    # Step 5: Fallback - patch missing fields and fix action format
    logger.warning(f"[QwenAdapter] ⚠️ No conversion matched, patching fields. Keys: {list(data.keys())}")
    
    # Ensure required string fields
    for field in ['evaluation_previous_goal', 'memory', 'next_goal']:
        if field not in data or data.get(field) is None:
            data[field] = ''
    
    # Sanitize existing action array if present
    if isinstance(data.get('action'), list) and len(data.get('action', [])) > 0:
        data['action'] = _sanitize_action_array(data['action'])
    
    # Fix action field
    if 'action' not in data or not isinstance(data.get('action'), list) or len(data.get('action', [])) == 0:
        # Try to salvage any useful info from the response
        info_text = json.dumps(data, ensure_ascii=False)[:500]
        logger.warning(f"[QwenAdapter] No valid actions found, creating done action from response")
        data['action'] = [{
            'done': {
                'text': f'Model output (non-standard format): {info_text}',
                'success': False
            }
        }]
    
    # Remove extra fields
    allowed_fields = {'evaluation_previous_goal', 'memory', 'next_goal', 'action', 'thinking'}
    for field in list(data.keys()):
        if field not in allowed_fields:
            data.pop(field, None)
    
    content = json.dumps(data, ensure_ascii=False)
    logger.info(f"[QwenAdapter] ✂️ Patched response (original: {len(original_content)}, patched: {len(content)})")
    return content


def wrap_qwen_llm(llm_instance: Any, enable_guided_json: bool = False) -> Any:
    """
    Wrap a browser-use LLM instance with Qwen output cleaning and optional guided JSON.
    
    This wrapper intercepts OpenAI client requests and responses:
    1. Injects guided_json schema into extra_body for vLLM (forces JSON output)
    2. Cleans response content before browser-use processes it
    
    Args:
        llm_instance: BrowserUseChatOpenAI instance
        enable_guided_json: Enable vLLM guided_json for strict JSON output (for RyoAIS/vLLM)
        
    Returns:
        Wrapped LLM instance with output cleaning and guided JSON
    """
    try:
        from functools import wraps
        from browser_use.agent.views import AgentOutput
        
        # Get JSON schema from browser-use's AgentOutput model
        # Simplify schema for vLLM guided decoding (remove $ref and complex anyOf)
        full_schema = AgentOutput.model_json_schema()
        
        # Simplified schema that vLLM can handle better
        AGENT_OUTPUT_SCHEMA = {
            "type": "object",
            "properties": {
                "evaluation_previous_goal": {"type": "string"},
                "memory": {"type": "string"},
                "next_goal": {"type": "string"},
                "action": {
                    "type": "array",
                    "items": {"type": "object"},
                    "minItems": 1
                }
            },
            "required": ["evaluation_previous_goal", "memory", "next_goal", "action"]
        }
        
        # Store original get_client method
        original_get_client = llm_instance.get_client
        
        def wrapped_get_client():
            """Wrapped get_client that adds guided JSON and response cleaning."""
            client = original_get_client()
            original_create = client.chat.completions.create
            
            @wraps(original_create)
            async def create_with_guided_json_and_cleaning(*args, **kwargs):
                """Intercept request to add guided_json, filter messages, then clean response."""
                
                # Step 0: Filter and convert unsupported message roles for RyoAIS
                # RyoAIS's Jinja2 template only supports: system, user, assistant
                # Browser Use may send: action, tool, function, etc.
                if 'messages' in kwargs:
                    original_messages = kwargs['messages']
                    filtered_messages = []
                    
                    for msg in original_messages:
                        # Get message role
                        msg_role = None
                        if isinstance(msg, dict):
                            msg_role = msg.get('role')
                        elif hasattr(msg, 'role'):
                            msg_role = msg.role
                        
                        # Convert unsupported roles to 'user'
                        if msg_role in ['system', 'user', 'assistant']:
                            # Supported role - keep as is
                            filtered_messages.append(msg)
                        else:
                            # Unsupported role (action, tool, function, etc.) - convert to user
                            logger.debug(f"[QwenAdapter] Converting unsupported role '{msg_role}' to 'user'")
                            
                            if isinstance(msg, dict):
                                # Dict message - modify role
                                converted_msg = msg.copy()
                                converted_msg['role'] = 'user'
                                # Wrap content to indicate it's a tool result
                                if msg_role in ['action', 'tool', 'function']:
                                    original_content = converted_msg.get('content', '')
                                    converted_msg['content'] = f"[Tool Result]\n{original_content}"
                                filtered_messages.append(converted_msg)
                            elif hasattr(msg, 'role'):
                                # Object message - create new user message
                                try:
                                    from browser_use.llm.messages import UserMessage
                                    content = msg.content if hasattr(msg, 'content') else str(msg)
                                    # Wrap content to indicate it's a tool result
                                    if msg_role in ['action', 'tool', 'function']:
                                        content = f"[Tool Result]\n{content}"
                                    filtered_messages.append(UserMessage(content=content))
                                except Exception as e:
                                    logger.warning(f"[QwenAdapter] Failed to convert message: {e}")
                                    # Fallback: keep original message
                                    filtered_messages.append(msg)
                            else:
                                # Unknown format - keep original
                                filtered_messages.append(msg)
                    
                    # Replace messages with filtered version
                    if len(filtered_messages) != len(original_messages):
                        logger.info(f"[QwenAdapter] Filtered messages: {len(original_messages)} → {len(filtered_messages)}")
                    
                    # Debug: Log actual messages being sent to RyoAIS
                    logger.debug(f"[QwenAdapter] Sending {len(filtered_messages)} messages to RyoAIS:")
                    for i, msg in enumerate(filtered_messages):
                        if isinstance(msg, dict):
                            role = msg.get('role', 'unknown')
                            content_type = type(msg.get('content', '')).__name__
                            has_tool_calls = 'tool_calls' in msg
                            has_function_call = 'function_call' in msg
                            logger.debug(f"[QwenAdapter]   [{i}] role={role}, content_type={content_type}, tool_calls={has_tool_calls}, function_call={has_function_call}")
                        elif hasattr(msg, 'role'):
                            role = msg.role
                            content_type = type(msg.content).__name__ if hasattr(msg, 'content') else 'unknown'
                            logger.debug(f"[QwenAdapter]   [{i}] role={role}, content_type={content_type}, type={type(msg).__name__}")
                        else:
                            logger.debug(f"[QwenAdapter]   [{i}] unknown message type: {type(msg)}")
                    
                    kwargs['messages'] = filtered_messages
                
                # Step 1: Force JSON output for vLLM/RyoAIS
                if enable_guided_json:
                    # IMPORTANT: Do NOT use response_format with vLLM/RyoAIS
                    # It conflicts with the chat template and causes "Unexpected message role" error
                    # Only use guided_json in extra_body
                    
                    # vLLM guided_json (primary approach for RyoAIS)
                    if 'extra_body' not in kwargs:
                        kwargs['extra_body'] = {}
                    kwargs['extra_body']['guided_json'] = AGENT_OUTPUT_SCHEMA
                    kwargs['extra_body']['guided_decoding_backend'] = 'outlines'
                    
                    logger.info("[QwenAdapter] ✅ Injected guided_json to extra_body (vLLM)")
                    logger.debug(f"[QwenAdapter] Request kwargs: {list(kwargs.keys())}")
                    logger.debug(f"[QwenAdapter] Note: response_format NOT used to avoid chat template conflicts")
                
                # Step 2: Call LLM with guided_json
                response = await original_create(*args, **kwargs)
                
                # Step 3: Clean response content (response interception)
                try:
                    if hasattr(response, 'choices') and response.choices and len(response.choices) > 0:
                        message = response.choices[0].message
                        if hasattr(message, 'content') and message.content:
                            original_content = message.content
                            logger.debug(f"[QwenAdapter] Original output (first 500 chars): {original_content[:500]}")
                            
                            # Apply Qwen-specific cleaning
                            cleaned_content = clean_qwen_response(original_content)
                            
                            if original_content != cleaned_content:
                                logger.info("[QwenAdapter] ✅ Cleaned and adapted output")
                                logger.debug(f"[QwenAdapter] Cleaned output (first 500 chars): {cleaned_content[:500]}")
                                message.content = cleaned_content
                            else:
                                logger.debug("[QwenAdapter] No cleaning needed")
                except Exception as e:
                    logger.error(f"[QwenAdapter] ❌ Failed to clean response: {e}", exc_info=True)
                
                return response
            
            client.chat.completions.create = create_with_guided_json_and_cleaning
            return client
        
        # Replace get_client method
        llm_instance.get_client = wrapped_get_client
        
        if enable_guided_json:
            logger.info("[QwenAdapter] ✅ Qwen adapter with vLLM guided_json applied successfully")
        else:
            logger.info("[QwenAdapter] ✅ Qwen output adapter applied successfully")
        return llm_instance
        
    except Exception as e:
        logger.error(f"[QwenAdapter] ❌ Failed to wrap LLM: {e}", exc_info=True)
        return llm_instance
