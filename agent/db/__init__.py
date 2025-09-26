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
    Base,
    get_engine,
    get_session_factory,
    create_all_tables,
    drop_all_tables,
    ECAN_BASE_DB,
    MigrationManager
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
    DBAgentOrg,
    DBAgentSkill
)

# Database services
from .services import (
    SingletonMeta,
    BaseService,
    DBChatService,
    DBAgentService,
    DBSkillService,
    DBOrgService
)

# Database utilities
from .utils import (
    ContentSchema,
    ContentType
)

# Database manager
from .ec_db_mgr import (
    ECDBMgr,
    create_db_manager,
    initialize_ecan_database,
    get_db_manager  # Deprecated, for backward compatibility
)

# Note: Agent and skill models are now imported from .models above

__all__ = [
    # Core database utilities
    'get_engine',
    'get_session_factory',
    'create_all_tables',
    'drop_all_tables',
    'ECAN_BASE_DB',
    'MigrationManager',
    
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
    'DBSkillService',
    'DBOrgService',
    
    # Utils
    'ContentSchema',
    'ContentType',
    
    # Database manager
    'ECDBMgr',
    'create_db_manager',
    'initialize_ecan_database',
    'get_db_manager',  # Deprecated

    # Agent models
    'DBAgent',
    'DBAgentTask',
    'DBAgentTool',
    'DBAgentKnowledge',
    'DBAgentOrg',

    # Skills models
    'DBAgentSkill'
]
