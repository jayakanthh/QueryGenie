"""The "all of what?" safeguard (querygenie/mentions.py) — no model needed."""
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT, os.path.join(ROOT, "desktop")]
from querygenie.mentions import is_unclear, schema_mentions  # noqa: E402
from querygenie.pipeline import matched_contents_for  # noqa: E402
from querygenie.vendor.codes_db_utils import get_db_schema  # noqa: E402


def _db(tmp_path):
    p = str(tmp_path / "school.sqlite")
    con = sqlite3.connect(p)
    con.executescript("""
        CREATE TABLE student (student_id INTEGER PRIMARY KEY, name TEXT, department TEXT);
        CREATE TABLE result (result_id INTEGER PRIMARY KEY, student_id INTEGER REFERENCES student(student_id),
                             subject TEXT, marks INTEGER);
        CREATE TABLE Highschooler (ID INTEGER PRIMARY KEY, grade INTEGER);
        INSERT INTO student VALUES (1, 'Asha', 'CSE'), (2, 'Ravi', 'IT');
        INSERT INTO result VALUES (1, 1, 'DBMS', 91), (2, 2, 'OS', 35);
        INSERT INTO Highschooler VALUES (1, 9);""")
    con.commit(); con.close()
    return p, get_db_schema(p, {}, "school")


def unclear(path, schema, q):
    m = schema_mentions(schema, q)
    if is_unclear(m):
        m = schema_mentions(schema, q, matched_contents_for(path, schema, q))
    return is_unclear(m)


def test_vague_requests_are_unclear(tmp_path):
    path, schema = _db(tmp_path)
    for q in ["show me all", "How many are there?", "show everything", "give me the data", "what is the total?"]:
        assert unclear(path, schema, q), q


def test_questions_that_name_something_are_clear(tmp_path):
    path, schema = _db(tmp_path)
    for q in ["show me all students", "list the results", "average marks per subject",
              "Which department has the most?", "Show Asha's marks",          # a stored value
              "how many high schoolers are there?",                           # Highschooler
              "list all studnets"]:                                           # a typo
        assert not unclear(path, schema, q), q


def test_api_offers_the_tables(tmp_path):
    import api
    from querygenie.databases import DbInfo
    path, _ = _db(tmp_path)
    info = DbInfo("school", path, "test", [], {})
    a = api.Api.__new__(api.Api)
    tables = a._unclear(info, "show me all")["tables"]
    assert [t["table"] for t in tables] == ["student", "result", "Highschooler"]
    assert tables[0]["rows"] == 2 and tables[0]["columns"][:2] == ["student_id", "name"]
    assert a._unclear(info, "show me all students") is None
