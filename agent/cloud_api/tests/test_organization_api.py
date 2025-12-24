"""
Unit Tests for Organization Cloud API Operations

Tests for query operations on the Organization table.
"""

import pytest
import json
from unittest.mock import patch, MagicMock
from agent.cloud_api.constants import DataType, Operation


class TestOrganizationAPI:
    """Test suite for Organization cloud API operations"""
    
    def test_gen_query_organizations_string(self, sample_organization):
        """Test generating GraphQL query string for querying organizations"""
        from agent.cloud_api.cloud_api import gen_query_organizations_string
        
        q_settings = {"byowneruser": True}
        query = gen_query_organizations_string(q_settings)
        
        assert "query MyQuery" in query
        assert "queryOrganizations" in query
    
    def test_gen_get_organizations_string(self):
        """Test generating GraphQL query string for getting organizations by IDs"""
        from agent.cloud_api.cloud_api import gen_get_organizations_string
        
        ids = ["org_1", "org_2", "org_3"]
        query = gen_get_organizations_string(ids)
        
        assert "query MyQuery" in query
        assert "getOrganizations" in query
        assert "org_1,org_2,org_3" in query
    
    def test_gen_get_organizations_string_single_id(self):
        """Test generating GraphQL query string for getting a single organization"""
        from agent.cloud_api.cloud_api import gen_get_organizations_string
        
        query = gen_get_organizations_string("org_123")
        
        assert "query MyQuery" in query
        assert "getOrganizations" in query
        assert "org_123" in query
    
    @patch('agent.cloud_api.cloud_api.appsync_http_request')
    def test_send_query_organizations_to_cloud(self, mock_request, mock_session, mock_token, mock_endpoint):
        """Test sending query organizations request to cloud"""
        from agent.cloud_api.cloud_api import send_query_organizations_to_cloud
        
        mock_request.return_value = {
            "data": {
                "queryOrganizations": '[]'
            }
        }
        
        q_settings = {"byowneruser": True}
        result = send_query_organizations_to_cloud(mock_session, mock_token, q_settings, mock_endpoint)
        
        mock_request.assert_called_once()
        assert result is not None
    
    @patch('agent.cloud_api.cloud_api.appsync_http_request')
    def test_query_organizations_with_filter(self, mock_request, mock_session, mock_token, mock_endpoint):
        """Test querying organizations with specific filter"""
        from agent.cloud_api.cloud_api import send_query_organizations_to_cloud
        
        mock_request.return_value = {
            "data": {
                "queryOrganizations": '[{"id": "org_1", "name": "Test Org"}]'
            }
        }
        
        q_settings = {"owner": "test_user@example.com", "name": "Test Org"}
        result = send_query_organizations_to_cloud(mock_session, mock_token, q_settings, mock_endpoint)
        
        mock_request.assert_called_once()
        assert result is not None
    
    def test_cloud_api_service_organization_sync(self, sample_organization):
        """Test CloudAPIService for organization sync operations"""
        from agent.cloud_api.cloud_api_service import CloudAPIService
        from agent.cloud_api.constants import DataType
        
        service = CloudAPIService(DataType.ORGANIZATION)
        
        assert service.data_type == DataType.ORGANIZATION
    
    @patch('agent.cloud_api.cloud_api.appsync_http_request')
    def test_organization_api_error_handling(self, mock_request, mock_session, mock_token, mock_endpoint):
        """Test error handling for organization API calls"""
        from agent.cloud_api.cloud_api import send_query_organizations_to_cloud
        
        mock_request.return_value = {
            "errors": [
                {
                    "errorType": "UnauthorizedError",
                    "message": "User not authorized to query organizations"
                }
            ]
        }
        
        q_settings = {"byowneruser": True}
        result = send_query_organizations_to_cloud(mock_session, mock_token, q_settings, mock_endpoint)
        
        assert "errorType" in result or "error" in str(result).lower()
    
    @patch('agent.cloud_api.cloud_api.appsync_http_request')
    def test_query_organizations_empty_result(self, mock_request, mock_session, mock_token, mock_endpoint):
        """Test querying organizations with empty result"""
        from agent.cloud_api.cloud_api import send_query_organizations_to_cloud
        
        mock_request.return_value = {
            "data": {
                "queryOrganizations": '[]'
            }
        }
        
        q_settings = {"byowneruser": True}
        result = send_query_organizations_to_cloud(mock_session, mock_token, q_settings, mock_endpoint)
        
        mock_request.assert_called_once()
        # Result should be empty list or empty dict
        assert result is not None
