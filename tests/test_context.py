"""Follow-up context in chats (querygenie/context.py, desktop/api.py) — no model needed."""
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT, os.path.join(ROOT, "desktop")]
from querygenie.context import combined_question, history_block, linking_text  # noqa: E402
from querygenie.providers.base import CandidateBackend  # noqa: E402

HIST = [{"question": "Which students failed more than two subjects?", "sql": "SELECT name FROM student ..."}]


def test_context_texts():
    assert combined_question(None, "only CSE") == "only CSE"
    assert combined_question(HIST, "only from CSE") == "Which students failed more than two subjects? Follow-up: only from CSE"
    assert linking_text(HIST, "only CSE").startswith("Which students failed") and linking_text([], "x") == "x"
    block = history_block(HIST)
    assert "Question: Which students failed" in block and "SQL used: SELECT name" in block and history_block([]) == ""


def _db(tmp_path):
    p = str(tmp_path / "s.sqlite")
    con = sqlite3.connect(p)
    con.executescript("CREATE TABLE student (id INTEGER PRIMARY KEY, name TEXT, department TEXT);"
                      "INSERT INTO student VALUES (1,'Asha','CSE'),(2,'Ravi','IT');")
    con.commit(); con.close()
    return p


class Echo(CandidateBackend):
    """Records the prompt it was given."""
    def raw_candidates(self, prompt):
        self.prompt = prompt
        return ["SELECT name FROM student WHERE department = 'CSE'"] * 4


def test_chat_models_see_the_conversation(tmp_path):
    be, path = Echo("echo"), _db(tmp_path)
    be.decide(path, "only from CSE", history=HIST)
    assert "Earlier in this conversation" in be.prompt and "Question: only from CSE" in be.prompt
    be.decide(path, "How many students?")                               # no history: nothing extra
    assert "Earlier in this conversation" not in be.prompt


def test_context_window_stops_at_a_new_topic(tmp_path, monkeypatch):
    import api
    monkeypatch.setattr(api, "HISTORY_DB", str(tmp_path / "h.sqlite"))
    a = api.Api.__new__(api.Api); a._decisions = {}; a._init_history()
    cid = a._new_chat("db", "q1")
    r = lambda q, brk=False: {"question": q, "agree": 4, "answered": True, "ran": True, "selected": 0,
                              "candidates": [{"sql": f"SQL for {q}"}], "context_break": brk}
    for q, brk in [("q1", False), ("q2", True), ("q3", False), ("q4", False)]:
        a._save_history("db", q, r(q, brk), cid)
    assert [h["question"] for h in a._context(cid, 5)] == ["q2", "q3", "q4"]   # q2 started a new topic
    assert [h["question"] for h in a._context(cid, 2)] == ["q3", "q4"]
    assert a._context(cid, 0) == [] and a._context(None, 3) == []
    assert a._context(cid, 1)[0]["sql"] == "SQL for q4"


def test_value_swap_follow_ups():
    from querygenie.context import substitute
    prev = [{"question": "Which students are in the CSE department?"}]
    match = lambda t: {"student.department": ["CSE"]} if "CSE" in t else {}
    values = lambda col: ["CSE", "IT", "ECE"]                       # the retriever skips "IT"; stored values don't
    assert substitute(prev, "what about IT?", match, values) == "Which students are in the IT department?"
    assert substitute(prev, "how many are there?", match, values) is None          # not a swap
    assert substitute(prev, "and what about it?", match, values) is None           # the word "it", not the value
    assert substitute(prev, "what about the students who failed more than two subjects in IT?", match, values) is None  # too long
    assert substitute([], "what about IT?", match, values) is None
