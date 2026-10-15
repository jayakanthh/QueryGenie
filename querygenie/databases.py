"""
The databases the app can query.

- The bundled academic database (querygenie/sample_data/academic.sqlite, built on start-up).
- The 20 Spider development-set databases, if present under data/spider_full/ (downloaded
  from Hugging Face — an approved source — by scripts/download_spider_dbs.py). These are the
  databases the reproduction and the abstention results were measured on, so the accuracy
  and confidence figures shown in the app apply to them directly. Example questions are real
  Spider dev questions for each database.
- SQLite files the user uploads in the app.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
from dataclasses import dataclass, field

from .pipeline import load_db_comments
from .sample_db import ensure_sample_dbs

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPIDER = os.environ.get("QG_SPIDER_DIR") or os.path.join(REPO, "data", "spider_full", "spider_data")
UPLOADS = os.environ.get("QG_UPLOADS_DIR") or os.path.join(REPO, "querygenie", "sample_data", "uploads")

ACADEMIC_EXAMPLES = [
    "Which students failed more than two subjects? A subject is failed if marks are below 40.",
    "List the subjects and the average marks for each subject.",
    "How many students are in each year?",
    "Who is the best student?",
    "List the top 3 students by total marks.",
    "Average marks per department",
]

# Readable names for the 20 Spider development databases.
SPIDER_NAMES = {
    "concert_singer": "Concerts & singers", "pets_1": "Students & pets", "car_1": "Car makers & models",
    "flight_2": "Airlines & flights", "employee_hire_evaluation": "Employees & shops",
    "cre_Doc_Template_Mgt": "Document templates", "course_teach": "Courses & teachers",
    "museum_visit": "Museum visits", "wta_1": "Women's tennis (WTA)", "battle_death": "Battles & ships",
    "student_transcripts_tracking": "Student transcripts", "tvshow": "TV channels & cartoons",
    "poker_player": "Poker players", "voter_1": "Contest votes", "world_1": "World countries & cities",
    "orchestra": "Orchestras & conductors", "network_1": "High-school friends",
    "dog_kennels": "Dog kennels", "singer": "Singers & songs", "real_estate_properties": "Real-estate properties",
}


@dataclass
class DbInfo:
    label: str
    path: str
    source: str
    examples: list = field(default_factory=list)
    comments: dict = field(default_factory=dict)   # tables.json descriptions (Spider only)
    conn: object = None                            # connectors.SqlAlchemySource for live databases


def _spider_examples(dev, db_id, k=6):
    qs = []
    for ex in dev:
        q = ex["question"].strip()
        if ex["db_id"] == db_id and q not in qs:
            qs.append(q)
    step = max(1, len(qs) // k)          # spread the picks over the question set
    return qs[::step][:k]


def build_catalog() -> dict:
    cat = {}
    for label, path in ensure_sample_dbs().items():
        cat[label] = DbInfo(label, path, "Bundled sample database", ACADEMIC_EXAMPLES)
    dev_path, tables_path = os.path.join(SPIDER, "dev.json"), os.path.join(SPIDER, "tables.json")
    if os.path.exists(dev_path) and os.path.exists(tables_path):
        dev = json.load(open(dev_path))
        comments = load_db_comments(tables_path)
        for db_id in sorted({e["db_id"] for e in dev}, key=lambda d: SPIDER_NAMES.get(d, d)):
            path = os.path.join(SPIDER, "database", db_id, f"{db_id}.sqlite")
            if os.path.exists(path):
                label = f"{SPIDER_NAMES.get(db_id, db_id)} · Spider"
                cat[label] = DbInfo(label, path, f"Spider dev set (Hugging Face) — <code>{db_id}</code>",
                                    _spider_examples(dev, db_id), comments.get(db_id, {}))
    if os.path.isdir(UPLOADS):
        for f in sorted(os.listdir(UPLOADS)):
            if f.endswith((".sqlite", ".db", ".sqlite3")):
                label = f"{os.path.splitext(f)[0]} · uploaded"
                cat[label] = DbInfo(label, os.path.join(UPLOADS, f), "Uploaded by you")
    cat.update(CONNECTED)
    return cat


CONNECTED = {}   # label -> DbInfo for live connections for open connections (memory only; saved profiles are kept by desktop/api.py: host and user in the settings, password in the OS keychain)


def connect(kind, host, port, database, user, password) -> str:
    """Open a live connection, read its schema and build the value index; return its label."""
    from .connectors import SqlAlchemySource, make_url
    if not database:
        raise ValueError("Enter a database name.")
    src = SqlAlchemySource(make_url(kind, host, port, database, user, password),
                           label=f"{database} · {kind.split(' ')[0]} @ {host or 'localhost'}")
    src.introspect(); src.build_index()
    CONNECTED[src.label] = DbInfo(src.label, "", f"Live {kind} connection (read-only)", conn=src)
    return src.label


def _connect_ro(path):
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def list_tables(path):
    con = _connect_ro(path)
    try:
        names = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY rowid")]
        out = []
        for t in names:
            cols = [r[1] for r in con.execute(f'PRAGMA table_info("{t}")')]
            n = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
            out.append((t, cols, n))
        return out
    finally:
        con.close()


def tables_of(info):
    return info.conn.tables_summary() if info.conn is not None else list_tables(info.path)


def schema_graph(info):
    """Tables with typed columns, primary keys and foreign keys, for the desktop schema map.

    [{"table", "rows", "columns": [{"name", "type", "pk", "ref": [table, column] | None}]}]
    """
    counts = {t: n for t, _cols, n in tables_of(info)}
    if info.conn is not None:
        schema = info.conn.introspect()
        refs = {(a, b): [c, d] for a, b, c, d in schema["foreign_keys"]}
        return [{"table": it["table_name"], "rows": counts.get(it["table_name"], 0),
                 "columns": [{"name": n, "type": ty, "pk": bool(pk), "ref": refs.get((it["table_name"], n))}
                             for n, ty, pk in zip(it["column_names"], it["column_types"], it["pk_indicators"])]}
                for it in schema["schema_items"]]
    con = _connect_ro(info.path)
    try:
        out = []
        for t in counts:
            refs = {r[3]: [r[2], r[4]] for r in con.execute(f'PRAGMA foreign_key_list("{t}")')}
            cols = [{"name": r[1], "type": (r[2] or "").lower(), "pk": bool(r[5]), "ref": refs.get(r[1])}
                    for r in con.execute(f'PRAGMA table_info("{t}")')]
            out.append({"table": t, "rows": counts[t], "columns": cols})
        return out
    finally:
        con.close()


def schema_markdown(info) -> str:
    rows = []
    for t, cols, n in tables_of(info):
        shown = ", ".join(cols[:8]) + (f", … (+{len(cols) - 8})" if len(cols) > 8 else "")
        rows.append(f"**{t}** · {n:,} rows  \n<span class='qg-cols'>{shown}</span>")
    return "\n\n".join(rows) or "_No tables found._"


def add_upload(src_path) -> str:
    """Validate an uploaded SQLite file, copy it into the uploads folder, return its label."""
    try:
        tables = list_tables(src_path)
    except sqlite3.DatabaseError as exc:
        raise ValueError(f"That file is not a readable SQLite database ({exc}).")
    if not tables:
        raise ValueError("That database has no tables.")
    os.makedirs(UPLOADS, exist_ok=True)
    base = os.path.basename(src_path)
    if not base.endswith((".sqlite", ".db", ".sqlite3")):
        base += ".sqlite"
    dst = os.path.join(UPLOADS, base)
    shutil.copyfile(src_path, dst)
    return f"{os.path.splitext(base)[0]} · uploaded"
