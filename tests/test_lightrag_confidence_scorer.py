import os
import sys
import unittest
import types
import logging

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Provide a minimal colorlog stub for environments where colorlog is not installed.
if "colorlog" not in sys.modules:
    colorlog_stub = types.ModuleType("colorlog")

    class ColoredFormatter(logging.Formatter):
        def __init__(self, *args, **kwargs):
            super().__init__("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    colorlog_stub.ColoredFormatter = ColoredFormatter
    sys.modules["colorlog"] = colorlog_stub

from knowledge.lightrag_confidence_scorer import LightRAGConfidenceScorer


class TestLightRAGConfidenceScorer(unittest.TestCase):
    def setUp(self):
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
        references = [
            {"file_path": "doc_a.txt", "reference_id": "r1", "similarity": 0.2},
            {"file_path": "doc_b.txt", "reference_id": "r2", "similarity": 0.3},
        ]
        chunks = [
            {"rerank_score": 0.81},
            {"rerank_score": 0.63},
        ]

        result = self._score(references=references, chunks=chunks)

        self.assertEqual(result.retrieval.get("score_source"), "rerank")
        self.assertEqual(result.retrieval.get("threshold"), 0.5)
        self.assertEqual(result.retrieval.get("scored_refs"), 2)
        self.assertAlmostEqual(result.retrieval.get("top1"), 0.81, places=4)

    def test_fallback_to_similarity_from_references(self):
        references = [
            {"file_path": "doc_a.txt", "reference_id": "r1", "similarity": 0.72},
            {"file_path": "doc_b.txt", "reference_id": "r2", "similarity": 0.61},
        ]

        result = self._score(references=references, chunks=[])

        self.assertEqual(result.retrieval.get("score_source"), "reference")
        self.assertEqual(result.retrieval.get("threshold"), 0.6)
        self.assertEqual(result.retrieval.get("scored_refs"), 2)
        self.assertAlmostEqual(result.retrieval.get("top1"), 0.72, places=4)

    def test_fallback_supports_distance_field(self):
        references = [
            {"file_path": "doc_a.txt", "reference_id": "r1", "distance": 0.2},
            {"file_path": "doc_b.txt", "reference_id": "r2", "distance": 2.0},
        ]

        result = self._score(references=references, chunks=[])

        # distance=0.2 -> normalized score=0.8
        self.assertEqual(result.retrieval.get("score_source"), "reference")
        self.assertEqual(result.retrieval.get("scored_refs"), 2)
        self.assertAlmostEqual(result.retrieval.get("top1"), 0.8, places=4)

    def test_zero_score_is_not_dropped(self):
        references = [
            {"file_path": "doc_a.txt", "reference_id": "r1", "score": 0.0},
        ]

        result = self._score(references=references, chunks=[])

        self.assertEqual(result.retrieval.get("score_source"), "reference")
        self.assertEqual(result.retrieval.get("scored_refs"), 1)
        self.assertEqual(result.retrieval.get("top1"), 0.0)


if __name__ == "__main__":
    unittest.main()
