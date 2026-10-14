"""
Benchmark-to-reality gap, part 2: BIRD Mini-Dev (Li et al. 2023, arXiv:2305.03111).

BIRD's databases are real-world (sports, finance, medicine, schools...): large tables, dirty values,
domain knowledge. Mini-Dev is the BIRD authors' 500-question subset of BIRD dev over 11 databases.
The model is the one the application ships and that was reproduced on Spider (CodeS-1B fine-tuned
on Spider) - this measures how that system holds up on real-world databases, not CodeS's BIRD result
(the paper fine-tunes separate BIRD models for that).

Setup, as in the authors' prepare_sft_datasets.py for BIRD with evidence:
  - input text = preprocessed evidence + " " + question
  - schema prompt, comments from dev_tables.json, 4 beams, first-executable selection, agreement:
    the evaluated pipeline (querygenie/pipeline.py)
  - value retrieval: coarse search over all database values, then the authors' fine matching.
    DEVIATION: the coarse stage is a token index in Python, not their Lucene BM25 index (no Java);
    for every 1-4-gram of the text it keeps up to 10 stored values containing the gram's words.
Scoring: BIRD's execution accuracy - set(predicted rows) == set(gold rows) - as in the BIRD
evaluation script; queries time out after 30 s.

Data (Hugging Face): questions birdsql/bird_mini_dev (official, CC BY-SA 4.0, SQLite version);
databases and dev_tables.json from nlile/BIRD-bench (a mirror of the BIRD dev release).

    python research/reality/bird_eval.py [--limit N] [--run-id BD-001]
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import sqlite3
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)
BIRD = os.path.join(REPO, "data", "bird")
DBDIR = os.path.join(BIRD, "dev_databases")
OUT = os.path.join(REPO, "results", "reality")
_STOP = set("a an the of in on at to for by with and or is are was were be what which who whom whose how many much "
            "list show give find name names number all each per from as that this those these there their its it "
            "do does did has have had than then please".split())


def preprocess_evidence(evidence, schema_items):
    """The authors' preprocess_evidence (prepare_sft_datasets.py)."""
    if not evidence or not evidence.strip():
        return ""
    evidence = evidence.strip()
    if not evidence.endswith(";"):
        evidence += ";"
    for table in schema_items:
        if table["table_name"] in evidence.lower():
            evidence = re.sub(re.escape(table["table_name"]), table["table_name"], evidence, 0, re.IGNORECASE)
        for column_name in table["column_names"]:
            if column_name in evidence.lower():
                evidence = re.sub(re.escape(column_name), column_name, evidence, 0, re.IGNORECASE)
    return evidence.replace("< =", "<=").replace("> =", ">=")


class ValueIndex:
    """All stored values of a database (as in the authors' content index: str(value), 1-25 chars),
    with a word -> values map for the coarse stage."""

    def __init__(self, path, schema):
        from querygenie.pipeline import get_column_picklist
        self.by_word = {}
        for table in schema["schema_items"]:
            for col in table["column_names"]:
                try:
                    values = get_column_picklist(table["table_name"], col, path)
                except Exception:  # noqa: BLE001
                    continue
                tc = f"{table['table_name']}.{col}"
                for v in values:
                    if v is None:
                        continue
                    if isinstance(v, bytes):
                        v = v.decode("utf-8", errors="ignore")
                    v = str(v).strip()
                    if not 0 < len(v) <= 25:
                        continue
                    for w in set(re.findall(r"\w+", v.lower())):
                        if w not in _STOP:
                            self.by_word.setdefault(w, []).append((tc, v))

    def coarse(self, text, k=10):
        words = [w for w in re.findall(r"\w+", text.lower())]
        grams = {" ".join(words[i:i + n]) for n in range(1, 5) for i in range(len(words) - n + 1)}
        hits = {}
        for g in grams:
            ws = [w for w in g.split() if w not in _STOP]
            if not ws:
                continue
            pool = None
            for w in ws:
                cand = self.by_word.get(w, [])
                pool = set(cand) if pool is None else pool & set(cand)
                if not pool:
                    break
            # closest in length to the gram first, like a BM25 hit on a short field
            for tc, v in sorted(pool or [], key=lambda x: (abs(len(x[1]) - len(g)), x[1]))[:k]:
                hits.setdefault(tc, [])
                if v not in hits[tc]:
                    hits[tc].append(v)
        return hits


def fine(text, coarse):
    """The authors' fine matching on the coarse hits."""
    from querygenie.pipeline import get_matched_entries
    out = {}
    for tc, contents in coarse.items():
        fm = get_matched_entries(text, contents)
        if not fm:
            continue
        for _m, (field_value, _s, match_score, _sm, _sz) in fm:
            if match_score < 0.9:
                continue
            out.setdefault(tc, [])
            if len(out[tc]) < 25:
                out[tc].append(field_value.strip())
    return out


def bird_rows(path, sql, timeout_s=30):
    from func_timeout import FunctionTimedOut, func_timeout

    def run():
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        con.text_factory = lambda b: b.decode(errors="ignore")
        try:
            return con.execute(sql).fetchall()
        finally:
            con.close()
    try:
        return func_timeout(timeout_s, run)
    except (FunctionTimedOut, Exception):  # noqa: BLE001
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=os.path.expanduser("~/Library/Application Support/QueryGenie/models/codes-1b-spider"))
    ap.add_argument("--run-id", default="BD-001")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    import torch
    from querygenie.model import CodesSFTBackend
    from querygenie.pipeline import decide, encode, get_db_schema, get_db_schema_sequence, get_matched_content_sequence, load_db_comments

    torch.manual_seed(42)
    os.makedirs(OUT, exist_ok=True)
    qs = json.load(open(os.path.join(BIRD, "mini_dev_sqlite.json")))[: args.limit or None]
    comments = load_db_comments(os.path.join(BIRD, "dev_tables.json"))
    out_path = os.path.join(OUT, f"bird_minidev_{args.run_id}.jsonl")
    done = {json.loads(l)["question_id"] for l in open(out_path)} if os.path.exists(out_path) else set()
    backend = CodesSFTBackend(args.model, label="CodeS-1B (Spider)")
    backend.load()
    schemas, indexes, t0, n = {}, {}, time.time(), 0
    with open(out_path, "a") as f:
        for q in qs:
            if q["question_id"] in done:
                continue
            db = q["db_id"]
            path = os.path.join(DBDIR, db, db + ".sqlite")
            if db not in schemas:
                schemas[db] = get_db_schema(path, comments, db)
                ti = time.time()
                indexes[db] = ValueIndex(path, schemas[db])
                print(f"indexed {db} in {time.time() - ti:.0f}s", flush=True)
            schema = schemas[db]
            evidence = preprocess_evidence(q.get("evidence", ""), schema["schema_items"])
            text = (evidence + " " + q["question"] if evidence else q["question"]).replace("\n", " ")
            t = time.time()
            matched = fine(text, indexes[db].coarse(text))
            prefix = get_db_schema_sequence(schema) + "\n" + get_matched_content_sequence(matched) + "\n" + text + "\n"
            ids = torch.tensor([encode(backend._tok, prefix)], device=backend.device)
            with torch.no_grad():
                gen = backend._model.generate(input_ids=ids, attention_mask=torch.ones_like(ids), max_new_tokens=256,
                                              num_beams=4, num_return_sequences=4, pad_token_id=backend._tok.eos_token_id,
                                              return_dict_in_generate=True, output_scores=True)
            texts = backend._tok.batch_decode(gen.sequences[:, ids.shape[1]:], skip_special_tokens=True,
                                              clean_up_tokenization_spaces=False)
            d = decide(path, schema, texts, [float(x) for x in gen.sequences_scores])
            sel = d.candidates[d.selected]
            gold = bird_rows(path, q["SQL"])
            pred = bird_rows(path, sel.sql) if sel.runs else None
            correct = int(gold is not None and pred is not None and set(pred) == set(gold))
            f.write(json.dumps({"question_id": q["question_id"], "db_id": db, "difficulty": q.get("difficulty"),
                                "question": q["question"], "evidence": evidence, "gold": q["SQL"],
                                "candidates": [c.sql for c in d.candidates], "beam_scores": [c.beam_score for c in d.candidates],
                                "selected": d.selected, "runs": sel.runs, "agreement": d.agreement, "confidence": d.confidence,
                                "correct": correct, "gold_ran": gold is not None, "prompt_tokens": int(ids.shape[1]),
                                "truncated": int(ids.shape[1]) >= 3840, "seconds": round(time.time() - t, 2)}) + "\n")
            f.flush()
            n += 1
            if n % 25 == 0:
                print(f"{n} done  {time.time() - t0:.0f}s", flush=True)
    meta = {"run_id": args.run_id, "model": args.model, "machine": platform.platform(), "device": backend.device,
            "torch": torch.__version__, "seconds": round(time.time() - t0), "questions": len(qs),
            "coarse_value_search": "python token index (deviation from Lucene BM25)"}
    json.dump(meta, open(os.path.join(OUT, f"bird_minidev_{args.run_id}.meta.json"), "w"), indent=2)
    print(json.dumps(meta))


if __name__ == "__main__":
    main()
