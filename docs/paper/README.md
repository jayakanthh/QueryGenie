# QueryGenie — research paper (IEEE conference format)

A short research paper, separate from the department thesis report in `docs/report-latex/`.
`IEEEtran.cls` is the class file shipped in `docs/Templates/Thesis_Template_KLH_BCP_Campus/` (unchanged);
`references.bib` is the report's bibliography (every entry from the arXiv API).

| File | Content |
|---|---|
| `main.tex` | the paper (5 pages) |
| `main.pdf` | compiled |
| `figures/` | architecture, accuracy–coverage curve, ablation chart (copies of `results/figures/`) |

Compile: `tectonic -X compile main.tex` (or upload the folder to Overleaf).

## Where every number comes from

All figures are from the repository's results, none estimated: `results/reproduction_log.csv`,
`results/harness_audit.md`, `results/week7_ablation_study.md`, `results/week12_comparative_results.md`,
`results/agreement_v2*.md` (candidate diversity, CodeS-3B T2-004, sampling SM-008),
`results/selection_analysis.md`, `results/repair_eval.md`, `results/reality/spider_realistic_RL-001.md`,
`results/postgres_translation_check.md`, `results/dataset_analysis.md`.

## Marked TBD in the paper (not measured)

Test-suite accuracy, BIRD Mini-Dev (run BD-001 stopped), the 8-beam run CN-008 (the first attempt printed
0.788 before it failed while saving; the re-run's results had not arrived when the paper was written),
MySQL, end-to-end PostgreSQL accuracy, CodeS-7B/15B. Fill these in only from logged runs.
