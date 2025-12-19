"""
unified_messenger.py - Unified Messaging Layer for LAN/WAN Auto-Routing

This module provides a single API for all agent-to-agent messaging, automatically
routing messages between:
- LAN: Direct HTTP A2A calls (for agents on the same network)
- WAN: AWS AppSync WebSocket (for agents across the internet)

The message format is unified using A2A's TaskSendParams/Message structure,
eliminating the need for data adaptation between transports.

Usage:
    messenger = UnifiedMessenger(agent, mainwin)
    
    # Send to a specific agent (auto-routes LAN vs WAN)
    await messenger.send(recipient_id, message)
    
    # Send to a group (all subscribers receive)
    await messenger.send_to_group(group_id, message)
    
    # Subscribe to incoming messages
    await messenger.subscribe(channel_id, on_message_callback)
"""

from __future__ import annotations
import asyncio
import traceback
from typing import TYPE_CHECKING, Dict, List, Optional, Any, Callable, Set
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor

from agent.a2a.common.client import A2AClient
from agent.a2a.common.types import (
    TaskSendParams,
    Message,
    TextPart,
    FilePart,
    DataPart,
    FileContent,
    SendTaskResponse,
    Part
)
from agent.chats.wan_a2a_chat import (
    wan_a2a_send_message,
    wan_a2a_send_message_sync,
    wan_a2a_subscribe,
    graphql_response_to_task_send_params
)
from utils.logger_helper import logger_helper as logger

if TYPE_CHECKING:
    from agent.ec_agent import EC_Agent
    from gui.MainGUI import MainWindow


# Thread pool for non-blocking sends
_unified_send_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="unified_msg_")


class UnifiedMessenger:
    """
    Unified messaging layer that auto-routes between LAN and WAN transports.
    
    This class provides a single API for sending messages to agents regardless
    of their location (local network or remote). It uses the A2A message format
    (TaskSendParams/Message) for all communications.
    
    Attributes:
        agent: The EC_Agent instance that owns this messenger
        mainwin: MainWindow instance for WAN connectivity and auth
        lan_registry: Maps agent_id -> local A2A URL for LAN agents
        wan_agents: Set of agent IDs known to be on WAN
        groups: Maps group_id -> list of member agent IDs
    """
    
    def __init__(self, agent: 'EC_Agent', mainwin: 'MainWindow'):
        """
        Initialize UnifiedMessenger.
        
        Args:
            agent: The EC_Agent that owns this messenger
            mainwin: MainWindow instance for WAN access
        """
        self.agent = agent
        self.mainwin = mainwin
        
        # LAN agent registry: agent_id -> A2A URL
        self.lan_registry: Dict[str, str] = {}
        
        # WAN agent set: agent IDs known to be on WAN
        self.wan_agents: Set[str] = set()
        
        # Group membership: group_id -> list of agent IDs
        self.groups: Dict[str, List[str]] = {}
        
        # Subscription callbacks: channel_id -> callback function
        self._subscriptions: Dict[str, Callable] = {}
        
        # A2A client for LAN communication
        self._a2a_client = A2AClient(url="http://localhost:5000/a2a/")  # Default, will be set per-request
        
        logger.info(f"[UnifiedMessenger] Initialized for agent: {agent.card.id if agent.card else 'unknown'}")
    
    # =========================================================================
    # Registry Management
    # =========================================================================
    
    def register_lan_agent(self, agent_id: str, a2a_url: str):
        """
        Register an agent as reachable on LAN.
        
        Args:
            agent_id: The agent's unique ID
            a2a_url: The agent's A2A endpoint URL (e.g., "http://192.168.1.100:5001/a2a/")
        """
        self.lan_registry[agent_id] = a2a_url
        # Remove from WAN set if present
        self.wan_agents.discard(agent_id)
        logger.debug(f"[UnifiedMessenger] Registered LAN agent: {agent_id} -> {a2a_url}")
    
    def register_wan_agent(self, agent_id: str):
        """
        Register an agent as reachable only via WAN.
        
        Args:
            agent_id: The agent's unique ID
        """
        self.wan_agents.add(agent_id)
        # Remove from LAN registry if present
        self.lan_registry.pop(agent_id, None)
        logger.debug(f"[UnifiedMessenger] Registered WAN agent: {agent_id}")
    
    def unregister_agent(self, agent_id: str):
        """
        Remove an agent from all registries.
        
        Args:
            agent_id: The agent's unique ID
        """
        self.lan_registry.pop(agent_id, None)
        self.wan_agents.discard(agent_id)
        logger.debug(f"[UnifiedMessenger] Unregistered agent: {agent_id}")
    
    def register_group(self, group_id: str, member_ids: List[str]):
        """
        Register a group with its member agent IDs.
        
        Args:
            group_id: The group's unique ID
            member_ids: List of agent IDs in the group
        """
        self.groups[group_id] = member_ids
        logger.debug(f"[UnifiedMessenger] Registered group: {group_id} with {len(member_ids)} members")
    
    def add_to_group(self, group_id: str, agent_id: str):
        """Add an agent to a group."""
        if group_id not in self.groups:
            self.groups[group_id] = []
        if agent_id not in self.groups[group_id]:
            self.groups[group_id].append(agent_id)
    
    def remove_from_group(self, group_id: str, agent_id: str):
        """Remove an agent from a group."""
        if group_id in self.groups and agent_id in self.groups[group_id]:
            self.groups[group_id].remove(agent_id)
    
    def get_group_members(self, group_id: str) -> List[str]:
        """Get all members of a group."""
        return self.groups.get(group_id, [])
    
    def is_lan_reachable(self, agent_id: str) -> bool:
        """Check if an agent is reachable on LAN."""
        return agent_id in self.lan_registry
    
    def is_wan_reachable(self, agent_id: str) -> bool:
        """Check if an agent is reachable via WAN."""
        return agent_id in self.wan_agents
    
    def get_agent_location(self, agent_id: str) -> str:
        """
        Get the location type of an agent.
        
        Returns:
            "lan", "wan", or "unknown"
        """
        if agent_id in self.lan_registry:
            return "lan"
        elif agent_id in self.wan_agents:
            return "wan"
        else:
            return "unknown"
    
    # =========================================================================
    # Auto-Discovery from MainWindow
    # =========================================================================
    
    def sync_from_mainwin(self):
        """
        Sync agent registry from MainWindow's agents list.
        
        This populates the LAN registry with all locally known agents.
        """
        try:
            if hasattr(self.mainwin, 'agents'):
                for agent in self.mainwin.agents:
                    if hasattr(agent, 'card') and agent.card:
                        agent_id = agent.card.id
                        agent_url = agent.card.url
                        if agent_url:
                            # Ensure URL ends with /a2a/
                            if not agent_url.endswith('/a2a/'):
                                agent_url = agent_url.rstrip('/') + '/a2a/'
                            self.register_lan_agent(agent_id, agent_url)
                
                logger.info(f"[UnifiedMessenger] Synced {len(self.lan_registry)} agents from MainWindow")
        except Exception as e:
            logger.error(f"[UnifiedMessenger] Error syncing from MainWindow: {e}")
    
    # =========================================================================
    # Message Sending - Core API
    # =========================================================================
    
    async def send(
        self,
        recipient_id: str,
        message: Message,
        session_id: Optional[str] = None,
        accepted_output_modes: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Send a message to a specific agent, auto-routing between LAN and WAN.
        
        Args:
            recipient_id: Target agent ID
            message: A2A Message object
            session_id: Optional session/chat ID
            accepted_output_modes: Optional list of accepted output modes
            metadata: Optional metadata dict
            
        Returns:
            Response dict from the transport
            
        Raises:
            ValueError: If recipient is not found in any registry
        """
        sender_id = self.agent.card.id if self.agent.card else "unknown"
        session_id = session_id or str(uuid4())
        
        logger.debug(f"[UnifiedMessenger] Sending message from {sender_id} to {recipient_id}")
        
        # Route decision
        if self.is_lan_reachable(recipient_id):
            logger.debug(f"[UnifiedMessenger] Routing to LAN: {recipient_id}")
            return await self._send_lan(recipient_id, message, session_id, accepted_output_modes, metadata)
        elif self.is_wan_reachable(recipient_id):
            logger.debug(f"[UnifiedMessenger] Routing to WAN: {recipient_id}")
            return await self._send_wan(recipient_id, message, session_id, accepted_output_modes, metadata)
        else:
            # Try WAN as fallback for unknown agents
            logger.warning(f"[UnifiedMessenger] Agent {recipient_id} not in registry, trying WAN fallback")
            return await self._send_wan(recipient_id, message, session_id, accepted_output_modes, metadata)
    
    def send_sync(
        self,
        recipient_id: str,
        message: Message,
        session_id: Optional[str] = None,
        accepted_output_modes: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Synchronous version of send().
        
        Use this when you need blocking behavior or are not in an async context.
        """
        sender_id = self.agent.card.id if self.agent.card else "unknown"
        session_id = session_id or str(uuid4())
        
        logger.debug(f"[UnifiedMessenger] Sending message (sync) from {sender_id} to {recipient_id}")
        
        # Route decision
        if self.is_lan_reachable(recipient_id):
            return self._send_lan_sync(recipient_id, message, session_id, accepted_output_modes, metadata)
        elif self.is_wan_reachable(recipient_id):
            return self._send_wan_sync(recipient_id, message, session_id, accepted_output_modes, metadata)
        else:
            # Try WAN as fallback
            logger.warning(f"[UnifiedMessenger] Agent {recipient_id} not in registry, trying WAN fallback (sync)")
            return self._send_wan_sync(recipient_id, message, session_id, accepted_output_modes, metadata)
    
    def send_async_fire_and_forget(
        self,
        recipient_id: str,
        message: Message,
        session_id: Optional[str] = None,
        accepted_output_modes: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Non-blocking fire-and-forget send.
        
        Use this when you don't need to wait for a response and want to avoid
        potential deadlocks in agent-to-agent communication.
        
        Returns:
            Future object (can be ignored for fire-and-forget)
        """
        def _send():
            try:
                return self.send_sync(recipient_id, message, session_id, accepted_output_modes, metadata)
            except Exception as e:
                logger.error(f"[UnifiedMessenger] Fire-and-forget send failed: {e}")
                return None
        
        future = _unified_send_executor.submit(_send)
        logger.debug(f"[UnifiedMessenger] Fire-and-forget send queued to {recipient_id}")
        return future
    
    # =========================================================================
    # Group Messaging
    # =========================================================================
    
    async def send_to_group(
        self,
        group_id: str,
        message: Message,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Send a message to all members of a group.
        
        For LAN members: Parallel direct sends
        For WAN members: Single broadcast to group channel
        
        Args:
            group_id: Group/channel ID
            message: A2A Message object
            session_id: Optional session ID
            metadata: Optional metadata
            
        Returns:
            Dict with results from LAN and WAN sends
        """
        sender_id = self.agent.card.id if self.agent.card else "unknown"
        session_id = session_id or str(uuid4())
        members = self.get_group_members(group_id)
        
        logger.debug(f"[UnifiedMessenger] Sending to group {group_id} with {len(members)} members")
        
        # Separate LAN and WAN members
        lan_members = [m for m in members if self.is_lan_reachable(m)]
        wan_members = [m for m in members if self.is_wan_reachable(m)]
        unknown_members = [m for m in members if not self.is_lan_reachable(m) and not self.is_wan_reachable(m)]
        
        results = {"lan": [], "wan": None, "errors": []}
        
        # LAN: Parallel direct sends
        if lan_members:
            lan_tasks = [
                self._send_lan(m, message, session_id, metadata=metadata)
                for m in lan_members
            ]
            try:
                lan_results = await asyncio.gather(*lan_tasks, return_exceptions=True)
                for i, result in enumerate(lan_results):
                    if isinstance(result, Exception):
                        results["errors"].append({"agent": lan_members[i], "error": str(result)})
                    else:
                        results["lan"].append({"agent": lan_members[i], "result": result})
            except Exception as e:
                logger.error(f"[UnifiedMessenger] LAN group send error: {e}")
                results["errors"].append({"type": "lan_batch", "error": str(e)})
        
        # WAN: Single broadcast to group channel (all WAN subscribers receive)
        if wan_members or unknown_members:
            try:
                wan_result = await wan_a2a_send_message(
                    mainwin=self.mainwin,
                    channel_id=group_id,  # Use group_id as channel
                    message=message,
                    sender_id=sender_id,
                    recipient_id=None,  # Broadcast
                    session_id=session_id,
                    metadata=metadata
                )
                results["wan"] = wan_result
            except Exception as e:
                logger.error(f"[UnifiedMessenger] WAN group send error: {e}")
                results["errors"].append({"type": "wan_broadcast", "error": str(e)})
        
        logger.debug(f"[UnifiedMessenger] Group send complete: {len(results['lan'])} LAN, WAN={'sent' if results['wan'] else 'none'}")
        return results
    
    # =========================================================================
    # Subscription Management
    # =========================================================================
    
    async def subscribe(
        self,
        channel_id: str,
        on_message_callback: Optional[Callable] = None
    ):
        """
        Subscribe to messages on a channel.
        
        For WAN channels, this establishes an AWS AppSync WebSocket subscription.
        For LAN, messages are received via the A2A server (no explicit subscription needed).
        
        Args:
            channel_id: Channel/group ID to subscribe to
            on_message_callback: Optional callback function(TaskSendParams, sender_id, channel_id)
        """
        self._subscriptions[channel_id] = on_message_callback
        
        # Start WAN subscription
        logger.info(f"[UnifiedMessenger] Subscribing to channel: {channel_id}")
        await wan_a2a_subscribe(
            mainwin=self.mainwin,
            channel_id=channel_id,
            on_message_callback=on_message_callback
        )
    
    def unsubscribe(self, channel_id: str):
        """
        Unsubscribe from a channel.
        
        Args:
            channel_id: Channel to unsubscribe from
        """
        self._subscriptions.pop(channel_id, None)
        logger.info(f"[UnifiedMessenger] Unsubscribed from channel: {channel_id}")
    
    # =========================================================================
    # Convenience Methods
    # =========================================================================
    
    async def send_text(
        self,
        recipient_id: str,
        text: str,
        role: str = "agent",
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Convenience method to send a simple text message.
        
        Args:
            recipient_id: Target agent ID
            text: Text content
            role: Message role ("user" or "agent")
            session_id: Optional session ID
            metadata: Optional metadata
        """
        message = Message(
            role=role,
            parts=[TextPart(type="text", text=text)],
            metadata=metadata
        )
        return await self.send(recipient_id, message, session_id, metadata=metadata)
    
    async def send_text_to_group(
        self,
        group_id: str,
        text: str,
        role: str = "agent",
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Convenience method to send a simple text message to a group.
        """
        message = Message(
            role=role,
            parts=[TextPart(type="text", text=text)],
            metadata=metadata
        )
        return await self.send_to_group(group_id, message, session_id, metadata)
    
    # =========================================================================
    # Internal Transport Methods
    # =========================================================================
    
    async def _send_lan(
        self,
        recipient_id: str,
        message: Message,
        session_id: str,
        accepted_output_modes: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Send message via LAN A2A HTTP."""
        try:
            url = self.lan_registry.get(recipient_id)
            if not url:
                raise ValueError(f"No LAN URL for agent: {recipient_id}")
            
            # Build TaskSendParams
            payload = TaskSendParams(
                id=str(uuid4()),
                sessionId=session_id,
                message=message,
                acceptedOutputModes=accepted_output_modes or ["text", "json"],
                metadata=metadata
            )
            
            # Send via A2A client
            self._a2a_client.set_recipient(url=url)
            response = await self._a2a_client.send_task(payload.model_dump())
            
            logger.debug(f"[UnifiedMessenger] LAN send success to {recipient_id}")
            return {"transport": "lan", "response": response}
            
        except Exception as e:
            logger.error(f"[UnifiedMessenger] LAN send failed to {recipient_id}: {e}")
            raise
    
    def _send_lan_sync(
        self,
        recipient_id: str,
        message: Message,
        session_id: str,
        accepted_output_modes: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Synchronous LAN send."""
        try:
            url = self.lan_registry.get(recipient_id)
            if not url:
                raise ValueError(f"No LAN URL for agent: {recipient_id}")
            
            payload = TaskSendParams(
                id=str(uuid4()),
                sessionId=session_id,
                message=message,
                acceptedOutputModes=accepted_output_modes or ["text", "json"],
                metadata=metadata
            )
            
            self._a2a_client.set_recipient(url=url)
            response = self._a2a_client.sync_send_task(payload.model_dump())
            
            logger.debug(f"[UnifiedMessenger] LAN send (sync) success to {recipient_id}")
            return {"transport": "lan", "response": response}
            
        except Exception as e:
            logger.error(f"[UnifiedMessenger] LAN send (sync) failed to {recipient_id}: {e}")
            raise
    
    async def _send_wan(
        self,
        recipient_id: str,
        message: Message,
        session_id: str,
        accepted_output_modes: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Send message via WAN AWS AppSync."""
        try:
            sender_id = self.agent.card.id if self.agent.card else "unknown"
            
            response = await wan_a2a_send_message(
                mainwin=self.mainwin,
                channel_id=recipient_id,  # Use recipient_id as channel for direct messages
                message=message,
                sender_id=sender_id,
                recipient_id=recipient_id,
                session_id=session_id,
                accepted_output_modes=accepted_output_modes,
                metadata=metadata
            )
            
            logger.debug(f"[UnifiedMessenger] WAN send success to {recipient_id}")
            return {"transport": "wan", "response": response}
            
        except Exception as e:
            logger.error(f"[UnifiedMessenger] WAN send failed to {recipient_id}: {e}")
            raise
    
    def _send_wan_sync(
        self,
        recipient_id: str,
        message: Message,
        session_id: str,
        accepted_output_modes: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Synchronous WAN send."""
        try:
            sender_id = self.agent.card.id if self.agent.card else "unknown"
            
            response = wan_a2a_send_message_sync(
                mainwin=self.mainwin,
                channel_id=recipient_id,
                message=message,
                sender_id=sender_id,
                recipient_id=recipient_id,
                session_id=session_id,
                accepted_output_modes=accepted_output_modes,
                metadata=metadata
            )
            
            logger.debug(f"[UnifiedMessenger] WAN send (sync) success to {recipient_id}")
            return {"transport": "wan", "response": response}
            
        except Exception as e:
            logger.error(f"[UnifiedMessenger] WAN send (sync) failed to {recipient_id}: {e}")
            raise


# =============================================================================
# Factory Function
# =============================================================================

def create_unified_messenger(agent: 'EC_Agent', mainwin: 'MainWindow') -> UnifiedMessenger:
    """
    Factory function to create and initialize a UnifiedMessenger.
    
    This also syncs the LAN registry from MainWindow's agent list.
    
    Args:
        agent: The EC_Agent that will use this messenger
        mainwin: MainWindow instance
        
    Returns:
        Initialized UnifiedMessenger instance
    """
    messenger = UnifiedMessenger(agent, mainwin)
    messenger.sync_from_mainwin()
    return messenger
