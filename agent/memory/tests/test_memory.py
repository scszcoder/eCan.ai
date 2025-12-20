"""
Unit Tests for Agent Memory Module

Tests:
1. ActionRecord, SessionRecord, DailyReflection schemas
2. EpisodicStore - save/load sessions and reflections
3. SessionRecorder - recording steps
4. ReflectionEngine - generating reflections (with mock LLM)

Run with:
    pytest agent/memory/tests/test_memory.py -v
    
Or run directly:
    python agent/memory/tests/test_memory.py
"""

import asyncio
import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

# Add project root to path
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from agent.memory.models import (
    ActionRecord,
    SessionRecord,
    DailyReflection,
    MemoryNamespaces,
)
from agent.memory.episodic_store import EpisodicStore, SessionRecorder
from agent.memory.reflection import ReflectionEngine


class TestActionRecord(unittest.TestCase):
    """Tests for ActionRecord dataclass."""
    
    def test_create_action_record(self):
        """Test creating an ActionRecord."""
        action = ActionRecord(
            timestamp=datetime.now(),
            session_id="test_session",
            step_number=1,
            action_type="browser_action",
            action_name="click",
            action_input={"element_id": 123},
            success=True,
            url="https://example.com",
            thinking="I need to click the button",
            next_goal="Submit the form",
        )
        
        self.assertEqual(action.session_id, "test_session")
        self.assertEqual(action.step_number, 1)
        self.assertEqual(action.action_name, "click")
        self.assertTrue(action.success)
    
    def test_action_record_to_dict(self):
        """Test converting ActionRecord to dict."""
        action = ActionRecord(
            timestamp=datetime(2024, 12, 14, 10, 30, 0),
            session_id="test_session",
            step_number=1,
            action_type="browser_action",
            action_name="navigate",
            action_input={"url": "https://example.com"},
            success=True,
        )
        
        data = action.to_dict()
        
        self.assertEqual(data["session_id"], "test_session")
        self.assertEqual(data["action_name"], "navigate")
        self.assertIn("timestamp", data)
    
    def test_action_record_from_dict(self):
        """Test creating ActionRecord from dict."""
        data = {
            "timestamp": "2024-12-14T10:30:00",
            "session_id": "test_session",
            "step_number": 2,
            "action_type": "tool_call",
            "action_name": "search",
            "success": True,
        }
        
        action = ActionRecord.from_dict(data)
        
        self.assertEqual(action.session_id, "test_session")
        self.assertEqual(action.step_number, 2)
        self.assertEqual(action.action_name, "search")
    
    def test_action_record_to_text(self):
        """Test converting ActionRecord to text."""
        action = ActionRecord(
            timestamp=datetime.now(),
            session_id="test",
            step_number=1,
            action_type="browser_action",
            action_name="click",
            success=True,
            url="https://example.com",
            thinking="Click the submit button",
        )
        
        text = action.to_text()
        
        self.assertIn("Step 1", text)
        self.assertIn("click", text)
        self.assertIn("example.com", text)


class TestSessionRecord(unittest.TestCase):
    """Tests for SessionRecord dataclass."""
    
    def test_create_session_record(self):
        """Test creating a SessionRecord."""
        session = SessionRecord(
            session_id="sess_001",
            agent_id="test_agent",
            task="Navigate to example.com",
            start_time=datetime.now(),
        )
        
        self.assertEqual(session.session_id, "sess_001")
        self.assertEqual(session.agent_id, "test_agent")
        self.assertEqual(len(session.actions), 0)
    
    def test_add_action_to_session(self):
        """Test adding actions to a session."""
        session = SessionRecord(
            session_id="sess_001",
            agent_id="test_agent",
            task="Test task",
            start_time=datetime.now(),
        )
        
        action1 = ActionRecord(
            timestamp=datetime.now(),
            session_id="sess_001",
            step_number=1,
            action_type="browser_action",
            action_name="navigate",
            success=True,
            url="https://example.com",
        )
        
        action2 = ActionRecord(
            timestamp=datetime.now(),
            session_id="sess_001",
            step_number=2,
            action_type="browser_action",
            action_name="click",
            success=False,
            error="Element not found",
            url="https://example.com",
        )
        
        session.add_action(action1)
        session.add_action(action2)
        
        self.assertEqual(len(session.actions), 2)
        self.assertEqual(len(session.urls_visited), 1)
        self.assertEqual(len(session.errors), 1)
        self.assertIn("Element not found", session.errors)
    
    def test_session_record_to_dict_and_back(self):
        """Test round-trip serialization."""
        session = SessionRecord(
            session_id="sess_001",
            agent_id="test_agent",
            task="Test task",
            start_time=datetime(2024, 12, 14, 10, 0, 0),
            end_time=datetime(2024, 12, 14, 10, 30, 0),
            success=True,
            final_result="Task completed successfully",
        )
        
        # Add an action
        action = ActionRecord(
            timestamp=datetime(2024, 12, 14, 10, 15, 0),
            session_id="sess_001",
            step_number=1,
            action_type="browser_action",
            action_name="click",
            success=True,
        )
        session.add_action(action)
        
        # Convert to dict and back
        data = session.to_dict()
        restored = SessionRecord.from_dict(data)
        
        self.assertEqual(restored.session_id, session.session_id)
        self.assertEqual(restored.task, session.task)
        self.assertEqual(restored.success, session.success)
        self.assertEqual(len(restored.actions), 1)
    
    def test_session_summary_text(self):
        """Test generating summary text."""
        session = SessionRecord(
            session_id="sess_001",
            agent_id="test_agent",
            task="Book a flight to Tokyo",
            start_time=datetime.now(),
            success=True,
            final_result="Flight booked for $500",
        )
        
        text = session.to_summary_text()
        
        self.assertIn("Book a flight", text)
        self.assertIn("Success", text)


class TestDailyReflection(unittest.TestCase):
    """Tests for DailyReflection dataclass."""
    
    def test_create_daily_reflection(self):
        """Test creating a DailyReflection."""
        reflection = DailyReflection(
            date="2024-12-14",
            agent_id="test_agent",
            total_sessions=5,
            successful_sessions=4,
            failed_sessions=1,
            lessons=["Always verify before clicking", "Check for popups"],
            knowledge_chunks=["Flight booking requires passport info"],
        )
        
        self.assertEqual(reflection.date, "2024-12-14")
        self.assertEqual(reflection.total_sessions, 5)
        self.assertEqual(len(reflection.lessons), 2)
        self.assertEqual(len(reflection.knowledge_chunks), 1)
    
    def test_reflection_to_dict_and_back(self):
        """Test round-trip serialization."""
        reflection = DailyReflection(
            date="2024-12-14",
            agent_id="test_agent",
            sessions_reviewed=["sess_001", "sess_002"],
            total_sessions=2,
            successful_sessions=2,
            failed_sessions=0,
            successes=["Completed booking flow"],
            patterns=["Users often need to scroll"],
            lessons=["Wait for page load"],
        )
        
        data = reflection.to_dict()
        restored = DailyReflection.from_dict(data)
        
        self.assertEqual(restored.date, reflection.date)
        self.assertEqual(restored.total_sessions, reflection.total_sessions)
        self.assertEqual(restored.lessons, reflection.lessons)


class TestEpisodicStore(unittest.TestCase):
    """Tests for EpisodicStore."""
    
    def setUp(self):
        """Create a temporary directory for testing."""
        self.temp_dir = tempfile.mkdtemp()
        self.store = EpisodicStore(base_dir=self.temp_dir)
    
    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_save_and_load_session(self):
        """Test saving and loading a session."""
        session = SessionRecord(
            session_id="test_sess_001",
            agent_id="test_agent",
            task="Test task",
            start_time=datetime(2024, 12, 14, 10, 0, 0),
            success=True,
        )
        
        # Save
        path = self.store.save_session(session)
        self.assertTrue(os.path.exists(path))
        
        # Load
        loaded = self.store.load_session("test_sess_001", "2024-12-14")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.session_id, "test_sess_001")
        self.assertEqual(loaded.task, "Test task")
    
    def test_load_sessions_for_date(self):
        """Test loading all sessions for a date."""
        # Create multiple sessions
        for i in range(3):
            session = SessionRecord(
                session_id=f"sess_{i:03d}",
                agent_id="test_agent",
                task=f"Task {i}",
                start_time=datetime(2024, 12, 14, 10 + i, 0, 0),
                success=i % 2 == 0,
            )
            self.store.save_session(session)
        
        # Load all
        sessions = self.store.load_sessions_for_date("2024-12-14")
        
        self.assertEqual(len(sessions), 3)
        # Should be sorted by start_time
        self.assertEqual(sessions[0].session_id, "sess_000")
    
    def test_load_sessions_for_range(self):
        """Test loading sessions for a date range."""
        # Create sessions across multiple days
        dates = ["2024-12-12", "2024-12-13", "2024-12-14"]
        for i, date_str in enumerate(dates):
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            session = SessionRecord(
                session_id=f"sess_{date_str}",
                agent_id="test_agent",
                task=f"Task for {date_str}",
                start_time=dt,
                success=True,
            )
            self.store.save_session(session)
        
        # Load range
        sessions = self.store.load_sessions_for_range("2024-12-12", "2024-12-14")
        
        self.assertEqual(len(sessions), 3)
    
    def test_save_and_load_reflection(self):
        """Test saving and loading a reflection."""
        reflection = DailyReflection(
            date="2024-12-14",
            agent_id="test_agent",
            total_sessions=5,
            successful_sessions=4,
            failed_sessions=1,
            lessons=["Lesson 1", "Lesson 2"],
        )
        
        # Save
        path = self.store.save_reflection(reflection)
        self.assertTrue(os.path.exists(path))
        
        # Load
        loaded = self.store.load_reflection("2024-12-14")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.total_sessions, 5)
        self.assertEqual(loaded.lessons, ["Lesson 1", "Lesson 2"])
    
    def test_get_stats(self):
        """Test getting statistics."""
        # Create sessions
        for i in range(5):
            session = SessionRecord(
                session_id=f"sess_{i:03d}",
                agent_id="test_agent",
                task=f"Task {i}",
                start_time=datetime(2024, 12, 14, 10 + i, 0, 0),
                success=i < 3,  # 3 successful, 2 failed
            )
            # Add some actions
            for j in range(3):
                action = ActionRecord(
                    timestamp=datetime.now(),
                    session_id=f"sess_{i:03d}",
                    step_number=j,
                    action_type="browser_action",
                    action_name="click",
                    success=True,
                )
                session.add_action(action)
            self.store.save_session(session)
        
        stats = self.store.get_stats("2024-12-14")
        
        self.assertEqual(stats["total_sessions"], 5)
        self.assertEqual(stats["successful"], 3)
        self.assertEqual(stats["failed"], 2)
        self.assertEqual(stats["total_actions"], 15)


class TestSessionRecorder(unittest.TestCase):
    """Tests for SessionRecorder."""
    
    def setUp(self):
        """Create a temporary directory for testing."""
        self.temp_dir = tempfile.mkdtemp()
        self.store = EpisodicStore(base_dir=self.temp_dir)
    
    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_record_steps(self):
        """Test recording steps."""
        recorder = SessionRecorder(
            agent_id="test_agent",
            task="Test task",
            store=self.store,
        )
        
        # Mock StepData
        class MockStepData:
            step_number = 1
            action = None
            error = None
            url = "https://example.com"
            title = "Example"
            thinking = "Thinking..."
            next_goal = "Next goal"
        
        # Record step
        asyncio.run(recorder.record_step(MockStepData()))
        
        self.assertEqual(len(recorder.session.actions), 1)
        self.assertEqual(recorder.session.actions[0].url, "https://example.com")
    
    def test_finalize_and_save(self):
        """Test finalizing and saving a session."""
        recorder = SessionRecorder(
            agent_id="test_agent",
            task="Test task",
            store=self.store,
        )
        
        # Finalize
        session = recorder.finalize(success=True, final_result="Done!")
        
        self.assertTrue(session.success)
        self.assertEqual(session.final_result, "Done!")
        self.assertIsNotNone(session.end_time)
        
        # Save
        path = recorder.save()
        self.assertTrue(os.path.exists(path))


class TestReflectionEngine(unittest.TestCase):
    """Tests for ReflectionEngine."""
    
    def setUp(self):
        """Create a temporary directory and mock LLM."""
        self.temp_dir = tempfile.mkdtemp()
        self.store = EpisodicStore(base_dir=self.temp_dir)
        
        # Create some test sessions
        for i in range(3):
            session = SessionRecord(
                session_id=f"sess_{i:03d}",
                agent_id="test_agent",
                task=f"Task {i}: Do something",
                start_time=datetime.now(),
                success=i < 2,
                final_result=f"Result {i}",
            )
            # Add actions
            for j in range(2):
                action = ActionRecord(
                    timestamp=datetime.now(),
                    session_id=f"sess_{i:03d}",
                    step_number=j,
                    action_type="browser_action",
                    action_name="click",
                    success=True,
                    thinking=f"Thinking step {j}",
                )
                session.add_action(action)
            self.store.save_session(session)
    
    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_generate_basic_reflection_without_llm(self):
        """Test generating reflection without LLM (basic stats only)."""
        engine = ReflectionEngine(
            llm=None,  # No LLM
            episodic_store=self.store,
            agent_id="test_agent",
        )
        
        today = datetime.now().strftime("%Y-%m-%d")
        reflection = asyncio.run(engine.generate_daily_reflection(today))
        
        self.assertIsNotNone(reflection)
        self.assertEqual(reflection.total_sessions, 3)
        self.assertEqual(reflection.successful_sessions, 2)
        self.assertEqual(reflection.failed_sessions, 1)
    
    def test_generate_reflection_with_mock_llm(self):
        """Test generating reflection with mock LLM."""
        # Create mock LLM
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "successes": ["Task 0 completed", "Task 1 completed"],
            "failures": ["Task 2 failed due to timeout"],
            "patterns": ["All tasks involved clicking"],
            "lessons": ["Always wait for page load", "Verify element exists"],
            "improvements": ["Add retry logic"],
            "knowledge_chunks": ["Clicking requires element to be visible"],
        })
        mock_llm.invoke = MagicMock(return_value=mock_response)
        
        engine = ReflectionEngine(
            llm=mock_llm,
            episodic_store=self.store,
            agent_id="test_agent",
        )
        
        today = datetime.now().strftime("%Y-%m-%d")
        reflection = asyncio.run(engine.generate_daily_reflection(today, force=True))
        
        self.assertIsNotNone(reflection)
        self.assertEqual(len(reflection.successes), 2)
        self.assertEqual(len(reflection.lessons), 2)
        self.assertEqual(len(reflection.knowledge_chunks), 1)
    
    def test_store_knowledge_to_rag(self):
        """Test storing knowledge to RAG."""
        # Create mock RAG client
        mock_rag = MagicMock()
        mock_rag.insert = AsyncMock()
        
        engine = ReflectionEngine(
            llm=None,
            rag_client=mock_rag,
            episodic_store=self.store,
            agent_id="test_agent",
        )
        
        reflection = DailyReflection(
            date="2024-12-14",
            agent_id="test_agent",
            knowledge_chunks=["Chunk 1", "Chunk 2", "Chunk 3"],
        )
        
        stored = asyncio.run(engine.store_knowledge_to_rag(reflection))
        
        self.assertEqual(stored, 3)
        self.assertEqual(mock_rag.insert.call_count, 3)


class TestMemoryNamespaces(unittest.TestCase):
    """Tests for MemoryNamespaces."""
    
    def test_namespaces_exist(self):
        """Test that all expected namespaces exist."""
        self.assertEqual(MemoryNamespaces.DEFAULT, "default")
        self.assertEqual(MemoryNamespaces.CHAT, "chat")
        self.assertEqual(MemoryNamespaces.TASK, "task")
        self.assertEqual(MemoryNamespaces.EPISODIC, "episodic")
        self.assertEqual(MemoryNamespaces.PROCEDURAL, "procedural")
        self.assertEqual(MemoryNamespaces.SEMANTIC, "semantic")
        self.assertEqual(MemoryNamespaces.REFLECTION, "reflection")


# =============================================================================
# Integration Test
# =============================================================================

class TestIntegration(unittest.TestCase):
    """Integration tests for the full memory workflow."""
    
    def setUp(self):
        """Create a temporary directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.store = EpisodicStore(base_dir=self.temp_dir)
    
    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_full_workflow(self):
        """Test the full workflow: record -> save -> reflect."""
        # 1. Record a session
        recorder = SessionRecorder(
            agent_id="integration_test",
            task="Complete integration test",
            store=self.store,
        )
        
        # Mock step data
        class MockStepData:
            def __init__(self, step_num, success=True):
                self.step_number = step_num
                self.action = None
                self.error = None if success else "Test error"
                self.url = f"https://example.com/step{step_num}"
                self.title = f"Step {step_num}"
                self.thinking = f"Thinking about step {step_num}"
                self.next_goal = f"Complete step {step_num + 1}"
        
        # Record multiple steps
        for i in range(5):
            asyncio.run(recorder.record_step(MockStepData(i, success=i < 4)))
        
        # 2. Finalize and save
        recorder.finalize(success=True, final_result="Integration test passed!")
        recorder.save()
        
        # 3. Verify session was saved
        today = datetime.now().strftime("%Y-%m-%d")
        sessions = self.store.load_sessions_for_date(today)
        self.assertEqual(len(sessions), 1)
        self.assertEqual(len(sessions[0].actions), 5)
        
        # 4. Generate reflection (without LLM)
        engine = ReflectionEngine(
            llm=None,
            episodic_store=self.store,
            agent_id="integration_test",
        )
        
        reflection = asyncio.run(engine.generate_daily_reflection(today))
        
        self.assertIsNotNone(reflection)
        self.assertEqual(reflection.total_sessions, 1)
        self.assertEqual(reflection.successful_sessions, 1)
        
        # 5. Verify reflection was saved
        loaded_reflection = self.store.load_reflection(today)
        self.assertIsNotNone(loaded_reflection)
        
        print("\n✅ Integration test passed!")
        print(f"   - Recorded 5 steps")
        print(f"   - Saved session to {self.temp_dir}")
        print(f"   - Generated reflection for {today}")


# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Agent Memory Module - Unit Tests")
    print("=" * 60)
    
    # Run tests
    unittest.main(verbosity=2)
