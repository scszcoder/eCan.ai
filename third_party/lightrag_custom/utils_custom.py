"""
Custom utils patches for LightRAG

This module provides patched versions of LightRAG utils functions
to add score fields to references for confidence scoring.

Author: eCan.ai Team
Date: 2025-12-20
"""

from lightrag.utils import logger


def generate_reference_list_from_chunks_with_scores(chunks: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Generate reference list from chunks, prioritizing by occurrence frequency.
    
    This is a patched version that includes score fields in references
    for confidence scoring.

    Args:
        chunks: List of chunk dictionaries with file_path information

    Returns:
        tuple: (reference_list, updated_chunks_with_reference_ids)
            - reference_list: List of dicts with reference_id, file_path, and score
            - updated_chunks_with_reference_ids: Original chunks with reference_id field added
    """
    if not chunks:
        return [], []

    # 1. Extract all valid file_paths, count their occurrences, and collect scores
    file_path_counts = {}
    file_path_scores = {}  # Collect scores for each file_path
    for chunk in chunks:
        file_path = chunk.get("file_path", "")
        if file_path and file_path != "unknown_source":
            file_path_counts[file_path] = file_path_counts.get(file_path, 0) + 1
            # Collect rerank_score or other score fields
            score = chunk.get("rerank_score") or chunk.get("score") or chunk.get("similarity")
            if score is not None:
                if file_path not in file_path_scores:
                    file_path_scores[file_path] = []
                try:
                    file_path_scores[file_path].append(float(score))
                except (ValueError, TypeError):
                    pass

    # 2. Sort file paths by frequency (descending), then by first appearance order
    file_path_with_indices = []
    seen_paths = set()
    for i, chunk in enumerate(chunks):
        file_path = chunk.get("file_path", "")
        if file_path and file_path != "unknown_source" and file_path not in seen_paths:
            file_path_with_indices.append((file_path, file_path_counts[file_path], i))
            seen_paths.add(file_path)

    # Sort by count (descending), then by first appearance index (ascending)
    sorted_file_paths = sorted(file_path_with_indices, key=lambda x: (-x[1], x[2]))
    unique_file_paths = [item[0] for item in sorted_file_paths]

    # 3. Create mapping from file_path to reference_id (prioritized by frequency)
    file_path_to_ref_id = {}
    for i, file_path in enumerate(unique_file_paths):
        file_path_to_ref_id[file_path] = str(i + 1)

    # 4. Add reference_id field to each chunk
    updated_chunks = []
    for chunk in chunks:
        chunk_copy = chunk.copy()
        file_path = chunk_copy.get("file_path", "")
        if file_path and file_path != "unknown_source":
            chunk_copy["reference_id"] = file_path_to_ref_id[file_path]
        else:
            chunk_copy["reference_id"] = ""
        updated_chunks.append(chunk_copy)

    # 5. Build reference_list with scores (for confidence scoring)
    reference_list = []
    for i, file_path in enumerate(unique_file_paths):
        ref_item = {"reference_id": str(i + 1), "file_path": file_path}
        # Add average score if available (for confidence scoring)
        if file_path in file_path_scores and file_path_scores[file_path]:
            scores = file_path_scores[file_path]
            ref_item["score"] = sum(scores) / len(scores)  # Average score
        reference_list.append(ref_item)

    logger.debug(f"[utils_custom] Generated {len(reference_list)} references with scores from {len(chunks)} chunks")
    
    return reference_list, updated_chunks


def patch_generate_reference_list_from_chunks():
    """
    Patch lightrag.utils.generate_reference_list_from_chunks to include scores.
    
    This enables confidence scoring to work correctly by providing
    rerank_score in the references.
    """
    try:
        from lightrag import utils
        from lightrag import operate
        
        # Replace the function in utils module
        original_func = utils.generate_reference_list_from_chunks
        utils.generate_reference_list_from_chunks = generate_reference_list_from_chunks_with_scores
        
        # Also replace in operate module where it's imported
        operate.generate_reference_list_from_chunks = generate_reference_list_from_chunks_with_scores
        
        logger.info("[utils_custom] ✅ generate_reference_list_from_chunks patched with score support")
        return True
        
    except Exception as e:
        logger.error(f"[utils_custom] ❌ Failed to patch generate_reference_list_from_chunks: {e}")
        return False
