"""
Week 11 — confidence-aware abstention on a CodeS candidate dump.

Input: dump_<RUN>.jsonl written by research/reproduction/colab_eval_tier2.py — one line per Spider dev
question with the 4 beam candidates, their length-normalised beam scores, execution
results (hash of the sorted rows) and official-evaluator correctness.

Confidence signals (fixed in the Week-9 proposal before any result was seen):
  agreement  primary: share of the 4 candidates whose execution result equals the
             returned answer's (0.25 .. 1.0; 0 if the returned SQL does not execute),
             with the beam probability as tie-breaker (the proposal's secondary signal).
  beam_prob  comparison: softmax of the 4 beam scores, value of the returned candidate.

Protocol (proposal, Week 9):
  10 random 50/50 splits of the dev set (seeds 0-9). On the calibration half choose the
  threshold tau giving at least 90% coverage; apply it to the test half. Compare the
  accuracy on answered test questions with random abstention at the same coverage, whose
  expected accuracy equals the test half's full-coverage accuracy. Paired t-test and
  Wilcoxon signed-rank on the 10 differences (alpha = 0.05).

Usage:
    python research/enhancement/abstention.py results/dump_T2-006.jsonl
"""
from __future__ import annotations
import argparse, json, math, os
import numpy as np
from scipy import stats

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TARGET_COVERAGE = 0.90
SEEDS = range(10)


def load(path):
    rows = [json.loads(l) for l in open(path) if l.strip()]
    rows.sort(key=lambda r: r["i"])
    return rows


def signals(r):
    sel = r["selected"]
    scores = np.array(r["beam_scores"], dtype=float)
    probs = np.exp(scores - scores.max()); probs /= probs.sum()
    p_sel = float(probs[sel]) if sel >= 0 else 0.0
    h = r["result_hash"][sel] if sel >= 0 else None
    agree = (sum(1 for x in r["result_hash"] if x is not None and x == h) / len(r["result_hash"])
             if h is not None else 0.0)
    # agreement first, beam probability only breaks ties (it is < 1, agreement steps are 0.25)
    return {"agreement": agree + 0.01 * p_sel, "beam_prob": p_sel, "agreement_raw": agree}


def curve(conf, correct):
    """Accuracy of the k most confident answers, for k = 1..n (stable for ties)."""
    order = np.argsort(-conf, kind="stable")
    c = correct[order]
    k = np.arange(1, len(c) + 1)
    return k / len(c), np.cumsum(c) / k


def aurc(conf, correct):
    """Area under the risk-coverage curve (lower is better)."""
    _, acc = curve(conf, correct)
    return float(np.mean(1 - acc))


def at_coverage(conf, correct, cov):
    k = max(1, int(math.ceil(cov * len(conf))))
    order = np.argsort(-conf, kind="stable")
    return float(correct[order[:k]].mean())


def split_trial(conf, correct, seed):
    rng = np.random.default_rng(seed)
    idx = rng.permutation(len(conf))
    cal, test = idx[: len(idx) // 2], idx[len(idx) // 2:]
    # tau: the highest threshold that still answers >= 90% of the calibration half
    cal_sorted = np.sort(conf[cal])[::-1]
    tau = cal_sorted[int(math.ceil(TARGET_COVERAGE * len(cal))) - 1]
    answered = conf[test] >= tau
    sel_acc = float(correct[test][answered].mean()) if answered.any() else float("nan")
    base = float(correct[test].mean())      # expected accuracy of random abstention
    return {"seed": seed, "tau": float(tau), "coverage": float(answered.mean()),
            "selective_acc": sel_acc, "random_acc": base, "diff": sel_acc - base,
            "abstained_wrong_rate": float(1 - correct[test][~answered].mean()) if (~answered).any() else float("nan")}


def analyse(rows):
    correct = np.array([r["selected_official_correct"] for r in rows], dtype=float)
    sig = [signals(r) for r in rows]
    out = {"n": len(rows), "accuracy_full_coverage": float(correct.mean()), "signals": {}}
    for name in ("agreement", "beam_prob"):
        conf = np.array([s[name] for s in sig])
        trials = [split_trial(conf, correct, s) for s in SEEDS]
        d = np.array([t["diff"] for t in trials])
        t_res = stats.ttest_1samp(d, 0.0, alternative="greater")
        try:
            w_res = stats.wilcoxon(d, alternative="greater")
            w_p = float(w_res.pvalue)
        except ValueError:            # all differences zero
            w_p = float("nan")
        out["signals"][name] = {
            "aurc": aurc(conf, correct),
            "acc_at_90pct_coverage_full_set": at_coverage(conf, correct, 0.90),
            "acc_at_80pct_coverage_full_set": at_coverage(conf, correct, 0.80),
            "trials": trials,
            "mean_coverage": float(np.mean([t["coverage"] for t in trials])),
            "mean_selective_acc": float(np.mean([t["selective_acc"] for t in trials])),
            "mean_random_acc": float(np.mean([t["random_acc"] for t in trials])),
            "mean_diff": float(d.mean()), "sd_diff": float(d.std(ddof=1)),
            "t_test_p_one_sided": float(t_res.pvalue), "wilcoxon_p_one_sided": w_p,
        }
    out["aurc_random"] = float(1 - correct.mean())
    agree_levels = np.array([s["agreement_raw"] for s in sig])
    out["by_agreement_level"] = {
        f"{lvl:.2f}": {"n": int((agree_levels == lvl).sum()),
                       "accuracy": float(correct[agree_levels == lvl].mean()) if (agree_levels == lvl).any() else None}
        for lvl in (0.0, 0.25, 0.5, 0.75, 1.0)}
    return out, correct, sig


# What each logged run is, for the figure title (T2-004 is the 3B model; SM-008 draws 8 samples instead of 4 beams).
RUN_LABEL = {"T2-006": "CodeS-1B", "T2-004": "CodeS-3B", "SM-008": "CodeS-1B, 8 sampled candidates"}


def plot(correct, sig, path, run_id):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    INK, INK2, MUTED, GRID, AXIS, SURF = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"
    SERIES = {"agreement": ("#2a78d6", "Execution agreement (proposed)"),
              "beam_prob": ("#eb6834", "Beam probability")}
    fig, ax = plt.subplots(figsize=(7.2, 4.2), dpi=200)
    fig.patch.set_facecolor(SURF); ax.set_facecolor(SURF)
    base = correct.mean()
    ax.axhline(base * 100, color=MUTED, lw=1.5, ls=(0, (4, 3)), zorder=1)
    ax.text(75, base * 100 + 0.3, f"Random abstention / answer everything: {base*100:.1f}%",
            color=INK2, fontsize=8, va="bottom", ha="center")
    if run_id == "SM-008":       # beam probability of sampled candidates is not a comparable score: do not draw it
        SERIES = {k: v for k, v in SERIES.items() if k == "agreement"}
    for name, (col, label) in SERIES.items():
        conf = np.array([s[name] for s in sig])
        cov, acc = curve(conf, correct)
        m = cov >= 0.5
        ax.plot(cov[m] * 100, acc[m] * 100, color=col, lw=2, label=label, zorder=3,
                solid_capstyle="round")
        a90 = at_coverage(conf, correct, 0.90)
        ax.plot([90], [a90 * 100], "o", ms=6, color=col, mec=SURF, mew=2, zorder=4)
    ax.axvline(90, color=GRID, lw=1, zorder=0)
    ax.set_xlim(50, 100); ax.invert_xaxis(); ax.set_ylim(bottom=base * 100 - 1.5)
    ax.set_xlabel("Coverage — share of questions answered (%)", color=INK2, fontsize=9)
    ax.set_ylabel("Execution accuracy on answered questions (%)", color=INK2, fontsize=9)
    ax.set_title(f"Accuracy vs coverage, {RUN_LABEL.get(run_id, 'CodeS')} on Spider dev ({run_id})", color=INK, fontsize=10,
                 loc="left", pad=10)
    ax.grid(axis="y", color=GRID, lw=0.6); ax.set_axisbelow(True)
    for s in ("top", "right"): ax.spines[s].set_visible(False)
    for s in ("left", "bottom"): ax.spines[s].set_color(AXIS)
    ax.tick_params(colors=MUTED, labelsize=8)
    ax.legend(frameon=False, fontsize=8, labelcolor=INK2, loc="upper left")
    fig.tight_layout(); os.makedirs(os.path.dirname(path), exist_ok=True)
    fig.savefig(path, facecolor=SURF); plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dump")
    ap.add_argument("--out-dir", default=os.path.join(REPO, "results"))
    args = ap.parse_args()
    run_id = os.path.basename(args.dump).replace("dump_", "").replace(".jsonl", "")
    rows = load(args.dump)
    res, correct, sig = analyse(rows)
    res["run_id"] = run_id
    os.makedirs(args.out_dir, exist_ok=True)
    jpath = os.path.join(args.out_dir, f"abstention_{run_id}.json")
    json.dump(res, open(jpath, "w"), indent=2)
    plot(correct, sig, os.path.join(args.out_dir, "figures", f"accuracy_coverage_{run_id}.png"), run_id)
    print(f"n={res['n']}  accuracy at full coverage = {res['accuracy_full_coverage']:.4f}")
    for name, s in res["signals"].items():
        print(f"[{name}] AURC {s['aurc']:.4f} (random {res['aurc_random']:.4f}) | "
              f"acc@90% cov {s['acc_at_90pct_coverage_full_set']:.4f} | 10 splits: coverage {s['mean_coverage']:.3f}, "
              f"selective {s['mean_selective_acc']:.4f} vs random {s['mean_random_acc']:.4f}, "
              f"diff {s['mean_diff']*100:+.2f} pts (sd {s['sd_diff']*100:.2f}) | "
              f"t-test p={s['t_test_p_one_sided']:.2e}, Wilcoxon p={s['wilcoxon_p_one_sided']:.2e}")
    print("accuracy by agreement level:", {k: v for k, v in res["by_agreement_level"].items()})
    print("wrote", jpath)


if __name__ == "__main__":
    main()
