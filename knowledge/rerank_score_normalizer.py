"""
Rerank Score Normalizer - Shared normalization logic for all rerank operations

This module provides a unified score normalization function that can be used by:
1. LightRAG Rerank Proxy (for LightRAG queries)
2. Agent Memory Manager (for direct reranker access)
3. Any other component that needs rerank score normalization

Key features:
- Auto-selects normalization algorithm based on model name
- BGE models: Sigmoid normalization (preserves absolute relevance)
- Jina/Cohere models: Min-Max normalization (preserves relative ranking)
- Handles single document edge cases
- Detailed logging for debugging

Supported models:
- BGE (BAAI General Embedding): bge-reranker-* → Sigmoid
- Jina: jina-reranker-* → Min-Max
- Cohere: rerank-* → Min-Max
- Others: Auto-detect based on score distribution
"""

from typing import List, Dict, Any, Optional
import math
from utils.logger_helper import logger_helper as logger


def _detect_model_type(model_name: str) -> str:
    """
    Detect rerank model type from model name.
    
    Args:
        model_name: Model name (e.g., "bge-reranker-v2-m3", "jina-reranker-v2")
        
    Returns:
        Model type: "bge", "jina", "cohere", or "unknown"
    """
    model_lower = model_name.lower()
    
    if "bge" in model_lower or "baai" in model_lower:
        return "bge"
    elif "jina" in model_lower:
        return "jina"
    elif "cohere" in model_lower or "rerank" in model_lower:
        return "cohere"
    else:
        return "unknown"


def _sigmoid_normalize(score: float) -> float:
    """
    Sigmoid normalization for BGE logits.
    
    Converts logits to probabilities in [0, 1] range:
    - Negative logits → close to 0 (irrelevant)
    - Positive logits → close to 1 (relevant)
    - Zero → 0.5 (neutral)
    
    Args:
        score: Raw logit score
        
    Returns:
        Normalized score in [0, 1]
    """
    try:
        return 1.0 / (1.0 + math.exp(-score))
    except OverflowError:
        # Handle extreme values
        return 0.0 if score < 0 else 1.0


def normalize_rerank_scores(
    results_list: List[Dict[str, Any]],
    model_name: str = "unknown",
    log_prefix: str = "[Rerank]"
) -> List[Dict[str, Any]]:
    """
    Normalize rerank scores to [0, 1] range with model-specific algorithms.
    
    Algorithm selection:
    - BGE models: Sigmoid normalization (preserves absolute relevance)
      - sigmoid(x) = 1 / (1 + exp(-x))
      - Negative logits → ~0 (irrelevant)
      - Positive logits → ~1 (relevant)
    
    - Jina/Cohere models: Min-Max normalization (preserves relative ranking)
      - normalized = (x - min) / (max - min)
      - Maps to [0, 1] based on relative position
    
    Args:
        results_list: List of result dicts with 'relevance_score' and 'index'
        model_name: Model name (used to select normalization algorithm)
        log_prefix: Prefix for log messages (default: "[Rerank]")
        
    Returns:
        List of results with normalized scores in [0, 1] range
        
    Examples:
        >>> # BGE model (Sigmoid)
        >>> results = [{"index": 0, "relevance_score": -2.5}, {"index": 1, "relevance_score": 3.2}]
        >>> normalized = normalize_rerank_scores(results, "bge-reranker-v2-m3")
        >>> # Returns: [{"index": 0, "relevance_score": 0.076}, {"index": 1, "relevance_score": 0.961}]
        
        >>> # Jina model (Min-Max)
        >>> results = [{"index": 0, "relevance_score": 0.2}, {"index": 1, "relevance_score": 0.8}]
        >>> normalized = normalize_rerank_scores(results, "jina-reranker-v2")
        >>> # Returns: [{"index": 0, "relevance_score": 0.0}, {"index": 1, "relevance_score": 1.0}]
    """
    if not results_list:
        return []
    
    # Detect model type
    model_type = _detect_model_type(model_name)
    logger.info(f"{log_prefix} Model: {model_name}, Type: {model_type}")
    
    # Extract raw scores
    raw_scores = [item.get("relevance_score", 0.0) for item in results_list]
    
    # Log raw scores for debugging
    logger.info(f"{log_prefix} Model '{model_name}' returned {len(raw_scores)} results")
    logger.info(f"{log_prefix} Raw scores: {raw_scores}")
    
    # ========== BGE Models: Use Sigmoid Normalization ==========
    if model_type == "bge":
        logger.info(f"{log_prefix} Using Sigmoid normalization for BGE model")
        logger.info(f"{log_prefix} Algorithm: sigmoid(x) = 1 / (1 + exp(-x))")
        
        for i, item in enumerate(results_list):
            original_score = raw_scores[i]
            normalized_score = _sigmoid_normalize(original_score)
            item["relevance_score"] = normalized_score
            
            # Detailed logging
            if original_score < 0:
                logger.info(f"{log_prefix} Doc {item.get('index', i)}: {original_score:.4f} → {normalized_score:.4f} (irrelevant, logit < 0)")
            elif original_score > 0:
                logger.info(f"{log_prefix} Doc {item.get('index', i)}: {original_score:.4f} → {normalized_score:.4f} (relevant, logit > 0)")
            else:
                logger.info(f"{log_prefix} Doc {item.get('index', i)}: {original_score:.4f} → {normalized_score:.4f} (neutral, logit = 0)")
        
        return results_list
    
    # ========== Jina/Cohere Models: Use Min-Max Normalization ==========
    logger.info(f"{log_prefix} Using Min-Max normalization for {model_type} model")
    
    # Auto-detect model type from score distribution (data-driven)
    has_negative = any(s < 0 for s in raw_scores)
    has_large_positive = any(s > 1 for s in raw_scores)
    all_in_unit_range = all(0 <= s <= 1 for s in raw_scores)
    
    if has_negative or has_large_positive:
        detected_type = "BGE-like (logits)"
        logger.info(f"{log_prefix} Detected model type: {detected_type} (scores outside [0,1])")
        logger.warning(f"{log_prefix} ⚠️  Model type mismatch: {model_type} model returned logits!")
        logger.warning(f"{log_prefix} ⚠️  Consider using BGE model type for better results")
    elif all_in_unit_range:
        detected_type = "Jina-like (normalized)"
        logger.info(f"{log_prefix} Detected model type: {detected_type} (scores in [0,1])")
    else:
        detected_type = "Unknown"
        logger.warning(f"{log_prefix} Could not detect model type from scores")
    
    # Check for identical scores (no ranking information) - only for multiple documents
    # Single document should keep its original score for proper filtering
    if len(results_list) > 1:
        all_same = len(set(raw_scores)) == 1
        
        if all_same:
            logger.warning(f"{log_prefix} ⚠️  All {len(results_list)} scores are identical ({raw_scores[0]:.4e}), using uniform scores")
            for i, item in enumerate(results_list):
                item["relevance_score"] = 0.5
                logger.info(f"{log_prefix} Doc {item.get('index', i)}: score=0.5000 (uniform, all same)")
            return results_list
    
    # Analyze score distribution (data-driven detection)
    min_score = min(raw_scores)
    max_score = max(raw_scores)
    score_range = max_score - min_score
    
    # Check if scores are already well-normalized in [0, 1] range
    all_in_range = all(0 <= s <= 1 for s in raw_scores)
    has_reasonable_spread = max_score >= 0.01  # At least one score is reasonably large
    
    if all_in_range and has_reasonable_spread:
        # Scores appear to be already normalized (e.g., Cohere, standard Jina)
        logger.info(f"{log_prefix} Scores already normalized in [0,1] range (max={max_score:.4f}, range={score_range:.4f}), keeping as-is")
        for i, item in enumerate(results_list):
            logger.info(f"{log_prefix} Doc {item.get('index', i)}: final_score={raw_scores[i]:.4f} (kept native)")
        return results_list
    
    # Scores need normalization
    if all_in_range and not has_reasonable_spread:
        logger.warning(f"{log_prefix} ⚠️  Scores in [0,1] but all very small (max={max_score:.4e}), likely raw probabilities")
    elif min_score < 0 or max_score > 1:
        logger.info(f"{log_prefix} Scores outside [0,1] range (min={min_score:.4f}, max={max_score:.4f}), likely logits")
    
    # Apply min-max normalization
    if score_range == 0:
        # Single document or all scores identical
        if min_score >= 0 and min_score <= 1:
            # Already normalized, keep as-is
            logger.info(f"{log_prefix} Single doc with score={min_score:.4f}, keeping as-is")
        else:
            # Use sigmoid for single document with logits
            logger.info(f"{log_prefix} Single doc with logit ({min_score:.4f}), using sigmoid")
            normalized_score = _sigmoid_normalize(min_score)
            for item in results_list:
                item["relevance_score"] = normalized_score
            logger.info(f"{log_prefix} Doc 0: {min_score:.4f} → {normalized_score:.4f}")
        return results_list
    
    # Min-max normalization: (score - min) / (max - min)
    logger.info(f"{log_prefix} Applying min-max normalization (range: [{min_score:.4f}, {max_score:.4f}])")
    
    for i, item in enumerate(results_list):
        original_score = raw_scores[i]
        normalized_score = (original_score - min_score) / score_range
        item["relevance_score"] = normalized_score
        logger.info(f"{log_prefix} Doc {item.get('index', i)}: {original_score:.4f} → {normalized_score:.4f}")
    
    return results_list


def filter_by_rerank_score(
    results_list: List[Dict[str, Any]],
    min_score: float = 0.3,
    log_prefix: str = "[Rerank]"
) -> List[Dict[str, Any]]:
    """
    Filter rerank results by minimum score threshold.
    
    Args:
        results_list: List of result dicts with 'relevance_score'
        min_score: Minimum score threshold (default: 0.3)
        log_prefix: Prefix for log messages
        
    Returns:
        Filtered list of results
    """
    if not results_list:
        return []
    
    original_count = len(results_list)
    filtered_results = [
        item for item in results_list 
        if item.get("relevance_score", 0.0) >= min_score
    ]
    filtered_count = len(filtered_results)
    
    if filtered_count < original_count:
        logger.info(f"{log_prefix} Filtered {original_count - filtered_count} results below threshold {min_score}")
        logger.info(f"{log_prefix} {filtered_count} results remained after filtering")
    
    return filtered_results


def normalize_and_filter_rerank_results(
    results_list: List[Dict[str, Any]],
    model_name: str = "unknown",
    min_score: float = 0.3,
    log_prefix: str = "[Rerank]"
) -> List[Dict[str, Any]]:
    """
    Convenience function: Normalize scores and filter by threshold in one call.
    
    Args:
        results_list: List of result dicts with 'relevance_score' and 'index'
        model_name: Model name (for logging)
        min_score: Minimum score threshold
        log_prefix: Prefix for log messages
        
    Returns:
        Normalized and filtered list of results
    """
    # Step 1: Normalize scores
    normalized_results = normalize_rerank_scores(results_list, model_name, log_prefix)
    
    # Step 2: Filter by threshold
    filtered_results = filter_by_rerank_score(normalized_results, min_score, log_prefix)
    
    return filtered_results
