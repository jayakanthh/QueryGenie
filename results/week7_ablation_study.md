# Week 7 — Ablation Study

**Deliverable:** SOP Week 7 — disable a component of the reproduced pipeline, re-measure, and show
the contribution of each part.

**Setup.** Model `seeklhy/codes-1b-spider` (SFT CodeS-1B), Spider development set, all 1034
examples per run. Metric: Execution Accuracy (EX) by sorted result-set match against the gold
query. Hardware: Tesla T4 (Google Colab), torch 2.11.0+cu128, transformers 5.16.1, seed 42.
Beam search with 4 beams; decoding is deterministic, so a repeat of the baseline returned an
identical 763/1034 (logged as T2-003r) — differences below are caused by the ablation, not by
sampling noise.

**Baseline (T2-003).** Full CodeS pipeline: database schema sequence (column types, primary keys,
representative values, foreign keys) + matched contents from the value retriever + the question,
BOS-prepended; 4 beam candidates, first one that passes `EXPLAIN QUERY PLAN` is returned.
**EX = 73.79% (763/1034), 97.3% of predictions executable.**

## Results

| Run | Component removed | EX | Δ EX | Executable | Runtime |
|---|---|---|---|---|---|
| T2-003 | — (full pipeline) | **73.79%** (763/1034) | — | 97.3% | 2111 s |
| T2-003r | — (repeat, determinism check) | 73.79% (763/1034) | 0.00 | 97.3% | 2270 s |
| AB-003 | representative column values in the schema | 72.24% (747/1034) | **−1.55** | 97.8% | 1652 s |
| AB-005 | foreign-keys block | 72.24% (747/1034) | **−1.55** | 95.5% | 2062 s |
| AB-006 | candidate selection (keep beam 0 only) | 71.66% (741/1034) | **−2.13** | 93.5% | 2265 s |
| AB-004 | matched contents (value retriever off) | 71.08% (735/1034) | **−2.71** | 96.8% | 2234 s |

## Interpretation

1. **Every component contributes; none dominates.** Removing any single part costs 1.5–2.7 points.
   The pipeline's accuracy comes from the combination, which is consistent with the paper's own
   claim that the database prompt is what makes a 1B model competitive.

2. **The value retriever is the single largest contributor (−2.71 pts).** Matched cell contents let
   the model write correct string literals in `WHERE` clauses; without them it guesses the spelling
   of values it has never seen. Notably, executability barely moves (96.8% vs 97.3%) — the queries
   still run, they just return the wrong rows. This is the failure mode the project's abstention
   contribution is aimed at: silently-wrong answers, not crashes.

3. **Candidate selection (−2.13 pts) works through a different mechanism.** It is the only ablation
   that changes executability sharply (93.5% vs 97.3%): re-ranking the 4 beams by executability
   converts roughly 4% of the set from broken SQL into runnable SQL, and about half of those become
   correct. AB-006 reproduced the earlier T2-002 run exactly (741/1034, 93.5% executable), which
   independently confirms the harness is deterministic.

4. **Foreign keys (−1.55 pts) matter for joins.** Their removal produces the worst executability of
   all runs (95.5%): without the FK list the model invents join conditions on columns that do not
   exist, so the SQL fails at parse/bind time rather than returning wrong rows.

5. **Representative values (−1.55 pts) are partly redundant with the value retriever.** They serve a
   similar purpose (showing the model what the data looks like), so removing just one of the two
   costs less than removing the retriever. Executability actually rises slightly (97.8%), because a
   shorter prompt leaves more room inside the 4096-token window for long schemas.

## Relation to the earlier 64.8% run

An earlier run (T2-001) used a reduced prompt — schema and foreign keys only, with no column types,
no primary-key markers, no representative values and no matched contents — and scored 64.8%. That
9-point gap is the *combined* effect of several missing components, not the cost of the value
retriever alone; the clean single-component figure is the −2.71 measured here as AB-004. The earlier
comparison is retained in the log for completeness but the ablation table above supersedes it.

## Deviations from the authors' setup (unchanged from the reproduction runs)

- The Lucene/BM25 coarse retrieval step is replaced by a direct distinct-value scan per column,
  which is a superset of the authors' candidate set; the fine matcher (difflib + rapidfuzz,
  score ≥ 0.9, ≤ 25 values per column) is the authors' own code, vendored unmodified.
- The schema item classifier (top-6 tables / top-10 columns) is not applied.
- Library versions are newer than the pinned ones (torch 1.13.1 / transformers 4.28.1); the authors
  note that this shifts inference results slightly.
