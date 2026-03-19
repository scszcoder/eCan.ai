"""
Chat ID Extractor - Multi-strategy extraction of chat/customer IDs from events and DOM.

Implements cascading extraction strategies with priority-based fallback:
1. Event payload extraction (fastest, most reliable)
2. DOM attribute extraction (reliable if element is present)
3. URL pattern matching (reliable if URL contains ID)
4. DOM text extraction (fallback for text-based IDs)

Usage:
    extractor = ChatIdExtractor()
    chat_id = extractor.extract(
        event_or_dom=event_params,
        extraction_rules=profile['chat_id_extraction'],
        browser_session=browser
    )
"""

import re
from typing import Optional, Any, Dict, List
from utils.logger_helper import logger_helper as logger


class ChatIdExtractor:
    """Extracts chat/customer IDs using multiple strategies."""
    
    def __init__(self):
        self._success_cache: Dict[str, str] = {}  # platform_id -> last successful method
        logger.debug("[ChatIdExtractor] Initialized")
    
    def extract(
        self,
        event_or_dom: Any,
        extraction_rules: List[dict],
        browser_session = None,
        platform_id: str = "unknown"
    ) -> Optional[str]:
        """
        Extract chat ID using prioritized extraction rules.
        
        Args:
            event_or_dom: Event params dict or DOM snapshot
            extraction_rules: List of extraction rule dicts from platform profile
            browser_session: Optional browser session for DOM access
            platform_id: Platform identifier for caching successful method
        
        Returns:
            Extracted and validated chat ID, or None if extraction failed
        """
        if not extraction_rules:
            logger.warning("[ChatIdExtractor] No extraction rules provided")
            return None
        
        # Sort rules by priority
        sorted_rules = sorted(extraction_rules, key=lambda r: r.get('priority', 999))
        
        # Try cached method first if available
        cached_method = self._success_cache.get(platform_id)
        if cached_method:
            for rule in sorted_rules:
                if rule.get('method') == cached_method:
                    chat_id = self._try_extract(rule, event_or_dom, browser_session)
                    if chat_id:
                        logger.debug(
                            f"[ChatIdExtractor] Extracted using cached method: {cached_method}"
                        )
                        return chat_id
                    break
        
        # Try each rule in priority order
        for rule in sorted_rules:
            method = rule.get('method')
            if not method:
                continue
            
            try:
                chat_id = self._try_extract(rule, event_or_dom, browser_session)
                
                if chat_id:
                    # Cache successful method
                    self._success_cache[platform_id] = method
                    
                    logger.info(
                        f"[ChatIdExtractor] Extracted chat_id using {method}: "
                        f"{chat_id[:20]}{'...' if len(chat_id) > 20 else ''}"
                    )
                    return chat_id
                    
            except Exception as e:
                logger.debug(f"[ChatIdExtractor] Method {method} failed: {e}")
                continue
        
        logger.warning(
            f"[ChatIdExtractor] All extraction methods failed for platform {platform_id}"
        )
        return None
    
    def _try_extract(
        self,
        rule: dict,
        event_or_dom: Any,
        browser_session
    ) -> Optional[str]:
        """Try a single extraction method."""
        method = rule.get('method')
        
        if method == 'event_payload':
            return self._extract_from_event_payload(event_or_dom, rule)
        elif method == 'dom_attribute':
            return self._extract_from_dom_attribute(browser_session, rule)
        elif method == 'url_pattern':
            return self._extract_from_url_pattern(browser_session, rule)
        elif method == 'dom_text':
            return self._extract_from_dom_text(browser_session, rule)
        else:
            logger.warning(f"[ChatIdExtractor] Unknown extraction method: {method}")
            return None
    
    def _extract_from_event_payload(self, event_params: Any, rule: dict) -> Optional[str]:
        """Extract chat ID from event payload using JSON path."""
        if not isinstance(event_params, dict):
            return None
        
        path = rule.get('path', '')
        if not path:
            return None
        
        # Navigate JSON path (e.g., "params.response.data.conversationId")
        value = self._navigate_path(event_params, path)
        
        if value is None:
            return None
        
        # Convert to string
        chat_id = str(value)
        
        # Validate
        return self._validate_chat_id(chat_id, rule)
    
    def _extract_from_dom_attribute(self, browser_session, rule: dict) -> Optional[str]:
        """Extract chat ID from DOM element attribute."""
        if not browser_session:
            return None
        
        selector = rule.get('selector', '')
        attribute = rule.get('attribute', '')
        
        if not selector or not attribute:
            return None
        
        try:
            # Execute JavaScript to get attribute value
            if hasattr(browser_session, 'execute_script'):
                script = f"""
                const elem = document.querySelector('{selector}');
                return elem ? elem.getAttribute('{attribute}') : null;
                """
                value = browser_session.execute_script(script)
                
                if value:
                    chat_id = str(value)
                    return self._validate_chat_id(chat_id, rule)
            
            return None
            
        except Exception as e:
            logger.debug(f"[ChatIdExtractor] DOM attribute extraction failed: {e}")
            return None
    
    def _extract_from_url_pattern(self, browser_session, rule: dict) -> Optional[str]:
        """Extract chat ID from URL using regex pattern."""
        regex = rule.get('regex', '')
        if not regex:
            return None
        
        # Get current URL
        url = None
        try:
            if browser_session and hasattr(browser_session, 'get_url'):
                url = browser_session.get_url()
            elif browser_session and hasattr(browser_session, 'current_url'):
                url = browser_session.current_url
        except Exception as e:
            logger.debug(f"[ChatIdExtractor] Failed to get URL: {e}")
            return None
        
        if not url:
            return None
        
        # Match regex
        match = re.search(regex, url)
        if match:
            # Get first capture group
            chat_id = match.group(1) if match.lastindex and match.lastindex >= 1 else match.group(0)
            return self._validate_chat_id(chat_id, rule)
        
        return None
    
    def _extract_from_dom_text(self, browser_session, rule: dict) -> Optional[str]:
        """Extract chat ID from DOM text content using regex."""
        if not browser_session:
            return None
        
        selector = rule.get('selector', '')
        regex = rule.get('regex', '')
        
        if not selector or not regex:
            return None
        
        try:
            # Execute JavaScript to get text content
            if hasattr(browser_session, 'execute_script'):
                script = f"""
                const elem = document.querySelector('{selector}');
                return elem ? elem.textContent : null;
                """
                text = browser_session.execute_script(script)
                
                if text:
                    # Match regex
                    match = re.search(regex, text)
                    if match:
                        chat_id = match.group(1) if match.lastindex and match.lastindex >= 1 else match.group(0)
                        return self._validate_chat_id(chat_id, rule)
            
            return None
            
        except Exception as e:
            logger.debug(f"[ChatIdExtractor] DOM text extraction failed: {e}")
            return None
    
    def _navigate_path(self, obj: Any, path: str) -> Any:
        """Navigate a dot-separated path in a nested dict/object."""
        if not path:
            return None
        
        parts = path.split('.')
        current = obj
        
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            elif hasattr(current, part):
                current = getattr(current, part)
            else:
                return None
            
            if current is None:
                return None
        
        return current
    
    def _validate_chat_id(self, chat_id: str, rule: dict) -> Optional[str]:
        """Validate extracted chat ID against regex pattern."""
        if not chat_id:
            return None
        
        # Strip whitespace
        chat_id = chat_id.strip()
        
        if not chat_id:
            return None
        
        # Check validation regex if provided
        validation_regex = rule.get('validation_regex', '')
        if validation_regex:
            if not re.match(validation_regex, chat_id):
                logger.debug(
                    f"[ChatIdExtractor] Validation failed: '{chat_id}' "
                    f"does not match pattern '{validation_regex}'"
                )
                return None
        
        return chat_id
    
    def clear_cache(self, platform_id: Optional[str] = None):
        """Clear success cache for a platform or all platforms."""
        if platform_id:
            self._success_cache.pop(platform_id, None)
            logger.debug(f"[ChatIdExtractor] Cleared cache for {platform_id}")
        else:
            self._success_cache.clear()
            logger.debug("[ChatIdExtractor] Cleared all cache")


# ==================== Singleton ====================

_instance: Optional[ChatIdExtractor] = None


def get_chat_id_extractor() -> ChatIdExtractor:
    """Get or create singleton ChatIdExtractor instance."""
    global _instance
    if _instance is None:
        _instance = ChatIdExtractor()
    return _instance


# ==================== Convenience Functions ====================

def extract_chat_id_from_event(
    event_params: dict,
    platform_profile: dict,
    browser_session = None
) -> Optional[str]:
    """
    Convenience function to extract chat ID from an event.
    
    Args:
        event_params: Event parameters dict
        platform_profile: Platform profile dict
        browser_session: Optional browser session for fallback DOM extraction
    
    Returns:
        Extracted chat ID or None
    """
    extractor = get_chat_id_extractor()
    extraction_rules = platform_profile.get('chat_id_extraction', [])
    platform_id = platform_profile.get('platform_id', 'unknown')
    
    return extractor.extract(
        event_or_dom=event_params,
        extraction_rules=extraction_rules,
        browser_session=browser_session,
        platform_id=platform_id
    )


def extract_chat_id_from_browser(
    browser_session,
    platform_profile: dict
) -> Optional[str]:
    """
    Convenience function to extract chat ID from current browser state.
    
    Args:
        browser_session: Browser session object
        platform_profile: Platform profile dict
    
    Returns:
        Extracted chat ID or None
    """
    extractor = get_chat_id_extractor()
    extraction_rules = platform_profile.get('chat_id_extraction', [])
    platform_id = platform_profile.get('platform_id', 'unknown')
    
    # Pass empty dict as event_or_dom since we're using browser-based extraction
    return extractor.extract(
        event_or_dom={},
        extraction_rules=extraction_rules,
        browser_session=browser_session,
        platform_id=platform_id
    )
