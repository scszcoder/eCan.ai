"""
Unified token estimation utilities for browser_use agents.

This module provides consistent token estimation across different components
to avoid confusion and ensure accurate token budget calculations.
"""

import re
from typing import Union


# Token estimation constants based on empirical testing
# Reference: OpenAI tokenizer behavior for different content types
CHARS_PER_TOKEN_ENGLISH = 4.0      # Pure English text
CHARS_PER_TOKEN_CJK = 1.6          # Pure Chinese/Japanese/Korean
CHARS_PER_TOKEN_MIXED = 2.5        # Mixed English + CJK (typical web content)
CHARS_PER_TOKEN_CODE = 3.0         # Code with symbols and formatting

# Multimodal accounting constants
# --------------------------------
# OpenAI / Anthropic-style vision models bill image content as a fixed-ish
# number of tokens that's essentially INDEPENDENT of the base64 payload size.
# For OpenAI: "low" detail = 85 tokens; "high" detail = 85 + 170*N_tiles.
# We use ~255 as a safe single-tile "auto" default — generous enough to
# never under-budget, tiny compared to the millions of tokens a raw base64
# blob would otherwise be counted as.
IMAGE_PART_TOKEN_COST = 255        # Fixed cost per image_url content part

# Regex that matches a full ``data:image/...;base64,<payload>`` URI (greedy on
# the base64 tail until the next non-base64 char).  Used to strip these blobs
# from string-form message content before token counting, so a caller that
# forgot to upgrade to multimodal doesn't blow the context budget.
_DATA_URI_IMAGE_RE = re.compile(r'data:image/[A-Za-z0-9.+-]+;base64,[A-Za-z0-9+/=]+')


def detect_content_type(text: str) -> str:
    """
    Automatically detect content type based on character distribution.
    
    Analyzes the text to determine if it's primarily CJK (Chinese/Japanese/Korean),
    English, or mixed content. This enables more accurate token estimation.
    
    Args:
        text: Text to analyze
        
    Returns:
        Content type: 'cjk', 'english', 'mixed', or 'code'
        
    Examples:
        >>> detect_content_type("Hello world")
        'english'
        
        >>> detect_content_type("你好世界")
        'cjk'
        
        >>> detect_content_type("Hello 世界")
        'mixed'
        
        >>> detect_content_type("function foo() { return 42; }")
        'code'
    """
    if not text:
        return 'mixed'
        
    if len(text) < 10:
        # For very short text, count CJK vs English characters directly
        cjk_cnt = len(re.findall(r'[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]', text))
        eng_cnt = len(re.findall(r'[a-zA-Z]', text))
        
        # If no relevant chars, default to mixed
        if cjk_cnt == 0 and eng_cnt == 0:
            return 'mixed'
            
        ratio = float(cjk_cnt) / float(cjk_cnt + eng_cnt)
        if ratio > 0.7:
            return 'cjk'
        elif ratio < 0.3:
            return 'english'
        return 'mixed'
    
    # Sample text for efficiency (analyze first 2000 chars)
    sample = text[:2000] if len(text) > 2000 else text
    
    # Count different character types
    cjk_count = len(re.findall(r'[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]', sample))
    ascii_alpha_count = len(re.findall(r'[a-zA-Z]', sample))
    code_symbols = len(re.findall(r'[{}();=<>[\]{}]', sample))
    
    total_chars = len(sample)
    
    # Detect code (high density of code symbols)
    if code_symbols / total_chars > 0.15:
        return 'code'
    
    # Calculate language ratios
    relevant_chars = cjk_count + ascii_alpha_count
    if relevant_chars == 0:
        return 'mixed'
    
    cjk_ratio = cjk_count / relevant_chars
    
    # Classify based on CJK ratio
    if cjk_ratio > 0.7:
        return 'cjk'
    elif cjk_ratio < 0.3:
        return 'english'
    else:
        return 'mixed'


def estimate_tokens(
    text: str,
    content_type: str = 'mixed'
) -> int:
    """
    Estimate token count for text content.
    
    This provides a conservative estimate based on content type.
    For accurate counting, use tiktoken library, but this is faster
    and sufficient for budget planning.
    
    Args:
        text: Text content to estimate
        content_type: Type of content ('english', 'cjk', 'mixed', 'code')
        
    Returns:
        Estimated token count
        
    Examples:
        >>> estimate_tokens("Hello world", content_type='english')
        3  # ~11 chars / 4 = 2.75 → 3
        
        >>> estimate_tokens("你好世界", content_type='cjk')
        3  # ~4 chars / 1.6 = 2.5 → 3
        
        >>> estimate_tokens("Hello 世界", content_type='mixed')
        3  # ~7 chars / 2.5 = 2.8 → 3
    """
    if not text:
        return 0
    
    char_count = len(text)
    
    # Select appropriate ratio based on content type
    if content_type == 'english':
        chars_per_token = CHARS_PER_TOKEN_ENGLISH
    elif content_type == 'cjk':
        chars_per_token = CHARS_PER_TOKEN_CJK
    elif content_type == 'code':
        chars_per_token = CHARS_PER_TOKEN_CODE
    else:  # 'mixed' or default
        chars_per_token = CHARS_PER_TOKEN_MIXED
    
    # Conservative estimate: round up
    estimated = int(char_count / chars_per_token + 0.5)
    return max(1, estimated)


def chars_to_tokens(
    char_count: int,
    content_type: str = 'mixed'
) -> int:
    """
    Convert character count to estimated token count.
    
    Args:
        char_count: Number of characters
        content_type: Type of content ('english', 'cjk', 'mixed', 'code')
        
    Returns:
        Estimated token count
    """
    if char_count <= 0:
        return 0
    
    if content_type == 'english':
        chars_per_token = CHARS_PER_TOKEN_ENGLISH
    elif content_type == 'cjk':
        chars_per_token = CHARS_PER_TOKEN_CJK
    elif content_type == 'code':
        chars_per_token = CHARS_PER_TOKEN_CODE
    else:
        chars_per_token = CHARS_PER_TOKEN_MIXED
    
    return int(char_count / chars_per_token + 0.5)


def tokens_to_chars(
    token_count: int,
    content_type: str = 'mixed'
) -> int:
    """
    Convert token count to estimated character count.
    
    Useful for calculating MAX_CHAR_LIMIT from available tokens.
    
    Args:
        token_count: Number of tokens
        content_type: Type of content ('english', 'cjk', 'mixed', 'code')
        
    Returns:
        Estimated character count
        
    Examples:
        >>> tokens_to_chars(1000, content_type='mixed')
        2500  # 1000 tokens * 2.5 chars/token
        
        >>> tokens_to_chars(1000, content_type='cjk')
        1600  # 1000 tokens * 1.6 chars/token (more conservative for CJK)
    """
    if token_count <= 0:
        return 0
    
    if content_type == 'english':
        chars_per_token = CHARS_PER_TOKEN_ENGLISH
    elif content_type == 'cjk':
        chars_per_token = CHARS_PER_TOKEN_CJK
    elif content_type == 'code':
        chars_per_token = CHARS_PER_TOKEN_CODE
    else:
        chars_per_token = CHARS_PER_TOKEN_MIXED
    
    return int(token_count * chars_per_token)


def estimate_tokens_auto(text: str) -> int:
    """
    Automatically detect content type and estimate tokens.
    
    This is the most accurate estimation function as it analyzes
    the text to determine its type (CJK, English, mixed, code) and
    uses the appropriate chars_per_token ratio.
    
    Args:
        text: Text to estimate tokens for
        
    Returns:
        Estimated token count
        
    Examples:
        >>> estimate_tokens_auto("Hello world")
        3  # English: ~11 chars / 4.0 = 2.75 → 3
        
        >>> estimate_tokens_auto("你好世界测试内容")
        5  # CJK: ~7 chars / 1.6 = 4.4 → 5
    """
    if not text:
        return 0
    
    content_type = detect_content_type(text)
    return estimate_tokens(text, content_type=content_type)


def estimate_message_tokens(message: Union[str, object]) -> int:
    """
    Estimate tokens for a LangChain message object or string.

    Multimodal-aware: image content (either as ``image_url`` content-parts in
    a list, or as ``data:image/...;base64,...`` blobs embedded inside a raw
    string) is billed as a small fixed cost (``IMAGE_PART_TOKEN_COST``), NOT
    as the length of the base64 payload.  This prevents a 6 MB inlined image
    from detonating the context-window filter in ``get_recent_context``.

    Content shapes handled:

    - **str**: strip any ``data:image/...;base64,...`` blobs, count each
      as ``IMAGE_PART_TOKEN_COST``, then count the remaining text normally.
    - **list** (OpenAI/Anthropic multimodal format, e.g.
      ``[{"type":"text","text":"..."}, {"type":"image_url","image_url":{"url":"..."}}]``):
      count each ``text`` part's ``text`` field via auto-detect, and add
      ``IMAGE_PART_TOKEN_COST`` per ``image_url`` / ``image`` part.
    - anything else: fall back to ``str(content)`` → auto-detect.

    Args:
        message: LangChain message object or string

    Returns:
        Estimated token count
    """
    try:
        if isinstance(message, str):
            content = message
        elif hasattr(message, 'content'):
            content = message.content
        else:
            content = str(message)

        # Multimodal content list: count text parts + flat cost per image.
        if isinstance(content, list):
            total = 0
            for part in content:
                if isinstance(part, dict):
                    ptype = part.get('type')
                    if ptype in ('image_url', 'image'):
                        total += IMAGE_PART_TOKEN_COST
                    elif ptype == 'text':
                        text_val = part.get('text') or ''
                        if isinstance(text_val, str) and text_val:
                            total += estimate_tokens_auto(text_val)
                    else:
                        # Unknown part type — fall back to its str length,
                        # but cap to avoid runaway for oddly-shaped parts.
                        total += estimate_tokens_auto(str(part)[:4000])
                elif isinstance(part, str):
                    total += estimate_tokens_auto(part)
                # Silently skip anything else (None, numbers, etc.)
            return total

        # String content: strip any inlined image data URIs before counting so
        # a legacy caller (one that didn't upgrade to multimodal parts) still
        # gets a sane token estimate.
        if isinstance(content, str):
            # Fast path: no data URI → count directly.
            if 'data:image/' not in content:
                return estimate_tokens_auto(content)
            # Count each stripped data URI as one image, then count the
            # remaining text normally.
            n_images = 0

            def _sub(_m):
                nonlocal n_images
                n_images += 1
                return ''  # remove the blob from the text used for counting

            stripped = _DATA_URI_IMAGE_RE.sub(_sub, content)
            return estimate_tokens_auto(stripped) + (n_images * IMAGE_PART_TOKEN_COST)

        # Dict or other exotic content: coerce to str.
        return estimate_tokens_auto(str(content))
    except Exception:
        return 0
