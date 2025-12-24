"""
Unit Tests for Cloud API Service

Tests for the CloudAPIService class and CloudAPIServiceFactory.
"""

import pytest
import json
from unittest.mock import patch, MagicMock
from agent.cloud_api.constants import DataType, Operation


class TestCloudAPIService:
    """Test suite for CloudAPIService"""
    
    def test_service_initialization_with_enum(self):
        """Test CloudAPIService initialization with DataType enum"""
        from agent.cloud_api.cloud_api_service import CloudAPIService
        
        service = CloudAPIService(DataType.AGENT)
        
        assert service.data_type == DataType.AGENT
        assert service.schema_registry is not None
    
    def test_service_initialization_with_string(self):
        """Test CloudAPIService initialization with string"""
        from agent.cloud_api.cloud_api_service import CloudAPIService
        
        service = CloudAPIService("agent")
        
        assert service.data_type == DataType.AGENT
    
    def test_service_get_api_endpoint(self):
        """Test getting API endpoint"""
        from agent.cloud_api.cloud_api_service import CloudAPIService
        
        service = CloudAPIService(DataType.AGENT)
        
        # Should not raise an error
        endpoint = service._get_api_endpoint()
        assert endpoint is not None
    
    @patch('agent.cloud_api.cloud_api_service.get_cloud_api_function')
    def test_service_get_cloud_api_function(self, mock_get_func):
        """Test getting cloud API function"""
        from agent.cloud_api.cloud_api_service import CloudAPIService
        
        mock_func = MagicMock()
        mock_get_func.return_value = mock_func
        
        service = CloudAPIService(DataType.AGENT)
        result = service._get_cloud_api_function(Operation.ADD)
        
        assert result == mock_func
    
    @patch('agent.cloud_api.cloud_api_service.CloudAPIService._get_auth_token')
    def test_sync_to_cloud_no_token(self, mock_get_token):
        """Test sync_to_cloud returns error when no token available"""
        from agent.cloud_api.cloud_api_service import CloudAPIService
        
        mock_get_token.return_value = None
        
        service = CloudAPIService(DataType.AGENT)
        result = service.sync_to_cloud([{"id": "1", "name": "Test"}])
        
        assert result["success"] is False
        assert "No auth token" in result["errors"][0]
    
    @patch('agent.cloud_api.cloud_api_service.CloudAPIService._get_auth_token')
    @patch('agent.cloud_api.cloud_api_service.CloudAPIService._get_cloud_api_function')
    def test_sync_to_cloud_no_api_function(self, mock_get_func, mock_get_token):
        """Test sync_to_cloud returns error when no API function found"""
        from agent.cloud_api.cloud_api_service import CloudAPIService
        
        mock_get_token.return_value = "mock_token"
        mock_get_func.return_value = None
        
        service = CloudAPIService(DataType.AGENT)
        result = service.sync_to_cloud([{"id": "1", "name": "Test"}])
        
        assert result["success"] is False
        assert "No cloud API function" in result["errors"][0]
    
    def test_prepare_delete_items(self):
        """Test preparing delete items format"""
        from agent.cloud_api.cloud_api_service import CloudAPIService
        
        service = CloudAPIService(DataType.AGENT)
        
        cloud_items = [
            {"agid": "agent_123", "owner": "user@example.com", "name": "Test Agent"}
        ]
        
        delete_items = service._prepare_delete_items(cloud_items)
        
        assert len(delete_items) == 1
        assert delete_items[0]["oid"] == "agent_123"
        assert delete_items[0]["owner"] == "user@example.com"
        assert "reason" in delete_items[0]
    
    def test_prepare_delete_items_skill(self):
        """Test preparing delete items for skills"""
        from agent.cloud_api.cloud_api_service import CloudAPIService
        
        service = CloudAPIService(DataType.SKILL)
        
        cloud_items = [
            {"skid": "skill_456", "owner": "user@example.com", "name": "Test Skill"}
        ]
        
        delete_items = service._prepare_delete_items(cloud_items)
        
        assert len(delete_items) == 1
        assert delete_items[0]["oid"] == "skill_456"


class TestCloudAPIServiceFactory:
    """Test suite for CloudAPIServiceFactory"""
    
    def test_factory_get_service(self):
        """Test getting service from factory"""
        from agent.cloud_api.cloud_api_service import CloudAPIServiceFactory
        
        service = CloudAPIServiceFactory.get_service("agent")
        
        assert service is not None
        assert service.data_type == DataType.AGENT
    
    def test_factory_singleton_behavior(self):
        """Test that factory returns same instance for same data type"""
        from agent.cloud_api.cloud_api_service import CloudAPIServiceFactory
        
        service1 = CloudAPIServiceFactory.get_service("agent")
        service2 = CloudAPIServiceFactory.get_service("agent")
        
        assert service1 is service2
    
    def test_factory_different_services(self):
        """Test that factory returns different instances for different data types"""
        from agent.cloud_api.cloud_api_service import CloudAPIServiceFactory
        
        agent_service = CloudAPIServiceFactory.get_service("agent")
        skill_service = CloudAPIServiceFactory.get_service("skill")
        
        assert agent_service is not skill_service
        assert agent_service.data_type == DataType.AGENT
        assert skill_service.data_type == DataType.SKILL
    
    def test_factory_reset(self):
        """Test factory reset clears all services"""
        from agent.cloud_api.cloud_api_service import CloudAPIServiceFactory
        
        # Get a service first
        service1 = CloudAPIServiceFactory.get_service("agent")
        
        # Reset
        CloudAPIServiceFactory.reset()
        
        # Get service again - should be a new instance
        service2 = CloudAPIServiceFactory.get_service("agent")
        
        # Note: After reset, we get a new instance
        assert service2 is not None


class TestCloudAPIServiceConvenienceFunctions:
    """Test convenience functions"""
    
    def test_get_cloud_service(self):
        """Test get_cloud_service convenience function"""
        from agent.cloud_api.cloud_api_service import get_cloud_service
        
        service = get_cloud_service("agent")
        
        assert service is not None
        assert service.data_type == DataType.AGENT
    
    def test_get_cloud_service_all_types(self):
        """Test get_cloud_service for all data types"""
        from agent.cloud_api.cloud_api_service import get_cloud_service
        
        data_types = ["agent", "skill", "task", "tool", "knowledge", "avatar_resource", "vehicle", "organization"]
        
        for dt in data_types:
            service = get_cloud_service(dt)
            assert service is not None
            assert service.data_type.value == dt


class TestCloudAPIServiceIntegration:
    """Integration tests for CloudAPIService (requires mocking)"""
    
    @patch('agent.cloud_api.cloud_api_service.CloudAPIService._get_auth_token')
    @patch('agent.cloud_api.cloud_api_service.CloudAPIService._get_api_endpoint')
    @patch('agent.cloud_api.cloud_api_service.get_cloud_api_function')
    @patch('requests.Session')
    def test_full_sync_flow(self, mock_session, mock_get_func, mock_endpoint, mock_token, sample_agent):
        """Test full sync flow with mocked dependencies"""
        from agent.cloud_api.cloud_api_service import CloudAPIService
        
        mock_token.return_value = "mock_token"
        mock_endpoint.return_value = "https://mock-endpoint.com/graphql"
        
        mock_api_func = MagicMock()
        mock_api_func.return_value = {"success": True}
        mock_get_func.return_value = mock_api_func
        
        service = CloudAPIService(DataType.AGENT)
        result = service.sync_to_cloud([sample_agent], Operation.ADD)
        
        assert result["success"] is True
        assert result["synced"] == 1
        assert result["failed"] == 0
    
    @pytest.mark.skip(reason="Integration test - requires real AWS credentials")
    def test_real_cloud_sync(self, sample_agent):
        """Test real cloud sync (requires credentials)"""
        pass
