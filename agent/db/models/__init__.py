"""
Database models package for eCan.ai.

This package contains all database models organized by functionality:
- base_model: Base classes and mixins for all models
- chat_model: Chat, Member, ChatNotification models
- message_model: Message, Attachment models  
- user_model: User, UserProfile, UserSession models
- version_model: DBVersion, MigrationLog models
- agent_model: DBAgent model
- task_model: DBAgentTask model
- tool_model: DBAgentTool model
- knowledge_model: DBAgentKnowledge model
- org_model: DBOrg model
- skill_model: DBAgentSkill model
- vehicle_model: DBAgentVehicle model
- association_models: Association tables for many-to-many relationships

All models inherit from BaseModel which provides common functionality
like timestamps, UUID primary keys, and utility methods.
"""

# Import base classes and mixins
from .base_model import (
    Base,
    BaseModel,
    TimestampMixin,
    SoftDeleteMixin,
    ExtensibleMixin
)

# Import chat-related models
from .chat_model import (
    Chat,
    Member,
    ChatNotification
)

# Import message-related models
from .message_model import (
    Message,
    Attachment
)

# Import user-related models
from .user_model import (
    User,
    UserProfile,
    UserSession
)

# Import version-related models
from .version_model import (
    DBVersion,
    MigrationLog
)

# Import agent-related models
from .agent_model import (
    DBAgent
)

# Import task-related models
from .task_model import (
    DBAgentTask
)

# Import tool-related models
from .tool_model import (
    DBAgentTool
)

# Import knowledge-related models
from .knowledge_model import (
    DBAgentKnowledge
)

# Import organization-related models
from .org_model import (
    DBAgentOrg
)

# Import skill-related models
from .skill_model import (
    DBAgentSkill
)

# Import vehicle-related models
from .vehicle_model import (
    DBAgentVehicle
)

# Import avatar-related models
from .avatar_model import (
    DBAvatarResource
)

# Import association models
from .association_models import (
    DBAgentOrgRel,
    DBAgentSkillRel,
    DBAgentTaskRel,
    DBSkillToolRel,
    DBAgentSkillKnowledgeRel,
    DBAgentTaskSkillRel
)

# Export all models and base classes
__all__ = [
    # Base classes and mixins
    'Base',
    'BaseModel',
    'TimestampMixin',
    'SoftDeleteMixin',
    'ExtensibleMixin',
    
    # Chat models
    'Chat',
    'Member',
    'ChatNotification',
    
    # Message models
    'Message',
    'Attachment',
    
    # User models
    'User',
    'UserProfile',
    'UserSession',
    
    # Version models
    'DBVersion',
    'MigrationLog',

    # Agent models
    'DBAgent',
    'DBAgentTask',
    'DBAgentTool',
    'DBAgentKnowledge',

    # Organization models
    'DBAgentOrg',

    # Skill models
    'DBAgentSkill',
    
    # Vehicle models
    'DBAgentVehicle',
    
    # Avatar models
    'DBAvatarResource',
    
    # Association models
    'DBAgentOrgRel',
    'DBAgentSkillRel',
    'DBAgentTaskRel',
    'DBSkillToolRel',
    'DBAgentSkillKnowledgeRel',
    'DBAgentTaskSkillRel'
]

# Model registry for easy access
MODEL_REGISTRY = {
    'Chat': Chat,
    'Member': Member,
    'ChatNotification': ChatNotification,
    'Message': Message,
    'Attachment': Attachment,
    'User': User,
    'UserProfile': UserProfile,
    'UserSession': UserSession,
    'DBVersion': DBVersion,
    'MigrationLog': MigrationLog,
    'DBAgent': DBAgent,
    'DBAgentTask': DBAgentTask,
    'DBAgentTool': DBAgentTool,
    'DBAgentKnowledge': DBAgentKnowledge,
    'DBAgentOrg': DBAgentOrg,
    'DBAgentSkill': DBAgentSkill,
    'DBAgentVehicle': DBAgentVehicle,
    'DBAvatarResource': DBAvatarResource,
    'DBAgentOrgRel': DBAgentOrgRel,
    'DBAgentSkillRel': DBAgentSkillRel,
    'DBAgentTaskRel': DBAgentTaskRel,
    'DBSkillToolRel': DBSkillToolRel,
    'DBAgentSkillKnowledgeRel': DBAgentSkillKnowledgeRel,
    'DBAgentTaskSkillRel': DBAgentTaskSkillRel
}

def get_model(model_name: str):
    """
    Get a model class by name.
    
    Args:
        model_name (str): Name of the model class
        
    Returns:
        Model class or None if not found
    """
    return MODEL_REGISTRY.get(model_name)

def get_all_models():
    """
    Get all model classes.
    
    Returns:
        dict: Dictionary of model name -> model class
    """
    return MODEL_REGISTRY.copy()

def get_table_names():
    """
    Get all table names from registered models.
    
    Returns:
        list: List of table names
    """
    table_names = []
    for model_class in MODEL_REGISTRY.values():
        if hasattr(model_class, '__tablename__'):
            table_names.append(model_class.__tablename__)
    return table_names
