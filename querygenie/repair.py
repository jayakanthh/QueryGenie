"""
Execution-guided self-correction (the DIN-SQL idea, arXiv:2304.11015), as an application feature.

After the four candidate queries have been run, each distinct query that failed is sent back to the
model once, with the database error, and the repaired query takes its place. A query that ran but
found no rows while the question names values stored in the database ("ford maverick" in
car_names.make) is sent back too, with those values; its repair is kept only if it finds rows. Selection, agreement and
abstention then run again on the repaired set with the same code as the evaluation (pipeline.decide).

The measured results (77.8% / 83.3% on Spider) are those of the pipeline *without* this step; the
application says so wherever it shows them.
"""
from __future__ import annotations

import re

from .pipeline import decide

MAX_REPAIRS = 4                       # at most one attempt per distinct failed query


def completion_hint(failed_sql: str, error: str) -> str:
    """For CodeS-style completion models: the failed attempt and its error as an SQL comment after
    the question (as in the Gradio prototype's retry loop)."""
    one_line = lambda s: " ".join(str(s).split())
    return f"-- previous attempt: {one_line(failed_sql)}\n-- it failed: {one_line(error)}\n"


def chat_repair_prompt(prompt: str, failed_sql: str, error: str) -> str:
    """For chat models: the original request, the failed query and the error."""
    return (f"{prompt}\n\nThis SQLite query was tried:\n{failed_sql}\n\nIt failed with this error:\n{error}\n\n"
            "Reply with a corrected SQLite query only.")


_NO_COLUMN = re.compile(r"no such column:\s*(?:\w+\.)?(\w+)", re.I)


def explain_error(error: str, sql: str, schema: dict) -> str:
    """Add the schema fact a "no such column" error is missing: which table has that column and how it
    joins to the tables the query uses ("horsepower is a column of cars_data; join cars_data.id =
    car_names.makeid"). Other errors are returned unchanged."""
    m = _NO_COLUMN.search(error or "")
    if not m:
        return error
    col = m.group(1).lower()
    owners = [t["table_name"] for t in schema["schema_items"] if col in [c.lower() for c in t["column_names"]]]
    if not owners:
        return error
    used = {t["table_name"] for t in schema["schema_items"] if re.search(rf"\b{re.escape(t['table_name'])}\b", sql or "", re.I)}
    joins = [f"{a}.{b} = {c}.{d}" for a, b, c, d in schema.get("foreign_keys", [])
             if (a in owners and c in used) or (c in owners and a in used)]
    return (f"{error}. {col} is a column of {', '.join(owners)}" + (f"; join {'; '.join(joins[:2])}" if joins else ""))


def add_missing_join(sql: str, error: str, schema: dict) -> str | None:
    """A rule, not the model: when a single-table query uses a column that lives in exactly one other
    table with a foreign key to it, join that table and qualify the columns. None when that's not the case."""
    m = _NO_COLUMN.search(error or "")
    if not m:
        return None
    try:
        import sqlglot
        from sqlglot import exp
        tree = sqlglot.parse_one(sql, read="sqlite")
    except Exception:  # noqa: BLE001
        return None
    col = m.group(1).lower()
    tables = {t.name.lower() for t in tree.find_all(exp.Table)}
    if len(tables) != 1 or not isinstance(tree, exp.Select):
        return None
    base = tables.pop()
    cols = {t["table_name"].lower(): [c.lower() for c in t["column_names"]] for t in schema["schema_items"]}
    owners = [t for t, cs in cols.items() if col in cs and t != base]
    links = [(a, b, c, d) for a, b, c, d in schema.get("foreign_keys", [])
             for o in owners if {a.lower(), c.lower()} == {base, o}]
    if len(owners) != 1 or len(links) != 1:
        return None
    owner = owners[0]
    for c in tree.find_all(exp.Column):
        if not c.table:
            name = c.name.lower()
            c.set("table", exp.to_identifier(base if name in cols.get(base, []) else owner if name in cols[owner] else base))
    a, b, c_, d = links[0]
    tree = tree.join(owner, on=f"{a}.{b} = {c_}.{d}", dialect="sqlite")
    return tree.sql(dialect="sqlite")


def self_correct(backend, decision):
    """Repair the candidates that failed. Returns (decision, repairs) where repairs lists, per candidate
    index, {"from": failed SQL, "error": ..., "to": repaired SQL, "runs": bool}. If nothing failed, or the
    model has no repair method, the decision is returned unchanged."""
    failed = [(i, c) for i, c in enumerate(decision.candidates) if c.sql and not c.runs]
    if not failed or not hasattr(backend, "fix_sql") or not getattr(backend, "last_context", None):
        return decision, {}
    target, schema, _prompt = backend.last_context
    fixes = {}
    for _i, c in failed:
        if c.sql not in fixes and len(fixes) < MAX_REPAIRS:
            try:
                fixes[c.sql] = backend.fix_sql(c.sql, explain_error(c.error, c.sql, schema))
            except Exception:  # noqa: BLE001 - a repair that fails leaves the candidate as it was
                fixes[c.sql] = None
    texts = []
    for c in decision.candidates:
        fixed = fixes.get(c.sql) if (c.sql and not c.runs) else None
        texts.append(fixed or c.sql)
    repaired = decide(target, schema, texts, [c.beam_score for c in decision.candidates])
    # The model's repair still fails on a column from another table: try adding the join by rule.
    joined = {}
    for i, c in failed:
        r = repaired.candidates[i]
        if not r.runs and c.sql not in joined:
            joined[c.sql] = add_missing_join(r.sql or c.sql, r.error or c.error, schema)
    if any(joined.values()):
        texts = [joined.get(c.sql) or t if (c.sql and not c.runs) else t for c, t in zip(decision.candidates, texts)]
        repaired = decide(target, schema, texts, [c.beam_score for c in decision.candidates])
    repairs = {i: {"from": c.sql, "error": c.error, "to": repaired.candidates[i].sql, "runs": repaired.candidates[i].runs,
                   **({"kind": "join"} if joined.get(c.sql) else {})}
               for i, c in failed if fixes.get(c.sql) or joined.get(c.sql)}
    return repaired, repairs


def unused_values(sql: str, matched: dict | None, limit: int = 5) -> list[tuple[str, str]]:
    """Stored values the question names ({"table.column": [values]}) that the query does not use."""
    low = (sql or "").lower()
    out = []
    for column, values in (matched or {}).items():
        for v in values:
            if str(v).lower() not in low and (column, v) not in out:
                out.append((column, str(v)))
    return out[:limit]


def empty_result_error(hints) -> str:
    return "it returned no rows. Stored values matching the question: " + "; ".join(f'{c} = "{v}"' for c, v in hints)


def repair_empty(backend, decision, matched_values):
    """When the chosen answer has no rows but the question names stored values the queries don't use,
    send each such empty query back once with those values. A repair replaces a candidate only if it
    finds rows. Returns (decision, repairs) like self_correct, repairs marked kind="empty"."""
    chosen = decision.candidates[decision.selected]
    if not (chosen.runs and not chosen.rows) or not hasattr(backend, "fix_sql") or not getattr(backend, "last_context", None):
        return decision, {}
    target, schema, _prompt = backend.last_context
    empty = [(i, c, unused_values(c.sql, matched_values)) for i, c in enumerate(decision.candidates) if c.runs and not c.rows]
    empty = [(i, c, h) for i, c, h in empty if h]
    if not empty:
        return decision, {}
    fixes = {}
    for _i, c, hints in empty:
        if c.sql not in fixes and len(fixes) < MAX_REPAIRS:
            try:
                fixes[c.sql] = backend.fix_sql(c.sql, empty_result_error(hints))
            except Exception:  # noqa: BLE001
                fixes[c.sql] = None
    trial = decide(target, schema, [fixes.get(c.sql) or c.sql for _i, c, _h in empty], [0.0] * len(empty))
    useful = {c.sql: t.sql for (_i, c, _h), t in zip(empty, trial.candidates) if t.runs and t.rows}
    if not useful:
        return decision, {}
    texts = [useful.get(c.sql, c.sql) if (c.runs and not c.rows) else c.sql for c in decision.candidates]
    repaired = decide(target, schema, texts, [c.beam_score for c in decision.candidates])
    repairs = {i: {"from": c.sql, "error": empty_result_error(h), "to": repaired.candidates[i].sql,
                   "runs": repaired.candidates[i].runs, "kind": "empty"}
               for i, c, h in empty if c.sql in useful}
    return repaired, repairs
