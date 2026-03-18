"""
Chat Event Dispatcher - Unified coordinator for CDP events and polling-based chat detection.

Manages the complete lifecycle of chat message monitoring:
1. Platform detection
2. CDP event subscription (if available)
3. Polling fallback (always active as safety net)
4. Chat ID extraction
5. Event deduplication
6. Routing to worker agents

Usage:
    dispatcher = get_chat_event_dispatcher()
    monitor_id = dispatcher.start_monitoring(
        agent_id="orchestrator_123",
        platform_id="amazon_seller_central",
        cdp_client=cdp_client,
        browser_session=browser,
        on_new_message=handle_message
    )
    # Later:
    dispatcher.stop_monitoring(monitor_id)
"""

import time
import uuid
import threading
from typing import Callable, Dict, Optional, Any, List, Set
from dataclasses import dataclass, field

from utils.logger_helper import logger_helper as logger

from agent.ec_tasks.platform_detector import get_platform_detector
from agent.ec_tasks.browser_event_service import subscribe_with_platform_profile, unsubscribe_all
from agent.ec_tasks.polling_service import get_polling_service
from agent.ec_tasks.chat_id_extractor import extract_chat_id_from_event, extract_chat_id_from_browser


@dataclass
class MonitorState:
    """State for a single monitoring instance."""
    monitor_id: str
    agent_id: str
    platform_id: str
    platform_profile: dict
    on_new_message: Callable
    
    # Subscription IDs
    cdp_subscription_ids: List[str] = field(default_factory=list)
    poll_id: Optional[str] = None
    
    # Deduplication
    seen_message_hashes: Set[str] = field(default_factory=set)
    last_event_time: float = field(default_factory=time.time)
    
    # Statistics
    event_count: int = 0
    cdp_event_count: int = 0
    poll_event_count: int = 0
    duplicate_count: int = 0
    
    # Runtime state
    is_active: bool = True


class ChatEventDispatcher:
    """Coordinates CDP events and polling for chat message detection."""
    
    def __init__(self):
        self._monitors: Dict[str, MonitorState] = {}
        self._lock = threading.Lock()
        logger.info("[ChatEventDispatcher] Initialized")
    
    def start_monitoring(
        self,
        agent_id: str,
        platform_id: Optional[str] = None,
        cdp_client = None,
        browser_session = None,
        on_new_message: Callable[[dict], None] = None,
        chat_id_filter: Optional[str] = None
    ) -> str:
        """
        Start monitoring for new chat messages.
        
        Args:
            agent_id: Agent ID for this monitoring instance
            platform_id: Platform identifier (if None, will auto-detect)
            cdp_client: CDP client for event subscription
            browser_session: Browser session for polling and extraction
            on_new_message: Callback when new message detected, receives event dict
            chat_id_filter: Optional specific chat ID to monitor
        
        Returns:
            monitor_id for managing this monitoring instance
        """
        if not on_new_message:
            logger.error("[ChatEventDispatcher] on_new_message callback is required")
            return ""
        
        # Auto-detect platform if not provided
        if not platform_id and browser_session:
            from agent.ec_tasks.platform_detector import detect_platform_from_browser
            platform_id = detect_platform_from_browser(browser_session)
            if not platform_id:
                logger.warning("[ChatEventDispatcher] Could not detect platform, using polling only")
                platform_id = "unknown"
        
        if not platform_id:
            logger.error("[ChatEventDispatcher] platform_id is required")
            return ""
        
        # Get platform profile
        detector = get_platform_detector()
        platform_profile = detector.get_profile(platform_id)
        
        if not platform_profile:
            logger.error(f"[ChatEventDispatcher] Profile not found for platform: {platform_id}")
            return ""
        
        monitor_id = str(uuid.uuid4())
        
        monitor_state = MonitorState(
            monitor_id=monitor_id,
            agent_id=agent_id,
            platform_id=platform_id,
            platform_profile=platform_profile,
            on_new_message=on_new_message
        )
        
        with self._lock:
            self._monitors[monitor_id] = monitor_state
        
        # Start CDP event subscriptions (if available)
        if cdp_client:
            try:
                subscription_ids = subscribe_with_platform_profile(
                    agent_id=agent_id,
                    cdp_client=cdp_client,
                    platform_profile=platform_profile,
                    chat_id_filter=chat_id_filter
                )
                
                with self._lock:
                    monitor_state.cdp_subscription_ids = subscription_ids
                
                if subscription_ids:
                    logger.info(
                        f"[ChatEventDispatcher] Subscribed to {len(subscription_ids)} "
                        f"CDP event(s) for {platform_id}"
                    )
            except Exception as e:
                logger.error(f"[ChatEventDispatcher] CDP subscription failed: {e}")
        
        # Start polling (always, as fallback/safety net)
        polling_service = get_polling_service()
        
        def polling_callback(event: dict):
            """Handle polling change events."""
            self._handle_event(monitor_id, event, source='polling', browser_session=browser_session)
        
        try:
            poll_id = polling_service.start_polling(
                agent_id=agent_id,
                platform_profile=platform_profile,
                callback=polling_callback,
                browser_session=browser_session
            )
            
            with self._lock:
                monitor_state.poll_id = poll_id
            
            if poll_id:
                logger.info(f"[ChatEventDispatcher] Started polling for {platform_id}")
        except Exception as e:
            logger.error(f"[ChatEventDispatcher] Polling start failed: {e}")
        
        logger.info(
            f"[ChatEventDispatcher] Started monitoring {platform_id} "
            f"(monitor_id={monitor_id[:8]}, cdp={len(monitor_state.cdp_subscription_ids)}, "
            f"polling={'yes' if monitor_state.poll_id else 'no'})"
        )
        
        return monitor_id
    
    def stop_monitoring(self, monitor_id: str) -> bool:
        """
        Stop a monitoring instance.
        
        Args:
            monitor_id: Monitoring instance ID
        
        Returns:
            True if stopped, False if not found
        """
        with self._lock:
            monitor_state = self._monitors.get(monitor_id)
            if not monitor_state:
                return False
            
            monitor_state.is_active = False
        
        # Unsubscribe from CDP events
        if monitor_state.cdp_subscription_ids:
            try:
                count = unsubscribe_all(monitor_state.cdp_subscription_ids)
                logger.debug(f"[ChatEventDispatcher] Unsubscribed from {count} CDP event(s)")
            except Exception as e:
                logger.error(f"[ChatEventDispatcher] CDP unsubscribe failed: {e}")
        
        # Stop polling
        if monitor_state.poll_id:
            try:
                polling_service = get_polling_service()
                polling_service.stop_polling(monitor_state.poll_id)
                logger.debug("[ChatEventDispatcher] Stopped polling")
            except Exception as e:
                logger.error(f"[ChatEventDispatcher] Polling stop failed: {e}")
        
        with self._lock:
            self._monitors.pop(monitor_id, None)
        
        logger.info(
            f"[ChatEventDispatcher] Stopped monitoring {monitor_state.platform_id} "
            f"(events={monitor_state.event_count}, cdp={monitor_state.cdp_event_count}, "
            f"poll={monitor_state.poll_event_count}, dupes={monitor_state.duplicate_count})"
        )
        
        return True
    
    def get_stats(self, monitor_id: str) -> Optional[dict]:
        """Get monitoring statistics."""
        with self._lock:
            monitor_state = self._monitors.get(monitor_id)
            if not monitor_state:
                return None
            
            return {
                'monitor_id': monitor_id,
                'platform_id': monitor_state.platform_id,
                'is_active': monitor_state.is_active,
                'event_count': monitor_state.event_count,
                'cdp_event_count': monitor_state.cdp_event_count,
                'poll_event_count': monitor_state.poll_event_count,
                'duplicate_count': monitor_state.duplicate_count,
                'cdp_subscriptions': len(monitor_state.cdp_subscription_ids),
                'polling_active': monitor_state.poll_id is not None,
                'time_since_last_event': time.time() - monitor_state.last_event_time
            }
    
    def _handle_event(
        self,
        monitor_id: str,
        event: dict,
        source: str,
        browser_session = None
    ):
        """
        Handle an event from CDP or polling.
        
        Args:
            monitor_id: Monitor instance ID
            event: Event dict
            source: 'cdp' or 'polling'
            browser_session: Optional browser session for chat ID extraction
        """
        with self._lock:
            monitor_state = self._monitors.get(monitor_id)
            if not monitor_state or not monitor_state.is_active:
                return
        
        # Extract chat ID
        chat_id = None
        try:
            if source == 'cdp':
                # Extract from event payload
                chat_id = extract_chat_id_from_event(
                    event_params=event,
                    platform_profile=monitor_state.platform_profile,
                    browser_session=browser_session
                )
            else:
                # Extract from current browser state
                if browser_session:
                    chat_id = extract_chat_id_from_browser(
                        browser_session=browser_session,
                        platform_profile=monitor_state.platform_profile
                    )
        except Exception as e:
            logger.error(f"[ChatEventDispatcher] Chat ID extraction failed: {e}")
        
        # Create event hash for deduplication
        event_hash = self._compute_event_hash(event, chat_id)
        
        with self._lock:
            # Check for duplicate
            if event_hash in monitor_state.seen_message_hashes:
                monitor_state.duplicate_count += 1
                logger.debug(
                    f"[ChatEventDispatcher] Duplicate event ignored "
                    f"(hash={event_hash[:8]}, source={source})"
                )
                return
            
            # Record event
            monitor_state.seen_message_hashes.add(event_hash)
            monitor_state.event_count += 1
            monitor_state.last_event_time = time.time()
            
            if source == 'cdp':
                monitor_state.cdp_event_count += 1
            else:
                monitor_state.poll_event_count += 1
            
            # Limit hash cache size
            if len(monitor_state.seen_message_hashes) > 1000:
                # Remove oldest half
                to_remove = list(monitor_state.seen_message_hashes)[:500]
                for h in to_remove:
                    monitor_state.seen_message_hashes.discard(h)
        
        # Enrich event with extracted data
        enriched_event = {
            **event,
            'chat_id': chat_id,
            'platform_id': monitor_state.platform_id,
            'source': source,
            'monitor_id': monitor_id,
            'event_hash': event_hash
        }
        
        logger.info(
            f"[ChatEventDispatcher] New message detected via {source} "
            f"(platform={monitor_state.platform_id}, chat_id={chat_id or 'unknown'})"
        )
        
        # Trigger callback
        try:
            monitor_state.on_new_message(enriched_event)
        except Exception as e:
            logger.error(f"[ChatEventDispatcher] Callback error: {e}")
    
    def _compute_event_hash(self, event: dict, chat_id: Optional[str]) -> str:
        """Compute hash for event deduplication."""
        import hashlib
        
        # Use chat_id + timestamp + event type for hash
        hash_parts = [
            str(chat_id or ''),
            str(event.get('timestamp', '')),
            str(event.get('type', '')),
            str(event.get('event_method', '')),
            str(event.get('snapshot_hash', ''))
        ]
        
        hash_str = '|'.join(hash_parts)
        return hashlib.md5(hash_str.encode('utf-8')).hexdigest()
    
    def stop_all(self) -> int:
        """Stop all monitoring instances."""
        with self._lock:
            monitor_ids = list(self._monitors.keys())
        
        count = 0
        for monitor_id in monitor_ids:
            if self.stop_monitoring(monitor_id):
                count += 1
        
        logger.info(f"[ChatEventDispatcher] Stopped all monitoring ({count} instances)")
        return count


# ==================== Singleton ====================

_instance: Optional[ChatEventDispatcher] = None
_instance_lock = threading.Lock()


def get_chat_event_dispatcher() -> ChatEventDispatcher:
    """Get or create singleton ChatEventDispatcher instance."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = ChatEventDispatcher()
    return _instance
