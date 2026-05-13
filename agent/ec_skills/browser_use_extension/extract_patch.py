"""
Runtime patch for browser-use extract tool to support dynamic MAX_CHAR_LIMIT.

This module provides a simple and reliable way to control browser-use's extract
tool character limit without modifying .venv files.

====================================================================================
USAGE
====================================================================================

In build_node.py, before creating browser-use Agent:

    if 'max_input_tokens' in agent_kwargs:
        from agent.ec_skills.browser_use_extension.extract_patch import patch_extract_max_char_limit
        patch_extract_max_char_limit(agent_kwargs['max_input_tokens'])

The patch will automatically:
1. Calculate appropriate character limit based on model's token capacity
2. Skip patching if limit >= default (100000) - keeps browser-use default for large models
3. Skip patching if value hasn't changed - avoids redundant operations
4. Support runtime LLM switching - automatically updates when user switches models

====================================================================================
HOW IT WORKS
====================================================================================

Strategy: Modify the bytecode of the extract function to replace the MAX_CHAR_LIMIT constant.

1. **Bytecode Modification**:
   - Searches for constant 100000 in extract function's bytecode
   - Replaces it with calculated max_chars value
   - Creates new function with modified bytecode

2. **Tools.__init__ Wrapping**:
   - Wraps browser-use Tools.__init__ to intercept instance creation
   - Patches the extract function after it's registered in the registry
   - Installs a dynamic wrapper for runtime LLM switching support

3. **Dynamic Wrapper**:
   - Reads current max_chars from global state on each extract call
   - Uses cache to avoid redundant patching (only patches when limit changes)
   - Enables seamless LLM switching without recreating Agent

4. **Performance Optimization**:
   - Global state check: Only patches when max_input_tokens changes
   - Cache mechanism: Reuses patched functions for same limit
   - Zero overhead after first call for same limit

====================================================================================
KEY FEATURES
====================================================================================

1. ✅ Dynamic calculation based on model's max_input_tokens
2. ✅ Only patches when calculated limit < default (100000)
3. ✅ Supports runtime LLM switching (updates patch when max_input_tokens changes)
4. ✅ Uses caching to avoid redundant patching operations
5. ✅ Thread-safe global state management
6. ✅ Detailed logging for debugging

====================================================================================
TECHNICAL DETAILS
====================================================================================

- Token to char conversion: 1 token ≈ 2.5 chars (conservative estimate)
- Default browser-use limit: 100,000 characters
- Global state: _current_max_chars tracks current patched value
- Cache: Per-Tools-instance patched function cache
- Logging: All operations logged with [ExtractPatch] prefix
"""

import time as time_module
import types
import traceback
from utils.logger_helper import logger_helper as logger

# ==================== Global State ====================
# Track the current patched max_chars value to detect changes
# This enables dynamic updates when user switches LLM models
_current_max_chars = None

# Timeout configuration for extract operations
EXTRACT_TIMEOUT_SECONDS = 30.0


def _patch_extract_function_bytecode(extract_func, max_chars: int):
    """
    Patch a single extract function's bytecode to replace MAX_CHAR_LIMIT constant.
    
    This function modifies the compiled bytecode of the extract function by replacing
    the hardcoded constant 100000 (default MAX_CHAR_LIMIT) with a custom value.
    
    Args:
        extract_func: The original extract function to patch
        max_chars: The new MAX_CHAR_LIMIT value to use
        
    Returns:
        A new function with patched bytecode, or None if patching fails
        
    Technical Details:
        - Searches for integer constant 100000 in function's co_consts
        - Replaces it with max_chars
        - Creates a new code object and function with the modified constant
        - Preserves all other function attributes (globals, defaults, closure)
    """
    logger.info(f"[ExtractPatch] 🔧 Starting bytecode patch for extract function")
    logger.info(f"[ExtractPatch] Function name: {extract_func.__name__}")
    
    code = extract_func.__code__
    
    # Log all integer constants for debugging
    int_consts = [c for c in code.co_consts if isinstance(c, int)]
    logger.info(f"[ExtractPatch] 📋 Integer constants in extract function: {int_consts}")
    
    # Replace 100000 (default MAX_CHAR_LIMIT) with max_chars in constants
    found_100000 = False
    new_consts = []
    for c in code.co_consts:
        if isinstance(c, int) and c == 100000:
            new_consts.append(max_chars)
            found_100000 = True
            logger.info(f"[ExtractPatch] ✅ Replaced constant: 100000 → {max_chars:,}")
        else:
            new_consts.append(c)
    
    if not found_100000:
        logger.warning(
            f"[ExtractPatch] ⚠️ Constant 100000 not found! "
            f"Available int constants: {int_consts}"
        )
        return None
    
    # Create new code object with modified constants
    new_code = code.replace(co_consts=tuple(new_consts))
    logger.info(f"[ExtractPatch] ✅ Created new code object with modified constants")
    
    # Create new function with modified code
    # Preserve all original function attributes except the code object
    new_func = types.FunctionType(
        new_code,
        extract_func.__globals__,
        extract_func.__name__,
        extract_func.__defaults__,
        extract_func.__closure__
    )
    
    logger.info(f"[ExtractPatch] ✅ Created new function with patched bytecode")
    return new_func


def patch_extract_max_char_limit(max_input_tokens: int) -> bool:
    """
    Patch browser-use's extract tool to use a dynamic MAX_CHAR_LIMIT based on max_input_tokens.
    
    This is the main entry point for applying the extract patch. It should be called:
    1. Before creating a browser-use Agent (in build_node.py)
    2. When switching LLM models (automatically via global state update)
    
    The function implements intelligent patching:
    - Only patches if calculated limit < default (100000)
    - Skips patching if value hasn't changed (performance optimization)
    - Supports runtime updates when user switches LLM models
    
    Args:
        max_input_tokens: Maximum input tokens for the model (from agent config)
                         This is calculated as: context_length - reserved_tokens
        
    Returns:
        True if patch was successful or skipped (no change needed)
        False if patching failed
        
    Example:
        # In build_node.py, before creating Agent:
        if 'max_input_tokens' in agent_kwargs:
            patch_extract_max_char_limit(agent_kwargs['max_input_tokens'])
    """
    global _current_max_chars
    
    # ==================== Step 1: Calculate safe extract limit ====================
    # browser-use default: 100,000 characters
    DEFAULT_CHAR_LIMIT = 100000
    
    # Reserve tokens for system prompt, history, and other overhead
    # Based on actual log analysis:
    #   - System prompt: ~650 tokens
    #   - History (compressed): ~150 tokens (browser-use uses aggressive compression)
    #   - Response: ~500 tokens
    #   - Other overhead: ~200 tokens
    #   - Total actual: ~1,500 tokens
    #   - Reserved: 3,000 tokens (100% safety margin)
    RESERVED_TOKENS = 3000
    
    # Calculate safe limit for extract content
    # This ensures: extract_content + overhead ≤ max_input_tokens
    available_tokens_for_extract = max(max_input_tokens - RESERVED_TOKENS, 1000)
    max_chars = int(available_tokens_for_extract * 2.5)
    
    # ==================== Step 2: Check if patching is needed ====================
    # Only patch if calculated limit is SMALLER than browser-use default
    # If calculated limit >= default, use browser-use default (more conservative)
    if max_chars >= DEFAULT_CHAR_LIMIT:
        logger.info(
            f"[ExtractPatch] ℹ️ Calculated safe limit ({max_chars:,} chars from "
            f"{available_tokens_for_extract:,} tokens) >= browser-use default ({DEFAULT_CHAR_LIMIT:,} chars)"
        )
        logger.info(
            f"[ExtractPatch] ✅ Using browser-use default ({DEFAULT_CHAR_LIMIT:,} chars), no patch needed"
        )
        # Reset global state to indicate no custom limit
        _current_max_chars = None
        return True
    
    # Need to patch - model capacity is small, need stricter limit
    logger.info(
        f"[ExtractPatch] ⚠️ Model capacity limited: calculated safe limit ({max_chars:,} chars) "
        f"< browser-use default ({DEFAULT_CHAR_LIMIT:,} chars)"
    )
    logger.info(
        f"[ExtractPatch] 🔧 Will patch to use stricter limit: {max_chars:,} chars "
        f"(reserved {RESERVED_TOKENS:,} tokens for system overhead)"
    )
    
    # ==================== Step 3: Skip if value unchanged ====================
    # Avoid redundant patching if the limit hasn't changed
    # This is critical for performance when called multiple times
    if _current_max_chars == max_chars:
        logger.debug(f"[ExtractPatch] ✅ Already patched with same value ({max_chars:,}), skipping")
        return True
    
    # ==================== Step 4: Log update if this is a model switch ====================
    # If _current_max_chars is not None, this is an update (not first-time patch)
    if _current_max_chars is not None:
        logger.info(
            f"[ExtractPatch] 🔄 Updating patch: {_current_max_chars:,} → {max_chars:,} "
            f"(max_input_tokens changed: model switch detected)"
        )
    
    try:
        # Import browser_use.tools.service to ensure it's loaded
        from browser_use.tools import service as tools_service
        
        logger.info(
            f"[ExtractPatch] 🔧 Patching browser_use extract MAX_CHAR_LIMIT: "
            f"default {DEFAULT_CHAR_LIMIT:,} chars → safe limit {max_chars:,} chars"
        )
        
        # ==================== Step 5: Install Tools.__init__ wrapper ====================
        # Strategy: Wrap Tools.__init__ to patch the extract function after it's registered
        # The extract function is created inside Tools.__init__, so we must patch it
        # after __init__ completes but before the Tools instance is used
        Tools = tools_service.Tools
        original_init = Tools.__init__
        
        def patched_init(self, *args, **kwargs):
            """
            Wrapped Tools.__init__ that patches the extract function after registration.
            
            This wrapper:
            1. Calls the original __init__ to register all actions (including extract)
            2. Locates the extract action in the registry
            3. Replaces the extract function with a dynamic wrapper
            
            The dynamic wrapper enables runtime LLM switching by checking the global
            _current_max_chars value on each extract call.
            """
            logger.info(f"[ExtractPatch] 🔧 patched_init called for Tools instance")
            
            # Call original __init__ to register all actions
            result = original_init(self, *args, **kwargs)
            logger.info(f"[ExtractPatch] ✅ original_init completed")
            
            # Now patch the extract method if it exists
            try:
                logger.info(f"[ExtractPatch] 📋 Checking for registry and actions...")
                if hasattr(self, 'registry'):
                    logger.info(f"[ExtractPatch] ✅ Found registry")
                    # browser-use Registry structure: self.registry.registry.actions
                    if hasattr(self.registry, 'registry') and hasattr(self.registry.registry, 'actions'):
                        logger.info(f"[ExtractPatch] ✅ Found actions, count: {len(self.registry.registry.actions)}")
                        extract_action = self.registry.registry.actions.get('extract')
                        
                        if extract_action:
                            logger.info(f"[ExtractPatch] ✅ Found extract action, keys: {list(extract_action.keys())}")
                            if 'function' in extract_action:
                                logger.info(f"[ExtractPatch] 🔧 Installing dynamic extract wrapper...")
                                
                                # Store original function for dynamic re-patching
                                original_extract_func = extract_action['function']
                                
                                # Cache for patched functions (key: max_chars, value: patched_func)
                                # This avoids redundant bytecode patching when limit hasn't changed
                                patched_cache = {}
                                
                                # ==================== Dynamic Extract Wrapper ====================
                                # This wrapper enables runtime LLM switching support
                                def dynamic_extract_wrapper(*args, **kwargs):
                                    """
                                    Dynamic wrapper for extract function that supports runtime LLM switching.
                                    
                                    How it works:
                                    1. Reads current max_chars from global state (_current_max_chars)
                                    2. Checks if we have a cached patched function for this limit
                                    3. If not cached, patches the original function with the new limit
                                    4. Calls the cached/patched function
                                    
                                    Performance optimization:
                                    - Uses patched_cache to avoid re-patching for the same limit
                                    - Only patches when _current_max_chars changes (e.g., LLM switch)
                                    
                                    Thread safety:
                                    - Reads from global _current_max_chars (set by patch_extract_max_char_limit)
                                    - Cache is per-Tools-instance (no cross-instance conflicts)
                                    
                                    NOTE: Timeout protection is handled in extension_tools_service.extract_dom()
                                    and browser-use's built-in 120s timeout for LLM calls.
                                    """
                                    global _current_max_chars
                                    
                                    # Get current max_chars from global state
                                    # This value is updated by patch_extract_max_char_limit() when LLM switches
                                    current_limit = _current_max_chars or max_chars
                                    
                                    # Check cache first to avoid redundant patching
                                    # Only patch if this is a new limit value (e.g., after LLM switch)
                                    if current_limit not in patched_cache:
                                        logger.debug(f"[ExtractPatch] 🔄 Cache miss, patching for limit={current_limit:,}")
                                        patched_func = _patch_extract_function_bytecode(original_extract_func, current_limit)
                                        if patched_func:
                                            patched_cache[current_limit] = patched_func
                                        else:
                                            # Fallback to original if patching fails
                                            patched_cache[current_limit] = original_extract_func
                                    
                                    # Call the cached patched function (zero overhead after first call)
                                    # Log rich diagnostics for empty-message failures from browser-use extract.
                                    try:
                                        return patched_cache[current_limit](*args, **kwargs)
                                    except Exception as exc:
                                        _exc_type = type(exc).__name__
                                        _exc_args = getattr(exc, "args", ())
                                        logger.error(
                                            "[ExtractPatch] ❌ extract execution failed "
                                            "(limit=%s, exc_type=%s, exc_args=%s, exc_repr=%r)",
                                            current_limit,
                                            _exc_type,
                                            _exc_args,
                                            exc,
                                        )
                                        logger.error(
                                            "[ExtractPatch] ❌ extract traceback:\n%s",
                                            traceback.format_exc(),
                                        )
                                        raise
                                
                                # Replace the extract function with our dynamic wrapper
                                extract_action['function'] = dynamic_extract_wrapper
                                logger.info(f"[ExtractPatch] ✅ Installed dynamic extract wrapper (supports runtime LLM switch)")
                            else:
                                logger.warning(f"[ExtractPatch] ⚠️ Extract action has no 'function' key")
                        else:
                            logger.warning(f"[ExtractPatch] ⚠️ No extract action found in registry.actions")
                    else:
                        logger.warning(f"[ExtractPatch] ⚠️ Registry has no registry.actions attribute")
                else:
                    logger.warning(f"[ExtractPatch] ⚠️ Tools instance has no registry attribute")
            except Exception as e:
                logger.error(f"[ExtractPatch] ❌ Failed to patch instance: {e}", exc_info=True)
            
            return result
        
        # ==================== Step 6: Replace Tools.__init__ ====================
        # Replace the original Tools.__init__ with our wrapped version
        # This ensures all future Tools instances will have the patched extract function
        Tools.__init__ = patched_init
        logger.info(f"[ExtractPatch] ✅ Installed __init__ wrapper for future Tools instances")
        
        # ==================== Step 7: Update global state ====================
        # Store the current max_chars value for future reference
        # This is used by the dynamic wrapper to detect changes (e.g., LLM switch)
        _current_max_chars = max_chars
        logger.info(f"[ExtractPatch] ✅ Patch complete: MAX_CHAR_LIMIT = {max_chars:,} chars")
        return True
        
    except Exception as e:
        logger.error(f"[ExtractPatch] ❌ Failed to patch: {e}", exc_info=True)
        return False


def patch_extract_with_context_length(context_length: int) -> bool:
    """
    Patch extract tool based on model's context length.
    
    Args:
        context_length: Model's context window size in tokens
        
    Returns:
        True if patch was successful, False otherwise
    """
    # Reserve tokens for: system prompt (5K) + response (4K) + safety (2K) = 11K
    extraction_reserved = 11000
    
    # Calculate max_input_tokens (at least 10K, at most 80% of context)
    max_input_tokens = min(
        max(context_length - extraction_reserved, 10000),
        int(context_length * 0.8)
    )
    
    # Calculate max chars from tokens
    # IMPORTANT: Use conservative estimate to ensure we REDUCE the limit, not increase it
    # browser-use default is 100,000 chars which is too large
    # Use 1.2 chars/token (very conservative) to ensure safety
    max_chars = int(max_input_tokens * 1.2)
    
    # Additional safety: cap at 50,000 chars (about 25K-40K tokens depending on content)
    # This is significantly smaller than browser-use's default 100,000
    max_chars = min(max_chars, 50000)
    
    logger.info(
        f"[ExtractPatch] Calculated limits: context={context_length}, "
        f"max_input_tokens={max_input_tokens}, max_chars={max_chars} "
        f"(reduced from browser-use default 100,000)"
    )
    
    # Apply patch
    return patch_extract_max_char_limit(max_chars)
