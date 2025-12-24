"""
Unit Tests for Task Cloud API Operations

Tests for add, update, delete, and query operations on the AgentTask table.
"""

import pytest
import json
from unittest.mock import patch, MagicMock
from agent.cloud_api.constants import DataType, Operation


class TestTaskAPI:
    """Test suite for Task cloud API operations"""
    
    def test_gen_add_tasks_string(self, sample_task):
        """Test generating GraphQL mutation string for adding tasks"""
        from agent.cloud_api.graphql_builder import build_mutation
        
        mutation = build_mutation(DataType.TASK, Operation.ADD, [sample_task])
        
        assert "mutation MyMutation" in mutation
        assert "addAgentTasks" in mutation
        assert "input:" in mutation
    
    def test_gen_update_tasks_string(self, sample_task):
        """Test generating GraphQL mutation string for updating tasks"""
        from agent.cloud_api.graphql_builder import build_mutation
        
        mutation = build_mutation(DataType.TASK, Operation.UPDATE, [sample_task])
        
        assert "mutation MyMutation" in mutation
        assert "updateAgentTasks" in mutation
    
    def test_gen_remove_tasks_string(self, sample_task):
        """Test generating GraphQL mutation string for removing tasks"""
        from agent.cloud_api.graphql_builder import build_mutation
        
        remove_order = {
            "oid": sample_task["ataskid"],
            "owner": sample_task["owner"],
            "reason": "Test deletion"
        }
        
        mutation = build_mutation(DataType.TASK, Operation.DELETE, [remove_order])
        
        assert "mutation MyMutation" in mutation
        assert "removeAgentTasks" in mutation
    
    @patch('agent.cloud_api.cloud_api.appsync_http_request')
    def test_send_add_tasks_request_to_cloud(self, mock_request, mock_session, mock_token, mock_endpoint, sample_task):
        """Test sending add tasks request to cloud"""
        from agent.cloud_api.cloud_api import send_add_tasks_request_to_cloud
        
        mock_request.return_value = {
            "data": {
                "addAgentTasks": '{"success": true, "count": 1}'
            }
        }
        
        result = send_add_tasks_request_to_cloud(mock_session, [sample_task], mock_token, mock_endpoint)
        
        mock_request.assert_called_once()
        assert result is not None
    
    @patch('agent.cloud_api.cloud_api.appsync_http_request')
    def test_send_update_tasks_request_to_cloud(self, mock_request, mock_session, mock_token, mock_endpoint, sample_task):
        """Test sending update tasks request to cloud"""
        from agent.cloud_api.cloud_api import send_update_tasks_request_to_cloud
        
        mock_request.return_value = {
            "data": {
                "updateAgentTasks": '{"success": true, "count": 1}'
            }
        }
        
        result = send_update_tasks_request_to_cloud(mock_session, [sample_task], mock_token, mock_endpoint)
        
        mock_request.assert_called_once()
        assert result is not None
    
    @patch('agent.cloud_api.cloud_api.appsync_http_request')
    def test_send_remove_tasks_request_to_cloud(self, mock_request, mock_session, mock_token, mock_endpoint, sample_task):
        """Test sending remove tasks request to cloud"""
        from agent.cloud_api.cloud_api import send_remove_tasks_request_to_cloud
        
        mock_request.return_value = {
            "data": {
                "removeAgentTasks": '{"success": true, "count": 1}'
            }
        }
        
        remove_order = {
            "task_id": sample_task["ataskid"],
            "owner": sample_task["owner"],
            "reason": "Test deletion"
        }
        
        result = send_remove_tasks_request_to_cloud(mock_session, [remove_order], mock_token, mock_endpoint)
        
        mock_request.assert_called_once()
        assert result is not None
    
    @patch('agent.cloud_api.cloud_api.appsync_http_request')
    def test_send_query_tasks_entity_to_cloud(self, mock_request, mock_session, mock_token, mock_endpoint):
        """Test sending query tasks request to cloud"""
        from agent.cloud_api.cloud_api import send_query_tasks_entity_to_cloud
        
        mock_request.return_value = {
            "data": {
                "queryAgentTasks": '[]'
            }
        }
        
        q_settings = {"byowneruser": True}
        result = send_query_tasks_entity_to_cloud(mock_session, mock_token, q_settings, mock_endpoint)
        
        mock_request.assert_called_once()
        assert result is not None
    
    def test_cloud_api_service_task_sync(self, sample_task):
        """Test CloudAPIService for task sync operations"""
        from agent.cloud_api.cloud_api_service import CloudAPIService
        from agent.cloud_api.constants import DataType
        
        service = CloudAPIService(DataType.TASK)
        
        assert service.data_type == DataType.TASK
        assert service.schema is not None


class TestAgentTaskRelationAPI:
    """Test suite for Agent-Task relationship operations"""
    
    def test_gen_add_agent_task_relations_string(self, sample_agent_task_relation):
        """Test generating GraphQL mutation string for adding agent-task relations"""
        from agent.cloud_api.graphql_builder import build_mutation
        
        mutation = build_mutation(DataType.AGENT_TASK, Operation.ADD, [sample_agent_task_relation])
        
        assert "mutation MyMutation" in mutation
        assert "addAgentTaskRelations" in mutation
    
    @patch('agent.cloud_api.cloud_api.appsync_http_request')
    def test_send_add_agent_task_relations_request_to_cloud(self, mock_request, mock_session, mock_token, mock_endpoint, sample_agent_task_relation):
        """Test sending add agent-task relations request to cloud"""
        from agent.cloud_api.cloud_api import send_add_agent_task_relations_request_to_cloud
        
        mock_request.return_value = {
            "data": {
                "addAgentTaskRelations": '{"success": true, "count": 1}'
            }
        }
        
        result = send_add_agent_task_relations_request_to_cloud(
            mock_session, [sample_agent_task_relation], mock_token, mock_endpoint
        )
        
        mock_request.assert_called_once()
        assert result is not None
    
    @patch('agent.cloud_api.cloud_api.appsync_http_request')
    def test_send_query_agent_task_relations_request_to_cloud(self, mock_request, mock_session, mock_token, mock_endpoint):
        """Test sending query agent-task relations request to cloud"""
        from agent.cloud_api.cloud_api import send_query_agent_task_relations_request_to_cloud
        
        mock_request.return_value = {
            "data": {
                "queryAgentTaskRelations": '[]'
            }
        }
        
        q_settings = {"byowneruser": True}
        result = send_query_agent_task_relations_request_to_cloud(mock_session, mock_token, q_settings, mock_endpoint)
        
        mock_request.assert_called_once()
        assert result is not None


class TestTaskSkillRelationAPI:
    """Test suite for Task-Skill relationship operations"""
    
    def test_gen_add_task_skill_relations_string(self, sample_task_skill_relation):
        """Test generating GraphQL mutation string for adding task-skill relations"""
        from agent.cloud_api.graphql_builder import build_mutation
        
        mutation = build_mutation(DataType.TASK_SKILL, Operation.ADD, [sample_task_skill_relation])
        
        assert "mutation MyMutation" in mutation
        assert "addTaskSkillRelations" in mutation
    
    @patch('agent.cloud_api.cloud_api.appsync_http_request')
    def test_send_add_task_skill_relations_to_cloud(self, mock_request, mock_session, mock_token, mock_endpoint, sample_task_skill_relation):
        """Test sending add task-skill relations request to cloud"""
        from agent.cloud_api.cloud_api import send_add_task_skill_relations_to_cloud
        
        mock_request.return_value = {
            "data": {
                "addTaskSkillRelations": '{"success": true, "count": 1}'
            }
        }
        
        result = send_add_task_skill_relations_to_cloud(
            mock_session, [sample_task_skill_relation], mock_token, mock_endpoint
        )
        
        mock_request.assert_called_once()
        assert result is not None
    
    @patch('agent.cloud_api.cloud_api.appsync_http_request')
    def test_send_query_task_skill_relations_to_cloud(self, mock_request, mock_session, mock_token, mock_endpoint):
        """Test sending query task-skill relations request to cloud"""
        from agent.cloud_api.cloud_api import send_query_task_skill_relations_to_cloud
        
        mock_request.return_value = {
            "data": {
                "queryTaskSkillRelations": '[]'
            }
        }
        
        q_settings = {"byowneruser": True}
        result = send_query_task_skill_relations_to_cloud(mock_session, mock_token, q_settings, mock_endpoint)
        
        mock_request.assert_called_once()
        assert result is not None
