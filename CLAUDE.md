# QueryGenie — Project Context

Read this fully before acting. It is the authoritative brief for this project.

## What this is

A final-year Engineering Capstone Project (Phase I) for the Department of Computer Science &
Information Technology, Koneru Lakshmaiah Education Foundation (KL University).

**Title:** QueryGenie: A Self-Correcting Natural Language to SQL Interface
**Domain:** AI/ML — Computation and Language (with a Databases crossover)
**Team 21**
- 2320090050 — N V V S S Jayakanth Kamisetti (primary user you are talking to; goes by Jaikanth)
- 2320090009 — Bodupally Narendar (handles documentation)
**Supervisor:** M Parameswar

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
  extension) — not a notebook. Everything on GitHub, supervisor added as collaborator, both
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
Paper: https://arxiv.org/abs/1809.08887 · Metrics: Exact-set Match (EM), Execution Accuracy (EX)

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

## Current state (as of the handover to Claude Code)

`docs/DELIVERABLES.md` is the live tracker — read it, and keep it updated as things complete.

Written and verified:
- Week 1: 3-paper shortlist + feasibility matrix; abstract; weekly report; Review-1 deck
- Review 1: **presented**. Topic, 44-paper literature review, objectives, deliverables
- Week 2: weekly report; `scripts/download_spider.py` (dataset + provenance record)
- Week 3: `Paper_Annotation_Worksheet.docx` (pre-filled with verified facts, blanks for the
  paper values); `CodeS_Architecture_Flowchart.png`; weekly report
- `notebooks/01_week4_gate_codes_setup.ipynb` — two-tier setup notebook
- `results/Reproduction_Log.xlsx` — log template with tolerance formulas
- `scripts/setup_local_mac.sh`, `scripts/smoke_test.py` — local Apple Silicon path

**Nothing has been EXECUTED yet.** No environment built, no model downloaded, no dataset pulled,
no reproduction numbers. In priority order:

1. **Run Tier 1 of the notebook — the Week-4 red-flag gate.** This is the only rejection-level
   item outstanding, and all of Month 2 is blocked behind it.
2. Run `scripts/download_spider.py` to close the Week 2 dataset deliverable.
3. Fill the Week 3 worksheet blanks by reading the CodeS PDF — above all the reported Execution
   Accuracy for CodeS-1B on Spider dev, which is the target the reproduction is measured against.
4. Verify `CodeS_Architecture_Flowchart.png` against Figure 1 of the paper; it was reconstructed
   from the abstract and repo structure, not from the figure, and says so on its face.

Weeks 2 and 3 weekly reports still need the supervisor's signature.

## Immediate task

Clear the Week-4 gate, then reproduce.

**Tier 1 (do this first — fast, low risk):** load `seeklhy/codes-1b`, generate SQL from a schema +
question, execute it against SQLite to confirm it works. This satisfies "the original code runs."
Log the run.

**Tier 2 (the graded 45%):** recreate the authors' environment and run their evaluation on Spider
dev to get real EX/EM numbers.

### Known Tier 2 friction (verified by reading the actual repo — do not re-discover this the hard way)

- Repo pins Python **3.8.5**, PyTorch **1.13.1**, transformers **4.28.1**, `scipy==1.5.4`.
  Modern Python will not build some of these — an isolated 3.8.5 env is required.
- `pyserini==0.21.0` needs **Java 11**.
- `SimCSE` installs from a fork: https://github.com/lihaoyang-ruc/SimCSE
- `data.zip`, `sic_ckpts.zip`, `test_suite_sql_eval.zip` are on **Google Drive** (rate-limited;
  have a manual-download fallback). Drive IDs are in the notebook.
- Authors evaluated on **8× A800 80GB**. Use `codes-1b` and reduce batch size.
- `bitsandbytes` and `deepspeed` are CUDA-only — **cannot run on the user's Apple Silicon Mac.**
  Tier 2 must run on Colab or another CUDA machine. Local Mac is for Tier 1 and app development.
- The authors themselves warn that newer transformers versions shift inference results slightly.
  If that shows up, it is a legitimate documented deviation, not a bug to hide.

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
├── README.md
├── docs/
│   ├── DELIVERABLES.md       # live tracker: every SOP week -> artefact -> status
│   ├── reference/            # department SOP + Phase-I guidelines
│   ├── Templates/            # official university templates (fill, don't rebuild)
│   ├── reviews/              # Week 1 shortlist, Review 1 pack
│   ├── weekly-reports/
│   │   ├── Week 1/           # Abstract, Weekly_Report, Team_21.pptx (submitted)
│   │   ├── Week 2/           # Weekly_Report
│   │   └── Week 3/           # Weekly_Report, Paper_Annotation_Worksheet, flowchart
│   ├── architecture.png              # QueryGenie system workflow (used in the deck)
│   └── codes_architecture_flowchart.png  # CodeS paper pipeline (Week 3 deliverable)
├── notebooks/                # 01_week4_gate_codes_setup.ipynb
├── scripts/                  # local mac setup + smoke test
├── results/                  # Reproduction_Log.xlsx, run logs, figures
└── src/                      # application code (not yet created — Month 4)
```

The user reorganises files as submissions go out (e.g. `Week 1/` holds what was actually handed in,
renamed to match what the department asked for). Check the tree before assuming a path.

## Timeline

| Weeks | Phase | Gate |
|---|---|---|
| 1–4 | Topic, paper, environment | **Week 4: original code must run** |
| 5–8 | Reproducibility + ablation | Metrics within ±5–10% or documented |
| 9–12 | Enhancement | Statistically significant improvement (t-test / Wilcoxon) |
| 13–16 | Finalization | Full-stack app, report, public repo, presentation |
