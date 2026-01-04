"""
eCan.ai - AI Agent Framework for Automation

This package provides the core library for building and running AI agents.

Example usage:
    from ecan_ai import EcanAI
    
    ecan = EcanAI(db_path="path/to/data")
    agents = ecan.agents.list()
    agent = ecan.agents.create(name="MyAgent", description="An AI agent")
"""

__version__ = "0.1.0"

# =============================================================================
# Main API - EcanAI facade class
# =============================================================================

from .core import EcanAI

# =============================================================================
# Database layer (advanced usage)
# =============================================================================

# Database services (from ecan_ai.db.services/)
try:
    from .db.services.db_agent_service import DBAgentService
    from .db.services.db_skill_service import DBSkillService
    from .db.services.db_task_service import DBTaskService
    from .db.services.db_vehicle_service import DBVehicleService
    from .db.services.db_org_service import DBOrgService
    from .db.services.db_chat_service import DBChatService
    from .db.services.base_service import BaseService
    from .db.services.singleton import SingletonMeta
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

# Database models (from ecan_ai.db.models/)
try:
    from .db.models.agent_model import DBAgent
    from .db.models.skill_model import DBAgentSkill
    from .db.models.task_model import DBAgentTask
    from .db.models.vehicle_model import DBAgentVehicle
    from .db.models.knowledge_model import DBAgentKnowledge
except ImportError:
    DBAgent = None
    DBAgentSkill = None
    DBAgentTask = None
    DBAgentVehicle = None
    DBAgentKnowledge = None

# A2A Task Manager (still from agent/a2a/ - will be migrated in later phase)
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
    # Main API
    "EcanAI",
    
    # Version
    "__version__",
    
    # Database services (advanced)
    "DBAgentService",
    "DBSkillService", 
    "DBTaskService",
    "DBVehicleService",
    "DBOrgService",
    "DBChatService",
    "BaseService",
    "SingletonMeta",
    
    # Database models (advanced)
    "DBAgent",
    "DBAgentSkill",
    "DBAgentTask",
    "DBAgentVehicle",
    "DBAgentKnowledge",
    
    # Task managers (advanced)
    "TaskManager",
    "InMemoryTaskManager",
    "AgentTaskManager",
]
