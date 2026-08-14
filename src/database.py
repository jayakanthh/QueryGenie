"""
Database helpers for QueryGenie.

Two jobs:
1. Serialize a SQLite schema into the CodeS-style prompt string the model expects.
2. Execute generated SQL and return rows/columns (or a clean error string) so the
   app's self-correction loop can react to failures.

Everything here is plain sqlite3 + introspection, so it works for any bundled DB.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


# SQLite storage classes -> the short type names CodeS was trained to see.
def _short_type(decl: str) -> str:
    d = (decl or "").upper()
    if "INT" in d:
        return "int"
    if any(t in d for t in ("CHAR", "CLOB", "TEXT")):
        return "text"
    if "BLOB" in d or d == "":
        return "text"
    if any(t in d for t in ("REAL", "FLOA", "DOUB", "DEC", "NUM")):
        return "number"
    return "text"


def list_tables(conn: sqlite3.Connection) -> list[str]:
    # Preserve *creation order* (sqlite_master rowid), NOT alphabetical. The model
    # is sensitive to table order in the serialized schema — listing the primary
    # entity table first materially improves generation quality.
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY rowid"
    ).fetchall()
    return [r[0] for r in rows]


def build_schema_string(conn: sqlite3.Connection) -> str:
    """Serialize the schema in the CodeS 'database schema :' format."""
    lines = ["database schema :"]
    fk_lines: list[str] = []

    for table in list_tables(conn):
        cols = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
        # PRAGMA table_info -> (cid, name, type, notnull, dflt_value, pk)
        parts = []
        for cid, name, ctype, notnull, dflt, pk in cols:
            tag = _short_type(ctype)
            if pk:
                tag += " | primary key"
            parts.append(f"{table}.{name} ( {tag} )")
        lines.append(f"table {table} , columns = [ {' , '.join(parts)} ]")

        for fk in conn.execute(f'PRAGMA foreign_key_list("{table}")').fetchall():
            # (id, seq, ref_table, from_col, to_col, on_update, on_delete, match)
            _, _, ref_table, from_col, to_col, *_ = fk
            fk_lines.append(f"{table}.{from_col} = {ref_table}.{to_col}")

    if fk_lines:
        lines.append("foreign keys : " + " , ".join(fk_lines))
    return "\n".join(lines)


@dataclass
class ExecResult:
    ok: bool
    columns: list[str]
    rows: list[tuple]
    error: str = ""


def execute_sql(conn: sqlite3.Connection, sql: str, limit: int = 200) -> ExecResult:
    """Run one SELECT-ish statement. Returns a result object; never raises."""
    stmt = sql.strip().rstrip(";").strip()
    if not stmt:
        return ExecResult(False, [], [], "empty query")
    try:
        cur = conn.execute(stmt)
        columns = [d[0] for d in cur.description] if cur.description else []
        rows = cur.fetchmany(limit)
        return ExecResult(True, columns, rows)
    except Exception as exc:  # noqa: BLE001 - we want the message, whatever it is
        return ExecResult(False, [], [], f"{type(exc).__name__}: {exc}")
