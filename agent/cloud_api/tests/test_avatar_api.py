"""
Unit Tests for Avatar Resource Cloud API Operations

Tests for add, update, delete, and query operations on the AvatarResource table.
"""

import pytest
import json
from unittest.mock import patch, MagicMock
from agent.cloud_api.constants import DataType, Operation


class TestAvatarResourceAPI:
    """Test suite for Avatar Resource cloud API operations"""
    
    def test_gen_add_avatar_resources_string(self, sample_avatar_resource):
        """Test generating GraphQL mutation string for adding avatar resources"""
        from agent.cloud_api.cloud_api import gen_add_avatar_resources_string
        
        mutation = gen_add_avatar_resources_string([sample_avatar_resource])
        
        assert "mutation MyMutation" in mutation
        assert "addAvatarResources" in mutation
        assert "input:" in mutation
    
    def test_gen_update_avatar_resources_string(self, sample_avatar_resource):
        """Test generating GraphQL mutation string for updating avatar resources"""
        from agent.cloud_api.cloud_api import gen_update_avatar_resources_string
        
        mutation = gen_update_avatar_resources_string([sample_avatar_resource])
        
        assert "mutation MyMutation" in mutation
        assert "updateAvatarResources" in mutation
    
    def test_gen_remove_avatar_resources_string(self, sample_avatar_resource):
        """Test generating GraphQL mutation string for removing avatar resources"""
        from agent.cloud_api.cloud_api import gen_remove_avatar_resources_string
        
        remove_order = {
            "oid": sample_avatar_resource["id"],
            "owner": sample_avatar_resource["owner"],
            "reason": "Test deletion"
        }
        
        mutation = gen_remove_avatar_resources_string([remove_order])
        
        assert "mutation MyMutation" in mutation
        assert "removeAvatarResources" in mutation
    
    def test_gen_query_avatar_resources_string(self):
        """Test generating GraphQL query string for querying avatar resources"""
        from agent.cloud_api.cloud_api import gen_query_avatar_resources_string
        
        q_settings = {"byowneruser": True}
        query = gen_query_avatar_resources_string(q_settings)
        
        assert "query MyQuery" in query
        assert "queryAvatarResources" in query
    
    @patch('agent.cloud_api.cloud_api.appsync_http_request')
    def test_send_add_avatar_resources_to_cloud(self, mock_request, mock_session, mock_token, mock_endpoint, sample_avatar_resource):
        """Test sending add avatar resources request to cloud"""
        from agent.cloud_api.cloud_api import send_add_avatar_resources_to_cloud
        
        mock_request.return_value = {
            "data": {
                "addAvatarResources": '{"success": true, "count": 1}'
            }
        }
        
        result = send_add_avatar_resources_to_cloud(mock_session, [sample_avatar_resource], mock_token, mock_endpoint)
        
        mock_request.assert_called_once()
        assert result is not None
    
    @patch('agent.cloud_api.cloud_api.appsync_http_request')
    def test_send_update_avatar_resources_to_cloud(self, mock_request, mock_session, mock_token, mock_endpoint, sample_avatar_resource):
        """Test sending update avatar resources request to cloud"""
        from agent.cloud_api.cloud_api import send_update_avatar_resources_to_cloud
        
        mock_request.return_value = {
            "data": {
                "updateAvatarResources": '{"success": true, "count": 1}'
            }
        }
        
        result = send_update_avatar_resources_to_cloud(mock_session, [sample_avatar_resource], mock_token, mock_endpoint)
        
        mock_request.assert_called_once()
        assert result is not None
    
    @patch('agent.cloud_api.cloud_api.appsync_http_request')
    def test_send_remove_avatar_resources_to_cloud(self, mock_request, mock_session, mock_token, mock_endpoint, sample_avatar_resource):
        """Test sending remove avatar resources request to cloud"""
        from agent.cloud_api.cloud_api import send_remove_avatar_resources_to_cloud
        
        mock_request.return_value = {
            "data": {
                "removeAvatarResources": '{"success": true, "count": 1}'
            }
        }
        
        remove_order = {
            "oid": sample_avatar_resource["id"],
            "owner": sample_avatar_resource["owner"],
            "reason": "Test deletion"
        }
        
        result = send_remove_avatar_resources_to_cloud(mock_session, [remove_order], mock_token, mock_endpoint)
        
        mock_request.assert_called_once()
        assert result is not None
    
    @patch('agent.cloud_api.cloud_api.appsync_http_request')
    def test_send_query_avatar_resources_to_cloud(self, mock_request, mock_session, mock_token, mock_endpoint):
        """Test sending query avatar resources request to cloud"""
        from agent.cloud_api.cloud_api import send_query_avatar_resources_to_cloud
        
        mock_request.return_value = {
            "data": {
                "queryAvatarResources": '[]'
            }
        }
        
        q_settings = {"byowneruser": True}
        result = send_query_avatar_resources_to_cloud(mock_session, mock_token, q_settings, mock_endpoint)
        
        mock_request.assert_called_once()
        assert result is not None
    
    def test_cloud_api_service_avatar_resource_sync(self, sample_avatar_resource):
        """Test CloudAPIService for avatar resource sync operations"""
        from agent.cloud_api.cloud_api_service import CloudAPIService
        from agent.cloud_api.constants import DataType
        
        service = CloudAPIService(DataType.AVATAR_RESOURCE)
        
        assert service.data_type == DataType.AVATAR_RESOURCE
    
    @patch('agent.cloud_api.cloud_api.appsync_http_request')
    def test_avatar_resource_api_error_handling(self, mock_request, mock_session, mock_token, mock_endpoint, sample_avatar_resource):
        """Test error handling for avatar resource API calls"""
        from agent.cloud_api.cloud_api import send_add_avatar_resources_to_cloud
        
        mock_request.return_value = {
            "errors": [
                {
                    "errorType": "ValidationError",
                    "message": "Invalid avatar resource data"
                }
            ]
        }
        
        result = send_add_avatar_resources_to_cloud(mock_session, [sample_avatar_resource], mock_token, mock_endpoint)
        
        assert "errorType" in result or "error" in str(result).lower()
    
    def test_avatar_resource_with_metadata(self, sample_avatar_resource):
        """Test avatar resource with complex metadata"""
        from agent.cloud_api.cloud_api import gen_add_avatar_resources_string
        
        sample_avatar_resource["avatar_metadata"] = {
            "width": 512,
            "height": 512,
            "format": "png",
            "tags": ["avatar", "test"]
        }
        
        mutation = gen_add_avatar_resources_string([sample_avatar_resource])
        
        assert "avatar_metadata" in mutation
        assert "mutation MyMutation" in mutation
