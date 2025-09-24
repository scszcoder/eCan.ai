"""
Database package for eCan.ai agent system.

This package contains all database-related functionality including:
- Database models and schemas
- Database migration utilities
- Database services and business logic
- Database connection management
- Content schema definitions
"""

# Core database components
from .core import (
    get_engine,
    get_session_factory,
    create_all_tables,
    drop_all_tables,
    ECAN_BASE_DB,
    DBMigration
)

# Database models (new structure)
from .models import (
    Base,
    BaseModel,
    Chat,
    Member,
    Message,
    Attachment,
    ChatNotification,
    DBVersion,
    User,
    UserProfile,
    UserSession,
    MigrationLog,
    DBAgent,
    DBAgentTask,
    DBAgentTool,
    DBAgentKnowledge,
    DBAgentSkill
)

# Database services
from .services import (
    SingletonMeta,
    BaseService,
    DBChatService,
    DBAgentService,
    AgentService,
    AgentsDBService,
    DBSkillService,
    SkillService
)

# Database utilities
from .utils import (
    ContentSchema,
    ContentType
)

# Database manager
from .ecan_db_manager import (
    ECanDBManager,
    get_db_manager,
    initialize_ecan_database
)

# Note: Agent and skill models are now imported from .models above

__all__ = [
    # Core database utilities
    'get_engine',
    'get_session_factory',
    'create_all_tables',
    'drop_all_tables',
    'ECAN_BASE_DB',
    'DBMigration',
    
    # Database models
    'Base',
    'BaseModel',
    'Chat',
    'Member',
    'Message',
    'Attachment',
    'ChatNotification',
    'DBVersion',
    'User',
    'UserProfile',
    'UserSession',
    'MigrationLog',
    
    # Services
    'SingletonMeta',
    'BaseService',
    'DBChatService',
    'DBAgentService',
    'AgentService',
    'AgentsDBService',
    'DBSkillService',
    'SkillService',
    
    # Utils
    'ContentSchema',
    'ContentType',
    
    # Database manager
    'ECanDBManager',
    'get_db_manager',
    'initialize_ecan_database',

    # Agent models
    'DBAgent',
    'DBAgentTask',
    'DBAgentTool',
    'DBAgentKnowledge',

    # Skills models
    'DBAgentSkill'
]
