"""
Unit Tests for Agent Cloud API Operations

Tests for add, update, delete, and query operations on the Agent table.
"""

import pytest
import json
from unittest.mock import patch, MagicMock
from agent.cloud_api.constants import DataType, Operation


class TestAgentAPI:
    """Test suite for Agent cloud API operations"""
    
    def test_gen_add_agents_string(self, sample_agent):
        """Test generating GraphQL mutation string for adding agents"""
        from agent.cloud_api.graphql_builder import build_mutation
        
        mutation = build_mutation(DataType.AGENT, Operation.ADD, [sample_agent])
        
        assert "mutation MyMutation" in mutation
        assert "addAgents" in mutation
        assert "input:" in mutation
    
    def test_gen_update_agents_string(self, sample_agent):
        """Test generating GraphQL mutation string for updating agents"""
        from agent.cloud_api.graphql_builder import build_mutation
        
        mutation = build_mutation(DataType.AGENT, Operation.UPDATE, [sample_agent])
        
        assert "mutation MyMutation" in mutation
        assert "updateAgents" in mutation
    
    def test_gen_remove_agents_string(self, sample_agent):
        """Test generating GraphQL mutation string for removing agents"""
        from agent.cloud_api.graphql_builder import build_mutation
        
        remove_order = {
            "oid": sample_agent["agid"],
            "owner": sample_agent["owner"],
            "reason": "Test deletion"
        }
        
        mutation = build_mutation(DataType.AGENT, Operation.DELETE, [remove_order])
        
        assert "mutation MyMutation" in mutation
        assert "removeAgents" in mutation
        assert "oid:" in mutation
    
    @patch('agent.cloud_api.cloud_api.appsync_http_request')
    def test_send_add_agents_request_to_cloud(self, mock_request, mock_session, mock_token, mock_endpoint, sample_agent):
        """Test sending add agents request to cloud"""
        from agent.cloud_api.cloud_api import send_add_agents_request_to_cloud
        
        mock_request.return_value = {
            "data": {
                "addAgents": '{"success": true, "count": 1}'
            }
        }
        
        result = send_add_agents_request_to_cloud(mock_session, [sample_agent], mock_token, mock_endpoint)
        
        mock_request.assert_called_once()
        assert result is not None
    
    @patch('agent.cloud_api.cloud_api.appsync_http_request')
    def test_send_update_agents_request_to_cloud(self, mock_request, mock_session, mock_token, mock_endpoint, sample_agent):
        """Test sending update agents request to cloud"""
        from agent.cloud_api.cloud_api import send_update_agents_request_to_cloud
        
        mock_request.return_value = {
            "data": {
                "updateAgents": '{"success": true, "count": 1}'
            }
        }
        
        result = send_update_agents_request_to_cloud(mock_session, [sample_agent], mock_token, mock_endpoint)
        
        mock_request.assert_called_once()
        assert result is not None
    
    @patch('agent.cloud_api.cloud_api.appsync_http_request')
    def test_send_remove_agents_request_to_cloud(self, mock_request, mock_session, mock_token, mock_endpoint, sample_agent):
        """Test sending remove agents request to cloud"""
        from agent.cloud_api.cloud_api import send_remove_agents_request_to_cloud
        
        mock_request.return_value = {
            "data": {
                "removeAgents": '{"success": true, "count": 1}'
            }
        }
        
        remove_order = {
            "agid": sample_agent["agid"],
            "owner": sample_agent["owner"],
            "reason": "Test deletion"
        }
        
        result = send_remove_agents_request_to_cloud(mock_session, [remove_order], mock_token, mock_endpoint)
        
        mock_request.assert_called_once()
        assert result is not None
    
    @patch('agent.cloud_api.cloud_api.appsync_http_request')
    def test_send_query_agents_request_to_cloud(self, mock_request, mock_session, mock_token, mock_endpoint):
        """Test sending query agents request to cloud"""
        from agent.cloud_api.cloud_api import send_query_agents_request_to_cloud
        
        mock_request.return_value = {
            "data": {
                "queryAgents": '[]'
            }
        }
        
        q_settings = {"byowneruser": True}
        result = send_query_agents_request_to_cloud(mock_session, mock_token, q_settings, mock_endpoint)
        
        mock_request.assert_called_once()
        assert result is not None
    
    @patch('agent.cloud_api.cloud_api.appsync_http_request')
    def test_agent_api_error_handling(self, mock_request, mock_session, mock_token, mock_endpoint, sample_agent):
        """Test error handling for agent API calls"""
        from agent.cloud_api.cloud_api import send_add_agents_request_to_cloud
        
        mock_request.return_value = {
            "errors": [
                {
                    "errorType": "ValidationError",
                    "message": "Invalid agent data"
                }
            ]
        }
        
        result = send_add_agents_request_to_cloud(mock_session, [sample_agent], mock_token, mock_endpoint)
        
        assert "errorType" in result or "error" in str(result).lower()
    
    def test_cloud_api_service_agent_sync(self, sample_agent):
        """Test CloudAPIService for agent sync operations"""
        from agent.cloud_api.cloud_api_service import CloudAPIService
        from agent.cloud_api.constants import DataType
        
        service = CloudAPIService(DataType.AGENT)
        
        assert service.data_type == DataType.AGENT
        assert service.schema is not None


class TestAgentAPIIntegration:
    """Integration tests for Agent API (requires real credentials)"""
    
    @pytest.mark.skip(reason="Integration test - requires real AWS credentials")
    def test_full_agent_lifecycle(self, sample_agent):
        """Test full agent lifecycle: create, update, query, delete"""
        pass
