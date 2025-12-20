"""
Centralized configuration for local MCP endpoints.

- Prefer host 127.0.0.1 by default
- Port defaults to 4668, can be overridden per call or via env ECAN_LOCAL_SERVER_PORT
- Also support env ECAN_LOCAL_SERVER_HOST to override host

All returned URLs avoid trailing slashes for endpoint roots.
"""
from __future__ import annotations
import os
from typing import Optional

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 4668


def get_local_host(default: str = DEFAULT_HOST) -> str:
    return os.getenv("ECAN_LOCAL_SERVER_HOST", default)


def get_local_port(default: int = DEFAULT_PORT) -> int:
    val = os.getenv("ECAN_LOCAL_SERVER_PORT")
    if val and val.isdigit():
        try:
            return int(val)
        except ValueError:
            pass
    return default


def base_url(host: Optional[str] = None, port: Optional[int] = None) -> str:
    h = host or get_local_host()
    p = port or get_local_port()
    return f"http://{h}:{p}"


def mcp_http_base(host: Optional[str] = None, port: Optional[int] = None) -> str:
    # Streamable HTTP clients expect the base endpoint to accept POST at the root; trailing slash is safest.
    return base_url(host, port) + "/mcp/"


def mcp_sse_url(host: Optional[str] = None, port: Optional[int] = None) -> str:
    return base_url(host, port) + "/sse"


def mcp_messages_url(host: Optional[str] = None, port: Optional[int] = None) -> str:
    # Internal transport route (server expects trailing slash); expose only if needed for tests
    return base_url(host, port) + "/messages/"


def mcp_stream_messages_url(host: Optional[str] = None, port: Optional[int] = None) -> str:
    # Internal transport route (server expects trailing slash); expose only if needed for tests
    return base_url(host, port) + "/mcp_messages/"

