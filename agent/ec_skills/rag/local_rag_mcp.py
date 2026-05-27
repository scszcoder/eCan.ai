import asyncio
import os
import threading
import time
from typing import Any, Dict, List, Optional

from utils.logger_helper import get_traceback
from utils.logger_helper import logger_helper as logger
from mcp.types import TextContent
from knowledge.lightrag_client import get_client


# ─── Test-mode RAG fault injection (opt-in via ECAN_EMULATION_TEST_FLAGS=1) ─
#
# 2026-05-24 mt038 (mt019/20 local repro): mirrors the LLM 429 injector in
# build_node.py.  Reads customer_logs/emulation/emulation_config.json's
# ``ragFault`` stanza before every rag_query call.  Two modes:
#
#   "hang"  → asyncio.sleep(hangSeconds) before letting the real RAG call
#             proceed — used to exercise mt019's 10s rag_query timeout
#             cap (set hangSeconds > 10 to force fallback).
#   "error" → raise ValueError immediately so the QA worker's RAG-error
#             handling path runs.
#
# Disabled entirely when the env flag is unset; even when enabled, a
# probability of 0 in the JSON is a no-op.
_RAG_FAULT_CONFIG_CACHE: dict = {"mtime": 0.0, "data": {}}


async def _maybe_inject_rag_test_fault(query_text: str) -> None:
    """If emulation test flags are on, possibly hang or raise before RAG."""
    if os.getenv("ECAN_EMULATION_TEST_FLAGS", "").strip() not in ("1", "true", "True", "TRUE"):
        return
    try:
        from pathlib import Path
        emu_root = Path(__file__).resolve().parents[3] / "customer_logs" / "emulation"
        cfg_path = emu_root / "emulation_config.json"
        if not cfg_path.is_file():
            return
        mtime = cfg_path.stat().st_mtime
        cache = _RAG_FAULT_CONFIG_CACHE
        if mtime != cache["mtime"]:
            import json as _json
            cache["data"] = _json.loads(cfg_path.read_text(encoding="utf-8"))
            cache["mtime"] = mtime
        fault = (cache["data"] or {}).get("ragFault") or {}
        prob = float(fault.get("injectProbability") or 0.0)
        if prob <= 0.0:
            return
        import random as _random
        if _random.random() >= prob:
            return
        mode = str(fault.get("mode") or "hang").lower()
        if mode == "error":
            logger.warning(
                f"[TEST-FAULT][RAG] Injecting synthetic RAG error "
                f"(query={query_text[:30]!r} prob={prob})"
            )
            raise ValueError(
                "Synthetic RAG fault injected by ECAN_EMULATION_TEST_FLAGS "
                "(mode=error)"
            )
        # default: hang
        hang_s = max(0.0, float(fault.get("hangSeconds") or 30))
        logger.warning(
            f"[TEST-FAULT][RAG] Hanging rag_query for {hang_s}s "
            f"(query={query_text[:30]!r} prob={prob})"
        )
        await asyncio.sleep(hang_s)
    except ValueError:
        raise
    except Exception as _exc:
        logger.debug(f"[TEST-FAULT][RAG] injector skipped due to error: {_exc}")
        return


async def ragify(mainwin, args):
    """
    MCP Tool: Ingest documents into LightRAG for RAG indexing.
    
    Supports two modes:
    1. File upload: Upload files from file_paths to LightRAG
    2. Text insert: Directly insert text content into LightRAG
    
    Based on LightRAG API:
    - POST /documents/upload (file upload)
    - POST /documents/text (text insert)
    """
    try:
        rag_result = None
        input_data = args.get('input', {})
        
        if not input_data:
            return [TextContent(type="text", text="Error: No input data provided")]
            
        logger.debug(f"[MCP][RAGIFY]: {input_data}")
        
        # Extract parameters
        file_paths = input_data.get("file_paths", [])
        text = input_data.get("text")
        file_source = input_data.get("file_source")
        # Optional LightRAG workspace (tenant) for data isolation.
        # Empty / missing → uses the server's default workspace.
        workspace = (input_data.get("workspace") or "").strip() or None
        
        # Initialize client
        client = get_client()
        
        # Mode 1: File upload
        if file_paths:
            # ingest_files / insert_text use sync requests under the hood;
            # off-load so we don't block the MCP server's event loop.
            rag_result = await asyncio.to_thread(
                client.ingest_files, file_paths, workspace=workspace
            )
            logger.info(f"[MCP][RAGIFY] File ingestion result: {rag_result} (workspace={workspace!r})")
            msg = f"Ingested {len(file_paths)} file(s)"
        # Mode 2: Text insert
        elif text:
            metadata = {"file_source": file_source} if file_source else None
            rag_result = await asyncio.to_thread(
                client.insert_text, text, metadata, workspace=workspace
            )
            logger.info(f"[MCP][RAGIFY] Text insert result: {rag_result}")
            msg = "Text inserted successfully"
        else:
            rag_result = {"status": "error", "message": "No file_paths or text provided"}
            msg = "Error: No file_paths or text provided"

        # Build response
        if rag_result.get("status") == "success":
            result_text = f"{msg}. Track ID: {rag_result.get('data', {}).get('track_id', 'N/A')}"
        else:
            result_text = f"Error: {rag_result.get('message', 'Unknown error')}"
            
        result = TextContent(type="text", text=result_text)
        if isinstance(rag_result, dict):
            result.meta = rag_result
        else:
            result.meta = {"result": str(rag_result)}
             
        return [result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorRagifyTool")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def rag_replace_document(mainwin, args):
    """MCP Tool: Re-ingest a file in place after it has been edited.

    Wraps :py:meth:`knowledge.lightrag_client.LightragClient.replace_document`.
    Use this when a source file (``abc.md``, etc.) has been modified on
    disk and you want the vector DB + knowledge graph to reflect the new
    contents. Naively re-ingesting would create duplicate entries because
    LightRAG dedupes by content hash; this tool deletes the old copies
    first.

    Input schema:
        path (str, required): Absolute local path to the *new* version
            of the file.
        workspace (str, optional): LightRAG workspace (tenant). Empty
            falls back to the server's default workspace.
        match_basename (bool, optional, default True): When True, match
            old copies by filename only. Set False to require an exact
            file_path string match instead.

    Returns a TextContent whose ``meta`` carries::

        {
            "matched_basename": "abc.md",
            "deleted_ids": [...],
            "deleted_count": 2,
            "delete_errors": [...],
            "ingest": {"status": "success", "track_id": "..."},
        }
    """
    try:
        input_data = args.get("input", {}) if args else {}
        if not input_data:
            return [TextContent(type="text", text="Error: No input data provided")]

        logger.debug(f"[MCP][RAG_REPLACE]: {input_data}")

        path = (input_data.get("path") or "").strip()
        if not path:
            return [TextContent(
                type="text",
                text="Error: 'path' is required and must be a non-empty string"
            )]

        workspace = (input_data.get("workspace") or "").strip() or None
        match_basename = bool(input_data.get("match_basename", True))

        client = get_client()
        result = await asyncio.to_thread(
            client.replace_document,
            path,
            workspace=workspace,
            match_basename=match_basename,
        )

        if result.get("status") == "success":
            data = result.get("data") or {}
            track_id = (data.get("ingest") or {}).get("track_id", "N/A")
            msg = (
                f"Replaced '{data.get('matched_basename', path)}': "
                f"deleted {data.get('deleted_count', 0)} old copy/copies, "
                f"re-ingest track_id={track_id}"
            )
            logger.info(
                f"[MCP][RAG_REPLACE] {msg} (workspace={workspace!r})"
            )
        else:
            msg = f"Error: {result.get('message', 'Unknown error')}"
            logger.warning(f"[MCP][RAG_REPLACE] {msg}")

        out = TextContent(type="text", text=msg)
        if isinstance(result, dict):
            out.meta = result
        else:
            out.meta = {"result": str(result)}
        return [out]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorRagReplaceDocumentTool")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def rag_query(mainwin, args):
    """
    MCP Tool: Query LightRAG knowledge base.
    
    Based on LightRAG API POST /query:
    - query: Query text (required, min 3 chars)
    - mode: Query mode (local, global, hybrid, naive, mix, bypass), default: mix
    - only_need_context: Return only context without generating response
    - only_need_prompt: Return only prompt without generating response
    - response_type: Response format (e.g., 'Multiple Paragraphs', 'Bullet Points')
    - top_k: Number of top items to retrieve
    - conversation_history: Past conversation for context
    - user_prompt: Custom user prompt
    - enable_rerank: Enable reranking (default: True)
    - include_references: Include reference list (default: True)
    """
    try:
        rag_result = None
        input_data = args.get('input', {})
        
        if not input_data:
            return [TextContent(type="text", text="Error: No input data provided")]
            
        logger.debug(f"[MCP][RAG_QUERY]: {input_data}")
        
        # Extract query (required)
        query_text = input_data.get("query")
        if not query_text or len(query_text.strip()) < 3:
            return [TextContent(type="text", text="Error: Query must be at least 3 characters")]

        # Test-mode fault injection (no-op unless ECAN_EMULATION_TEST_FLAGS=1
        # AND ragFault.injectProbability > 0 in emulation_config.json).
        await _maybe_inject_rag_test_fault(query_text)

        try:
            from agent.ec_tasks.runner import is_app_shutdown_active
            if is_app_shutdown_active():
                msg = "Error: RAG query aborted because application shutdown is in progress"
                logger.warning(f"[MCP][RAG_QUERY] {msg}")
                out = TextContent(type="text", text=msg)
                out.meta = {
                    "status": "shutdown_aborted",
                    "code": "APP_SHUTDOWN",
                    "message": msg,
                    "query": query_text.strip(),
                }
                return [out]
        except Exception:
            pass
        
        # Optional LightRAG workspace (tenant) for data isolation.
        # Empty / missing → uses the server's default workspace.
        workspace = (input_data.get("workspace") or "").strip() or None
        
        # Initialize client
        client = get_client()
        
        # Build options from input - map to LightRAG QueryRequest parameters
        options = {}
        
        # Mode: local, global, hybrid, naive, mix, bypass
        # 2026-05-21 mt020 — default mode is operator-tunable.  Customer
        # live-site trace 21:00-21:17 showed 80% of rag_query calls
        # triggered a deepseek-API keyword-extraction LLM call (cache miss),
        # adding 5-50 seconds per query.  Only ``naive`` mode skips the
        # keyword-extraction LLM entirely (pure vector search).  Default
        # remains ``mix`` for backwards compat; operators serving a Q&A
        # workload on a well-indexed KB should set
        # ``ECAN_RAG_QUERY_DEFAULT_MODE=naive`` to cut RAG latency 5-10x.
        import os as _os
        _env_default_mode = (_os.getenv("ECAN_RAG_QUERY_DEFAULT_MODE") or "mix").strip().lower()
        if _env_default_mode not in ["local", "global", "hybrid", "naive", "mix", "bypass"]:
            _env_default_mode = "mix"
        mode = input_data.get("mode") or _env_default_mode
        if mode in ["local", "global", "hybrid", "naive", "mix", "bypass"]:
            options["mode"] = mode
        else:
            options["mode"] = _env_default_mode
            
        # All optional parameters from LightRAG QueryRequest schema
        OPTIONAL_PARAMS = [
            "only_need_context",     # bool
            "only_need_prompt",      # bool
            "response_type",         # str
            "top_k",                 # int
            "chunk_top_k",           # int
            "max_entity_tokens",     # int
            "max_relation_tokens",   # int
            "max_total_tokens",      # int
            "hl_keywords",           # list[str]
            "ll_keywords",           # list[str]
            "conversation_history",  # list[dict]
            "user_prompt",           # str
            "enable_rerank",         # bool
            "include_references",    # bool
            "include_chunk_content", # bool
        ]
        
        for param in OPTIONAL_PARAMS:
            if param in input_data and input_data[param] is not None:
                # Skip empty lists/strings
                val = input_data[param]
                if isinstance(val, list) and len(val) == 0:
                    continue
                if isinstance(val, str) and not val.strip():
                    continue
                options[param] = val

        # Default to context-only retrieval. LightRAG's internal synthesis LLM
        # is the dominant latency cost (~10-13s of a typical /query); skipping
        # it cuts rag_query end-to-end from ~16s to ~3s. The caller's outer LLM
        # composes the customer-facing reply from the retrieved chunks anyway.
        # Callers that want a fully synthesized answer can pass
        # only_need_context=false explicitly.
        if "only_need_context" not in options:
            options["only_need_context"] = True

        # 2026-05-26 mt047A — single-knob fast-path for Q&A workloads.
        # Live customer trace 2026-05-26 10:16 showed a typical Q&A turn
        # spending ~8s in rag_query with mode='mix' + only_need_context=False
        # + enable_rerank=True (the defaults baked into the skill's MCP node).
        # The outer Q&A LLM throws away RAG's narrative answer and regenerates
        # from the retrieved chunks anyway, so the synthesis LLM round-trip +
        # keyword-extraction LLM round-trip + rerank LLM round-trip are pure
        # waste here.
        #
        # When ECAN_RAG_QUERY_FAST_PATH is set to a truthy value (1/true/yes/on),
        # force the fastest configuration regardless of what the MCP node sends:
        # mode='naive' (pure vector search, skips keyword-extraction LLM),
        # only_need_context=True (skip synthesis LLM), enable_rerank=False
        # (skip rerank LLM).  Expected impact: ~8-12s per call.  Tradeoff: RAG
        # returns raw chunks instead of synthesized answer + similarity-ranked
        # instead of LLM-reranked.  Outer LLM compensates.
        #
        # mt050M (2026-05-27): Default flipped to ON.  The 2026-05-27 9-hour
        # customer log showed mt047A had never fired in production — the env
        # var was never set on the customer's machine, so 89 rag_query calls
        # each paid the keyword-extraction + rerank LLM tax.  Defaulting to
        # ON pays back ~700-1000s of cumulative RAG latency per session for
        # the Q&A path that already compensates for the lost narrative.  To
        # opt out: set ECAN_RAG_QUERY_FAST_PATH=0 (or false / no / off).
        #
        # This block MUST run before the _is_context_only read below;
        # otherwise the override of only_need_context here is ignored by the
        # path-selection branch.
        _fast_path_env = (_os.getenv("ECAN_RAG_QUERY_FAST_PATH") or "1").strip().lower()
        if _fast_path_env in ("1", "true", "yes", "on"):
            options["mode"] = "naive"
            options["only_need_context"] = True
            options["enable_rerank"] = False
            logger.info(
                "[MCP][RAG_QUERY] mt047A fast-path active: forced "
                "mode=naive, only_need_context=True, enable_rerank=False"
            )

        # Context-only queries use blocking /query (fast, <5s).
        # Full-generation queries use /query/stream to avoid timeout on slow LLMs.
        _is_context_only = options.get("only_need_context", False)
        
        if _is_context_only:
            # Off-load to a worker thread: client.query uses requests.Session
            # (sync HTTP). Calling it directly inside this async handler blocks
            # the MCP server's event loop, serializing every other concurrent
            # tool call and starving the streamable-HTTP response stream —
            # which manifests as a 60s persistent-session timeout on the
            # build_node client side.
            #
            # Timeout sized for the rerank-disabled steady state.  Customer
            # forensics on 2026-05-18 13:40:23-57 showed a 33.7s LightRAG-side
            # query where ~30.7s was 3 failed rerank-retry round-trips after
            # gui/lightrag_rerank_proxy.py returned 400 for RERANK_BINDING=null.
            # That same trace timed out the client at 30s and forced a no-rag
            # fallback.  With the proxy now short-circuiting "null" /
            # "disabled" / etc. to a neutral-score passthrough, the actual
            # query work is ~3-5s and 45s leaves a ~10× safety margin for
            # large-KG or under-concurrent-load tail cases.  If you see this
            # timeout firing again, look first for new rerank-retry tax or
            # other upstream regressions before bumping further.
            response = await asyncio.to_thread(
                client.query, query_text.strip(), options, timeout=45, workspace=workspace
            )
            if response.get("status") == "success":
                data = response.get("data", {})
                if isinstance(data, dict):
                    answer = data.get("response", str(data))
                    # /query in context-only mode doesn't emit confidence, but
                    # downstream gates (system prompt Step 3) require it. Mirror
                    # the streaming-path fallback so callers always see a score.
                    if "confidence" not in data:
                        try:
                            from knowledge.lightrag_confidence_scorer import score_lightrag_response
                            data["confidence"] = score_lightrag_response(
                                query=query_text.strip(),
                                response_data={
                                    "response": answer,
                                    "references": data.get("references", []),
                                },
                                query_options=options,
                            )
                        except Exception as score_err:
                            logger.warning(f"[MCP][RAG_QUERY] Local confidence scoring failed: {score_err}")
                else:
                    answer = str(data)
                rag_result = response
            elif response.get("status") == "aborted":
                data = response.get("data", {})
                answer = data.get("response", response.get("message", "Query aborted")) if isinstance(data, dict) else response.get("message", "Query aborted")
                rag_result = response
            else:
                answer = f"Error: {response.get('message', 'Query failed')}"
                rag_result = response
        else:
            # Streaming call — keeps connection alive for slow LLM generation.
            # query_stream is a sync generator over a blocking HTTP socket;
            # consume it inside a worker thread so the MCP server's event
            # loop remains responsive for other concurrent tool calls.
            import json as _json

            def _consume_stream():
                accumulated = ""
                refs = []
                confidence = None
                no_answer_message = None
                aborted = False
                abort_message = ""
                for chunk_line in client.query_stream(query_text.strip(), options, workspace=workspace):
                    try:
                        chunk_data = _json.loads(chunk_line)
                        if chunk_data.get("aborted") or chunk_data.get("status") == "aborted":
                            aborted = True
                            abort_message = chunk_data.get("message") or chunk_data.get("response") or "Query aborted"
                            accumulated += abort_message
                            break
                        if "response" in chunk_data:
                            accumulated += chunk_data.get("response", "")
                        if "references" in chunk_data:
                            refs = chunk_data.get("references", [])
                        # Final confidence chunk emitted by lightrag_client.query_stream
                        if "confidence" in chunk_data:
                            confidence = chunk_data.get("confidence")
                        if "no_answer_message" in chunk_data:
                            no_answer_message = chunk_data.get("no_answer_message")
                    except _json.JSONDecodeError:
                        accumulated += chunk_line
                return accumulated, refs, confidence, no_answer_message, aborted, abort_message

            _accumulated = ""
            _refs = []
            _confidence = None
            _no_answer_message = None
            _aborted = False
            _abort_message = ""
            try:
                _accumulated, _refs, _confidence, _no_answer_message, _aborted, _abort_message = await asyncio.to_thread(_consume_stream)

                if _aborted:
                    answer = _abort_message or _accumulated or "Query aborted"
                    rag_result = {
                        "status": "aborted",
                        "message": answer,
                        "reason": "shutdown",
                        "data": {
                            "response": answer,
                            "aborted": True,
                            "abort_reason": "shutdown",
                            "references": _refs,
                        },
                    }
                    result = TextContent(type="text", text=answer)
                    result.meta = rag_result
                    return [result]

                # Fallback: if upstream didn't emit a confidence chunk, compute it
                # locally so callers always see the score.
                if _confidence is None:
                    try:
                        from knowledge.lightrag_confidence_scorer import score_lightrag_response
                        _confidence = score_lightrag_response(
                            query=query_text.strip(),
                            response_data={"response": _accumulated, "references": _refs},
                            query_options=options,
                        )
                    except Exception as score_err:
                        logger.warning(f"[MCP][RAG_QUERY] Local confidence scoring failed: {score_err}")
                        _confidence = None

                # If LightRAG (or our fallback) decided the answer is unsafe,
                # surface its no-answer message as the tool text.
                _decision = (_confidence or {}).get("decision") or {}
                if _decision.get("should_answer") is False and _no_answer_message:
                    answer = _no_answer_message
                else:
                    answer = _accumulated

                _data_payload = {
                    "response": _accumulated,
                    "references": _refs,
                }
                if _confidence is not None:
                    _data_payload["confidence"] = _confidence
                if _no_answer_message:
                    _data_payload["no_answer_message"] = _no_answer_message
                rag_result = {"status": "success", "data": _data_payload}
            except Exception as stream_err:
                logger.warning(f"[MCP][RAG_QUERY] Stream failed, falling back to blocking: {stream_err}")
                response = await asyncio.to_thread(
                    client.query, query_text.strip(), options, timeout=90, workspace=workspace
                )
                if response.get("status") == "success":
                    data = response.get("data", {})
                    answer = data.get("response", str(data)) if isinstance(data, dict) else str(data)
                    rag_result = response
                elif response.get("status") == "aborted":
                    data = response.get("data", {})
                    answer = data.get("response", response.get("message", "Query aborted")) if isinstance(data, dict) else response.get("message", "Query aborted")
                    rag_result = response
                else:
                    answer = f"Error: {response.get('message', 'Query failed')}"
                    rag_result = response

        result = TextContent(type="text", text=answer)
        if isinstance(rag_result, dict):
            result.meta = rag_result
        else:
            result.meta = {"result": str(rag_result)}
             
        return [result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorRagQueryTool")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]

def add_ragify_tool_schema(tool_schemas):
    """
    Add ragify tool schema for document ingestion into LightRAG.
    
    Based on LightRAG API:
    - POST /documents/upload - Upload files for indexing
    - POST /documents/text - Insert text directly
    
    Reference: https://github.com/HKUDS/LightRAG/blob/main/lightrag/api/routers/document_routes.py
    """
    import mcp.types as types

    tool_schema = types.Tool(_meta={"run_in_cloud": False},
        name="ragify",
        description="Ingest documents or text into LightRAG for RAG indexing. Supports file upload or direct text insertion. Returns a track_id for monitoring processing status.",
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "properties": {
                        "file_paths": {
                            "type": "array",
                            "description": "List of file paths to upload and index. Supports: pdf, doc, docx, txt, md, html, csv, json, xml, py, js, etc.",
                            "items": {"type": "string"}
                        },
                        "text": {
                            "type": "string",
                            "description": "Direct text content to insert into the knowledge base (alternative to file_paths)."
                        },
                        "file_source": {
                            "type": "string",
                            "description": "Optional source identifier for the inserted text."
                        },
                        "workspace": {
                            "type": "string",
                            "description": "Optional LightRAG workspace (tenant) name for data isolation. Use the same workspace consistently per category (e.g. 'customer_service', 'product_details'). Omit to use the server's default workspace."
                        }
                    }
                }
            }
        },
    )

    tool_schemas.append(tool_schema)


# ==================== Option 4: wait_for_rag_completion ====================

def _calculate_timeout_seconds(file_paths: List[str], text: str = None) -> int:
    """
    Calculate timeout based on file sizes.
    Formula: (total_size_kb / 10) * 60 + 180 seconds (10KB/min + 3min buffer)
    """
    total_size_bytes = 0
    
    if file_paths:
        for path in file_paths:
            try:
                if os.path.exists(path):
                    total_size_bytes += os.path.getsize(path)
            except Exception:
                pass
    
    if text:
        total_size_bytes += len(text.encode('utf-8'))
    
    # Convert to KB
    total_size_kb = total_size_bytes / 1024
    
    # Formula: 10KB/min + 3min buffer
    timeout_seconds = int((total_size_kb / 10) * 60 + 180)
    
    # Minimum 3 minutes, maximum 60 minutes
    return max(180, min(timeout_seconds, 3600))


async def wait_for_rag_completion(mainwin, args):
    """
    MCP Tool: Wait for RAG ingestion to complete by polling track_id status.
    
    This is a synchronous blocking tool that polls LightRAG until all documents
    in the track_id are processed or failed, or timeout is reached.
    
    Timeout formula: (total_file_size_kb / 10) * 60 + 180 seconds (10KB/min + 3min buffer)
    
    Returns partial results if some documents succeed and others fail.
    """
    try:
        input_data = args.get('input', {})
        
        if not input_data:
            return [TextContent(type="text", text="Error: No input data provided")]
        
        track_id = input_data.get("track_id")
        if not track_id:
            return [TextContent(type="text", text="Error: track_id is required")]
        
        poll_interval = input_data.get("poll_interval_seconds", 15)
        timeout_seconds = input_data.get("timeout_seconds")
        max_retries = input_data.get("max_retries", 3)
        # Optional LightRAG workspace (tenant). Must match the workspace
        # passed to ragify / ragify_async when this track_id was created.
        workspace = (input_data.get("workspace") or "").strip() or None
        
        # If timeout not provided, use default based on typical file size estimate
        # (we don't have file sizes here, so use a reasonable default)
        if timeout_seconds is None:
            timeout_seconds = 600  # 10 minutes default
        
        logger.info(f"[wait_for_rag_completion] Waiting for track_id={track_id}, "
                   f"timeout={timeout_seconds}s, poll_interval={poll_interval}s")
        
        client = get_client()
        start_time = time.time()
        retry_count = 0
        last_status = None
        
        while True:
            elapsed = time.time() - start_time
            
            # Check timeout
            if elapsed >= timeout_seconds:
                logger.warning(f"[wait_for_rag_completion] Timeout after {elapsed:.1f}s for track_id={track_id}")
                result_text = f"Timeout after {elapsed:.1f}s. Last status: {last_status}"
                result = TextContent(type="text", text=result_text)
                result.meta = {
                    "status": "timeout",
                    "track_id": track_id,
                    "elapsed_seconds": elapsed,
                    "last_status": last_status
                }
                return [result]
            
            # Poll status
            try:
                status_response = await asyncio.to_thread(
                    client.track_status, track_id, workspace=workspace
                )
                retry_count = 0  # Reset retry count on success
                
                if status_response.get("status") == "success":
                    data = status_response.get("data", {})
                    documents = data.get("documents", [])
                    status_summary = data.get("status_summary", {})
                    
                    last_status = status_summary
                    
                    # Check if all documents are done (processed or failed)
                    pending_count = status_summary.get("pending", 0)
                    processing_count = status_summary.get("processing", 0)
                    preprocessed_count = status_summary.get("preprocessed", 0)
                    processed_count = status_summary.get("processed", 0)
                    failed_count = status_summary.get("failed", 0)
                    
                    in_progress = pending_count + processing_count + preprocessed_count
                    
                    logger.debug(f"[wait_for_rag_completion] Status: pending={pending_count}, "
                               f"processing={processing_count}, preprocessed={preprocessed_count}, "
                               f"processed={processed_count}, failed={failed_count}")
                    
                    if in_progress == 0:
                        # All done
                        if failed_count > 0 and processed_count > 0:
                            result_text = f"Partial completion: {processed_count} processed, {failed_count} failed"
                            final_status = "partial_success"
                        elif failed_count > 0:
                            result_text = f"All {failed_count} document(s) failed"
                            final_status = "failed"
                        else:
                            result_text = f"All {processed_count} document(s) processed successfully"
                            final_status = "success"
                        
                        logger.info(f"[wait_for_rag_completion] Completed: {result_text}")
                        
                        result = TextContent(type="text", text=result_text)
                        result.meta = {
                            "status": final_status,
                            "track_id": track_id,
                            "elapsed_seconds": elapsed,
                            "processed_count": processed_count,
                            "failed_count": failed_count,
                            "documents": documents
                        }
                        return [result]
                else:
                    logger.warning(f"[wait_for_rag_completion] Status check failed: {status_response.get('message')}")
                    retry_count += 1
                    
            except Exception as e:
                logger.warning(f"[wait_for_rag_completion] Poll error: {e}")
                retry_count += 1
                
                if retry_count >= max_retries:
                    result_text = f"Max retries ({max_retries}) exceeded. Last error: {e}"
                    result = TextContent(type="text", text=result_text)
                    result.meta = {
                        "status": "error",
                        "track_id": track_id,
                        "elapsed_seconds": elapsed,
                        "error": str(e)
                    }
                    return [result]
            
            # Wait before next poll
            await asyncio.sleep(poll_interval)
            
    except Exception as e:
        err_trace = get_traceback(e, "ErrorWaitForRagCompletion")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


# ==================== Option 3: ragify_async with callback ====================

# Global registry for pending async RAG operations
_pending_rag_callbacks: Dict[str, Dict[str, Any]] = {}


def _rag_completion_monitor(
    track_id: str,
    timeout_seconds: int,
    poll_interval: int,
    task_id: str,
    chat_id: str,
    mainwin: Any,
    notification_message: str = None,
    workspace: Optional[str] = None,
):
    """
    Background thread that monitors RAG completion and sends notification to task queue.
    
    If the original task is ended, falls back to the chat task.
    """
    try:
        logger.info(f"[RAG_MONITOR] Started for track_id={track_id}, task_id={task_id}, timeout={timeout_seconds}s")
        
        client = get_client()
        start_time = time.time()
        
        while True:
            elapsed = time.time() - start_time
            
            # Check timeout
            if elapsed >= timeout_seconds:
                logger.warning(f"[RAG_MONITOR] Timeout for track_id={track_id}")
                _send_rag_notification(
                    mainwin, task_id, chat_id, track_id,
                    status="timeout",
                    message=notification_message or f"RAG ingestion timed out after {elapsed:.0f}s",
                    elapsed_seconds=elapsed
                )
                break
            
            # Poll status
            try:
                status_response = client.track_status(track_id, workspace=workspace)
                
                if status_response.get("status") == "success":
                    data = status_response.get("data", {})
                    status_summary = data.get("status_summary", {})
                    
                    pending_count = status_summary.get("pending", 0)
                    processing_count = status_summary.get("processing", 0)
                    preprocessed_count = status_summary.get("preprocessed", 0)
                    processed_count = status_summary.get("processed", 0)
                    failed_count = status_summary.get("failed", 0)
                    
                    in_progress = pending_count + processing_count + preprocessed_count
                    
                    if in_progress == 0:
                        # All done
                        if failed_count > 0 and processed_count > 0:
                            final_status = "partial_success"
                            msg = f"RAG ingestion partial: {processed_count} processed, {failed_count} failed"
                        elif failed_count > 0:
                            final_status = "failed"
                            msg = f"RAG ingestion failed: {failed_count} document(s)"
                        else:
                            final_status = "success"
                            msg = f"RAG ingestion complete: {processed_count} document(s) processed"
                        
                        logger.info(f"[RAG_MONITOR] Completed: {msg}")
                        _send_rag_notification(
                            mainwin, task_id, chat_id, track_id,
                            status=final_status,
                            message=notification_message or msg,
                            elapsed_seconds=elapsed,
                            processed_count=processed_count,
                            failed_count=failed_count,
                            documents=data.get("documents", [])
                        )
                        break
                        
            except Exception as e:
                logger.warning(f"[RAG_MONITOR] Poll error for track_id={track_id}: {e}")
            
            # Wait before next poll
            time.sleep(poll_interval)
            
    except Exception as e:
        logger.error(get_traceback(e, "ErrorRagMonitor"))
    finally:
        # Cleanup
        if track_id in _pending_rag_callbacks:
            del _pending_rag_callbacks[track_id]


def _send_rag_notification(
    mainwin: Any,
    task_id: str,
    chat_id: str,
    track_id: str,
    status: str,
    message: str,
    elapsed_seconds: float = 0,
    processed_count: int = 0,
    failed_count: int = 0,
    documents: List = None
):
    """
    Send RAG completion notification to the task's message queue.
    Falls back to chat task if original task is ended.
    """
    try:
        notification = {
            "type": "rag_completion",
            "track_id": track_id,
            "status": status,
            "message": message,
            "elapsed_seconds": elapsed_seconds,
            "processed_count": processed_count,
            "failed_count": failed_count,
            "documents": documents or [],
            "timestamp": int(time.time() * 1000)
        }
        
        # Try to find the target task
        target_task = None
        
        if mainwin and hasattr(mainwin, 'agents'):
            for agent in mainwin.agents:
                tasks = getattr(agent, 'tasks', []) or []
                for task in tasks:
                    # First try to find the original task
                    if task_id and getattr(task, 'id', None) == task_id:
                        # Check if task is still active
                        task_status = getattr(task, 'status', None)
                        if task_status:
                            state = getattr(task_status, 'state', None)
                            state_str = state.value if hasattr(state, 'value') else str(state)
                            if state_str.lower() in ('working', 'running', 'in_progress', 'pending'):
                                target_task = task
                                break
                    
                    # Fallback: find chat task by chat_id
                    if not target_task and chat_id:
                        skill = getattr(task, 'skill', None)
                        if skill and getattr(skill, 'name', '').lower() in ('chat', 'chatter'):
                            target_task = task
                
                if target_task:
                    break
        
        if target_task and hasattr(target_task, 'queue') and target_task.queue:
            try:
                target_task.queue.put_nowait(notification)
                logger.info(f"[RAG_NOTIFY] Sent notification to task={getattr(target_task, 'name', 'unknown')}")
            except Exception as e:
                logger.error(f"[RAG_NOTIFY] Failed to queue notification: {e}")
        else:
            logger.warning(f"[RAG_NOTIFY] No active task found for notification. task_id={task_id}, chat_id={chat_id}")
            
    except Exception as e:
        logger.error(get_traceback(e, "ErrorSendRagNotification"))


async def ragify_async(mainwin, args):
    """
    MCP Tool: Ingest documents into LightRAG with async completion notification.
    
    This is a fire-and-forget tool that starts ingestion and optionally monitors
    completion in a background thread, sending a notification to the task queue
    when done.
    
    Parameters:
        - file_paths: List of file paths to upload
        - text: Direct text to insert (alternative to file_paths)
        - file_source: Source identifier for text
        - on_complete: If true, monitor completion and send notification
        - notify_task_id: Target task ID for notification (defaults to current task)
        - notify_chat_id: Fallback chat ID if task is ended
        - timeout_seconds: Max time to wait (auto-calculated from file size if not provided)
        - poll_interval_seconds: How often to check status (default: 15)
        - notification_message: Custom message to include in notification
    """
    try:
        input_data = args.get('input', {})
        
        if not input_data:
            return [TextContent(type="text", text="Error: No input data provided")]
        
        logger.debug(f"[MCP][RAGIFY_ASYNC]: {input_data}")
        
        # Extract parameters
        file_paths = input_data.get("file_paths", [])
        text = input_data.get("text")
        file_source = input_data.get("file_source")
        on_complete = input_data.get("on_complete", False)
        notify_task_id = input_data.get("notify_task_id", "")
        notify_chat_id = input_data.get("notify_chat_id", "")
        timeout_seconds = input_data.get("timeout_seconds")
        poll_interval = input_data.get("poll_interval_seconds", 15)
        notification_message = input_data.get("notification_message")
        # Optional LightRAG workspace (tenant) for data isolation.
        workspace = (input_data.get("workspace") or "").strip() or None
        
        # Initialize client
        client = get_client()
        
        # Mode 1: File upload
        if file_paths:
            rag_result = await asyncio.to_thread(
                client.ingest_files, file_paths, workspace=workspace
            )
            logger.info(f"[MCP][RAGIFY_ASYNC] File ingestion result: {rag_result} (workspace={workspace!r})")
            msg = f"Ingested {len(file_paths)} file(s)"

            # Calculate timeout from file sizes if not provided
            if timeout_seconds is None:
                timeout_seconds = _calculate_timeout_seconds(file_paths)

        # Mode 2: Text insert
        elif text:
            metadata = {"file_source": file_source} if file_source else None
            rag_result = await asyncio.to_thread(
                client.insert_text, text, metadata, workspace=workspace
            )
            logger.info(f"[MCP][RAGIFY_ASYNC] Text insert result: {rag_result}")
            msg = "Text inserted successfully"
            
            # Calculate timeout from text size if not provided
            if timeout_seconds is None:
                timeout_seconds = _calculate_timeout_seconds([], text)
        else:
            rag_result = {"status": "error", "message": "No file_paths or text provided"}
            msg = "Error: No file_paths or text provided"
        
        # Build response
        track_id = None
        if rag_result.get("status") == "success":
            track_id = rag_result.get('data', {}).get('track_id', 'N/A')
            result_text = f"{msg}. Track ID: {track_id}"
            
            # Start background monitor if on_complete is enabled
            if on_complete and track_id and track_id != 'N/A':
                logger.info(f"[RAGIFY_ASYNC] Starting completion monitor for track_id={track_id}")
                
                # Store callback info
                _pending_rag_callbacks[track_id] = {
                    "task_id": notify_task_id,
                    "chat_id": notify_chat_id,
                    "start_time": time.time()
                }
                
                # Start background thread
                monitor_thread = threading.Thread(
                    target=_rag_completion_monitor,
                    args=(track_id, timeout_seconds, poll_interval, notify_task_id, notify_chat_id, mainwin, notification_message, workspace),
                    daemon=True,
                    name=f"rag_monitor_{track_id}"
                )
                monitor_thread.start()
                
                result_text += f" (monitoring for completion, timeout={timeout_seconds}s)"
        else:
            result_text = f"Error: {rag_result.get('message', 'Unknown error')}"
        
        result = TextContent(type="text", text=result_text)
        if isinstance(rag_result, dict):
            result.meta = rag_result
            if on_complete:
                result.meta["monitoring"] = True
                result.meta["timeout_seconds"] = timeout_seconds
        else:
            result.meta = {"result": str(rag_result)}
        
        return [result]
        
    except Exception as e:
        err_trace = get_traceback(e, "ErrorRagifyAsyncTool")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


# ==================== Tool Schema Functions ====================

def add_rag_query_tool_schema(tool_schemas):
    """
    Add rag_query tool schema for querying LightRAG knowledge base.
    
    Based on LightRAG API POST /query QueryRequest schema.
    Reference: https://github.com/HKUDS/LightRAG/blob/main/lightrag/api/routers/query_routes.py
    """
    import mcp.types as types

    tool_schema = types.Tool(_meta={"run_in_cloud": False},
        name="rag_query",
        description="Query LightRAG knowledge base using RAG. Retrieves relevant documents and generates natural language answers.",
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": ["query"],
                    "properties": {
                        "query": {
                            "type": "string",
                            "minLength": 3,
                            "description": "The query text to search for in the knowledge base."
                        },
                        "mode": {
                            "type": "string",
                            "enum": ["local", "global", "hybrid", "naive", "mix", "bypass"],
                            "default": "mix",
                            "description": "Query mode: local (entity-focused), global (relationship patterns), hybrid (combined), naive (vector search), mix (knowledge graph + vector), bypass (direct LLM)."
                        },
                        "only_need_context": {
                            "type": "boolean",
                            "default": False,
                            "description": "If true, only returns the retrieved context without generating a response."
                        },
                        "only_need_prompt": {
                            "type": "boolean",
                            "default": False,
                            "description": "If true, only returns the generated prompt without producing a response."
                        },
                        "response_type": {
                            "type": "string",
                            "description": "Defines the response format. Examples: 'Multiple Paragraphs', 'Single Paragraph', 'Bullet Points'."
                        },
                        "top_k": {
                            "type": "integer",
                            "minimum": 1,
                            "description": "Number of top items to retrieve. Represents entities in 'local' mode and relationships in 'global' mode."
                        },
                        "chunk_top_k": {
                            "type": "integer",
                            "minimum": 1,
                            "description": "Number of text chunks to retrieve from vector search."
                        },
                        "max_entity_tokens": {
                            "type": "integer",
                            "minimum": 1,
                            "description": "Maximum tokens for entity context."
                        },
                        "max_relation_tokens": {
                            "type": "integer",
                            "minimum": 1,
                            "description": "Maximum tokens for relationship context."
                        },
                        "max_total_tokens": {
                            "type": "integer",
                            "minimum": 1,
                            "description": "Maximum total tokens budget for query context."
                        },
                        "hl_keywords": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "High-level keywords to prioritize in retrieval."
                        },
                        "ll_keywords": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Low-level keywords to refine retrieval focus."
                        },
                        "conversation_history": {
                            "type": "array",
                            "description": "Past conversation history for context. Format: [{'role': 'user/assistant', 'content': 'message'}].",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "role": {"type": "string", "enum": ["user", "assistant"]},
                                    "content": {"type": "string"}
                                },
                                "required": ["role", "content"]
                            }
                        },
                        "user_prompt": {
                            "type": "string",
                            "description": "Custom user prompt to guide LLM response generation (does not affect retrieval)."
                        },
                        "enable_rerank": {
                            "type": "boolean",
                            "default": True,
                            "description": "Enable reranking for retrieved text chunks."
                        },
                        "include_references": {
                            "type": "boolean",
                            "default": True,
                            "description": "If true, includes reference list in responses."
                        },
                        "include_chunk_content": {
                            "type": "boolean",
                            "default": False,
                            "description": "If true, includes actual chunk text content in references."
                        },
                        "workspace": {
                            "type": "string",
                            "description": "Optional LightRAG workspace (tenant) to query. Use the same name the documents were ingested under (e.g. 'customer_service', 'product_details'). Omit to query the server's default workspace."
                        }
                    }
                }
            }
        },
    )

    tool_schemas.append(tool_schema)


def add_wait_for_rag_completion_tool_schema(tool_schemas):
    """
    Add wait_for_rag_completion tool schema for synchronous waiting on RAG ingestion.
    """
    import mcp.types as types

    tool_schema = types.Tool(_meta={"run_in_cloud": False},
        name="wait_for_rag_completion",
        description="Wait for RAG ingestion to complete by polling track_id status. Blocks until all documents are processed/failed or timeout. Use this when you need to query the documents immediately after ingestion. Timeout is auto-calculated: (file_size_kb / 10) * 60 + 180 seconds.",
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": ["track_id"],
                    "properties": {
                        "track_id": {
                            "type": "string",
                            "description": "The track_id returned from ragify or ragify_async tool."
                        },
                        "poll_interval_seconds": {
                            "type": "integer",
                            "default": 15,
                            "minimum": 5,
                            "description": "How often to check status (default: 15 seconds)."
                        },
                        "timeout_seconds": {
                            "type": "integer",
                            "minimum": 60,
                            "description": "Max time to wait in seconds. If not provided, defaults to 600 seconds (10 minutes)."
                        },
                        "max_retries": {
                            "type": "integer",
                            "default": 3,
                            "minimum": 1,
                            "description": "Max consecutive poll failures before giving up (default: 3)."
                        },
                        "workspace": {
                            "type": "string",
                            "description": "Optional LightRAG workspace (tenant). Must match the workspace that was used when the track_id was created by ragify / ragify_async."
                        }
                    }
                }
            }
        },
    )

    tool_schemas.append(tool_schema)


def add_ragify_async_tool_schema(tool_schemas):
    """
    Add ragify_async tool schema for async RAG ingestion with completion notification.
    """
    import mcp.types as types

    tool_schema = types.Tool(_meta={"run_in_cloud": False},
        name="ragify_async",
        description="Ingest documents into LightRAG with optional async completion notification. Fire-and-forget by default. Set on_complete=true to receive a notification in the task queue when processing finishes. Timeout is auto-calculated from file size: (size_kb / 10) * 60 + 180 seconds.",
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "properties": {
                        "file_paths": {
                            "type": "array",
                            "description": "List of file paths to upload and index.",
                            "items": {"type": "string"}
                        },
                        "text": {
                            "type": "string",
                            "description": "Direct text content to insert (alternative to file_paths)."
                        },
                        "file_source": {
                            "type": "string",
                            "description": "Optional source identifier for the inserted text."
                        },
                        "on_complete": {
                            "type": "boolean",
                            "default": False,
                            "description": "If true, monitor completion and send notification to task queue when done."
                        },
                        "notify_task_id": {
                            "type": "string",
                            "description": "Target task ID for completion notification. If task ends, falls back to chat task."
                        },
                        "notify_chat_id": {
                            "type": "string",
                            "description": "Fallback chat ID for notification if original task is ended."
                        },
                        "timeout_seconds": {
                            "type": "integer",
                            "minimum": 60,
                            "description": "Max time to monitor for completion. Auto-calculated from file size if not provided."
                        },
                        "poll_interval_seconds": {
                            "type": "integer",
                            "default": 15,
                            "minimum": 5,
                            "description": "How often to check status when monitoring (default: 15 seconds)."
                        },
                        "notification_message": {
                            "type": "string",
                            "description": "Custom message to include in the completion notification."
                        },
                        "workspace": {
                            "type": "string",
                            "description": "Optional LightRAG workspace (tenant) name for data isolation. Use the same name consistently per category. The background completion monitor will poll track status scoped to this workspace."
                        }
                    }
                }
            }
        },
    )

    tool_schemas.append(tool_schema)


def add_rag_replace_document_tool_schema(tool_schemas):
    """Add ``rag_replace_document`` tool schema.

    See :func:`rag_replace_document` for semantics. The tool runs locally
    (``run_in_cloud=False``) because it touches the local LightRAG
    server's filesystem-backed workspace.
    """
    import mcp.types as types

    tool_schema = types.Tool(_meta={"run_in_cloud": False},
        name="rag_replace_document",
        description=(
            "Re-ingest a file into LightRAG after it has been edited on disk. "
            "Deletes any existing copies in the workspace whose filename matches "
            "(by basename), then uploads the new version. Use this — NOT plain "
            "ragify — when a source file's contents have changed; otherwise the "
            "knowledge graph keeps stale entries from the previous version. "
            "Re-ingest is asynchronous on the server side: the tool returns as "
            "soon as the upload is queued. Pair with wait_for_rag_completion if "
            "you need the new contents query-ready before continuing."
        ),
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": ["path"],
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Absolute local path to the NEW version of the file to ingest.",
                        },
                        "workspace": {
                            "type": "string",
                            "description": (
                                "Optional LightRAG workspace (tenant). Both the "
                                "lookup of old copies and the re-ingest are "
                                "scoped to this workspace. LEAVE EMPTY for the "
                                "server's default workspace."
                            ),
                        },
                        "match_basename": {
                            "type": "boolean",
                            "default": True,
                            "description": (
                                "When true (default), match old copies by "
                                "filename only — handy when the new file lives "
                                "in a different folder than the original ingest "
                                "path. Set false to require an exact file_path "
                                "string match instead."
                            ),
                        },
                    },
                }
            },
        },
    )

    tool_schemas.append(tool_schema)