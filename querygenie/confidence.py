"""
Month-3 enhancement: confidence-aware abstention on top of the evaluated pipeline.

A Decision (pipeline.decide) carries the four candidates and how many agree; a strictness mode
turns it into "answer" or "ask the user which reading they meant". The coverage and accuracy of
each mode were measured on Spider dev (results/abstention_operating_points.json).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from .pipeline import ABSTAIN_TAU, Decision

_OP_FILE = os.environ.get("QG_OPERATING_POINTS") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results", "abstention_operating_points.json")

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


def run_confident(backend, db_path: str, question: str, mode: str = "balanced",
                  db_comments: dict | None = None) -> ConfidentRun:
    """Generate 4 candidates, select as in the evaluation, then answer or abstain."""
    return ConfidentRun(question, backend.decide(db_path, question, db_comments), mode)


def run_confident_connected(backend, source, question: str, mode: str = "balanced") -> ConfidentRun:
    """As run_confident, on a live database (SQL translated to its dialect, run read-only)."""
    return ConfidentRun(question, backend.decide_connected(source, question), mode)
