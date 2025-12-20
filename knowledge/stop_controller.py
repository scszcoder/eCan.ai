"""
Stop Controller for LightRAG Processing

Provides a thread-safe mechanism to request and check stop status
for document processing operations.

This controller is used by:
- document_routes_custom.py: Check before processing files
- advanced_chunker.py: Check during chunking operations
- operate_custom.py: Cancel extraction tasks
"""

import asyncio
import threading
from typing import Optional
from utils.logger_helper import logger_helper as logger


class StopController:
    """
    Thread-safe stop controller for LightRAG processing.
    
    Provides mechanisms to:
    1. Request stop for all processing operations
    2. Check if stop has been requested
    3. Reset stop status for new operations
    4. Cancel running asyncio tasks
    """
    
    def __init__(self):
        self._stop_requested = False
        self._lock = threading.Lock()
        self._async_lock: Optional[asyncio.Lock] = None
        logger.debug("[StopController] Initialized")
    
    def _get_async_lock(self) -> asyncio.Lock:
        """Get or create async lock for the current event loop"""
        if self._async_lock is None:
            self._async_lock = asyncio.Lock()
        return self._async_lock
    
    def request_stop(self) -> None:
        """
        Request stop for all processing operations.
        Thread-safe method that can be called from any thread.
        """
        with self._lock:
            if not self._stop_requested:
                self._stop_requested = True
                logger.info("[StopController] 🛑 Stop requested")
    
    def is_stop_requested(self) -> bool:
        """
        Check if stop has been requested.
        Thread-safe method that can be called from any thread.
        
        Returns:
            bool: True if stop has been requested
        """
        with self._lock:
            return self._stop_requested
    
    def reset(self) -> None:
        """
        Reset stop status to allow new operations.
        Should be called before starting a new batch of operations.
        """
        with self._lock:
            if self._stop_requested:
                self._stop_requested = False
                logger.info("[StopController] ✅ Stop status reset")
    
    async def async_request_stop(self) -> None:
        """
        Async version of request_stop.
        Also cancels all registered extraction tasks.
        
        Note: For LLM calls in progress, the cancellation will take effect at the next
        await point. Long-running HTTP requests (like Ollama) may need to complete or
        timeout before the cancellation is fully processed.
        """
        self.request_stop()
        
        # Cancel extraction tasks from operate_custom
        try:
            from operate_custom import cancel_all_extraction_tasks
            cancelled_count = await cancel_all_extraction_tasks()
            logger.info(f"[StopController] Cancelled {cancelled_count} extraction tasks")
        except ImportError:
            logger.debug("[StopController] operate_custom not available for task cancellation")
        except Exception as e:
            logger.warning(f"[StopController] Error cancelling extraction tasks: {e}")
    
    async def async_is_stop_requested(self) -> bool:
        """
        Async version of is_stop_requested.
        """
        return self.is_stop_requested()
    
    async def async_reset(self) -> None:
        """
        Async version of reset.
        """
        self.reset()


# Global singleton instance
_stop_controller: Optional[StopController] = None
_controller_lock = threading.Lock()


def get_stop_controller() -> StopController:
    """
    Get the global StopController singleton instance.
    Thread-safe lazy initialization.
    
    Returns:
        StopController: The global stop controller instance
    """
    global _stop_controller
    
    if _stop_controller is None:
        with _controller_lock:
            # Double-check locking pattern
            if _stop_controller is None:
                _stop_controller = StopController()
                logger.info("[StopController] Global instance created")
    
    return _stop_controller


def request_stop() -> None:
    """Convenience function to request stop"""
    get_stop_controller().request_stop()


def is_stop_requested() -> bool:
    """Convenience function to check stop status"""
    return get_stop_controller().is_stop_requested()


def reset_stop() -> None:
    """Convenience function to reset stop status"""
    get_stop_controller().reset()
