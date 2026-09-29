"""Chat storage in the desktop API (desktop/api.py) — model-free."""
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "desktop"))
import api  # noqa: E402


def _api(tmp_path):
    api.HISTORY_DB = str(tmp_path / "history.sqlite")
    a = api.Api.__new__(api.Api)
    a._decisions = {}
    a._init_history()
    return a


def test_chat_thread_and_counts(tmp_path):
    a = _api(tmp_path)
    cid = a._new_chat("db1", "first question")
    a._save_history("db1", "first question", {"question": "first question", "agree": 4, "answered": True}, cid)
    h2 = a._save_history("db1", "follow up", {"question": "follow up", "agree": 2, "answered": True}, cid)
    other = a._new_chat("db2", "elsewhere")
    a._save_history("db2", "elsewhere", {"agree": 1, "answered": False}, other)

    chats = a.chats("db1")
    assert len(chats) == 1 and chats[0]["questions"] == 2 and chats[0]["agree"] == 2   # latest answer
    assert [t["question"] for t in a.chat(cid)["turns"]] == ["first question", "follow up"]
    assert a.history_counts() == {"db1": 1, "db2": 1}
    assert a.chats("db1", "follow")[0]["id"] == cid and a.chats("db1", "nothing") == []

    a.chat_rename(cid, "  Renamed  ")
    assert a.chats("db1")[0]["title"] == "Renamed"
    a.history_delete(h2)
    assert a.chats("db1")[0]["questions"] == 1
    a.chat_delete(cid)
    assert a.chats("db1") == [] and a.history_counts() == {"db2": 1}


def test_old_history_becomes_one_chat_per_question(tmp_path):
    path = tmp_path / "history.sqlite"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE history (id TEXT PRIMARY KEY, db_id TEXT, question TEXT, "
                "agree INTEGER, answered INTEGER, created TEXT, result TEXT)")
    con.execute("INSERT INTO history VALUES ('h1','db1','old q',3,1,'2026-09-01T10:00:00',?)",
                (json.dumps({"question": "old q"}),))
    con.commit(); con.close()
    a = _api(tmp_path)
    a._init_history()                                   # running twice must be harmless
    chats = a.chats("db1")
    assert [(c["id"], c["title"], c["questions"]) for c in chats] == [("h1", "old q", 1)]
