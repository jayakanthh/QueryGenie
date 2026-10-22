# QueryGenie — Project Context

Read this fully before acting. It is the authoritative brief for this project.

## What this is

A final-year Engineering Capstone Project (Phase I) for the Department of Computer Science &
Information Technology, Koneru Lakshmaiah Education Foundation (KL University).

**Title:** QueryGenie: A Self-Correcting Natural Language to SQL Interface
**Domain:** AI/ML — Computation and Language (with a Databases crossover)
**Team 18** (renumbered from Team 21 on 2026-10-02; documents submitted before that keep "Team 21")
- 2320090050 — N V V S S Jayakanth Kamisetti (primary user you are talking to; goes by Jaikanth)
- 2320090009 — Boddupally Narendar (handles documentation) — spelling confirmed by Jaikanth 2026-09-29
- 2320090018 — M Praneeth Reddy (team member; listed on all project records)
**Supervisor:** M Parameswar, Associate Professor

**The product:** a user types a plain-English question ("which students failed more than two
subjects?"); the system generates SQL, executes it, self-corrects if execution fails, and returns
a results table plus an auto-selected chart.

## The academic rules (these are hard constraints, not preferences)

The department SOP governs everything. Full text in `docs/reference/` — read it if a compliance
question arises. Key rules:

- **Papers must come from arXiv only.**
- **Datasets must come from approved sources only:** Hugging Face, PhysioNet, Microsoft Research,
  Google Datasets, The Cancer Imaging Archive, OpenNeuro. **Kaggle is explicitly banned.**
- **Week 4 red-flag rule:** the original paper's code must run by end of Week 4. If it does not,
  the paper must be abandoned and replaced. Failure to comply = automatic project rejection.
- **Reproduction tolerance:** ±5–10% of the reported metric for ML/AI work. Outside that, the
  deviation must be documented with a specific stated cause, or reproduction counts as failed.
- **Falsifying metrics = immediate rejection + academic misconduct.** Never invent, estimate, or
  guess a number. If a figure is unknown, write "TBD" and say so.
- **Weekly reports** must be discussed with and signed by the supervisor before submission.
  Three missed reports = automatic rejection.
- **Final deliverable must be** a full-stack app OR a packaged tool (PyPI / npm / VS Code
  extension) — not a notebook. Everything on GitHub, supervisor added as collaborator, all
  members committing under their own accounts.

Grade weighting (45% is locked in by Week 8, so reproduction is the priority):
| Component | Weight | Due |
|---|---|---|
| Paper selection + feasibility | 5% | Week 2 |
| Environment runs without error | 5% | Week 4 |
| Reproduction log (3 runs) | 20% | Week 5 |
| Reproduction report | 25% | Week 8 |
| Enhancement proposal | 10% | Week 9 |
| Enhancement results | 20% | Week 12 |
| Final code + README | 10% | Week 15 |
| Final report + presentation | 5% | Week 16 |

## The papers

**Anchor paper (the one being reproduced):**
CodeS — *Towards Building Open-source Language Models for Text-to-SQL*, SIGMOD 2024
- arXiv: https://arxiv.org/abs/2402.16347
- Code: https://github.com/RUCKBReasoning/codes (Apache-2.0)
- Weights: https://huggingface.co/seeklhy/codes-1b (also 3b / 7b / 15b)
- Companion demo repo (useful for Month 4): https://github.com/RUCKBReasoning/text2sql-demo

**Fallback anchor** (same lab, same benchmark — switching stays inside the approved topic):
RESDSQL, AAAI 2023 — https://arxiv.org/abs/2302.05965 — https://github.com/RUCKBReasoning/RESDSQL

**Enhancement source:**
DIN-SQL, NeurIPS 2023 — https://arxiv.org/abs/2304.11015 — execution-guided self-correction

**Visualization layer:**
LIDA, ACL 2023 — https://arxiv.org/abs/2303.02927

**Benchmark:** Spider — https://huggingface.co/datasets/spider (approved source ✅)
Paper: https://arxiv.org/abs/1809.08887 · Metrics used by CodeS: Execution Accuracy (EX) and Test-suite accuracy (TS) — not EM

## Planned contributions (Month 3 enhancement)

1. **Execution-guided self-correction** — detect SQL that fails to execute, repair it
   automatically (DIN-SQL strategy applied on top of CodeS).
2. **Confidence-aware abstention** — the novel angle. Generate multiple candidates, measure
   agreement, and *abstain with a clarifying question* when confidence is low rather than
   answering wrongly. Evaluate with an accuracy-vs-coverage curve. Existing systems answer with
   uniform confidence and never report this.
3. **Benchmark-to-reality gap** — evaluate on a custom academic schema alongside Spider. Published
   models score 85%+ on Spider but reportedly collapse to 10–20% on real enterprise databases;
   quantifying and narrowing that gap is the project's practical story.

Framing for reviewers who ask "how is this different from ChatGPT?": **trustworthiness** — it knows
when it doesn't know, and it runs fully locally on open weights (no schema sent to a third party).

## Current state (updated 2026-09-28)

`docs/DELIVERABLES.md` is the live tracker — read it, and keep it updated as things complete.

Done and measured (all runs in `results/reproduction_log.csv`):
- **Week-4 gate** cleared (T1-001). Spider downloaded (`xlangai/spider`).
- **Reproduction:** SFT CodeS-1B, official Spider evaluator — **77.8%** EX vs paper 77.9% (T2-005,
  fresh re-run T2-006 = 804/1034). Earlier 64.8/71.7/73.8% used a simplified metric and had a
  value-retriever bug — see `results/harness_audit.md`. Test-suite accuracy: **TBD**.
- **Ablation** (official metric): −0.9 to −1.9 pts per component (`results/week7_ablation_study.md`).
- **Enhancement = confidence-aware abstention** (the ONE graded enhancement, Tier 4; proposal
  `docs/weekly-reports/Week 9/Enhancement_Proposal_Week9.docx`). 83.3% on answered at 90.4% coverage vs 77.8%; t-test
  p = 7.7e-10, Wilcoxon p = 9.8e-4, bootstrap CI [+4.5, +6.7] (`results/week12_comparative_results.md`).
  Self-correction and charts are app features, not graded enhancements.
- **App** is the desktop app (`desktop/`, macOS + Windows, pywebview; chats, schema map, packaged via
  `desktop/QueryGenie.spec`). It runs the evaluated core (`querygenie/pipeline.py`) with confidence badge,
  "Did you mean…?" and strictness modes. Final report draft: `docs/weekly-reports/Week 14/Final_Report_Draft.docx`.
- Weekly reports written through Week 12. **Signatures are collected at the end** (department
  decision) — don't flag them as blockers.

Repo made public 2026-10-22 (https://github.com/jayakanthh/QueryGenie); research paper in `docs/paper/`. Remaining: Week 16 final deck, supervisor as collaborator and the other members' own commits; optional TS
scoring and CodeS-3B evaluation.

## The Colab MCP

`colab-mcp` (https://github.com/googlecolab/colab-mcp) is configured. It bridges to a Colab
notebook **already open in the user's browser** — there is no separate account linking; the
browser session is the auth. Ask the user to have the notebook tab open and a GPU runtime
selected before driving it.

## How to work on this

- **Never fabricate a metric, benchmark figure, or citation.** This project is graded on
  reproduction honesty and falsification is an expulsion-level offence. Unknown = "TBD".
- **Verify before asserting.** Read the actual repo/paper rather than recalling it. An earlier
  session incorrectly claimed the CodeS repo would run easily on free Colab; reading the README
  showed otherwise. Check first.
- **Log every run** to `results/reproduction_log.csv` / `Reproduction_Log.xlsx` — including
  failures. The SOP wants three logged runs with seeds, runtime and hardware.
- **Record every deviation** from the paper's setup as you make it. These go in the
  reproducibility report and are worth marks; reconstructing them later is painful.
- Documentation goes in `docs/`. Department templates live in `docs/Templates/` — **fill them by
  editing the originals** (unzip → edit `word/document.xml` → rezip) so the letterhead survives.
  Never rebuild a template from scratch.
- The user is a student, not an ML engineer. Explain plainly, flag risks early, and be direct when
  something is a bad idea.

## Repository layout

```
QueryGenie/
├── CLAUDE.md                 # this file
├── README.md                 # run it, reproduce it, where things moved
├── querygenie/               # core package: evaluated pipeline, model, confidence, databases, connectors
├── desktop/                  # desktop app (native window + ui/), first-run setup, PyInstaller spec
├── research/                 # how the numbers were produced
│   ├── reproduction/         #   Colab harness, local evaluation, score_dump, dataset analysis, notebooks/
│   ├── enhancement/          #   abstention, agreement v2, selection and repair analyses
│   ├── reality/              #   Spider-Realistic and BIRD (benchmark-to-reality gap)
│   └── app-checks/           #   PostgreSQL translation, "unclear" check, demo rehearsal
├── results/                  # Reproduction_Log.xlsx + .csv, run dumps, analyses, figures (scripts write here)
├── scripts/
│   ├── (setup)               #   Spider download, PostgreSQL loader, Mac setup
│   ├── docs/                 #   builders: Review-3 deck, speaker script
│   └── poster/               #   builders: poster charts + pptx
├── legacy/                   # Gradio prototype (Reviews 1-2) + MLX/GGUF/base backends
├── tests/                    # model-free tests
└── docs/
    ├── DELIVERABLES.md       # live tracker: every SOP week -> artefact -> status
    ├── weekly-reports/       # Week 1-14: each week's report + the document due that week
    ├── reviews/              # Review-1/, Review-2/, Review-3/ (Review-3 = the Review-III pack)
    ├── poster/               # project poster (pptx + print PDF) + assets - not part of a review
    ├── figures/              # pipeline / architecture diagrams, app screenshots
    ├── report-latex/         # the LaTeX project report (source + PDF)
    ├── Templates/            # official university templates (fill, don't rebuild)
    └── reference/            # department SOP + Phase-I guidelines
```

Files moved from `src/`, `scripts/` and `notebooks/` on 2026-09-30, and `research/`, `scripts/` and `docs/`
regrouped on 2026-10-14 — README has the old→new tables; submitted documents (the printed report, the run
log) keep the old paths. Never move `results/`: scripts and the Colab watcher write into it.

The user reorganises files as submissions go out (e.g. each review has its own folder holding what was
actually handed in). Check the tree before assuming a path.

## Timeline

| Weeks | Phase | Gate |
|---|---|---|
| 1–4 | Topic, paper, environment | **Week 4: original code must run** |
| 5–8 | Reproducibility + ablation | Metrics within ±5–10% or documented |
| 9–12 | Enhancement | Statistically significant improvement (t-test / Wilcoxon) |
| 13–16 | Finalization | Full-stack app, report, public repo, presentation |
