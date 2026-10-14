# Project poster — Team 18, QueryGenie

Not part of Review-III: the poster has its own folder.

| File | What it is |
|---|---|
| `QueryGenie_Poster.pptx` | The poster (A0 portrait), built on the department's poster template. Open in PowerPoint. |
| `QueryGenie_Poster.pdf` | The same poster as a print-ready PDF (A0, 84 × 119 cm) for the print shop. |
| `assets/` | The four charts (`chart_*.png`), icons and licences used on the poster. |

Print: take the `.pdf` (or the `.pptx`) to a print shop with a large-format plotter. To check it first, print it on A4 with "scale to fit".

## How it is built

- Template: `docs/Templates/project-poster-tempalte.pptx`; reference posters (other teams', kept locally only): `docs/Templates/poster_examples/`.
- Builders: `scripts/poster/poster_charts.py` (the charts) then `scripts/poster/build_poster.py` (the poster).
- Every number on it comes from `results/` (run log: `results/reproduction_log.csv`).
- Font: Aptos, the template's own font (as in the reviewer's reference poster).
