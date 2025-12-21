"""
UserContext - Per-User State Container

This class holds all user-specific state that was previously stored in MainWindow.
In web deployment mode, each user session gets its own UserContext instance.

The UserContext is designed to:
1. Mirror the relevant state from MainWindow
2. Be serializable for future Option A (external state store)
3. Support the same interface that handlers expect
"""

from __future__ import annotations
from typing import TYPE_CHECKING, Optional, List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4
import asyncio

if TYPE_CHECKING:
    from agent.ec_agent import EC_Agent
    from agent.ec_skills.ec_skill import EC_Skill
    from agent.vehicles.vehicle import Vehicle
    from config.config_manager import ConfigManager


@dataclass
class UserContext:
    """
    Container for per-user state in multi-user web deployment.
    
    This mirrors the user-specific attributes from MainWindow that handlers need.
    In desktop mode, this wraps MainWindow. In web mode, each user gets their own.
    
    Attributes:
        user_id: Unique identifier for the user (e.g., email or Cognito sub)
        session_id: Current session identifier
        username: Display username
        auth_token: Current authentication token
        agents: List of user's EC_Agent instances
        agent_skills: List of user's skills
        vehicles: List of user's vehicles
        mcp_tools_schemas: MCP tool schemas
        config_manager: User's configuration manager
        wan_chat_msg_queue: Queue for WAN chat messages
    """
    
    # Identity
    user_id: str
    session_id: str = field(default_factory=lambda: str(uuid4()))
    username: str = ""
    auth_token: str = ""
    
    # User data (mirrors MainWindow)
    agents: List[Any] = field(default_factory=list)  # List[EC_Agent]
    agent_skills: List[Any] = field(default_factory=list)  # List[EC_Skill]
    vehicles: List[Any] = field(default_factory=list)  # List[Vehicle]
    mcp_tools_schemas: List[Any] = field(default_factory=list)
    
    # Configuration
    config_manager: Optional[Any] = None  # ConfigManager
    
    # Database and services
    ec_db_mgr: Optional[Any] = None
    db_chat_service: Optional[Any] = None
    vehicle_service: Optional[Any] = None
    lightrag_server: Optional[Any] = None
    llm: Optional[Any] = None
    
    # Tasks and temp storage
    agent_tasks: List[Any] = field(default_factory=list)
    temp_dir: str = ""
    
    # Message queues
    wan_chat_msg_queue: Optional[asyncio.Queue] = None
    
    # Session metadata
    created_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)
    is_dirty: bool = False  # Track if state needs saving (for future Option A)
    
    # WAN connection state
    _wan_connected: bool = False
    _wan_msg_subscribed: bool = False
    
    def __post_init__(self):
        """Initialize after dataclass creation"""
        if self.wan_chat_msg_queue is None:
            self.wan_chat_msg_queue = asyncio.Queue()
    
    # ==========================================================================
    # MainWindow-compatible interface
    # ==========================================================================
    
    def get_auth_token(self) -> str:
        """Get current auth token (MainWindow compatibility)"""
        return self.auth_token
    
    def set_auth_token(self, token: str) -> None:
        """Set auth token"""
        self.auth_token = token
        self._mark_dirty()
    
    def set_wan_connected(self, connected: bool) -> None:
        """Set WAN connection status (MainWindow compatibility)"""
        self._wan_connected = connected
    
    def set_wan_msg_subscribed(self, subscribed: bool) -> None:
        """Set WAN message subscription status (MainWindow compatibility)"""
        self._wan_msg_subscribed = subscribed
    
    @property
    def is_wan_connected(self) -> bool:
        """Check if WAN is connected"""
        return self._wan_connected
    
    @property
    def is_wan_msg_subscribed(self) -> bool:
        """Check if subscribed to WAN messages"""
        return self._wan_msg_subscribed
    
    # ==========================================================================
    # Activity tracking
    # ==========================================================================
    
    def update_activity(self) -> None:
        """Update last activity timestamp"""
        self.last_activity = datetime.now()
    
    def _mark_dirty(self) -> None:
        """Mark context as needing save (for future Option A)"""
        self.is_dirty = True
        self.update_activity()
    
    # ==========================================================================
    # Serialization (for future Option A - external state store)
    # ==========================================================================
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize context to dictionary for external storage.
        
        Note: This is a placeholder for future Option A implementation.
        Complex objects (agents, skills) need their own to_dict methods.
        """
        return {
            "user_id": self.user_id,
            "session_id": self.session_id,
            "username": self.username,
            # Don't serialize auth_token for security
            "agents": [a.to_dict() if hasattr(a, 'to_dict') else str(a) for a in self.agents],
            "agent_skills": [s.to_dict() if hasattr(s, 'to_dict') else str(s) for s in self.agent_skills],
            "vehicles": [v.genJson() if hasattr(v, 'genJson') else str(v) for v in self.vehicles],
            "created_at": self.created_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UserContext':
        """
        Deserialize context from dictionary.
        
        Note: This is a placeholder for future Option A implementation.
        Complex objects need to be reconstructed from their serialized forms.
        """
        ctx = cls(
            user_id=data["user_id"],
            session_id=data.get("session_id", str(uuid4())),
            username=data.get("username", ""),
        )
        ctx.created_at = datetime.fromisoformat(data["created_at"]) if "created_at" in data else datetime.now()
        ctx.last_activity = datetime.fromisoformat(data["last_activity"]) if "last_activity" in data else datetime.now()
        
        # Note: agents, skills, vehicles need proper deserialization
        # This will be implemented in Option A migration
        
        return ctx
    
    # ==========================================================================
    # Convenience methods
    # ==========================================================================
    
    def get_agent_by_id(self, agent_id: str) -> Optional[Any]:
        """Find agent by ID"""
        for agent in self.agents:
            if hasattr(agent, 'card') and hasattr(agent.card, 'id'):
                if agent.card.id == agent_id:
                    return agent
        return None
    
    def add_agent(self, agent: Any) -> None:
        """Add an agent to the context"""
        self.agents.append(agent)
        self._mark_dirty()
    
    def remove_agent(self, agent_id: str) -> bool:
        """Remove an agent by ID. Returns True if found and removed."""
        original_count = len(self.agents)
        self.agents = [a for a in self.agents if not (hasattr(a, 'card') and hasattr(a.card, 'id') and a.card.id == agent_id)]
        if len(self.agents) < original_count:
            self._mark_dirty()
            return True
        return False
    
    def get_all_tasks(self) -> List[Any]:
        """Get all tasks from all agents"""
        all_tasks = []
        for agent in self.agents:
            if hasattr(agent, 'tasks'):
                all_tasks.extend(agent.tasks)
        return all_tasks
    
    def __repr__(self) -> str:
        return (
            f"UserContext(user_id={self.user_id!r}, "
            f"session_id={self.session_id!r}, "
            f"agents={len(self.agents)}, "
            f"skills={len(self.agent_skills)})"
        )
