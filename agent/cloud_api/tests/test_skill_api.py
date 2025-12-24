"""
Unit Tests for Skill Cloud API Operations

Tests for add, update, delete, and query operations on the AgentSkill table.
"""

import pytest
import json
from unittest.mock import patch, MagicMock
from agent.cloud_api.constants import DataType, Operation


class TestSkillAPI:
    """Test suite for Skill cloud API operations"""
    
    def test_gen_add_skills_string(self, sample_skill):
        """Test generating GraphQL mutation string for adding skills"""
        from agent.cloud_api.graphql_builder import build_mutation
        
        mutation = build_mutation(DataType.SKILL, Operation.ADD, [sample_skill])
        
        assert "mutation MyMutation" in mutation
        assert "addAgentSkills" in mutation
        assert "input:" in mutation
    
    def test_gen_update_skills_string(self, sample_skill):
        """Test generating GraphQL mutation string for updating skills"""
        from agent.cloud_api.graphql_builder import build_mutation
        
        mutation = build_mutation(DataType.SKILL, Operation.UPDATE, [sample_skill])
        
        assert "mutation MyMutation" in mutation
        assert "updateAgentSkills" in mutation
    
    def test_gen_remove_skills_string(self, sample_skill):
        """Test generating GraphQL mutation string for removing skills"""
        from agent.cloud_api.graphql_builder import build_mutation
        
        remove_order = {
            "oid": sample_skill["askid"],
            "owner": sample_skill["owner"],
            "reason": "Test deletion"
        }
        
        mutation = build_mutation(DataType.SKILL, Operation.DELETE, [remove_order])
        
        assert "mutation MyMutation" in mutation
        assert "removeAgentSkills" in mutation
    
    @patch('agent.cloud_api.cloud_api.appsync_http_request')
    def test_send_add_skills_request_to_cloud(self, mock_request, mock_session, mock_token, mock_endpoint, sample_skill):
        """Test sending add skills request to cloud"""
        from agent.cloud_api.cloud_api import send_add_skills_request_to_cloud
        
        mock_request.return_value = {
            "data": {
                "addAgentSkills": '{"success": true, "count": 1}'
            }
        }
        
        result = send_add_skills_request_to_cloud(mock_session, [sample_skill], mock_token, mock_endpoint)
        
        mock_request.assert_called_once()
        assert result is not None
    
    @patch('agent.cloud_api.cloud_api.appsync_http_request')
    def test_send_update_skills_request_to_cloud(self, mock_request, mock_session, mock_token, mock_endpoint, sample_skill):
        """Test sending update skills request to cloud"""
        from agent.cloud_api.cloud_api import send_update_skills_request_to_cloud
        
        mock_request.return_value = {
            "data": {
                "updateAgentSkills": '{"success": true, "count": 1}'
            }
        }
        
        result = send_update_skills_request_to_cloud(mock_session, [sample_skill], mock_token, mock_endpoint)
        
        mock_request.assert_called_once()
        assert result is not None
    
    @patch('agent.cloud_api.cloud_api.appsync_http_request')
    def test_send_remove_skills_request_to_cloud(self, mock_request, mock_session, mock_token, mock_endpoint, sample_skill):
        """Test sending remove skills request to cloud"""
        from agent.cloud_api.cloud_api import send_remove_skills_request_to_cloud
        
        mock_request.return_value = {
            "data": {
                "removeAgentSkills": '{"success": true, "count": 1}'
            }
        }
        
        remove_order = {
            "skid": sample_skill["askid"],
            "owner": sample_skill["owner"],
            "reason": "Test deletion"
        }
        
        result = send_remove_skills_request_to_cloud(mock_session, [remove_order], mock_token, mock_endpoint)
        
        mock_request.assert_called_once()
        assert result is not None
    
    @patch('agent.cloud_api.cloud_api.appsync_http_request')
    def test_send_query_skills_entity_to_cloud(self, mock_request, mock_session, mock_token, mock_endpoint):
        """Test sending query skills request to cloud"""
        from agent.cloud_api.cloud_api import send_query_skills_entity_to_cloud
        
        mock_request.return_value = {
            "data": {
                "queryAgentSkills": '[]'
            }
        }
        
        q_settings = {"byowneruser": True}
        result = send_query_skills_entity_to_cloud(mock_session, mock_token, q_settings, mock_endpoint)
        
        mock_request.assert_called_once()
        assert result is not None
    
    def test_cloud_api_service_skill_sync(self, sample_skill):
        """Test CloudAPIService for skill sync operations"""
        from agent.cloud_api.cloud_api_service import CloudAPIService
        from agent.cloud_api.constants import DataType
        
        service = CloudAPIService(DataType.SKILL)
        
        assert service.data_type == DataType.SKILL
        assert service.schema is not None


class TestAgentSkillRelationAPI:
    """Test suite for Agent-Skill relationship operations"""
    
    def test_gen_add_agent_skill_relations_string(self, sample_agent_skill_relation):
        """Test generating GraphQL mutation string for adding agent-skill relations"""
        from agent.cloud_api.graphql_builder import build_mutation
        
        mutation = build_mutation(DataType.AGENT_SKILL, Operation.ADD, [sample_agent_skill_relation])
        
        assert "mutation MyMutation" in mutation
        assert "addAgentSkillRelations" in mutation
    
    @patch('agent.cloud_api.cloud_api.appsync_http_request')
    def test_send_add_agent_skill_relations_request_to_cloud(self, mock_request, mock_session, mock_token, mock_endpoint, sample_agent_skill_relation):
        """Test sending add agent-skill relations request to cloud"""
        from agent.cloud_api.cloud_api import send_add_agent_skill_relations_request_to_cloud
        
        mock_request.return_value = {
            "data": {
                "addAgentSkillRelations": '{"success": true, "count": 1}'
            }
        }
        
        result = send_add_agent_skill_relations_request_to_cloud(
            mock_session, [sample_agent_skill_relation], mock_token, mock_endpoint
        )
        
        mock_request.assert_called_once()
        assert result is not None
    
    @patch('agent.cloud_api.cloud_api.appsync_http_request')
    def test_send_query_agent_skill_relations_request_to_cloud(self, mock_request, mock_session, mock_token, mock_endpoint):
        """Test sending query agent-skill relations request to cloud"""
        from agent.cloud_api.cloud_api import send_query_agent_skill_relations_request_to_cloud
        
        mock_request.return_value = {
            "data": {
                "queryAgentSkillRelations": '[]'
            }
        }
        
        q_settings = {"byowneruser": True}
        result = send_query_agent_skill_relations_request_to_cloud(mock_session, mock_token, q_settings, mock_endpoint)
        
        mock_request.assert_called_once()
        assert result is not None
