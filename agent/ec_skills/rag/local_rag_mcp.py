from utils.logger_helper import get_traceback
from utils.logger_helper import logger_helper as logger

def ragify_tool(mainwin, args):
    try:
        rag_result = None
        if args['input']:
            logger.debug(f"[MCP][RAGIFY DOCs]: {args['input']}")

        msg = "completed ragify fileds"
        result = [TextContent(type="text", text=msg)]
        result.meta = {"rag_result": rag_result}
        return [result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorRagifyTool")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]



def rag_query_tool(mainwin, args):
    try:
        answer = ""
        if args['input']:
            logger.debug(f"[MCP][RAG QUERY]: {args['input']}")

        msg = "completed rag query"
        result = [TextContent(type="text", text=msg)]
        result.meta = {"answer": answer}
        return [result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorRagQueryTool")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]

def add_ragify_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="ragify_tool",
        description="use RAG to vectorized target documents or direct content, refer to: https://github.com/HKUDS/RAG-Anything/tree/main/examples",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["file_paths", "content_list", "output_dir", "api_key", "base_url", "working_dir", "parser", "config"],
                    "properties": {
                        "file_paths": {
                            "type": "array",
                            "description": "pathes of the files to be ragified (stored in vector DB)",
                            "items": {"type": "string"}
                        },
                        "content_list": {
                            "type": "array",
                            "description": "direct content to ragify. refer to: https://github.com/HKUDS/RAG-Anything/blob/main/examples/insert_content_list_example.py#L94",
                            "items": {"type": "object"}
                        },
                        "output_dir": {
                            "type": "string",
                            "description": "path of the output directory",
                        },
                        "api_key": {
                            "type": "string",
                            "description": "api key for embedding model provider",
                        },
                        "base_url": {
                            "type": "string",
                            "description": "base url for embedding model provider",
                        },
                        "working_dir": {
                            "type": "string",
                            "description": "working directory",
                        },
                        "parser": {
                            "type": "string",
                            "description": "name of the parser function to use",
                        },
                        "config": {
                            "type": "object",
                            "required": ["max_token_size", "embedding_dim", "embedding_model", "max_workers", "context_window", "context_mode", "timeout_per_file", "parsing_method", "enable_image_processing", "enable_table_processing", "enable_equation_processing", "display_content_stats", "recursive", "show_progress", "skip_installation_check"],
                            "properties": {
                                "max_token_size": {"type": "integer"},
                                "embedding_dim": {"type": "integer"},
                                "context_window": {"type": "integer"},
                                "max_workers": {"type": "integer"},
                                "context_mode": {"type": "string"},
                                "timeout_per_file": {"type": "integer", "description": "timeout per file in seconds"},
                                "embedding_model": {"type": "string"},
                                "parsing_method": {"type": "string"},
                                "enable_image_processing": {"type": "boolean"},
                                "enable_table_processing": {"type": "boolean"},
                                "enable_equation_processing": {"type": "boolean"},
                                "display_content_stats": {"type": "boolean"},
                                "recursive": {"type": "boolean"},
                                "show_progress": {"type": "boolean"},
                                "skip_installation_check": {"type": "boolean"}
                            }
                        },
                    },
                }
            }
        },
    )

    tool_schemas.append(tool_schema)


def add_rag_query_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="rag_query_tool",
        description="use RAG to query vector DB and retrieve relevant documents and return answer in natural language",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["query", "multimodal_content", "mode"],
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "agent id",
                        },
                        "multimodal_content": {
                            "type": "array",
                            "description": "a list of multimodal content, refer to: https://github.com/HKUDS/RAG-Anything/blob/main/raganything/query.py",
                            "items": {
                                "type": "object",
                                "description": "this will include, type, latex, caption",
                            }
                        },
                        "mode": {
                            "type": "string",
                            "description": "query mode, local/global/hybrid/naive/mix",
                        }
                    },
                }
            }
        },
    )

    tool_schemas.append(tool_schema)