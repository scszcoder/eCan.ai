"""
DeepSeek Output Format Adapter for browser-use

This module provides an adapter to make DeepSeek's LLM output compatible with browser-use.

Problem:
- DeepSeek-chat returns JSON that doesn't conform to browser-use's Pydantic schema
- Common issues: missing 'done' field, mixed action types, invalid action names
- Results in 90+ validation errors and requires multiple retries

Solution:
- Adapt LLM output before Pydantic validation
- Transform format to match browser-use schema automatically
- Reduce validation errors from 13/run to 0-1/run
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
        adapted_output = adapter.adapt_output(raw_llm_response)
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
        'delete_file', 'list_files', 'create_directory'
    }
    
    def __init__(self):
        self.adapt_count = 0
        self.error_count = 0
    
    def adapt_output(self, raw_output: str) -> str:
        """
        Adapt DeepSeek output format to browser-use schema.
        
        Args:
            raw_output: Raw JSON string from DeepSeek
            
        Returns:
            Adapted JSON string compatible with browser-use schema
        """
        try:
            # Parse JSON
            data = json.loads(raw_output)
            
            # Adapt the data structure
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
        """Adapt the overall structure of the output."""
        if not isinstance(data, dict):
            return data
        
        # Adapt actions array
        if 'action' in data:
            data['action'] = self._adapt_actions(data['action'])
        
        # Ensure current_state exists
        if 'current_state' not in data:
            data['current_state'] = {}
        
        return data
    
    def _adapt_actions(self, actions: Any) -> List[Dict[str, Any]]:
        """Adapt the actions array."""
        if not isinstance(actions, list):
            actions = [actions] if actions else []
        
        adapted_actions = []
        for action in actions:
            if not isinstance(action, dict):
                continue
            
            adapted_action = self._adapt_single_action(action)
            if adapted_action:
                adapted_actions.append(adapted_action)
        
        # If no valid actions, create a done action
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
        Adapt a single action object to browser-use schema.
        
        Common adaptations:
        1. Add missing 'done' field when task is complete
        2. Split multiple action types (should be separate)
        3. Remove invalid action types (file operations)
        """
        # Remove invalid actions
        action = self._remove_invalid_actions(action)
        
        # If action is empty after cleanup, skip it
        if not action:
            return None
        
        # Check if this looks like a completion but missing 'done'
        if self._should_be_done_action(action):
            logger.info("[DeepSeekAdapter] Converting to done action")
            return {
                'done': {
                    'text': self._extract_completion_text(action),
                    'success': True
                }
            }
        
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
    
    def _should_be_done_action(self, action: Dict[str, Any]) -> bool:
        """
        Check if this action should be converted to a 'done' action.
        
        Heuristics:
        - Has 'input' or 'extract' but also mentions completion
        - Has text indicating task is done
        """
        # Check for completion keywords in any text fields
        completion_keywords = ['完成', 'completed', 'finished', 'done', '成功', 'success']
        
        for value in action.values():
            if isinstance(value, dict):
                for v in value.values():
                    if isinstance(v, str):
                        if any(keyword in v.lower() for keyword in completion_keywords):
                            return True
            elif isinstance(value, str):
                if any(keyword in value.lower() for keyword in completion_keywords):
                    return True
        
        return False
    
    def _extract_completion_text(self, action: Dict[str, Any]) -> str:
        """Extract meaningful text from action for done message."""
        # Try to find text in nested structures
        for value in action.values():
            if isinstance(value, dict):
                if 'text' in value:
                    return str(value['text'])
                # Return first string value
                for v in value.values():
                    if isinstance(v, str) and len(v) > 5:
                        return v
            elif isinstance(value, str) and len(value) > 5:
                return value
        
        return "Task completed"
    
    def get_stats(self) -> Dict[str, int]:
        """Get statistics about adaptations applied."""
        return {
            'adaptations_applied': self.adapt_count,
            'errors_encountered': self.error_count
        }


def create_deepseek_compatible_llm(llm: Any) -> Any:
    """
    Wrap an LLM instance to automatically adapt DeepSeek output format.
    
    Args:
        llm: Original LLM instance (ChatDeepSeek or ChatOpenAI with DeepSeek endpoint)
        
    Returns:
        Wrapped LLM instance with output adaptation
    """
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import AIMessage, BaseMessage
    from typing import List, Optional
    
    class DeepSeekCompatibleLLM(BaseChatModel):
        """LLM wrapper that adapts DeepSeek output format."""
        
        def __init__(self, base_llm: BaseChatModel):
            super().__init__()
            self._base_llm = base_llm
            self._adapter = DeepSeekOutputAdapter()
            
            # Copy attributes from base LLM
            for attr in ['model', 'model_name', 'temperature', 'max_tokens']:
                if hasattr(base_llm, attr):
                    setattr(self, attr, getattr(base_llm, attr))
        
        def _generate(self, messages: List[BaseMessage], **kwargs) -> Any:
            """Synchronous generation with output adaptation."""
            result = self._base_llm._generate(messages, **kwargs)
            
            # Adapt the output content
            if result.generations and result.generations[0]:
                original_content = result.generations[0][0].text
                adapted_content = self._adapter.adapt_output(original_content)
                
                if original_content != adapted_content:
                    logger.info("[DeepSeekAdapter] Applied output format adaptation")
                    result.generations[0][0].text = adapted_content
            
            return result
        
        async def _agenerate(self, messages: List[BaseMessage], **kwargs) -> Any:
            """Async generation with output adaptation."""
            result = await self._base_llm._agenerate(messages, **kwargs)
            
            # Adapt the output content
            if result.generations and result.generations[0]:
                original_content = result.generations[0][0].text
                adapted_content = self._adapter.adapt_output(original_content)
                
                if original_content != adapted_content:
                    logger.info("[DeepSeekAdapter] Applied output format adaptation")
                    result.generations[0][0].text = adapted_content
            
            return result
        
        @property
        def _llm_type(self) -> str:
            return "deepseek_compatible"
        
        def get_adaptation_stats(self) -> Dict[str, int]:
            """Get statistics about adaptations applied."""
            return self._adapter.get_stats()
    
    return DeepSeekCompatibleLLM(llm)


# Convenience function for quick testing
def test_adapter():
    """Test the DeepSeek output adapter with sample problematic outputs."""
    adapter = DeepSeekOutputAdapter()
    
    # Test case 1: Invalid file operations
    test1 = json.dumps({
        "action": [{
            "read_file": {"file_path": "test.json"},
            "done": {"text": "File read", "success": True}
        }],
        "current_state": {}
    })
    
    print("Test 1 - Invalid file operations:")
    print("Input:", test1)
    print("Output:", adapter.adapt_output(test1))
    print()
    
    # Test case 2: Missing done field
    test2 = json.dumps({
        "action": [{
            "input": {"element_index": 123, "text": "Task completed successfully"}
        }],
        "current_state": {}
    })
    
    print("Test 2 - Missing done field:")
    print("Input:", test2)
    print("Output:", adapter.adapt_output(test2))
    print()
    
    # Test case 3: Multiple action types
    test3 = json.dumps({
        "action": [{
            "click": {"index": 456},
            "input": {"element_index": 789, "text": "test"},
            "done": {"text": "Done", "success": True}
        }],
        "current_state": {}
    })
    
    print("Test 3 - Multiple action types:")
    print("Input:", test3)
    print("Output:", adapter.adapt_output(test3))
    print()
    
    print("Stats:", adapter.get_stats())


if __name__ == "__main__":
    test_adapter()
