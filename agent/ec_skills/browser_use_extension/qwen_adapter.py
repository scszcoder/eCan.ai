"""
Qwen/Ollama Output Format Adapter for browser-use

Standard approach: Use browser-use's compatibility flags:
- add_schema_to_system_prompt=True
- dont_force_structured_output=True
- remove_min_items_from_schema=True
- remove_defaults_from_schema=True

This adapter ONLY handles model-specific quirks:
1. Remove markdown code blocks (```json)
2. Convert reasoning model output format (QwQ, etc.)

Note: <think> tags should be controlled via prompt, not cleaned here.
Browser-use has a 'thinking' field that can be used directly.

All structural validation is handled by browser-use's Pydantic validation.
"""

import re
from typing import Any

from utils.logger_helper import logger_helper as logger


def convert_reasoning_to_browser_action(content: str) -> str:
    """
    Convert Qwen reasoning model output to browser-use AgentOutput format.
    
    Qwen reasoning models return:
    {
        "success": true,
        "results": [...]
    }
    
    browser-use expects:
    {
        "evaluation_previous_goal": "...",
        "memory": "...",
        "next_goal": "...",
        "action": [{"done": {"text": "..."}}]
    }
    
    Args:
        content: Raw response from Qwen reasoning model
        
    Returns:
        Converted content in browser-use format
    """
    try:
        import json
        
        # Try to parse as JSON
        data = json.loads(content)
        
        # Check if it's a reasoning model response (has 'success' or 'results')
        if 'success' in data or 'results' in data:
            logger.info("[QwenAdapter] 🔄 Detected reasoning model output, converting to browser-use format")
            
            # Extract results/content
            results = data.get('results', [])
            success = data.get('success', True)
            
            # Build summary text
            if results:
                if isinstance(results, list):
                    summary = '\n'.join([str(r.get('title', r)) if isinstance(r, dict) else str(r) for r in results[:5]])
                else:
                    summary = str(results)
            else:
                summary = "Task completed" if success else "Task failed"
            
            # Convert to browser-use format
            converted = {
                "evaluation_previous_goal": "Completed reasoning task",
                "memory": f"Reasoning results: {summary[:200]}",
                "next_goal": "Return results to user",
                "action": [
                    {
                        "done": {
                            "text": summary[:500]  # Limit length
                        }
                    }
                ]
            }
            
            converted_json = json.dumps(converted, ensure_ascii=False)
            logger.info(f"[QwenAdapter] ✅ Converted reasoning output to browser-use format")
            logger.debug(f"[QwenAdapter] Converted: {converted_json[:200]}...")
            return converted_json
            
    except json.JSONDecodeError:
        logger.debug("[QwenAdapter] Not a JSON response, applying standard cleaning")
    except Exception as e:
        logger.warning(f"[QwenAdapter] Failed to convert reasoning output: {e}")
    
    # If not a reasoning model response, return as-is
    return content


def clean_qwen_response(content: str) -> str:
    """
    Clean and adapt Qwen/Ollama model response.
    
    Handles:
    1. Remove markdown code blocks (```json)
    2. Convert reasoning model format (QwQ)
    3. Ensure required fields exist (browser-use schema)
    
    Args:
        content: Raw response content from LLM
        
    Returns:
        Cleaned and adapted content
    """
    if not content:
        return content
    
    original_content = content
    
    # 1. Remove markdown code blocks
    if '```json' in content or '```' in content:
        content = re.sub(r'```json\s*', '', content)
        content = re.sub(r'```\s*', '', content)
    
    # 2. Try to convert reasoning model output (QwQ, etc.)
    converted_content = convert_reasoning_to_browser_action(content)
    if converted_content != content:
        logger.info(f"[QwenAdapter] ✅ Applied reasoning model conversion")
        return converted_content
    
    # 3. Clean up whitespace
    content = content.strip()
    
    # 4. Ensure required fields exist (browser-use AgentOutput schema)
    try:
        import json
        data = json.loads(content)
        
        if isinstance(data, dict):
            # Ensure required fields exist
            if 'evaluation_previous_goal' not in data or data.get('evaluation_previous_goal') is None:
                data['evaluation_previous_goal'] = ''
            if 'memory' not in data or data.get('memory') is None:
                data['memory'] = ''
            if 'next_goal' not in data or data.get('next_goal') is None:
                data['next_goal'] = ''
            
            # Ensure action exists and is not empty (browser-use requires min_items=1)
            if 'action' not in data or not isinstance(data.get('action'), list) or len(data.get('action', [])) == 0:
                logger.warning("[QwenAdapter] No valid actions found, creating done action")
                data['action'] = [{
                    'done': {
                        'text': 'Task completed',
                        'success': True
                    }
                }]
            
            content = json.dumps(data, ensure_ascii=False)
    except json.JSONDecodeError:
        pass  # Not JSON, skip field validation
    except Exception as e:
        logger.warning(f"[QwenAdapter] Failed to validate fields: {e}")
    
    # Log if modifications were made
    if content != original_content:
        logger.info(f"[QwenAdapter] ✂️ Cleaned response (original: {len(original_content)}, cleaned: {len(content)})")
    
    return content


def wrap_qwen_llm(llm_instance: Any) -> Any:
    """
    Wrap a browser-use LLM instance with Qwen output cleaning.
    
    This wrapper intercepts OpenAI client responses at the lowest level,
    before browser-use calls model_validate_json().
    
    Args:
        llm_instance: BrowserUseChatOpenAI instance
        
    Returns:
        Wrapped LLM instance with output cleaning
    """
    try:
        from functools import wraps
        
        # Store original get_client method
        original_get_client = llm_instance.get_client
        
        def wrapped_get_client():
            """Wrapped get_client that adds response cleaning."""
            client = original_get_client()
            original_create = client.chat.completions.create
            
            @wraps(original_create)
            async def create_with_cleaning(*args, **kwargs):
                """Intercept response and apply Qwen cleaning."""
                response = await original_create(*args, **kwargs)
                
                # Clean response content before browser-use processes it
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
            
            client.chat.completions.create = create_with_cleaning
            return client
        
        # Replace get_client method
        llm_instance.get_client = wrapped_get_client
        
        logger.info("[QwenAdapter] ✅ Qwen output adapter applied successfully")
        return llm_instance
        
    except Exception as e:
        logger.error(f"[QwenAdapter] ❌ Failed to wrap LLM: {e}", exc_info=True)
        return llm_instance
