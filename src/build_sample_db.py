"""
Create the bundled sample SQLite database(s) the prototype demos against.

Run once (the app calls ensure_sample_dbs() on startup, so you rarely need to
run this by hand):

    python src/build_sample_db.py

Databases are written to src/sample_data/ and are small enough to commit.
"""

from __future__ import annotations

import os
import sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE_DIR = os.path.join(HERE, "sample_data")

ACADEMIC_DB = os.path.join(SAMPLE_DIR, "academic.sqlite")


def build_academic(path: str = ACADEMIC_DB) -> str:
    """A small college schema — the running example from the project brief,
    expanded enough that aggregate / group-by / having questions are interesting."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        os.remove(path)
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE student (
            student_id INTEGER PRIMARY KEY,
            name       TEXT,
            department TEXT,
            year       INTEGER
        );
        CREATE TABLE result (
            result_id  INTEGER PRIMARY KEY,
            student_id INTEGER REFERENCES student(student_id),
            subject    TEXT,
            marks      INTEGER
        );
        INSERT INTO student VALUES
            (1,'Asha','CSE',3),(2,'Ravi','CSE',3),(3,'Meera','IT',2),
            (4,'Karthik','ECE',3),(5,'Divya','IT',2),(6,'Sana','CSE',1);
        INSERT INTO result VALUES
            (1,1,'DBMS',35),(2,1,'OS',30),(3,1,'CN',72),
            (4,2,'DBMS',55),(5,2,'OS',61),(6,2,'CN',48),
            (7,3,'DBMS',20),(8,3,'OS',25),(9,3,'CN',38),
            (10,4,'DBMS',66),(11,4,'OS',58),(12,4,'CN',41),
            (13,5,'DBMS',33),(14,5,'OS',39),(15,5,'CN',44),
            (16,6,'DBMS',80),(17,6,'OS',75),(18,6,'CN',90);
        """
    )
    con.commit()
    con.close()
    return path


# name -> (path, one-line description) for the app's DB picker
SAMPLE_DBS = {
    "academic (students & results)": ACADEMIC_DB,
}


def ensure_sample_dbs() -> dict[str, str]:
    """Build any missing sample DBs and return the {label: path} mapping."""
    if not os.path.exists(ACADEMIC_DB):
        build_academic()
    return SAMPLE_DBS


if __name__ == "__main__":
    p = build_academic()
    print("built", p)
