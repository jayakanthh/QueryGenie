"""
Agreement v2, after the Review-III feedback. Two flaws of the evaluated agreement (v1):

  1. Repeats count twice. Beam search often returns the same query with different spacing or
     capitals ("ORDER BY age DESC" twice), so 2-of-4 can be one query counted twice.
  2. Swapped columns count as disagreement. (department, count) and (count, department) are the
     same answer - the official Spider evaluator accepts reordered columns - but v1 hashed rows in
     column order.

v2 executes every saved candidate of run T2-006 again (no model: the SQL is in the record), compares
results up to row AND column order, and counts each different query once. The selected query - and
therefore every answer and its correctness - is unchanged; only the confidence signal differs. The
signals are tested with the same 10 calibration/test splits as research/abstention.py.

    python research/agreement_v2.py            # writes results/agreement_v2.md and .json
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys

import numpy as np
from scipy import stats

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [REPO, os.path.join(REPO, "research")]
from abstention import SEEDS, at_coverage, aurc, split_trial  # noqa: E402
from querygenie.pipeline import normalise_sql  # noqa: E402

SPIDER = os.path.join(REPO, "data", "spider_full", "spider_data")
RUN = sys.argv[1] if len(sys.argv) > 1 else "T2-006"          # python research/agreement_v2.py [RUN_ID]
DUMP = os.path.join(REPO, "results", f"dump_{RUN}.jsonl")
SUFFIX = "" if RUN == "T2-006" else f"_{RUN}"                    # T2-006 keeps its original file names
CACHE = os.path.join(REPO, "results", f"agreement_v2_cache{SUFFIX}.jsonl")


def run(path, sql, timeout_s=30):
    from func_timeout import FunctionTimedOut, func_timeout

    def go():
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        con.text_factory = lambda b: b.decode(errors="ignore")
        try:
            return con.execute(sql).fetchall()
        finally:
            con.close()
    try:
        return func_timeout(timeout_s, go)
    except (FunctionTimedOut, Exception):  # noqa: BLE001
        return None


def canonical(rows):
    """Hash of a result that ignores row order and column order."""
    if rows is None:
        return None
    if not rows:
        return "empty"
    cols = list(zip(*rows))
    order = sorted(range(len(cols)), key=lambda j: sorted(map(repr, cols[j])))
    body = sorted(repr(tuple(r[j] for j in order)) for r in rows)
    return hashlib.md5(repr(body).encode()).hexdigest()


def results_for(rows):
    """Canonical result hash of every candidate, cached so a re-run takes seconds."""
    cache = {}
    if os.path.exists(CACHE):
        for line in open(CACHE):
            c = json.loads(line)
            cache[c["i"]] = c["canon"]
    with open(CACHE, "a") as f:
        for n, r in enumerate(rows):
            if r["i"] in cache:
                continue
            path = os.path.join(SPIDER, "database", r["db_id"], r["db_id"] + ".sqlite")
            canon = [canonical(run(path, q)) if q and ok else None for q, ok in zip(r["candidates"], r["exec_ok"])]
            cache[r["i"]] = canon
            f.write(json.dumps({"i": r["i"], "canon": canon}) + "\n")
            if (n + 1) % 200 == 0:
                print(f"executed {n + 1}/{len(rows)} questions", flush=True)
    return cache


def signals(r, canon):
    sel = r["selected"]
    scores = np.array(r["beam_scores"], dtype=float)
    p = np.exp(scores - scores.max()); p /= p.sum()
    p_sel = float(p[sel])
    # v1: as evaluated (all 4 candidates, result hash in column order)
    h1 = r["result_hash"][sel] if r["exec_ok"][sel] else None
    v1 = sum(1 for x in r["result_hash"] if h1 is not None and x == h1) / 4 if h1 else 0.0
    # v2: each different query once, results compared up to row and column order
    first = {}
    for q, c in zip(r["candidates"], canon):
        if q:
            first.setdefault(normalise_sql(q), c)
    h2 = canon[sel] if r["exec_ok"][sel] else None
    distinct = list(first.values())
    agree_n = sum(1 for c in distinct if h2 is not None and c == h2)
    v2_share = agree_n / len(distinct) if (distinct and h2) else 0.0
    return {"v1": v1 + 0.01 * p_sel, "v2_share": v2_share + 0.01 * p_sel, "v2_count": agree_n + 0.01 * p_sel,
            "beam_prob": p_sel, "distinct": len(distinct), "v2_agree_n": agree_n if h2 else 0,
            "v1_raw": v1, "swap_fixed": h2 is not None and agree_n > len({normalise_sql(q) for q, x in zip(r["candidates"], r["result_hash"]) if q and x == h1})}


def test(conf, correct):
    trials = [split_trial(conf, correct, s) for s in SEEDS]
    d = np.array([t["diff"] for t in trials])
    return {"aurc": aurc(conf, correct), "acc_at_90_full": at_coverage(conf, correct, 0.90),
            "mean_coverage": float(np.mean([t["coverage"] for t in trials])),
            "mean_selective_acc": float(np.mean([t["selective_acc"] for t in trials])),
            "mean_gain_vs_random": float(d.mean()),
            "t_p": float(stats.ttest_1samp(d, 0.0, alternative="greater").pvalue),
            "wilcoxon_p": float(stats.wilcoxon(d, alternative="greater").pvalue), "trials": trials}


def main():
    rows = [json.loads(l) for l in open(DUMP)]
    canon = results_for(rows)
    correct = np.array([r["selected_official_correct"] for r in rows], dtype=float)
    sig = [signals(r, canon[r["i"]]) for r in rows]
    res = {"n": len(rows), "accuracy_full_coverage": float(correct.mean())}
    for name in ("v1", "v2_share", "v2_count", "beam_prob"):
        res[name] = test(np.array([s[name] for s in sig]), correct)
    # v2 against v1 directly, split by split
    dv = np.array([a["selective_acc"] - b["selective_acc"] for a, b in zip(res["v2_share"]["trials"], res["v1"]["trials"])])
    res["v2_share_minus_v1"] = {"mean": float(dv.mean()), "per_split": dv.tolist()}
    dist = np.array([s["distinct"] for s in sig])
    res["distinct_queries"] = {str(k): int((dist == k).sum()) for k in range(1, 5)}
    res["questions_where_column_order_hid_agreement"] = int(sum(s["swap_fixed"] for s in sig))
    lv = np.array([s["v2_agree_n"] for s in sig])
    res["v2_by_agreeing_distinct_queries"] = {str(k): {"n": int((lv == k).sum()),
                                                      "accuracy": float(correct[lv == k].mean()) if (lv == k).any() else None}
                                             for k in range(0, 5)}
    json.dump(res, open(os.path.join(REPO, "results", f"agreement_v2{SUFFIX}.json"), "w"), indent=2)

    f = lambda x: f"{100 * x:.1f}%"
    md = [f"# Agreement v2 (after the Review-III feedback) — run {RUN}", "",
          f"Generated by `research/agreement_v2.py {RUN}` from the saved candidates of run {RUN} (1,034 Spider dev questions). "
          "Every candidate was executed again; the selected query, and so every answer, is unchanged. "
          "v1 = the evaluated agreement (all 4 candidates, column order significant). v2 = each different query counted "
          "once, results compared up to row and column order. Same 10 calibration/test splits as `research/abstention.py`.", "",
          f"- Different queries per question: 1 → {res['distinct_queries']['1']}, 2 → {res['distinct_queries']['2']}, "
          f"3 → {res['distinct_queries']['3']}, 4 → {res['distinct_queries']['4']}.",
          f"- Questions where column order hid agreement between different queries: {res['questions_where_column_order_hid_agreement']}.", "",
          "| Signal | Coverage (mean) | Accuracy on answered (mean of 10 test halves) | Gain vs random | t-test p | Wilcoxon p | AURC |",
          "|---|---|---|---|---|---|---|"]
    names = {"v1": "v1 — as evaluated", "v2_share": "v2 — share of different queries that agree",
             "v2_count": "v2 — number of different queries that agree", "beam_prob": "Beam probability (comparison)"}
    for k, label in names.items():
        t = res[k]
        md.append(f"| {label} | {f(t['mean_coverage'])} | {f(t['mean_selective_acc'])} | {100 * t['mean_gain_vs_random']:+.2f} pts | "
                  f"{t['t_p']:.2g} | {t['wilcoxon_p']:.2g} | {t['aurc']:.3f} |")
    md += ["", f"v2 (share) minus v1, mean over the 10 test halves: {100 * res['v2_share_minus_v1']['mean']:+.2f} pts.", "",
           "Accuracy by the number of different queries that agree with the answer (v2):", "",
           "| Agreeing different queries | Questions | Accuracy |", "|---|---|---|"]
    md += [f"| {k} | {v['n']} | {f(v['accuracy']) if v['accuracy'] is not None else '—'} |"
           for k, v in res["v2_by_agreeing_distinct_queries"].items()]
    open(os.path.join(REPO, "results", f"agreement_v2{SUFFIX}.md"), "w").write("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
