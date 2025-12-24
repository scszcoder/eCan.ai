"""
Unit Tests for Knowledge Cloud API Operations

Tests for add, update, delete, and query operations on the Knowledge table.
"""

import pytest
import json
from unittest.mock import patch, MagicMock
from agent.cloud_api.constants import DataType, Operation


class TestKnowledgeAPI:
    """Test suite for Knowledge cloud API operations"""
    
    def test_gen_add_knowledges_string(self, sample_knowledge):
        """Test generating GraphQL mutation string for adding knowledges"""
        from agent.cloud_api.graphql_builder import build_mutation
        
        mutation = build_mutation(DataType.KNOWLEDGE, Operation.ADD, [sample_knowledge])
        
        assert "mutation MyMutation" in mutation
        assert "addKnowledges" in mutation
        assert "input:" in mutation
    
    def test_gen_update_knowledges_string(self, sample_knowledge):
        """Test generating GraphQL mutation string for updating knowledges"""
        from agent.cloud_api.graphql_builder import build_mutation
        
        mutation = build_mutation(DataType.KNOWLEDGE, Operation.UPDATE, [sample_knowledge])
        
        assert "mutation MyMutation" in mutation
        assert "updateKnowledges" in mutation
    
    def test_gen_remove_knowledges_string(self, sample_knowledge):
        """Test generating GraphQL mutation string for removing knowledges"""
        from agent.cloud_api.graphql_builder import build_mutation
        
        remove_order = {
            "oid": sample_knowledge["knId"],
            "owner": sample_knowledge["owner"],
            "reason": "Test deletion"
        }
        
        mutation = build_mutation(DataType.KNOWLEDGE, Operation.DELETE, [remove_order])
        
        assert "mutation MyMutation" in mutation
        assert "removeKnowledges" in mutation
    
    @patch('agent.cloud_api.cloud_api.appsync_http_request')
    def test_send_add_knowledges_decorated_to_cloud(self, mock_request, mock_session, mock_token, mock_endpoint, sample_knowledge):
        """Test sending add knowledges request to cloud"""
        from agent.cloud_api.cloud_api import send_add_knowledges_decorated_to_cloud
        
        mock_request.return_value = {
            "data": {
                "addKnowledges": '{"success": true, "count": 1}'
            }
        }
        
        result = send_add_knowledges_decorated_to_cloud(mock_session, [sample_knowledge], mock_token, mock_endpoint)
        
        mock_request.assert_called_once()
        assert result is not None
    
    @patch('agent.cloud_api.cloud_api.appsync_http_request')
    def test_send_update_knowledges_decorated_to_cloud(self, mock_request, mock_session, mock_token, mock_endpoint, sample_knowledge):
        """Test sending update knowledges request to cloud"""
        from agent.cloud_api.cloud_api import send_update_knowledges_decorated_to_cloud
        
        mock_request.return_value = {
            "data": {
                "updateKnowledges": '{"success": true, "count": 1}'
            }
        }
        
        result = send_update_knowledges_decorated_to_cloud(mock_session, [sample_knowledge], mock_token, mock_endpoint)
        
        mock_request.assert_called_once()
        assert result is not None
    
    @patch('agent.cloud_api.cloud_api.appsync_http_request')
    def test_send_remove_knowledges_decorated_to_cloud(self, mock_request, mock_session, mock_token, mock_endpoint, sample_knowledge):
        """Test sending remove knowledges request to cloud"""
        from agent.cloud_api.cloud_api import send_remove_knowledges_decorated_to_cloud
        
        mock_request.return_value = {
            "data": {
                "removeKnowledges": '{"success": true, "count": 1}'
            }
        }
        
        remove_order = {
            "oid": sample_knowledge["knId"],
            "owner": sample_knowledge["owner"],
            "reason": "Test deletion"
        }
        
        result = send_remove_knowledges_decorated_to_cloud(mock_session, [remove_order], mock_token, mock_endpoint)
        
        mock_request.assert_called_once()
        assert result is not None
    
    @patch('agent.cloud_api.cloud_api.appsync_http_request')
    def test_send_query_knowledges_decorated_to_cloud(self, mock_request, mock_session, mock_token, mock_endpoint):
        """Test sending query knowledges request to cloud"""
        from agent.cloud_api.cloud_api import send_query_knowledges_decorated_to_cloud
        
        mock_request.return_value = {
            "data": {
                "queryKnowledges": '[]'
            }
        }
        
        q_settings = {"byowneruser": True}
        result = send_query_knowledges_decorated_to_cloud(mock_session, mock_token, q_settings, mock_endpoint)
        
        mock_request.assert_called_once()
        assert result is not None
    
    def test_cloud_api_service_knowledge_sync(self, sample_knowledge):
        """Test CloudAPIService for knowledge sync operations"""
        from agent.cloud_api.cloud_api_service import CloudAPIService
        from agent.cloud_api.constants import DataType
        
        service = CloudAPIService(DataType.KNOWLEDGE)
        
        assert service.data_type == DataType.KNOWLEDGE


class TestSkillKnowledgeRelationAPI:
    """Test suite for Skill-Knowledge relationship operations"""
    
    def test_gen_add_skill_knowledge_relations_string(self, sample_skill_knowledge_relation):
        """Test generating GraphQL mutation string for adding skill-knowledge relations"""
        from agent.cloud_api.graphql_builder import build_mutation
        
        mutation = build_mutation(DataType.SKILL_KNOWLEDGE, Operation.ADD, [sample_skill_knowledge_relation])
        
        assert "mutation MyMutation" in mutation
        assert "addSkillKnowledgeRelations" in mutation
    
    @patch('agent.cloud_api.cloud_api.appsync_http_request')
    def test_send_add_skill_knowledge_relations_to_cloud(self, mock_request, mock_session, mock_token, mock_endpoint, sample_skill_knowledge_relation):
        """Test sending add skill-knowledge relations request to cloud"""
        from agent.cloud_api.cloud_api import send_add_skill_knowledge_relations_to_cloud
        
        mock_request.return_value = {
            "data": {
                "addSkillKnowledgeRelations": '{"success": true, "count": 1}'
            }
        }
        
        result = send_add_skill_knowledge_relations_to_cloud(
            mock_session, [sample_skill_knowledge_relation], mock_token, mock_endpoint
        )
        
        mock_request.assert_called_once()
        assert result is not None
    
    @patch('agent.cloud_api.cloud_api.appsync_http_request')
    def test_send_query_skill_knowledge_relations_to_cloud(self, mock_request, mock_session, mock_token, mock_endpoint):
        """Test sending query skill-knowledge relations request to cloud"""
        from agent.cloud_api.cloud_api import send_query_skill_knowledge_relations_to_cloud
        
        mock_request.return_value = {
            "data": {
                "querySkillKnowledgeRelations": '[]'
            }
        }
        
        q_settings = {"byowneruser": True}
        result = send_query_skill_knowledge_relations_to_cloud(mock_session, mock_token, q_settings, mock_endpoint)
        
        mock_request.assert_called_once()
        assert result is not None
    
    @patch('agent.cloud_api.cloud_api.appsync_http_request')
    def test_send_update_skill_knowledge_relations_to_cloud(self, mock_request, mock_session, mock_token, mock_endpoint, sample_skill_knowledge_relation):
        """Test sending update skill-knowledge relations request to cloud"""
        from agent.cloud_api.cloud_api import send_update_skill_knowledge_relations_to_cloud
        
        mock_request.return_value = {
            "data": {
                "updateSkillKnowledgeRelations": '{"success": true, "count": 1}'
            }
        }
        
        result = send_update_skill_knowledge_relations_to_cloud(
            mock_session, [sample_skill_knowledge_relation], mock_token, mock_endpoint
        )
        
        mock_request.assert_called_once()
        assert result is not None
    
    @patch('agent.cloud_api.cloud_api.appsync_http_request')
    def test_send_remove_skill_knowledge_relations_to_cloud(self, mock_request, mock_session, mock_token, mock_endpoint):
        """Test sending remove skill-knowledge relations request to cloud"""
        from agent.cloud_api.cloud_api import send_remove_skill_knowledge_relations_to_cloud
        
        mock_request.return_value = {
            "data": {
                "removeSkillKnowledgeRelations": '{"success": true, "count": 1}'
            }
        }
        
        remove_order = {
            "oid": "relation_123",
            "owner": "test_user@example.com",
            "reason": "Test deletion"
        }
        
        result = send_remove_skill_knowledge_relations_to_cloud(mock_session, [remove_order], mock_token, mock_endpoint)
        
        mock_request.assert_called_once()
        assert result is not None
