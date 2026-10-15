"""
The CodeS inference pipeline as evaluated in the reproduction (harness v2), shared by
the Spider evaluation (research/reproduction/eval_spider_full.py) and the application.

  prompt     = schema sequence + matched contents + question (+ BOS), exactly as the
               authors' prepare_text2sql_prefix_sequence builds it
  candidates = 4 beams, all returned; post-processed like text2sql_zero_shot.py
  selection  = first candidate that passes EXPLAIN QUERY PLAN, else beam 0
  confidence = execution agreement among the 4 candidates, beam probability as
               tie-breaker (Week-11 abstention, results/week11_abstention.md)

Authors' code is vendored unmodified in querygenie/vendor/ (Apache-2.0).
"""
from __future__ import annotations

import hashlib
import math
import os
import re
import sqlite3
from dataclasses import dataclass, field

from .vendor.codes_db_utils import (get_db_schema, get_db_schema_sequence,
                                    get_matched_content_sequence, check_sql_executability,
                                    detect_special_char)
from .vendor.codes_bridge import get_matched_entries, get_column_picklist

# Abstention threshold on the confidence score (agreement + 0.01 * beam probability).
# Median of the 10 calibration-half thresholds chosen for >= 90% coverage on Spider dev
# with SFT CodeS-1B (run T2-006; values 0.25256-0.25265, results/abstention_T2-006.json).
# In words: abstain when no candidate executes, or when only 1 of 4 candidates supports
# the answer and its beam probability is below ~0.26.
ABSTAIN_TAU = 0.2526
MAX_PROMPT_TOKENS = 4096 - 256          # load_sft_dataset.prepare_inputs


def load_db_comments(tables_json_path):
    """Table/column descriptions from a Spider-style tables.json, built exactly as the
    authors' prepare_sft_datasets.py does (descriptions that merely repeat the name dropped)."""
    import json

    def rsc(names, comments):
        return ["" if n.replace("_", "").replace(" ", "") == c.replace("_", "").replace(" ", "") else c
                for n, c in zip(names, comments)]
    out = {}
    for d in json.load(open(tables_json_path)):
        cn = [c.lower() for _, c in d["column_names_original"]]
        ti = [t for t, _ in d["column_names_original"]]
        cc = rsc(cn, [c.lower() for _, c in d["column_names"]])
        tn = [t.lower() for t in d["table_names_original"]]
        tc = rsc(tn, [t.lower() for t in d["table_names"]])
        out[d["db_id"]] = {t: {"table_comment": tcm,
                               "column_comments": {c: m for tix, c, m in zip(ti, cn, cc) if tix == k}}
                           for k, (t, tcm) in enumerate(zip(tn, tc))}
    return out


def post_process(sql, schema_items):
    """Authors' text2sql_zero_shot.post_process: backtick-quote special column names."""
    sql = sql.replace("\n", " ")
    for table in schema_items:
        for cn in table["column_names"]:
            if detect_special_char(cn) and cn in sql:
                sql = sql.replace(cn, "`" + cn + "`")
    while "``" in sql:
        sql = sql.replace("``", "`")
    return sql


def normalise_sql(sql):
    """The same query written with different spacing or capitals maps to one string, so duplicate
    beam candidates (e.g. "ORDER BY age DESC" twice, spaced differently) can be recognised."""
    s = re.sub(r"\s+", " ", (sql or "").lower())
    s = re.sub(r"\s*([(),=<>+\-*/])\s*", r"\1", s)
    return s.strip().rstrip(";").strip()


def canonical_sql(text, schema):
    """What a candidate becomes after the evaluation's own clean-up, in a spacing/capitals-insensitive form:
    two candidates with the same canonical form are the same query."""
    return normalise_sql(clean_sql(post_process(text, schema["schema_items"])))

def structural_key(text, schema):
    """A stricter 'same query' test than canonical_sql, used by the application when it asks a model for different
    queries: table aliases, column qualifiers on a one-table query and a trivial WHERE 1 = 1 do not make a query
    different. Falls back to canonical_sql when the text does not parse."""
    base = canonical_sql(text, schema)
    if not base:
        return base
    try:
        import sqlglot
        from sqlglot import exp
        tree = sqlglot.parse_one(base, read="sqlite")
        tables = list(tree.find_all(exp.Table))
        names = [t.name for t in tables]
        alias_of = {t.alias: t.name for t in tables if t.alias and names.count(t.name) == 1}
        for col in tree.find_all(exp.Column):
            if col.table in alias_of:
                col.set("table", exp.to_identifier(alias_of[col.table]))
            if len(tables) == 1 and col.table:
                col.set("table", None)
        for t in tables:
            if t.alias in alias_of:
                t.set("alias", None)
        where = tree.args.get("where")
        if where is not None and isinstance(where.this, exp.EQ) and where.this.left == where.this.right \
                and isinstance(where.this.left, exp.Literal):
            tree.set("where", None)
        return tree.sql(dialect="sqlite").lower()
    except Exception:  # noqa: BLE001 - an odd query must never stop an answer
        return base


def distinct_first(texts, scores, schema, n):
    """The first n candidates (in the given order, i.e. most likely first) that are different queries.
    If fewer than n different queries exist among them, the list is filled with the repeats in order,
    so the answer count stays n and agreement keeps its meaning (a question the model answers one way
    shows that one query, repeated). Returns (texts, scores)."""
    chosen, repeats, seen = [], [], set()
    for t, s in zip(texts, scores):
        key = canonical_sql(t, schema)
        (repeats if key in seen or not key else chosen).append((t, s))
        seen.add(key)
    if len(chosen) < n:
        chosen = chosen + repeats
    chosen = chosen[:n]
    return [t for t, _ in chosen], [s for _, s in chosen]


def clean_sql(text):
    text = text.strip().replace("```sql", "").replace("```", "").strip()
    return text.split(";")[0].strip()


def matched_contents_for(path, schema, question):
    """Authors' fine value matching over every column's distinct values. As in their
    content index (build_contents_index.py): str(value) for every column, numbers
    included, empty and >25-character values dropped."""
    fine = {}
    for table in schema["schema_items"]:
        tname = table["table_name"]
        for cname in table["column_names"]:
            try:
                picklist = get_column_picklist(tname, cname, path)
            except Exception:
                continue
            vals = []
            for v in picklist:
                if v is None:
                    continue
                if isinstance(v, bytes):
                    try:
                        v = v.decode("utf-8")
                    except UnicodeDecodeError:
                        v = v.decode("latin-1")
                v = str(v).strip()
                if 0 < len(v) <= 25 and v not in vals:
                    vals.append(v)
            picklist = sorted(vals)
            if not picklist:
                continue
            fm = get_matched_entries(question, picklist)
            if not fm:
                continue
            tc = f"{tname}.{cname}"
            for _m, (field_value, _s, match_score, _sm, _sz) in fm:
                if match_score < 0.9:
                    continue
                fv = field_value.strip()
                fine.setdefault(tc, [])
                if len(fine[tc]) < 25 and fv not in fine[tc]:
                    fine[tc].append(fv)
    return fine


def matched_contents_from_index(index, question):
    """The same fine matching as matched_contents_for, over a prebuilt value index
    {"table.column": [values]} — used for connected (non-SQLite) databases."""
    fine = {}
    for tc, picklist in index.items():
        fm = get_matched_entries(question, picklist)
        if not fm:
            continue
        for _m, (field_value, _s, match_score, _sm, _sz) in fm:
            if match_score < 0.9:
                continue
            fv = field_value.strip()
            fine.setdefault(tc, [])
            if len(fine[tc]) < 25 and fv not in fine[tc]:
                fine[tc].append(fv)
    return fine


def build_prefix_connected(source, question):
    """Prompt for a connected database: introspected schema + matches from its value index."""
    question = question.replace("\n", " ")
    schema = source.introspect()
    content_seq = get_matched_content_sequence(matched_contents_from_index(source.build_index(), question))
    return schema, get_db_schema_sequence(schema) + "\n" + content_seq + "\n" + question + "\n"


def build_prefix(db_path, question, db_comments=None, schema=None):
    """Return (schema dict, prompt text) for one question."""
    question = question.replace("\n", " ")
    if schema is None:
        db_id = os.path.splitext(os.path.basename(db_path))[0]
        schema = get_db_schema(db_path, db_comments or {}, db_id)
    schema_seq = get_db_schema_sequence(schema)
    content_seq = get_matched_content_sequence(matched_contents_for(db_path, schema, question))
    return schema, schema_seq + "\n" + content_seq + "\n" + question + "\n"


def encode(tok, prefix):
    ids = [tok.bos_token_id] + tok(prefix, truncation=False)["input_ids"]
    if len(ids) > MAX_PROMPT_TOKENS:     # authors keep the END (the question)
        ids = [tok.bos_token_id] + ids[-(MAX_PROMPT_TOKENS - 1):]
    return ids


def _run_rows(path, sql):
    # read-only: generated SQL can never modify the database
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.text_factory = lambda b: b.decode(errors="ignore")
    try:
        cur = con.execute(sql)
        cols = [d[0] for d in cur.description] if cur.description else []
        return cols, cur.fetchall()
    finally:
        con.close()


def result_signature(path, sql, timeout_s=30):
    """(ok, columns, rows, hash). The hash is computed exactly as in the evaluation dump
    (md5 of the repr of the sorted, stringified rows), so agreement means the same thing
    in the app as in the measured results."""
    from func_timeout import func_timeout, FunctionTimedOut
    try:
        cols, rows = func_timeout(timeout_s, _run_rows, args=(path, sql))
    except FunctionTimedOut:
        return False, [], [], None, "query timed out"
    except Exception as exc:  # noqa: BLE001
        return False, [], [], None, f"{type(exc).__name__}: {exc}"
    canon = sorted([tuple(str(c) for c in r) for r in rows])
    return True, cols, rows, hashlib.md5(repr(canon).encode()).hexdigest(), ""


@dataclass
class Candidate:
    sql: str
    beam_score: float
    runs: bool = False
    columns: list = field(default_factory=list)
    rows: list = field(default_factory=list)
    result_hash: str | None = None
    error: str = ""


@dataclass
class Decision:
    candidates: list[Candidate]
    selected: int                  # index into candidates (-1: nothing usable)
    agreement: float               # share of the 4 candidates with the same result
    beam_prob: float               # softmax over the 4 beam scores, selected one
    confidence: float
    abstain: bool

    @property
    def n_agree(self) -> int:
        return round(self.agreement * len(self.candidates))

    def interpretations(self, limit=3):
        """Distinct executable results, most-supported first: the options offered to the
        user when the system abstains."""
        groups = {}
        for i, c in enumerate(self.candidates):
            if c.runs:
                groups.setdefault(c.result_hash, []).append(i)
        ordered = sorted(groups.values(), key=lambda idx: (-len(idx), idx[0]))
        return [(idx[0], len(idx)) for idx in ordered[:limit]]


class SqliteTarget:
    """A local SQLite file, executed exactly as in the evaluation."""

    def __init__(self, path):
        self.path = path

    def signature(self, sql):
        return result_signature(self.path, sql)

    def explain_ok(self, sql):
        return check_sql_executability(sql, self.path) is None


def decide(target, schema, raw_candidates, beam_scores):
    """Post-process, execute and select exactly as in the evaluation, then score.
    `target` is a SQLite path (the evaluated setting) or a connected source with the same
    signature() / explain_ok() methods (connectors.SqlAlchemySource)."""
    if isinstance(target, str):
        target = SqliteTarget(target)
    cands = []
    for text, score in zip(raw_candidates, beam_scores):
        sql = clean_sql(post_process(text, schema["schema_items"]))
        ok, cols, rows, h, err = target.signature(sql) if sql else (False, [], [], None, "empty")
        cands.append(Candidate(sql, float(score), ok, cols, rows, h, err))
    selected = next((i for i, c in enumerate(cands) if c.sql and target.explain_ok(c.sql)), 0)
    m = max(c.beam_score for c in cands)
    exps = [math.exp(c.beam_score - m) for c in cands]
    beam_prob = exps[selected] / sum(exps)
    h = cands[selected].result_hash if cands[selected].runs else None
    agreement = (sum(1 for c in cands if c.result_hash is not None and c.result_hash == h) / len(cands)
                 if h is not None else 0.0)
    confidence = agreement + 0.01 * beam_prob
    return Decision(cands, selected, agreement, beam_prob, confidence, confidence < ABSTAIN_TAU)
