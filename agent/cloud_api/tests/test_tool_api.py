"""
Unit Tests for Tool Cloud API Operations

Tests for add, update, delete, and query operations on the AgentTool table.
"""

import pytest
import json
from unittest.mock import patch, MagicMock
from agent.cloud_api.constants import DataType, Operation


class TestToolAPI:
    """Test suite for Tool cloud API operations"""
    
    def test_gen_add_tools_string(self, sample_tool):
        """Test generating GraphQL mutation string for adding tools"""
        from agent.cloud_api.graphql_builder import build_mutation
        
        mutation = build_mutation(DataType.TOOL, Operation.ADD, [sample_tool])
        
        assert "mutation MyMutation" in mutation
        assert "addAgentTools" in mutation
        assert "input:" in mutation
    
    def test_gen_update_tools_string(self, sample_tool):
        """Test generating GraphQL mutation string for updating tools"""
        from agent.cloud_api.graphql_builder import build_mutation
        
        mutation = build_mutation(DataType.TOOL, Operation.UPDATE, [sample_tool])
        
        assert "mutation MyMutation" in mutation
        assert "updateAgentTools" in mutation
    
    def test_gen_remove_tools_string(self, sample_tool):
        """Test generating GraphQL mutation string for removing tools"""
        from agent.cloud_api.graphql_builder import build_mutation
        
        remove_order = {
            "oid": sample_tool["toolid"],
            "owner": sample_tool["owner"],
            "reason": "Test deletion"
        }
        
        mutation = build_mutation(DataType.TOOL, Operation.DELETE, [remove_order])
        
        assert "mutation MyMutation" in mutation
        assert "removeAgentTools" in mutation
    
    @patch('agent.cloud_api.cloud_api.appsync_http_request')
    def test_send_add_tools_request_to_cloud(self, mock_request, mock_session, mock_token, mock_endpoint, sample_tool):
        """Test sending add tools request to cloud"""
        from agent.cloud_api.cloud_api import send_add_tools_request_to_cloud
        
        mock_request.return_value = {
            "data": {
                "addAgentTools": '{"success": true, "count": 1}'
            }
        }
        
        result = send_add_tools_request_to_cloud(mock_session, [sample_tool], mock_token, mock_endpoint)
        
        mock_request.assert_called_once()
        assert result is not None
    
    @patch('agent.cloud_api.cloud_api.appsync_http_request')
    def test_send_update_tools_request_to_cloud(self, mock_request, mock_session, mock_token, mock_endpoint, sample_tool):
        """Test sending update tools request to cloud"""
        from agent.cloud_api.cloud_api import send_update_tools_request_to_cloud
        
        mock_request.return_value = {
            "data": {
                "updateAgentTools": '{"success": true, "count": 1}'
            }
        }
        
        result = send_update_tools_request_to_cloud(mock_session, [sample_tool], mock_token, mock_endpoint)
        
        mock_request.assert_called_once()
        assert result is not None
    
    @patch('agent.cloud_api.cloud_api.appsync_http_request')
    def test_send_remove_tools_request_to_cloud(self, mock_request, mock_session, mock_token, mock_endpoint, sample_tool):
        """Test sending remove tools request to cloud"""
        from agent.cloud_api.cloud_api import send_remove_tools_request_to_cloud
        
        mock_request.return_value = {
            "data": {
                "removeAgentTools": '{"success": true, "count": 1}'
            }
        }
        
        remove_order = {
            "tool_id": sample_tool["toolid"],
            "owner": sample_tool["owner"],
            "reason": "Test deletion"
        }
        
        result = send_remove_tools_request_to_cloud(mock_session, [remove_order], mock_token, mock_endpoint)
        
        mock_request.assert_called_once()
        assert result is not None
    
    @patch('agent.cloud_api.cloud_api.appsync_http_request')
    def test_send_query_tools_entity_to_cloud(self, mock_request, mock_session, mock_token, mock_endpoint):
        """Test sending query tools request to cloud"""
        from agent.cloud_api.cloud_api import send_query_tools_entity_to_cloud
        
        mock_request.return_value = {
            "data": {
                "queryAgentTools": '[]'
            }
        }
        
        q_settings = {"byowneruser": True}
        result = send_query_tools_entity_to_cloud(mock_session, mock_token, q_settings, mock_endpoint)
        
        mock_request.assert_called_once()
        assert result is not None
    
    def test_cloud_api_service_tool_sync(self, sample_tool):
        """Test CloudAPIService for tool sync operations"""
        from agent.cloud_api.cloud_api_service import CloudAPIService
        from agent.cloud_api.constants import DataType
        
        service = CloudAPIService(DataType.TOOL)
        
        assert service.data_type == DataType.TOOL
        assert service.schema is not None


class TestAgentToolRelationAPI:
    """Test suite for Agent-Tool relationship operations"""
    
    def test_gen_add_agent_tool_relations_string(self, sample_agent_tool_relation):
        """Test generating GraphQL mutation string for adding agent-tool relations"""
        from agent.cloud_api.graphql_builder import build_mutation
        
        mutation = build_mutation(DataType.AGENT_TOOL, Operation.ADD, [sample_agent_tool_relation])
        
        assert "mutation MyMutation" in mutation
        assert "addAgentToolRelations" in mutation
    
    @patch('agent.cloud_api.cloud_api.appsync_http_request')
    def test_send_add_agent_tool_relations_request_to_cloud(self, mock_request, mock_session, mock_token, mock_endpoint, sample_agent_tool_relation):
        """Test sending add agent-tool relations request to cloud"""
        from agent.cloud_api.cloud_api import send_add_agent_tool_relations_request_to_cloud
        
        mock_request.return_value = {
            "data": {
                "addAgentToolRelations": '{"success": true, "count": 1}'
            }
        }
        
        result = send_add_agent_tool_relations_request_to_cloud(
            mock_session, [sample_agent_tool_relation], mock_token, mock_endpoint
        )
        
        mock_request.assert_called_once()
        assert result is not None
    
    @patch('agent.cloud_api.cloud_api.appsync_http_request')
    def test_send_query_agent_tool_relations_request_to_cloud(self, mock_request, mock_session, mock_token, mock_endpoint):
        """Test sending query agent-tool relations request to cloud"""
        from agent.cloud_api.cloud_api import send_query_agent_tool_relations_request_to_cloud
        
        mock_request.return_value = {
            "data": {
                "queryAgentToolRelations": '[]'
            }
        }
        
        q_settings = {"byowneruser": True}
        result = send_query_agent_tool_relations_request_to_cloud(mock_session, mock_token, q_settings, mock_endpoint)
        
        mock_request.assert_called_once()
        assert result is not None


class TestSkillToolRelationAPI:
    """Test suite for Skill-Tool relationship operations"""
    
    def test_gen_add_skill_tool_relations_string(self, sample_skill_tool_relation):
        """Test generating GraphQL mutation string for adding skill-tool relations"""
        from agent.cloud_api.graphql_builder import build_mutation
        
        mutation = build_mutation(DataType.SKILL_TOOL, Operation.ADD, [sample_skill_tool_relation])
        
        assert "mutation MyMutation" in mutation
        assert "addSkillToolRelations" in mutation
    
    @patch('agent.cloud_api.cloud_api.appsync_http_request')
    def test_send_add_skill_tool_relations_to_cloud(self, mock_request, mock_session, mock_token, mock_endpoint, sample_skill_tool_relation):
        """Test sending add skill-tool relations request to cloud"""
        from agent.cloud_api.cloud_api import send_add_skill_tool_relations_to_cloud
        
        mock_request.return_value = {
            "data": {
                "addSkillToolRelations": '{"success": true, "count": 1}'
            }
        }
        
        result = send_add_skill_tool_relations_to_cloud(
            mock_session, [sample_skill_tool_relation], mock_token, mock_endpoint
        )
        
        mock_request.assert_called_once()
        assert result is not None
    
    @patch('agent.cloud_api.cloud_api.appsync_http_request')
    def test_send_query_skill_tool_relations_to_cloud(self, mock_request, mock_session, mock_token, mock_endpoint):
        """Test sending query skill-tool relations request to cloud"""
        from agent.cloud_api.cloud_api import send_query_skill_tool_relations_to_cloud
        
        mock_request.return_value = {
            "data": {
                "querySkillToolRelations": '[]'
            }
        }
        
        q_settings = {"byowneruser": True}
        result = send_query_skill_tool_relations_to_cloud(mock_session, mock_token, q_settings, mock_endpoint)
        
        mock_request.assert_called_once()
        assert result is not None
