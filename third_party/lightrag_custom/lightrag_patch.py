"""
Patch for LightRAG to prevent auto-retry of user-cancelled documents.

This patch modifies the document validation logic in LightRAG to skip documents
that were manually cancelled by the user.
"""

import asyncio
import logging
from datetime import datetime, timezone
from lightrag.base import DocStatus

from lightrag.utils import logger

async def patched_validate_and_fix_document_consistency(
    self,
    to_process_docs,
    pipeline_status,
    pipeline_status_lock,
):
    """
    Patched version of _validate_and_fix_document_consistency that respects user cancellation.
    
    This method prevents auto-retry of documents that were cancelled by the user.
    """
    inconsistent_docs = []
    failed_docs_to_preserve = []
    successful_deletions = 0

    # Check each document's data consistency
    for doc_id, status_doc in to_process_docs.items():
        # Check if corresponding content exists in full_docs
        content_data = await self.full_docs.get_by_id(doc_id)
        if not content_data:
            # Check if this is a failed document that should be preserved
            if (
                hasattr(status_doc, "status")
                and status_doc.status == DocStatus.FAILED
            ):
                failed_docs_to_preserve.append(doc_id)
            else:
                inconsistent_docs.append(doc_id)

    # Log information about failed documents that will be preserved
    if failed_docs_to_preserve:
        async with pipeline_status_lock:
            preserve_message = f"Preserving {len(failed_docs_to_preserve)} failed document entries for manual review"
            logger.info(preserve_message)
            pipeline_status["latest_message"] = preserve_message
            pipeline_status["history_messages"].append(preserve_message)

        # Remove failed documents from processing list but keep them in doc_status
        for doc_id in failed_docs_to_preserve:
            to_process_docs.pop(doc_id, None)

    # Delete inconsistent document entries(excluding failed documents)
    if inconsistent_docs:
        async with pipeline_status_lock:
            summary_message = (
                f"Inconsistent document entries found: {len(inconsistent_docs)}"
            )
            logger.info(summary_message)
            pipeline_status["latest_message"] = summary_message
            pipeline_status["history_messages"].append(summary_message)

        successful_deletions = 0
        for doc_id in inconsistent_docs:
            try:
                status_doc = to_process_docs[doc_id]
                file_path = getattr(status_doc, "file_path", "unknown_source")

                # Delete doc_status entry
                await self.doc_status.delete([doc_id])
                successful_deletions += 1

                # Log successful deletion
                async with pipeline_status_lock:
                    log_message = (
                        f"Deleted inconsistent entry: {doc_id} ({file_path})"
                    )
                    logger.info(log_message)
                    pipeline_status["latest_message"] = log_message
                    pipeline_status["history_messages"].append(log_message)

                # Remove from processing list
                to_process_docs.pop(doc_id, None)

            except Exception as e:
                # Log deletion failure
                async with pipeline_status_lock:
                    error_message = f"Failed to delete entry: {doc_id} - {str(e)}"
                    logger.error(error_message)
                    pipeline_status["latest_message"] = error_message
                    pipeline_status["history_messages"].append(error_message)

    # ========== PATCH: Remove user-cancelled documents from processing queue ==========
    # IMPORTANT: Remove these documents BEFORE any reset logic
    docs_to_remove = []
    for doc_id, status_doc in to_process_docs.items():
        metadata = getattr(status_doc, "metadata", {})
        if isinstance(metadata, dict) and metadata.get("user_cancelled"):
            docs_to_remove.append(doc_id)
            logger.info(
                f"[Patch] ✅ Removing user-cancelled document from queue: {doc_id} "
                f"({getattr(status_doc, 'file_path', 'unknown')}, status={getattr(status_doc, 'status', 'unknown')})"
            )
    
    # Remove user-cancelled documents from processing queue
    for doc_id in docs_to_remove:
        to_process_docs.pop(doc_id, None)
    
    if docs_to_remove:
        async with pipeline_status_lock:
            skip_message = f"Removed {len(docs_to_remove)} user-cancelled documents from processing queue"
            logger.info(f"[Patch] {skip_message}")
            pipeline_status["latest_message"] = skip_message
            pipeline_status["history_messages"].append(skip_message)
    # ========== End Patch ==========
    
    # Reset PROCESSING and FAILED documents that pass consistency checks to PENDING status
    docs_to_reset = {}
    reset_count = 0
    skipped_count = len(docs_to_remove)

    for doc_id, status_doc in to_process_docs.items():
        # Check if document has corresponding content in full_docs (consistency check)
        content_data = await self.full_docs.get_by_id(doc_id)
        if content_data:  # Document passes consistency check
            # Check if document is in PROCESSING or FAILED status
            if hasattr(status_doc, "status") and status_doc.status in [
                DocStatus.PROCESSING,
                DocStatus.FAILED,
            ]:

                # Prepare document for status reset to PENDING
                docs_to_reset[doc_id] = {
                    "status": DocStatus.PENDING,
                    "content_summary": status_doc.content_summary,
                    "content_length": status_doc.content_length,
                    "created_at": status_doc.created_at,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "file_path": getattr(status_doc, "file_path", "unknown_source"),
                    "track_id": getattr(status_doc, "track_id", ""),
                    # Clear any error messages and processing metadata
                    "error_msg": "",
                    "metadata": {},
                }

                # Update the status in to_process_docs as well
                status_doc.status = DocStatus.PENDING
                reset_count += 1

    # Update doc_status storage if there are documents to reset
    if docs_to_reset:
        await self.doc_status.upsert(docs_to_reset)

        async with pipeline_status_lock:
            reset_message = f"Reset {reset_count} documents from PROCESSING/FAILED to PENDING status"
            if skipped_count > 0:
                reset_message += f" (skipped {skipped_count} user-cancelled documents)"
            logger.info(reset_message)
            pipeline_status["latest_message"] = reset_message
            pipeline_status["history_messages"].append(reset_message)
    elif skipped_count > 0:
        async with pipeline_status_lock:
            skip_message = f"Skipped {skipped_count} user-cancelled documents from auto-retry"
            logger.info(f"[Patch] {skip_message}")
            pipeline_status["latest_message"] = skip_message
            pipeline_status["history_messages"].append(skip_message)

    return to_process_docs


def apply_lightrag_patch():
    """
    Apply the patch to LightRAG to prevent auto-retry of user-cancelled documents.
    
    This should be called during LightRAG initialization.
    """
    try:
        from lightrag import LightRAG
        
        # Replace the _validate_and_fix_document_consistency method
        LightRAG._validate_and_fix_document_consistency = patched_validate_and_fix_document_consistency
        
        logger.info("[Patch] Successfully applied LightRAG auto-retry prevention patch")
        return True
    except Exception as e:
        logger.error(f"[Patch] Failed to apply LightRAG patch: {e}")
        return False
