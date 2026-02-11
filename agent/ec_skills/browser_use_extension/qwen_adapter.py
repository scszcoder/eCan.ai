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
        
        # Map common simplified action names to browser-use action names
        action_map = {
            'navigate': 'go_to_url',
            'goto': 'go_to_url',
            'go_to': 'go_to_url',
            'open': 'go_to_url',
            'go_to_url': 'go_to_url',
            'click': 'click_element',
            'click_element': 'click_element',
            'input': 'input_text',
            'input_text': 'input_text',
            'type': 'input_text',
            'scroll': 'scroll_down',
            'scroll_down': 'scroll_down',
            'scroll_up': 'scroll_up',
            'done': 'done',
            'finish': 'done',
            'complete': 'done',
            'wait': 'wait',
            'extract': 'extract_content',
            'extract_content': 'extract_content',
            'screenshot': 'screenshot',
        }
        
        bu_action_name = action_map.get(action_name, action_name)
        
        # Build action params based on action type
        if bu_action_name == 'go_to_url':
            url = params.get('url', params.get('href', params.get('link', '')))
            action_obj = {bu_action_name: {'url': url}}
        elif bu_action_name in ('click_element',):
            index = params.get('index', params.get('element', params.get('xpath', 0)))
            action_obj = {bu_action_name: {'index': int(index) if str(index).isdigit() else 0}}
        elif bu_action_name == 'input_text':
            index = params.get('index', params.get('element', 0))
            text = params.get('text', params.get('value', ''))
            action_obj = {bu_action_name: {'index': int(index) if str(index).isdigit() else 0, 'text': str(text)}}
        elif bu_action_name == 'done':
            text = params.get('text', params.get('message', params.get('result', 'Task completed')))
            success = params.get('success', True)
            action_obj = {bu_action_name: {'text': str(text), 'success': bool(success)}}
        elif bu_action_name in ('scroll_down', 'scroll_up', 'wait', 'screenshot'):
            action_obj = {bu_action_name: params or {}}
        else:
            # Unknown action - wrap as-is
            action_obj = {bu_action_name: params}
        
        logger.info(f"[QwenAdapter] 🔄 Converted flat action '{action_name}' → '{bu_action_name}'")
        return _make_agent_output(
            [action_obj],
            eval_text=data.get('evaluation_previous_goal', ''),
            memory_text=data.get('memory', ''),
            goal_text=data.get('next_goal', '')
        )
    
    # Pattern 2: {"go_to_url": {"url": "..."}} or {"navigate": {"url": "..."}}
    # (action dict at top level, no wrapping)
    known_actions = {
        'go_to_url', 'click_element', 'input_text', 'done', 'scroll_down', 'scroll_up',
        'wait', 'screenshot', 'extract_content', 'navigate', 'click', 'open_tab',
        'switch_tab', 'close_tab', 'go_back', 'search_google',
    }
    top_level_actions = set(data.keys()) & known_actions
    if top_level_actions and 'action' not in data:
        action_name = list(top_level_actions)[0]
        action_params = data[action_name]
        if not isinstance(action_params, dict):
            action_params = {}
        action_obj = {action_name: action_params}
        logger.info(f"[QwenAdapter] 🔄 Converted top-level action '{action_name}' to action array")
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
        # Already valid - just clean extra fields
        allowed_fields = {'evaluation_previous_goal', 'memory', 'next_goal', 'action', 'thinking'}
        extra_fields = set(data.keys()) - allowed_fields
        if extra_fields:
            logger.debug(f"[QwenAdapter] Removing extra fields: {extra_fields}")
            for field in extra_fields:
                data.pop(field, None)
            content = json.dumps(data, ensure_ascii=False)
        if content != original_content:
            logger.info(f"[QwenAdapter] ✂️ Cleaned valid response (removed extra fields)")
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
                """Intercept request to add guided_json, then clean response."""
                
                # Step 1: Force JSON output for vLLM/RyoAIS
                if enable_guided_json:
                    # Try multiple approaches to force JSON output
                    
                    # Approach 1: OpenAI standard response_format (may work with newer vLLM)
                    try:
                        kwargs['response_format'] = {"type": "json_object"}
                        logger.info("[QwenAdapter] ✅ Set response_format=json_object (OpenAI standard)")
                    except Exception as e:
                        logger.debug(f"[QwenAdapter] response_format not supported: {e}")
                    
                    # Approach 2: vLLM guided_json (if supported)
                    if 'extra_body' not in kwargs:
                        kwargs['extra_body'] = {}
                    kwargs['extra_body']['guided_json'] = AGENT_OUTPUT_SCHEMA
                    kwargs['extra_body']['guided_decoding_backend'] = 'outlines'
                    
                    logger.info("[QwenAdapter] ✅ Injected guided_json to extra_body (vLLM fallback)")
                    logger.debug(f"[QwenAdapter] Request kwargs: {list(kwargs.keys())}")
                
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
