"""
Unit Tests for Vehicle Cloud API Operations

Tests for add (report), update operations on the Vehicle table.
"""

import pytest
import json
from unittest.mock import patch, MagicMock
from agent.cloud_api.constants import DataType, Operation


class TestVehicleAPI:
    """Test suite for Vehicle cloud API operations"""
    
    def test_gen_report_vehicles_string(self, sample_vehicle):
        """Test generating GraphQL mutation string for reporting vehicles"""
        from agent.cloud_api.cloud_api import gen_report_vehicles_string
        
        mutation = gen_report_vehicles_string([sample_vehicle])
        
        assert "mutation MyMutation" in mutation
        assert "reportVehicles" in mutation
        assert "input:" in mutation
    
    def test_gen_update_vehicles_string(self, sample_vehicle):
        """Test generating GraphQL mutation string for updating vehicles"""
        from agent.cloud_api.cloud_api import gen_update_vehicles_string
        
        mutation = gen_update_vehicles_string([sample_vehicle])
        
        assert "mutation MyMutation" in mutation
        assert "updateVehicles" in mutation
    
    @patch('agent.cloud_api.cloud_api.appsync_http_request')
    def test_send_add_vehicles_request_to_cloud(self, mock_request, mock_session, mock_token, mock_endpoint, sample_vehicle):
        """Test sending add/report vehicles request to cloud"""
        from agent.cloud_api.cloud_api import send_add_vehicles_request_to_cloud
        
        mock_request.return_value = {
            "data": {
                "reportVehicles": '{"success": true, "count": 1}'
            }
        }
        
        result = send_add_vehicles_request_to_cloud(mock_session, [sample_vehicle], mock_token, mock_endpoint)
        
        mock_request.assert_called_once()
        assert result is not None
    
    @patch('agent.cloud_api.cloud_api.appsync_http_request')
    def test_send_update_vehicles_decorated_to_cloud(self, mock_request, mock_session, mock_token, mock_endpoint, sample_vehicle):
        """Test sending update vehicles request to cloud"""
        from agent.cloud_api.cloud_api import send_update_vehicles_decorated_to_cloud
        
        mock_request.return_value = {
            "data": {
                "updateVehicles": '{"success": true, "count": 1}'
            }
        }
        
        result = send_update_vehicles_decorated_to_cloud(mock_session, [sample_vehicle], mock_token, mock_endpoint)
        
        mock_request.assert_called_once()
        assert result is not None
    
    @patch('agent.cloud_api.cloud_api.appsync_http_request')
    def test_send_report_vehicles_to_cloud(self, mock_request, mock_session, mock_token, mock_endpoint, sample_vehicle):
        """Test sending report vehicles request to cloud (legacy function)"""
        from agent.cloud_api.cloud_api import send_report_vehicles_to_cloud
        
        mock_request.return_value = {
            "data": {
                "reportVehicles": '{"success": true, "count": 1}'
            }
        }
        
        result = send_report_vehicles_to_cloud(mock_session, mock_token, [sample_vehicle], mock_endpoint)
        
        mock_request.assert_called_once()
        assert result is not None
    
    @patch('agent.cloud_api.cloud_api.appsync_http_request')
    def test_send_update_vehicles_request_to_cloud(self, mock_request, mock_session, mock_token, mock_endpoint, sample_vehicle):
        """Test sending update vehicles request to cloud (legacy function)"""
        from agent.cloud_api.cloud_api import send_update_vehicles_request_to_cloud
        
        mock_request.return_value = {
            "data": {
                "updateVehicles": '{"success": true, "count": 1}'
            }
        }
        
        result = send_update_vehicles_request_to_cloud(mock_session, [sample_vehicle], mock_token, mock_endpoint)
        
        mock_request.assert_called_once()
        assert result is not None
    
    def test_cloud_api_service_vehicle_sync(self, sample_vehicle):
        """Test CloudAPIService for vehicle sync operations"""
        from agent.cloud_api.cloud_api_service import CloudAPIService
        from agent.cloud_api.constants import DataType
        
        service = CloudAPIService(DataType.VEHICLE)
        
        assert service.data_type == DataType.VEHICLE
    
    @patch('agent.cloud_api.cloud_api.appsync_http_request')
    def test_vehicle_api_error_handling(self, mock_request, mock_session, mock_token, mock_endpoint, sample_vehicle):
        """Test error handling for vehicle API calls"""
        from agent.cloud_api.cloud_api import send_add_vehicles_request_to_cloud
        
        mock_request.return_value = {
            "errors": [
                {
                    "errorType": "ValidationError",
                    "message": "Invalid vehicle data"
                }
            ]
        }
        
        result = send_add_vehicles_request_to_cloud(mock_session, [sample_vehicle], mock_token, mock_endpoint)
        
        assert "errorType" in result or "error" in str(result).lower()
    
    def test_vehicle_with_multiple_agents(self, sample_vehicle):
        """Test vehicle with multiple agent IDs"""
        from agent.cloud_api.cloud_api import gen_report_vehicles_string
        
        sample_vehicle["agent_ids"] = "agent_1,agent_2,agent_3,agent_4"
        
        mutation = gen_report_vehicles_string([sample_vehicle])
        
        assert "agent_1,agent_2,agent_3,agent_4" in mutation or "bids" in mutation
    
    def test_multiple_vehicles_report(self, sample_vehicle):
        """Test reporting multiple vehicles at once"""
        from agent.cloud_api.cloud_api import gen_report_vehicles_string
        
        vehicle2 = sample_vehicle.copy()
        vehicle2["vid"] = 2
        vehicle2["vname"] = "TestMachine2:linux"
        vehicle2["ip"] = "192.168.1.101"
        
        mutation = gen_report_vehicles_string([sample_vehicle, vehicle2])
        
        assert "TestMachine:win" in mutation
        assert "TestMachine2:linux" in mutation
