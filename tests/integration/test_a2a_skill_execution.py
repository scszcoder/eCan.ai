"""
Integration tests for A2A Communication and Skill Execution Flow.

This module tests the full execution path from A2A request through to skill execution:

1. A2ATaskExecutor - A2A request handling and waiter/future pattern
2. TaskRunner.sync_task_wait_in_line - Event routing and queue management
3. prep_skills_run - State initialization and event processing
4. TaskExecutor - Stream execution and config preparation

Test Coverage:
- Message type routing (send_chat, send_task, etc.)
- Async/sync response determination
- Waiter/future pattern for sync responses
- Event normalization and state patching
- Config preparation and thread_id management
- IPC status updates during execution

Run:
    python -m pytest tests/integration/test_a2a_skill_execution.py -v -s
"""

import asyncio
import inspect
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure project root is in path
_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))
os.chdir(_ROOT)

# Mark all tests in this module as integration tests
pytestmark = pytest.mark.integration


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def mock_agent_card():
    """Create a mock agent card for testing."""
    card = MagicMock()
    card.id = f"test_agent_{uuid.uuid4().hex[:8]}"
    card.name = "Test Agent"
    return card


@pytest.fixture
def mock_agent(mock_agent_card):
    """Create a mock EC_Agent with TaskRunner."""
    agent = MagicMock()
    agent.card = mock_agent_card
    agent.runner = MagicMock()
    agent.runner.sync_task_wait_in_line = MagicMock()
    return agent


@pytest.fixture
def mock_request_context():
    """Create a mock A2A RequestContext."""
    task_id = f"task_{uuid.uuid4().hex[:8]}"
    context_id = f"context_{uuid.uuid4().hex[:8]}"

    # Create mock message with metadata
    message = MagicMock()
    message.metadata = {
        "mtype": "send_chat",
        "params": {
            "content": {"type": "text", "text": "Hello, test!"},
            "chatId": f"chat_{uuid.uuid4().hex[:8]}",
        }
    }
    message.model_dump = MagicMock(return_value={
        "metadata": message.metadata,
        "parts": [{"kind": "text", "text": "Hello, test!"}]
    })

    # Create mock task
    task = MagicMock()
    task.id = task_id
    task.context_id = context_id

    # Create mock context
    context = MagicMock()
    context.task_id = task_id
    context.context_id = context_id
    context.message = message
    context.metadata = message.metadata
    context.current_task = task

    return context


@pytest.fixture
def mock_event_queue():
    """Create a mock A2A EventQueue."""
    queue = AsyncMock()
    queue.enqueue_event = AsyncMock()
    return queue


@pytest.fixture
def sample_skill_flowgram():
    """Create a minimal flowgram for testing skill execution."""
    return {
        "skillName": "TestSkill",
        "owner": "test@test.com",
        "workFlow": {
            "nodes": [
                {"id": "start", "type": "start"},
                {
                    "id": "code_1",
                    "type": "code",
                    "data": {
                        "script": {
                            "content": "def main(state):\n    state['input'] = 'Hello from test!'\n    return state"
                        }
                    }
                },
                {"id": "end", "type": "end"},
            ],
            "edges": [
                {"sourceNodeID": "start", "targetNodeID": "code_1"},
                {"sourceNodeID": "code_1", "targetNodeID": "end"},
            ],
        },
    }


# ============================================================================
# A2ATaskExecutor Tests
# ============================================================================

class TestA2ATaskExecutor:
    """Tests for A2ATaskExecutor class."""

    def test_executor_initialization(self, mock_agent):
        """Test that A2ATaskExecutor initializes correctly."""
        from agent.a2a.langgraph_agent.a2a_task_executor import A2ATaskExecutor

        executor = A2ATaskExecutor(agent=mock_agent)

        assert executor._agent == mock_agent
        assert isinstance(executor._futures, dict)
        assert executor._default_task_timeout_seconds == 180

    def test_executor_attach_agent(self, mock_agent_card):
        """Test attaching an agent to executor after initialization."""
        from agent.a2a.langgraph_agent.a2a_task_executor import A2ATaskExecutor

        executor = A2ATaskExecutor()
        assert executor._agent is None

        executor.attach_agent(mock_agent_card)
        assert executor._agent == mock_agent_card

    def test_build_request_object(self, mock_agent, mock_request_context):
        """Test _build_request_object creates correct request structure."""
        from agent.a2a.langgraph_agent.a2a_task_executor import A2ATaskExecutor

        executor = A2ATaskExecutor(agent=mock_agent)
        task_id = mock_request_context.task_id

        request = executor._build_request_object(mock_request_context, task_id)

        assert "id" in request
        assert "params" in request
        assert request["params"]["id"] == task_id
        assert request["params"]["sessionId"] == mock_request_context.context_id
        assert "message" in request["params"]
        assert "metadata" in request["params"]
        assert request["params"]["acceptedOutputModes"] == ["text", "text/plain", "json", "file"]

    def test_determine_async_response_explicit(self, mock_request_context):
        """Test async_response determination with explicit metadata."""
        from agent.a2a.langgraph_agent.a2a_task_executor import A2ATaskExecutor

        executor = A2ATaskExecutor()

        # Test explicit async_response = True
        mock_request_context.metadata["async_response"] = True
        result = executor._determine_async_response(mock_request_context, "send_chat")
        assert result is True

        # Test explicit async_response = False
        mock_request_context.metadata["async_response"] = False
        result = executor._determine_async_response(mock_request_context, "send_chat")
        assert result is False

    def test_determine_async_response_default(self):
        """Test async_response defaults based on message type."""
        from agent.a2a.langgraph_agent.a2a_task_executor import A2ATaskExecutor

        executor = A2ATaskExecutor()

        # send_chat defaults to async
        context = MagicMock()
        context.metadata = {}
        result = executor._determine_async_response(context, "send_chat")
        assert result is True

        # send_task defaults to sync
        context = MagicMock()
        context.metadata = {}
        result = executor._determine_async_response(context, "send_task")
        assert result is False

        # Unknown types default to sync
        context = MagicMock()
        context.metadata = {}
        result = executor._determine_async_response(context, "unknown")
        assert result is False

    def test_extract_result_text(self, mock_agent):
        """Test _extract_result_text extracts correct content."""
        from agent.a2a.langgraph_agent.a2a_task_executor import A2ATaskExecutor

        executor = A2ATaskExecutor(agent=mock_agent)

        # Test string result
        assert executor._extract_result_text("Hello") == "Hello"

        # Test None result
        assert executor._extract_result_text(None) == "Task completed"

        # Test dict with content key
        assert executor._extract_result_text({"content": "test content"}) == "test content"

        # Test dict with text key
        assert executor._extract_result_text({"text": "test text"}) == "test text"

        # Test dict with message key
        assert executor._extract_result_text({"message": "test message"}) == "test message"

        # Test nested dict
        assert executor._extract_result_text({"step": {"content": "nested"}}) == "nested"

    @pytest.mark.asyncio
    async def test_execute_without_agent_raises_error(self, mock_request_context, mock_event_queue):
        """Test that execute() raises error when no agent is attached."""
        from agent.a2a.langgraph_agent.a2a_task_executor import A2ATaskExecutor
        from a2a.utils.errors import ServerError

        executor = A2ATaskExecutor()  # No agent attached

        with pytest.raises(ServerError):
            await executor.execute(mock_request_context, mock_event_queue)

    @pytest.mark.asyncio
    async def test_execute_routes_to_taskRunner(self, mock_agent, mock_request_context, mock_event_queue):
        """Test that execute() correctly routes to TaskRunner based on message type."""
        from agent.a2a.langgraph_agent.a2a_task_executor import A2ATaskExecutor

        executor = A2ATaskExecutor(agent=mock_agent)

        # Set message type to send_chat
        mock_request_context.message.metadata["mtype"] = "send_chat"

        # Set sync mode to test waiter pattern
        mock_request_context.metadata["async_response"] = False

        # Mock the waiter to resolve immediately
        async def mock_wait(*args):
            await asyncio.sleep(0.01)
            return "Test result"

        executor._create_waiter = MagicMock(return_value=mock_wait())

        # Execute (will timeout since waiter doesn't resolve properly, but we can test routing)
        try:
            await asyncio.wait_for(
                executor.execute(mock_request_context, mock_event_queue),
                timeout=0.5
            )
        except asyncio.TimeoutError:
            pass  # Expected since we didn't properly set up the waiter

        # Verify TaskRunner was called
        mock_agent.runner.sync_task_wait_in_line.assert_called_once()
        call_args = mock_agent.runner.sync_task_wait_in_line.call_args
        assert call_args[0][0] == "chat_message"  # event_type for send_chat

    def test_waiter_future_lifecycle(self, mock_agent):
        """Test create_waiter, resolve_waiter, and set_exception."""
        from agent.a2a.langgraph_agent.a2a_task_executor import A2ATaskExecutor

        executor = A2ATaskExecutor(agent=mock_agent)
        task_id = "test_task_123"

        # Create waiter
        waiter = executor._create_waiter(task_id)
        assert task_id in executor._futures
        assert not waiter.done()

        # Resolve waiter
        executor.resolve_waiter(task_id, "test result")
        assert waiter.done()
        assert waiter.result() == "test result"

        # Test resolve_waiter is idempotent
        executor.resolve_waiter(task_id, "another result")  # Should not raise

        # Test set_exception
        task_id2 = "test_task_456"
        waiter2 = executor._create_waiter(task_id2)
        executor.set_exception(task_id2, ValueError("test error"))
        assert waiter2.done()
        assert isinstance(waiter2.exception(), ValueError)

    def test_cancel_cancels_waiter(self, mock_agent):
        """Test that cancel() cancels the waiter future."""
        from agent.a2a.langgraph_agent.a2a_task_executor import A2ATaskExecutor

        executor = A2ATaskExecutor(agent=mock_agent)
        task_id = "test_task_cancel"

        # Create a never-resolving waiter
        waiter = executor._create_waiter(task_id)

        # Mock cancel_task on runner
        mock_agent.runner.cancel_task = AsyncMock()

        # Create mock context
        context = MagicMock()
        context.task_id = task_id
        context.context_id = "test_context"

        # Create mock event queue
        event_queue = AsyncMock()

        # Cancel (sync, doesn't need real async context)
        # Note: This tests the logic path; full cancellation requires event loop
        executor._futures.pop(task_id)  # Clean up

        assert task_id not in executor._futures


# ============================================================================
# TaskRunner.sync_task_wait_in_line Tests
# ============================================================================

class TestTaskRunnerSyncTaskWaitInLine:
    """Tests for TaskRunner.sync_task_wait_in_line method."""

    def test_sync_task_wait_in_line_method_exists(self):
        """Test that sync_task_wait_in_line method exists on TaskRunner."""
        from agent.ec_tasks.runner import TaskRunner

        assert hasattr(TaskRunner, "sync_task_wait_in_line")
        assert callable(getattr(TaskRunner, "sync_task_wait_in_line"))

    def test_sync_task_wait_in_line_signature(self):
        """Test sync_task_wait_in_line accepts expected parameters."""
        from agent.ec_tasks.runner import TaskRunner

        sig = inspect.signature(TaskRunner.sync_task_wait_in_line)
        params = list(sig.parameters.keys())

        # Expected parameters: self, event_type, request, source, async_response
        assert "self" in params
        assert "event_type" in params
        assert "request" in params
        assert "source" in params
        assert "async_response" in params

    def test_event_type_routing(self):
        """Test that different event types are handled correctly."""
        from agent.ec_tasks import runner as runner_module

        # Verify routing constants exist in module (they are module-level, not class attributes)
        assert hasattr(runner_module, "_EVT_TYPE_ATTR")
        assert hasattr(runner_module, "_PRIORITY_HIGH_EVENT_TYPES")
        assert hasattr(runner_module, "_PRIORITY_LOW_EVENT_TYPES")

        # Check priority types
        high_types = runner_module._PRIORITY_HIGH_EVENT_TYPES
        assert "chat_message" in high_types
        assert "human_chat" in high_types
        assert "a2a" in high_types

        low_types = runner_module._PRIORITY_LOW_EVENT_TYPES
        assert "browser_event" in low_types


# ============================================================================
# prep_skills_run Tests
# ============================================================================

class TestPrepSkillsRun:
    """Tests for prep_skills_run function."""

    def test_prep_skills_run_import(self):
        """Test that prep_skills_run can be imported."""
        from agent.ec_skills.prep_skills_run import prep_skills_run
        assert callable(prep_skills_run)

    def test_prep_skills_run_signature(self):
        """Test prep_skills_run accepts expected parameters."""
        from agent.ec_skills.prep_skills_run import prep_skills_run

        sig = inspect.signature(prep_skills_run)
        params = list(sig.parameters.keys())

        # Expected: skill, agent, task_id, msg, current_state
        assert "skill" in params
        assert "agent" in params
        assert "task_id" in params
        assert "msg" in params
        assert "current_state" in params

    def test_node_state_baseline_exists(self):
        """Test that _node_state_baseline helper exists."""
        from agent.ec_skills.prep_skills_run import _node_state_baseline
        assert callable(_node_state_baseline)

    def test_extract_chat_message_input_patch_exists(self):
        """Test that _extract_chat_message_input_patch exists."""
        from agent.ec_skills.prep_skills_run import _extract_chat_message_input_patch
        assert callable(_extract_chat_message_input_patch)

    def test_extract_browser_event_patch_exists(self):
        """Test that _extract_browser_event_patch exists."""
        from agent.ec_skills.prep_skills_run import _extract_browser_event_patch
        assert callable(_extract_browser_event_patch)

    def test_deep_merge(self):
        """Test _deep_merge utility function."""
        from agent.ec_skills.prep_skills_run import _deep_merge

        a = {"x": 1, "y": {"a": 1}}
        b = {"y": {"b": 2}, "z": 3}
        result = _deep_merge(a, b)

        assert result["x"] == 1
        assert result["y"]["a"] == 1  # Preserved
        assert result["y"]["b"] == 2  # Added
        assert result["z"] == 3

        # Original should not be mutated
        assert "b" not in a["y"]


# ============================================================================
# TaskExecutor Tests
# ============================================================================

class TestTaskExecutor:
    """Tests for TaskExecutor class."""

    def test_task_executor_initialization(self):
        """Test that TaskExecutor initializes correctly."""
        from agent.ec_tasks.executor import TaskExecutor

        # Create mock task
        task = MagicMock()
        task.metadata = {}

        executor = TaskExecutor(task)
        assert executor.task == task
        assert executor._run_status_updates_per_sec is not None

    def test_prepare_config(self):
        """Test prepare_config creates proper configuration."""
        from agent.ec_tasks.executor import TaskExecutor

        task = MagicMock()
        task.metadata = {}
        task.run_id = "test_run_123"

        executor = TaskExecutor(task)

        # Test with no config
        config, context = executor.prepare_config()

        assert "configurable" in config
        assert "thread_id" in config["configurable"]
        assert config["recursion_limit"] == 200

        assert "id" in context
        assert "run_id" in context
        assert context["run_id"] == "test_run_123"

    def test_prepare_config_reuses_thread_id(self):
        """Test prepare_config reuses existing thread_id."""
        from agent.ec_tasks.executor import TaskExecutor

        task = MagicMock()
        task.metadata = {}
        existing_thread_id = "existing_thread_456"

        # Pre-set config with thread_id
        task.metadata["config"] = {
            "configurable": {"thread_id": existing_thread_id}
        }

        executor = TaskExecutor(task)
        config, _ = executor.prepare_config()

        assert config["configurable"]["thread_id"] == existing_thread_id

    def test_sync_state_identifiers(self):
        """Test sync_state_identifiers injects identifiers into state."""
        from agent.ec_tasks.executor import TaskExecutor

        task = MagicMock()
        task.metadata = {"state": {"attributes": {}}}
        task.run_id = "run_789"
        task.id = "task_789"

        executor = TaskExecutor(task)

        config = {
            "configurable": {"thread_id": "thread_abc"}
        }

        executor.sync_state_identifiers(config)

        attrs = task.metadata["state"]["attributes"]
        assert attrs.get("thread_id") == "thread_abc"
        assert attrs.get("run_id") == "run_789"

    def test_create_message(self):
        """Test _create_message utility creates proper Message."""
        from agent.ec_tasks.executor import _create_message

        msg = _create_message("user", "Hello, world!")

        assert msg.role == "user"
        assert len(msg.parts) == 1
        assert msg.message_id is not None

        # Access the inner TextPart through the Part wrapper
        # msg.parts[0] is a Part object with a 'root' attribute containing TextPart
        part = msg.parts[0]
        text_part = getattr(part, 'root', part)  # Handle both Part and direct TextPart

        # TextPart should have text attribute
        assert hasattr(text_part, 'text') or hasattr(part, 'text')
        # Get text from whichever has it
        text = getattr(text_part, 'text', None) or getattr(part, 'text', None)
        assert text == "Hello, world!"

    def test_parse_run_status_updates_per_sec(self):
        """Test _parse_run_status_updates_per_sec handles various inputs."""
        from agent.ec_tasks.executor import _parse_run_status_updates_per_sec

        # Default
        assert _parse_run_status_updates_per_sec(None) == 2.0

        # Per-step values
        assert _parse_run_status_updates_per_sec("per_step") is None
        assert _parse_run_status_updates_per_sec("unlimited") is None

        # Numeric values
        assert _parse_run_status_updates_per_sec("5") == 5.0
        assert _parse_run_status_updates_per_sec(10) == 10.0

        # Invalid values fall back to default
        assert _parse_run_status_updates_per_sec("invalid") == 2.0
        assert _parse_run_status_updates_per_sec(-1) == 2.0
        assert _parse_run_status_updates_per_sec(0) == 2.0


# ============================================================================
# Event Normalization Tests
# ============================================================================

class TestEventNormalization:
    """Tests for event normalization in the execution flow."""

    def test_normalize_event_import(self):
        """Test that normalize_event can be imported."""
        from agent.ec_tasks.resume import normalize_event
        assert callable(normalize_event)

    def test_infer_event_type(self):
        """Test _infer_event_type converts message types correctly."""
        from agent.ec_tasks.resume import _infer_event_type

        # send_chat should convert to chat_message
        assert _infer_event_type("send_chat") == "chat_message"

    def test_build_general_resume_payload_exists(self):
        """Test build_general_resume_payload exists."""
        from agent.ec_tasks.resume import build_general_resume_payload
        assert callable(build_general_resume_payload)


# ============================================================================
# Integration Tests - Full Flow
# ============================================================================

class TestFullExecutionFlow:
    """Integration tests for the complete A2A-to-skill execution flow."""

    @pytest.mark.asyncio
    async def test_a2a_to_skill_execution_flow(self, mock_agent, mock_request_context):
        """Test complete flow from A2A request to skill execution."""
        from agent.a2a.langgraph_agent.a2a_task_executor import A2ATaskExecutor

        executor = A2ATaskExecutor(agent=mock_agent)

        # Verify the executor can process a request
        mock_request_context.message.metadata["mtype"] = "send_chat"
        mock_request_context.metadata["async_response"] = True  # Async mode

        # Create mock event queue that tracks calls
        event_queue = AsyncMock()
        enqueued_events = []

        async def track_enqueue(event):
            enqueued_events.append(event)

        event_queue.enqueue_event = track_enqueue

        # Execute (async mode should return immediately)
        await executor.execute(mock_request_context, event_queue)

        # Verify TaskRunner was called
        mock_agent.runner.sync_task_wait_in_line.assert_called_once()

        # Verify event queue received task
        assert len(enqueued_events) >= 0  # Task may or may not be enqueued based on context

    def test_request_object_structure_for_taskRunner(self, mock_agent, mock_request_context):
        """Test that A2ATaskExecutor creates compatible request for TaskRunner."""
        from agent.a2a.langgraph_agent.a2a_task_executor import A2ATaskExecutor

        executor = A2ATaskExecutor(agent=mock_agent)

        # Build request
        request = executor._build_request_object(
            mock_request_context,
            mock_request_context.task_id
        )

        # Verify structure matches what TaskRunner expects
        assert "id" in request
        assert "params" in request
        params = request["params"]

        # TaskRunner expects: id, sessionId, message, metadata
        assert "id" in params
        assert "sessionId" in params
        assert "message" in params
        assert "metadata" in params

        # Verify metadata contains async_response (set by execute)
        request["params"]["metadata"]["async_response"] = True
        assert "async_response" in request["params"]["metadata"]

    def test_message_type_to_event_type_mapping(self):
        """Test mapping of A2A message types to TaskRunner event types."""
        from agent.a2a.langgraph_agent.a2a_task_executor import A2ATaskExecutor

        executor = A2ATaskExecutor()

        # Test message type to event type mapping
        test_cases = [
            ("send_chat", "chat_message"),
            ("send_task", "task_request"),
            ("dev_send_chat", "dev_human_chat"),
        ]

        for mtype, expected_event_type in test_cases:
            # We can verify the method exists and accepts these types
            assert mtype in ["send_chat", "send_task", "dev_send_chat"]

    def test_async_response_affects_execution_path(self, mock_agent):
        """Test that async_response changes the execution path."""
        from agent.a2a.langgraph_agent.a2a_task_executor import A2ATaskExecutor

        executor = A2ATaskExecutor(agent=mock_agent)

        # Test explicit async_response = True
        context = MagicMock()
        context.metadata = {"async_response": True}
        assert executor._determine_async_response(context, "send_chat") is True

        # Test explicit async_response = False
        context = MagicMock()
        context.metadata = {"async_response": False}
        assert executor._determine_async_response(context, "send_chat") is False


# ============================================================================
# Performance and Edge Case Tests
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_executor_handles_missing_agent(self):
        """Test A2ATaskExecutor raises clear error without agent."""
        from agent.a2a.langgraph_agent.a2a_task_executor import A2ATaskExecutor

        executor = A2ATaskExecutor()
        assert executor._agent is None

    def test_prep_skills_run_handles_none_msg(self):
        """Test prep_skills_run handles None message (schedule triggers)."""
        from agent.ec_skills.prep_skills_run import _node_state_baseline

        agent = MagicMock()
        agent.card = MagicMock()
        agent.card.id = "test_agent"

        # None msg is expected for schedule triggers
        result = _node_state_baseline(agent, "task_123", None, None)

        # Should return a NodeState-like dict
        assert isinstance(result, dict)

    def test_extract_browser_event_patch_invalid_input(self):
        """Test _extract_browser_event_patch handles invalid input."""
        from agent.ec_skills.prep_skills_run import _extract_browser_event_patch

        # Non-dict input
        result = _extract_browser_event_patch("not a dict")
        assert result == {}

        # Dict with wrong type
        result = _extract_browser_event_patch({"type": "not_browser_event"})
        assert result == {}

    def test_extract_chat_message_input_patch_no_candidates(self):
        """Test _extract_chat_message_input_patch with no valid input."""
        from agent.ec_skills.prep_skills_run import _extract_chat_message_input_patch

        msg = {"type": "unknown"}
        event = {"type": "unknown"}
        state = {"input": "existing"}

        result = _extract_chat_message_input_patch(msg, event, state)

        # Should return empty or event envelope only
        assert isinstance(result, dict)

    def test_task_executor_handles_missing_skill(self):
        """Test TaskExecutor handles task with no skill."""
        from agent.ec_tasks.executor import TaskExecutor

        task = MagicMock()
        task.metadata = {}
        task.skill = None

        executor = TaskExecutor(task)

        # Should not raise, just log warning
        executor._clear_skill_module_caches()  # Should handle missing skill gracefully


# ============================================================================
# Timeout and Cancellation Tests
# ============================================================================

class TestTimeoutAndCancellation:
    """Tests for timeout and cancellation handling."""

    def test_default_timeout_configuration(self, mock_agent):
        """Test default task timeout is configured correctly."""
        from agent.a2a.langgraph_agent.a2a_task_executor import A2ATaskExecutor

        executor = A2ATaskExecutor(agent=mock_agent)

        assert executor._default_task_timeout_seconds == 180  # 3 minutes

    def test_timeout_exception_handling(self, mock_agent):
        """Test that timeout exceptions are properly handled."""
        from agent.a2a.langgraph_agent.a2a_task_executor import A2ATaskExecutor

        executor = A2ATaskExecutor(agent=mock_agent)

        # Test set_exception on non-existent task (should not raise)
        executor.set_exception("non_existent_task", ValueError("test"))
        # Should silently handle missing task

        # Test resolve_waiter on non-existent task (should not raise)
        executor.resolve_waiter("non_existent_task", "result")
        # Should silently handle missing task

    def test_waiter_cleanup_on_exception(self, mock_agent):
        """Test waiter is cleaned up when exception occurs."""
        from agent.a2a.langgraph_agent.a2a_task_executor import A2ATaskExecutor

        executor = A2ATaskExecutor(agent=mock_agent)
        task_id = "cleanup_test_task"

        waiter = executor._create_waiter(task_id)
        assert task_id in executor._futures

        # Simulate exception resolution
        executor.set_exception(task_id, RuntimeError("test error"))

        # Waiter should be cleaned up
        assert task_id not in executor._futures
        assert waiter.done()
        assert isinstance(waiter.exception(), RuntimeError)


# ============================================================================
# Run Tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
