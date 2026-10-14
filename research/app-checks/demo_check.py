"""
Rehearse the Review-III demo: ask every demo question through the application exactly as on stage
(desktop/api.py, evaluated CodeS-1B, Balanced setting, no follow-up context), and compare the answer
with a hand-written correct query run on the same database.

    python research/app-checks/demo_check.py            # writes results/demo_check.json and .md

Questions are asked in a temporary chat that is deleted afterwards. CodeS is deterministic, so a
question that passes here gives the same answer on stage (same model, database and setting).
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path[:0] = [os.path.join(REPO, "desktop"), REPO]

ACADEMIC = "academic (students & results)"
# (database, question, correct SQL or None when the right behaviour is to ask, what it shows)
DEMO = [
    (ACADEMIC, "List the subjects and the average marks for each subject.",
     "SELECT subject, avg(marks) FROM result GROUP BY subject", "confident answer + bar chart"),
    (ACADEMIC, "What are the names of the students in the CSE department?",
     "SELECT name FROM student WHERE department = 'CSE'", "finds the stored value 'CSE'"),
    (ACADEMIC, "Which student scored the highest marks in DBMS?",
     "SELECT s.name FROM student s JOIN result r ON s.student_id = r.student_id WHERE r.subject = 'DBMS' ORDER BY r.marks DESC LIMIT 1",
     "join across two tables"),
    (ACADEMIC, "Show the name and average marks of every student.",
     "SELECT s.name, avg(r.marks) FROM student s JOIN result r ON s.student_id = r.student_id GROUP BY s.student_id",
     "join + group by + chart"),
    (ACADEMIC, "How many students are there in each department?",
     "SELECT department, count(*) FROM student GROUP BY department", "3 of 4 agree + chart"),
    (ACADEMIC, "Who topped each subject?", None, "the enhancement: queries disagree, it asks"),
    (ACADEMIC, "show me all", None, "vague: asks 'All of what?'"),
]


def rows(path, sql):
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def same(a, b, ordered):
    """Same rows, columns in any order (as the official Spider evaluator allows); row order only if sorted."""
    norm = lambda rs: [tuple(sorted(repr(round(v, 4) if isinstance(v, float) else v) for v in r)) for r in rs]
    a, b = norm(a), norm(b)
    return a == b if ordered else sorted(a) == sorted(b)


def main():
    import main as _app  # noqa: F401 - sets up the data folders
    from api import Api

    api = Api()
    s = api.settings_get()
    assert s.get("engine") is None and s["model"] == "codes-1b-spider", "switch the app to CodeS-1B (Spider) first"
    saved = {k: s.get(k) for k in ("context_on", "mode")}
    api.settings_set({"context_on": False})
    out, chat = [], None
    try:
        for db, q, gold, shows in DEMO:
            info = api._catalog()[db]
            t = time.time()
            r = api.ask(db, q, "balanced", None)
            chat = r["chat_id"]
            got = [tuple(x) for x in r["rows"]] if r["answered"] else None
            if gold is None:
                verdict = "asks (correct behaviour)" if (not r["answered"] or r.get("unclear")) else "answered (should have asked)"
                ok = not r["answered"] or bool(r.get("unclear"))
            else:
                ok = r["answered"] and same(got, rows(info.path, gold), "ORDER BY" in gold.upper())
                verdict = "correct" if ok else ("declined" if not r["answered"] else "WRONG")
            out.append({"db": db, "question": q, "shows": shows, "ok": bool(ok), "verdict": verdict,
                        "agree": r["agree"], "answered": r["answered"], "unclear": bool(r.get("unclear")),
                        "chart": (r.get("chart") or {}).get("kind"), "sql": r["candidates"][r["selected"]]["sql"],
                        "rows": [list(x) for x in r["rows"][:6]], "seconds": round(time.time() - t, 1)})
            api.chat_delete(chat)
            print(f"{'OK ' if ok else 'XX '} {r['agree']}/4 {verdict:28} {q}", flush=True)
    finally:
        api.settings_set(saved)
    json.dump(out, open(os.path.join(REPO, "results", "demo_check.json"), "w"), indent=2)
    md = ["# Demo rehearsal (research/app-checks/demo_check.py)", "",
          "Every demo question asked through the app (CodeS-1B, Balanced, no context) and compared with a hand-written correct query.", "",
          "| # | Question | Shows | Queries agree | Result |", "|---|---|---|---|---|"]
    md += [f"| {i} | {o['question']} | {o['shows']} | {o['agree']} of 4 | {'✅' if o['ok'] else '❌'} {o['verdict']} |"
           for i, o in enumerate(out, 1)]
    open(os.path.join(REPO, "results", "demo_check.md"), "w").write("\n".join(md) + "\n")


if __name__ == "__main__":
    main()
