# QueryGenie

**A Self-Correcting Natural Language to SQL Interface**

Final Year Project — Phase I
Department of Computer Science & Information Technology
Domain: Artificial Intelligence and Machine Learning — Computation and Language (with Databases crossover)

---

## Overview

QueryGenie lets a non-technical user ask a question in plain English (e.g. *"which students failed more than two subjects?"*), automatically generates the corresponding SQL query, validates and self-corrects it if execution fails, and returns the results as a table together with an automatically selected chart.

## Papers

| Role | Paper | Venue | Link |
|---|---|---|---|
| **Anchor** (reproduced) | CodeS: Towards Building Open-source Language Models for Text-to-SQL | SIGMOD 2024 | https://arxiv.org/abs/2402.16347 |
| Backup anchor | RESDSQL: Decoupling Schema Linking and Skeleton Parsing for Text-to-SQL | AAAI 2023 | https://arxiv.org/abs/2302.05965 |
| Enhancement source | DIN-SQL: Decomposed In-Context Learning of Text-to-SQL with Self-Correction | NeurIPS 2023 | https://arxiv.org/abs/2304.11015 |
| Visualization layer | LIDA: Automatic Generation of Grammar-Agnostic Visualizations and Infographics using LLMs | ACL 2023 | https://arxiv.org/abs/2303.02927 |

**Code (anchor):** https://github.com/RUCKBReasoning/codes
**Model weights:** https://huggingface.co/seeklhy/codes-1b

## Dataset

- **Spider** — https://huggingface.co/datasets/spider (Hugging Face — approved data source)
- Dataset paper: https://arxiv.org/abs/1809.08887
- Metrics: Exact-set Match (EM) and Execution Accuracy (EX) on the Spider dev set

> Kaggle is **not** used — it is excluded by the department SOP.

## Project Phases

| Month | Phase | Key gate |
|---|---|---|
| 1 | Topic & paper selection, environment setup | Week 4: original code must run |
| 2 | Reproducibility | Metrics within ±5–10% or documented deviation |
| 3 | Enhancement (execution-guided self-correction) | Statistically significant improvement |
| 4 | Finalization: full-stack app, report, presentation | Public repo + final submission |

## Repository Structure

```
QueryGenie/
├── README.md
├── docs/
│   ├── reference/            # Department SOP and Phase-I guidelines
│   ├── reviews/              # Review deliverables (Week 1, Review 1, ...)
│   ├── weekly-reports/       # Signed weekly status reports
│   └── Documentation_Brief_For_Teammate.txt
├── scripts/                  # Local setup and smoke test
├── src/                      # Application source code
├── notebooks/                # Experiments and reproduction notebooks
└── results/                  # Reproduction logs, metrics, figures
```

## Running Locally (Apple Silicon Mac)

```bash
bash scripts/setup_local_mac.sh     # creates .venv, installs deps, checks MPS
source .venv/bin/activate
python scripts/smoke_test.py        # Tier 1: loads CodeS-1B, generates + executes SQL
```

The first run downloads the CodeS-1B weights (~2–3 GB). Results are appended to
`results/reproduction_log.csv`.

### Where each tier runs

| Tier | What | Where | Why |
|---|---|---|---|
| **1 — Smoke test** | Load CodeS-1B, generate SQL, execute it | **Local Mac (MPS)** | Fast, no session limits, good for iteration |
| **2 — Faithful reproduction** | Authors' environment + Spider evaluation | **Colab / CUDA machine** | Repo pins `pytorch-cuda`, `bitsandbytes`, `deepspeed` — all CUDA-only |

Apple Silicon cannot run the anchor repository's pinned environment. The local setup
therefore uses a current PyTorch/transformers stack on the MPS backend. **This is a
documented deviation** and must be stated in the reproducibility report: local runs are
liveness checks and development work; all graded reproduction metrics come from Tier 2.

## Status

- [x] Week 1 — Paper shortlist + feasibility matrix
- [x] Review 1 — Topic, literature review (44 papers), objectives, deliverables
- [ ] Week 2 — Faculty approval, dataset download, repo clone
- [ ] Weeks 3–4 — Paper annotation, environment setup, first run
- [ ] Weeks 5–8 — Reproduction, ablation, Reproducibility Report v1.0
- [ ] Weeks 9–12 — Enhancement implementation and comparison
- [ ] Weeks 13–16 — Final experiments, report, repository, presentation
