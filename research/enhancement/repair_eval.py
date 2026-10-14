"""
What does execution-guided self-correction (querygenie/repair.py) do to the evaluated pipeline?

Isolates the repair step: the four candidate queries are taken from the saved record of run T2-006
(results/dump_T2-006.jsonl), not generated again, so the only difference between "before" and "after"
is the repair. For every question with a failing candidate, each distinct failed query is sent back to
CodeS-1B once with its error (greedy), the repaired set goes through the same selection and agreement
code as the evaluation, and the selected query is scored with the official execution match.

    python research/enhancement/repair_eval.py --evaluator /path/to/test-suite-sql-eval [--model path]
    -> results/repair_eval.json, results/repair_eval.md   (repairs cached in results/repair_cache_T2-006.jsonl)
"""
import argparse
import json
import os
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)
SPIDER = os.path.join(REPO, "data", "spider_full", "spider_data")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--evaluator", required=True)
    ap.add_argument("--model", default=os.path.expanduser("~/Library/Application Support/QueryGenie/models/codes-1b-spider"))
    ap.add_argument("--dump", default=os.path.join(REPO, "results", "dump_T2-006.jsonl"))
    args = ap.parse_args()
    sys.path.insert(0, args.evaluator)
    from exec_eval import eval_exec_match                      # the official execution match
    from querygenie.model import CodesSFTBackend
    from querygenie.pipeline import ABSTAIN_TAU, build_prefix, decide, load_db_comments
    from querygenie.repair import self_correct

    rows = [json.loads(l) for l in open(args.dump)]
    dev = json.load(open(os.path.join(SPIDER, "dev.json")))
    comments = load_db_comments(os.path.join(SPIDER, "tables.json"))
    cache_path = os.path.join(REPO, "results", "repair_cache_T2-006.jsonl")
    cache = {}
    if os.path.exists(cache_path):
        for l in open(cache_path):
            c = json.loads(l); cache[(c["i"], c["from"])] = c["to"]
    backend = CodesSFTBackend(args.model, label="CodeS-1B (Spider)")

    class Cached:                                               # reuse earlier repairs when re-run
        def __init__(self, i): self.i = i
        def fix_sql(self, sql, err):
            if (self.i, sql) not in cache:
                cache[(self.i, sql)] = backend.fix_sql(sql, err)
                with open(cache_path, "a") as f:
                    f.write(json.dumps({"i": self.i, "from": sql, "to": cache[(self.i, sql)]}) + "\n")
            return cache[(self.i, sql)]

    out, same_selection, t0 = [], 0, time.time()
    for n, (r, q) in enumerate(zip(rows, dev)):
        assert r["question"] == q["question"]
        db = q["db_id"]
        path = os.path.join(SPIDER, "database", db, db + ".sqlite")
        schema, prefix = build_prefix(path, q["question"], db_comments=comments)
        before = decide(path, schema, r["candidates"], r["beam_scores"])
        same_selection += before.selected == r["selected"]
        rec = {"i": r["i"], "before_correct": int(r["selected_official_correct"]), "before_conf": before.confidence,
               "before_runs": before.candidates[before.selected].runs}
        if all(c.runs for c in before.candidates):
            rec.update(after_correct=rec["before_correct"], after_conf=before.confidence, after_runs=rec["before_runs"], repaired=0)
        else:
            backend.last_context = (path, schema, prefix)
            wrapper = Cached(r["i"]); wrapper.last_context = backend.last_context
            after, repairs = self_correct(wrapper, before)
            sel = after.candidates[after.selected]
            if sel.sql == before.candidates[before.selected].sql:
                correct = rec["before_correct"]
            else:
                correct = int(bool(sel.runs) and eval_exec_match(path, sel.sql, q["query"], plug_value=False,
                                                                keep_distinct=False, progress_bar_for_each_datapoint=False))
            rec.update(after_correct=correct, after_conf=after.confidence, after_runs=sel.runs, repaired=len(repairs),
                       repaired_ran=sum(x["runs"] for x in repairs.values()))
        out.append(rec)
        if (n + 1) % 100 == 0:
            print(f"{n + 1}/{len(rows)}  {time.time() - t0:.0f}s", flush=True)

    def summary(key):
        correct = sum(o[f"{key}_correct"] for o in out)
        ans = [o for o in out if o[f"{key}_runs"] and o[f"{key}_conf"] >= ABSTAIN_TAU]
        return {"ex": round(100 * correct / len(out), 2), "correct": correct,
                "balanced_coverage": round(100 * len(ans) / len(out), 2),
                "balanced_accuracy": round(100 * sum(o[f"{key}_correct"] for o in ans) / len(ans), 2)}
    touched = [o for o in out if o.get("repaired")]
    res = {"questions": len(out), "selection_matches_T2-006": same_selection,
           "questions_with_a_failed_candidate": sum(1 for o in out if "repaired_ran" in o),
           "queries_repaired": sum(o.get("repaired", 0) for o in out),
           "repaired_queries_that_run": sum(o.get("repaired_ran", 0) for o in out),
           "answers_changed": sum(o["before_correct"] != o["after_correct"] for o in out),
           "now_correct": sum(o["after_correct"] > o["before_correct"] for o in out),
           "now_wrong": sum(o["after_correct"] < o["before_correct"] for o in out),
           "before": summary("before"), "after": summary("after"), "model": args.model, "dump": args.dump}
    json.dump(res, open(os.path.join(REPO, "results", "repair_eval.json"), "w"), indent=2)
    b, a = res["before"], res["after"]
    md = ["# Self-correction (repair) on the evaluated pipeline", "",
          "Generated by `research/enhancement/repair_eval.py`. Candidates from run T2-006; only the repair step differs.", "",
          f"- Questions with at least one failing candidate: {res['questions_with_a_failed_candidate']} of {res['questions']}",
          f"- Failed queries sent back for repair: {res['queries_repaired']}; repaired queries that run: {res['repaired_queries_that_run']}",
          f"- Answers that became correct: {res['now_correct']}; became wrong: {res['now_wrong']}",
          f"- Selection recomputed from the record matches T2-006 on {res['selection_matches_T2-006']} of {res['questions']} questions", "",
          "| | Without repair | With repair |", "|---|---|---|",
          f"| Execution accuracy, answering everything | {b['ex']}% ({b['correct']}) | {a['ex']}% ({a['correct']}) |",
          f"| Balanced setting: questions answered | {b['balanced_coverage']}% | {a['balanced_coverage']}% |",
          f"| Balanced setting: accuracy on answered | {b['balanced_accuracy']}% | {a['balanced_accuracy']}% |"]
    open(os.path.join(REPO, "results", "repair_eval.md"), "w").write("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
