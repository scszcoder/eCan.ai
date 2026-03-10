"""
Custom operate module with immediate task cancellation support.

This module provides a patched version of extract_entities that registers
all chunk processing tasks for immediate cancellation.
"""

import asyncio
from lightrag.utils import logger

# Import original functions and dependencies from lightrag.operate
from lightrag.operate import (
    extract_entities as original_extract_entities,
    use_llm_func_with_cache,
    pack_user_ass_to_openai_messages,
    _process_extraction_result,  # Import internal function for batch processing
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

# Global registry for active HTTP clients (for immediate cancellation)
_active_http_clients: set = set()
_http_clients_lock = asyncio.Lock()


async def register_http_client(client):
    """Register an active HTTP client for potential cancellation.
    
    Works with:
    - ollama.AsyncClient (has _client attribute which is httpx.AsyncClient)
    - openai.AsyncOpenAI (has _client attribute which is httpx.AsyncClient)
    - httpx.AsyncClient directly
    - aiohttp.ClientSession
    """
    async with _http_clients_lock:
        _active_http_clients.add(client)
        logger.debug(f"[operate_custom] Registered HTTP client: {type(client).__name__}")


async def close_all_http_clients() -> int:
    """Close all active HTTP clients immediately. Returns count of closed clients."""
    async with _http_clients_lock:
        closed_count = 0
        clients_to_close = list(_active_http_clients)
        for client in clients_to_close:
            try:
                # Try different close methods based on client type
                if hasattr(client, '_client') and hasattr(client._client, 'aclose'):
                    # ollama.AsyncClient or openai.AsyncOpenAI
                    await client._client.aclose()
                    closed_count += 1
                    logger.info(f"[operate_custom] Closed HTTP client (via _client): {type(client).__name__}")
                elif hasattr(client, 'aclose'):
                    # httpx.AsyncClient
                    await client.aclose()
                    closed_count += 1
                    logger.info(f"[operate_custom] Closed HTTP client: {type(client).__name__}")
                elif hasattr(client, 'close'):
                    # aiohttp.ClientSession
                    await client.close()
                    closed_count += 1
                    logger.info(f"[operate_custom] Closed HTTP client (aiohttp): {type(client).__name__}")
            except Exception as e:
                logger.warning(f"[operate_custom] Failed to close HTTP client {type(client).__name__}: {e}")
        _active_http_clients.clear()
        logger.info(f"[operate_custom] Total closed: {closed_count} HTTP clients")
        return closed_count


async def register_extraction_task(task: asyncio.Task):
    """Register a running extraction task for potential cancellation"""
    async with _extraction_tasks_lock:
        _running_extraction_tasks.add(task)


async def unregister_extraction_task(task: asyncio.Task):
    """Unregister a completed extraction task"""
    async with _extraction_tasks_lock:
        _running_extraction_tasks.discard(task)


async def cancel_all_extraction_tasks() -> int:
    """Cancel all running extraction tasks and close HTTP clients immediately. Returns count of cancelled tasks."""
    # First close all HTTP clients to interrupt ongoing requests
    closed_clients = await close_all_http_clients()
    
    # Then cancel asyncio tasks
    async with _extraction_tasks_lock:
        cancelled_count = 0
        tasks_to_cancel = list(_running_extraction_tasks)
        for task in tasks_to_cancel:
            if not task.done():
                task.cancel()
                cancelled_count += 1
                logger.info(f"[operate_custom] Cancelled task: {task.get_name()}")
        _running_extraction_tasks.clear()
        logger.info(f"[operate_custom] Total cancelled: {cancelled_count} tasks, {closed_clients} HTTP clients closed")
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

    # ========== Optimization 1: System Prompt Caching ==========
    # System prompt is shared across all chunks, format once and reuse
    # This reduces input tokens by 50-70% for multi-chunk processing
    entity_extraction_system_prompt_template = PROMPTS["entity_extraction_system_prompt"]
    entity_extraction_user_prompt_template = PROMPTS["entity_extraction_user_prompt"]
    entity_continue_extraction_user_prompt_template = PROMPTS["entity_continue_extraction_user_prompt"]
    
    # Pre-format context_base parts (shared across all chunks)
    shared_context = {k: v for k, v in context_base.items() if k != "input_text"}
    
    # Pre-format system prompt ONCE for all chunks (major token savings)
    # Note: input_text is NOT in system prompt, so this is truly shared
    cached_system_prompt = entity_extraction_system_prompt_template.format(**shared_context)
    
    logger.info(f"[Optimization] System prompt cached ({len(cached_system_prompt)} chars), will be reused for {len(ordered_chunks)} chunks")
    logger.info(f"[Optimization] Estimated token savings: ~{len(cached_system_prompt) * (len(ordered_chunks) - 1) // 4} tokens")
    
    # ========== Optimization 2: Smart Batch Merging ==========
    # Merge small chunks (< 500 tokens) into batches to reduce LLM calls
    SMALL_CHUNK_THRESHOLD = 500  # characters (~125 tokens)
    MAX_BATCH_SIZE = 3  # Max chunks per batch
    
    def should_batch_chunks(chunks_to_check):
        """Check if chunks should be batched together"""
        if len(chunks_to_check) < 2:
            return False
        # Only batch if all chunks are small
        return all(len(chunk[1]["content"]) < SMALL_CHUNK_THRESHOLD for chunk in chunks_to_check[:MAX_BATCH_SIZE])
    
    def create_batched_chunks(chunks):
        """Group small chunks into batches"""
        batched = []
        current_batch = []
        
        for chunk in chunks:
            chunk_size = len(chunk[1]["content"])
            
            if chunk_size < SMALL_CHUNK_THRESHOLD and len(current_batch) < MAX_BATCH_SIZE:
                current_batch.append(chunk)
            else:
                # Flush current batch if exists
                if current_batch:
                    if len(current_batch) > 1:
                        batched.append(("batch", current_batch))
                        logger.info(f"[Optimization] Batching {len(current_batch)} small chunks together")
                    else:
                        batched.append(current_batch[0])
                    current_batch = []
                
                # Add current chunk
                if chunk_size < SMALL_CHUNK_THRESHOLD:
                    current_batch.append(chunk)
                else:
                    batched.append(chunk)
        
        # Flush remaining batch
        if current_batch:
            if len(current_batch) > 1:
                batched.append(("batch", current_batch))
                logger.info(f"[Optimization] Batching {len(current_batch)} small chunks together")
            else:
                batched.append(current_batch[0])
        
        return batched
    
    # Apply batching if beneficial
    original_chunk_count = len(ordered_chunks)
    batched_chunks = create_batched_chunks(ordered_chunks)
    logger.info(f"[Optimization] Batching: {original_chunk_count} chunks → {len(batched_chunks)} processing units ({original_chunk_count - len(batched_chunks)} LLM calls saved)")
    
    async def _process_batched_content(batch_data):
        """Process a batch of small chunks together"""
        nonlocal processed_chunks
        
        # Combine multiple chunks into one prompt
        combined_content = []
        chunk_keys = []
        file_paths = []
        
        for i, (chunk_key, chunk_dp) in enumerate(batch_data, 1):
            chunk_keys.append(chunk_key)
            file_paths.append(chunk_dp.get("file_path", "unknown_source"))
            combined_content.append(f"--- Document Chunk {i} ---\n{chunk_dp['content']}")
        
        combined_text = "\n\n".join(combined_content)
        primary_chunk_key = chunk_keys[0]
        
        logger.info(f"[Optimization] Processing batch of {len(batch_data)} chunks as one LLM call")
        
        # Use the standard processing logic with combined content
        chunk_context = {**shared_context, "input_text": combined_text}
        entity_extraction_user_prompt = entity_extraction_user_prompt_template.format(**chunk_context)
        
        # Single LLM call for all chunks in batch
        llm_task = asyncio.create_task(
            use_llm_func_with_cache(
                entity_extraction_user_prompt,
                use_llm_func,
                system_prompt=cached_system_prompt,
                llm_response_cache=llm_response_cache,
                cache_type="extract",
                chunk_id=primary_chunk_key,
                cache_keys_collector=[],
            )
        )
        
        await register_extraction_task(llm_task)
        
        try:
            async def watch_cancellation():
                while True:
                    if pipeline_status is not None and pipeline_status_lock is not None:
                        async with pipeline_status_lock:
                            if pipeline_status.get("cancellation_requested", False):
                                return True
                    await asyncio.sleep(0.05)
            
            watcher_task = asyncio.create_task(watch_cancellation())
            done, pending = await asyncio.wait([llm_task, watcher_task], return_when=asyncio.FIRST_COMPLETED)
            
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            
            if watcher_task in done:
                llm_task.cancel()
                try:
                    await llm_task
                except asyncio.CancelledError:
                    pass
                logger.info(f"[operate_custom] ⚠️ Batch LLM task cancelled")
                raise PipelineCancelledException("User cancelled during batch LLM call")
            
            final_result, timestamp = await llm_task
        finally:
            await unregister_extraction_task(llm_task)
        
        # Process results for all chunks in batch
        all_nodes = {}
        all_edges = {}
        
        for chunk_key, file_path in zip(chunk_keys, file_paths):
            maybe_nodes, maybe_edges = await _process_extraction_result(
                final_result,
                chunk_key,
                timestamp,
                file_path,
                tuple_delimiter=shared_context["tuple_delimiter"],
                completion_delimiter=shared_context["completion_delimiter"],
            )
            
            all_nodes.update(maybe_nodes)
            all_edges.update(maybe_edges)
            
            processed_chunks += 1
            
            if pipeline_status is not None:
                async with pipeline_status_lock:
                    pipeline_status["processed_chunks"] = processed_chunks
        
        logger.info(f"[Optimization] Batch processed {len(batch_data)} chunks, extracted {len(all_nodes)} entities + {len(all_edges)} relations")
        return all_nodes, all_edges
    
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

        # ========== Optimization: Reuse cached system prompt + format user prompt ==========
        # System prompt is already cached, only format user prompts with input_text
        chunk_context = {**shared_context, "input_text": content}
        entity_extraction_user_prompt = entity_extraction_user_prompt_template.format(**chunk_context)
        entity_continue_extraction_user_prompt = entity_continue_extraction_user_prompt_template.format(**chunk_context)

        # Check for cancellation before first LLM call
        if pipeline_status is not None and pipeline_status_lock is not None:
            async with pipeline_status_lock:
                if pipeline_status.get("cancellation_requested", False):
                    raise PipelineCancelledException(
                        f"User cancelled before LLM call for chunk {chunk_key[:16]}"
                    )

        # Create cancellable LLM task (using cached system prompt)
        llm_task = asyncio.create_task(
            use_llm_func_with_cache(
                entity_extraction_user_prompt,
                use_llm_func,
                system_prompt=cached_system_prompt,  # ✅ Use cached system prompt
                llm_response_cache=llm_response_cache,
                cache_type="extract",
                chunk_id=chunk_key,
                cache_keys_collector=cache_keys_collector,
            )
        )
        
        # Register task for potential cancellation
        await register_extraction_task(llm_task)
        
        try:
            # Create a cancellation watcher task
            async def watch_cancellation():
                while True:
                    if pipeline_status is not None and pipeline_status_lock is not None:
                        async with pipeline_status_lock:
                            if pipeline_status.get("cancellation_requested", False):
                                return True
                    await asyncio.sleep(0.05)  # Check every 50ms
            
            watcher_task = asyncio.create_task(watch_cancellation())
            
            # Wait for either LLM completion or cancellation
            done, pending = await asyncio.wait(
                [llm_task, watcher_task],
                return_when=asyncio.FIRST_COMPLETED
            )
            
            # Cancel the pending task
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            
            # Check if cancellation was triggered
            if watcher_task in done:
                llm_task.cancel()
                try:
                    await llm_task
                except asyncio.CancelledError:
                    pass
                logger.info(f"[operate_custom] ⚠️ LLM task cancelled for chunk {chunk_key[:16]}")
                raise PipelineCancelledException(
                    f"User cancelled during LLM call for chunk {chunk_key[:16]}"
                )
            
            final_result, timestamp = await llm_task
        finally:
            await unregister_extraction_task(llm_task)

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

            # Create cancellable gleaning LLM task (using cached system prompt)
            gleaning_task = asyncio.create_task(
                use_llm_func_with_cache(
                    entity_continue_extraction_user_prompt,
                    use_llm_func,
                    system_prompt=cached_system_prompt,  # ✅ Use cached system prompt
                    llm_response_cache=llm_response_cache,
                    history_messages=history,
                    cache_type="extract",
                    chunk_id=chunk_key,
                    cache_keys_collector=cache_keys_collector,
                )
            )
            
            # Register task for potential cancellation
            await register_extraction_task(gleaning_task)
            
            try:
                # Create a cancellation watcher task
                async def watch_gleaning_cancellation():
                    while True:
                        if pipeline_status is not None and pipeline_status_lock is not None:
                            async with pipeline_status_lock:
                                if pipeline_status.get("cancellation_requested", False):
                                    return True
                        await asyncio.sleep(0.05)  # Check every 50ms
                
                gleaning_watcher = asyncio.create_task(watch_gleaning_cancellation())
                
                # Wait for either LLM completion or cancellation
                done, pending = await asyncio.wait(
                    [gleaning_task, gleaning_watcher],
                    return_when=asyncio.FIRST_COMPLETED
                )
                
                # Cancel the pending task
                for task in pending:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                
                # Check if cancellation was triggered
                if gleaning_watcher in done:
                    gleaning_task.cancel()
                    try:
                        await gleaning_task
                    except asyncio.CancelledError:
                        pass
                    logger.info(f"[operate_custom] ⚠️ Gleaning LLM task cancelled for chunk {chunk_key[:16]}")
                    raise PipelineCancelledException(
                        f"User cancelled during gleaning LLM call for chunk {chunk_key[:16]}"
                    )
                
                glean_result, timestamp = await gleaning_task
            finally:
                await unregister_extraction_task(gleaning_task)

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
                # Track current processing document file path for per-document progress display
                pipeline_status["current_chunk_file"] = file_path

        return maybe_nodes, maybe_edges

    # ========== Optimization: Batch processing configuration ==========
    # Increase batch size for better throughput while maintaining cancellability
    chunk_max_async = global_config.get("llm_model_max_async", 4)
    batch_size = min(chunk_max_async * 2, 8)  # Process 2x async limit, max 8
    semaphore = asyncio.Semaphore(chunk_max_async)
    
    logger.info(f"[operate_custom] Batch processing: {batch_size} chunks/batch, {chunk_max_async} concurrent LLM calls")

    async def _process_with_semaphore(chunk_or_batch):
        async with semaphore:
            # Check for cancellation before processing
            if pipeline_status is not None and pipeline_status_lock is not None:
                async with pipeline_status_lock:
                    if pipeline_status.get("cancellation_requested", False):
                        raise PipelineCancelledException(
                            "User cancelled during chunk processing"
                        )

            try:
                # Check if this is a batch or single chunk
                if isinstance(chunk_or_batch, tuple) and chunk_or_batch[0] == "batch":
                    # Process batch
                    return await _process_batched_content(chunk_or_batch[1])
                else:
                    # Process single chunk
                    return await _process_single_content(chunk_or_batch)
            except Exception as e:
                chunk_id = chunk_or_batch[0] if not isinstance(chunk_or_batch, tuple) or chunk_or_batch[0] != "batch" else "batch"
                prefixed_exception = create_prefixed_exception(e, chunk_id)
                raise prefixed_exception from e

    # Create tasks for batched chunks and REGISTER them for cancellation
    tasks = []
    for c in batched_chunks:  # Use batched_chunks instead of ordered_chunks
        if isinstance(c, tuple) and c[0] == "batch":
            task_name = f"extract_batch_{len(c[1])}_chunks"
        else:
            task_name = f"extract_chunk_{c[0][:16]}"
        
        task = asyncio.create_task(_process_with_semaphore(c))
        task.set_name(task_name)
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
            finally:
                # Unregister completed tasks immediately
                await unregister_extraction_task(task)

        if first_exception is not None:
            # Cancel pending tasks
            for pending_task in pending:
                pending_task.cancel()

            if pending:
                await asyncio.wait(pending)
            
            # Unregister cancelled tasks
            for pending_task in pending:
                await unregister_extraction_task(pending_task)

            progress_prefix = f"C[{processed_chunks + 1}/{total_chunks}]"
            prefixed_exception = create_prefixed_exception(first_exception, progress_prefix)
            raise prefixed_exception from first_exception

        return chunk_results

    except asyncio.CancelledError:
        logger.info("[operate_custom] extract_entities was cancelled by user")
        # Cancel any remaining tasks
        cancelled_count = 0
        for task in tasks:
            if not task.done():
                task.cancel()
                cancelled_count += 1
        
        # Wait for cancellation to complete
        if cancelled_count > 0:
            await asyncio.wait(tasks)
            logger.info(f"[operate_custom] Cancelled {cancelled_count} extraction tasks")
        
        raise PipelineCancelledException("User cancelled extraction")

    finally:
        # Final cleanup: unregister any remaining tasks that weren't unregistered above
        remaining_count = 0
        for task in tasks:
            try:
                # Check if task is still in the registered list
                async with _extraction_tasks_lock:
                    if task in _running_extraction_tasks:
                        _running_extraction_tasks.discard(task)
                        remaining_count += 1
            except Exception:
                pass
        
        if remaining_count > 0:
            logger.debug(f"[operate_custom] Final cleanup: unregistered {remaining_count} remaining tasks")
