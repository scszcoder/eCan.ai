"""
Custom operate module with immediate task cancellation support.

This module provides a patched version of extract_entities that registers
all chunk processing tasks for immediate cancellation.
"""

import asyncio
from lightrag.utils import logger

# Import original functions and dependencies from lightrag.operate
from lightrag.operate import (
    _process_extraction_result,
    use_llm_func_with_cache,
    pack_user_ass_to_openai_messages,
    update_chunk_cache_list,
    create_prefixed_exception,
    PROMPTS,
    DEFAULT_ENTITY_TYPES,
    DEFAULT_SUMMARY_LANGUAGE,
)
from lightrag.exceptions import PipelineCancelledException
from lightrag.base import TextChunkSchema, BaseKVStorage

# Global registry for running extraction tasks
_running_extraction_tasks: set = set()
_extraction_tasks_lock = asyncio.Lock()


async def register_extraction_task(task: asyncio.Task):
    """Register a running extraction task for potential cancellation"""
    async with _extraction_tasks_lock:
        _running_extraction_tasks.add(task)


async def unregister_extraction_task(task: asyncio.Task):
    """Unregister a completed extraction task"""
    async with _extraction_tasks_lock:
        _running_extraction_tasks.discard(task)


async def cancel_all_extraction_tasks() -> int:
    """Cancel all running extraction tasks immediately. Returns count of cancelled tasks."""
    async with _extraction_tasks_lock:
        cancelled_count = 0
        tasks_to_cancel = list(_running_extraction_tasks)
        for task in tasks_to_cancel:
            if not task.done():
                task.cancel()
                cancelled_count += 1
                logger.info(f"[operate_custom] Cancelled task: {task.get_name()}")
        _running_extraction_tasks.clear()
        logger.info(f"[operate_custom] Total cancelled: {cancelled_count} tasks")
        return cancelled_count


async def extract_entities_with_cancellation(
    chunks: dict[str, TextChunkSchema],
    global_config: dict[str, str],
    pipeline_status: dict = None,
    pipeline_status_lock=None,
    llm_response_cache: BaseKVStorage | None = None,
    text_chunks_storage: BaseKVStorage | None = None,
) -> list:
    """
    Extract entities from chunks with immediate cancellation support.
    
    This is a patched version of lightrag.operate.extract_entities that
    registers all chunk processing tasks for immediate cancellation.
    """
    # Check for cancellation at the start of entity extraction
    if pipeline_status is not None and pipeline_status_lock is not None:
        async with pipeline_status_lock:
            if pipeline_status.get("cancellation_requested", False):
                raise PipelineCancelledException(
                    "User cancelled during entity extraction"
                )

    use_llm_func: callable = global_config["llm_model_func"]
    entity_extract_max_gleaning = global_config["entity_extract_max_gleaning"]

    ordered_chunks = list(chunks.items())
    language = global_config["addon_params"].get("language", DEFAULT_SUMMARY_LANGUAGE)
    entity_types = global_config["addon_params"].get(
        "entity_types", DEFAULT_ENTITY_TYPES
    )

    examples = "\n".join(PROMPTS["entity_extraction_examples"])

    example_context_base = dict(
        tuple_delimiter=PROMPTS["DEFAULT_TUPLE_DELIMITER"],
        completion_delimiter=PROMPTS["DEFAULT_COMPLETION_DELIMITER"],
        entity_types=", ".join(entity_types),
        language=language,
    )
    examples = examples.format(**example_context_base)

    context_base = dict(
        tuple_delimiter=PROMPTS["DEFAULT_TUPLE_DELIMITER"],
        completion_delimiter=PROMPTS["DEFAULT_COMPLETION_DELIMITER"],
        entity_types=",".join(entity_types),
        examples=examples,
        language=language,
    )

    processed_chunks = 0
    total_chunks = len(ordered_chunks)

    # Initialize chunk progress in pipeline_status
    if pipeline_status is not None and pipeline_status_lock is not None:
        async with pipeline_status_lock:
            pipeline_status["total_chunks"] = total_chunks
            pipeline_status["processed_chunks"] = 0

    async def _process_single_content(chunk_key_dp: tuple[str, TextChunkSchema]):
        """Process a single chunk with cancellation checks before each LLM call"""
        nonlocal processed_chunks
        chunk_key = chunk_key_dp[0]
        chunk_dp = chunk_key_dp[1]
        content = chunk_dp["content"]
        file_path = chunk_dp.get("file_path", "unknown_source")

        # Check for cancellation before starting
        if pipeline_status is not None and pipeline_status_lock is not None:
            async with pipeline_status_lock:
                if pipeline_status.get("cancellation_requested", False):
                    raise PipelineCancelledException(
                        f"User cancelled before processing chunk {chunk_key[:16]}"
                    )

        cache_keys_collector = []

        entity_extraction_system_prompt = PROMPTS[
            "entity_extraction_system_prompt"
        ].format(**{**context_base, "input_text": content})
        entity_extraction_user_prompt = PROMPTS["entity_extraction_user_prompt"].format(
            **{**context_base, "input_text": content}
        )
        entity_continue_extraction_user_prompt = PROMPTS[
            "entity_continue_extraction_user_prompt"
        ].format(**{**context_base, "input_text": content})

        # Check for cancellation before first LLM call
        if pipeline_status is not None and pipeline_status_lock is not None:
            async with pipeline_status_lock:
                if pipeline_status.get("cancellation_requested", False):
                    raise PipelineCancelledException(
                        f"User cancelled before LLM call for chunk {chunk_key[:16]}"
                    )

        final_result, timestamp = await use_llm_func_with_cache(
            entity_extraction_user_prompt,
            use_llm_func,
            system_prompt=entity_extraction_system_prompt,
            llm_response_cache=llm_response_cache,
            cache_type="extract",
            chunk_id=chunk_key,
            cache_keys_collector=cache_keys_collector,
        )

        # Check for cancellation after first LLM call
        if pipeline_status is not None and pipeline_status_lock is not None:
            async with pipeline_status_lock:
                if pipeline_status.get("cancellation_requested", False):
                    raise PipelineCancelledException(
                        f"User cancelled after first LLM call for chunk {chunk_key[:16]}"
                    )

        history = pack_user_ass_to_openai_messages(
            entity_extraction_user_prompt, final_result
        )

        maybe_nodes, maybe_edges = await _process_extraction_result(
            final_result,
            chunk_key,
            timestamp,
            file_path,
            tuple_delimiter=context_base["tuple_delimiter"],
            completion_delimiter=context_base["completion_delimiter"],
        )

        if entity_extract_max_gleaning > 0:
            # Check for cancellation before gleaning LLM call
            if pipeline_status is not None and pipeline_status_lock is not None:
                async with pipeline_status_lock:
                    if pipeline_status.get("cancellation_requested", False):
                        raise PipelineCancelledException(
                            f"User cancelled before gleaning for chunk {chunk_key[:16]}"
                        )

            glean_result, timestamp = await use_llm_func_with_cache(
                entity_continue_extraction_user_prompt,
                use_llm_func,
                system_prompt=entity_extraction_system_prompt,
                llm_response_cache=llm_response_cache,
                history_messages=history,
                cache_type="extract",
                chunk_id=chunk_key,
                cache_keys_collector=cache_keys_collector,
            )

            glean_nodes, glean_edges = await _process_extraction_result(
                glean_result,
                chunk_key,
                timestamp,
                file_path,
                tuple_delimiter=context_base["tuple_delimiter"],
                completion_delimiter=context_base["completion_delimiter"],
            )

            for entity_name, glean_entities in glean_nodes.items():
                if entity_name in maybe_nodes:
                    original_desc_len = len(
                        maybe_nodes[entity_name][0].get("description", "") or ""
                    )
                    glean_desc_len = len(glean_entities[0].get("description", "") or "")
                    if glean_desc_len > original_desc_len:
                        maybe_nodes[entity_name] = list(glean_entities)
                else:
                    maybe_nodes[entity_name] = list(glean_entities)

            for edge_key, glean_edge_list in glean_edges.items():
                if edge_key in maybe_edges:
                    original_desc_len = len(
                        maybe_edges[edge_key][0].get("description", "") or ""
                    )
                    glean_desc_len = len(glean_edge_list[0].get("description", "") or "")
                    if glean_desc_len > original_desc_len:
                        maybe_edges[edge_key] = list(glean_edge_list)
                else:
                    maybe_edges[edge_key] = list(glean_edge_list)

        if cache_keys_collector and text_chunks_storage:
            await update_chunk_cache_list(
                chunk_key,
                text_chunks_storage,
                cache_keys_collector,
                "entity_extraction",
            )

        processed_chunks += 1
        entities_count = len(maybe_nodes)
        relations_count = len(maybe_edges)
        log_message = f"Chunk {processed_chunks} of {total_chunks} extracted {entities_count} Ent + {relations_count} Rel {chunk_key}"
        logger.info(log_message)
        if pipeline_status is not None:
            async with pipeline_status_lock:
                pipeline_status["latest_message"] = log_message
                pipeline_status["history_messages"].append(log_message)
                pipeline_status["processed_chunks"] = processed_chunks
                pipeline_status["total_chunks"] = total_chunks

        return maybe_nodes, maybe_edges

    chunk_max_async = global_config.get("llm_model_max_async", 4)
    semaphore = asyncio.Semaphore(chunk_max_async)

    async def _process_with_semaphore(chunk):
        async with semaphore:
            # Check for cancellation before processing chunk
            if pipeline_status is not None and pipeline_status_lock is not None:
                async with pipeline_status_lock:
                    if pipeline_status.get("cancellation_requested", False):
                        raise PipelineCancelledException(
                            "User cancelled during chunk processing"
                        )

            try:
                return await _process_single_content(chunk)
            except Exception as e:
                chunk_id = chunk[0]
                prefixed_exception = create_prefixed_exception(e, chunk_id)
                raise prefixed_exception from e

    # Create tasks and REGISTER them for cancellation
    tasks = []
    for c in ordered_chunks:
        task = asyncio.create_task(_process_with_semaphore(c))
        task.set_name(f"extract_chunk_{c[0][:16]}")
        tasks.append(task)
        # Register task for immediate cancellation
        await register_extraction_task(task)

    logger.info(f"[operate_custom] Registered {len(tasks)} extraction tasks for cancellation")

    try:
        # Wait for tasks to complete or for the first exception to occur
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)

        first_exception = None
        chunk_results = []

        for task in done:
            try:
                exception = task.exception()
                if exception is not None:
                    if first_exception is None:
                        first_exception = exception
                else:
                    chunk_results.append(task.result())
            except Exception as e:
                if first_exception is None:
                    first_exception = e

        if first_exception is not None:
            for pending_task in pending:
                pending_task.cancel()

            if pending:
                await asyncio.wait(pending)

            progress_prefix = f"C[{processed_chunks + 1}/{total_chunks}]"
            prefixed_exception = create_prefixed_exception(first_exception, progress_prefix)
            raise prefixed_exception from first_exception

        return chunk_results

    except asyncio.CancelledError:
        logger.info("[operate_custom] extract_entities was cancelled by user")
        # Cancel any remaining tasks
        for task in tasks:
            if not task.done():
                task.cancel()
        raise PipelineCancelledException("User cancelled extraction")

    finally:
        # Unregister all tasks
        for task in tasks:
            await unregister_extraction_task(task)
        logger.info(f"[operate_custom] Unregistered {len(tasks)} extraction tasks")
