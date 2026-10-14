# Week 12 — Comparative Results: Original vs Enhanced

**Original:** SFT CodeS-1B, reproduced (run T2-006; harness v2; official Spider evaluator).
**Enhanced:** the same model and predictions, plus confidence-aware abstention (execution agreement
among the 4 beam candidates; proposal `docs/weekly-reports/Week 9/Enhancement_Proposal_Week9.docx`).
Both are evaluated on the same 1,034 Spider dev questions from one run, so the comparison is exactly
paired. Numbers: `results/week12_comparison.json`, produced from `results/dump_T2-006.jsonl`.

## Table 1 — Side-by-side results

| System | Questions answered | Accuracy on answered | Wrong answers given |
|---|---|---|---|
| CodeS-1B as reported in the paper (Table 5) | 1,034 (100%) | 77.9% | — |
| **Original — CodeS-1B reproduced** | 1,034 (100%) | **77.76%** (804) | **230** |
| **Enhanced — balanced (the tested rule)** | 935 (90.4%) | **83.32%** (779) | **156** |
| Enhanced — strict (≥ 3 of 4 agree) | 649 (62.8%) | 86.13% (559) | 90 |
| Enhanced — very strict (all 4 agree) | 412 (39.8%) | 88.35% (364) | 48 |
| Comparison signal — beam probability, ~90% coverage | 931 (90.0%) | 80.67% | — |

**Trade-off at the tested setting.** The enhanced system declines 99 questions. 74 of them would
have been answered wrongly and 25 correctly. Wrong answers fall from 230 to 156 (−32%), at the cost of
withholding 25 correct answers (3.1% of the 804 the original gets right).

## Table 2 — Significance tests (pre-registered protocol)

10 random 50/50 splits; the threshold is chosen on the calibration half for ≥ 90% coverage and
applied to the test half. The paired quantity is accuracy on answered questions minus the expected
accuracy of random abstention at the same coverage (= the original system's accuracy on that half).

| Signal | Mean gain | SD | Paired t-test (df = 9) | Wilcoxon signed-rank | Question-level bootstrap, 95% CI |
|---|---|---|---|---|---|
| **Execution agreement** | **+5.46 pts** | 0.71 | t = 24.44, p = 7.7 × 10⁻¹⁰ | W = 55, p = 9.8 × 10⁻⁴ | [+4.51, +6.71] |
| Beam probability | +3.08 pts | 0.90 | t = 10.81, p = 9.3 × 10⁻⁷ | W = 55, p = 9.8 × 10⁻⁴ | [+1.97, +3.94] |

All tests one-sided (H1: gain > 0), α = 0.05. W = 55 is the maximum (all 10 splits positive), and
9.8 × 10⁻⁴ is the smallest p the Wilcoxon test can give with 10 pairs. The bootstrap resamples the
questions (5,000 times), which does not rely on the splits being independent.

**Agreement vs beam probability, head to head** (same splits): agreement is higher by 2.37 points
(paired t = 6.31, df = 9, two-sided p = 1.4 × 10⁻⁴). Their coverages differ slightly (90.5% vs 89.7%)
because each threshold is chosen separately.

## Table 3 — The 10 trials (execution agreement)

| Split (seed) | Threshold | Coverage | Accuracy on answered | Original accuracy | Gain | Share of declined that were wrong |
|---|---|---|---|---|---|---|
| 0 | 0.2526 | 88.8% | 83.88% | 77.56% | +6.32 | 72.4% |
| 1 | 0.2526 | 90.5% | 82.48% | 77.18% | +5.30 | 73.5% |
| 2 | 0.2526 | 89.9% | 83.44% | 78.14% | +5.30 | 69.2% |
| 3 | 0.2526 | 89.2% | 84.60% | 78.53% | +6.07 | 71.4% |
| 4 | 0.2526 | 91.3% | 83.90% | 78.14% | +5.76 | 82.2% |
| 5 | 0.2526 | 92.1% | 82.77% | 77.95% | +4.82 | 78.1% |
| 6 | 0.2526 | 89.6% | 83.15% | 77.18% | +5.98 | 74.1% |
| 7 | 0.2526 | 89.0% | 83.26% | 77.18% | +6.08 | 71.9% |
| 8 | 0.2526 | 90.9% | 82.34% | 77.56% | +4.78 | 70.2% |
| 9 | 0.2526 | 93.8% | 82.68% | 78.53% | +4.15 | 84.4% |
| **Mean** | | **90.5%** | **83.25%** | **77.79%** | **+5.46** | |

## Table 4 — Whole-curve summary (area under the risk–coverage curve; lower is better)

| Ranking | AURC |
|---|---|
| Random (no signal) | 0.2224 |
| Execution agreement | 0.1025 |
| Beam probability | 0.0905 |
| Oracle (perfect ranking, lower bound) | 0.0269 |

Beam probability ranks answers better over the whole curve: it is ahead below about 74% coverage.
Execution agreement is ahead from 100% down to about 74% — the region where a usable assistant
operates and where the proposal set its operating point. Figure:
`results/figures/accuracy_coverage_T2-006.png`.

## Conclusion

**H0 is rejected.** At about 90% coverage, confidence-aware abstention raises accuracy on answered
questions from 77.8% to 83.3% and removes about a third of the wrong answers. This is significant
under a paired t-test, a Wilcoxon signed-rank test and a question-level bootstrap. The result is always
stated together with its coverage: the enhanced system answers fewer questions, and it does not
change the 77.8% reproduction figure.

## Limitations

- One model (CodeS-1B) and one benchmark (Spider dev); the threshold is calibrated on that data.
- The 10 splits reuse the same questions; the bootstrap is the check that does not depend on this.
- Candidates can agree on a wrong answer: 11.7% of the answers where all 4 candidates agree are wrong.
- Agreement takes only five values; the beam-probability tie-breaker is what allows intermediate
  coverages.
