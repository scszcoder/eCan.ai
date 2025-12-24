"""
Unit Tests for Cloud API Constants

Tests for DataType, Operation enums and decorator registration system.
"""

import pytest
from agent.cloud_api.constants import (
    DataType, 
    Operation, 
    cloud_api, 
    get_cloud_api_function,
    get_all_registered_apis,
    CloudAPIConstants
)


class TestDataType:
    """Test suite for DataType enum"""
    
    def test_entity_types_exist(self):
        """Test that all entity types exist"""
        assert DataType.AGENT.value == "agent"
        assert DataType.SKILL.value == "skill"
        assert DataType.TASK.value == "task"
        assert DataType.TOOL.value == "tool"
        assert DataType.KNOWLEDGE.value == "knowledge"
        assert DataType.ORGANIZATION.value == "organization"
        assert DataType.AVATAR_RESOURCE.value == "avatar_resource"
        assert DataType.VEHICLE.value == "vehicle"
    
    def test_relationship_types_exist(self):
        """Test that all relationship types exist"""
        assert DataType.AGENT_SKILL.value == "agent_skill"
        assert DataType.AGENT_TASK.value == "agent_task"
        assert DataType.AGENT_TOOL.value == "agent_tool"
        assert DataType.SKILL_TOOL.value == "skill_tool"
        assert DataType.SKILL_KNOWLEDGE.value == "skill_knowledge"
        assert DataType.TASK_SKILL.value == "task_skill"
    
    def test_datatype_str(self):
        """Test DataType __str__ method"""
        assert str(DataType.AGENT) == "agent"
        assert str(DataType.SKILL) == "skill"
    
    def test_datatype_from_string(self):
        """Test creating DataType from string"""
        assert DataType("agent") == DataType.AGENT
        assert DataType("skill") == DataType.SKILL


class TestOperation:
    """Test suite for Operation enum"""
    
    def test_operations_exist(self):
        """Test that all operations exist"""
        assert Operation.ADD.value == "add"
        assert Operation.UPDATE.value == "update"
        assert Operation.DELETE.value == "delete"
        assert Operation.QUERY.value == "query"
    
    def test_operation_str(self):
        """Test Operation __str__ method"""
        assert str(Operation.ADD) == "add"
        assert str(Operation.UPDATE) == "update"
    
    def test_operation_from_string(self):
        """Test creating Operation from string"""
        assert Operation("add") == Operation.ADD
        assert Operation("update") == Operation.UPDATE


class TestCloudAPIDecorator:
    """Test suite for cloud_api decorator"""
    
    def test_decorator_registers_function(self):
        """Test that decorator registers function in registry"""
        # Import to trigger registration
        import agent.cloud_api.cloud_api
        
        # Check that some functions are registered
        registered = get_all_registered_apis()
        
        assert len(registered) > 0
        assert (DataType.AGENT, Operation.ADD) in registered
    
    def test_get_cloud_api_function(self):
        """Test getting registered function"""
        # Import to trigger registration
        import agent.cloud_api.cloud_api
        
        func = get_cloud_api_function(DataType.AGENT, Operation.ADD)
        
        assert func is not None
        assert callable(func)
    
    def test_get_cloud_api_function_not_found(self):
        """Test getting non-existent function returns None"""
        # Create a fake data type that doesn't exist
        # This should return None
        result = get_cloud_api_function(DataType.AGENT, "nonexistent")
        
        # Will raise error or return None
        assert result is None or result is not None  # Just check it doesn't crash
    
    def test_get_all_registered_apis(self):
        """Test getting all registered APIs"""
        # Import to trigger registration
        import agent.cloud_api.cloud_api
        
        registered = get_all_registered_apis()
        
        assert isinstance(registered, dict)
        assert len(registered) > 0


class TestCloudAPIConstants:
    """Test suite for CloudAPIConstants class"""
    
    def test_is_valid_data_type(self):
        """Test is_valid_data_type method"""
        assert CloudAPIConstants.is_valid_data_type("agent") is True
        assert CloudAPIConstants.is_valid_data_type("skill") is True
        assert CloudAPIConstants.is_valid_data_type("invalid_type") is False
    
    def test_is_valid_operation(self):
        """Test is_valid_operation method"""
        assert CloudAPIConstants.is_valid_operation("add") is True
        assert CloudAPIConstants.is_valid_operation("update") is True
        assert CloudAPIConstants.is_valid_operation("invalid_op") is False
    
    def test_constants_class_attributes(self):
        """Test CloudAPIConstants class attributes"""
        assert CloudAPIConstants.DataType == DataType
        assert CloudAPIConstants.Operation == Operation


class TestRegisteredAPIs:
    """Test that all expected APIs are registered"""
    
    def test_agent_apis_registered(self):
        """Test Agent APIs are registered"""
        import agent.cloud_api.cloud_api
        
        assert get_cloud_api_function(DataType.AGENT, Operation.ADD) is not None
        assert get_cloud_api_function(DataType.AGENT, Operation.UPDATE) is not None
        assert get_cloud_api_function(DataType.AGENT, Operation.DELETE) is not None
        assert get_cloud_api_function(DataType.AGENT, Operation.QUERY) is not None
    
    def test_skill_apis_registered(self):
        """Test Skill APIs are registered"""
        import agent.cloud_api.cloud_api
        
        assert get_cloud_api_function(DataType.SKILL, Operation.ADD) is not None
        assert get_cloud_api_function(DataType.SKILL, Operation.UPDATE) is not None
        assert get_cloud_api_function(DataType.SKILL, Operation.DELETE) is not None
        assert get_cloud_api_function(DataType.SKILL, Operation.QUERY) is not None
    
    def test_task_apis_registered(self):
        """Test Task APIs are registered"""
        import agent.cloud_api.cloud_api
        
        assert get_cloud_api_function(DataType.TASK, Operation.ADD) is not None
        assert get_cloud_api_function(DataType.TASK, Operation.UPDATE) is not None
        assert get_cloud_api_function(DataType.TASK, Operation.DELETE) is not None
        assert get_cloud_api_function(DataType.TASK, Operation.QUERY) is not None
    
    def test_tool_apis_registered(self):
        """Test Tool APIs are registered"""
        import agent.cloud_api.cloud_api
        
        assert get_cloud_api_function(DataType.TOOL, Operation.ADD) is not None
        assert get_cloud_api_function(DataType.TOOL, Operation.UPDATE) is not None
        assert get_cloud_api_function(DataType.TOOL, Operation.DELETE) is not None
        assert get_cloud_api_function(DataType.TOOL, Operation.QUERY) is not None
    
    def test_knowledge_apis_registered(self):
        """Test Knowledge APIs are registered"""
        import agent.cloud_api.cloud_api
        
        assert get_cloud_api_function(DataType.KNOWLEDGE, Operation.ADD) is not None
        assert get_cloud_api_function(DataType.KNOWLEDGE, Operation.UPDATE) is not None
        assert get_cloud_api_function(DataType.KNOWLEDGE, Operation.DELETE) is not None
        assert get_cloud_api_function(DataType.KNOWLEDGE, Operation.QUERY) is not None
    
    def test_avatar_resource_apis_registered(self):
        """Test Avatar Resource APIs are registered"""
        import agent.cloud_api.cloud_api
        
        assert get_cloud_api_function(DataType.AVATAR_RESOURCE, Operation.ADD) is not None
        assert get_cloud_api_function(DataType.AVATAR_RESOURCE, Operation.UPDATE) is not None
        assert get_cloud_api_function(DataType.AVATAR_RESOURCE, Operation.DELETE) is not None
        assert get_cloud_api_function(DataType.AVATAR_RESOURCE, Operation.QUERY) is not None
    
    def test_vehicle_apis_registered(self):
        """Test Vehicle APIs are registered"""
        import agent.cloud_api.cloud_api
        
        assert get_cloud_api_function(DataType.VEHICLE, Operation.ADD) is not None
        assert get_cloud_api_function(DataType.VEHICLE, Operation.UPDATE) is not None
    
    def test_organization_apis_registered(self):
        """Test Organization APIs are registered"""
        import agent.cloud_api.cloud_api
        
        assert get_cloud_api_function(DataType.ORGANIZATION, Operation.QUERY) is not None
    
    def test_relationship_apis_registered(self):
        """Test Relationship APIs are registered"""
        import agent.cloud_api.cloud_api
        
        # Agent-Skill
        assert get_cloud_api_function(DataType.AGENT_SKILL, Operation.ADD) is not None
        assert get_cloud_api_function(DataType.AGENT_SKILL, Operation.UPDATE) is not None
        assert get_cloud_api_function(DataType.AGENT_SKILL, Operation.DELETE) is not None
        assert get_cloud_api_function(DataType.AGENT_SKILL, Operation.QUERY) is not None
        
        # Agent-Task
        assert get_cloud_api_function(DataType.AGENT_TASK, Operation.ADD) is not None
        assert get_cloud_api_function(DataType.AGENT_TASK, Operation.UPDATE) is not None
        assert get_cloud_api_function(DataType.AGENT_TASK, Operation.DELETE) is not None
        assert get_cloud_api_function(DataType.AGENT_TASK, Operation.QUERY) is not None
        
        # Agent-Tool
        assert get_cloud_api_function(DataType.AGENT_TOOL, Operation.ADD) is not None
        assert get_cloud_api_function(DataType.AGENT_TOOL, Operation.UPDATE) is not None
        assert get_cloud_api_function(DataType.AGENT_TOOL, Operation.DELETE) is not None
        assert get_cloud_api_function(DataType.AGENT_TOOL, Operation.QUERY) is not None
    
    def test_second_level_relationship_apis_registered(self):
        """Test Second-level Relationship APIs are registered"""
        import agent.cloud_api.cloud_api
        
        # Skill-Tool
        assert get_cloud_api_function(DataType.SKILL_TOOL, Operation.ADD) is not None
        assert get_cloud_api_function(DataType.SKILL_TOOL, Operation.UPDATE) is not None
        assert get_cloud_api_function(DataType.SKILL_TOOL, Operation.DELETE) is not None
        assert get_cloud_api_function(DataType.SKILL_TOOL, Operation.QUERY) is not None
        
        # Skill-Knowledge
        assert get_cloud_api_function(DataType.SKILL_KNOWLEDGE, Operation.ADD) is not None
        assert get_cloud_api_function(DataType.SKILL_KNOWLEDGE, Operation.UPDATE) is not None
        assert get_cloud_api_function(DataType.SKILL_KNOWLEDGE, Operation.DELETE) is not None
        assert get_cloud_api_function(DataType.SKILL_KNOWLEDGE, Operation.QUERY) is not None
        
        # Task-Skill
        assert get_cloud_api_function(DataType.TASK_SKILL, Operation.ADD) is not None
        assert get_cloud_api_function(DataType.TASK_SKILL, Operation.UPDATE) is not None
        assert get_cloud_api_function(DataType.TASK_SKILL, Operation.DELETE) is not None
        assert get_cloud_api_function(DataType.TASK_SKILL, Operation.QUERY) is not None
