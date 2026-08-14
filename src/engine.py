"""
The QueryGenie pipeline: generate SQL, execute it, and self-correct on failure.

This is the seed of enhancement #1 (execution-guided self-correction): the same
try/execute/repair loop from the Week-4 gate, made iterative. When a generated
query fails to execute, the error is fed back to the model and it tries again.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from database import ExecResult, build_schema_string, execute_sql


@dataclass
class Attempt:
    sql: str
    ok: bool
    error: str = ""


@dataclass
class QueryRun:
    question: str
    attempts: list[Attempt] = field(default_factory=list)
    result: ExecResult | None = None

    @property
    def sql(self) -> str:
        return self.attempts[-1].sql if self.attempts else ""

    @property
    def self_corrected(self) -> bool:
        # More than one attempt AND we ended up succeeding.
        return len(self.attempts) > 1 and bool(self.result and self.result.ok)

    @property
    def ok(self) -> bool:
        return bool(self.result and self.result.ok)


def run_query(backend, conn: sqlite3.Connection, question: str,
              max_retries: int = 2) -> QueryRun:
    schema = build_schema_string(conn)
    run = QueryRun(question=question)

    prior_error: str | None = None
    for _ in range(max_retries + 1):
        sql = backend.generate(schema, question, prior_error=prior_error)
        res = execute_sql(conn, sql)
        run.attempts.append(Attempt(sql=sql, ok=res.ok, error=res.error))
        run.result = res
        if res.ok:
            break
        prior_error = res.error  # feed the failure back into the next attempt

    return run
