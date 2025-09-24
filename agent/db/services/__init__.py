"""
Database services module.

This module contains service classes that provide high-level
database operations for different business domains.
"""

from .singleton import SingletonMeta
from .base_service import BaseService
from .db_chat_service import DBChatService
from .db_agent_service import DBAgentService, AgentService, AgentsDBService
from .db_skill_service import DBSkillService, SkillService

__all__ = [
    'SingletonMeta',
    'BaseService',
    'DBChatService',
    'DBAgentService',
    'AgentService',      # Backward compatibility alias
    'AgentsDBService',   # Legacy compatibility alias
    'DBSkillService',
    'SkillService'       # Backward compatibility alias
]
