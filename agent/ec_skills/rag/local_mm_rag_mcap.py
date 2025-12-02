from utils.logger_helper import get_traceback
from utils.logger_helper import logger_helper as logger
from mcp.types import TextContent
from knowledge.lightrag_client import get_client


async def mm_ragify(mainwin, args):
    """
    MCP Tool: Ingest documents into RAG Anything for RAG indexing.

    Supports two modes:
    1. File upload: Upload files from file_paths to RAG Anything
    2. Text insert: Directly insert text content into RAG Anything

    Based on RAG Anything API:
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

        # Initialize client
        client = get_client()

        # Mode 1: File upload
        if file_paths:
            rag_result = client.ingest_files(file_paths)
            logger.info(f"[MCP][MM_RAGIFY] File ingestion result: {rag_result}")
            msg = f"Ingested {len(file_paths)} file(s)"
        # Mode 2: Text insert
        elif text:
            metadata = {"file_source": file_source} if file_source else None
            rag_result = client.insert_text(text, metadata)
            logger.info(f"[MCP][MM_RAGIFY] Text insert result: {rag_result}")
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
        err_trace = get_traceback(e, "ErrorMMRagifyTool")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def mm_rag_query(mainwin, args):
    """
    MCP Tool: Query RAG Anything knowledge base.

    Based on RAG Anything API POST /query:
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

        logger.debug(f"[MCP][MM_RAG_QUERY]: {input_data}")

        # Extract query (required)
        query_text = input_data.get("query")
        if not query_text or len(query_text.strip()) < 3:
            return [TextContent(type="text", text="Error: Query must be at least 3 characters")]

        # Initialize client
        client = get_client()

        # Build options from input - map to LightRAG QueryRequest parameters
        options = {}

        # Mode: local, global, hybrid, naive, mix, bypass
        mode = input_data.get("mode", "mix")
        if mode in ["local", "global", "hybrid", "naive", "mix", "bypass"]:
            options["mode"] = mode
        else:
            options["mode"] = "mix"  # Default to mix

        # All optional parameters from LightRAG QueryRequest schema
        OPTIONAL_PARAMS = [
            "only_need_context",  # bool
            "only_need_prompt",  # bool
            "response_type",  # str
            "top_k",  # int
            "chunk_top_k",  # int
            "max_entity_tokens",  # int
            "max_relation_tokens",  # int
            "max_total_tokens",  # int
            "hl_keywords",  # list[str]
            "ll_keywords",  # list[str]
            "conversation_history",  # list[dict]
            "user_prompt",  # str
            "enable_rerank",  # bool
            "include_references",  # bool
            "include_chunk_content",  # bool
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

        # Execute query
        response = client.query(query_text.strip(), options)

        if response.get("status") == "success":
            data = response.get("data", {})
            # LightRAG returns {"response": "...", "references": [...]}
            if isinstance(data, dict):
                answer = data.get("response", str(data))
            else:
                answer = str(data)
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
        err_trace = get_traceback(e, "ErrorMMRagQueryTool")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


def add_mm_ragify_tool_schema(tool_schemas):
    """
    Add ragify tool schema for document ingestion into LightRAG.

    Based on LightRAG API:
    - POST /documents/upload - Upload files for indexing
    - POST /documents/text - Insert text directly

    Reference: https://github.com/HKUDS/LightRAG/blob/main/lightrag/api/routers/document_routes.py
    """
    import mcp.types as types

    tool_schema = types.Tool(
        name="mm_ragify",
        description="<category>Multi-Modal RAG</category><sub-category>Store</sub-category>Ingest multi-modal documents, including image, video, audio, files into RAGAnything for RAG indexing. Supports file upload or direct text insertion. Returns a track_id for monitoring processing status.",
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
                        }
                    }
                }
            }
        },
    )

    tool_schemas.append(tool_schema)


def add_mm_rag_query_tool_schema(tool_schemas):
    """
    Add rag_query tool schema for querying LightRAG knowledge base.

    Based on LightRAG API POST /query QueryRequest schema.
    Reference: https://github.com/HKUDS/LightRAG/blob/main/lightrag/api/routers/query_routes.py
    """
    import mcp.types as types

    tool_schema = types.Tool(
        name="mm_rag_query",
        description="<category>Multi-Modal RAG</category><sub-category>Query</sub-category>Query RAG Anything knowledge base using RAG. Retrieves relevant documents and generates natural language answers.",
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
                        }
                    }
                }
            }
        },
    )

    tool_schemas.append(tool_schema)