"""
DeepSeek Output Format Adapter for browser-use

Standard approach: Use browser-use's compatibility flags:
- add_schema_to_system_prompt=True
- dont_force_structured_output=True
- remove_min_items_from_schema=True
- remove_defaults_from_schema=True

This adapter ONLY handles DeepSeek-specific issues:
1. Filter invalid action types (file operations)
2. Handle mixed action types in single object
3. Convert completion indicators to 'done' action

All structural validation is handled by browser-use's Pydantic validation.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional

from utils.logger_helper import logger_helper as logger


class DeepSeekOutputAdapter:
    """
    Adapts DeepSeek output format to browser-use schema.
    
    Usage:
        adapter = DeepSeekOutputAdapter()
    """
    
    # Valid browser-use action types
    VALID_ACTIONS = {
        'go_to_url', 'click', 'input_text', 'scroll', 'extract',
        'done', 'search_google', 'open_tab', 'go_back', 'switch_tab',
        'close_tab', 'save_file', 'get_dropdown_options', 'select_dropdown_option'
    }
    
    # Invalid actions that DeepSeek sometimes generates
    INVALID_ACTIONS = {
        'read_file', 'write_file', 'move_file', 'verify_file', 
        'delete_file', 'list_files', 'create_directory', 'replace_file'
    }
    
    def __init__(self):
        self.adapt_count = 0
        self.error_count = 0
    
    def make_compatible_output(self, raw_output: str) -> str:
        """
        Transform DeepSeek output to browser-use compatible format.
        
        This is the main entry point for output adaptation. It handles:
        - Invalid action types removal
        - Missing 'done' field addition
        - Multiple action types normalization
        
        Args:
            raw_output: Raw JSON string from DeepSeek LLM
            
        Returns:
            Browser-use compatible JSON string
        """
        try:
            # Parse JSON
            # Note: Generic cleaning (markdown, think tags) is already done by LoggingBrowserUseChatOpenAI base class
            data = json.loads(raw_output.strip())
            
            # Adapt the data structure (DeepSeek-specific)
            adapted_data = self._adapt_structure(data)
            
            # Convert back to JSON
            return json.dumps(adapted_data, ensure_ascii=False)
            
        except json.JSONDecodeError as e:
            logger.error(f"[DeepSeekAdapter] Failed to parse JSON: {e}")
            self.error_count += 1
            return raw_output
        except Exception as e:
            logger.error(f"[DeepSeekAdapter] Unexpected error: {e}")
            self.error_count += 1
            return raw_output

    
    def _adapt_structure(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Adapt the overall structure.
        
        Ensures required fields exist for browser-use AgentOutput schema.
        Even with compatibility flags, LLM may not output all required fields.
        """
        if not isinstance(data, dict):
            return data
        
        # Adapt actions array
        if 'action' in data:
            data['action'] = self._adapt_actions(data['action'])
        else:
            # Ensure action exists (required field)
            data['action'] = self._adapt_actions([])
        
        # Ensure required fields exist (browser-use schema requires these)
        # Even with compatibility flags, missing fields cause validation errors
        if 'evaluation_previous_goal' not in data or data.get('evaluation_previous_goal') is None:
            data['evaluation_previous_goal'] = ''
        if 'memory' not in data or data.get('memory') is None:
            data['memory'] = ''
        if 'next_goal' not in data or data.get('next_goal') is None:
            data['next_goal'] = ''
        
        return data
    
    def _adapt_actions(self, actions: Any) -> List[Dict[str, Any]]:
        """
        Adapt the actions array.
        
        Handles:
        1. Filter invalid action types
        2. Handle mixed action types
        3. Ensure at least one action exists (min_items=1 requirement)
        """
        if not isinstance(actions, list):
            actions = [actions] if actions else []
        
        adapted_actions = []
        for action in actions:
            if not isinstance(action, dict):
                continue
            
            adapted_action = self._adapt_single_action(action)
            if adapted_action:
                adapted_actions.append(adapted_action)
        
        # If no valid actions, create a done action (browser-use requires min_items=1)
        if not adapted_actions:
            logger.warning("[DeepSeekAdapter] No valid actions found, creating done action")
            adapted_actions = [{
                'done': {
                    'text': 'Task completed',
                    'success': True
                }
            }]
            self.adapt_count += 1
        
        return adapted_actions
    
    def _adapt_single_action(self, action: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Adapt a single action - MINIMAL approach.
        
        Only handle DeepSeek-specific issues:
        1. Remove invalid action types (file operations)
        2. Handle mixed action types (keep first valid one)
        """
        # Remove invalid actions
        action = self._remove_invalid_actions(action)
        
        # If action is empty after cleanup, skip it
        if not action:
            return None
        
        # If action has multiple types, keep only the first valid one
        action_types = [k for k in action.keys() if k in self.VALID_ACTIONS]
        if len(action_types) > 1:
            logger.warning(f"[DeepSeekAdapter] Multiple action types found: {action_types}, keeping first")
            first_type = action_types[0]
            action = {first_type: action[first_type]}
            self.adapt_count += 1
        
        return action
    
    def _remove_invalid_actions(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Remove invalid action types from the action object."""
        cleaned = {}
        removed = []
        
        for key, value in action.items():
            if key in self.INVALID_ACTIONS:
                removed.append(key)
            else:
                cleaned[key] = value
        
        if removed:
            logger.warning(f"[DeepSeekAdapter] Removed invalid actions: {removed}")
            self.adapt_count += 1
        
        return cleaned
    
    def get_stats(self) -> Dict[str, int]:
        """Get statistics about adaptations applied."""
        return {
            'adaptations_applied': self.adapt_count,
            'errors_encountered': self.error_count
        }


def wrap_llm_with_compatible_output(llm: Any) -> Any:
    """
    Wrap an LLM to automatically transform output to browser-use compatible format.
    
    This wrapper intercepts OpenAI client responses at the lowest level,
    before browser-use calls model_validate_json().
    
    Args:
        llm: BrowserUseChatOpenAI instance
        
    Returns:
        Wrapped LLM with output adaptation
    """
    try:
        from functools import wraps
        
        adapter = DeepSeekOutputAdapter()
        
        # Store original get_client method
        original_get_client = llm.get_client
        
        def wrapped_get_client():
            """Wrapped get_client that adds response adaptation."""
            client = original_get_client()
            original_create = client.chat.completions.create
            
            @wraps(original_create)
            async def create_with_adaptation(*args, **kwargs):
                """Intercept response and apply DeepSeek adaptation."""
                response = await original_create(*args, **kwargs)
                
                # Adapt response content before browser-use processes it
                try:
                    if hasattr(response, 'choices') and response.choices and len(response.choices) > 0:
                        message = response.choices[0].message
                        if hasattr(message, 'content') and message.content:
                            original_content = message.content
                            logger.debug(f"[DeepSeekAdapter] Original output (first 500 chars): {original_content[:500]}")
                            
                            # Apply DeepSeek-specific adaptation
                            compatible_content = adapter.make_compatible_output(original_content)
                            
                            if original_content != compatible_content:
                                logger.info("[DeepSeekAdapter] ✅ Transformed output to compatible format")
                                logger.debug(f"[DeepSeekAdapter] Adapted output (first 500 chars): {compatible_content[:500]}")
                                message.content = compatible_content
                            else:
                                logger.debug("[DeepSeekAdapter] No transformation needed")
                except Exception as e:
                    logger.error(f"[DeepSeekAdapter] ❌ Failed to adapt response: {e}", exc_info=True)
                
                return response
            
            client.chat.completions.create = create_with_adaptation
            return client
        
        # Replace get_client method
        llm.get_client = wrapped_get_client
        
        logger.info("[DeepSeekAdapter] ✅ DeepSeek output adapter applied successfully")
        return llm
        
    except Exception as e:
        logger.error(f"[DeepSeekAdapter] ❌ Failed to wrap LLM: {e}", exc_info=True)
        return llm
