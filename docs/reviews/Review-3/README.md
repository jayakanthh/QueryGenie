# Review-3 (Review-III) — Team 18, QueryGenie

Everything for the Review-III presentation, in one place.

| File | What it is | Open with |
|---|---|---|
| `QueryGenie_Report.pdf` | The report for the spiral-bound hard copy (LaTeX, department thesis template). Topics as required: Abstract, Introduction (objectives), Literature Review, Proposed Methodology, Experimental Results, Limitations and Future Work, References. No code. | Any PDF viewer / print |
| `QueryGenie_Review-III.pptx` | The presentation, built on the department's Review-III template (18 slides). | PowerPoint |
| `Speaker_Script.pdf` / `.docx` | Who presents which slides (Jayakanth, team lead: opening 1–3, results + demo 12–13, close 16–18; Narendar: 4–8 and 14–15; Praneeth: 9–11), what to say on each, and who answers which questions. Send to the team. | PDF / Word |
| `Demo_Script.pdf` / `.md` | The live demo: 7 rehearsed questions with the answers to expect, questions to avoid, and answers for questions about the numbers. | Any PDF viewer / print |

## Printing

- **Report** — `QueryGenie_Report.pdf`, A4, 33 pages. Print double-sided if the department allows it; spiral bind.
  Print in colour if you can (figures and the app screenshots use colour); black-and-white still reads.
- **Deck** — present from PowerPoint. For a paper copy: File → Print → Handouts, 3 or 6 slides per page.
- **Demo script** — `Demo_Script.pdf`, 2 pages of A4; keep it next to the laptop.

## Still to fill in

- **BIRD Mini-Dev result** — TBD until run BD-001 finishes. Spider-Realistic is done
  (RL-001: 69.5% vs the paper's 70.9%).

## Where the sources are

- Report source: `docs/report-latex/` (`main.tex` and one file per chapter). The PDF here is a copy of
  `docs/report-latex/main.pdf`.
- The deck is generated from the template in `docs/Templates/` by `scripts/docs/build_review3_deck.py`;
  re-run it after a change (it overwrites the .pptx, so keep manual edits out of it).
- Every number comes from `results/` (run log: `results/reproduction_log.csv`).

`earlier-draft/` holds the deck made before the department's Review-III template arrived; it is kept for the record only.
The project poster is not part of this pack: it lives in `docs/poster/`.
