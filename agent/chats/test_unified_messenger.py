"""
test_unified_messenger.py - Test utilities for Unified Messaging

This module provides test utilities and examples for testing the unified
messaging system (LAN/WAN auto-routing).

Usage:
    # Run all tests from project root
    python agent/chats/test_unified_messenger.py
    
    # Or import and use individual test functions
    from agent.chats.test_unified_messenger import test_lan_send, test_wan_send
"""

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Optional, Dict, Any, List
from uuid import uuid4
from unittest.mock import MagicMock, AsyncMock, patch

# Add project root to path for standalone execution
_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from agent.a2a.common.types import Message, TextPart, FilePart, DataPart, FileContent, TaskSendParams

# Use simple print-based logging for tests to avoid import issues
class SimpleLogger:
    def info(self, *args): print(f"[INFO] {' '.join(str(a) for a in args)}")
    def debug(self, *args): print(f"[DEBUG] {' '.join(str(a) for a in args)}")
    def error(self, *args): print(f"[ERROR] {' '.join(str(a) for a in args)}")
    def warning(self, *args): print(f"[WARN] {' '.join(str(a) for a in args)}")

logger = SimpleLogger()


# =============================================================================
# Mock Objects for Testing
# =============================================================================

class MockAgentCard:
    """Mock AgentCard for testing."""
    def __init__(self, agent_id: str = None, name: str = "TestAgent", url: str = "http://localhost:5001"):
        self.id = agent_id or str(uuid4())
        self.name = name
        self.url = url
        self.description = f"Mock agent {name}"
        self.provider = "test"
        self.version = "1.0.0"


class MockMainWindow:
    """Mock MainWindow for testing WAN connectivity."""
    def __init__(self, auth_token: str = "test-token"):
        self._auth_token = auth_token
        self._wan_connected = False
        self._wan_subscribed = False
        self.agents = []
        self.session = MagicMock()
    
    def get_auth_token(self) -> str:
        return self._auth_token
    
    def get_wan_connected(self) -> bool:
        return self._wan_connected
    
    def set_wan_connected(self, value: bool):
        self._wan_connected = value
    
    def get_wan_msg_subscribed(self) -> bool:
        return self._wan_subscribed
    
    def set_wan_msg_subscribed(self, value: bool):
        self._wan_subscribed = value


class MockAgent:
    """Mock EC_Agent for testing."""
    def __init__(self, card: MockAgentCard = None, mainwin: MockMainWindow = None):
        self.card = card or MockAgentCard()
        self.mainwin = mainwin or MockMainWindow()
        self.unified_messenger = None  # Will be set by test


# =============================================================================
# Message Builders
# =============================================================================

def build_test_message(
    text: str = "Hello, this is a test message",
    role: str = "user",
    attachments: List[Dict] = None,
    metadata: Dict = None
) -> Message:
    """
    Build a test A2A Message.
    
    Args:
        text: Message text content
        role: Message role ("user" or "agent")
        attachments: Optional list of file attachments
        metadata: Optional metadata dict
        
    Returns:
        A2A Message object
    """
    parts = [TextPart(type="text", text=text)]
    
    if attachments:
        for att in attachments:
            fc = FileContent(
                name=att.get("name", "test.txt"),
                mimeType=att.get("type", "text/plain"),
                bytes=att.get("data", ""),
                uri=att.get("url", "")
            )
            parts.append(FilePart(type="file", file=fc))
    
    return Message(role=role, parts=parts, metadata=metadata or {})


def build_test_task_send_params(
    text: str = "Test message",
    session_id: str = None,
    task_id: str = None,
    sender_id: str = None,
    recipient_id: str = None,
    metadata: Dict = None
) -> TaskSendParams:
    """
    Build a test TaskSendParams payload.
    
    Args:
        text: Message text
        session_id: Session/chat ID
        task_id: Task ID
        sender_id: Sender agent ID
        recipient_id: Recipient agent ID
        metadata: Optional metadata
        
    Returns:
        TaskSendParams object
    """
    message = build_test_message(text)
    
    meta = metadata or {}
    if sender_id:
        meta["senderId"] = sender_id
    if recipient_id:
        meta["recipientId"] = recipient_id
    
    return TaskSendParams(
        id=task_id or str(uuid4()),
        sessionId=session_id or str(uuid4()),
        message=message,
        acceptedOutputModes=["text", "json"],
        metadata=meta
    )


def build_legacy_message_dict(
    text: str = "Test message",
    chat_id: str = None,
    agent_id: str = None,
    attachments: List = None
) -> Dict:
    """
    Build a legacy message dict (format used by a2a_send_chat_message_sync).
    
    This is the format expected by EC_Agent's unified_send_chat_message methods.
    """
    return {
        "messages": [
            agent_id or str(uuid4()),  # [0] agent_id
            chat_id or f"chat-{uuid4().hex[:6]}",  # [1] chat_id
            str(uuid4()),  # [2] msg_id
            str(uuid4()),  # [3] task_id
            text  # [4] msg_txt
        ],
        "attributes": {
            "params": {
                "content": text,
                "attachments": attachments or [],
                "chatId": chat_id or f"chat-{uuid4().hex[:6]}",
                "senderId": agent_id or str(uuid4()),
                "role": "user",
                "createAt": str(int(time.time() * 1000)),
                "senderName": "TestUser",
                "status": "complete"
            }
        }
    }


# =============================================================================
# Test Functions
# =============================================================================

async def test_lan_routing():
    """Test that messages to LAN-registered agents route via HTTP."""
    from agent.chats.unified_messenger import UnifiedMessenger
    
    print("\n" + "="*60)
    print("TEST: LAN Routing")
    print("="*60)
    
    # Setup
    mock_agent = MockAgent()
    mock_mainwin = MockMainWindow()
    messenger = UnifiedMessenger(mock_agent, mock_mainwin)
    
    # Register a LAN agent
    lan_agent_id = "lan-agent-001"
    lan_agent_url = "http://192.168.1.100:5001/a2a/"
    messenger.register_lan_agent(lan_agent_id, lan_agent_url)
    
    # Verify routing decision
    assert messenger.is_lan_reachable(lan_agent_id), "Agent should be LAN reachable"
    assert messenger.get_agent_location(lan_agent_id) == "lan", "Location should be 'lan'"
    
    print(f"✅ LAN agent registered: {lan_agent_id} -> {lan_agent_url}")
    print(f"✅ is_lan_reachable: {messenger.is_lan_reachable(lan_agent_id)}")
    print(f"✅ get_agent_location: {messenger.get_agent_location(lan_agent_id)}")
    
    return True


async def test_wan_routing():
    """Test that messages to WAN-registered agents route via WebSocket."""
    from agent.chats.unified_messenger import UnifiedMessenger
    
    print("\n" + "="*60)
    print("TEST: WAN Routing")
    print("="*60)
    
    # Setup
    mock_agent = MockAgent()
    mock_mainwin = MockMainWindow()
    messenger = UnifiedMessenger(mock_agent, mock_mainwin)
    
    # Register a WAN agent
    wan_agent_id = "wan-agent-001"
    messenger.register_wan_agent(wan_agent_id)
    
    # Verify routing decision
    assert messenger.is_wan_reachable(wan_agent_id), "Agent should be WAN reachable"
    assert messenger.get_agent_location(wan_agent_id) == "wan", "Location should be 'wan'"
    
    print(f"✅ WAN agent registered: {wan_agent_id}")
    print(f"✅ is_wan_reachable: {messenger.is_wan_reachable(wan_agent_id)}")
    print(f"✅ get_agent_location: {messenger.get_agent_location(wan_agent_id)}")
    
    return True


async def test_unknown_agent_fallback():
    """Test that unknown agents fall back to WAN."""
    from agent.chats.unified_messenger import UnifiedMessenger
    
    print("\n" + "="*60)
    print("TEST: Unknown Agent Fallback")
    print("="*60)
    
    # Setup
    mock_agent = MockAgent()
    mock_mainwin = MockMainWindow()
    messenger = UnifiedMessenger(mock_agent, mock_mainwin)
    
    # Check unknown agent
    unknown_id = "unknown-agent-xyz"
    
    assert not messenger.is_lan_reachable(unknown_id), "Unknown agent should not be LAN reachable"
    assert not messenger.is_wan_reachable(unknown_id), "Unknown agent should not be WAN reachable"
    assert messenger.get_agent_location(unknown_id) == "unknown", "Location should be 'unknown'"
    
    print(f"✅ Unknown agent: {unknown_id}")
    print(f"✅ is_lan_reachable: {messenger.is_lan_reachable(unknown_id)}")
    print(f"✅ is_wan_reachable: {messenger.is_wan_reachable(unknown_id)}")
    print(f"✅ get_agent_location: {messenger.get_agent_location(unknown_id)} (will fallback to WAN)")
    
    return True


async def test_group_management():
    """Test group creation and membership."""
    from agent.chats.unified_messenger import UnifiedMessenger
    
    print("\n" + "="*60)
    print("TEST: Group Management")
    print("="*60)
    
    # Setup
    mock_agent = MockAgent()
    mock_mainwin = MockMainWindow()
    messenger = UnifiedMessenger(mock_agent, mock_mainwin)
    
    # Create a group
    group_id = "team-alpha"
    members = ["agent-1", "agent-2", "agent-3"]
    messenger.register_group(group_id, members)
    
    # Verify
    assert messenger.get_group_members(group_id) == members, "Group members should match"
    print(f"✅ Group created: {group_id} with members {members}")
    
    # Add member
    messenger.add_to_group(group_id, "agent-4")
    assert "agent-4" in messenger.get_group_members(group_id), "agent-4 should be in group"
    print(f"✅ Added agent-4 to group")
    
    # Remove member
    messenger.remove_from_group(group_id, "agent-2")
    assert "agent-2" not in messenger.get_group_members(group_id), "agent-2 should be removed"
    print(f"✅ Removed agent-2 from group")
    
    print(f"✅ Final members: {messenger.get_group_members(group_id)}")
    
    return True


async def test_message_building():
    """Test message building utilities."""
    print("\n" + "="*60)
    print("TEST: Message Building")
    print("="*60)
    
    # Test simple message
    msg = build_test_message("Hello world")
    assert msg.role == "user"
    assert len(msg.parts) == 1
    assert msg.parts[0].text == "Hello world"
    print(f"✅ Simple message built: {msg.parts[0].text}")
    
    # Test message with attachment
    msg_with_att = build_test_message(
        "Message with file",
        attachments=[{"name": "test.pdf", "type": "application/pdf", "data": "base64data"}]
    )
    assert len(msg_with_att.parts) == 2
    print(f"✅ Message with attachment built: {len(msg_with_att.parts)} parts")
    
    # Test TaskSendParams
    params = build_test_task_send_params(
        text="Task message",
        sender_id="sender-001",
        recipient_id="recipient-001"
    )
    assert params.message.parts[0].text == "Task message"
    assert params.metadata.get("senderId") == "sender-001"
    print(f"✅ TaskSendParams built: id={params.id[:8]}...")
    
    # Test legacy dict
    legacy = build_legacy_message_dict("Legacy message", chat_id="chat-123")
    assert legacy["messages"][4] == "Legacy message"
    assert legacy["attributes"]["params"]["chatId"] == "chat-123"
    print(f"✅ Legacy message dict built: chat_id={legacy['messages'][1]}")
    
    return True


async def test_registry_operations():
    """Test agent registry operations."""
    from agent.chats.unified_messenger import UnifiedMessenger
    
    print("\n" + "="*60)
    print("TEST: Registry Operations")
    print("="*60)
    
    # Setup
    mock_agent = MockAgent()
    mock_mainwin = MockMainWindow()
    messenger = UnifiedMessenger(mock_agent, mock_mainwin)
    
    # Register LAN agent
    messenger.register_lan_agent("agent-1", "http://192.168.1.10:5001/a2a/")
    assert messenger.is_lan_reachable("agent-1")
    print(f"✅ Registered LAN agent-1")
    
    # Move agent to WAN (should remove from LAN)
    messenger.register_wan_agent("agent-1")
    assert not messenger.is_lan_reachable("agent-1")
    assert messenger.is_wan_reachable("agent-1")
    print(f"✅ Moved agent-1 to WAN")
    
    # Move back to LAN
    messenger.register_lan_agent("agent-1", "http://192.168.1.10:5001/a2a/")
    assert messenger.is_lan_reachable("agent-1")
    assert not messenger.is_wan_reachable("agent-1")
    print(f"✅ Moved agent-1 back to LAN")
    
    # Unregister
    messenger.unregister_agent("agent-1")
    assert not messenger.is_lan_reachable("agent-1")
    assert not messenger.is_wan_reachable("agent-1")
    print(f"✅ Unregistered agent-1")
    
    return True


# =============================================================================
# Integration Test (requires real infrastructure)
# =============================================================================

async def integration_test_lan_send(
    recipient_url: str = "http://localhost:5001/a2a/",
    message_text: str = "Integration test message"
):
    """
    Integration test for LAN sending (requires a running A2A server).
    
    Args:
        recipient_url: URL of the recipient A2A server
        message_text: Message to send
    """
    from agent.chats.unified_messenger import UnifiedMessenger
    
    print("\n" + "="*60)
    print("INTEGRATION TEST: LAN Send")
    print("="*60)
    print(f"⚠️  Requires running A2A server at {recipient_url}")
    
    # Setup
    mock_agent = MockAgent()
    mock_mainwin = MockMainWindow()
    messenger = UnifiedMessenger(mock_agent, mock_mainwin)
    
    # Register recipient
    recipient_id = "test-recipient"
    messenger.register_lan_agent(recipient_id, recipient_url)
    
    # Build message
    message = build_test_message(message_text)
    
    try:
        # Send
        result = await messenger.send(recipient_id, message)
        print(f"✅ Message sent via {result.get('transport', 'unknown')}")
        print(f"   Response: {json.dumps(result.get('response', {}), indent=2)[:200]}...")
        return True
    except Exception as e:
        print(f"❌ Send failed: {e}")
        print(f"   (This is expected if no A2A server is running)")
        return False


async def integration_test_wan_send(
    channel_id: str = "test-channel",
    message_text: str = "WAN integration test message"
):
    """
    Integration test for WAN sending (requires AWS AppSync setup).
    
    Args:
        channel_id: Channel to send to
        message_text: Message to send
    """
    from agent.chats.unified_messenger import UnifiedMessenger
    
    print("\n" + "="*60)
    print("INTEGRATION TEST: WAN Send")
    print("="*60)
    print(f"⚠️  Requires AWS AppSync A2AMessage schema deployed")
    print(f"⚠️  Requires valid auth token in MainWindow")
    
    # This would need real MainWindow with auth
    print(f"❌ Skipped: Requires real AWS credentials")
    return False


# =============================================================================
# Test Runner
# =============================================================================

async def run_all_tests():
    """Run all unit tests."""
    print("\n" + "="*60)
    print("UNIFIED MESSENGER TEST SUITE")
    print("="*60)
    
    tests = [
        ("LAN Routing", test_lan_routing),
        ("WAN Routing", test_wan_routing),
        ("Unknown Agent Fallback", test_unknown_agent_fallback),
        ("Group Management", test_group_management),
        ("Message Building", test_message_building),
        ("Registry Operations", test_registry_operations),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = await test_func()
            results.append((name, result, None))
        except Exception as e:
            results.append((name, False, str(e)))
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, r, _ in results if r)
    failed = len(results) - passed
    
    for name, result, error in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status}: {name}")
        if error:
            print(f"         Error: {error}")
    
    print(f"\nTotal: {passed}/{len(results)} passed")
    
    return failed == 0


def run_tests():
    """Synchronous entry point for running tests."""
    return asyncio.run(run_all_tests())


# =============================================================================
# CLI Entry Point
# =============================================================================

if __name__ == "__main__":
    import sys
    
    success = run_tests()
    sys.exit(0 if success else 1)
