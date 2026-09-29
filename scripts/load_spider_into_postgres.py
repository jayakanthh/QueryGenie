#!/usr/bin/env python3
"""
Copy the Spider development databases (SQLite) into a PostgreSQL server — one Postgres
database per Spider database — so the connector layer can be tested on a real server
against questions whose correct answers are known.

    python scripts/load_spider_into_postgres.py --url postgresql://qg@127.0.0.1:5544/postgres

Identifiers are lower-cased (Postgres folds unquoted names to lower case, and the CodeS prompt
lower-cases names anyway). Column types are chosen from the data: integer, double precision or
text. Primary keys and foreign keys are recreated where the data allows; the ones Postgres rejects
(duplicates, references to non-unique columns) are skipped and counted.
"""
import argparse
import json
import os
import sqlite3

from sqlalchemy import create_engine, text

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPIDER = os.path.join(REPO, "data", "spider_full", "spider_data")


def infer_type(values):
    vals = [v for v in values if v is not None and str(v).strip() != ""]
    if not vals:
        return "text"
    def all_(fn):
        try:
            for v in vals: fn(v)
            return True
        except (ValueError, TypeError):
            return False
    if all(isinstance(v, int) for v in vals) or all_(lambda v: int(str(v)) if str(v).lstrip("-").isdigit() else (_ for _ in ()).throw(ValueError)):
        return "integer" if all(abs(int(str(v))) < 2**31 for v in vals) else "bigint"
    if all_(lambda v: float(str(v))):
        return "double precision"
    return "text"


def cast(v, typ):
    if v is None or (isinstance(v, str) and v.strip() == "" and typ != "text"):
        return None
    if typ in ("integer", "bigint"):
        return int(str(v))
    if typ == "double precision":
        return float(str(v))
    return v if isinstance(v, str) else (v.decode(errors="ignore") if isinstance(v, bytes) else str(v))


def q(name):
    return '"' + name.lower().replace('"', '""') + '"'


def load_one(src, admin_url, db_id):
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    pg_name = db_id.lower()
    with admin.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{pg_name}"'))
        c.execute(text(f'CREATE DATABASE "{pg_name}"'))
    eng = create_engine(admin_url.rsplit("/", 1)[0] + "/" + pg_name)
    con = sqlite3.connect(src); con.text_factory = lambda b: b.decode(errors="ignore")
    tables = [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY rowid")]
    stats = {"tables": 0, "rows": 0, "pk_skipped": 0, "fk_added": 0, "fk_skipped": 0}
    with eng.begin() as pg:
        for t in tables:
            info = con.execute(f'PRAGMA table_info("{t}")').fetchall()
            cols = [r[1] for r in info]
            rows = con.execute(f'SELECT * FROM "{t}"').fetchall()
            types = [infer_type([r[i] for r in rows]) for i in range(len(cols))]
            pg.execute(text(f"CREATE TABLE {q(t)} (" + ", ".join(f"{q(c)} {ty}" for c, ty in zip(cols, types)) + ")"))
            if rows:
                ins = text(f"INSERT INTO {q(t)} VALUES (" + ", ".join(f":p{i}" for i in range(len(cols))) + ")")
                pg.execute(ins, [{f"p{i}": cast(r[i], types[i]) for i in range(len(cols))} for r in rows])
            stats["tables"] += 1; stats["rows"] += len(rows)
    # keys in separate transactions so one rejected constraint does not undo the rest
    for t in tables:
        pks = [r[1] for r in sorted(con.execute(f'PRAGMA table_info("{t}")').fetchall(), key=lambda r: r[5]) if r[5]]
        if pks:
            try:
                with eng.begin() as pg:
                    pg.execute(text(f"ALTER TABLE {q(t)} ADD PRIMARY KEY (" + ", ".join(map(q, pks)) + ")"))
            except Exception:
                stats["pk_skipped"] += 1
    for t in tables:
        for fk in con.execute(f'PRAGMA foreign_key_list("{t}")').fetchall():
            ref_t, frm, to = fk[2], fk[3], fk[4]
            if None in (ref_t, frm, to):
                continue
            try:
                with eng.begin() as pg:
                    pg.execute(text(f"ALTER TABLE {q(t)} ADD FOREIGN KEY ({q(frm)}) REFERENCES {q(ref_t)} ({q(to)}) NOT VALID"))
                stats["fk_added"] += 1
            except Exception:
                stats["fk_skipped"] += 1
    con.close(); eng.dispose(); admin.dispose()
    return stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True, help="admin connection URL, e.g. postgresql://qg@127.0.0.1:5544/postgres")
    args = ap.parse_args()
    dev = json.load(open(os.path.join(SPIDER, "dev.json")))
    for db_id in sorted({e["db_id"] for e in dev}):
        s = load_one(os.path.join(SPIDER, "database", db_id, f"{db_id}.sqlite"), args.url, db_id)
        print(f"{db_id:32s} {s}")


if __name__ == "__main__":
    main()
