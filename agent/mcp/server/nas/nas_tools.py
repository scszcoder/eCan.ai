"""MCP tools for reading/writing the UGREEN NAS over SMB.

Thin handlers over ``agent.ec_skills.nas.ugreen_nas``; each returns
``[TextContent]`` as the MCP server expects. All paths are relative to the NAS
base folder (``ECAN_NAS_BASE``, default ``chips/microchip``). Credentials are
resolved by the engine at runtime -- never passed in by the caller.
"""
from __future__ import annotations

import base64
import json

from mcp.types import TextContent

from utils.logger_helper import logger_helper as logger


def _text(obj) -> list:
    return [TextContent(type="text", text=obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False))]


def _err(msg: str) -> list:
    logger.error(f"[nas_tools] {msg}")
    return [TextContent(type="text", text=f"Error: {msg}")]


async def nas_save_text(mainwin, args):
    """Write UTF-8 text to a file on the NAS. input: {remote_path, content}."""
    try:
        inp = args["input"]
        from agent.ec_skills.nas import ugreen_nas as nas
        res = nas.nas_write_text(inp["remote_path"], inp.get("content", ""))
        return _text({"ok": True, **res})
    except Exception as e:
        return _err(f"nas_save_text failed: {e}")


async def nas_upload_file(mainwin, args):
    """Upload a local file to the NAS. input: {local_path, remote_path?}."""
    try:
        inp = args["input"]
        from agent.ec_skills.nas import ugreen_nas as nas
        res = nas.nas_upload(inp["local_path"], inp.get("remote_path") or None)
        return _text({"ok": True, **res})
    except Exception as e:
        return _err(f"nas_upload_file failed: {e}")


async def nas_read_file(mainwin, args):
    """Read a file from the NAS. input: {remote_path, mode?: text|base64}."""
    try:
        inp = args["input"]
        from agent.ec_skills.nas import ugreen_nas as nas
        data = nas.nas_read_bytes(inp["remote_path"])
        mode = inp.get("mode", "text")
        if mode == "base64":
            return _text({"ok": True, "mode": "base64", "content": base64.b64encode(data).decode("ascii")})
        return _text({"ok": True, "mode": "text", "content": data.decode(inp.get("encoding", "utf-8"), errors="replace")})
    except Exception as e:
        return _err(f"nas_read_file failed: {e}")


async def nas_list_dir(mainwin, args):
    """List a directory on the NAS. input: {remote_dir?}."""
    try:
        inp = args.get("input", {}) or {}
        from agent.ec_skills.nas import ugreen_nas as nas
        entries = nas.nas_list(inp.get("remote_dir", ""))
        return _text({"ok": True, "dir": inp.get("remote_dir", ""), "entries": entries})
    except Exception as e:
        return _err(f"nas_list_dir failed: {e}")


async def nas_delete_file(mainwin, args):
    """Delete a file on the NAS. input: {remote_path}."""
    try:
        inp = args["input"]
        from agent.ec_skills.nas import ugreen_nas as nas
        res = nas.nas_delete(inp["remote_path"])
        return _text({"ok": True, **res})
    except Exception as e:
        return _err(f"nas_delete_file failed: {e}")
