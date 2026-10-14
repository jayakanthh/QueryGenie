# Weeks 10–11 — Confidence-Aware Abstention: Baseline and Results

Enhancement proposed in `docs/weekly-reports/Week 9/Enhancement_Proposal_Week9.docx` (Tier 4). Analysis code:
`src/abstention.py`. Raw data: `results/dump_T2-006.jsonl` (every question, all 4 candidates, beam
scores, execution results, official correctness). Numbers: `results/abstention_T2-006.json`.
Figure: `results/figures/accuracy_coverage_T2-006.png`.

## Week 10 — fresh baseline (run T2-006, 2026-09-28)

Same configuration as T2-005 (SFT CodeS-1B, harness v2, Colab Tesla T4, torch 2.11.0+cu128,
transformers 5.16.1), re-run from scratch:

| | T2-005 | T2-006 (fresh) |
|---|---|---|
| Official Execution Accuracy | 0.778 (printed) | **804/1034 = 77.76%** (printed 0.778) |
| Simple metric | 759/1034 | 759/1034 |
| Executable | 97.3% | 97.3% |

Identical, as expected from deterministic beam search. The per-question official scores recorded in
the dump sum to exactly 804, matching `evaluation.py` (which rounds to three decimals).

## Week 11 — results

Protocol fixed in the proposal before any result was seen: confidence = execution agreement among
the 4 candidates (beam probability as tie-breaker); 10 random 50/50 calibration/test splits; threshold
chosen on the calibration half for ≥ 90% coverage; compared with random abstention at the same
coverage; one-sided paired t-test and Wilcoxon signed-rank test, α = 0.05. Beam probability alone is
reported as a comparison signal.

### Headline (pre-registered test)

| Signal | Coverage (mean of 10 splits) | Accuracy on answered | Random abstention | Gain | t-test p | Wilcoxon p |
|---|---|---|---|---|---|---|
| **Execution agreement (proposed)** | 90.5% | **83.25%** | 77.79% | **+5.46 pts** (sd 0.71) | 7.7 × 10⁻¹⁰ | 9.8 × 10⁻⁴ |
| Beam probability | 89.7% | 80.88% | 77.79% | +3.08 pts (sd 0.90) | 9.3 × 10⁻⁷ | 9.8 × 10⁻⁴ |

**H0 is rejected: at about 90% coverage, agreement-based abstention answers significantly more
accurately than random abstention and than the 77.8% baseline.** Every one of the 10 splits showed a
positive gain; 9.8 × 10⁻⁴ is the smallest Wilcoxon p-value possible with 10 pairs.

### Robustness check — bootstrap over questions

The 10 splits reuse the same 1,034 questions, so they are not independent and the p-values above are
optimistic. As a check that does not share this weakness, the questions themselves were resampled
5,000 times (seed 0) and the gain at 90% coverage recomputed each time:

| Signal | Mean gain at 90% coverage | 95% bootstrap CI | Resamples with gain ≤ 0 |
|---|---|---|---|
| Execution agreement | +5.68 pts | [+4.51, +6.71] | 0 of 5,000 |
| Beam probability | +2.96 pts | [+1.97, +3.94] | 0 of 5,000 |

### The confidence signal is calibrated

Accuracy rises steadily with the number of candidates that agree with the returned answer:

| Candidates agreeing (of 4) | Questions | Accuracy |
|---|---|---|
| 0 (returned SQL does not execute) | 28 | 0.0% |
| 1 | 132 | 56.8% |
| 2 | 225 | 75.6% |
| 3 | 237 | 82.3% |
| 4 | 412 | 88.3% |

### What does not favour the proposal (reported, not hidden)

- **Over the whole curve, beam probability ranks answers slightly better.** Area under the
  risk–coverage curve (lower is better): beam probability 0.0905, agreement 0.1025, random 0.2224.
  Agreement is ahead from 100% down to about 74% coverage (by 2.0 points on average between 90 and
  100%); below about 74% beam probability is ahead (by 1.5 points on average between 50 and 70%).
  So agreement is the better signal when abstaining on a small share of questions — the operating
  point proposed — and beam probability is better when abstaining aggressively.
  A combined score is a natural Week-12 follow-up; it must be tuned on calibration halves only.
- **Agreement is coarse.** It takes only five values, so the 90% threshold cannot be hit exactly; the
  beam-probability tie-breaker is what makes intermediate coverages reachable.
- **Candidates can agree on the same wrong answer:** 11.7% of the questions where all four candidates
  agree are still wrong. Abstention reduces errors; it does not remove them.

## What this means for the product

At 90% coverage the system answers about 9 questions in 10 and is right on 83% of those, instead of
answering everything and being right on 78%. For the one question in ten it declines, it asks the user
to clarify rather than returning a confident wrong table. This number is always reported together
with its coverage; it is not a replacement for the 77.8% reproduction figure.

## Still to do

- Clarifying-question generation and the abstention UI in the application (Week 11 code, app side).
- Week 12: comparative results table in the final report format; optional combined signal.
- Week 13 (SOP): 5–10 trials — satisfied by the 10 splits plus the bootstrap; re-state in the report.

## Application integration (2026-09-28)

`src/app.py` now runs the evaluated pipeline (`src/codes_prompt.py`, shared with the evaluation:
same prompt, same 4-beam candidates, same selection rule, same result hash for agreement). For each
question it shows a confidence badge (how many of the 4 candidates return the answer), the SQL behind
the table, and — when the candidates disagree — the alternative interpretations to choose from.
A strictness setting offers the measured operating points (`results/abstention_operating_points.json`,
Spider dev, CodeS-1B): answer everything 100% / 77.8%, balanced (the tested rule) 90.4% / 83.3%,
3-of-4 agree 62.8% / 86.1%, all 4 agree 39.9% / 88.3%. In the strict settings the app withholds the
table and asks "Did you mean…" instead.

Qualitative check on the bundled academic database (5 questions each; illustrative, not a metric):
- CodeS-1B pipeline: on the flagship question ("students who failed more than two subjects") the
  selected answer is wrong (it returns students who failed any subject and took more than two); the
  candidates split 2–2, the badge shows *low* confidence and the correct reading (Meera) is offered as
  an alternative; the strict setting abstains.
- CodeS-3B pipeline: answers the flagship question correctly (still 2 of 4, low confidence); on
  "Average marks per department" no candidate that runs is selected, and it abstains.
