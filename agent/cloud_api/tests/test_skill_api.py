"""
Unit Tests for Skill Cloud API Operations

Tests for add, update, delete, and query operations on the AgentSkill table.
Includes tests for skill file upload functionality with presigned URLs.
"""

import pytest
import json
import os
import tempfile
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


class TestSkillFileUpload:
    """Test suite for Skill file upload functionality"""
    
    def test_collect_skill_files(self):
        """Test collecting files from skill directory"""
        from agent.cloud_api.cloud_api import collect_skill_files
        
        # Create temp directory with test files
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            os.makedirs(os.path.join(tmpdir, "subdir"))
            with open(os.path.join(tmpdir, "main.py"), "w") as f:
                f.write("# main file")
            with open(os.path.join(tmpdir, "config.json"), "w") as f:
                f.write("{}")
            with open(os.path.join(tmpdir, "subdir", "helper.py"), "w") as f:
                f.write("# helper file")
            
            # Collect files
            files = collect_skill_files(tmpdir)
            
            assert len(files) == 3
            assert "main.py" in files
            assert "config.json" in files
            assert "subdir/helper.py" in files
    
    def test_collect_skill_files_empty_dir(self):
        """Test collecting files from empty directory"""
        from agent.cloud_api.cloud_api import collect_skill_files
        
        with tempfile.TemporaryDirectory() as tmpdir:
            files = collect_skill_files(tmpdir)
            assert files == []
    
    def test_collect_skill_files_nonexistent_dir(self):
        """Test collecting files from non-existent directory"""
        from agent.cloud_api.cloud_api import collect_skill_files
        
        files = collect_skill_files("/nonexistent/path/to/skill")
        assert files == []
    
    def test_build_skill_source_string(self):
        """Test building comma-separated source string"""
        from agent.cloud_api.cloud_api import build_skill_source_string
        
        file_paths = ["main.py", "config.json", "subdir/helper.py"]
        source = build_skill_source_string(file_paths)
        
        assert source == "main.py,config.json,subdir/helper.py"
    
    def test_build_skill_source_string_empty(self):
        """Test building source string with empty list"""
        from agent.cloud_api.cloud_api import build_skill_source_string
        
        source = build_skill_source_string([])
        assert source == ""
    
    def test_prepare_skill_with_source(self, sample_skill):
        """Test preparing skill with source attribute"""
        from agent.cloud_api.cloud_api import prepare_skill_with_source
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            with open(os.path.join(tmpdir, "skill.py"), "w") as f:
                f.write("# skill code")
            with open(os.path.join(tmpdir, "data.json"), "w") as f:
                f.write("{}")
            
            sample_skill['path'] = tmpdir
            prepared = prepare_skill_with_source(sample_skill)
            
            assert 'source' in prepared
            assert "skill.py" in prepared['source']
            assert "data.json" in prepared['source']
    
    def test_prepare_skill_with_source_no_directory(self, sample_skill):
        """Test preparing skill when directory doesn't exist"""
        from agent.cloud_api.cloud_api import prepare_skill_with_source
        
        sample_skill['path'] = "/nonexistent/path"
        sample_skill['source'] = "existing_source.py"
        prepared = prepare_skill_with_source(sample_skill)
        
        assert prepared['source'] == "existing_source.py"
    
    @patch('agent.cloud_api.cloud_api.send_file_with_presigned_url')
    def test_upload_skill_files_with_presigned_urls(self, mock_upload):
        """Test uploading skill files with presigned URLs"""
        from agent.cloud_api.cloud_api import upload_skill_files_with_presigned_urls
        
        mock_upload.return_value = 200
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test file
            with open(os.path.join(tmpdir, "test.py"), "w") as f:
                f.write("# test")
            
            presigned_urls = [{"url": "https://s3.example.com/upload", "fields": {}}]
            file_paths = ["test.py"]
            
            result = upload_skill_files_with_presigned_urls(
                None, tmpdir, presigned_urls, file_paths
            )
            
            assert len(result['success']) == 1
            assert len(result['failed']) == 0
            mock_upload.assert_called_once()
    
    @patch('agent.cloud_api.cloud_api.send_file_with_presigned_url')
    def test_upload_skill_files_file_not_found(self, mock_upload):
        """Test uploading when file doesn't exist"""
        from agent.cloud_api.cloud_api import upload_skill_files_with_presigned_urls
        
        with tempfile.TemporaryDirectory() as tmpdir:
            presigned_urls = [{"url": "https://s3.example.com/upload", "fields": {}}]
            file_paths = ["nonexistent.py"]
            
            result = upload_skill_files_with_presigned_urls(
                None, tmpdir, presigned_urls, file_paths
            )
            
            assert len(result['success']) == 0
            assert len(result['failed']) == 1
            assert result['failed'][0]['error'] == 'File not found'
            mock_upload.assert_not_called()
    
    @patch('agent.cloud_api.cloud_api.appsync_http_request')
    def test_send_add_skills_with_files_to_cloud(self, mock_request, mock_session, mock_token, mock_endpoint, sample_skill):
        """Test adding skills with file upload support"""
        from agent.cloud_api.cloud_api import send_add_skills_with_files_to_cloud
        
        mock_request.return_value = {
            "data": {
                "addAgentSkills": '{"success": true, "count": 1}'
            }
        }
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test file
            with open(os.path.join(tmpdir, "skill.py"), "w") as f:
                f.write("# skill code")
            
            sample_skill['path'] = tmpdir
            
            result = send_add_skills_with_files_to_cloud(
                mock_session, [sample_skill], mock_token, mock_endpoint
            )
            
            assert 'cloud_response' in result
            assert 'upload_results' in result
            assert result['skills_processed'] == 1
            mock_request.assert_called_once()
    
    @patch('agent.cloud_api.cloud_api.appsync_http_request')
    def test_send_update_skills_with_files_to_cloud(self, mock_request, mock_session, mock_token, mock_endpoint, sample_skill):
        """Test updating skills with file upload support"""
        from agent.cloud_api.cloud_api import send_update_skills_with_files_to_cloud
        
        mock_request.return_value = {
            "data": {
                "updateAgentSkills": '{"success": true, "count": 1}'
            }
        }
        
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "skill.py"), "w") as f:
                f.write("# updated skill code")
            
            sample_skill['path'] = tmpdir
            
            result = send_update_skills_with_files_to_cloud(
                mock_session, [sample_skill], mock_token, mock_endpoint
            )
            
            assert 'cloud_response' in result
            assert 'upload_results' in result
            assert result['skills_processed'] == 1
            mock_request.assert_called_once()
    
    @patch('agent.cloud_api.cloud_api.send_file_with_presigned_url')
    @patch('agent.cloud_api.cloud_api.appsync_http_request')
    def test_send_add_skills_with_presigned_url_response(self, mock_request, mock_upload, mock_session, mock_token, mock_endpoint, sample_skill):
        """Test adding skills when cloud returns presigned URLs"""
        from agent.cloud_api.cloud_api import send_add_skills_with_files_to_cloud
        
        skill_id = sample_skill.get('askid', 'test_skill_id')
        
        mock_request.return_value = {
            "data": {
                "addAgentSkills": json.dumps({
                    "success": True,
                    "presigned_urls": {
                        skill_id: [{"url": "https://s3.example.com/upload", "fields": {}}]
                    }
                })
            }
        }
        mock_upload.return_value = 200
        
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "skill.py"), "w") as f:
                f.write("# skill code")
            
            sample_skill['path'] = tmpdir
            sample_skill['askid'] = skill_id
            
            result = send_add_skills_with_files_to_cloud(
                mock_session, [sample_skill], mock_token, mock_endpoint
            )
            
            assert 'cloud_response' in result
            assert result['skills_processed'] == 1
    
    def test_skill_source_in_graphql_mutation(self, sample_skill):
        """Test that source field is included in GraphQL mutation"""
        from agent.cloud_api.graphql_builder import build_mutation
        
        sample_skill['source'] = "main.py,config.json,utils/helper.py"
        
        mutation = build_mutation(DataType.SKILL, Operation.ADD, [sample_skill])
        
        assert "source:" in mutation or "source" in mutation
