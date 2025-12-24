"""
Unit Tests for GraphQL Builder

Tests for the generic GraphQL mutation builder functionality.
"""

import pytest
import json
from datetime import datetime, date
from agent.cloud_api.constants import DataType, Operation
from agent.cloud_api.graphql_builder import GraphQLBuilder, build_mutation


class TestGraphQLBuilder:
    """Test suite for GraphQL Builder"""
    
    def test_builder_initialization(self):
        """Test GraphQLBuilder initialization"""
        builder = GraphQLBuilder()
        
        assert builder.schema_registry is not None
        assert builder.MUTATION_NAMES is not None
    
    def test_mutation_names_mapping(self):
        """Test that all expected mutation names are mapped"""
        builder = GraphQLBuilder()
        
        # Entity operations
        assert (DataType.AGENT, Operation.ADD) in builder.MUTATION_NAMES
        assert (DataType.SKILL, Operation.ADD) in builder.MUTATION_NAMES
        assert (DataType.TASK, Operation.ADD) in builder.MUTATION_NAMES
        assert (DataType.TOOL, Operation.ADD) in builder.MUTATION_NAMES
        assert (DataType.KNOWLEDGE, Operation.ADD) in builder.MUTATION_NAMES
        assert (DataType.AVATAR_RESOURCE, Operation.ADD) in builder.MUTATION_NAMES
        assert (DataType.VEHICLE, Operation.ADD) in builder.MUTATION_NAMES
        
        # Relationship operations
        assert (DataType.AGENT_SKILL, Operation.ADD) in builder.MUTATION_NAMES
        assert (DataType.AGENT_TASK, Operation.ADD) in builder.MUTATION_NAMES
        assert (DataType.AGENT_TOOL, Operation.ADD) in builder.MUTATION_NAMES
        assert (DataType.SKILL_TOOL, Operation.ADD) in builder.MUTATION_NAMES
        assert (DataType.SKILL_KNOWLEDGE, Operation.ADD) in builder.MUTATION_NAMES
        assert (DataType.TASK_SKILL, Operation.ADD) in builder.MUTATION_NAMES
    
    def test_build_add_mutation(self, sample_agent):
        """Test building ADD mutation"""
        mutation = build_mutation(DataType.AGENT, Operation.ADD, [sample_agent])
        
        assert "mutation MyMutation" in mutation
        assert "addAgents" in mutation
        assert "input:" in mutation
    
    def test_build_update_mutation(self, sample_agent):
        """Test building UPDATE mutation"""
        mutation = build_mutation(DataType.AGENT, Operation.UPDATE, [sample_agent])
        
        assert "mutation MyMutation" in mutation
        assert "updateAgents" in mutation
    
    def test_build_delete_mutation(self, sample_agent):
        """Test building DELETE mutation"""
        remove_order = {
            "agid": sample_agent["agid"],
            "owner": sample_agent["owner"],
            "reason": "Test deletion"
        }
        
        mutation = build_mutation(DataType.AGENT, Operation.DELETE, [remove_order])
        
        assert "mutation MyMutation" in mutation
        assert "removeAgents" in mutation
        assert "oid:" in mutation
    
    def test_build_mutation_with_settings(self, sample_task):
        """Test building mutation with settings parameter"""
        settings = {"testmode": True}
        
        mutation = build_mutation(DataType.TASK, Operation.ADD, [sample_task], settings)
        
        assert "mutation MyMutation" in mutation
        assert "settings:" in mutation
    
    def test_format_graphql_value_string(self):
        """Test formatting string values for GraphQL"""
        builder = GraphQLBuilder()
        
        result = builder._format_graphql_value("test string")
        assert result == '"test string"'
    
    def test_format_graphql_value_string_with_quotes(self):
        """Test formatting string values with quotes for GraphQL"""
        builder = GraphQLBuilder()
        
        result = builder._format_graphql_value('test "quoted" string')
        assert '\\"' in result
    
    def test_format_graphql_value_boolean(self):
        """Test formatting boolean values for GraphQL"""
        builder = GraphQLBuilder()
        
        assert builder._format_graphql_value(True) == "true"
        assert builder._format_graphql_value(False) == "false"
    
    def test_format_graphql_value_number(self):
        """Test formatting number values for GraphQL"""
        builder = GraphQLBuilder()
        
        assert builder._format_graphql_value(42) == "42"
        assert builder._format_graphql_value(3.14) == "3.14"
    
    def test_format_graphql_value_none(self):
        """Test formatting None values for GraphQL"""
        builder = GraphQLBuilder()
        
        result = builder._format_graphql_value(None)
        assert result == '""'
    
    def test_format_aws_datetime(self):
        """Test formatting AWS datetime values"""
        builder = GraphQLBuilder()
        
        dt = datetime(2024, 1, 15, 10, 30, 0)
        result = builder._format_aws_datetime(dt)
        
        assert "2024-01-15" in result
    
    def test_format_aws_date(self):
        """Test formatting AWS date values"""
        builder = GraphQLBuilder()
        
        d = date(2024, 1, 15)
        result = builder._format_aws_datetime(d)
        
        assert result == "2024-01-15"
    
    def test_build_graphql_object(self):
        """Test building GraphQL object from dict"""
        builder = GraphQLBuilder()
        
        data = {
            "name": "Test",
            "count": 5,
            "active": True
        }
        
        result = builder._build_graphql_object(data)
        
        assert "name:" in result
        assert '"Test"' in result
        assert "count: 5" in result
        assert "active: true" in result
    
    def test_build_graphql_object_skips_none(self):
        """Test that None values are skipped in GraphQL object"""
        builder = GraphQLBuilder()
        
        data = {
            "name": "Test",
            "description": None,
            "count": 5
        }
        
        result = builder._build_graphql_object(data)
        
        assert "name:" in result
        assert "description:" not in result
        assert "count:" in result
    
    def test_build_mutation_multiple_items(self, sample_agent):
        """Test building mutation with multiple items"""
        agent2 = sample_agent.copy()
        agent2["name"] = "Agent 2"
        
        mutation = build_mutation(DataType.AGENT, Operation.ADD, [sample_agent, agent2])
        
        assert "mutation MyMutation" in mutation
        assert "addAgents" in mutation
        # Should have comma-separated items
        assert "}, {" in mutation or "},\n{" in mutation or "} , {" in mutation or "},{" in mutation
    
    def test_build_remove_mutation_extracts_id(self):
        """Test that remove mutation correctly extracts ID from various fields"""
        builder = GraphQLBuilder()
        
        # Test with agid
        remove_order = {"agid": "agent_123", "owner": "user", "reason": "test"}
        mutation = builder._build_remove_mutation("removeAgents", [remove_order])
        assert 'oid: "agent_123"' in mutation
        
        # Test with skid
        remove_order = {"skid": "skill_456", "owner": "user", "reason": "test"}
        mutation = builder._build_remove_mutation("removeAgentSkills", [remove_order])
        assert 'oid: "skill_456"' in mutation
    
    def test_unsupported_operation_raises_error(self):
        """Test that unsupported operation raises ValueError"""
        builder = GraphQLBuilder()
        
        # Create a fake data type/operation combination that doesn't exist
        with pytest.raises(ValueError):
            builder.build_mutation(DataType.AGENT, "invalid_operation", [{}])


class TestGraphQLBuilderLegacyFunctions:
    """Test legacy wrapper functions for backward compatibility"""
    
    def test_gen_add_agents_string(self, sample_agent):
        """Test legacy gen_add_agents_string function"""
        from agent.cloud_api.graphql_builder import gen_add_agents_string
        
        mutation = gen_add_agents_string([sample_agent])
        
        assert "addAgents" in mutation
    
    def test_gen_update_agents_string(self, sample_agent):
        """Test legacy gen_update_agents_string function"""
        from agent.cloud_api.graphql_builder import gen_update_agents_string
        
        mutation = gen_update_agents_string([sample_agent])
        
        assert "updateAgents" in mutation
    
    def test_gen_remove_agents_string(self, sample_agent):
        """Test legacy gen_remove_agents_string function"""
        from agent.cloud_api.graphql_builder import gen_remove_agents_string
        
        remove_order = {"agid": sample_agent["agid"], "owner": sample_agent["owner"], "reason": "test"}
        mutation = gen_remove_agents_string([remove_order])
        
        assert "removeAgents" in mutation
    
    def test_gen_add_agent_skills_string(self, sample_skill):
        """Test legacy gen_add_agent_skills_string function"""
        from agent.cloud_api.graphql_builder import gen_add_agent_skills_string
        
        mutation = gen_add_agent_skills_string([sample_skill])
        
        assert "addAgentSkills" in mutation
    
    def test_gen_add_agent_tasks_string(self, sample_task):
        """Test legacy gen_add_agent_tasks_string function"""
        from agent.cloud_api.graphql_builder import gen_add_agent_tasks_string
        
        mutation = gen_add_agent_tasks_string([sample_task])
        
        assert "addAgentTasks" in mutation
    
    def test_gen_add_agent_tools_string(self, sample_tool):
        """Test legacy gen_add_agent_tools_string function"""
        from agent.cloud_api.graphql_builder import gen_add_agent_tools_string
        
        mutation = gen_add_agent_tools_string([sample_tool])
        
        assert "addAgentTools" in mutation
