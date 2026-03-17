"""
Universal LLM Output Cleaner

Generic cleaning utilities for LLM outputs that apply to ALL providers
(DeepSeek, Qwen, Ollama, RyoAIS, etc.), regardless of whether the call
is for browser-use or normal LLM usage.

Handles:
1. Remove markdown code blocks (```json ... ```)
2. Remove <think>...</think> tags (reasoning model artifacts)
3. Strip whitespace
4. Extract JSON from mixed text+JSON output

Browser-use specific cleaning (AgentOutput format conversion) is handled
separately in browser_use_extension/qwen_adapter.py and deepseek_adapter.py.
"""

import re
from typing import Optional

from utils.logger_helper import logger_helper as logger


def clean_markdown_code_blocks(content: str) -> str:
    """
    Remove markdown code block wrappers from LLM output.
    
    Handles:
      ```json\n{...}\n```
      ```\n{...}\n```
      ```python\n...\n```
    
    Args:
        content: Raw LLM output string
        
    Returns:
        Content with markdown code blocks removed
    """
    if not content:
        return content
    
    if '```' not in content:
        return content
    
    # Remove ```json or ```<language> opening tags
    cleaned = re.sub(r'```(?:json|python|javascript|typescript|html|css|xml|yaml|toml|text)?\s*\n?', '', content)
    # Remove closing ```
    cleaned = re.sub(r'\n?\s*```', '', cleaned)
    
    if cleaned != content:
        logger.debug(f"[OutputCleaner] Removed markdown code blocks (original: {len(content)}, cleaned: {len(cleaned)})")
    
    return cleaned


def clean_think_tags(content: str) -> str:
    """
    Remove <think>...</think> tags from reasoning model output.
    
    Some models (QwQ, DeepSeek-R1, etc.) wrap their reasoning in <think> tags.
    The actual response content is outside these tags.
    
    Args:
        content: Raw LLM output string
        
    Returns:
        Content with think tags and their contents removed
    """
    if not content:
        return content
    
    if '<think>' not in content and '</think>' not in content:
        return content
    
    # Remove <think>...</think> blocks (including multiline)
    cleaned = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
    cleaned = cleaned.strip()
    
    if cleaned != content:
        logger.debug(f"[OutputCleaner] Removed <think> tags (original: {len(content)}, cleaned: {len(cleaned)})")
    
    return cleaned


def extract_json_from_text(content: str) -> Optional[str]:
    """
    Extract JSON object or array from mixed text+JSON output.
    
    Some models output explanatory text before/after the JSON.
    This function tries to find and extract the JSON portion.
    
    Args:
        content: Raw LLM output that may contain JSON mixed with text
        
    Returns:
        Extracted JSON string, or None if no valid JSON found
    """
    if not content:
        return None
    
    import json
    
    # First, try parsing the whole content as JSON
    stripped = content.strip()
    try:
        json.loads(stripped)
        return stripped  # Already valid JSON
    except json.JSONDecodeError as e:
        # If error is "trailing characters", try to extract just the valid JSON part
        if "trailing characters" in str(e).lower() or "extra data" in str(e).lower():
            # Find where the valid JSON ends by parsing incrementally
            for i in range(len(stripped), 0, -1):
                try:
                    candidate = stripped[:i].rstrip()
                    json.loads(candidate)
                    logger.debug(f"[OutputCleaner] Stripped trailing characters (original: {len(stripped)}, valid: {len(candidate)})")
                    return candidate
                except json.JSONDecodeError:
                    continue
    
    # Try to find JSON object {...}
    # Find the first { and last }
    first_brace = stripped.find('{')
    last_brace = stripped.rfind('}')
    
    if first_brace != -1 and last_brace > first_brace:
        candidate = stripped[first_brace:last_brace + 1]
        try:
            json.loads(candidate)
            logger.debug(f"[OutputCleaner] Extracted JSON object from text (pos {first_brace}-{last_brace})")
            return candidate
        except json.JSONDecodeError:
            pass
    
    # Try to find JSON array [...]
    first_bracket = stripped.find('[')
    last_bracket = stripped.rfind(']')
    
    if first_bracket != -1 and last_bracket > first_bracket:
        candidate = stripped[first_bracket:last_bracket + 1]
        try:
            json.loads(candidate)
            logger.debug(f"[OutputCleaner] Extracted JSON array from text (pos {first_bracket}-{last_bracket})")
            return candidate
        except json.JSONDecodeError:
            pass
    
    return None


def clean_llm_output(content: str) -> str:
    """
    Apply all generic LLM output cleaning steps.
    
    This is the main entry point for universal output cleaning.
    Safe to use for any LLM provider and any call type (browser-use or normal).
    
    Cleaning steps (in order):
    1. Remove <think>...</think> tags
    2. Remove markdown code blocks
    3. Strip whitespace
    4. If result is not valid JSON, try to extract JSON from mixed text
    
    Args:
        content: Raw LLM output string
        
    Returns:
        Cleaned output string
    """
    if not content:
        return content
    
    original = content
    
    # Step 1: Remove think tags
    content = clean_think_tags(content)
    
    # Step 2: Remove markdown code blocks
    content = clean_markdown_code_blocks(content)
    
    # Step 3: Strip whitespace
    content = content.strip()
    
    # Step 4: If not valid JSON, try to extract JSON from mixed text
    if content:
        import json
        try:
            json.loads(content)
        except json.JSONDecodeError:
            extracted = extract_json_from_text(content)
            if extracted:
                content = extracted
    
    if content != original:
        logger.debug(f"[OutputCleaner] Cleaned LLM output (original: {len(original)}, cleaned: {len(content)})")
    
    return content
