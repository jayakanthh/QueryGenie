<h1 align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="desktop/assets/brand/logo-wordmark-dark.png">
    <img alt="QueryGenie" src="desktop/assets/brand/logo-wordmark.png" width="440">
  </picture>
</h1>

**A self-correcting natural-language-to-SQL interface that tells you when it isn't sure.**

Ask a database a question in plain English — *“Which students failed more than two subjects?”* —
and QueryGenie writes the SQL, runs it, and shows the result as a table and a chart. It runs
locally on open weights ([CodeS](https://arxiv.org/abs/2402.16347)), so by default no schema or data
leaves the machine. Unlike most text-to-SQL systems, it measures its own confidence: when its candidate
queries disagree, it asks *“Did you mean…?”* instead of returning a confident wrong answer.

Engineering Capstone Project (Phase I), Department of Computer Science & Information Technology,
Koneru Lakshmaiah Education Foundation (KL University). Team 21 — supervisor M Parameswar.

![Pipeline](docs/final_pipeline.png)

## Results

All numbers are on the Spider development set (1,034 questions), scored with the official Spider
evaluator, using the released fine-tuned CodeS-1B checkpoint.

| | Questions answered | Execution accuracy on answered |
|---|---|---|
| CodeS-1B, as reported in the paper | 100% | 77.9% |
| **CodeS-1B, reproduced here** | 100% | **77.8%** |
| **+ confidence-aware abstention** (tested setting) | 90.4% | **83.3%** |

- **Reproduction:** within 0.1 points of the paper. Getting there required an audit of our own
  evaluation harness, which found a scoring mismatch and a value-retriever bug
  ([`results/harness_audit.md`](results/harness_audit.md)).
- **Enhancement:** wrong answers fall from 230 to 156 (−32%). The gain is significant under a paired
  t-test (p = 7.7 × 10⁻¹⁰), a Wilcoxon signed-rank test (p = 9.8 × 10⁻⁴) and a question-level
  bootstrap (95% CI +4.5 to +6.7 points)
  ([`results/week12_comparative_results.md`](results/week12_comparative_results.md)).
- **Ablation:** every part of the CodeS prompt contributes 0.9–1.9 points; the value retriever
  matters most ([`results/week7_ablation_study.md`](results/week7_ablation_study.md)).
- **Not yet measured:** Test-suite accuracy (the paper reports 72.2%) — TBD.

## Run the app

QueryGenie is a desktop app for macOS and Windows (a native window, not a web page).

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python desktop/main.py
```

On first start a setup assistant checks the computer and downloads the model
(`seeklhy/codes-1b-spider`, about 4.5 GB) and, optionally, the 20 Spider development databases
(about 0.2 GB) from Hugging Face. Everything is stored in your user folder
(`~/Library/Application Support/QueryGenie`, or `%APPDATA%\QueryGenie` on Windows), not in the app.
To build a double-clickable app instead, see [`desktop/build.md`](desktop/build.md).

In the app:

- **Databases** (left): a small academic database, the 20 Spider databases the 77.8% / 83.3% figures
  were measured on, any **SQLite file** you add, and live **PostgreSQL / MySQL** connections.
  Everything runs read-only.
- **Chats** (middle): *New chat* (⌘N / Ctrl+N) starts a thread; keep asking in it. Follow-ups use the last
  few questions as context (Settings → General; *New topic* starts fresh). Chat models get the earlier
  questions and their SQL; CodeS, trained on single questions, gets the previous question and the follow-up
  combined, and "what about IT?"-style follow-ups are rewritten as the earlier question with the value
  swapped. On a six-question spot check CodeS-1B got 5 follow-ups right (0 without context) — illustrative,
  not a measurement.
- **Chat view**: every answer shows how many of the 4 candidate queries agree, the table, a chart,
  the SQL (editable) and all four candidates. When they disagree it asks *"I'm not sure which you
  mean"* and shows the readings instead of guessing.
- **Map view**: the whole database as a tree (tables, columns, keys, links). Tap a table or column
  for ready-made questions, or to use its name in your question.
- **Self-correction:** a candidate query that fails is sent back once with its error and replaced by the repair
  (Settings → General). Measured on Spider with CodeS-1B it changes little — 61 of 377 failed queries ran after
  repair, one more answer was right (77.76% → 77.85%; [`results/repair_eval.md`](results/repair_eval.md)) — since
  CodeS was not trained on error feedback; the reported figures are without it.
- **Model picker** under the question box: switch model, and set its effort where the provider has one
  (Claude low → max; OpenAI-style reasoning models low / medium / high; Ollama thinking on / off).
- **Settings → Model**: the evaluated CodeS-1B-Spider (the default, and the only model whose accuracy
  was measured); the earlier prototype's CodeS models (MLX 4-bit, GGUF 2-bit, base CodeS — from source
  only); any model in **Ollama**; your own CodeS-format model or any **OpenAI-compatible server**
  (LM Studio, vLLM…); and cloud services — **OpenAI, Anthropic (Claude), Google (Gemini), xAI (Grok)**,
  DeepSeek, Mistral, Groq, OpenRouter and Together. Every model gets the same four-candidate
  confidence check, labelled "not calibrated" for anything but CodeS-1B. Cloud services receive the
  schema, a few example values and the question (never result rows), after a confirmation; API keys
  are kept in the macOS Keychain / Windows Credential Manager.
- **Settings → when to decline**: answer everything (100% / 77.8%), balanced (90% / 83.3%),
  strict (63% / 86.1%), very strict (40% / 88.3%) — coverage and accuracy measured on Spider dev.

![Abstention in the app: the candidates disagree, so it asks "Did you mean…?"](docs/screenshots/app_abstain.png)

### Connect your own database

**Add database → Connect to PostgreSQL or MySQL**, then enter host, database, user and password.
QueryGenie reads the schema, builds a value index once, and answers on the live database:

- the model's SQLite-style SQL is translated to the server's dialect (sqlglot) and shown next to
  the original;
- only a single read-only query is accepted, run inside a **READ ONLY transaction** with a
  30-second timeout and a 1,000-row limit — use a read-only database user anyway;
- the password is kept in memory only.

On Spider's databases loaded into PostgreSQL, translated queries return the same answer as on
SQLite for 94.4% of gold queries and 93.7% of model predictions
([`results/postgres_translation_check.md`](results/postgres_translation_check.md)). Accuracy and
confidence were calibrated on SQLite; on other engines they are not yet measured.

### The earlier web prototype

The Gradio prototype shown at Reviews 1–2, with the experimental MLX / GGUF / base-CodeS backends,
is kept in [`legacy/`](legacy/) and still runs: `python legacy/app.py` (then open
http://127.0.0.1:7860). It uses the same evaluated core as the desktop app.

## Reproduce the results

**1. Reproduction and the candidate record (GPU, about 1 hour).** Open
[`research/notebooks/02_tier2_colab_eval.ipynb`](research/notebooks/02_tier2_colab_eval.ipynb) in Google Colab with a
T4 GPU runtime and run the Week-10 cell. It runs
[`research/colab_eval_tier2.py`](research/colab_eval_tier2.py), which downloads Spider and the model
from Hugging Face, evaluates all 1,034 questions with the official evaluator, and saves
`preds_<run>.txt` and `dump_<run>.jsonl` (all 4 candidates per question). Ablations are set with
`QG_ABLATE` (`no_values`, `no_content`, `no_fk`, `no_select`); another model with `QG_MODEL`.

**2. Enhancement analysis (CPU, seconds).**

```bash
python research/abstention.py results/dump_T2-006.jsonl
```

This reproduces the significance tests, the operating points and the accuracy–coverage figure
from the committed candidate record.

**3. Tests (no model needed).** `python -m pytest tests/ -q` (23 tests)

**4. Dataset provenance.** `python scripts/download_spider.py` fetches Spider from Hugging Face
(`xlangai/spider`) and records its provenance in `results/dataset_provenance.json`.

Every run — including superseded ones — is logged with seed, hardware, runtime and library versions
in [`results/reproduction_log.csv`](results/reproduction_log.csv) and
`results/Reproduction_Log.xlsx`.

### Deviations from the authors' setup

Inference-only reproduction with the released checkpoint (the authors' pre-training used 8 × A800
GPUs). Newer PyTorch / transformers than the pinned versions; a scan of all column values instead of
the authors' Lucene BM25 index before their (unchanged) value matcher; no schema item classifier;
Tesla T4 with the same fp16 precision and batch size as the authors' inference. Details and their
effects: final report, Section 6.

## Repository layout

```
querygenie/           the core — what the app runs, and what was evaluated
  pipeline.py         the evaluated CodeS pipeline: prompt, 4 candidates, selection, agreement
  model.py            CodesSFTBackend: fine-tuned CodeS with scored beam candidates
  confidence.py       strictness modes, measured operating points, answer-or-abstain
  databases.py        catalogue: sample, Spider dev, added files, live connections; schema map
  connectors.py       live PostgreSQL / MySQL: schema, value index, SQL translation, read-only execution
  sample_db.py        builds the small academic database
  vendor/             authors' CodeS utilities, unmodified (Apache-2.0)
desktop/              the desktop app: native window (pywebview), interface (ui/), first-run setup,
                      packaging (QueryGenie.spec, build.md)
research/             how the numbers were produced
  colab_eval_tier2.py the Colab evaluation harness behind every Tier-2 run (official evaluator)
  abstention.py       Week-11 analysis: tests, bootstrap, operating points, figure
  eval_spider_full.py local (simple-metric) variant of the evaluation
  eval_spider_v1.py   first harness, produced run T2-001
  check_postgres_translation.py   PostgreSQL translation check
  smoke_test.py       Week-4 gate smoke test
  notebooks/          Week-4 gate notebook; Colab notebook for all Tier-2 runs
legacy/               Gradio web prototype (Reviews 1–2) and its MLX / GGUF / base-CodeS backends
scripts/              setup: Spider dataset and database download, PostgreSQL loader, Mac setup
results/              run log, audit, ablation, abstention results, figures, candidate record
tests/                model-free tests: selection, agreement, abstention, databases, chats
docs/                 reports, weekly reports, department SOP and templates, diagrams
```

### Where files moved (30 September 2026)

Documents written before this date (weekly reports, reproducibility reports v1–v2, the Review 2
deck, `results/`) cite the old paths. The code is unchanged apart from imports.

| Old path | New path |
|---|---|
| `src/codes_prompt.py` | `querygenie/pipeline.py` |
| `src/model.py` | `querygenie/model.py` (evaluated backend) + `legacy/models.py` (other backends) |
| `src/engine.py` | `querygenie/confidence.py` (abstention) + `legacy/self_correct.py` (retry loop) |
| `src/databases.py`, `src/connectors.py`, `src/vendor/` | `querygenie/` (same names) |
| `src/build_sample_db.py` | `querygenie/sample_db.py` |
| `src/app.py`, `src/charts.py`, `src/database.py` | `legacy/` (same names) |
| `src/abstention.py`, `src/eval_spider_full.py` | `research/` (same names) |
| `src/eval_spider.py` | `research/eval_spider_v1.py` |
| `scripts/colab_eval_tier2.py`, `scripts/check_postgres_translation.py`, `scripts/smoke_test.py` | `research/` (same names) |
| `scripts/convert_mlx.py` | `legacy/scripts/convert_mlx.py` |
| `notebooks/` | `research/notebooks/` |

## Documents

| Document | File |
|---|---|
| Project report (LaTeX, department template) | [`docs/report-latex/main.pdf`](docs/report-latex/main.pdf) — source in [`docs/report-latex/`](docs/report-latex/) |
| Final report (draft) | [`docs/Final_Report_Draft.docx`](docs/Final_Report_Draft.docx) |
| Code reproducibility report v2 | [`docs/Code_Reproducibility_Report_v2.docx`](docs/Code_Reproducibility_Report_v2.docx) |
| Enhancement proposal (Week 9) | [`docs/Enhancement_Proposal_Week9.docx`](docs/Enhancement_Proposal_Week9.docx) |
| Comparative results (Week 12) | [`docs/Week12_Comparative_Results.docx`](docs/Week12_Comparative_Results.docx) |
| Annotated CodeS paper (Week 3) | [`docs/CodeS_Annotated_Paper.pdf`](docs/CodeS_Annotated_Paper.pdf) |
| Deliverables tracker | [`docs/DELIVERABLES.md`](docs/DELIVERABLES.md) |
| Weekly status reports | [`docs/weekly-reports/`](docs/weekly-reports/) |

## Papers

| Role | Paper | arXiv |
|---|---|---|
| Anchor (reproduced) | CodeS: Towards Building Open-source Language Models for Text-to-SQL (SIGMOD 2024) | [2402.16347](https://arxiv.org/abs/2402.16347) |
| Benchmark | Spider (EMNLP 2018) | [1809.08887](https://arxiv.org/abs/1809.08887) |
| Evaluation | Semantic Evaluation for Text-to-SQL with Distilled Test Suites (EMNLP 2020) | [2010.02840](https://arxiv.org/abs/2010.02840) |
| Self-correction (app feature) | DIN-SQL (NeurIPS 2023) | [2304.11015](https://arxiv.org/abs/2304.11015) |
| Abstention | Selective Classification for Deep Neural Networks (NeurIPS 2017) | [1705.08500](https://arxiv.org/abs/1705.08500) |
| Candidate agreement | Self-Consistency Improves Chain of Thought Reasoning in Language Models (ICLR 2023) | [2203.11171](https://arxiv.org/abs/2203.11171) |
| Charts | LIDA (ACL 2023) | [2303.02927](https://arxiv.org/abs/2303.02927) |

## Team

- N V V S S Jayakanth Kamisetti — 2320090050
- Boddupally Narendar — 2320090009
- M Praneeth Reddy — 2320090018
- Supervisor: M Parameswar

## Licence

Apache License 2.0 — see [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE). The files in `querygenie/vendor/` are
from [RUCKBReasoning/codes](https://github.com/RUCKBReasoning/codes) (Apache-2.0), unmodified.
Model weights and the Spider dataset are downloaded under their own licences and are not included.
