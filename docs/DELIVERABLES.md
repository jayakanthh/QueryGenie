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
| 3 | Annotated paper (inputs, outputs, equations, hyperparameters) | `docs/weekly-reports/Week 3/Paper_Annotation_Worksheet.docx` | 🟡 **worksheet built, blanks to fill by reading the PDF** |
| 3 | Algorithm / architecture flowchart | `docs/weekly-reports/Week 3/CodeS_Architecture_Flowchart.png` | 🟡 **drafted, verify against Figure 1** |
| 3 | Weekly report | `docs/weekly-reports/Week 3/Weekly_Report.docx` | 🟡 needs supervisor signature |
| 4 | **Working environment + run log (RED-FLAG GATE)** | `notebooks/01_week4_gate_codes_setup.ipynb` | ✅ **Tier 1 CLEARED 2026-08-14** — codes-1b loaded on Colab T4, generated valid SQL, executed against SQLite (`results/reproduction_log.csv` run T1-001) |
| 4 | Weekly report | — | ⬜ |

## Month 2 — Reproducibility

| Week | SOP deliverable | Artefact | Status |
|---|---|---|---|
| 5 | Reproduction log, 3 runs (20%) | `results/Reproduction_Log.xlsx` | ⬜ template ready, no runs |
| 6 | Comparison table vs paper (±5–10%) | `results/Reproduction_Log.xlsx` (Diff % auto-computes) | ⬜ |
| 7 | Ablation study — disable schema filter | — | ⬜ |
| 8 | **Reproducibility Report v1.0 (25%)** | — | ⬜ |

## Month 3 — Enhancement

| Week | SOP deliverable | Artefact | Status |
|---|---|---|---|
| 9 | Enhancement proposal (10%) | — | ⬜ |
| 10 | Fresh baseline on our hardware | — | ⬜ |
| 11 | Working enhanced code | — | ⬜ |
| 12 | Comparative results + significance test (20%) | — | ⬜ |

## Month 4 — Finalization

| Week | SOP deliverable | Artefact | Status |
|---|---|---|---|
| 13 | Final figures + statistics | — | ⬜ |
| 14 | Draft final report | — | ⬜ |
| 15 | Public GitHub repo + README (10%) | `README.md` | 🟡 |
| 16 | Final report + presentation (5%) | — | ⬜ |

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
5. **Write the Week 4 weekly report** (still outstanding in the Month 1 table).
6. **Tier 2 (graded 45%)** — faithful reproduction on a CUDA machine with the authors' pinned
   environment. Not started; this is the next big block.

## Standing rules

- Never record a metric that has not actually been measured or read from the source. Unknown
  values are written as TBD.
- Every run goes in the reproduction log, including failed ones.
- Every deviation from the paper's setup is recorded as it is made, not reconstructed later.
- Weekly reports must be discussed with the supervisor and signed before submission.
