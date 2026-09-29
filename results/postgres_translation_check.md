# Live-database connector — SQLite → PostgreSQL translation check (2026-09-30)

**Question:** CodeS writes SQLite-style SQL (it was fine-tuned on Spider, which is SQLite). When
QueryGenie is connected to a PostgreSQL server, `src/connectors.py` translates each query with
sqlglot and runs it read-only. Does the translated query return the same answer?

**Method** (`scripts/check_postgres_translation.py`, no model needed): the 20 Spider dev databases
were copied into PostgreSQL 14 (`scripts/load_spider_into_postgres.py`; 2 foreign keys rejected by
the data, all primary keys kept). For all 1,034 dev questions, the gold query and our saved T2-006
prediction were run on SQLite and, translated, on PostgreSQL. Results are compared as multisets of
rows, numbers compared by value to 6 decimal places.

| | Same answer on PostgreSQL | Different rows | Error on PostgreSQL |
|---|---|---|---|
| First version (plain sqlglot translation) | gold 67.0% · predictions 71.1% | 53 · 54 | 288 · 237 |
| **Current version** | **gold 94.4% (976/1034) · predictions 93.7% (943/1006)** | 41 · 49 | 17 · 14 |

(28 predictions that already fail on SQLite are excluded from the prediction rate.)

**What the current version rewrites** — SQLite behaviours CodeS relies on:
1. `"double-quoted"` text that is not a column name → a string literal (SQLite's rule).
2. `LIKE` → `ILIKE` on PostgreSQL (SQLite's LIKE ignores case).
3. Non-grouped columns next to aggregates → wrapped in `MAX()`.
4. `%` escaped for the PostgreSQL/MySQL drivers; NULL ordering handled by sqlglot.

**Remaining differences, stated:** of the 41 gold / 49 prediction mismatches, 27 / 35 are
`ORDER BY … LIMIT` queries, where tied rows may legitimately differ between engines. The rest, and
the 17 / 14 errors, include SQLite's "column next to MIN/MAX returns the row holding the min/max"
idiom, which is deliberately not rewritten — such a candidate fails, lowers agreement, and the app
abstains rather than answering wrongly — and a few type-dependent functions (e.g. `AVG` over a
text column).

**Not yet measured:** end-to-end accuracy of generated queries on PostgreSQL (a qualitative run of
12 `concert_singer` questions through the app: 10 matched the gold answer), confidence
calibration on PostgreSQL, and MySQL (supported by the code, not yet tested against a server).
