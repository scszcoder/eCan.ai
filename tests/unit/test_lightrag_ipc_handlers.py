"""Unit tests for LightRAG IPC handlers."""

import pytest
from unittest.mock import MagicMock, patch

pytestmark = pytest.mark.unit


class TestLightRAGIPCHandlers:
    """Tests for LightRAG IPC handler functions."""

    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch):
        """Patch get_client before each test and restore after."""
        self.mock_client = MagicMock()
        # Patch get_client to return our mock for every call
        monkeypatch.setattr(
            "gui.ipc.w2p_handlers.lightrag_handler.get_client",
            lambda: self.mock_client,
        )
        # Import handler module after patching
        from gui.ipc.w2p_handlers import lightrag_handler

        self.handler = lightrag_handler
        self.mock_request = {
            "id": "test-id-123",
            "type": "request",
            "method": "test.method",
            "params": {},
            "timestamp": 1234567890,
        }

    # -------------------------------------------------------------------------
    # Ingest
    # -------------------------------------------------------------------------

    def test_handle_ingest_files_success(self):
        """Ingest files returns success on valid paths."""
        params = {"paths": ["/tmp/test.txt"]}
        self.mock_client.ingest_files.return_value = {"track_id": "123"}

        response = self.handler.handle_ingest_files(self.mock_request, params)

        assert response["status"] == "success"
        # Handler wraps return value in 'result' field
        assert response["result"]["track_id"] == "123"
        self.mock_client.ingest_files.assert_called_with(["/tmp/test.txt"], {})

    def test_handle_ingest_files_missing_params(self):
        """Missing paths parameter returns INVALID_PARAMS error."""
        response = self.handler.handle_ingest_files(self.mock_request, {})
        assert response["status"] == "error"
        assert response["error"]["code"] == "INVALID_PARAMS"

    # -------------------------------------------------------------------------
    # Query
    # -------------------------------------------------------------------------

    def test_handle_query_success(self):
        """Query handler returns answer on valid text."""
        params = {"text": "hello", "options": {"mode": "local"}}
        self.mock_client.query.return_value = {"status": "success", "data": "answer"}

        response = self.handler.handle_query(self.mock_request, params)

        assert response["status"] == "success"
        self.mock_client.query.assert_called_with("hello", {"mode": "local"})

    def test_handle_query_empty_text(self):
        """Empty query text returns error."""
        response = self.handler.handle_query(self.mock_request, {"text": ""})
        assert response["status"] == "error"

    def test_handle_query_graphs_success(self):
        """Graph query returns structured node/edge data."""
        params = {"label": "*", "maxDepth": 2, "maxNodes": 100}
        mock_graph_data = {"nodes": [{"id": "A"}], "edges": []}
        self.mock_client.query_graphs.return_value = mock_graph_data

        response = self.handler.handle_query_graphs(self.mock_request, params)

        assert response["status"] == "success"
        assert response["result"] == mock_graph_data
        self.mock_client.query_graphs.assert_called_with("*", 2, 100)

    # -------------------------------------------------------------------------
    # Labels
    # -------------------------------------------------------------------------

    def test_handle_get_graph_label_list(self):
        """Label list returns available entity types."""
        mock_labels = ["Person", "Organization"]
        # get_client is patched to return self.mock_client
        self.mock_client.get_graph_label_list.return_value = {
            "status": "success",
            "data": mock_labels,
        }

        response = self.handler.handle_get_graph_label_list(self.mock_request, {})

        assert response["status"] == "success"
        # Handler wraps data in 'result' field
        assert response["result"] == mock_labels

    # -------------------------------------------------------------------------
    # Text / Document operations
    # -------------------------------------------------------------------------

    def test_handle_insert_text_success(self):
        """Text insertion returns success."""
        params = {"text": "Sample content", "metadata": {"source": "test"}}
        self.mock_client.insert_text.return_value = {"status": "success"}

        response = self.handler.handle_insert_text(self.mock_request, params)

        assert response["status"] == "success"
        self.mock_client.insert_text.assert_called_with("Sample content", {"source": "test"})

    def test_handle_delete_document_success(self):
        """Document deletion returns success."""
        params = {"id": "doc-123"}
        self.mock_client.delete_document.return_value = {"status": "success"}

        response = self.handler.handle_delete_document(self.mock_request, params)

        assert response["status"] == "success"
        self.mock_client.delete_document.assert_called_with("doc-123")

    def test_handle_update_entity_success(self):
        """Entity update returns success with correct parameters."""
        params = {
            "entity_name": "Entity1",
            "updated_data": {"prop": "val"},
            "allow_rename": True,
        }
        self.mock_client.update_entity.return_value = {"status": "success"}

        response = self.handler.handle_update_entity(self.mock_request, params)

        assert response["status"] == "success"
        self.mock_client.update_entity.assert_called_with("Entity1", {"prop": "val"}, True, False)
