# QueryGenie — project report (LaTeX)

The department's thesis template (`docs/Templates/Thesis_Template_KLH_BCP_Campus/`, kept unchanged),
filled in for this project. `main.pdf` is the compiled report.

| File | Content |
|---|---|
| `main.tex` | title page, certificate, front matter, chapter order (the template's preamble) |
| `cert.tex`, `ack.tex`, `abstract.tex`, `biography.tex` | certificate, acknowledgments, abstract, biography |
| `intro.tex` | Chapter 1 — Introduction |
| `liturature.tex` | Chapter 2 — Literature survey (file name as in the template) |
| `dcandpa.tex` | Chapter 3 — Data collection and preliminary analysis |
| `proposed.tex` | Chapter 4 — Proposed approach: architecture, reproduction, ablation, enhancement, application, code |
| `conclusion.tex` | Chapter 5 — Conclusion and future scope |
| `references.bib` | 45 references, generated from the arXiv API (see the file header) |
| `images/` | the template's logo and header; `images/figures/` — the report's figures |

## Compile

**Overleaf:** zip this folder, *New Project → Upload Project*, compile (pdfLaTeX or XeLaTeX both work).

**This Mac:** `tectonic -X compile main.tex` (Tectonic, installed with Homebrew).

## Changes to the template itself

- `xcolor` was loaded twice with different options (an option clash that stops a strict compile);
  it is now loaded once as `\usepackage[svgnames]{xcolor}`.
- `\usepackage{xurl}` added so long file names can break across lines.
- The template's "Examples" chapter (how to write figures, tables and algorithms) was removed, as it is
  guidance for students; its helper files (`examples.tex`, `algorithm_template.tex`, `disease_url.txt`)
  are not used.
- The title page says **Bachelor of Technology** (the template's title page said "Bachelor of Science"
  while its certificate said B.Tech).

## Still to fill in by the team

- **Supervisor designation** on the certificate page (`cert.tex`: the line `Designation,`).
- Signatures and date on the certificate (at the end, as the department decided).

## Where the numbers come from

Every figure in the report is from the repository's results: `results/reproduction_log.csv`,
`results/harness_audit.md`, `results/week7_ablation_study.md`, `results/week12_comparative_results.md`,
`results/postgres_translation_check.md`, and `results/dataset_analysis.json` (Chapter 3, produced by
`research/dataset_analysis.py`). Test-suite accuracy is reported as TBD.
