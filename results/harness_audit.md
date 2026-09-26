# Tier-2 Harness Audit (2026-09-26)

Line-by-line comparison of our Spider evaluation harness (`scripts/colab_eval_tier2.py`,
`src/eval_spider_full.py`) against the authors' code in RUCKBReasoning/codes:
`utils/load_sft_dataset.py`, `prepare_sft_datasets.py`, `build_contents_index.py`,
`text2sql_zero_shot.py`, `utils/db_utils.py`. Every effect below was measured on the 1034
Spider dev examples, not estimated.

## Checks that passed

| Check | Result |
|---|---|
| Vendored `db_utils.py` vs upstream | Byte-identical apart from the licence header |
| Colab-inlined functions vs vendored files | All 22 functions identical |
| Prompt assembly (`schema + content + question`, BOS prepended) | Matches `prepare_text2sql_prefix_sequence` |
| Decoding (4 beams, 4 returned, first that passes `EXPLAIN QUERY PLAN`, fall back to beam 0) | Matches `text2sql_zero_shot.py` |
| Post-processing (newline removal, back-quoting special column names) | Matches `post_process` |
| Precision on GPU | fp16, as the authors use |
| Determinism | T2-003 repeated exactly (763/1034); AB-006 reproduced T2-002 exactly (741/1034) |
| Prompt truncation | Longest dev prompt is 1,717 tokens, far below the 3,840 limit, so truncation never fires; our right-truncation was nonetheless replaced with the authors' left-truncation |
| Questions containing newlines | 0 in Spider dev |

## Discrepancies found and fixed (harness v2)

1. **Numeric values were never retrieved (a bug in our port).** The authors' content index
   (`build_contents_index.py`) stores `str(value)` for every column, numbers included, and drops
   values longer than 25 characters. Our port kept only Python `str` values, so numbers in
   questions were never matched, and it did not apply the 25-character limit.
   **This changed the matched-contents block for 128 of 1034 prompts (12.4%).**
   Example: *"Find number of pets owned by students who are older than 20."* — ours:
   `matched contents : None`; authors: `student.age ( 20 )`.

2. **Column comments missing.** The authors build comments from Spider's `tables.json`
   (human-readable names, removed where they merely repeat the column name) and pass them to
   `get_db_schema`. We passed an empty dict. This affects 12 of 439 dev-set columns (3%).

3. **Different scoring metric.** The authors score Spider with the official test-suite evaluator
   (`test_suite_sql_eval/evaluation.py --etype exec`). That evaluator treats row order as
   significant when the gold query has `ORDER BY`, accepts permuted columns, and strips `DISTINCT`
   by default. Our metric compared sorted, stringified rows: it ignored row order (more lenient)
   but did not accept permuted columns or `1` vs `1.0` (stricter). **Our earlier EX numbers
   (64.8 / 71.7 / 73.8) were therefore not measured on the same scale as the paper's 77.9.**
   Harness v2 reports both metrics; the official one is the number to compare with the paper.
   The evaluator was verified locally: gold scored against itself gives 1.000.

4. **Predictions were not saved**, so earlier runs cannot be re-scored. Harness v2 writes every
   predicted SQL to `preds_<RUN_ID>.txt`.

## Remaining known deviations (documented, not fixed)

- Coarse retrieval: Lucene BM25 (top-10 hits per question n-gram) is replaced by a scan of all
  distinct values. The candidate set is a superset of the authors', so the matched contents can
  include extra values, and their order in the prompt may differ.
- The schema item classifier (top-6 tables / top-10 columns) is not applied.
- Library versions: torch 2.11 / transformers 5.16 instead of the pinned 1.13.1 / 4.28.1.

## Consequence for the logged numbers

The earlier runs stay in the log: they are real measurements of the harness as it was. They are
**not** directly comparable with the paper, because of discrepancies 1 and 3. The ablation deltas
in `week7_ablation_study.md` remain valid as *relative* comparisons, since every run shared the same
harness and metric, but should be re-measured with harness v2 before going in the final report.
