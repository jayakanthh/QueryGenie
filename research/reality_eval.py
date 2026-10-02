"""
Benchmark-to-reality gap, part 1: Spider-Realistic (Deng et al. 2020, arXiv:2010.12773).

Spider-Realistic rewrites 508 Spider dev questions so they no longer name the columns ("from the
oldest to the youngest" instead of "ordered by age"), keeping the databases and gold SQL. Each
question therefore has an original twin, and both are run here through the evaluated pipeline
(querygenie/pipeline.py, the same code as T2-006: full CodeS prompt, 4 beams, first-executable
selection, agreement) on the same machine, so the only difference is the wording. The selected
query is scored with the official Spider execution match (taoyds/test-suite-sql-eval exec_eval).

Data: data/spider_realistic/dev.json from Hugging Face (aherntech/spider-realistic, a copy of the
authors' Zenodo release, CC BY-SA 4.0); databases from Spider (xlangai/spider).

    python research/reality_eval.py --evaluator /path/to/test-suite-sql-eval [--limit N]

Resumable: records go to results/reality/spider_realistic_<run>.jsonl, one line per question and
version; a re-run skips what is there.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
SPIDER = os.path.join(REPO, "data", "spider_full", "spider_data")
REALISTIC = os.path.join(REPO, "data", "spider_realistic", "dev.json")
OUT = os.path.join(REPO, "results", "reality")


def pairs():
    """(index in Spider dev, Spider dev item, realistic item): matched in order on db_id and gold SQL."""
    dev = json.load(open(os.path.join(SPIDER, "dev.json")))
    real = json.load(open(REALISTIC))
    out, j = [], 0
    norm = lambda s: " ".join(s.split()).lower()
    for r in real:
        while j < len(dev) and not (dev[j]["db_id"] == r["db_id"] and norm(dev[j]["query"]) == norm(r["query"])):
            j += 1
        if j == len(dev):
            raise SystemExit(f"no Spider dev twin for: {r['question']}")
        out.append((j, dev[j], r))
        j += 1
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--evaluator", required=True, help="clone of taoyds/test-suite-sql-eval")
    ap.add_argument("--model", default=os.path.expanduser("~/Library/Application Support/QueryGenie/models/codes-1b-spider"))
    ap.add_argument("--run-id", default="RL-001")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    sys.path.insert(0, args.evaluator)
    from exec_eval import eval_exec_match
    import torch
    from querygenie.model import CodesSFTBackend
    from querygenie.pipeline import load_db_comments

    torch.manual_seed(42)
    os.makedirs(OUT, exist_ok=True)
    path_out = os.path.join(OUT, f"spider_realistic_{args.run_id}.jsonl")
    done = set()
    if os.path.exists(path_out):
        for line in open(path_out):
            r = json.loads(line)
            done.add((r["i"], r["version"]))
    comments = load_db_comments(os.path.join(SPIDER, "tables.json"))
    backend = CodesSFTBackend(args.model, label="CodeS-1B (Spider)")
    items = pairs()[: args.limit or None]
    t0, n = time.time(), 0
    with open(path_out, "a") as f:
        for i, orig, real in items:
            db = orig["db_id"]
            path = os.path.join(SPIDER, "database", db, db + ".sqlite")
            for version, question in (("original", orig["question"]), ("realistic", real["question"])):
                if (i, version) in done:
                    continue
                t = time.time()
                d = backend.decide(path, question, comments.get(db))
                sel = d.candidates[d.selected]
                correct = int(bool(sel.runs) and bool(eval_exec_match(
                    db=path, p_str=sel.sql, g_str=orig["query"], plug_value=False, keep_distinct=False,
                    progress_bar_for_each_datapoint=False)))
                f.write(json.dumps({"i": i, "version": version, "db_id": db, "question": question, "gold": orig["query"],
                                    "candidates": [c.sql for c in d.candidates], "beam_scores": [c.beam_score for c in d.candidates],
                                    "selected": d.selected, "runs": sel.runs, "agreement": d.agreement,
                                    "confidence": d.confidence, "correct": correct,
                                    "prompt_tokens": backend.calls[0]["prompt"] if backend.calls else None,
                                    "seconds": round(time.time() - t, 2)}) + "\n")
                f.flush()
                n += 1
            if n and n % 50 == 0:
                print(f"{n} done  {time.time() - t0:.0f}s", flush=True)
    meta = {"run_id": args.run_id, "model": args.model, "machine": platform.platform(),
            "device": backend.device, "torch": torch.__version__, "seconds": round(time.time() - t0),
            "questions": len(items)}
    json.dump(meta, open(os.path.join(OUT, f"spider_realistic_{args.run_id}.meta.json"), "w"), indent=2)
    print(json.dumps(meta))


if __name__ == "__main__":
    main()
