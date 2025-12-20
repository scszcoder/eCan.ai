"""
LightRAG Query Response Confidence Scorer

This module provides a comprehensive scoring system to evaluate the confidence/quality
of LightRAG query responses based on various metrics.

Author: eCan.ai Team
Date: 2025-12-10
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
import re
import statistics
from utils.logger_helper import logger_helper as logger


@dataclass
class ConfidenceScore:
    """Confidence score result with detailed breakdown."""
    
    overall_score: float  # 0.0 - 1.0
    reference_score: float  # 0.0 - 1.0
    content_quality_score: float  # 0.0 - 1.0
    relevance_score: float  # 0.0 - 1.0
    completeness_score: float  # 0.0 - 1.0
    
    # Detailed metrics
    reference_count: int = 0
    response_length: int = 0
    has_structured_content: bool = False
    keyword_match_ratio: float = 0.0
    
    # Confidence level
    confidence_level: str = "unknown"  # low, medium, high, very_high
    
    # Explanation
    explanation: str = ""

    # Retrieval & decision signals (backward compatible: new fields only)
    retrieval: Dict[str, Any] = field(default_factory=dict)
    decision: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "overall_score": round(self.overall_score, 3),
            "confidence_level": self.confidence_level,
            "breakdown": {
                "reference_score": round(self.reference_score, 3),
                "content_quality_score": round(self.content_quality_score, 3),
                "relevance_score": round(self.relevance_score, 3),
                "completeness_score": round(self.completeness_score, 3),
            },
            "metrics": {
                "reference_count": self.reference_count,
                "response_length": self.response_length,
                "has_structured_content": self.has_structured_content,
                "keyword_match_ratio": round(self.keyword_match_ratio, 3),
            },
            "signals": {
                "retrieval": self.retrieval,
            },
            "decision": self.decision,
            "explanation": self.explanation
        }


class LightRAGConfidenceScorer:
    """
    Evaluate confidence/quality of LightRAG query responses.
    
    Scoring Dimensions:
    1. Reference Score: Based on number and quality of references
    2. Content Quality Score: Based on response structure and completeness
    3. Relevance Score: Based on keyword matching and context
    4. Completeness Score: Based on response length and detail
    
    Overall Score = weighted average of all dimensions
    """
    
    def __init__(
        self,
        reference_weight: float = 0.3,
        content_quality_weight: float = 0.25,
        relevance_weight: float = 0.25,
        completeness_weight: float = 0.2
    ):
        """
        Initialize scorer with custom weights.
        
        Args:
            reference_weight: Weight for reference score (default: 0.3)
            content_quality_weight: Weight for content quality (default: 0.25)
            relevance_weight: Weight for relevance score (default: 0.25)
            completeness_weight: Weight for completeness score (default: 0.2)
        """
        self.reference_weight = reference_weight
        self.content_quality_weight = content_quality_weight
        self.relevance_weight = relevance_weight
        self.completeness_weight = completeness_weight
        
        # Validate weights sum to 1.0
        total_weight = sum([
            reference_weight, content_quality_weight,
            relevance_weight, completeness_weight
        ])
        if abs(total_weight - 1.0) > 0.01:
            logger.warning(
                f"Weights sum to {total_weight}, not 1.0. "
                f"Scores may not be properly normalized."
            )
    
    def score(
        self,
        query: str,
        response_data: Dict[str, Any],
        query_options: Optional[Dict[str, Any]] = None
    ) -> ConfidenceScore:
        """
        Calculate confidence score for a LightRAG query response.
        
        Args:
            query: Original query text
            response_data: LightRAG response data containing:
                - response: str (the answer text)
                - references: List[Dict] (optional, reference list)
            query_options: Optional query parameters used (mode, top_k, etc.)
        
        Returns:
            ConfidenceScore object with detailed breakdown
        """
        try:
            # Extract response and references
            response_text = response_data.get("response", "")
            references = response_data.get("references", [])
            
            # Also try to get chunks from data (for /query/data endpoint or enriched responses)
            # chunks may contain rerank_score which references don't have
            chunks = response_data.get("data", {}).get("chunks", []) if isinstance(response_data.get("data"), dict) else []

            # IMPORTANT: Filter out invalid/empty references and deduplicate
            # Only count references that have actual content (file_path or reference_id)
            valid_references = []
            seen_file_paths = set()  # For deduplication
            for ref in references:
                if isinstance(ref, dict):
                    # Check if reference has meaningful data
                    file_path = ref.get('file_path', '')
                    has_file_path = file_path and file_path != 'unknown_source'
                    has_ref_id = ref.get('reference_id')
                    if has_file_path or has_ref_id:
                        # Deduplicate by file_path
                        if file_path and file_path in seen_file_paths:
                            continue  # Skip duplicate
                        if file_path:
                            seen_file_paths.add(file_path)
                        valid_references.append(ref)
            
            # Use valid_references instead of all references
            references = valid_references
            logger.debug(f"Filtered references: {len(valid_references)} unique valid out of {len(response_data.get('references', []))} total")

            # Extract retrieval scores from multiple sources:
            # 1. First try references (may have score from /query/data endpoint)
            # 2. Then try chunks (may have rerank_score from reranking)
            scores: List[float] = []
            
            # Try to get scores from references first
            for ref in references:
                if isinstance(ref, dict):
                    score_val = ref.get('score') or ref.get('similarity') or ref.get('relevance')
                    if score_val is not None:
                        try:
                            scores.append(float(score_val))
                        except (ValueError, TypeError):
                            pass
            
            # If no scores from references, try to get from chunks (rerank_score)
            if not scores and chunks:
                for chunk in chunks:
                    if isinstance(chunk, dict):
                        # Try rerank_score first (from reranking), then other score fields
                        score_val = chunk.get('rerank_score') or chunk.get('score') or chunk.get('similarity')
                        if score_val is not None:
                            try:
                                scores.append(float(score_val))
                            except (ValueError, TypeError):
                                pass
                logger.debug(f"Extracted {len(scores)} scores from chunks (rerank_score)")

            scores_sorted = sorted(scores, reverse=True)
            top1 = scores_sorted[0] if len(scores_sorted) >= 1 else None
            top2 = scores_sorted[1] if len(scores_sorted) >= 2 else None
            avg = (sum(scores_sorted) / len(scores_sorted)) if scores_sorted else None
            gap = (top1 - top2) if (top1 is not None and top2 is not None) else None
            std = None
            if len(scores_sorted) >= 2:
                try:
                    std = statistics.pstdev(scores_sorted)
                except Exception:
                    std = None

            # Rerank score threshold - lowered from 0.60 to 0.50 for better recall
            # Rerank scores are typically lower than embedding similarity scores
            retrieval_threshold = 0.50
            supporting_refs = sum(1 for s in scores_sorted if s >= retrieval_threshold)
            retrieval_signal: Dict[str, Any] = {
                "threshold": retrieval_threshold,
                "top1": round(top1, 4) if top1 is not None else None,
                "top2": round(top2, 4) if top2 is not None else None,
                "gap": round(gap, 4) if gap is not None else None,
                "avg": round(avg, 4) if avg is not None else None,
                "std": round(std, 4) if std is not None else None,
                "supporting_refs": int(supporting_refs),
                "scored_refs": int(len(scores_sorted)),
            }
            
            # Calculate individual scores
            # Pass scores_sorted to _calculate_reference_score as external_scores
            # This allows using rerank_score from chunks when references don't have score fields
            ref_score = self._calculate_reference_score(references, external_scores=scores_sorted)
            quality_score = self._calculate_content_quality_score(response_text)
            relevance_score = self._calculate_relevance_score(query, response_text)
            completeness_score = self._calculate_completeness_score(
                response_text, query, query_options
            )
            
            # Calculate weighted overall score
            overall = (
                ref_score * self.reference_weight +
                quality_score * self.content_quality_weight +
                relevance_score * self.relevance_weight +
                completeness_score * self.completeness_weight
            )

            # Decision: should we answer or decline due to weak retrieval?
            # Optimized logic: focus on overall score and reference count, not just retrieval threshold
            should_answer = True
            no_answer_reason = None
            if len(references) == 0:
                should_answer = False
                no_answer_reason = "no_references"
            elif overall < 0.25:
                # Only decline if overall confidence is very low
                should_answer = False
                no_answer_reason = "overall_too_low"
            # Note: Removed strict retrieval_below_threshold check
            # If we have references and reasonable overall score, we should answer
            # The confidence score itself will indicate quality to the user

            decision: Dict[str, Any] = {
                "should_answer": bool(should_answer),
                "no_answer_reason": no_answer_reason,
            }
            
            # Determine confidence level
            confidence_level = self._determine_confidence_level(overall)
            
            # Generate explanation
            explanation = self._generate_explanation(
                overall, ref_score, quality_score, relevance_score,
                completeness_score, len(references), len(response_text)
            )
            
            # Extract keywords for matching ratio
            query_keywords = self._extract_keywords(query)
            response_keywords = self._extract_keywords(response_text)
            keyword_match_ratio = self._calculate_keyword_match_ratio(
                query_keywords, response_keywords
            )
            
            return ConfidenceScore(
                overall_score=overall,
                reference_score=ref_score,
                content_quality_score=quality_score,
                relevance_score=relevance_score,
                completeness_score=completeness_score,
                reference_count=len(references),
                response_length=len(response_text),
                has_structured_content=self._has_structured_content(response_text),
                keyword_match_ratio=keyword_match_ratio,
                confidence_level=confidence_level,
                explanation=explanation,
                retrieval=retrieval_signal,
                decision=decision
            )
            
        except Exception as e:
            logger.error(f"Error calculating confidence score: {e}")
            return ConfidenceScore(
                overall_score=0.0,
                reference_score=0.0,
                content_quality_score=0.0,
                relevance_score=0.0,
                completeness_score=0.0,
                confidence_level="unknown",
                explanation=f"Error calculating score: {str(e)}",
                retrieval={},
                decision={"should_answer": False, "no_answer_reason": "scoring_error"}
            )
    
    def _calculate_reference_score(self, references: List[Dict[str, Any]], external_scores: List[float] = None) -> float:
        """
        Calculate score based on references.
        
        Scoring logic (improved with similarity scores):
        - Uses both reference count AND similarity scores (if available)
        - Similarity threshold: 0.6 (industry standard for RAG)
        - 0 references: 0.0
        - 1 reference: 0.4
        - 2 references: 0.6
        - 3 references: 0.75
        - 4+ references: 0.85
        - 6+ references: 0.95
        - 10+ references: 1.0
        
        Args:
            references: List of reference dictionaries
            external_scores: Optional list of scores from chunks (rerank_score)
        """
        ref_count = len(references)
        
        if ref_count == 0:
            return 0.0
        
        # Base score from count
        if ref_count == 1:
            count_score = 0.4
        elif ref_count == 2:
            count_score = 0.6
        elif ref_count == 3:
            count_score = 0.75
        elif ref_count < 6:
            count_score = 0.85
        elif ref_count < 10:
            count_score = 0.95
        else:
            count_score = 1.0
        
        # Check if references have similarity/score fields
        # Common field names: 'score', 'similarity', 'relevance', 'distance'
        scores = []
        for ref in references:
            if isinstance(ref, dict):
                # Try common score field names
                score = ref.get('score') or ref.get('similarity') or ref.get('relevance')
                if score is not None:
                    try:
                        scores.append(float(score))
                    except (ValueError, TypeError):
                        pass
        
        # If no scores from references, use external scores (from chunks rerank_score)
        if not scores and external_scores:
            scores = external_scores
            logger.debug(f"Using {len(scores)} external scores (from chunks) for reference scoring")
        
        # If we have similarity scores, adjust the confidence
        if scores:
            avg_similarity = sum(scores) / len(scores)
            
            # Adjusted thresholds for rerank scores (typically lower than embedding similarity):
            # >= 0.70: strong match
            # 0.50-0.70: moderate match
            # < 0.50: weak match
            if avg_similarity >= 0.70:
                similarity_factor = 1.0
            elif avg_similarity >= 0.50:
                similarity_factor = 0.7 + (avg_similarity - 0.50) * 1.5  # 0.7-1.0
            else:
                similarity_factor = avg_similarity / 0.50  # 0.0-0.7
            
            # Combine count score with similarity factor
            # Weight: 60% count, 40% similarity
            final_score = count_score * 0.6 + (count_score * similarity_factor) * 0.4
            
            logger.debug(f"Reference score: count={ref_count}, avg_sim={avg_similarity:.3f}, "
                        f"count_score={count_score:.3f}, final={final_score:.3f}")
            
            return min(final_score, 1.0)
        
        # Fallback to count-only score if no similarity data
        return count_score
    
    def _calculate_content_quality_score(self, response: str) -> float:
        """
        Calculate score based on content quality.
        
        Factors:
        - Has structured content (lists, paragraphs)
        - Proper punctuation
        - Reasonable length
        - No error messages
        """
        if not response or len(response.strip()) == 0:
            return 0.0
        
        score = 0.5  # Base score for non-empty response
        
        # Check for structured content
        if self._has_structured_content(response):
            score += 0.2
        
        # Check for proper punctuation
        if self._has_proper_punctuation(response):
            score += 0.15
        
        # Check length is reasonable (not too short, not error message)
        if len(response) > 50 and not self._is_error_message(response):
            score += 0.15
        
        return min(score, 1.0)
    
    def _calculate_relevance_score(self, query: str, response: str) -> float:
        """
        Calculate relevance score based on keyword matching.
        
        Factors:
        - Query keywords present in response
        - Semantic similarity (simplified)
        """
        if not query or not response:
            return 0.0
        
        query_keywords = self._extract_keywords(query)
        response_keywords = self._extract_keywords(response)
        
        if not query_keywords:
            return 0.5  # Neutral score if no keywords
        
        # Calculate keyword match ratio
        match_ratio = self._calculate_keyword_match_ratio(
            query_keywords, response_keywords
        )
        
        # Base score on match ratio
        # 0% match: 0.2, 50% match: 0.6, 100% match: 1.0
        score = 0.2 + (match_ratio * 0.8)
        
        return min(score, 1.0)
    
    def _calculate_completeness_score(
        self,
        response: str,
        query: str,
        query_options: Optional[Dict[str, Any]] = None
    ) -> float:
        """
        Calculate completeness score based on response detail.
        
        Factors:
        - Response length
        - Multiple sentences/paragraphs
        - Addresses query complexity
        """
        if not response:
            return 0.0
        
        score = 0.0
        
        # Length-based scoring
        length = len(response)
        if length < 50:
            score += 0.2
        elif length < 200:
            score += 0.5
        elif length < 500:
            score += 0.7
        elif length < 1000:
            score += 0.85
        else:
            score += 1.0
        
        # Sentence count
        sentences = response.count('.') + response.count('。') + response.count('!')
        if sentences >= 3:
            score += 0.15
        elif sentences >= 1:
            score += 0.05
        
        # Paragraph structure
        paragraphs = response.count('\n\n') + 1
        if paragraphs >= 2:
            score += 0.1
        
        return min(score / 1.25, 1.0)  # Normalize to 0-1
    
    def _has_structured_content(self, text: str) -> bool:
        """Check if text has structured content (lists, sections, etc.)."""
        # Check for bullet points, numbered lists, or multiple paragraphs
        has_bullets = bool(re.search(r'[•\-\*]\s', text))
        has_numbers = bool(re.search(r'\d+[\.\)]\s', text))
        has_paragraphs = text.count('\n\n') >= 1
        
        return has_bullets or has_numbers or has_paragraphs
    
    def _has_proper_punctuation(self, text: str) -> bool:
        """Check if text has proper punctuation."""
        # Check for sentence-ending punctuation
        has_periods = '.' in text or '。' in text
        has_commas = ',' in text or '，' in text
        
        return has_periods and has_commas
    
    def _is_error_message(self, text: str) -> bool:
        """Check if text appears to be an error message."""
        error_keywords = [
            'error', 'exception', 'failed', 'cannot', 'unable',
            '错误', '失败', '无法', 'sorry', '抱歉'
        ]
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in error_keywords)
    
    def _extract_keywords(self, text: str) -> set:
        """
        Extract keywords from text (simplified).
        
        In production, consider using:
        - NLTK or spaCy for better keyword extraction
        - TF-IDF for importance weighting
        - Language-specific tokenizers
        """
        # Simple word extraction (remove common stop words)
        stop_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'from', 'is', 'are', 'was', 'were', 'be', 'been',
            '的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一',
            '一个', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有'
        }
        
        # Extract words (alphanumeric sequences)
        words = re.findall(r'\w+', text.lower())
        
        # Filter out stop words and short words
        keywords = {
            word for word in words
            if len(word) > 2 and word not in stop_words
        }
        
        return keywords
    
    def _calculate_keyword_match_ratio(
        self,
        query_keywords: set,
        response_keywords: set
    ) -> float:
        """Calculate ratio of query keywords found in response."""
        if not query_keywords:
            return 0.0
        
        matches = query_keywords.intersection(response_keywords)
        return len(matches) / len(query_keywords)
    
    def _determine_confidence_level(self, overall_score: float) -> str:
        """Determine confidence level from overall score."""
        if overall_score >= 0.85:
            return "very_high"
        elif overall_score >= 0.7:
            return "high"
        elif overall_score >= 0.5:
            return "medium"
        elif overall_score >= 0.3:
            return "low"
        else:
            return "very_low"
    
    def _generate_explanation(
        self,
        overall: float,
        ref_score: float,
        quality_score: float,
        relevance_score: float,
        completeness_score: float,
        ref_count: int,
        response_length: int
    ) -> str:
        """Generate human-readable explanation of the score."""
        level = self._determine_confidence_level(overall)
        
        explanations = []
        
        # Overall assessment
        if level == "very_high":
            explanations.append("This response has very high confidence.")
        elif level == "high":
            explanations.append("This response has high confidence.")
        elif level == "medium":
            explanations.append("This response has medium confidence.")
        elif level == "low":
            explanations.append("This response has low confidence.")
        else:
            explanations.append("This response has very low confidence.")
        
        # Reference assessment
        if ref_count == 0:
            explanations.append("No references provided.")
        elif ref_count == 1:
            explanations.append("Only 1 reference provided.")
        elif ref_count < 3:
            explanations.append(f"{ref_count} references provided.")
        else:
            explanations.append(f"Strong reference support with {ref_count} sources.")
        
        # Quality assessment
        if quality_score < 0.5:
            explanations.append("Content quality could be improved.")
        elif quality_score < 0.7:
            explanations.append("Content quality is acceptable.")
        else:
            explanations.append("Content quality is good.")
        
        # Relevance assessment
        if relevance_score < 0.5:
            explanations.append("Relevance to query is limited.")
        elif relevance_score < 0.7:
            explanations.append("Moderately relevant to query.")
        else:
            explanations.append("Highly relevant to query.")
        
        # Completeness assessment
        if completeness_score < 0.5:
            explanations.append("Response may lack detail.")
        elif completeness_score < 0.7:
            explanations.append("Response provides adequate detail.")
        else:
            explanations.append("Response is comprehensive.")
        
        return " ".join(explanations)


# Convenience function for quick scoring
def score_lightrag_response(
    query: str,
    response_data: Dict[str, Any],
    query_options: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Quick function to score a LightRAG response.
    
    Args:
        query: Original query text
        response_data: LightRAG response data
        query_options: Optional query parameters
    
    Returns:
        Dictionary with confidence score details
    
    Example:
        >>> result = lightrag_client.query("What is AI?", {"include_references": True})
        >>> score = score_lightrag_response("What is AI?", result["data"])
        >>> print(f"Confidence: {score['overall_score']:.2f} ({score['confidence_level']})")
    """
    scorer = LightRAGConfidenceScorer()
    confidence = scorer.score(query, response_data, query_options)
    return confidence.to_dict()
