"""Execution-guided self-correction (querygenie/repair.py) and line charts — no model needed."""
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT, os.path.join(ROOT, "desktop")]
from querygenie.pipeline import build_prefix, decide  # noqa: E402
from querygenie.repair import chat_repair_prompt, completion_hint, self_correct  # noqa: E402


def _db(tmp_path):
    p = str(tmp_path / "shop.sqlite")
    con = sqlite3.connect(p)
    con.executescript("CREATE TABLE item (id INTEGER PRIMARY KEY, name TEXT, price REAL);"
                      "INSERT INTO item VALUES (1,'pen',2.5),(2,'book',12.0),(3,'bag',30.0);")
    con.commit(); con.close()
    return p


class FakeModel:
    """Repairs 'prise' to 'price'; records what it was asked."""
    def __init__(self, ctx):
        self.last_context, self.asked = ctx, []

    def fix_sql(self, sql, error):
        self.asked.append((sql, error))
        return sql.replace("prise", "price")


def test_failed_candidates_are_repaired_and_reselected(tmp_path):
    path = _db(tmp_path)
    schema, prefix = build_prefix(path, "Which items cost more than 10?")
    good, bad = "SELECT name FROM item WHERE price > 10", "SELECT name FROM item WHERE prise > 10"
    d = decide(path, schema, [bad, bad, good, "SELECT nonsense FROM nowhere"], [-0.1, -0.2, -0.3, -0.4])
    assert d.n_agree == 1 and not d.candidates[0].runs
    model = FakeModel((path, schema, prefix))
    d2, repairs = self_correct(model, d)
    assert [sql for sql, _ in model.asked] == [bad, "SELECT nonsense FROM nowhere"]     # each distinct failure once
    assert "no such column" in model.asked[0][1]
    assert d2.n_agree == 3 and sorted(d2.candidates[d2.selected].rows) == [("bag",), ("book",)]
    assert repairs[0]["runs"] and not repairs[3]["runs"] and set(repairs) == {0, 1, 3}


def test_nothing_to_repair_leaves_the_decision_alone(tmp_path):
    path = _db(tmp_path)
    schema, prefix = build_prefix(path, "How many items?")
    d = decide(path, schema, ["SELECT count(*) FROM item"] * 4, [0.0] * 4)
    model = FakeModel((path, schema, prefix))
    d2, repairs = self_correct(model, d)
    assert d2 is d and repairs == {} and model.asked == []


def test_repair_prompts_carry_the_query_and_error():
    hint = completion_hint("SELECT a\nFROM t", "no such column: a")
    assert hint == "-- previous attempt: SELECT a FROM t\n-- it failed: no such column: a\n"
    p = chat_repair_prompt("schema...\nQuestion: q", "SELECT a FROM t", "no such column: a")
    assert "SELECT a FROM t" in p and "no such column: a" in p and p.endswith("Reply with a corrected SQLite query only.")


def test_dates_draw_line_charts():
    from api import chart_spec
    spec = chart_spec(["month", "sales"], [["2026-03-01", 5], ["2026-01-01", 3], ["2026-02-01", 4]])
    assert spec["kind"] == "line" and [p[0] for p in spec["points"]] == ["2026-01-01", "2026-02-01", "2026-03-01"]
    assert chart_spec(["year", "n"], [[2016, 2], [2014, 5]])["kind"] == "line"
    assert chart_spec(["dept", "n"], [["CSE", 3], ["IT", 2]])["kind"] == "bar"
    assert chart_spec(["id", "n"], [[1, 2], [3, 4]])["kind"] == "scatter"      # an id is not a year
