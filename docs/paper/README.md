# QueryGenie — research paper (IEEE conference format)

A short research paper, separate from the department thesis report in `docs/report-latex/`.
`IEEEtran.cls` is the class file shipped in `docs/Templates/Thesis_Template_KLH_BCP_Campus/` (unchanged);
`references.bib` is the report's bibliography (every entry from the arXiv API).

| File | Content |
|---|---|
| `main.tex` | the paper (7 pages, IEEE two-column) |
| `main.pdf` | compiled |
| `figures/` | architecture, accuracy–coverage curves (copies of `results/figures/`), app screenshot (very strict, not-sure case) |

Compile: `tectonic -X compile main.tex` (or upload the folder to Overleaf).

## Where every number comes from

All figures are from the repository's results, none estimated: `results/reproduction_log.csv`,
`results/harness_audit.md`, `results/week7_ablation_study.md`, `results/week12_comparative_results.md`,
`results/agreement_v2*.md` (candidate diversity, CodeS-3B T2-004, sampling SM-008),
`results/selection_analysis.md`, `results/repair_eval.md`, `results/reality/spider_realistic_RL-001.md`,
`results/postgres_translation_check.md`, `results/dataset_analysis.md`.

## Audit (2026-10-22)

Every number was recomputed from the raw run dumps (`results/dump_*.jsonl`) and the per-split trials (counts, accuracies,
t-tests, Wilcoxon, paired comparison, majority votes). The comparison figures of the CodeS paper (Table 5: 77.9 / 83.4 EX,
72.2 TS; Table 7: Spider-Realistic 70.9; 4 beams; 8 A800 GPUs) were read from the arXiv PDF. All 26 references were checked
against the arXiv API; three venue errors were corrected (MAC-SQL is COLING 2025; Shi et al. is ACM Computing Surveys; the
unsupported TKDE note on Qin et al. was removed). Prior work on confidence/abstention for text-to-SQL ([7]-[9], [25], [26])
was added and the novelty claim narrowed accordingly. A second, wider search (2026-10-22: ambiguity, answerability,
uncertainty, execution-based voting, semantic-parsing calibration) added eight more references, each checked on arXiv:
Stengel-Eskin & Van Durme (two papers), EHRSQL, Maleki et al., Borchmann & Wydmuch, Liu et al. (sub-clause calibration),
AMBROSIA, AmbiQT. Xin et al. (ACL 2021, selective prediction) was left out: it is not on arXiv and the department accepts
arXiv papers only. Papers that appeared only as search snippets were not cited.

## Marked TBD in the paper (not measured)

Test-suite accuracy, BIRD Mini-Dev (run BD-001 stopped), the 8-beam run CN-008 (the first attempt printed
0.788 before it failed while saving; the re-run's results had not arrived when the paper was written),
MySQL, end-to-end PostgreSQL accuracy, CodeS-7B/15B. Fill these in only from logged runs.

## Originality check (2026-10-22)

`scripts/similarity_check.py` (open, local; word n-gram shingles, citation markers and the reference list excluded) compared the
paper with the arXiv PDFs of the cited works. 33 of the 38 cited papers were readable and compared: no shared run of 8 or more
words with any of them; the only 6-word overlaps are the stock phrase "semantic parsing and text to SQL" and two technical wordings
that echoed abstracts (reworded). Not compared (the downloads were truncated): Self-Consistency (2203.11171), BIRD (2305.03111),
CHESS (2405.16755) and the surveys 2407.15186 and 2408.05109. This is a check against the cited sources only, not a web-wide
or institutional check (Turnitin / iThenticate), which is what the department counts.
