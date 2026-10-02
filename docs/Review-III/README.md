# Review-III — Team 21, QueryGenie

Everything for the Review-III presentation, in one place.

| File | What it is | Open with |
|---|---|---|
| `QueryGenie_Report.pdf` | The report for the spiral-bound hard copy (LaTeX, department thesis template). Topics as required: Abstract, Introduction (objectives), Literature Review, Proposed Methodology, Experimental Results, Limitations and Future Work, References. No code. | Any PDF viewer / print |
| `QueryGenie_Review-III.pptx` | The presentation, built on the department's Review-III template (18 slides). | PowerPoint |
| `QueryGenie_Poster.pptx` | The project poster, built on the department's poster template. | PowerPoint |
| `Speaker_Script.docx` | Who presents which slides (Narendar 1–8, Praneeth 9–11, Jayakanth 12–18 + demo), what to say on each, and who answers which questions. Send to the team. | Word |
| `Demo_Script.pdf` / `.md` | The live demo: 7 rehearsed questions with the answers to expect, questions to avoid, and answers for questions about the numbers. | Any PDF viewer / print |

## Printing

- **Report** — `QueryGenie_Report.pdf`, A4, 33 pages. Print double-sided if the department allows it; spiral bind.
  Print in colour if you can (figures and the app screenshots use colour); black-and-white still reads.
- **Deck** — present from PowerPoint. For a paper copy: File → Print → Handouts, 3 or 6 slides per page.
- **Poster** — the template is A0-sized (84 × 119 cm), so it needs a print shop's plotter. Take the
  .pptx (or export it from PowerPoint as PDF: File → Save As → PDF) on a USB stick. To check it first,
  print it on A4 with "scale to fit".
- **Demo script** — `Demo_Script.pdf`, 2 pages of A4; keep it next to the laptop.

## Still to fill in

- **BIRD Mini-Dev result** — TBD in all three until run BD-001 finishes. Spider-Realistic is done
  (RL-001: 69.5% vs the paper's 70.9%).

## Where the sources are

- Report source: `docs/report-latex/` (`main.tex` and one file per chapter). The PDF here is a copy of
  `docs/report-latex/main.pdf`.
- Deck and poster are generated from the templates in `docs/Templates/` by
  `scripts/build_review3_deck.py` and `scripts/build_poster.py`; re-run them after a change.
- Every number comes from `results/` (run log: `results/reproduction_log.csv`).
