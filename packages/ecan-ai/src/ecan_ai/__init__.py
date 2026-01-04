"""
eCan.ai - AI Agent Framework for Automation

This package provides the core library for building and running AI agents.

Example usage:
    from ecan_ai import EcanAI
    
    ecan = EcanAI()
    agents = ecan.agents.list()
"""

__version__ = "0.1.0"

# =============================================================================
# Phase 1: Re-export from existing locations
# These imports will be updated in later phases as code is migrated
# =============================================================================

# Database services (from agent/db/services/)
try:
    from agent.db.services.db_agent_service import DBAgentService
    from agent.db.services.db_skill_service import DBSkillService
    from agent.db.services.db_task_service import DBTaskService
    from agent.db.services.db_vehicle_service import DBVehicleService
    from agent.db.services.db_org_service import DBOrgService
    from agent.db.services.db_chat_service import DBChatService
    from agent.db.services.base_service import BaseService
    from agent.db.services.singleton import SingletonMeta
except ImportError:
    # Allow import even if not all dependencies are available
    DBAgentService = None
    DBSkillService = None
    DBTaskService = None
    DBVehicleService = None
    DBOrgService = None
    DBChatService = None
    BaseService = None
    SingletonMeta = None

# Database models (from agent/db/models/)
try:
    from agent.db.models.agent_model import DBAgent
    from agent.db.models.skill_model import DBAgentSkill
    from agent.db.models.task_model import DBAgentTask
    from agent.db.models.vehicle_model import DBAgentVehicle
    from agent.db.models.knowledge_model import DBAgentKnowledge
except ImportError:
    DBAgent = None
    DBAgentSkill = None
    DBAgentTask = None
    DBAgentVehicle = None
    DBAgentKnowledge = None

# A2A Task Manager (from agent/a2a/)
try:
    from agent.a2a.common.server.task_manager import TaskManager, InMemoryTaskManager
    from agent.a2a.langgraph_agent.task_manager import AgentTaskManager
except ImportError:
    TaskManager = None
    InMemoryTaskManager = None
    AgentTaskManager = None

# =============================================================================
# Public API - will be expanded in later phases
# =============================================================================

__all__ = [
    # Version
    "__version__",
    
    # Database services
    "DBAgentService",
    "DBSkillService", 
    "DBTaskService",
    "DBVehicleService",
    "DBOrgService",
    "DBChatService",
    "BaseService",
    "SingletonMeta",
    
    # Database models
    "DBAgent",
    "DBAgentSkill",
    "DBAgentTask",
    "DBAgentVehicle",
    "DBAgentKnowledge",
    
    # Task managers
    "TaskManager",
    "InMemoryTaskManager",
    "AgentTaskManager",
]
