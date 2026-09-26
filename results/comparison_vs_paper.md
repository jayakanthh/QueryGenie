# Comparison against the paper — CodeS on Spider dev (Week 6 deliverable)

Anchor paper: CodeS (SIGMOD 2024, arXiv:2402.16347), Table 5 (page 11).
Metric: Execution Accuracy (EX) on the Spider development set (1,034 examples).
**Update 2026-09-26:** a harness audit (`harness_audit.md`) found that runs T2-001–T2-003 used a
simpler EX metric than the paper's official evaluator, and a value-retriever bug. T2-005 fixes both
and is the headline comparison.
Tolerance (department SOP): ±5–10% of the reported value. All values below are
measured; nothing is estimated. Raw rows: `reproduction_log.csv` / `Reproduction_Log.xlsx`.

## Faithful reproduction — SFT CodeS-1B (paper: 77.9% EX)

| Run | Prompt / decoding | Hardware | Our EX | Δ abs | Δ rel | Within ±10%? |
|---|---|---|---|---|---|---|
| T2-001 | schema + foreign keys only; beam 0 of 4 | Apple M4, MPS bf16 | 64.8% (670/1034) | −13.1 | −16.8% | **No** — cause: value retriever absent |
| T2-002 | full CodeS prompt; beam 0 of 4 | Colab T4, fp16 | 71.7% (741/1034) | −6.2 | −8.0% | Yes |
| T2-003 | full CodeS prompt + authors' selection rule (first of 4 beams that passes `EXPLAIN QUERY PLAN`) | Colab T4, fp16 | 73.8% (763/1034) | −4.1 | −5.3% | Yes |
| **T2-005** | **harness v2** (retriever fix, tables.json comments) — **scored with the official Spider evaluator** | Colab T4, fp16 | **77.8% official** (73.4% simple) | **−0.1** | **−0.1%** | **Yes** |

T2-001–T2-003 are scored with a simple sorted-rows metric (not the paper's); only T2-005 is on the
paper's scale. On T2-005's predictions the two metrics differ by 4.4 points.

Executable-prediction rate: 93.5% (T2-002) → 97.3% (T2-003).

## Other Table-5 rows

| Model | Paper EX | Our EX | Status |
|---|---|---|---|
| SFT CodeS-3B | 83.4% | TBD | planned run T2-004 (same harness, Colab T4) |
| SFT CodeS-7B / 15B | 85.4% / 84.9% | — | do not fit a free Colab GPU in fp16 |

## Remaining deviations from the authors' setup (the gap is now −0.1 pts; kept for the record)

| # | Authors | Ours | Expected effect |
|---|---|---|---|
| 1 | Schema item classifier (SIC) trims each prompt to top-6 tables / top-10 columns; the SFT model was *trained* on trimmed schemas | Full schema passed | Train/test mismatch on Spider DBs with many tables/columns — most likely main cause; to be tested |
| 2 | Lucene BM25 coarse retrieval → fine match (difflib + rapidfuzz, ≥0.9) | Direct distinct-value scan → same fine match | Superset of authors' candidates; small or nil |
| 3 | Python 3.8.5, PyTorch 1.13.1, transformers 4.28.1 | Colab-default PyTorch / transformers (2.x / 4.5x) | Authors warn newer versions shift inference results; small |
| 4 | 8× A800 80 GB, fp16 | 1× T4 16 GB, fp16 | None on accuracy (batch size 1 in both) |
| 5 | Test-suite accuracy (TS) also reported | EX only | TS not reproduced (needs `test_suite_sql_eval` databases) |

## Ablation evidence already collected (Week 7 input)

| Component removed | Baseline | Ablated | Cost |
|---|---|---|---|
| Value retriever (matched contents) | 71.7% (T2-002) | 64.8% (T2-001) | −6.9 pts |
| Execution-guided candidate selection | 73.8% (T2-003) | 71.7% (T2-002) | −2.1 pts |
