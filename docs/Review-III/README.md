# Review-III — Team 21, QueryGenie

Everything for the Review-III presentation, in one place.

| File | What it is | Open with |
|---|---|---|
| `QueryGenie_Report.pdf` | The report for the spiral-bound hard copy (LaTeX, department thesis template). Topics as required: Abstract, Introduction (objectives), Literature Review, Proposed Methodology, Experimental Results, Limitations and Future Work, References. No code. | Any PDF viewer / print |
| `QueryGenie_Review-III.pptx` | The presentation, built on the department's Review-III template (17 slides). | PowerPoint |
| `QueryGenie_Poster.pptx` | The project poster, built on the department's poster template. | PowerPoint |

## Still to fill in

- **Supervisor designation** — title slide of the deck ("<Associate/Assistant Professor>"), the poster's
  Team Details ("Designation"), and the report's certificate page.
- **Benchmark-to-reality numbers** (Spider-Realistic, BIRD Mini-Dev) — TBD in all three until runs
  RL-001 and BD-001 finish.

## Where the sources are

- Report source: `docs/report-latex/` (`main.tex` and one file per chapter). The PDF here is a copy of
  `docs/report-latex/main.pdf`.
- Deck and poster are generated from the templates in `docs/Templates/` by
  `scripts/build_review3_deck.py` and `scripts/build_poster.py`; re-run them after a change.
- Every number comes from `results/` (run log: `results/reproduction_log.csv`).
