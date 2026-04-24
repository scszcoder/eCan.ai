"""Unit tests for LightRAG Confidence Scorer."""

import pytest

pytestmark = pytest.mark.unit


class TestLightRAGConfidenceScorer:
    """Tests for knowledge retrieval confidence scoring."""

    def setup_method(self):
        from knowledge.lightrag_confidence_scorer import LightRAGConfidenceScorer

        self.scorer = LightRAGConfidenceScorer()
        self.query = "what is machine learning"
        self.response_text = (
            "Machine learning is a method where models learn from data. "
            "It is widely used in classification and prediction tasks."
        )

    def _score(self, references, chunks=None):
        response_data = {
            "response": self.response_text,
            "references": references,
        }
        if chunks is not None:
            response_data["data"] = {"chunks": chunks}
        return self.scorer.score(self.query, response_data)

    def test_prefers_rerank_scores_from_chunks(self):
        """Rerank scores from chunks take priority over reference similarity."""
        references = [
            {"file_path": "doc_a.txt", "reference_id": "r1", "similarity": 0.2},
            {"file_path": "doc_b.txt", "reference_id": "r2", "similarity": 0.3},
        ]
        chunks = [
            {"rerank_score": 0.81},
            {"rerank_score": 0.63},
        ]
        result = self._score(references=references, chunks=chunks)

        assert result.retrieval.get("score_source") == "rerank"
        assert result.retrieval.get("threshold") == 0.5
        assert result.retrieval.get("scored_refs") == 2
        assert abs(result.retrieval.get("top1") - 0.81) < 0.01

    def test_fallback_to_similarity_from_references(self):
        """Without chunks, falls back to similarity scores from references."""
        references = [
            {"file_path": "doc_a.txt", "reference_id": "r1", "similarity": 0.72},
            {"file_path": "doc_b.txt", "reference_id": "r2", "similarity": 0.61},
        ]
        result = self._score(references=references, chunks=[])

        assert result.retrieval.get("score_source") == "reference"
        assert result.retrieval.get("threshold") == 0.6
        assert result.retrieval.get("scored_refs") == 2
        assert abs(result.retrieval.get("top1") - 0.72) < 0.01

    def test_fallback_supports_distance_field(self):
        """Distance field can be used as fallback with distance-to-similarity conversion."""
        references = [
            {"file_path": "doc_a.txt", "reference_id": "r1", "distance": 0.2},
            {"file_path": "doc_b.txt", "reference_id": "r2", "distance": 2.0},
        ]
        result = self._score(references=references, chunks=[])

        # distance=0.2 → normalized score=0.8
        assert abs(result.retrieval.get("top1") - 0.8) < 0.01

    def test_empty_references_returns_none(self):
        """Empty references should not crash. top1 is None when no data to score."""
        result = self._score(references=[], chunks=None)
        # With empty references and no chunks, top1 is None (no score computed)
        assert result.retrieval.get("top1") is None
