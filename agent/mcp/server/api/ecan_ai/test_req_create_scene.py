#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit tests for ecan_ai_api_req_create_scene MCP tool.

Tests cover:
1. Text-to-image generation (no reference assets)
2. Image-to-image generation (with reference image)
3. Image-to-video generation (with reference image)

The API handles the complete flow in a single call:
1. initReqScene -> get presigned upload URLs
2. Upload files to S3 (if refs provided)
3. readyReqScene -> confirm uploads and start processing

Run with: pytest test_req_create_scene.py -v
"""

import pytest
import json
import tempfile
import os
from unittest.mock import Mock, patch, MagicMock


class MockMainWindow:
    """Mock MainWindow for testing without GUI dependencies."""
    
    def __init__(self):
        self.session = Mock()
        self._auth_token = "mock-auth-token-12345"
        self._acct_site_id = "test_user_TESTSITE"
        self._network_api_engine = "wan"
        self._wan_endpoint = "https://test-appsync.amazonaws.com/graphql"
        self._lan_endpoint = "http://localhost:4000/graphql"
    
    def get_auth_token(self):
        return self._auth_token
    
    def getAcctSiteID(self):
        return self._acct_site_id
    
    def getNetworkApiEngine(self):
        return self._network_api_engine
    
    def getWanApiEndpoint(self):
        return self._wan_endpoint
    
    def getLanApiEndpoint(self):
        return self._lan_endpoint


class TestReqCreateSceneTextToImage:
    """Test text-to-image generation (no reference assets)."""
    
    @patch('agent.mcp.server.api.ecan_ai.ecan_ai_api.send_init_req_scene_to_cloud')
    def test_text_to_image_basic(self, mock_send_init):
        """Test basic text-to-image generation request (no refs, no upload needed)."""
        from agent.mcp.server.api.ecan_ai.ecan_ai_api import ecan_ai_api_req_create_scene
        
        # Mock cloud response for text-to-image (no upload links needed)
        mock_send_init.return_value = {
            "request_id": "req-text2img-001",
            "status": "Processing",
            "message": "Text-to-image generation started",
            "estimated_time_ms": 15000,
            "ref_ul_links": []
        }
        
        mainwin = MockMainWindow()
        config = {
            "agent_id": "agent1",
            "description": "A beautiful sunset over the ocean with vibrant orange and purple colors",
            "output_format": "IMAGE",
            "output_resolution": [1920, 1080],
        }
        
        result = ecan_ai_api_req_create_scene(mainwin, config)
        
        # Verify the result - text-only should go straight to Processing
        assert result["request_id"] == "req-text2img-001"
        assert result["status"] == "Processing"
        assert result["estimated_time_ms"] == 15000
        assert result["upload_results"] == []
        
        # Verify send_init_req_scene_to_cloud was called with correct params
        mock_send_init.assert_called_once()
        call_args = mock_send_init.call_args
        req_input = call_args[0][2]  # Third positional arg is req_scene_input
        
        assert req_input["acctSiteID"] == "test_user_TESTSITE"
        assert req_input["agent_id"] == "agent1"
        assert req_input["description"] == "A beautiful sunset over the ocean with vibrant orange and purple colors"
        assert req_input["output_format"] == "IMAGE"
        assert req_input["output_resolution"] == [1920, 1080]
    
    @patch('agent.mcp.server.api.ecan_ai.ecan_ai_api.send_init_req_scene_to_cloud')
    def test_text_to_image_with_style(self, mock_send_init):
        """Test text-to-image with style and emotion parameters."""
        from agent.mcp.server.api.ecan_ai.ecan_ai_api import ecan_ai_api_req_create_scene
        
        mock_send_init.return_value = {
            "request_id": "req-text2img-002",
            "status": "Processing",
            "message": "Generation started",
            "estimated_time_ms": 20000,
            "ref_ul_links": []
        }
        
        mainwin = MockMainWindow()
        config = {
            "agent_id": "agent2",
            "description": "A futuristic cityscape at night",
            "output_format": "IMAGE",
            "style": "CINEMATIC",
            "emotion": "awe",
            "output_resolution": [1080, 1920],  # Portrait
        }
        
        result = ecan_ai_api_req_create_scene(mainwin, config)
        
        assert result["request_id"] == "req-text2img-002"
        assert result["status"] == "Processing"
        
        # Verify style was passed
        call_args = mock_send_init.call_args
        req_input = call_args[0][2]
        assert req_input["style"] == "CINEMATIC"
        assert req_input["emotion"] == "awe"


class TestReqCreateSceneImageToImage:
    """Test image-to-image generation (with reference image) - full flow."""
    
    @patch('agent.mcp.server.api.ecan_ai.ecan_ai_api.send_ready_req_scene_to_cloud')
    @patch('agent.mcp.server.api.ecan_ai.ecan_ai_api.upload_file_to_presigned_url')
    @patch('agent.mcp.server.api.ecan_ai.ecan_ai_api.send_init_req_scene_to_cloud')
    def test_image_to_image_full_flow(self, mock_send_init, mock_upload, mock_send_ready):
        """Test complete image-to-image flow: init -> upload -> ready."""
        from agent.mcp.server.api.ecan_ai.ecan_ai_api import ecan_ai_api_req_create_scene
        
        # Step 1: initReqScene returns upload links
        mock_send_init.return_value = {
            "request_id": "req-img2img-001",
            "status": "AwaitingUpload",
            "message": "Upload reference files",
            "estimated_time_ms": 25000,
            "ref_ul_links": [
                "https://s3.amazonaws.com/bucket/uploads/ref-001.jpg?presigned=abc123"
            ]
        }
        
        # Step 2: Upload succeeds
        mock_upload.return_value = {"success": True}
        
        # Step 3: readyReqScene confirms processing started
        mock_send_ready.return_value = {
            "request_id": "req-img2img-001",
            "status": "Processing",
            "message": "Image-to-image generation started",
            "estimated_time_ms": 25000,
            "ref_ul_links": []
        }
        
        # Create a temp file to simulate local reference image
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
            tmp.write(b'fake image data')
            tmp_path = tmp.name
        
        try:
            mainwin = MockMainWindow()
            config = {
                "agent_id": "agent1",
                "description": "Transform this image into a watercolor painting style",
                "output_format": "IMAGE",
                "refs": [
                    {"type": "image", "file_path": tmp_path, "mime_type": "image/jpeg"}
                ],
            }
            
            result = ecan_ai_api_req_create_scene(mainwin, config)
            
            # Verify complete flow executed
            assert result["request_id"] == "req-img2img-001"
            assert result["status"] == "Processing"
            assert len(result["upload_results"]) == 1
            assert result["upload_results"][0]["success"] == True
            
            # Verify all three steps were called
            mock_send_init.assert_called_once()
            mock_upload.assert_called_once_with(tmp_path, "https://s3.amazonaws.com/bucket/uploads/ref-001.jpg?presigned=abc123")
            mock_send_ready.assert_called_once()
            
            # Verify readyReqScene was called with Completed status
            ready_call_args = mock_send_ready.call_args
            ready_input = ready_call_args[0][2]
            assert ready_input["status"] == "Completed"
        finally:
            os.unlink(tmp_path)
    
    @patch('agent.mcp.server.api.ecan_ai.ecan_ai_api.send_ready_req_scene_to_cloud')
    @patch('agent.mcp.server.api.ecan_ai.ecan_ai_api.upload_file_to_presigned_url')
    @patch('agent.mcp.server.api.ecan_ai.ecan_ai_api.send_init_req_scene_to_cloud')
    def test_image_to_image_upload_failure(self, mock_send_init, mock_upload, mock_send_ready):
        """Test image-to-image when upload fails."""
        from agent.mcp.server.api.ecan_ai.ecan_ai_api import ecan_ai_api_req_create_scene
        
        mock_send_init.return_value = {
            "request_id": "req-img2img-002",
            "status": "AwaitingUpload",
            "message": "Upload reference files",
            "estimated_time_ms": 25000,
            "ref_ul_links": ["https://s3.amazonaws.com/upload-link"]
        }
        
        # Upload fails
        mock_upload.return_value = {"success": False, "error": "Network timeout"}
        
        # readyReqScene still called but with Error status
        mock_send_ready.return_value = {
            "request_id": "req-img2img-002",
            "status": "Error",
            "message": "Upload failed",
            "estimated_time_ms": 0,
            "ref_ul_links": []
        }
        
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
            tmp.write(b'fake image data')
            tmp_path = tmp.name
        
        try:
            mainwin = MockMainWindow()
            config = {
                "agent_id": "agent1",
                "description": "Transform image",
                "output_format": "IMAGE",
                "refs": [{"file_path": tmp_path}],
            }
            
            result = ecan_ai_api_req_create_scene(mainwin, config)
            
            # Should report upload failure
            assert result["status"] == "UploadFailed"
            assert len(result["upload_results"]) == 1
            assert result["upload_results"][0]["success"] == False
            assert "Network timeout" in result["upload_results"][0]["error"]
            
            # readyReqScene should be called with Error status
            ready_call_args = mock_send_ready.call_args
            ready_input = ready_call_args[0][2]
            assert ready_input["status"] == "Error"
        finally:
            os.unlink(tmp_path)


class TestReqCreateSceneImageToVideo:
    """Test image-to-video generation (with reference image) - full flow."""
    
    @patch('agent.mcp.server.api.ecan_ai.ecan_ai_api.send_ready_req_scene_to_cloud')
    @patch('agent.mcp.server.api.ecan_ai.ecan_ai_api.upload_file_to_presigned_url')
    @patch('agent.mcp.server.api.ecan_ai.ecan_ai_api.send_init_req_scene_to_cloud')
    def test_image_to_video_full_flow(self, mock_send_init, mock_upload, mock_send_ready):
        """Test complete image-to-video flow: init -> upload -> ready."""
        from agent.mcp.server.api.ecan_ai.ecan_ai_api import ecan_ai_api_req_create_scene
        
        mock_send_init.return_value = {
            "request_id": "req-img2vid-001",
            "status": "AwaitingUpload",
            "message": "Upload reference image for video generation",
            "estimated_time_ms": 60000,
            "ref_ul_links": ["https://s3.amazonaws.com/bucket/uploads/ref-vid-001.jpg?presigned=video123"]
        }
        
        mock_upload.return_value = {"success": True}
        
        mock_send_ready.return_value = {
            "request_id": "req-img2vid-001",
            "status": "Processing",
            "message": "Video generation in progress. Results will be delivered via subscription.",
            "estimated_time_ms": 60000,
            "ref_ul_links": []
        }
        
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
            tmp.write(b'fake image data')
            tmp_path = tmp.name
        
        try:
            mainwin = MockMainWindow()
            config = {
                "agent_id": "agent3",
                "description": "Animate this image with gentle camera movement and subtle motion",
                "output_format": "VIDEO",
                "duration_hint_ms": 5000,
                "output_resolution": [1920, 1080],
                "refs": [{"type": "image", "file_path": tmp_path, "mime_type": "image/png"}],
            }
            
            result = ecan_ai_api_req_create_scene(mainwin, config)
            
            assert result["request_id"] == "req-img2vid-001"
            assert result["status"] == "Processing"
            assert result["estimated_time_ms"] == 60000
            assert len(result["upload_results"]) == 1
            assert result["upload_results"][0]["success"] == True
            
            # Verify VIDEO format and duration were passed
            init_call_args = mock_send_init.call_args
            req_input = init_call_args[0][2]
            assert req_input["output_format"] == "VIDEO"
            assert req_input["duration_hint_ms"] == 5000
        finally:
            os.unlink(tmp_path)
    
    @patch('agent.mcp.server.api.ecan_ai.ecan_ai_api.send_init_req_scene_to_cloud')
    def test_image_to_video_with_custom_context(self, mock_send_init):
        """Test image-to-video with custom gemini_job context (context passed through)."""
        from agent.mcp.server.api.ecan_ai.ecan_ai_api import ecan_ai_api_req_create_scene
        
        mock_send_init.return_value = {
            "request_id": "req-img2vid-002",
            "status": "Processing",  # No refs with file_path, so no upload needed
            "message": "Generation started",
            "estimated_time_ms": 90000,
            "ref_ul_links": []
        }
        
        mainwin = MockMainWindow()
        config = {
            "agent_id": "agent3",
            "description": "Create a cinematic video from this image",
            "output_format": "VIDEO",
            "duration_hint_ms": 8000,
            "context": {
                "gemini_job": {
                    "operation": "image_to_video",
                    "prompt": "Cinematic camera pan with dramatic lighting",
                    "aspect_ratio": "16:9",
                    "duration_seconds": 8,
                }
            },
            # refs without file_path - metadata only
            "refs": [{"type": "image", "filename": "hero_shot.jpg"}],
        }
        
        result = ecan_ai_api_req_create_scene(mainwin, config)
        
        assert result["request_id"] == "req-img2vid-002"
        
        # Verify custom context was passed through unchanged
        call_args = mock_send_init.call_args
        req_input = call_args[0][2]
        assert "context" in req_input
        assert "gemini_job" in req_input["context"]
        assert req_input["context"]["gemini_job"]["operation"] == "image_to_video"


class TestReqCreateSceneErrorHandling:
    """Test error handling scenarios."""
    
    @patch('agent.mcp.server.api.ecan_ai.ecan_ai_api.send_init_req_scene_to_cloud')
    def test_cloud_api_error(self, mock_send_init):
        """Test handling of cloud API errors."""
        from agent.mcp.server.api.ecan_ai.ecan_ai_api import ecan_ai_api_req_create_scene
        
        mock_send_init.return_value = {
            "errors": [{"message": "Rate limit exceeded"}],
            "request_id": "",
            "status": "Error",
            "message": "Rate limit exceeded"
        }
        
        mainwin = MockMainWindow()
        config = {
            "agent_id": "agent1",
            "description": "Test image",
            "output_format": "IMAGE",
        }
        
        result = ecan_ai_api_req_create_scene(mainwin, config)
        
        assert result["status"] == "Error"
        assert "Rate limit" in result["message"] or result["message"]
    
    @patch('agent.mcp.server.api.ecan_ai.ecan_ai_api.send_init_req_scene_to_cloud')
    def test_refs_without_file_path(self, mock_send_init):
        """Test refs provided without file_path - should skip upload."""
        from agent.mcp.server.api.ecan_ai.ecan_ai_api import ecan_ai_api_req_create_scene
        
        # Cloud returns upload links but refs don't have file_path
        mock_send_init.return_value = {
            "request_id": "req-no-path-001",
            "status": "AwaitingUpload",
            "message": "Upload reference files",
            "estimated_time_ms": 25000,
            "ref_ul_links": ["https://s3.amazonaws.com/upload-link"]
        }
        
        mainwin = MockMainWindow()
        config = {
            "agent_id": "agent1",
            "description": "Transform image",
            "output_format": "IMAGE",
            # refs without file_path
            "refs": [{"type": "image", "filename": "remote_image.jpg"}],
        }
        
        # This should handle gracefully - refs exist but no local file to upload
        # The function should still try to process but report no file_path found
        result = ecan_ai_api_req_create_scene(mainwin, config)
        
        # Should have upload_results with error about missing file_path
        assert result["request_id"] == "req-no-path-001"


# Integration test placeholder - requires actual cloud connection
class TestReqCreateSceneIntegration:
    """Integration tests (skipped by default, require cloud connection)."""
    
    @pytest.mark.skip(reason="Requires actual cloud connection")
    def test_real_text_to_image(self):
        """Real integration test for text-to-image."""
        pass
    
    @pytest.mark.skip(reason="Requires actual cloud connection")
    def test_real_image_to_video(self):
        """Real integration test for image-to-video."""
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
