"""
Tests for Pending Events System

Tests the fire-and-forget async operation tracking mechanism:
- PendingEvent model
- TimerService
- Registration and resolution utilities
- Completion gate in executor
- Callback routing
"""

import asyncio
import threading
import time
import unittest
from queue import Queue, Empty
from unittest.mock import MagicMock, patch, AsyncMock

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.ec_tasks.models import (
    ManagedTask,
    PendingEvent,
    PendingEventStatus,
)
from agent.ec_tasks.timer_service import (
    TimerService,
    TimerHandle,
    get_timer_service,
    set_timer_service,
)
from agent.ec_tasks.pending_events import (
    generate_correlation_id,
    parse_correlation_id,
    register_async_operation,
    resolve_async_operation,
    cancel_task_async_operations,
    build_callback_event,
    route_callback_to_task,
)


class TestPendingEventModel(unittest.TestCase):
    """Test PendingEvent model."""
    
    def test_create_pending_event(self):
        """Test creating a pending event."""
        event = PendingEvent(
            correlation_id="task-123:abc",
            source_node="my_tool",
            timeout_at=time.time() + 60,
            timeout_seconds=60,
        )
        
        self.assertEqual(event.correlation_id, "task-123:abc")
        self.assertEqual(event.source_node, "my_tool")
        self.assertEqual(event.status, PendingEventStatus.PENDING)
        self.assertTrue(event.is_pending())
        self.assertFalse(event.is_expired())
    
    def test_mark_completed(self):
        """Test marking event as completed."""
        event = PendingEvent(
            correlation_id="task-123:abc",
            source_node="my_tool",
            timeout_at=time.time() + 60,
            timeout_seconds=60,
        )
        
        event.mark_completed(result={"data": 123})
        
        self.assertEqual(event.status, PendingEventStatus.COMPLETED)
        self.assertEqual(event.result, {"data": 123})
        self.assertFalse(event.is_pending())
    
    def test_mark_timed_out(self):
        """Test marking event as timed out."""
        event = PendingEvent(
            correlation_id="task-123:abc",
            source_node="my_tool",
            timeout_at=time.time() + 60,
            timeout_seconds=60,
        )
        
        event.mark_timed_out()
        
        self.assertEqual(event.status, PendingEventStatus.TIMED_OUT)
        self.assertEqual(event.error, "timeout")
        self.assertFalse(event.is_pending())
    
    def test_is_expired(self):
        """Test expiration check."""
        # Create already expired event
        event = PendingEvent(
            correlation_id="task-123:abc",
            source_node="my_tool",
            timeout_at=time.time() - 1,  # Already expired
            timeout_seconds=60,
        )
        
        self.assertTrue(event.is_expired())


class TestManagedTaskPendingEvents(unittest.TestCase):
    """Test ManagedTask pending event methods."""
    
    def setUp(self):
        """Create a mock task for testing."""
        self.task = ManagedTask(
            id="task-123",
            name="test_task",
        )
    
    def test_register_pending_event(self):
        """Test registering a pending event."""
        event = self.task.register_pending_event(
            correlation_id="task-123:abc",
            source_node="my_tool",
            timeout_seconds=60,
        )
        
        self.assertIn("task-123:abc", self.task.pending_events)
        self.assertEqual(event.source_node, "my_tool")
        self.assertTrue(self.task.has_pending_events())
    
    def test_resolve_pending_event_success(self):
        """Test resolving a pending event with success."""
        self.task.register_pending_event(
            correlation_id="task-123:abc",
            source_node="my_tool",
            timeout_seconds=60,
        )
        
        event = self.task.resolve_pending_event(
            correlation_id="task-123:abc",
            result={"data": 123},
        )
        
        self.assertIsNotNone(event)
        self.assertEqual(event.status, PendingEventStatus.COMPLETED)
        self.assertEqual(event.result, {"data": 123})
        self.assertFalse(self.task.has_pending_events())
    
    def test_resolve_pending_event_error(self):
        """Test resolving a pending event with error."""
        self.task.register_pending_event(
            correlation_id="task-123:abc",
            source_node="my_tool",
            timeout_seconds=60,
        )
        
        event = self.task.resolve_pending_event(
            correlation_id="task-123:abc",
            error="timeout",
        )
        
        self.assertIsNotNone(event)
        self.assertEqual(event.status, PendingEventStatus.TIMED_OUT)
    
    def test_get_pending_events(self):
        """Test getting pending events."""
        self.task.register_pending_event("task-123:a", "tool1", 60)
        self.task.register_pending_event("task-123:b", "tool2", 60)
        
        # Resolve one
        self.task.resolve_pending_event("task-123:a", result="done")
        
        pending = self.task.get_pending_events()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].correlation_id, "task-123:b")
    
    def test_cleanup_expired_events(self):
        """Test cleaning up expired events."""
        # Register an already expired event
        event = self.task.register_pending_event(
            correlation_id="task-123:abc",
            source_node="my_tool",
            timeout_seconds=0,  # Immediate timeout
        )
        # Manually set timeout_at to past
        event.timeout_at = time.time() - 1
        
        expired = self.task.cleanup_expired_events()
        
        self.assertEqual(len(expired), 1)
        self.assertEqual(expired[0], "task-123:abc")
        self.assertFalse(self.task.has_pending_events())
    
    def test_cancel_all_pending_events(self):
        """Test cancelling all pending events."""
        self.task.register_pending_event("task-123:a", "tool1", 60)
        self.task.register_pending_event("task-123:b", "tool2", 60)
        
        cancelled = self.task.cancel_all_pending_events()
        
        self.assertEqual(len(cancelled), 2)
        self.assertFalse(self.task.has_pending_events())
        
        # Check all are marked cancelled
        for event in self.task.pending_events.values():
            self.assertEqual(event.status, PendingEventStatus.CANCELLED)


class TestTimerService(unittest.TestCase):
    """Test TimerService."""
    
    def setUp(self):
        """Create a fresh timer service for each test."""
        self.timer_service = TimerService()
    
    def tearDown(self):
        """Clean up timers."""
        self.timer_service.clear_all()
    
    def test_start_timer(self):
        """Test starting a timer."""
        callback_called = threading.Event()
        
        def callback():
            callback_called.set()
        
        handle = self.timer_service.start_timer(
            correlation_id="test-123",
            task_id="task-1",
            delay_seconds=0.1,
            callback=callback,
        )
        
        self.assertIsNotNone(handle)
        self.assertEqual(handle.correlation_id, "test-123")
        self.assertTrue(handle.is_active())
        
        # Wait for timer to fire
        callback_called.wait(timeout=1.0)
        self.assertTrue(callback_called.is_set())
    
    def test_cancel_timer(self):
        """Test cancelling a timer."""
        callback_called = threading.Event()
        
        def callback():
            callback_called.set()
        
        self.timer_service.start_timer(
            correlation_id="test-123",
            task_id="task-1",
            delay_seconds=1.0,  # Long delay
            callback=callback,
        )
        
        # Cancel before it fires
        result = self.timer_service.cancel_timer("test-123")
        self.assertTrue(result)
        
        # Wait and verify callback was not called
        time.sleep(0.2)
        self.assertFalse(callback_called.is_set())
    
    def test_cancel_all_for_task(self):
        """Test cancelling all timers for a task."""
        callbacks_called = []
        
        def make_callback(name):
            def callback():
                callbacks_called.append(name)
            return callback
        
        # Start multiple timers for same task
        self.timer_service.start_timer("a", "task-1", 1.0, make_callback("a"))
        self.timer_service.start_timer("b", "task-1", 1.0, make_callback("b"))
        self.timer_service.start_timer("c", "task-2", 1.0, make_callback("c"))
        
        # Cancel all for task-1
        count = self.timer_service.cancel_all_for_task("task-1")
        self.assertEqual(count, 2)
        
        # Verify only task-2 timer remains
        active = self.timer_service.get_active_timers()
        self.assertEqual(len(active), 1)
        self.assertIn("c", active)
    
    def test_timer_fires_callback(self):
        """Test that timer fires callback with correct data."""
        result = {}
        
        def callback():
            result["fired"] = True
        
        def on_fire(corr_id):
            result["correlation_id"] = corr_id
        
        self.timer_service.start_timer(
            correlation_id="test-123",
            task_id="task-1",
            delay_seconds=0.1,
            callback=callback,
            on_fire=on_fire,
        )
        
        time.sleep(0.3)
        
        self.assertTrue(result.get("fired"))
        self.assertEqual(result.get("correlation_id"), "test-123")


class TestCorrelationId(unittest.TestCase):
    """Test correlation ID utilities."""
    
    def test_generate_correlation_id(self):
        """Test generating correlation ID."""
        corr_id = generate_correlation_id("task-123")
        
        self.assertTrue(corr_id.startswith("task-123:"))
        self.assertGreater(len(corr_id), len("task-123:"))
    
    def test_parse_correlation_id(self):
        """Test parsing correlation ID."""
        task_id, unique = parse_correlation_id("task-123:abc-def")
        
        self.assertEqual(task_id, "task-123")
        self.assertEqual(unique, "abc-def")
    
    def test_parse_invalid_correlation_id(self):
        """Test parsing invalid correlation ID."""
        task_id, unique = parse_correlation_id("invalid")
        
        self.assertIsNone(task_id)
        self.assertIsNone(unique)
    
    def test_parse_empty_correlation_id(self):
        """Test parsing empty correlation ID."""
        task_id, unique = parse_correlation_id("")
        
        self.assertIsNone(task_id)
        self.assertIsNone(unique)


class TestRegisterAsyncOperation(unittest.TestCase):
    """Test register_async_operation."""
    
    def setUp(self):
        """Create mock task and timer service."""
        self.task = ManagedTask(
            id="task-123",
            name="test_task",
        )
        self.timer_service = TimerService()
    
    def tearDown(self):
        """Clean up."""
        self.timer_service.clear_all()
    
    def test_register_async_operation(self):
        """Test registering an async operation."""
        corr_id = register_async_operation(
            task=self.task,
            source_node="my_tool",
            timeout_seconds=60,
            timer_service=self.timer_service,
        )
        
        # Check correlation ID format
        self.assertTrue(corr_id.startswith("task-123:"))
        
        # Check pending event registered
        self.assertIn(corr_id, self.task.pending_events)
        self.assertTrue(self.task.has_pending_events())
        
        # Check timer started
        active = self.timer_service.get_active_timers()
        self.assertIn(corr_id, active)
    
    def test_timeout_fires_event_to_queue(self):
        """Test that timeout fires event to task queue."""
        corr_id = register_async_operation(
            task=self.task,
            source_node="my_tool",
            timeout_seconds=0.1,  # Short timeout
            timer_service=self.timer_service,
        )
        
        # Wait for timeout
        time.sleep(0.3)
        
        # Check queue has timeout event
        try:
            event = self.task.queue.get(timeout=0.1)
            self.assertEqual(event["type"], "async_timeout")
            self.assertEqual(event["correlation_id"], corr_id)
        except Empty:
            self.fail("Expected timeout event in queue")


class TestResolveAsyncOperation(unittest.TestCase):
    """Test resolve_async_operation."""
    
    def setUp(self):
        """Create mock task and timer service."""
        self.task = ManagedTask(
            id="task-123",
            name="test_task",
        )
        self.timer_service = TimerService()
    
    def tearDown(self):
        """Clean up."""
        self.timer_service.clear_all()
    
    def test_resolve_cancels_timer(self):
        """Test that resolving cancels the timer."""
        corr_id = register_async_operation(
            task=self.task,
            source_node="my_tool",
            timeout_seconds=60,
            timer_service=self.timer_service,
        )
        
        # Verify timer is active
        self.assertIn(corr_id, self.timer_service.get_active_timers())
        
        # Resolve
        event = resolve_async_operation(
            task=self.task,
            correlation_id=corr_id,
            result={"data": 123},
            timer_service=self.timer_service,
        )
        
        # Verify timer cancelled
        self.assertNotIn(corr_id, self.timer_service.get_active_timers())
        
        # Verify event resolved
        self.assertIsNotNone(event)
        self.assertEqual(event.status, PendingEventStatus.COMPLETED)


class TestBuildCallbackEvent(unittest.TestCase):
    """Test build_callback_event."""
    
    def test_build_success_event(self):
        """Test building success callback event."""
        event = build_callback_event(
            correlation_id="task-123:abc",
            result={"data": 123},
        )
        
        self.assertEqual(event["type"], "async_callback")
        self.assertEqual(event["correlation_id"], "task-123:abc")
        self.assertEqual(event["result"], {"data": 123})
        self.assertIsNone(event["error"])
    
    def test_build_error_event(self):
        """Test building error callback event."""
        event = build_callback_event(
            correlation_id="task-123:abc",
            error="something went wrong",
        )
        
        self.assertEqual(event["type"], "async_callback")
        self.assertEqual(event["error"], "something went wrong")


class TestRouteCallbackToTask(unittest.TestCase):
    """Test route_callback_to_task."""
    
    def test_route_to_correct_task(self):
        """Test routing callback to correct task."""
        task1 = ManagedTask(id="task-1", name="task1")
        task2 = ManagedTask(id="task-2", name="task2")
        
        task_lookup = {
            "task-1": task1,
            "task-2": task2,
        }
        
        result = route_callback_to_task(
            correlation_id="task-2:abc",
            result={"data": 123},
            task_lookup=task_lookup,
        )
        
        self.assertTrue(result)
        
        # Check event in correct queue
        event = task2.queue.get(timeout=0.1)
        self.assertEqual(event["correlation_id"], "task-2:abc")
        
        # Check other queue is empty
        self.assertTrue(task1.queue.empty())
    
    def test_route_invalid_correlation_id(self):
        """Test routing with invalid correlation ID."""
        result = route_callback_to_task(
            correlation_id="invalid",
            result={"data": 123},
            task_lookup={},
        )
        
        self.assertFalse(result)
    
    def test_route_task_not_found(self):
        """Test routing when task not found."""
        result = route_callback_to_task(
            correlation_id="task-999:abc",
            result={"data": 123},
            task_lookup={"task-1": ManagedTask(id="task-1", name="task1")},
        )
        
        self.assertFalse(result)


class TestCancelTaskAsyncOperations(unittest.TestCase):
    """Test cancel_task_async_operations."""
    
    def setUp(self):
        """Create mock task and timer service."""
        self.task = ManagedTask(
            id="task-123",
            name="test_task",
        )
        self.timer_service = TimerService()
    
    def tearDown(self):
        """Clean up."""
        self.timer_service.clear_all()
    
    def test_cancel_all_operations(self):
        """Test cancelling all async operations for a task."""
        # Register multiple operations
        corr_id1 = register_async_operation(
            self.task, "tool1", 60, self.timer_service
        )
        corr_id2 = register_async_operation(
            self.task, "tool2", 60, self.timer_service
        )
        
        # Verify timers active
        self.assertEqual(len(self.timer_service.get_active_timers()), 2)
        
        # Cancel all
        count = cancel_task_async_operations(self.task, self.timer_service)
        
        self.assertEqual(count, 2)
        self.assertFalse(self.task.has_pending_events())
        self.assertEqual(len(self.timer_service.get_active_timers()), 0)


if __name__ == "__main__":
    unittest.main()
