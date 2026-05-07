"""SQL MCP tools for structured data the agent should NOT route through RAG.

Why a dedicated tool?
---------------------
Sales / inventory / shipment numbers and other transactional data have hard
correctness requirements: a vector-recall RAG can paraphrase a row, miss a
filter, or quietly drop a JOIN, which is unacceptable for a customer-facing
quote or stock check. Instead, the agent calls an explicit SQL tool that:

  * Runs against a real database (SQLite by default; the same code can be
    pointed at Postgres / MySQL by overriding ``_open_connection``).
  * Restricts the agent to read-only ``SELECT`` queries (no INSERT/UPDATE/
    DELETE/DDL/PRAGMA), so a bad LLM call can't mutate the books.
  * Caps row count and execution time so the agent can't accidentally fetch
    a million rows into the conversation context.
  * Returns deterministic JSON (columns + rows) the LLM or downstream code
    can parse without recall errors.

Configuration
-------------
The DB path is read in this priority order:
  1. ``input.db_path`` (per-call override, intended for testing).
  2. Environment variable ``ECAN_SALES_DB_PATH``.
  3. Fallback: ``<repo>/data/sales.db``.

Setting up a real sales DB is left to the integrator (it usually means
creating a SQLite file or pointing this module at the existing ERP read
replica). The tool is intentionally a thin, conservative wrapper.
"""

from __future__ import annotations

import os
import re
import sqlite3
import time
from typing import Any, Dict, List, Optional, Tuple

from utils.logger_helper import get_traceback
from utils.logger_helper import logger_helper as logger
from mcp.types import TextContent


# ---------------------------------------------------------------------------
# Safety helpers
# ---------------------------------------------------------------------------

# Statements that mutate state or reach outside the query engine. Anything
# matching these (case-insensitive, on a word boundary) is rejected before
# the query reaches the DB driver.
_FORBIDDEN_KEYWORDS: Tuple[str, ...] = (
    "insert",
    "update",
    "delete",
    "drop",
    "alter",
    "truncate",
    "create",
    "replace",
    "merge",
    "grant",
    "revoke",
    "attach",
    "detach",
    "pragma",
    "vacuum",
    "reindex",
    "analyze",
)

_DEFAULT_ROW_LIMIT = 200
_HARD_ROW_LIMIT = 5000
_DEFAULT_TIMEOUT_SECONDS = 10


def _strip_sql_comments(sql: str) -> str:
    """Remove ``--`` line comments and ``/* ... */`` block comments.

    Done before keyword scanning so an attacker can't smuggle ``DELETE``
    inside a comment. Strings keep their content intact (we don't mask
    string literals because forbidden keywords inside a string literal
    can still only be useful if the parser reaches them, which it won't
    for a SELECT-only check)."""
    no_block = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    no_line = re.sub(r"--[^\n]*", " ", no_block)
    return no_line


def _validate_select_only(sql: str) -> Optional[str]:
    """Return ``None`` if the SQL is a safe single ``SELECT``/``WITH``,
    otherwise return a human-readable rejection reason."""
    if not sql or not sql.strip():
        return "SQL is empty"

    cleaned = _strip_sql_comments(sql).strip().rstrip(";").strip()
    if not cleaned:
        return "SQL is empty after stripping comments"

    # Reject multi-statement payloads (``SELECT 1; DELETE ...``).
    if ";" in cleaned:
        return "Only a single statement is allowed (no ';' in the middle of the SQL)"

    head = cleaned.split(None, 1)[0].lower()
    if head not in ("select", "with"):
        return f"Only SELECT/WITH queries are allowed; got '{head.upper()}'"

    lowered = cleaned.lower()
    for kw in _FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{re.escape(kw)}\b", lowered):
            return f"Forbidden keyword '{kw.upper()}' found in SQL"

    return None


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

def _resolve_db_path(input_data: Dict[str, Any]) -> str:
    """Decide which SQLite file to open. See module docstring."""
    override = (input_data.get("db_path") or "").strip()
    if override:
        return override

    env_path = (os.environ.get("ECAN_SALES_DB_PATH") or "").strip()
    if env_path:
        return env_path

    # Repo-local fallback so a fresh checkout has a deterministic location.
    repo_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, os.pardir)
    )
    return os.path.join(repo_root, "data", "sales.db")


def _open_connection(db_path: str, timeout_seconds: int) -> sqlite3.Connection:
    """Open the DB read-only. Override this if you switch to Postgres."""
    if not os.path.exists(db_path):
        raise FileNotFoundError(
            f"Sales database not found at '{db_path}'. Set ECAN_SALES_DB_PATH "
            "or pass `db_path` in the tool input."
        )

    # SQLite read-only URI prevents accidental writes even if a SELECT is
    # somehow misclassified.
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=timeout_seconds)
    conn.row_factory = sqlite3.Row
    return conn


def _run_select(
    conn: sqlite3.Connection,
    sql: str,
    params: Optional[List[Any]],
    row_limit: int,
) -> Tuple[List[str], List[Dict[str, Any]], bool]:
    """Execute the SELECT and return ``(columns, rows, truncated)``."""
    cur = conn.cursor()
    cur.execute(sql, params or [])
    columns = [d[0] for d in cur.description] if cur.description else []

    rows: List[Dict[str, Any]] = []
    truncated = False
    for i, raw in enumerate(cur):
        if i >= row_limit:
            truncated = True
            break
        rows.append({col: raw[col] for col in columns})

    return columns, rows, truncated


# ---------------------------------------------------------------------------
# MCP tool
# ---------------------------------------------------------------------------

async def query_sales_db(mainwin, args):
    """MCP tool entry point. See ``add_query_sales_db_tool_schema`` for the
    public schema documentation."""
    try:
        input_data = (args or {}).get("input", {}) or {}
        if not isinstance(input_data, dict):
            return [TextContent(type="text", text="Error: input must be an object")]

        sql: str = (input_data.get("sql") or "").strip()
        params = input_data.get("params") or []
        if not isinstance(params, list):
            return [TextContent(type="text", text="Error: 'params' must be an array")]

        row_limit_raw = input_data.get("row_limit", _DEFAULT_ROW_LIMIT)
        try:
            row_limit = int(row_limit_raw)
        except (TypeError, ValueError):
            row_limit = _DEFAULT_ROW_LIMIT
        row_limit = max(1, min(row_limit, _HARD_ROW_LIMIT))

        timeout_raw = input_data.get("timeout_seconds", _DEFAULT_TIMEOUT_SECONDS)
        try:
            timeout_seconds = int(timeout_raw)
        except (TypeError, ValueError):
            timeout_seconds = _DEFAULT_TIMEOUT_SECONDS
        timeout_seconds = max(1, min(timeout_seconds, 60))

        # 1. SQL safety gate.
        rejection = _validate_select_only(sql)
        if rejection:
            logger.warning(f"[MCP][query_sales_db] Rejected SQL: {rejection}")
            result = TextContent(
                type="text",
                text=f"Error: {rejection}",
            )
            result.meta = {"status": "error", "message": rejection}
            return [result]

        # 2. Resolve DB path.
        db_path = _resolve_db_path(input_data)
        logger.info(
            f"[MCP][query_sales_db] db={db_path!r} row_limit={row_limit} "
            f"timeout={timeout_seconds}s sql={sql[:120]!r}"
        )

        # 3. Run the query.
        started = time.time()
        try:
            conn = _open_connection(db_path, timeout_seconds)
        except FileNotFoundError as fnf:
            msg = str(fnf)
            logger.error(f"[MCP][query_sales_db] {msg}")
            result = TextContent(type="text", text=f"Error: {msg}")
            result.meta = {"status": "error", "message": msg, "db_path": db_path}
            return [result]

        try:
            columns, rows, truncated = _run_select(conn, sql, params, row_limit)
        finally:
            try:
                conn.close()
            except Exception:
                pass

        elapsed_ms = int((time.time() - started) * 1000)

        # 4. Render a compact text answer for the LLM AND attach structured
        #    meta so build_node / downstream code can read the rows.
        if not rows:
            text_answer = "No rows matched."
        else:
            preview_n = min(len(rows), 20)
            preview_lines = [" | ".join(columns)]
            preview_lines.append(" | ".join("---" for _ in columns))
            for r in rows[:preview_n]:
                preview_lines.append(
                    " | ".join("" if r[c] is None else str(r[c]) for c in columns)
                )
            extra = ""
            if truncated:
                extra = (
                    f"\n... (truncated to first {row_limit} rows; raise `row_limit` "
                    "or refine the query if you need more)."
                )
            elif len(rows) > preview_n:
                extra = f"\n... ({len(rows) - preview_n} more rows in `meta.rows`)"
            text_answer = "\n".join(preview_lines) + extra

        result = TextContent(type="text", text=text_answer)
        result.meta = {
            "status": "success",
            "db_path": db_path,
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "truncated": truncated,
            "elapsed_ms": elapsed_ms,
        }
        return [result]
    except sqlite3.OperationalError as e:
        msg = f"SQL execution error: {e}"
        logger.error(f"[MCP][query_sales_db] {msg}")
        result = TextContent(type="text", text=f"Error: {msg}")
        result.meta = {"status": "error", "message": msg}
        return [result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorQuerySalesDbTool")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


# ---------------------------------------------------------------------------
# Schema registration
# ---------------------------------------------------------------------------

def add_query_sales_db_tool_schema(tool_schemas):
    """Register the ``query_sales_db`` MCP tool schema."""
    import mcp.types as types

    tool_schema = types.Tool(
        _meta={"run_in_cloud": False},
        name="query_sales_db",
        description=(
            "Run a read-only SQL query against the structured sales / inventory "
            "database. Use this INSTEAD of rag_query whenever the user asks for "
            "exact numbers, IDs, prices, stock levels, order status, shipment "
            "tracking, customer records, or any data where paraphrasing would be "
            "wrong. Only SELECT / WITH queries are accepted; INSERT/UPDATE/DELETE/"
            "DDL are blocked. The tool returns columns + rows as structured "
            "metadata plus a Markdown-table preview as text."
        ),
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": ["sql"],
                    "properties": {
                        "sql": {
                            "type": "string",
                            "minLength": 6,
                            "description": (
                                "A single SELECT (or WITH ... SELECT) statement. "
                                "Use parameter placeholders ('?') for any user-"
                                "provided values and pass them via `params`. "
                                "Example: 'SELECT order_id, total FROM orders "
                                "WHERE customer_id = ? ORDER BY created_at DESC'."
                            ),
                        },
                        "params": {
                            "type": "array",
                            "description": (
                                "Positional bind parameters for '?' placeholders "
                                "in the SQL. Strongly preferred over string-"
                                "interpolating user input into the query."
                            ),
                            "items": {
                                "anyOf": [
                                    {"type": "string"},
                                    {"type": "number"},
                                    {"type": "boolean"},
                                    {"type": "null"},
                                ]
                            },
                        },
                        "row_limit": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": _HARD_ROW_LIMIT,
                            "default": _DEFAULT_ROW_LIMIT,
                            "description": (
                                f"Max rows to return (default {_DEFAULT_ROW_LIMIT}, "
                                f"hard cap {_HARD_ROW_LIMIT})."
                            ),
                        },
                        "timeout_seconds": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 60,
                            "default": _DEFAULT_TIMEOUT_SECONDS,
                            "description": (
                                "Per-query timeout in seconds (default "
                                f"{_DEFAULT_TIMEOUT_SECONDS}, max 60)."
                            ),
                        },
                        "db_path": {
                            "type": "string",
                            "description": (
                                "Optional override for the SQLite database file "
                                "path. Normally leave empty and let the server "
                                "use the ECAN_SALES_DB_PATH environment variable."
                            ),
                        },
                    },
                }
            },
        },
    )

    tool_schemas.append(tool_schema)
