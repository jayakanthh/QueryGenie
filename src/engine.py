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
              max_retries: int = 1) -> QueryRun:
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


# ---------------------------------------------------------------------------
# Month-3 enhancement: confidence-aware abstention (evaluated pipeline only).
# ---------------------------------------------------------------------------
import json
import os

from codes_prompt import ABSTAIN_TAU, Decision

_OP_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "results", "abstention_operating_points.json")

# Strictness modes -> (rule on the decision, key of the measured operating point).
# "balanced" is the pre-registered rule tested in Week 11; the others are the
# agreement levels, each with its coverage/accuracy measured on Spider dev.
MODES = {
    "answer_all": (lambda d: True, "answer_all"),
    "balanced": (lambda d: d.confidence >= ABSTAIN_TAU, "calibrated_90"),
    "strict": (lambda d: d.agreement >= 0.75, "min_3_of_4"),
    "very_strict": (lambda d: d.agreement >= 1.0, "all_4"),
}


def operating_points() -> dict:
    try:
        return json.load(open(_OP_FILE))["operating_points"]
    except (OSError, KeyError, ValueError):
        return {}


@dataclass
class ConfidentRun:
    question: str
    decision: Decision
    mode: str

    @property
    def answered(self) -> bool:
        rule, _ = MODES[self.mode]
        return self.decision.candidates[self.decision.selected].runs and rule(self.decision)

    @property
    def chosen(self):
        return self.decision.candidates[self.decision.selected]


def run_confident(backend, db_path: str, question: str, mode: str = "balanced") -> ConfidentRun:
    """Generate 4 candidates, select as in the evaluation, then answer or abstain."""
    return ConfidentRun(question, backend.decide(db_path, question), mode)
