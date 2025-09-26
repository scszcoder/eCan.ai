"""
Database services module.

This module contains service classes that provide high-level
database operations for different business domains.
"""

from .singleton import SingletonMeta
from .base_service import BaseService

# Main database services with db_ prefix
from .db_chat_service import DBChatService
from .db_agent_service import DBAgentService
from .db_skill_service import DBSkillService
from .db_org_service import DBOrgService
from .db_vehicle_service import DBVehicleService
from .db_task_service import DBTaskService

__all__ = [
    'SingletonMeta',
    'BaseService',
    'DBChatService',
    'DBAgentService',
    'DBSkillService',
    'DBOrgService',
    'DBVehicleService',
    'DBTaskService'
]
