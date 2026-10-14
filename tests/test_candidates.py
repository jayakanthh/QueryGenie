"""Candidates must be different queries (the application's mode) - no model needed."""
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT]
from querygenie.pipeline import build_prefix, canonical_sql, distinct_first  # noqa: E402
from querygenie.providers.base import CandidateBackend  # noqa: E402


def _schema(tmp_path):
    p = str(tmp_path / "pets.sqlite")
    con = sqlite3.connect(p)
    con.executescript("CREATE TABLE pets (id INTEGER PRIMARY KEY, kind TEXT, age INTEGER);"
                      "INSERT INTO pets VALUES (1,'cat',3),(2,'dog',5);")
    con.commit(); con.close()
    return build_prefix(p, "How many pets are there?")[0]


def test_spacing_and_capitals_do_not_make_a_different_query(tmp_path):
    schema = _schema(tmp_path)
    assert canonical_sql("SELECT count(*) FROM pets", schema) == canonical_sql("select COUNT ( * )  from pets;", schema)
    assert canonical_sql("SELECT count(*) FROM pets", schema) != canonical_sql("SELECT count(DISTINCT kind) FROM pets", schema)


def test_the_first_four_different_queries_are_kept_in_order(tmp_path):
    schema = _schema(tmp_path)
    texts = ["SELECT count(*) FROM pets", "select count(*)  from pets", "SELECT count(id) FROM pets",
             "SELECT count(*) FROM pets;", "SELECT count(kind) FROM pets", "SELECT count(age) FROM pets",
             "SELECT count(DISTINCT kind) FROM pets", "SELECT count(DISTINCT age) FROM pets"]
    scores = [-0.1 * i for i in range(8)]
    out, sc = distinct_first(texts, scores, schema, 4)
    assert out == [texts[0], texts[2], texts[4], texts[5]] and sc == [scores[0], scores[2], scores[4], scores[5]]


def test_when_the_model_has_only_one_answer_it_is_repeated_to_four(tmp_path):
    schema = _schema(tmp_path)
    out, _ = distinct_first(["SELECT count(*) FROM pets"] * 5 + ["SELECT count(id) FROM pets"], [0.0] * 6, schema, 4)
    assert len(out) == 4 and out[0] == "SELECT count(*) FROM pets" and out[1] == "SELECT count(id) FROM pets"


class _Sampler(CandidateBackend):
    def raw_candidates(self, prompt):
        return []


def test_sampling_continues_until_four_different_queries(tmp_path):
    b = _Sampler("m")
    b.current_schema = _schema(tmp_path)
    answers = iter(["SELECT count(*) FROM pets"] * 3 + ["SELECT count(id) FROM pets", "SELECT count(*) FROM pets",
                                                         "SELECT count(kind) FROM pets", "SELECT count(age) FROM pets"])
    calls = []
    out = b.distinct_candidates(lambda i: (calls.append(i), next(answers))[1])
    assert len({canonical_sql(t, b.current_schema) for t in out}) == 4 and calls == list(range(7))


def test_sampling_gives_up_after_the_cap_and_fills_with_repeats(tmp_path):
    b = _Sampler("m")
    b.current_schema = _schema(tmp_path)
    calls = []
    out = b.distinct_candidates(lambda i: (calls.append(i), "SELECT count(*) FROM pets")[1])
    assert len(out) == 4 and len(calls) == 12
