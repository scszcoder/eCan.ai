"""
Qwen/Ollama Output Format Adapter for browser-use

This adapter fixes common output issues from Qwen and Ollama models:
1. Removes <think> tags and other XML-style reasoning tags
2. Fixes numeric JSON keys (e.g., 46: -> "46":)
3. Removes markdown code blocks (```json, ```)
4. Cleans up extra whitespace

Similar to deepseek_adapter.py but specifically for Qwen/Ollama models.
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
    Clean and fix Qwen/Ollama model response.
    
    Args:
        content: Raw response content from LLM
        
    Returns:
        Cleaned content with fixes applied
    """
    if not content:
        return content
    
    original_content = content
    
    # 1. Remove <think>...</think> blocks first (before JSON parsing)
    content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL | re.IGNORECASE)
    
    # 2. Remove other common XML-style tags that might interfere with JSON parsing
    content = re.sub(r'<step>.*?</step>', '', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'<reasoning>.*?</reasoning>', '', content, flags=re.DOTALL | re.IGNORECASE)
    
    # 3. Remove markdown code blocks if present
    if '```json' in content or '```' in content:
        content = re.sub(r'```json\s*', '', content)
        content = re.sub(r'```\s*', '', content)
    
    # 3.5. Fix bullet points replacing quotes (Qwen sometimes outputs • instead of ")
    # Pattern: • key" → "key"
    content = re.sub(r'•\s*([a-zA-Z_][a-zA-Z0-9_]*)"', r'"\1"', content)
    
    # 4. Fix numeric JSON keys BEFORE trying to parse JSON
    # This is critical: must fix numeric keys before convert_reasoning_to_browser_action
    # This fixes the "key must be a string" error
    try:
        content_before_fix = content
        
        # Debug: Check for numeric keys before fixing
        pattern1 = r'([{\[,\n]\s*)(\d+)(\s*):'
        matches1 = re.findall(pattern1, content)
        if matches1:
            logger.info(f"[QwenAdapter] 🔍 Found {len(matches1)} numeric keys (pattern 1): {matches1[:3]}")
        
        # First pass: Fix numeric keys that appear after common JSON delimiters
        # Handles: {123:, [123:, ,123:, \n  123:
        content = re.sub(pattern1, r'\1"\2"\3:', content)
        
        # Second pass: Fix numeric keys at the start of the string or after whitespace
        # This catches cases where the JSON starts with a number key
        # Use negative lookbehind to avoid matching already quoted numbers
        pattern2 = r'(?<!")(\b\d+)(\s*):'
        matches2 = re.findall(pattern2, content)
        if matches2:
            logger.info(f"[QwenAdapter] 🔍 Found {len(matches2)} numeric keys (pattern 2): {matches2[:3]}")
        content = re.sub(pattern2, r'"\1"\2:', content)
        
        # Third pass: Clean up any double-quoted numbers (in case we over-quoted)
        content = re.sub(r'""\s*(\d+)\s*""', r'"\1"', content)
        
        if content != content_before_fix:
            logger.info(f"[QwenAdapter] ✅ Fixed numeric JSON keys")
            logger.debug(f"[QwenAdapter] Before (first 10k):\n{content_before_fix[:10000]}")
            logger.debug(f"[QwenAdapter] After (first 10k):\n{content[:10000]}")
        else:
            logger.warning(f"[QwenAdapter] ⚠️ No numeric keys detected by regex")
            # Log full content (up to 10k) to debug why regex didn't match
            logger.warning(f"[QwenAdapter] Content length: {len(content)} chars")
            logger.warning(f"[QwenAdapter] Full content (first 10k chars):\n{content[:10000]}")
    except Exception as e:
        logger.warning(f"[QwenAdapter] Failed to fix numeric keys: {e}")
    
    # 5. Try to convert reasoning model output (after fixing numeric keys)
    converted_content = convert_reasoning_to_browser_action(content)
    if converted_content != content:
        # Already converted, return
        logger.info(f"[QwenAdapter] ✅ Applied reasoning model conversion")
        return converted_content
    
    # 6. Clean up extra whitespace
    content = content.strip()
    
    # Log if modifications were made
    if content != original_content:
        logger.info(f"[QwenAdapter] ✂️ Cleaned response (original: {len(original_content)}, cleaned: {len(content)})")
        logger.debug(f"[QwenAdapter] Removed: {len(original_content) - len(content)} characters")
    
    return content


def wrap_qwen_llm(llm_instance: Any) -> Any:
    """
    Wrap a browser-use LLM instance with Qwen output cleaning.
    
    This function wraps the LLM's get_client method to clean response content
    (remove <think> tags, fix numeric keys, etc.)
    
    Note: Vision filtering for judge requests is now handled by LoggingBrowserUseChatOpenAI
    via the disable_vision_for_judge parameter.
    
    Args:
        llm_instance: BrowserUseChatOpenAI instance
        
    Returns:
        Wrapped LLM instance with response cleaning
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
                
                # Clean response content
                try:
                    if hasattr(response, 'choices') and response.choices and len(response.choices) > 0:
                        message = response.choices[0].message
                        if hasattr(message, 'content') and message.content:
                            # Apply Qwen-specific cleaning
                            cleaned_content = clean_qwen_response(message.content)
                            message.content = cleaned_content
                            
                            logger.debug(f"[QwenAdapter] Response preview: {cleaned_content[:200]}...")
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
