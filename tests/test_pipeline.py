"""Model-free tests for the evaluated pipeline's selection, agreement and abstention logic.

Run:  python -m pytest tests/ -q
"""
import os
import sqlite3
import sys

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT, os.path.join(ROOT, "research")]

from querygenie.pipeline import ABSTAIN_TAU, decide, post_process  # noqa: E402
from querygenie.confidence import MODES, ConfidentRun  # noqa: E402
import abstention  # noqa: E402

SCHEMA = {"schema_items": [{"table_name": "student", "column_names": ["student_id", "name", "year"]}]}


@pytest.fixture()
def db(tmp_path):
    path = str(tmp_path / "t.sqlite")
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE student (student_id INTEGER PRIMARY KEY, name TEXT, year INTEGER)")
    con.executemany("INSERT INTO student VALUES (?, ?, ?)", [(1, "Asha", 1), (2, "Ravi", 2), (3, "Sana", 2)])
    con.commit(); con.close()
    return path


ALL = "SELECT name FROM student"
YEAR2 = "SELECT name FROM student WHERE year = 2"
YEAR2_REORDERED = "SELECT name FROM student WHERE year = 2 ORDER BY name DESC"   # same rows
ONE = "SELECT name FROM student WHERE student_id = 1"
BROKEN = "SELECT nope FROM student"


def test_agreement_counts_candidates_with_the_same_result(db):
    d = decide(db, SCHEMA, [YEAR2, YEAR2_REORDERED, YEAR2, ALL], [-0.1, -0.2, -0.3, -0.4])
    assert d.selected == 0
    assert d.agreement == 0.75            # row order does not matter for agreement
    assert not d.abstain


def test_first_executable_candidate_is_selected(db):
    d = decide(db, SCHEMA, [BROKEN, ONE, ALL, YEAR2], [-0.1, -0.2, -0.3, -0.4])
    assert d.selected == 1
    assert not d.candidates[0].runs and d.candidates[1].runs


def test_abstains_when_nothing_runs(db):
    d = decide(db, SCHEMA, [BROKEN] * 4, [-0.1, -0.2, -0.3, -0.4])
    assert d.agreement == 0.0 and d.abstain


def test_abstains_when_all_candidates_disagree_with_low_probability(db):
    # equal beam scores -> beam probability 0.25 -> confidence 0.2525 < tau
    d = decide(db, SCHEMA, [ALL, YEAR2, ONE, "SELECT year FROM student"], [-1.0] * 4)
    assert d.agreement == 0.25
    assert d.confidence == pytest.approx(0.25 + 0.01 * 0.25)
    assert d.confidence < ABSTAIN_TAU and d.abstain


def test_answers_when_one_candidate_is_very_probable(db):
    d = decide(db, SCHEMA, [ALL, YEAR2, ONE, "SELECT year FROM student"], [0.0, -9.0, -9.0, -9.0])
    assert d.agreement == 0.25 and d.beam_prob > 0.99
    assert not d.abstain                  # the tie-breaker lifts it over the threshold


def test_interpretations_group_by_result_most_supported_first(db):
    d = decide(db, SCHEMA, [ONE, YEAR2, YEAR2_REORDERED, BROKEN], [-0.1, -0.2, -0.3, -0.4])
    assert d.interpretations() == [(1, 2), (0, 1)]


def test_strictness_modes(db):
    d = decide(db, SCHEMA, [YEAR2, YEAR2, ALL, ONE], [-0.1, -0.2, -0.3, -0.4])   # 2 of 4 agree
    answered = {m: ConfidentRun("q", d, m).answered for m in MODES}
    assert answered == {"answer_all": True, "balanced": True, "strict": False, "very_strict": False}


def test_post_process_quotes_special_column_names():
    schema = {"schema_items": [{"column_names": ["first name"]}]}
    assert post_process("SELECT first name\nFROM t", schema["schema_items"]) == "SELECT `first name` FROM t"


def test_abstention_signals_and_curve():
    row = {"selected": 0, "beam_scores": [0.0, -1.0, -2.0, -3.0], "result_hash": ["a", "a", "b", None]}
    s = abstention.signals(row)
    assert s["agreement_raw"] == 0.5 and s["agreement"] > 0.5
    conf = np.array([0.9, 0.8, 0.1, 0.2]); correct = np.array([1.0, 1.0, 0.0, 1.0])
    cov, acc = abstention.curve(conf, correct)
    assert list(cov) == [0.25, 0.5, 0.75, 1.0] and acc[0] == 1.0 and acc[-1] == 0.75


def test_catalog_and_upload_validation(tmp_path, monkeypatch):
    from querygenie import databases
    monkeypatch.setattr(databases, "UPLOADS", str(tmp_path / "uploads"))
    cat = databases.build_catalog()
    assert any(k.startswith("academic") for k in cat)
    bad = tmp_path / "bad.sqlite"; bad.write_text("not a database")
    with pytest.raises(ValueError):
        databases.add_upload(str(bad))
    good = tmp_path / "shop.sqlite"
    con = sqlite3.connect(str(good)); con.execute("CREATE TABLE item (id INTEGER, name TEXT)")
    con.execute("INSERT INTO item VALUES (1, 'pen')"); con.commit(); con.close()
    label = databases.add_upload(str(good))
    assert label in databases.build_catalog()
    assert databases.list_tables(databases.build_catalog()[label].path) == [("item", ["id", "name"], 1)]


def test_candidate_execution_is_read_only(db):
    from querygenie.pipeline import result_signature
    ok, *_, err = result_signature(db, "DELETE FROM student")
    assert not ok and "readonly" in err.replace(" ", "").lower()
    con = sqlite3.connect(db); assert con.execute("SELECT COUNT(*) FROM student").fetchone()[0] == 3


# ---- connector: translation + read-only guard, tested on SQLite (no server needed) ----
@pytest.fixture()
def pg_like(db):
    from querygenie.connectors import SqlAlchemySource
    src = SqlAlchemySource(f"sqlite:///{db}")
    src.dialect = "postgres"          # exercise the Postgres rewrites without a Postgres server
    return src


def test_translate_rejects_writes_and_multiple_statements(pg_like):
    from querygenie.connectors import ReadOnlyViolation
    for bad in ["DELETE FROM student", "DROP TABLE student", "SELECT 1; SELECT 2",
                "INSERT INTO student VALUES (9, 'x', 1)"]:
        with pytest.raises(ReadOnlyViolation):
            pg_like.translate(bad)


def test_translate_sqlite_semantics_for_postgres(pg_like):
    t = pg_like.translate
    assert "'Asha'" in t('SELECT year FROM student WHERE name = "Asha"')          # "text" -> string
    assert "'name'" not in t('SELECT "name" FROM student')                        # real column kept
    assert "ILIKE" in t("SELECT name FROM student WHERE name LIKE '%a%'")          # case-insensitive LIKE
    assert "MAX(name)" in t("SELECT name, COUNT(*) FROM student GROUP BY year")     # bare column wrapped
    # SQLite's "row holding the max" idiom is left alone (it would fail -> lower agreement)
    assert "MAX(name)" not in t("SELECT name, MAX(year) FROM student GROUP BY year")
