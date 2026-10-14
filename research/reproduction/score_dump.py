"""
Score a raw candidate dump locally with the official Spider execution match - the same per-candidate
step the Colab harness runs (research/reproduction/colab_eval_tier2.py), so a run is not lost if Colab dies while
scoring. Writes results/dump_<RUN>.jsonl with official_correct and selected_official_correct.

    python research/reproduction/score_dump.py results/dump_CN-008_raw.jsonl --evaluator /path/to/test-suite-sql-eval
"""
from __future__ import annotations

import argparse
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SPIDER = os.path.join(REPO, "data", "spider_full", "spider_data")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("raw")
    ap.add_argument("--evaluator", required=True, help="clone of taoyds/test-suite-sql-eval")
    args = ap.parse_args()
    sys.path.insert(0, args.evaluator)
    from exec_eval import eval_exec_match

    rows = [json.loads(l) for l in open(args.raw)]
    for n, d in enumerate(rows):
        path = os.path.join(SPIDER, "database", d["db_id"], d["db_id"] + ".sqlite")
        scores = []
        for c in d["candidates"]:
            try:
                scores.append(int(bool(eval_exec_match(db=path, p_str=c.replace("\n", " ").replace("\t", " "), g_str=d["gold"],
                                                       plug_value=False, keep_distinct=False, progress_bar_for_each_datapoint=False))))
            except Exception:  # noqa: BLE001 - as in the harness: an unscorable candidate counts as wrong
                scores.append(0)
        d["official_correct"] = scores
        d["selected_official_correct"] = scores[d["selected"]] if d["selected"] >= 0 else 0
        if (n + 1) % 100 == 0:
            print(f"{n + 1}/{len(rows)}", flush=True)
    out = args.raw.replace("_raw.jsonl", ".jsonl")
    with open(out, "w") as f:
        for d in rows:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    ex = sum(d["selected_official_correct"] for d in rows) / len(rows)
    print(f"official EX (per question) = {ex:.4f} ({sum(d['selected_official_correct'] for d in rows)}/{len(rows)}) -> {out}")


if __name__ == "__main__":
    main()
