"""
Unified configuration for browser_use agents (both local and cloud modes).

This module provides centralized configuration for MessageCompaction and other
agent settings to ensure consistency across different agent types and make
optimization easier.
"""

from browser_use.agent.views import MessageCompactionSettings
from typing import Optional, Any, List
import logging
import re

logger = logging.getLogger(__name__)


# ============================================================================
# Configuration Constants
# ============================================================================

class TokenEstimationConfig:
    """
    Token estimation constants based on empirical data from e-commerce sites.
    
    These values are derived from analyzing real-world e-commerce pages:
    - Amazon (English): ~4.0 chars/token
    - Taobao/JD (Chinese): ~2.5 chars/token
    - Mixed content: ~3.0-3.5 chars/token
    """
    # CJK ratio thresholds
    CJK_HEAVY_THRESHOLD = 0.5      # >50% CJK characters
    MIXED_THRESHOLD = 0.2          # 20-50% CJK characters
    
    # Chars per token ratios (measured from real data)
    CJK_CHARS_PER_TOKEN = 2.5      # Measured from Taobao/JD pages
    MIXED_CHARS_PER_TOKEN = 3.0    # Measured from mixed content pages
    ENGLISH_CHARS_PER_TOKEN = 4.0  # OpenAI standard for English
    DEFAULT_CHARS_PER_TOKEN = 3.5  # Balanced for e-commerce (Chinese + English)
    
    # Performance optimization
    SAMPLE_SIZE = 1000             # Sample size for fast estimation


class CompressionConfig:
    """
    MessageCompaction configuration for different context sizes.
    
    These settings are optimized for e-commerce scenarios where:
    - Single step DOM: 5-8K tokens
    - Typical task: 3-12 steps
    - Need to balance history retention and token usage
    """
    # Context size thresholds
    LARGE_CONTEXT_THRESHOLD = 128000   # 128K+ models
    MEDIUM_CONTEXT_THRESHOLD = 100000  # 100K models
    STANDARD_CONTEXT_THRESHOLD = 65536 # 65K models
    MIN_CONTEXT_LENGTH = 8192          # Minimum reasonable context
    
    # Large context settings (128K+)
    LARGE_TRIGGER_TOKENS = 60000
    LARGE_COMPACT_EVERY = 4
    LARGE_KEEP_ITEMS = 4
    LARGE_SUMMARY_CHARS = 5000
    
    # Medium context settings (100K)
    MEDIUM_TRIGGER_TOKENS = 50000
    MEDIUM_COMPACT_EVERY = 3
    MEDIUM_KEEP_ITEMS = 3
    MEDIUM_SUMMARY_CHARS = 4000
    
    # Standard context settings (65K)
    STANDARD_TRIGGER_TOKENS = 35000
    STANDARD_COMPACT_EVERY = 3
    STANDARD_KEEP_ITEMS = 3
    STANDARD_SUMMARY_CHARS = 3500
    
    # Validation thresholds
    MAX_TRIGGER_RATIO = 0.8        # Trigger should be <80% of context
    MAX_DOM_RATIO = 0.5            # DOM should be <50% of context


class DOMConfig:
    """
    DOM size limits based on real e-commerce page analysis.
    
    Analysis of major e-commerce sites:
    - Amazon: 12K-18K chars
    - Taobao: 15K-25K chars
    - JD: 14K-22K chars
    - eBay: 10K-16K chars
    """
    # DOM size limits for different context sizes
    LARGE_CONTEXT_DOM_LIMIT = 25000    # 128K+ models
    MEDIUM_CONTEXT_DOM_LIMIT = 22000   # 100K models
    STANDARD_CONTEXT_DOM_LIMIT = 18000 # 65K models
    
    # Default values
    DEFAULT_MAX_CLICKABLE_ELEMENTS = 18000  # Covers 90% of e-commerce pages
    DEFAULT_RESERVED_TOKENS = 35000         # For extraction LLM calculations
    
    # Warning threshold
    LARGE_DOM_WARNING_THRESHOLD = 28000     # Warn if DOM is very large


def _is_cjk_char(c: str) -> bool:
    """
    Check if a character is CJK (Chinese, Japanese, Korean).
    
    Args:
        c: Single character to check
        
    Returns:
        True if character is CJK, False otherwise
    """
    return (
        '\u4e00' <= c <= '\u9fff' or  # CJK Unified Ideographs
        '\u3040' <= c <= '\u309f' or  # Hiragana
        '\u30a0' <= c <= '\u30ff' or  # Katakana
        '\uac00' <= c <= '\ud7af'     # Hangul
    )


def _calculate_cjk_ratio(content: str, sample_size: Optional[int] = None) -> float:
    """
    Calculate CJK character ratio in content.
    
    Performance optimization: Uses sampling for large content (10-100x faster).
    
    Args:
        content: Content to analyze
        sample_size: Number of characters to sample (None = analyze all)
        
    Returns:
        Ratio of CJK characters (0.0 to 1.0)
    """
    if not content:
        return 0.0
    
    # Use sampling for large content to improve performance
    if sample_size and len(content) > sample_size:
        sample = content[:sample_size]
        logger.debug(
            f"[AgentConfig] Sampling first {sample_size} chars "
            f"(out of {len(content)}) for fast estimation"
        )
    else:
        sample = content
    
    if not sample:
        return 0.0
    
    try:
        cjk_count = sum(1 for c in sample if _is_cjk_char(c))
        return cjk_count / len(sample)
    except Exception as e:
        logger.error(f"[AgentConfig] Error calculating CJK ratio: {e}", exc_info=True)
        return 0.0


def estimate_chars_per_token(
    content: Optional[str] = None,
    cjk_ratio: Optional[float] = None,
    use_sampling: bool = True
) -> float:
    """
    Estimate chars_per_token based on content type (CJK vs English).
    
    Different languages have different token densities:
    - Pure English: ~4.0 chars/token
    - Mixed content: ~3.0 chars/token
    - CJK-heavy: ~2.5 chars/token
    
    Performance: Uses sampling for large content (10-100x faster).
    
    Args:
        content: Sample content to analyze (optional)
        cjk_ratio: Pre-calculated CJK ratio (optional, overrides content analysis)
        use_sampling: Whether to use sampling for large content (default: True)
        
    Returns:
        Estimated chars_per_token ratio
        
    Raises:
        No exceptions - returns safe default on any error
    """
    try:
        # If cjk_ratio is provided, use it directly
        if cjk_ratio is not None:
            if cjk_ratio > TokenEstimationConfig.CJK_HEAVY_THRESHOLD:
                return TokenEstimationConfig.CJK_CHARS_PER_TOKEN
            elif cjk_ratio > TokenEstimationConfig.MIXED_THRESHOLD:
                return TokenEstimationConfig.MIXED_CHARS_PER_TOKEN
            else:
                return TokenEstimationConfig.ENGLISH_CHARS_PER_TOKEN
        
        # If content is provided, analyze it
        if content and len(content) > 0:
            # Calculate CJK ratio (with optional sampling)
            sample_size = TokenEstimationConfig.SAMPLE_SIZE if use_sampling else None
            ratio = _calculate_cjk_ratio(content, sample_size)
            
            if ratio > TokenEstimationConfig.CJK_HEAVY_THRESHOLD:
                logger.debug(
                    f"[AgentConfig] Content is CJK-heavy ({ratio:.1%}), "
                    f"using chars_per_token={TokenEstimationConfig.CJK_CHARS_PER_TOKEN}"
                )
                return TokenEstimationConfig.CJK_CHARS_PER_TOKEN
            elif ratio > TokenEstimationConfig.MIXED_THRESHOLD:
                logger.debug(
                    f"[AgentConfig] Content is mixed ({ratio:.1%}), "
                    f"using chars_per_token={TokenEstimationConfig.MIXED_CHARS_PER_TOKEN}"
                )
                return TokenEstimationConfig.MIXED_CHARS_PER_TOKEN
            else:
                logger.debug(
                    f"[AgentConfig] Content is English-heavy ({ratio:.1%}), "
                    f"using chars_per_token={TokenEstimationConfig.ENGLISH_CHARS_PER_TOKEN}"
                )
                return TokenEstimationConfig.ENGLISH_CHARS_PER_TOKEN
        
        # Default: Balanced estimate for mixed e-commerce pages
        logger.debug(
            f"[AgentConfig] No content to analyze, "
            f"using balanced chars_per_token={TokenEstimationConfig.DEFAULT_CHARS_PER_TOKEN}"
        )
        return TokenEstimationConfig.DEFAULT_CHARS_PER_TOKEN
        
    except Exception as e:
        logger.error(
            f"[AgentConfig] Error in estimate_chars_per_token: {e}",
            exc_info=True
        )
        # Safe fallback on any error
        return TokenEstimationConfig.DEFAULT_CHARS_PER_TOKEN


def detect_context_length(llm: Optional[Any]) -> int:
    """
    Detect context_length from LLM instance using multiple strategies.
    
    Tries multiple approaches:
    1. Check common attributes (context_length, max_tokens, model_max_length)
    2. Infer from model name (e.g., 'gpt-4-128k', 'claude-3-opus-200k')
    3. Fall back to safe default (65536)
    
    Args:
        llm: LLM instance to detect context_length from
        
    Returns:
        Detected context_length in tokens
    """
    if llm is None:
        return CompressionConfig.STANDARD_CONTEXT_THRESHOLD
    
    # Strategy 1: Try common attribute names
    for attr in ['context_length', 'max_tokens', 'model_max_length', 'n_ctx']:
        value = getattr(llm, attr, None)
        if value and isinstance(value, int) and value >= 8192:
            logger.info(f"[AgentConfig] ✅ Detected context_length={value} from llm.{attr}")
            return value
    
    # Strategy 2: Infer from model name
    model_name = getattr(llm, 'model_name', '') or getattr(llm, 'model', '') or ''
    if model_name:
        model_lower = model_name.lower()
        
        # Check for explicit size markers
        size_patterns = [
            (r'(\d+)k', 1000),      # e.g., '128k' -> 128000
            (r'(\d+)000', 1),       # e.g., '128000' -> 128000
        ]
        
        for pattern, multiplier in size_patterns:
            match = re.search(pattern, model_lower)
            if match:
                size = int(match.group(1)) * multiplier
                if size >= 8192:
                    logger.info(f"[AgentConfig] ✅ Inferred context_length={size} from model name '{model_name}'")
                    return size
        
        # Known model families
        if 'gpt-4' in model_lower or 'gpt-4o' in model_lower:
            return 128000  # GPT-4 Turbo/4o default
        elif 'claude-3' in model_lower or 'claude-opus' in model_lower:
            return 200000  # Claude 3 default
        elif 'gemini-1.5' in model_lower or 'gemini-2' in model_lower:
            return 1000000  # Gemini 1.5/2.0 default
        elif 'qwen' in model_lower and ('2.5' in model_lower or '3' in model_lower):
            return 128000  # Qwen 2.5/3 default
    
    # Strategy 3: Safe fallback
    logger.warning(
        f"[AgentConfig] ⚠️  Could not detect context_length from LLM "
        f"(model_name='{model_name}'), using safe default {CompressionConfig.STANDARD_CONTEXT_THRESHOLD}"
    )
    return CompressionConfig.STANDARD_CONTEXT_THRESHOLD


def get_compaction_settings_for_context_size(
    context_length: int = CompressionConfig.STANDARD_CONTEXT_THRESHOLD
) -> MessageCompactionSettings:
    """
    Get MessageCompaction settings optimized for the model's context window size.
    
    Standard compression strategy: When each step adds ~20K tokens, we need regular
    compaction regardless of context size to prevent unbounded growth.
    
    Args:
        context_length: Model's context window size in tokens
        
    Returns:
        MessageCompactionSettings optimized for the given context size
    """
    # Use balanced chars_per_token for e-commerce pages
    default_chars_per_token = TokenEstimationConfig.DEFAULT_CHARS_PER_TOKEN
    
    if context_length >= CompressionConfig.LARGE_CONTEXT_THRESHOLD:
        # Large context models (128K+): Balanced compaction
        # E-commerce scenario: ~5-8K tokens/step, allow 8-10 steps history
        settings = MessageCompactionSettings(
            enabled=True,
            compact_every_n_steps=CompressionConfig.LARGE_COMPACT_EVERY,
            trigger_token_count=CompressionConfig.LARGE_TRIGGER_TOKENS,
            keep_last_items=CompressionConfig.LARGE_KEEP_ITEMS,
            summary_max_chars=CompressionConfig.LARGE_SUMMARY_CHARS,
            chars_per_token=default_chars_per_token,
        )
    elif context_length >= CompressionConfig.MEDIUM_CONTEXT_THRESHOLD:
        # Medium-large context (100K-128K): Moderate compaction
        # E-commerce scenario: allow 6-8 steps history
        settings = MessageCompactionSettings(
            enabled=True,
            compact_every_n_steps=CompressionConfig.MEDIUM_COMPACT_EVERY,
            trigger_token_count=CompressionConfig.MEDIUM_TRIGGER_TOKENS,
            keep_last_items=CompressionConfig.MEDIUM_KEEP_ITEMS,
            summary_max_chars=CompressionConfig.MEDIUM_SUMMARY_CHARS,
            chars_per_token=default_chars_per_token,
        )
    else:
        # Standard context (65K): Balanced compaction for e-commerce
        # E-commerce scenario: ~5-8K tokens/step, allow 4-5 steps history
        settings = MessageCompactionSettings(
            enabled=True,
            compact_every_n_steps=CompressionConfig.STANDARD_COMPACT_EVERY,
            trigger_token_count=CompressionConfig.STANDARD_TRIGGER_TOKENS,
            keep_last_items=CompressionConfig.STANDARD_KEEP_ITEMS,
            summary_max_chars=CompressionConfig.STANDARD_SUMMARY_CHARS,
            chars_per_token=default_chars_per_token,
        )

    # Keep behavior consistent with get_ultra_aggressive_compaction_settings():
    # avoid AgentSettings validation conflicts when trigger_char_count is auto-populated.
    settings.trigger_char_count = None
    return settings


def get_ultra_aggressive_compaction_settings() -> MessageCompactionSettings:
    """
    Get ultra-aggressive MessageCompaction settings to prevent token overflow.
    
    Background:
    - Issue: Step 4 reached 91K tokens, exceeding 65K limit
    - Root cause: DOM-heavy pages with CJK content accumulate tokens quickly
    - Solution: Aggressive compaction with low trigger threshold
    
    Configuration rationale:
    - DOM size: 15K chars × 0.8 (CJK ratio) ≈ 12K tokens per step
    - Trigger: 10K tokens (below single step, ensures compaction after step 1)
    - Frequency: Every 2 steps (backup mechanism)
    - History: Keep only 1 recent item (most aggressive)
    - Summary: 2K chars (compact summaries)
    
    Expected token usage:
    - Single step DOM: ~12K tokens
    - History (1 item): ~4K tokens
    - System prompt: ~5K tokens
    - Response: ~4K tokens
    - Safety margin: ~10K tokens
    - Total: ~35K tokens (well below 65K limit)
    
    Returns:
        MessageCompactionSettings configured for ultra-aggressive compaction
    """
    logger.debug("=" * 80)
    logger.debug("[AGENT_CONFIG] Creating MessageCompactionSettings...")
    logger.debug("=" * 80)
    
    # Use balanced chars_per_token for e-commerce pages
    default_chars_per_token = TokenEstimationConfig.DEFAULT_CHARS_PER_TOKEN
    
    settings = MessageCompactionSettings(
        enabled=True,
        compact_every_n_steps=CompressionConfig.STANDARD_COMPACT_EVERY,
        trigger_token_count=15000,       # More aggressive for ultra mode
        keep_last_items=2,               # Keep 2 recent items (maintains context)
        summary_max_chars=3000,          # Reasonable summary size
        chars_per_token=default_chars_per_token,
    )
    
    logger.debug(f"[AGENT_CONFIG] Created settings:")
    logger.debug(f"  enabled={settings.enabled}")
    logger.debug(f"  compact_every_n_steps={settings.compact_every_n_steps}")
    logger.debug(f"  trigger_char_count={settings.trigger_char_count}")
    logger.debug(f"  trigger_token_count={settings.trigger_token_count}")
    logger.debug(f"  keep_last_items={settings.keep_last_items}")
    logger.debug(f"  summary_max_chars={settings.summary_max_chars}")
    logger.debug(f"  chars_per_token={settings.chars_per_token}")
    logger.debug("=" * 80)
    
    # CRITICAL FIX: AgentSettings validator checks if BOTH trigger fields are set
    # MessageCompactionSettings validator auto-calculates trigger_char_count from trigger_token_count
    # But AgentSettings validator rejects objects with both fields set
    # Solution: Set trigger_char_count back to None before passing to AgentSettings
    logger.info("[AGENT_CONFIG] ⚠️  WORKAROUND: Setting trigger_char_count=None to avoid AgentSettings validation error")
    settings.trigger_char_count = None
    logger.info(f"[AGENT_CONFIG] After workaround: trigger_char_count={settings.trigger_char_count}, trigger_token_count={settings.trigger_token_count}")
    logger.debug("=" * 80)
    
    return settings


def get_agent_kwargs_with_compaction(
    use_vision: bool = True,
    use_thinking: bool = False,
    use_judge: bool = True,
    max_clickable_elements_length: int = DOMConfig.DEFAULT_MAX_CLICKABLE_ELEMENTS,
    context_length: Optional[int] = None,
    llm: Optional[Any] = None,
    **extra_kwargs
) -> dict:
    """
    Get agent kwargs with adaptive compaction settings based on model context size.
    
    This function automatically adapts MessageCompaction settings and DOM size limits
    based on the model's context window (65K, 100K, 128K+).
    
    Args:
        use_vision: Enable vision capabilities (default: True)
        use_thinking: Enable thinking mode (default: False)
        use_judge: Enable action validation (default: True)
        max_clickable_elements_length: Max DOM chars (default: 20000)
        context_length: Model's context window size in tokens (auto-detect if None)
        llm: LLM object to auto-detect context_length from
        **extra_kwargs: Additional kwargs to pass to agent
        
    Returns:
        Dictionary of agent kwargs ready to pass to Agent constructor
    """
    # Auto-detect context_length from LLM if not provided
    if context_length is None:
        context_length = detect_context_length(llm)
    
    # Validate and fix context_length if unreasonable
    if context_length < CompressionConfig.MIN_CONTEXT_LENGTH:
        logger.error(
            f"[AgentConfig] ❌ context_length={context_length} is too small "
            f"(< {CompressionConfig.MIN_CONTEXT_LENGTH}), "
            f"forcing minimum {CompressionConfig.MIN_CONTEXT_LENGTH}. "
            f"This may indicate a configuration error."
        )
        context_length = CompressionConfig.MIN_CONTEXT_LENGTH
    
    logger.info(f"[AgentConfig] 🎯 Using context_length={context_length} tokens")
    
    # Use adaptive compaction settings based on context size
    compaction_settings = get_compaction_settings_for_context_size(context_length)
    
    # Optionally adjust max_clickable_elements_length based on context size
    # Larger context models can handle more DOM content
    original_dom_limit = max_clickable_elements_length
    if max_clickable_elements_length == DOMConfig.DEFAULT_MAX_CLICKABLE_ELEMENTS:
        if context_length >= CompressionConfig.LARGE_CONTEXT_THRESHOLD:
            max_clickable_elements_length = DOMConfig.LARGE_CONTEXT_DOM_LIMIT
        elif context_length >= CompressionConfig.MEDIUM_CONTEXT_THRESHOLD:
            max_clickable_elements_length = DOMConfig.MEDIUM_CONTEXT_DOM_LIMIT
        # else: keep default for 65K models (covers 90% of e-commerce pages)
    
    # Warn if DOM limit is very large (may cause performance issues)
    if max_clickable_elements_length > DOMConfig.LARGE_DOM_WARNING_THRESHOLD:
        logger.warning(
            f"[AgentConfig] ⚠️  Large DOM limit ({max_clickable_elements_length} chars) may cause:"
            f"\n  - Slower DOM extraction (>1s)"
            f"\n  - Slower LLM inference (>4s)"
            f"\n  - Higher API costs (2x tokens)"
            f"\n  Consider reducing if performance is an issue."
        )
    
    # Log configuration for debugging
    logger.warning(
        f"[AgentConfig] 🔧 ULTRA-AGGRESSIVE MessageCompaction: "
        f"compact_every={compaction_settings.compact_every_n_steps}, "
        f"trigger={compaction_settings.trigger_token_count}, "
        f"keep_items={compaction_settings.keep_last_items}"
    )
    logger.warning(
        f"[AgentConfig] 🔧 Reduced DOM size: "
        f"max_clickable_elements_length={max_clickable_elements_length}"
    )
    
    agent_kwargs = {
        'use_vision': use_vision,
        'use_thinking': use_thinking,
        'use_judge': use_judge,
        'message_compaction': compaction_settings,
        'max_clickable_elements_length': max_clickable_elements_length,
        **extra_kwargs
    }
    
    # Validate configuration for potential issues
    _validate_agent_config(agent_kwargs, context_length)
    
    return agent_kwargs


def _validate_agent_config(agent_kwargs: dict, context_length: int) -> None:
    """
    Validate agent configuration and warn about potential issues.
    
    Args:
        agent_kwargs: Agent configuration dictionary
        context_length: Model's context window size
    """
    mc = agent_kwargs.get('message_compaction')
    if mc:
        # Check if trigger is too high (may cause overflow)
        max_trigger = context_length * CompressionConfig.MAX_TRIGGER_RATIO
        if mc.trigger_token_count and mc.trigger_token_count > max_trigger:
            logger.error(
                f"[AgentConfig] ❌ trigger_token_count ({mc.trigger_token_count}) is too high "
                f"(>{max_trigger:.0f}, {CompressionConfig.MAX_TRIGGER_RATIO:.0%} of context). "
                f"This will likely cause token overflow!"
            )
        
        # Check if compaction is disabled (risky)
        if not mc.enabled:
            logger.warning(
                f"[AgentConfig] ⚠️  MessageCompaction is DISABLED. "
                f"This may cause unbounded token growth and overflow!"
            )
    
    # Check DOM limit vs context size mismatch
    dom_limit = agent_kwargs.get('max_clickable_elements_length', 0)
    if dom_limit > 0:
        # Rough estimate: DOM chars → tokens (conservative)
        estimated_dom_tokens = dom_limit / TokenEstimationConfig.CJK_CHARS_PER_TOKEN
        max_dom_tokens = context_length * CompressionConfig.MAX_DOM_RATIO
        if estimated_dom_tokens > max_dom_tokens:
            logger.warning(
                f"[AgentConfig] ⚠️  DOM limit ({dom_limit} chars ≈ {estimated_dom_tokens:.0f} tokens) "
                f"is very large relative to context ({context_length} tokens). "
                f"This may leave insufficient space for history and responses."
            )


# Export constants for backward compatibility
DEFAULT_MAX_CLICKABLE_ELEMENTS = DOMConfig.DEFAULT_MAX_CLICKABLE_ELEMENTS
DEFAULT_RESERVED_TOKENS = DOMConfig.DEFAULT_RESERVED_TOKENS
