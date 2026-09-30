# Deliverables Tracker — Phase I

Maps every week of the department SOP to its required deliverable, the artefact in this
repository, and its status. Update the status column as each item is completed and signed.

**Legend:** ✅ done · 🟡 partially done · ⬜ not started

---

## Month 1 — Topic and Paper Selection

| Week | SOP deliverable | Artefact in this repo | Status |
|---|---|---|---|
| 1 | Shortlist with feasibility matrix | `docs/reviews/Week1_Shortlist_Feasibility_Matrix.docx` | ✅ |
| 1 | Weekly report | `docs/weekly-reports/Week 1/Weekly_Report.docx` | ✅ signed |
| 1 | Abstract submission | `docs/weekly-reports/Week 1/Abstract.docx` | ✅ |
| — | Review 1 pack (topic, 44-paper literature review, objectives, deliverables) | `docs/reviews/Review1_QueryGenie.docx` | ✅ presented |
| — | Review 1 deck | `docs/weekly-reports/Week 1/Team_21.pptx` | ✅ presented |
| 2 | Approved paper | CodeS confirmed at Review 1 (arXiv:2402.16347) | ✅ |
| 2 | Dataset downloaded | `scripts/download_spider.py` → writes `results/dataset_provenance.json` | ✅ run 2026-08-14 (train 7000 / dev 1034; source `xlangai/spider`) |
| 2 | Weekly report | `docs/weekly-reports/Week 2/Weekly_Report.docx` | 🟡 needs supervisor signature |
| 3 | Annotated paper (inputs, outputs, equations, hyperparameters) | `docs/weekly-reports/Week 3/Paper_Annotation_Worksheet.docx` + **`docs/CodeS_Annotated_Paper.pdf`** | ✅ worksheet filled from the CodeS PDF; **annotated PDF** with highlights + margin notes on inputs/outputs, Eq 1–2, hyperparameters, metrics, and the 77.9% target |
| 3 | Algorithm / architecture flowchart | `docs/weekly-reports/Week 3/CodeS_Architecture_Flowchart.png` (source: `docs/codes_architecture_flowchart.svg`) | ✅ **verified against Figure 3** — corrected metrics to EX/TS, added LCS value-match + prompt metadata |
| 3 | Weekly report | `docs/weekly-reports/Week 3/Weekly_Report.docx` | 🟡 needs supervisor signature |
| 4 | **Working environment + run log (RED-FLAG GATE)** | `research/notebooks/01_week4_gate_codes_setup.ipynb` | ✅ **Tier 1 CLEARED 2026-08-14** — codes-1b loaded on Colab T4, generated valid SQL, executed against SQLite (`results/reproduction_log.csv` run T1-001) |
| 4 | Weekly report | `docs/weekly-reports/Week 4/Weekly_Report.docx` | 🟡 written, needs supervisor signature |
| 5 | Weekly report | `docs/weekly-reports/Week 5/Weekly_Report.docx` | 🟡 written (13 Sep), needs supervisor signature |

## Month 2 — Reproducibility

| Week | SOP deliverable | Artefact | Status |
|---|---|---|---|
| 5 | Reproduction log, 3 runs (20%) | `results/reproduction_log.csv` + `results/Reproduction_Log.xlsx` | ✅ T2-001, T2-002, T2-003 (+ repeat), T2-005 — full runs logged with seed/hardware/runtime/versions |
| 6 | Comparison table vs paper (±5–10%) | `results/comparison_vs_paper.md` | ✅ **Official EX 77.8%** (T2-005, harness v2, paper's evaluator) vs paper 77.9% — **−0.1 pts**; earlier runs used a simpler metric (see `harness_audit.md`) |
| 6 | Weekly report | `docs/weekly-reports/Week 6/Weekly_Report.docx` | 🟡 written (20 Sep), needs supervisor signature |
| 7 | Ablation study | `results/week7_ablation_study.md` | ✅ 4 ablations on harness v2, official metric: −0.9 to −1.9 pts vs 77.8 (retriever −1.9 largest); significance test pending |
| 7 | Weekly report | `docs/weekly-reports/Week 7/Weekly_Report.docx` | 🟡 written (22 Sep), needs supervisor signature |
| 8 | **Reproducibility Report (25%)** | `docs/Code_Reproducibility_Report_v2.docx` (v1 = Review-II submission, kept) | ✅ v2 (26 Sep): headline official EX 77.8% vs 77.9%, harness audit, ablation study; TS still TBD |
| 8 | Weekly report | `docs/weekly-reports/Week 8/Weekly_Report.docx` | 🟡 written (26 Sep), needs supervisor signature |

## Month 3 — Enhancement

| Week | SOP deliverable | Artefact | Status |
|---|---|---|---|
| 9 | Enhancement proposal (10%) — 1 page, ONE tier, guide approval required | `docs/Enhancement_Proposal_Week9.docx` | 🟡 written: **Tier 4, confidence-aware abstention** (hypothesis + t-test/Wilcoxon plan); switch from the abstract's self-correction justified with data; **needs guide approval + signature** |
| 9 | Weekly report | `docs/weekly-reports/Week 9/Weekly_Report.docx` | 🟡 written (28 Sep), needs supervisor signature |
| 10 | Fresh baseline on our hardware | `results/reproduction_log.csv` (T2-006), `results/week11_abstention.md` | ✅ T2-006 (28 Sep): official EX 804/1034 = 77.76%, identical to T2-005; full candidate dump saved |
| 10 | Weekly report | `docs/weekly-reports/Week 10/Weekly_Report.docx` | 🟡 written (28 Sep), needs supervisor signature |
| 11 | Working enhanced code | `research/abstention.py`, `querygenie/pipeline.py`, `desktop/` (was `src/abstention.py`, `src/codes_prompt.py`, `src/app.py`) | ✅ abstention analysis + in the app (confidence badge, 'Did you mean…', strictness with measured coverage/accuracy) |
| 11 | Weekly report | `docs/weekly-reports/Week 11/Weekly_Report.docx` | 🟡 written (28 Sep), needs supervisor signature |
| 12 | Comparative results + significance test (20%) | `docs/Week12_Comparative_Results.docx`, `results/week12_comparative_results.md` | ✅ original 77.76% vs enhanced 83.32% at 90.4% coverage; wrong answers 230→156; t=24.4 p=7.7e-10, Wilcoxon W=55 p=9.8e-4, bootstrap CI [+4.5,+6.7] |
| 12 | Weekly report | `docs/weekly-reports/Week 12/Weekly_Report.docx` | 🟡 written (28 Sep), needs supervisor signature |

## Month 4 — Finalization

| Week | SOP deliverable | Artefact | Status |
|---|---|---|---|
| 13 | Final figures + statistics | — | ⬜ |
| 14 | Draft final report | `docs/Final_Report_Draft.docx` | ✅ draft (28 Sep, 14 pp): SOP structure Intro → Methodology → Results → Enhancement → Discussion → Conclusion; figures + appendices |
| 15 | Public GitHub repo + README (10%) | `README.md`, `LICENSE`, `NOTICE`, `tests/` | 🟡 README rewritten (reproduce / run enhancement / requirements / licence), Apache-2.0, 9 tests; **repo still private — visibility change pending** |
| 16 | Final report + presentation (5%) | `docs/reviews/Review3_QueryGenie.pptx`, `docs/Final_Report_Draft.docx` | 🟡 Review-3 deck (19 slides, dept template, speaker notes, real app screenshots); LaTeX documentation pending department template |

---

## Immediate priorities

1. ✅ **DONE (2026-08-14) — Tier 1 of the setup notebook / Week-4 gate.** codes-1b loaded on a
   Colab T4, generated valid SQL, executed it against SQLite. Evidence in
   `results/week4_gate_evidence.md`, logged as T1-001 in `results/reproduction_log.csv`.
2. ✅ **DONE (2026-08-14) — `scripts/download_spider.py`.** Spider pulled from `xlangai/spider`
   (train 7000 / dev 1034); provenance in `results/dataset_provenance.json`.
3. **Fill the Week 3 worksheet** while reading the CodeS PDF — especially the reported
   Execution Accuracy for CodeS-1B on Spider dev, which is the number the reproduction will
   be measured against.
4. **Get Weeks 2 and 3 weekly reports signed.** Three missed reports is an automatic
   rejection; unsigned reports count as not submitted.
5. ✅ **DONE — Week 4 weekly report written** (`docs/weekly-reports/Week 4/Weekly_Report.docx`); needs the supervisor's physical signature.
6. ✅ **DONE — Tier 2 reproduction:** 3 runs logged, best 73.8% vs 77.9% (within tolerance).
7. **Next:** reviewer asked for ≥78% → run SFT CodeS-3B (T2-004, paper 83.4%); port SIC schema
   filter to test the remaining 1B gap; update the reproducibility report.

## Standing rules

- Never record a metric that has not actually been measured or read from the source. Unknown
  values are written as TBD.
- Every run goes in the reproduction log, including failed ones.
- Every deviation from the paper's setup is recorded as it is made, not reconstructed later.
- Weekly reports must be discussed with the supervisor and signed before submission.
