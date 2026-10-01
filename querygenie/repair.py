"""
Execution-guided self-correction (the DIN-SQL idea, arXiv:2304.11015), as an application feature.

After the four candidate queries have been run, each distinct query that failed is sent back to the
model once, with the database error, and the repaired query takes its place. Selection, agreement and
abstention then run again on the repaired set with the same code as the evaluation (pipeline.decide).

The measured results (77.8% / 83.3% on Spider) are those of the pipeline *without* this step; the
application says so wherever it shows them.
"""
from __future__ import annotations

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
                fixes[c.sql] = backend.fix_sql(c.sql, c.error)
            except Exception:  # noqa: BLE001 - a repair that fails leaves the candidate as it was
                fixes[c.sql] = None
    texts = []
    for c in decision.candidates:
        fixed = fixes.get(c.sql) if (c.sql and not c.runs) else None
        texts.append(fixed or c.sql)
    repaired = decide(target, schema, texts, [c.beam_score for c in decision.candidates])
    repairs = {i: {"from": c.sql, "error": c.error, "to": repaired.candidates[i].sql, "runs": repaired.candidates[i].runs}
               for i, c in failed if fixes.get(c.sql)}
    return repaired, repairs
