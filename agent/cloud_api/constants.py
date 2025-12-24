"""
Cloud API Constants - Cloud API Constant Definitions

Defines data type and operation type enums, and decorator registration system.
"""

from enum import Enum
from typing import Callable, Dict, Tuple


class DataType(str, Enum):
    """Data type enumeration - Standard naming convention
    
    Naming Convention:
    - Entity types: AGENT, SKILL, TASK, TOOL, KNOWLEDGE, ORGANIZATION
    - Relationship types: AGENT_SKILL, AGENT_TASK, AGENT_TOOL, SKILL_TOOL, etc.
    
    This makes it clear whether we're dealing with an entity or a relationship.
    """
    # ============================================================================
    # Entity Types (Independent entities)
    # ============================================================================
    AGENT = 'agent'              # Agent entity
    SKILL = 'skill'              # Skill entity
    TASK = 'task'                # Task entity
    TOOL = 'tool'                # Tool entity
    KNOWLEDGE = 'knowledge'      # Knowledge entity
    ORGANIZATION = 'organization' # Organization entity
    AVATAR_RESOURCE = 'avatar_resource' # Avatar resource entity
    VEHICLE = 'vehicle'          # Vehicle entity
    
    # ============================================================================
    # First-Level Relationships (Agent relationships with other entities)
    # ============================================================================
    AGENT_SKILL = 'agent_skill'  # Agent-Skill relationship
    AGENT_TASK = 'agent_task'    # Agent-Task relationship
    AGENT_TOOL = 'agent_tool'    # Agent-Tool relationship
    
    # ============================================================================
    # Second-Level Relationships (Nested relationships)
    # ============================================================================
    SKILL_TOOL = 'skill_tool'              # Skill-Tool relationship
    SKILL_KNOWLEDGE = 'skill_knowledge'    # Skill-Knowledge relationship
    TASK_SKILL = 'task_skill'              # Task-Skill relationship
    
    def __str__(self):
        return self.value


class Operation(str, Enum):
    """Operation type enumeration"""
    ADD = 'add'
    UPDATE = 'update'
    DELETE = 'delete'
    QUERY = 'query'
    
    def __str__(self):
        return self.value


# Global registry
_CLOUD_API_REGISTRY: Dict[Tuple[DataType, Operation], Callable] = {}


def cloud_api(data_type: DataType, operation: Operation):
    """
    Cloud API function decorator
    
    Usage:
        @cloud_api(DataType.SKILL, Operation.ADD)
        def send_add_agent_skills_request_to_cloud(session, data, token, endpoint):
            ...
    
    Args:
        data_type: Data type
        operation: Operation type
    """
    def decorator(func: Callable) -> Callable:
        # Register function
        _CLOUD_API_REGISTRY[(data_type, operation)] = func
        return func
    return decorator


def get_cloud_api_function(data_type: DataType, operation: Operation) -> Callable:
    """
    Get cloud API function
    
    Args:
        data_type: Data type
        operation: Operation type
        
    Returns:
        Cloud API function, returns None if not found
    """
    return _CLOUD_API_REGISTRY.get((data_type, operation))


def get_all_registered_apis() -> Dict[Tuple[DataType, Operation], Callable]:
    """Get all registered API functions"""
    return _CLOUD_API_REGISTRY.copy()


# Convenience access (optional)
class CloudAPIConstants:
    """Cloud API constants collection"""
    
    # Data types
    DataType = DataType
    
    # Operation types
    Operation = Operation
    
    @staticmethod
    def is_valid_data_type(data_type: str) -> bool:
        """Check if data type is valid"""
        try:
            DataType(data_type)
            return True
        except ValueError:
            return False
    
    @staticmethod
    def is_valid_operation(operation: str) -> bool:
        """Check if operation type is valid"""
        try:
            Operation(operation)
            return True
        except ValueError:
            return False
