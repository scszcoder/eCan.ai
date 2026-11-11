r"""``ec_store``: the seller's local data, one SQLite file per tenant (``ec_data.db``).

Holds versioned KB records (store profiles, product facts, thresholds, user instructions,
learnings), the normalized report tables, and the decision log. Nothing here leaves the
machine; a cloud copy is the owner's choice and goes through ``snapshot``.

Location: ``$ECAN_ECOM_HOME`` or ``~/.ecan/ecom``, then ``<tenant_id>/ec_data.db``.

Report tables are plain SQLite tables named after the canonical table (``gads_search_term_rows``
...), each row carrying ``_store_id``, ``_source_file``, ``_ingested_at``, ``_currency``, ``_tz``.
Writing a batch replaces that store's rows for the same dates (or, for tables without a date,
the same source file), so downloading the last 7 days again never doubles anything.

``query`` is the only way an LLM step gets numbers: it opens the file read-only and refuses
anything but SELECT.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

DEFAULT_TENANT = "local"
_META_COLS = ("_store_id", "_source_file", "_ingested_at", "_currency", "_tz")
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def home() -> Path:
    return Path(os.environ.get("ECAN_ECOM_HOME") or Path.home() / ".ecan" / "ecom")


def db_path(tenant_id: str = DEFAULT_TENANT) -> Path:
    if not _IDENT.match(tenant_id or ""):
        raise ValueError(f"bad tenant id {tenant_id!r}")
    return home() / tenant_id / "ec_data.db"


def _ident(name: str) -> str:
    if not _IDENT.match(name or ""):
        raise ValueError(f"bad table or column name {name!r}")
    return name


_SCHEMA = """
CREATE TABLE IF NOT EXISTS kb (
    collection TEXT NOT NULL, key TEXT NOT NULL, version INTEGER NOT NULL,
    value TEXT NOT NULL, source TEXT, updated_at TEXT NOT NULL,
    PRIMARY KEY (collection, key, version));
CREATE TABLE IF NOT EXISTS decision_log (
    id TEXT PRIMARY KEY, kind TEXT NOT NULL, store_id TEXT, record TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS report_tables (
    name TEXT PRIMARY KEY, columns TEXT NOT NULL, updated_at TEXT NOT NULL);
"""


class Store:
    def __init__(self, tenant_id: str = DEFAULT_TENANT, path: Optional[Path] = None):
        self.tenant_id = tenant_id
        self.path = Path(path) if path else db_path(tenant_id)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.execute("PRAGMA journal_mode=WAL")
            c.executescript(_SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    # ---- KB records (versioned; a put never overwrites an older version) ----
    def kb_put(self, collection: str, key: str, value: Any, source: str = "") -> int:
        with self._conn() as c:
            row = c.execute("SELECT MAX(version) FROM kb WHERE collection=? AND key=?", (collection, key)).fetchone()
            version = (row[0] or 0) + 1
            c.execute("INSERT INTO kb VALUES (?,?,?,?,?,?)",
                      (collection, key, version, json.dumps(value, ensure_ascii=False), source, now_iso()))
        return version

    def kb_get(self, collection: str, key: str, version: Optional[int] = None) -> Optional[Dict[str, Any]]:
        sql = "SELECT * FROM kb WHERE collection=? AND key=?"
        args: List[Any] = [collection, key]
        if version is not None:
            sql += " AND version=?"
            args.append(version)
        sql += " ORDER BY version DESC LIMIT 1"
        with self._conn() as c:
            row = c.execute(sql, args).fetchone()
        if not row:
            return None
        return {"collection": collection, "key": key, "version": row["version"], "value": json.loads(row["value"]),
                "source": row["source"], "updated_at": row["updated_at"]}

    def kb_list(self, collection: str) -> List[Dict[str, Any]]:
        """The newest version of every key in ``collection``."""
        with self._conn() as c:
            rows = c.execute("SELECT k.* FROM kb k JOIN (SELECT key, MAX(version) v FROM kb WHERE collection=? "
                             "GROUP BY key) m ON k.key=m.key AND k.version=m.v WHERE k.collection=? ORDER BY k.key",
                             (collection, collection)).fetchall()
        return [{"collection": collection, "key": r["key"], "version": r["version"],
                 "value": json.loads(r["value"]), "source": r["source"], "updated_at": r["updated_at"]} for r in rows]

    # ---- report tables ----
    def write_rows(self, table: str, rows: List[Dict[str, Any]], *, store_id: str, source_file: str,
                   currency: str = "", tz: str = "", date_col: Optional[str] = "date") -> int:
        _ident(table)
        if not rows:
            return 0
        cols = list(dict.fromkeys(k for r in rows for k in r))
        for col in cols:
            _ident(col)
        ingested = now_iso()
        with self._conn() as c:
            known = self._ensure_table(c, table, cols)
            has_date = date_col in known and all(r.get(date_col) for r in rows)
            if has_date:
                dates = sorted({str(r[date_col]) for r in rows})
                c.execute(f"DELETE FROM {table} WHERE _store_id=? AND {date_col} IN "
                          f"({','.join('?' * len(dates))})", [store_id, *dates])
            else:
                c.execute(f"DELETE FROM {table} WHERE _store_id=? AND _source_file=?", (store_id, source_file))
            all_cols = [*cols, *_META_COLS]
            c.executemany(f"INSERT INTO {table} ({','.join(all_cols)}) VALUES ({','.join('?' * len(all_cols))})",
                          [[_cell(r.get(k)) for k in cols] + [store_id, source_file, ingested, currency, tz]
                           for r in rows])
        return len(rows)

    def _ensure_table(self, c: sqlite3.Connection, table: str, cols: List[str]) -> List[str]:
        row = c.execute("SELECT columns FROM report_tables WHERE name=?", (table,)).fetchone()
        known = json.loads(row[0]) if row else []
        if not row:
            c.execute(f"CREATE TABLE {table} ({','.join([*cols, *_META_COLS])})")
            known = list(cols)
        else:
            for col in cols:
                if col not in known:
                    c.execute(f"ALTER TABLE {table} ADD COLUMN {col}")
                    known.append(col)
        c.execute("INSERT OR REPLACE INTO report_tables VALUES (?,?,?)", (table, json.dumps(known), now_iso()))
        return known

    def tables(self) -> Dict[str, List[str]]:
        with self._conn() as c:
            return {r["name"]: json.loads(r["columns"]) for r in c.execute("SELECT * FROM report_tables")}

    def query(self, sql: str, params: Iterable[Any] = (), limit: int = 500) -> Dict[str, Any]:
        """Read-only SQL. Anything that would write, attach or change settings is refused."""
        if not re.match(r"^\s*(select|with)\b", sql or "", re.I):
            raise PermissionError("only SELECT queries are allowed")
        conn = sqlite3.connect(f"file:{self.path.as_posix()}?mode=ro", uri=True)
        conn.set_authorizer(_read_only_authorizer)
        try:
            cur = conn.execute(sql, list(params))
            columns = [d[0] for d in cur.description or []]
            rows = cur.fetchmany(max(1, int(limit)) + 1)
        finally:
            conn.close()
        truncated = len(rows) > limit
        rows = [list(r) for r in rows[:limit]]
        return {"columns": columns, "rows": rows, "row_count": len(rows), "truncated": truncated}

    def rows(self, table: str, store_id: Optional[str] = None, where: str = "", params: Iterable[Any] = ()
             ) -> List[Dict[str, Any]]:
        _ident(table)
        if table not in self.tables():
            return []
        sql = f"SELECT * FROM {table}"
        args = list(params)
        conds = [where] if where else []
        if store_id is not None:
            conds.insert(0, "_store_id=?")
            args.insert(0, store_id)
        if conds:
            sql += " WHERE " + " AND ".join(f"({x})" for x in conds)
        with self._conn() as c:
            return [dict(r) for r in c.execute(sql, args)]

    # ---- decision log ----
    def log(self, kind: str, record: Dict[str, Any], store_id: str = "") -> str:
        rid = record.get("id") or record.get("action_id") or f"{kind}-{now_iso()}"
        with self._conn() as c:
            c.execute("INSERT OR REPLACE INTO decision_log VALUES (?,?,?,?,?)",
                      (rid, kind, store_id, json.dumps(record, ensure_ascii=False), now_iso()))
        return rid

    def log_query(self, kind: Optional[str] = None, store_id: Optional[str] = None) -> List[Dict[str, Any]]:
        sql, args = "SELECT * FROM decision_log WHERE 1=1", []
        if kind:
            sql += " AND kind=?"
            args.append(kind)
        if store_id:
            sql += " AND store_id=?"
            args.append(store_id)
        with self._conn() as c:
            return [json.loads(r["record"]) for r in c.execute(sql + " ORDER BY created_at", args)]

    def snapshot(self, target_dir: Path) -> Path:
        """A consistent copy of the whole file (SQLite backup API), for the owner's own backup."""
        target_dir = Path(target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        out = target_dir / f"ec_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        src, dst = self._conn(), sqlite3.connect(out)
        try:
            src.backup(dst)
        finally:
            src.close()
            dst.close()
        return out


_READ_OPS = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE}


def _read_only_authorizer(action, *_args):
    return sqlite3.SQLITE_OK if action in _READ_OPS else sqlite3.SQLITE_DENY


def _cell(value: Any) -> Any:
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return value
