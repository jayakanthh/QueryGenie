#!/usr/bin/env python3
"""
Measure the connector's SQLite -> PostgreSQL translation on Spider dev (no model needed).

For every dev question, the gold query and our saved T2-006 prediction are run on the SQLite
database and, translated by connectors.SqlAlchemySource, on the same data loaded into
PostgreSQL (scripts/load_spider_into_postgres.py). Results are compared as multisets of rows
(numbers — including numbers stored as text — compared by value to 6 decimal places). Writes results/postgres_translation_check.json.

    python research/app-checks/check_postgres_translation.py --url postgresql+psycopg://qg@127.0.0.1:5544
"""
import argparse, collections, json, os, sqlite3, sys
from decimal import Decimal

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)
from querygenie.connectors import SqlAlchemySource  # noqa: E402

SPIDER = os.path.join(REPO, "data", "spider_full", "spider_data")


def norm(rows):
    def v(x):
        if isinstance(x, (int, float, Decimal)) and not isinstance(x, bool):
            f = float(x)
            return f"{round(f, 6):.6f}"
        if isinstance(x, (bytes, bytearray)):
            x = x.decode(errors="ignore")
        if x is None:
            return ""
        try:                      # numbers stored as text in SQLite ('2009') equal numbers (2009)
            return f"{round(float(str(x).strip()), 6):.6f}"
        except ValueError:
            return str(x)
    return collections.Counter(tuple(v(c) for c in r) for r in rows)


def sqlite_rows(path, sql):
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True); con.text_factory = lambda b: b.decode(errors="ignore")
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True, help="server URL without database, e.g. postgresql+psycopg://qg@127.0.0.1:5544")
    ap.add_argument("--preds", default=os.path.join(REPO, "results", "preds_T2-006.txt"))
    args = ap.parse_args()
    dev = json.load(open(os.path.join(SPIDER, "dev.json")))
    preds = [l.rstrip("\n") for l in open(args.preds)]
    gold = [l.rstrip("\n").split("\t")[0] for l in open(os.path.join(SPIDER, "dev_gold.sql")) if l.strip()]
    assert len(preds) == len(gold) == len(dev)
    sources, out = {}, collections.Counter()
    failures = collections.Counter()
    for i, ex in enumerate(dev):
        db = ex["db_id"]
        path = os.path.join(SPIDER, "database", db, f"{db}.sqlite")
        src = sources.get(db) or sources.setdefault(db, SqlAlchemySource(f"{args.url}/{db.lower()}"))
        for kind, sql in (("gold", gold[i]), ("pred", preds[i])):
            try:
                ref = norm(sqlite_rows(path, sql))
            except Exception:
                out[f"{kind}_sqlite_error"] += 1
                continue
            out[f"{kind}_total"] += 1
            ok, cols, rows, _h, err = src.signature(sql)
            if not ok:
                out[f"{kind}_pg_error"] += 1
                failures[(kind, err.split(":")[0][:60])] += 1
            elif norm(rows) == ref:
                out[f"{kind}_same"] += 1
            else:
                out[f"{kind}_different"] += 1
                s = sql.lower()
                if "order by" in s and "limit" in s:
                    out[f"{kind}_different_order_limit"] += 1   # ties may legitimately differ
        if (i + 1) % 200 == 0:
            print(f"[{i+1}/{len(dev)}] {dict(out)}", flush=True)
    res = {"questions": len(dev), **dict(out),
           "gold_same_rate": out["gold_same"] / out["gold_total"],
           "pred_same_rate": out["pred_same"] / out["pred_total"],
           "top_failures": [[k[0], k[1], n] for k, n in failures.most_common(12)]}
    json.dump(res, open(os.path.join(REPO, "results", "postgres_translation_check.json"), "w"), indent=2)
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
