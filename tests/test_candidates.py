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


class _Chat(CandidateBackend):
    """A chat model that repeats itself until it is shown what it has written, then writes something new."""

    def __init__(self, stubborn=False):
        super().__init__("fake")
        self.stubborn, self.prompts, self.n = stubborn, [], 0

    def once(self, prompt, temperature=0.0):
        self.prompts.append((prompt, temperature))
        if self.stubborn or "already been written" not in prompt:
            return "```sql\nSELECT count(*) FROM pets\n```"
        self.n += 1
        return ["SELECT count(id) FROM pets", "SELECT count(kind) FROM pets", "SELECT count(age) FROM pets"][(self.n - 1) % 3]

    complete_once = once


def test_a_local_chat_model_is_asked_one_at_a_time_until_four_differ(tmp_path):
    be = _Chat()
    be.current_schema = _schema(tmp_path)
    out = be.diverse_candidates(be.once, "Question: How many pets?\nSQLite query:")
    assert len({canonical_sql(t, be.current_schema) for t in out}) == 4
    asked = [p for p, _ in be.prompts]
    # greedy, then a plain sample; that one repeated, so from the third request on the model is shown its queries
    assert "already been written" not in asked[0] + asked[1] and "already been written" in asked[2]
    assert be.prompts[0][1] == 0.0 and be.prompts[1][1] > 0


def test_a_stubborn_model_stops_at_the_cap_and_is_repeated(tmp_path):
    be = _Chat(stubborn=True)
    be.current_schema = _schema(tmp_path)
    out = be.diverse_candidates(be.once, "Question: How many pets?\nSQLite query:")
    assert len(be.prompts) == 8 and len(out) == 4 and len({canonical_sql(t, be.current_schema) for t in out}) == 1


def test_a_cloud_model_gets_top_up_requests_only_for_the_missing_queries(tmp_path):
    be = _Chat()
    be.current_schema = _schema(tmp_path)
    out = be.sample("Question: How many pets?\nSQLite query:")
    assert len({canonical_sql(t, be.current_schema) for t in out}) == 4
    assert len(be.prompts) == 4 + 3                                   # four parallel, three top-ups


def test_the_number_of_candidates_is_a_setting(tmp_path):
    from querygenie.providers.base import clamp_candidates
    assert [clamp_candidates(x) for x in (1, 2, 6, 12, 99, "5", None, "x")] == [2, 2, 6, 12, 12, 5, 4, 4]
    be = _Chat()
    be.current_schema = _schema(tmp_path)
    be.n_candidates = 7
    out = be.diverse_candidates(be.once, "Question: How many pets?\nSQLite query:")
    assert len(out) == 7 and len({canonical_sql(t, be.current_schema) for t in out}) == 4   # the fake knows only 4 ways
    two = _Chat()
    two.n_candidates = 2
    assert len(two.distinct_candidates(lambda i: f"SELECT {i} FROM pets")) == 2


def test_renamed_aliases_and_always_true_conditions_are_not_a_different_query(tmp_path):
    from querygenie.pipeline import structural_key
    schema = _schema(tmp_path)
    same = ["SELECT DISTINCT kind FROM pets", "SELECT DISTINCT T1.kind FROM pets AS T1",
            "SELECT DISTINCT T.kind FROM pets AS T", "SELECT DISTINCT kind FROM pets WHERE 1=1"]
    assert len({structural_key(q, schema) for q in same}) == 1
    different = ["SELECT kind FROM pets GROUP BY kind", "WITH k AS (SELECT kind FROM pets) SELECT DISTINCT kind FROM k"]
    assert len({structural_key(q, schema) for q in same + different}) == 3
