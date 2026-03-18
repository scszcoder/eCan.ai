"""
Intelligent Polling Service - Adaptive DOM polling for platforms without reliable CDP events.

Implements smart polling with:
- Adaptive frequency (fast when active, slow when idle)
- DOM snapshot comparison for change detection
- Automatic deduplication with event-based detection
- Pause/resume when workers are processing

Usage:
    service = get_polling_service()
    poll_id = service.start_polling(
        agent_id="...",
        platform_profile=profile,
        callback=on_message_detected
    )
    # Later:
    service.stop_polling(poll_id)
"""

import asyncio
import hashlib
import threading
import time
import uuid
from typing import Callable, Dict, Optional, Any, List
from dataclasses import dataclass, field

from utils.logger_helper import logger_helper as logger


@dataclass
class PollState:
    """State for a single polling instance."""
    poll_id: str
    agent_id: str
    platform_id: str
    callback: Callable
    interval_ms: int
    idle_interval_ms: int
    max_interval_ms: int
    snapshot_selector: str
    change_detection: str
    
    # Runtime state
    is_running: bool = True
    is_paused: bool = False
    last_snapshot_hash: Optional[str] = None
    last_change_time: float = field(default_factory=time.time)
    poll_count: int = 0
    change_count: int = 0
    current_interval_ms: int = 0
    
    def __post_init__(self):
        if self.current_interval_ms == 0:
            self.current_interval_ms = self.interval_ms


class PollingService:
    """Manages adaptive polling for chat message detection."""
    
    def __init__(self):
        self._polls: Dict[str, PollState] = {}
        self._threads: Dict[str, threading.Thread] = {}
        self._lock = threading.Lock()
        logger.info("[PollingService] Initialized")
    
    def start_polling(
        self,
        agent_id: str,
        platform_profile: dict,
        callback: Callable[[dict], None],
        browser_session = None
    ) -> str:
        """
        Start polling for a platform.
        
        Args:
            agent_id: Agent ID for this polling instance
            platform_profile: Platform profile dict
            callback: Function to call when changes detected, receives event dict
            browser_session: Optional browser session for DOM access
        
        Returns:
            poll_id for managing this polling instance
        """
        polling_config = platform_profile.get('polling_config', {})
        
        if not polling_config.get('enabled', True):
            logger.info(f"[PollingService] Polling disabled for {platform_profile.get('platform_id')}")
            return ""
        
        poll_id = str(uuid.uuid4())
        platform_id = platform_profile.get('platform_id', 'unknown')
        
        poll_state = PollState(
            poll_id=poll_id,
            agent_id=agent_id,
            platform_id=platform_id,
            callback=callback,
            interval_ms=polling_config.get('interval_ms', 3000),
            idle_interval_ms=polling_config.get('idle_interval_ms', 5000),
            max_interval_ms=polling_config.get('max_interval_ms', 10000),
            snapshot_selector=polling_config.get('snapshot_selector', 'body'),
            change_detection=polling_config.get('change_detection', 'dom_hash')
        )
        
        with self._lock:
            self._polls[poll_id] = poll_state
        
        # Start polling thread
        thread = threading.Thread(
            target=self._poll_loop,
            args=(poll_id, browser_session),
            daemon=True,
            name=f"poll-{platform_id}-{poll_id[:8]}"
        )
        
        with self._lock:
            self._threads[poll_id] = thread
        
        thread.start()
        
        logger.info(
            f"[PollingService] Started polling for {platform_id} "
            f"(interval={poll_state.interval_ms}ms, poll_id={poll_id[:8]})"
        )
        
        return poll_id
    
    def stop_polling(self, poll_id: str) -> bool:
        """
        Stop a polling instance.
        
        Args:
            poll_id: Polling instance ID
        
        Returns:
            True if stopped, False if not found
        """
        with self._lock:
            poll_state = self._polls.get(poll_id)
            if not poll_state:
                return False
            
            poll_state.is_running = False
        
        # Wait for thread to finish (with timeout)
        thread = self._threads.get(poll_id)
        if thread and thread.is_alive():
            thread.join(timeout=2.0)
        
        with self._lock:
            self._polls.pop(poll_id, None)
            self._threads.pop(poll_id, None)
        
        logger.info(f"[PollingService] Stopped polling {poll_id[:8]}")
        return True
    
    def pause_polling(self, poll_id: str) -> bool:
        """Temporarily pause polling (e.g., when worker is processing)."""
        with self._lock:
            poll_state = self._polls.get(poll_id)
            if poll_state:
                poll_state.is_paused = True
                logger.debug(f"[PollingService] Paused polling {poll_id[:8]}")
                return True
        return False
    
    def resume_polling(self, poll_id: str) -> bool:
        """Resume paused polling."""
        with self._lock:
            poll_state = self._polls.get(poll_id)
            if poll_state:
                poll_state.is_paused = False
                logger.debug(f"[PollingService] Resumed polling {poll_id[:8]}")
                return True
        return False
    
    def adjust_frequency(self, poll_id: str, interval_ms: int) -> bool:
        """Manually adjust polling frequency."""
        with self._lock:
            poll_state = self._polls.get(poll_id)
            if poll_state:
                poll_state.current_interval_ms = max(
                    poll_state.interval_ms,
                    min(interval_ms, poll_state.max_interval_ms)
                )
                logger.debug(
                    f"[PollingService] Adjusted frequency for {poll_id[:8]} "
                    f"to {poll_state.current_interval_ms}ms"
                )
                return True
        return False
    
    def get_stats(self, poll_id: str) -> Optional[dict]:
        """Get polling statistics."""
        with self._lock:
            poll_state = self._polls.get(poll_id)
            if not poll_state:
                return None
            
            return {
                'poll_id': poll_id,
                'platform_id': poll_state.platform_id,
                'is_running': poll_state.is_running,
                'is_paused': poll_state.is_paused,
                'poll_count': poll_state.poll_count,
                'change_count': poll_state.change_count,
                'current_interval_ms': poll_state.current_interval_ms,
                'time_since_last_change': time.time() - poll_state.last_change_time
            }
    
    def _poll_loop(self, poll_id: str, browser_session):
        """Main polling loop (runs in separate thread)."""
        while True:
            with self._lock:
                poll_state = self._polls.get(poll_id)
                if not poll_state or not poll_state.is_running:
                    break
                
                is_paused = poll_state.is_paused
                interval_ms = poll_state.current_interval_ms
            
            # Sleep for interval
            time.sleep(interval_ms / 1000.0)
            
            if is_paused:
                continue
            
            # Perform poll
            try:
                self._do_poll(poll_id, browser_session)
            except Exception as e:
                logger.error(f"[PollingService] Poll error for {poll_id[:8]}: {e}")
        
        logger.debug(f"[PollingService] Poll loop ended for {poll_id[:8]}")
    
    def _do_poll(self, poll_id: str, browser_session):
        """Perform a single poll check."""
        with self._lock:
            poll_state = self._polls.get(poll_id)
            if not poll_state:
                return
            
            poll_state.poll_count += 1
        
        # Get DOM snapshot
        snapshot = self._get_snapshot(browser_session, poll_state.snapshot_selector)
        if not snapshot:
            return
        
        # Compute hash
        snapshot_hash = hashlib.md5(snapshot.encode('utf-8')).hexdigest()
        
        with self._lock:
            poll_state = self._polls.get(poll_id)
            if not poll_state:
                return
            
            # Check if changed
            if poll_state.last_snapshot_hash is None:
                # First poll, just store hash
                poll_state.last_snapshot_hash = snapshot_hash
                logger.debug(f"[PollingService] Initial snapshot for {poll_id[:8]}")
                return
            
            if snapshot_hash != poll_state.last_snapshot_hash:
                # Change detected!
                poll_state.change_count += 1
                poll_state.last_snapshot_hash = snapshot_hash
                poll_state.last_change_time = time.time()
                
                # Speed up polling (activity detected)
                poll_state.current_interval_ms = poll_state.interval_ms
                
                logger.info(
                    f"[PollingService] Change detected for {poll_state.platform_id} "
                    f"(poll #{poll_state.poll_count}, change #{poll_state.change_count})"
                )
                
                # Trigger callback
                try:
                    event = {
                        'type': 'polling_change',
                        'platform_id': poll_state.platform_id,
                        'poll_id': poll_id,
                        'change_count': poll_state.change_count,
                        'snapshot_hash': snapshot_hash,
                        'timestamp': int(time.time() * 1000)
                    }
                    poll_state.callback(event)
                except Exception as e:
                    logger.error(f"[PollingService] Callback error: {e}")
            else:
                # No change, slow down polling (idle)
                time_since_change = time.time() - poll_state.last_change_time
                
                if time_since_change > 30:  # 30 seconds idle
                    # Gradually increase interval
                    new_interval = min(
                        poll_state.current_interval_ms + 500,
                        poll_state.max_interval_ms
                    )
                    if new_interval != poll_state.current_interval_ms:
                        poll_state.current_interval_ms = new_interval
                        logger.debug(
                            f"[PollingService] Slowed polling to {new_interval}ms "
                            f"(idle for {time_since_change:.0f}s)"
                        )
    
    def _get_snapshot(self, browser_session, selector: str) -> Optional[str]:
        """Get DOM snapshot from browser session."""
        if not browser_session:
            return None
        
        try:
            # Try to execute JavaScript to get element HTML
            if hasattr(browser_session, 'execute_script'):
                script = f"""
                const elem = document.querySelector('{selector}');
                return elem ? elem.innerHTML : null;
                """
                result = browser_session.execute_script(script)
                return result
            
            # Fallback: try to get full page HTML
            if hasattr(browser_session, 'get_page_source'):
                return browser_session.get_page_source()
            
            return None
            
        except Exception as e:
            logger.debug(f"[PollingService] Failed to get snapshot: {e}")
            return None
    
    def stop_all(self) -> int:
        """Stop all polling instances."""
        with self._lock:
            poll_ids = list(self._polls.keys())
        
        count = 0
        for poll_id in poll_ids:
            if self.stop_polling(poll_id):
                count += 1
        
        logger.info(f"[PollingService] Stopped all polling ({count} instances)")
        return count


# ==================== Singleton ====================

_instance: Optional[PollingService] = None
_instance_lock = threading.Lock()


def get_polling_service() -> PollingService:
    """Get or create singleton PollingService instance."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = PollingService()
    return _instance
